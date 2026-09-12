"""VN Lookup — Decky plugin backend.

Pipeline per trigger press: capture frame via gamescope's PipeWire source →
OCR (local RapidOCR in a venv subprocess, or Gemini Vision) → rule-based
cleanup → broadcast to the texthooker page (Yomitan hovers it there).
Anki cards (native lookup path) are buffered locally and exported as a
batch .apkg on demand, scanned onto a phone via QR code.
"""

import asyncio
import base64
import os
import time

import decky

from vnlookup import cleanup
from vnlookup.anki_export import AnkiExportError, build_apkg
from vnlookup.anki_server import AnkiExportServer
from vnlookup.buffer import PendingCards
from vnlookup.capture import CaptureError, ScreenCapture
from vnlookup.deliver import DeliveryServer
from vnlookup.deps import RuntimeInstaller
from vnlookup.dictionary import Dictionary
from vnlookup.hid_monitor import HidrawButtonMonitor
from vnlookup.models import ModelDownloader
from vnlookup.ocr import GeminiBackend, OCRError, RapidOCRBackend, tokenize
from vnlookup.settings import Settings

logger = decky.logger

RUNTIME_DIR = decky.DECKY_PLUGIN_RUNTIME_DIR
SETTINGS_DIR = decky.DECKY_PLUGIN_SETTINGS_DIR
PLUGIN_DIR = decky.DECKY_PLUGIN_DIR
CAPTURES_DIR = os.path.join(RUNTIME_DIR, "captures")

# fallback shapes used only by the one-time capture_areas migration below
# and as the starting point for newly-added areas
_LEGACY_REGION = {"x": 0.03, "y": 0.62, "w": 0.94, "h": 0.36}
_LEGACY_REGION_ALT = {"x": 0.1, "y": 0.08, "w": 0.8, "h": 0.84}


class Plugin:
    async def _main(self):
        self.settings = Settings(SETTINGS_DIR)
        if not self.settings.get("capture_areas"):
            # migrate from the region/region_alt/button_map (or even older
            # single trigger_button) era into the capture_areas list
            legacy_map = self.settings.get("button_map")
            if not legacy_map:
                legacy_map = {self.settings.get("trigger_button") or "L5": "box"}
            region = self.settings.get("region") or _LEGACY_REGION
            region_alt = self.settings.get("region_alt") or _LEGACY_REGION_ALT
            areas = [
                {"region": region if mode == "box" else region_alt, "button": button}
                for button, mode in legacy_map.items()
                if mode in ("box", "alt")
            ]
            self.settings.set("capture_areas", areas or [{"region": region, "button": None}])
        self.installer = RuntimeInstaller(RUNTIME_DIR)
        self.downloader = ModelDownloader(RUNTIME_DIR)
        self.capture = ScreenCapture(
            gst_plugin_path=os.path.join(PLUGIN_DIR, "bin", "gstreamer-1.0"),
            lib_path=os.path.join(PLUGIN_DIR, "bin"),
        )
        self.monitor = HidrawButtonMonitor()
        self.delivery = DeliveryServer(port=int(self.settings.get("texthooker_port")))
        self.anki_buffer = PendingCards(RUNTIME_DIR)
        self.anki_server = AnkiExportServer()
        self.dictionary = Dictionary(
            os.path.join(RUNTIME_DIR, "dictionary.sqlite3"),
            os.path.join(RUNTIME_DIR, "dicts"))
        self._token_cache = {"text": None, "tokens": []}

        self._busy = False
        self._last_result = None

        os.makedirs(CAPTURES_DIR, exist_ok=True)
        self.monitor.start()
        try:
            await self.delivery.start()
        except Exception as e:
            logger.error(f"delivery server failed to start: {e}")

        logger.info("VN Lookup backend up")

    async def _unload(self):
        monitor = getattr(self, "monitor", None)
        if monitor:
            # stop() joins the reader thread; keep it off the event loop
            await asyncio.to_thread(monitor.stop)
        delivery = getattr(self, "delivery", None)
        if delivery:
            await delivery.stop()
        anki_server = getattr(self, "anki_server", None)
        if anki_server:
            await anki_server.stop()

    async def _uninstall(self):
        pass

    # ---- events to frontend --------------------------------------------

    async def _emit(self, stage: str, **payload):
        await decky.emit("vnl_event", {"stage": stage, **payload})

    # ---- trigger support -------------------------------------------------

    async def get_button_state(self):
        return {"success": True, "buttons": self.monitor.get_button_state()}

    # ---- the pipeline ----------------------------------------------------

    async def capture_and_mine(self, button: str | None = None, appid: str | None = None):
        if self._busy:
            return {"ok": False, "error": "capture already in progress"}
        self._busy = True
        try:
            return await self._run_pipeline(button, appid)
        finally:
            self._busy = False

    # bucket for captures with no Steam appid to key by — matches
    # UNKNOWN_APP_KEY in src/api.ts
    UNKNOWN_PROFILE_KEY = "unknown"

    def _areas_for(self, appid: str | None):
        """This game's capture areas, or the Default list if it has none."""
        profiles = self.settings.get("capture_profiles") or {}
        key = str(appid) if appid else self.UNKNOWN_PROFILE_KEY
        profile = profiles.get(key)
        areas = profile.get("areas") if profile else None
        return areas or self.settings.get("capture_areas") or []

    async def _run_pipeline(self, button: str | None = None, appid: str | None = None):
        ts = int(time.time() * 1000)
        full_png = os.path.join(CAPTURES_DIR, f"capture_{ts}.png")
        crop_png = os.path.join(CAPTURES_DIR, f"crop_{ts}.png")

        # 1. capture — give the compositor a beat before grabbing the frame
        await self._emit("capturing")
        await asyncio.sleep(0.15)
        try:
            await self.capture.capture_png(full_png)
        except CaptureError as e:
            # No pngenc in the system GStreamer: grab a raw RGB frame and
            # let the venv (Pillow) encode it instead.
            if "pngenc" in str(e) and self.installer.is_installed():
                try:
                    raw, (w, h) = await self.capture.capture_raw_rgb()
                    encoder = RapidOCRBackend(self.installer.python,
                                              self.downloader.target_dir)
                    await encoder.encode_raw(raw, w, h, full_png)
                except (CaptureError, OCRError) as e2:
                    await self._emit("error", message=f"Capture failed: {e2}")
                    return {"ok": False, "error": str(e2)}
            else:
                await self._emit("error", message=f"Capture failed: {e}")
                return {"ok": False, "error": str(e)}

        # 2. OCR — the trigger button picks which capture area gets cropped.
        # region rides along on the "ocr" event so the frontend can outline
        # the area actively being scanned, directly over the running game.
        backend_name = self.settings.get("ocr_backend")
        area = next(
            (a for a in self._areas_for(appid) if a.get("button") == button),
            None)
        region = area["region"] if area else None
        await self._emit("ocr", region=region)

        runtime_ok = self.installer.is_installed()
        cloud_full_frame = False
        try:
            if backend_name == "gemini":
                image_for_ocr = full_png
                crop_path = None
                if region and runtime_ok:
                    # crop locally so the cloud sees only the text box
                    local = RapidOCRBackend(self.installer.python,
                                            self.downloader.target_dir)
                    try:
                        crop_path = await local.crop(full_png, region, crop_png)
                        image_for_ocr = crop_path
                    except OCRError as e:
                        logger.warning(f"crop failed, sending full frame: {e}")
                        cloud_full_frame = True
                elif region:
                    cloud_full_frame = True
                gemini = GeminiBackend(self.settings.get("gemini_api_key"),
                                       self.settings.get("gemini_model"))
                result = await gemini.recognize(image_for_ocr, crop_out=crop_path)
            else:
                if not runtime_ok:
                    msg = ("Local OCR runtime not installed — install it in "
                           "the VN Lookup settings panel")
                    await self._emit("error", message=msg)
                    return {"ok": False, "error": msg}
                if not self.downloader.is_installed():
                    msg = ("OCR models not downloaded — download them in the "
                           "VN Lookup settings panel")
                    await self._emit("error", message=msg)
                    return {"ok": False, "error": msg}
                local = RapidOCRBackend(self.installer.python,
                                        self.downloader.target_dir)
                result = await local.recognize(
                    full_png, region=region, crop_out=crop_png,
                    min_confidence=float(self.settings.get("min_confidence")))
        except OCRError as e:
            await self._emit("error", message=f"OCR failed: {e}")
            return {"ok": False, "error": str(e)}

        raw_text = result.text
        confidence = result.mean_confidence

        # 3. cleanup — first drop UI chrome (Auto/Skip/…) around the box,
        # then normalize. raw_text keeps the unfiltered read for debugging.
        kept, dropped = cleanup.filter_ui_regions(result.regions)
        if dropped:
            logger.info(f"dropped UI fragments: {dropped}")
            result.regions = kept
        cleaned = cleanup.clean_ocr_text(raw_text, remove_speaker=False)

        if not cleaned:
            # total OCR miss: nothing detected in the region. Still record
            # this as the last result (empty text) so the polled sidebar
            # can show a "no text found" notice instead of a stale sentence
            self._last_result = {
                "text": "", "raw": raw_text, "confidence": round(confidence, 3)}
            msg = "No text detected in the capture region"
            await self._emit("error", message=msg, raw=raw_text)
            return {"ok": False, "error": msg, "raw": raw_text}

        warning = None
        if not cleanup.looks_like_japanese(cleaned):
            warning = "Text doesn't look Japanese — check the capture region"
        elif cloud_full_frame:
            warning = ("Region crop unavailable — the FULL screen was sent "
                       "to the cloud OCR")

        # 4. deliver (clipboard copy happens frontend-side, in Steam's CEF —
        # gamescope propagates it to the other XWayland windows)
        await self.delivery.broadcast(cleaned)

        self._prune_captures()

        payload = {
            "text": cleaned,
            "raw": raw_text,
            "confidence": round(confidence, 3),
            "clients": self.delivery.client_count,
            "copy_to_clipboard": bool(self.settings.get("copy_to_clipboard")),
            "auto_open_qam": True,
            "warning": warning,
        }
        self._last_result = payload
        await self._emit("done", **payload)
        return {"ok": True, **payload}

    def _prune_captures(self):
        # full + crop per capture; never below one capture's worth
        keep = max(2, int(self.settings.get("screenshot_history")) * 2)
        try:
            files = sorted(
                (os.path.join(CAPTURES_DIR, f) for f in os.listdir(CAPTURES_DIR)),
                key=os.path.getmtime, reverse=True)
            for f in files[keep:]:
                os.remove(f)
        except OSError as e:
            logger.warning(f"capture pruning failed: {e}")

    # ---- visual region editor ----------------------------------------------
    # The editor works on the LATEST pipeline capture, never a fresh frame:
    # a fresh capture would photograph the editor modal itself (the PipeWire
    # source is the composited screen, UI included). Pipeline captures are
    # taken in-game with no UI up, so they're always clean.

    def _latest_capture_path(self):
        """Newest clean frame: pipeline captures or the editor's refresh."""
        try:
            files = [os.path.join(CAPTURES_DIR, f)
                     for f in os.listdir(CAPTURES_DIR)
                     if f.startswith("capture_")]
            preview = os.path.join(RUNTIME_DIR, "preview.png")
            if os.path.exists(preview):
                files.append(preview)
            return max(files, key=os.path.getmtime) if files else None
        except OSError:
            return None

    async def get_editor_frame(self):
        """Latest clean full-frame capture for the region editor."""
        path = self._latest_capture_path()
        if not path:
            return {"ok": False,
                    "error": "no capture yet — use Refresh frame, or hold "
                             "your capture button in-game"}
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return {"ok": True, "image": b64}

    async def capture_editor_frame(self):
        """Fresh frame for the editor. Only call with all UI closed — the
        frontend choreographs: close modal + QAM, wait, capture, reopen."""
        if self._busy:
            return {"ok": False, "error": "capture already in progress"}
        self._busy = True
        try:
            path = os.path.join(RUNTIME_DIR, "preview.png")
            await self.capture.capture_png(path)
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return {"ok": True, "image": b64}
        except CaptureError as e:
            return {"ok": False, "error": str(e)}
        finally:
            self._busy = False

    async def detect_region(self):
        """Snap a region to the Japanese text in the latest capture."""
        if not (self.installer.is_installed() and self.downloader.is_installed()):
            return {"ok": False,
                    "error": "auto-detect needs the local OCR runtime + models"}
        path = self._latest_capture_path()
        if not path:
            return {"ok": False,
                    "error": "no capture yet — hold your capture button "
                             "in-game first"}
        if self._busy:
            return {"ok": False, "error": "capture already in progress"}
        self._busy = True
        try:
            local = RapidOCRBackend(self.installer.python,
                                    self.downloader.target_dir)
            result = await local.recognize(
                path, region=None,
                min_confidence=float(self.settings.get("min_confidence")))
            if not result.image_size:
                return {"ok": False, "error": "OCR returned no image size"}
            width, height = result.image_size

            # prefer Japanese lines of some substance; fall back to any text
            candidates = [r for r in result.regions
                          if cleanup.looks_like_japanese(r["text"], 0.25)
                          and len(r["text"]) >= 3] or result.regions
            # drop button/hint bars (Auto | Skip | Log…) sitting near the
            # text box — they OCR as real Japanese, so the length filter
            # above doesn't catch them; only their layout does
            without_chrome = cleanup.drop_ui_chrome_rows(candidates)
            if without_chrome:
                candidates = without_chrome
            if not candidates:
                return {"ok": False, "error": "no text detected on screen"}

            left = min(r["rect"]["left"] for r in candidates) / width
            top = min(r["rect"]["top"] for r in candidates) / height
            right = max(r["rect"]["right"] for r in candidates) / width
            bottom = max(r["rect"]["bottom"] for r in candidates) / height
            pad = 0.02
            region = {
                "x": max(0.0, round(left - pad, 4)),
                "y": max(0.0, round(top - pad, 4)),
            }
            region["w"] = min(1.0 - region["x"], round(right - left + 2 * pad, 4))
            region["h"] = min(1.0 - region["y"], round(bottom - top + 2 * pad, 4))

            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return {"ok": True, "region": region, "image": b64}
        except (CaptureError, OCRError) as e:
            return {"ok": False, "error": str(e)}
        finally:
            self._busy = False

    # ---- native lookup (Phase C: no Yomitan needed) ------------------------

    async def tokenize_line(self, text: str):
        """Split a sentence into word tokens with dictionary-form keys."""
        if not text:
            return {"ok": False, "error": "no text"}
        if not self.installer.is_lookup_installed():
            return {"ok": False,
                    "error": "lookup runtime not installed"}
        if self._token_cache["text"] == text:
            return {"ok": True, "tokens": self._token_cache["tokens"]}
        try:
            tokens = await tokenize(self.installer.python, text)
        except OCRError as e:
            return {"ok": False, "error": str(e)}
        self._token_cache = {"text": text, "tokens": tokens}
        return {"ok": True, "tokens": tokens}

    async def lookup_word(self, queries):
        """Look a word up by candidate keys, best-first.

        `queries` come from a token: [dict_form, lemma, surface, reading].
        UniDic marks loanword lemmas like データ-data; strip the suffix.
        """
        cleaned = []
        for q in queries or []:
            if not q:
                continue
            q = q.split("-")[0] if "-" in q and not q.startswith("-") else q
            if q and q not in cleaned:
                cleaned.append(q)
        entries = await asyncio.to_thread(self.dictionary.lookup, cleaned)
        return {"ok": True, "entries": entries}

    async def lookup_selection(self, text: str):
        """Longest-prefix lookup for merged token selections."""
        exact = await asyncio.to_thread(self.dictionary.lookup, [text])
        if exact:
            return {"ok": True, "entries": exact}
        entries = await asyncio.to_thread(
            self.dictionary.longest_prefix_lookup, text)
        return {"ok": True, "entries": entries}

    async def get_lookup_status(self):
        return {
            "runtime_installed": self.installer.is_lookup_installed(),
            "runtime": self.installer.get_status(),
            "dictionary": self.dictionary.get_status(),
        }

    async def install_lookup_runtime(self):
        return {"started": self.installer.start_install_lookup()}

    async def import_dictionaries(self, download_jitendex: bool = False):
        return {"started": self.dictionary.start_import(download_jitendex)}

    async def create_anki_card(self, expression: str, reading: str,
                               glosses: str, sentence: str, game: str = ""):
        """Buffer a card for later batch export as a .apkg via QR code."""
        if not self.settings.get("anki_enabled"):
            return {"ok": False, "error": "Anki integration is disabled in settings"}
        self.anki_buffer.add(expression, reading, glosses, sentence, game)
        return {"ok": True, "buffered": self.anki_buffer.count()}

    async def clear_anki_buffer(self):
        self.anki_buffer.clear()
        return {"ok": True}

    async def get_anki_buffer(self):
        return {"cards": self.anki_buffer.all()}

    async def install_anki_export_runtime(self):
        return {"started": self.installer.start_install_anki()}

    async def export_anki_buffer(self):
        """Package the buffer into a .apkg and serve it over the LAN for a
        QR-code scan. Does not clear the buffer — that's a separate,
        explicit action."""
        if not self.anki_buffer.count():
            return {"ok": False, "error": "No buffered cards to export"}
        if not self.installer.is_anki_installed():
            return {"ok": False, "error": "Anki export runtime not installed",
                    "needs_install": True}
        s = self.settings
        field_map = {}
        for role, key in (
            ("expression", "anki_expression_field"),
            ("reading", "anki_reading_field"),
            ("glossary", "anki_glossary_field"),
            ("sentence", "anki_sentence_field"),
            ("game", "anki_game_field"),
        ):
            name = (s.get(key) or "").strip()
            if name:
                field_map[role] = name
        if not field_map:
            return {"ok": False,
                    "error": "no Anki fields configured in settings"}

        out_path = os.path.join(RUNTIME_DIR, "anki_export.apkg")
        try:
            await build_apkg(self.installer.python, self.anki_buffer.all(),
                             s.get("anki_deck"), s.get("anki_note_type"),
                             field_map, out_path)
        except AnkiExportError as e:
            return {"ok": False, "error": str(e)}
        try:
            url = await self.anki_server.start(out_path)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "url": url, "count": self.anki_buffer.count()}

    # ---- setup / status callables -----------------------------------------

    async def get_status(self):
        probe = {}
        try:
            probe = await self.capture.probe()
        except Exception as e:
            probe = {"error": str(e)}
        return {
            "monitor": self.monitor.get_status(),
            "runtime": self.installer.get_status(),
            "models": self.downloader.get_status(),
            "capture": probe,
            "delivery": {
                "port": self.delivery.port,
                "clients": self.delivery.client_count,
            },
            "anki_buffered": self.anki_buffer.count(),
            "last_result": self._last_result,
            "busy": self._busy,
        }

    async def install_runtime(self):
        return {"started": self.installer.start_install()}

    async def get_runtime_status(self):
        return self.installer.get_status()

    async def download_models(self):
        return {"started": self.downloader.start_download()}

    async def get_models_status(self):
        return self.downloader.get_status()

    async def cancel_models_download(self):
        self.downloader.cancel()
        return {"ok": True}

    async def test_line(self):
        """Send a test sentence to connected texthooker pages."""
        text = "これはテストです。辞書で調べてみてください。"
        await self.delivery.broadcast(text)
        return {"ok": True, "clients": self.delivery.client_count}

    # ---- settings ----------------------------------------------------------

    async def get_all_settings(self):
        return self.settings.all()

    async def set_setting(self, key, value):
        self.settings.set(key, value)
        if key == "texthooker_port":
            await self.delivery.stop()
            self.delivery = DeliveryServer(port=int(value))
            try:
                await self.delivery.start()
            except Exception as e:
                logger.error(f"delivery restart failed: {e}")
        # let every frontend instance (trigger watcher) pick up the change
        await decky.emit("vnl_settings", self.settings.all())
        return {"ok": True}
