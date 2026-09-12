"""VN Lookup — Decky plugin backend.

Pipeline per trigger press: capture frame via gamescope's PipeWire source →
OCR (local RapidOCR in a venv subprocess, or Gemini Vision) → rule-based
cleanup → broadcast to the texthooker page (Yomitan hovers it there) →
remember the screenshot so new Anki cards get enriched with it.
"""

import asyncio
import base64
import os
import time

import decky

from vnlookup import cleanup
from vnlookup.anki import AnkiConnect, AnkiError
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
        self.anki = AnkiConnect(self.settings.get("ankiconnect_url"))
        self.dictionary = Dictionary(
            os.path.join(RUNTIME_DIR, "dictionary.sqlite3"),
            os.path.join(RUNTIME_DIR, "dicts"))
        self._token_cache = {"text": None, "tokens": []}

        self._busy = False
        self._last_result = None
        # pending capture waiting to be attached to the next Anki note
        self._pending_capture = None
        self._anki_last_note_seen = int(time.time() * 1000)
        self._anki_attempts = {}  # note_id -> failed enrichment attempts

        os.makedirs(CAPTURES_DIR, exist_ok=True)
        self.monitor.start()
        try:
            await self.delivery.start()
        except Exception as e:
            logger.error(f"delivery server failed to start: {e}")

        self._anki_task = asyncio.get_event_loop().create_task(self._anki_watcher())
        logger.info("VN Lookup backend up")

    async def _unload(self):
        monitor = getattr(self, "monitor", None)
        if monitor:
            # stop() joins the reader thread; keep it off the event loop
            await asyncio.to_thread(monitor.stop)
        if getattr(self, "_anki_task", None):
            self._anki_task.cancel()
        delivery = getattr(self, "delivery", None)
        if delivery:
            await delivery.stop()

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

    def _areas_for(self, appid: str | None):
        """This game's capture areas, or the Default list if it has none."""
        profiles = self.settings.get("capture_profiles") or {}
        profile = profiles.get(str(appid)) if appid else None
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
        cleaned = cleanup.clean_ocr_text(
            raw_text, remove_speaker=bool(self.settings.get("strip_speaker_name")))

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

        # 5. remember for Anki enrichment
        crop_exists = os.path.exists(crop_png)
        self._pending_capture = {
            "ts": ts,
            "sentence": cleaned,
            "full": full_png,
            "crop": crop_png if crop_exists else full_png,
        }
        self._prune_captures()

        payload = {
            "text": cleaned,
            "raw": raw_text,
            "confidence": round(confidence, 3),
            "clients": self.delivery.client_count,
            "copy_to_clipboard": bool(self.settings.get("copy_to_clipboard")),
            "auto_open_qam": bool(self.settings.get("auto_open_qam")),
            "warning": warning,
        }
        self._last_result = payload
        await self._emit("done", **payload)
        return {"ok": True, **payload}

    def _prune_captures(self):
        # full + crop per capture; never below one capture's worth
        keep = max(2, int(self.settings.get("screenshot_history")) * 2)
        pending = self._pending_capture or {}
        protected = {pending.get("full"), pending.get("crop")}
        try:
            files = sorted(
                (os.path.join(CAPTURES_DIR, f) for f in os.listdir(CAPTURES_DIR)),
                key=os.path.getmtime, reverse=True)
            for f in files[keep:]:
                if f not in protected:
                    os.remove(f)
        except OSError as e:
            logger.warning(f"capture pruning failed: {e}")

    # ---- Anki enrichment -------------------------------------------------

    async def _anki_watcher(self):
        """Attach screenshot/sentence to Yomitan-created notes."""
        while True:
            try:
                await asyncio.sleep(3)
                if not self.settings.get("anki_enabled"):
                    continue
                if not self.settings.get("anki_auto_enrich"):
                    continue
                pending = self._pending_capture
                if not pending:
                    continue
                # stop watching 15 min after the last capture
                if time.time() * 1000 - pending["ts"] > 15 * 60 * 1000:
                    self._pending_capture = None
                    continue
                try:
                    new_notes = await self.anki.notes_created_after(
                        max(self._anki_last_note_seen, pending["ts"]))
                except AnkiError:
                    continue  # Anki not running — fine, try later
                for note_id in new_notes:
                    image = (pending["crop"]
                             if self.settings.get("anki_image") == "crop"
                             else pending["full"])
                    try:
                        wrote = await self.anki.enrich_note(
                            note_id, image, pending["sentence"],
                            picture_field=self.settings.get("anki_picture_field"),
                            sentence_field=self.settings.get("anki_sentence_field"))
                        logger.info(f"enriched note {note_id}: {wrote}")
                        self._anki_last_note_seen = max(
                            self._anki_last_note_seen, note_id)
                        self._anki_attempts.pop(note_id, None)
                        await self._emit("anki", note_id=note_id, **wrote)
                    except AnkiError as e:
                        # transient errors retry next tick; give up after 3
                        # so a bad field name can't loop forever
                        tries = self._anki_attempts.get(note_id, 0) + 1
                        self._anki_attempts[note_id] = tries
                        logger.warning(
                            f"note enrichment failed (try {tries}/3): {e}")
                        if tries >= 3:
                            self._anki_last_note_seen = max(
                                self._anki_last_note_seen, note_id)
                            self._anki_attempts.pop(note_id, None)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"anki watcher error: {e}")

    async def enrich_latest_note(self):
        """Manual fallback: attach the last capture to the newest note."""
        if not self.settings.get("anki_enabled"):
            return {"ok": False, "error": "Anki integration is disabled in settings"}
        pending = self._pending_capture
        if not pending:
            return {"ok": False, "error": "no capture to attach"}
        try:
            ids = await self.anki.invoke("findNotes", query="added:1")
            if not ids:
                return {"ok": False, "error": "no notes added today"}
            note_id = max(ids)
            image = (pending["crop"] if self.settings.get("anki_image") == "crop"
                     else pending["full"])
            wrote = await self.anki.enrich_note(
                note_id, image, pending["sentence"],
                picture_field=self.settings.get("anki_picture_field"),
                sentence_field=self.settings.get("anki_sentence_field"))
            # don't let the auto-watcher enrich the same note again
            self._anki_last_note_seen = max(self._anki_last_note_seen, note_id)
            return {"ok": True, "note_id": note_id, **wrote}
        except AnkiError as e:
            return {"ok": False, "error": str(e)}

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
                               glosses: str, sentence: str):
        """Direct card creation from the native lookup panel."""
        s = self.settings
        if not s.get("anki_enabled"):
            return {"ok": False, "error": "Anki integration is disabled in settings"}
        fields = {}
        for field_key, value in (
            ("anki_expression_field", expression),
            ("anki_reading_field", reading),
            ("anki_glossary_field", glosses),
            ("anki_sentence_field", sentence),
        ):
            name = (s.get(field_key) or "").strip()
            if name:
                fields[name] = value or ""

        picture_field = (s.get("anki_picture_field") or "").strip()
        pending = self._pending_capture
        picture_path = None
        if picture_field and pending:
            fields.setdefault(picture_field, "")
            picture_path = (pending["crop"] if s.get("anki_image") == "crop"
                            else pending["full"])

        if not fields:
            return {"ok": False,
                    "error": "no Anki fields configured in settings"}
        try:
            note_id = await self.anki.add_note(
                s.get("anki_deck"), s.get("anki_note_type"), fields,
                picture_path=picture_path, picture_field=picture_field)
            # keep the Yomitan-watcher from enriching this card again
            self._anki_last_note_seen = max(self._anki_last_note_seen, note_id)
            return {"ok": True, "note_id": note_id}
        except AnkiError as e:
            return {"ok": False, "error": str(e)}

    # ---- setup / status callables -----------------------------------------

    async def get_status(self):
        anki_ok = (await self.anki.is_available()
                   if self.settings.get("anki_enabled") else False)
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
            "anki_available": anki_ok,
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
        if key == "ankiconnect_url":
            self.anki = AnkiConnect(value)
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
