"""VN Lookup — Decky plugin backend.

Pipeline per trigger press: capture frame via gamescope's PipeWire source →
OCR (local RapidOCR in a venv subprocess, or Gemini Vision) → rule-based
cleanup → broadcast to the texthooker page (Yomitan hovers it there) →
remember the screenshot so new Anki cards get enriched with it.
"""

import asyncio
import os
import time

import decky

from vnlookup import cleanup
from vnlookup.anki import AnkiConnect, AnkiError
from vnlookup.capture import CaptureError, ScreenCapture
from vnlookup.deliver import DeliveryServer
from vnlookup.deps import RuntimeInstaller
from vnlookup.hid_monitor import HidrawButtonMonitor
from vnlookup.models import ModelDownloader
from vnlookup.ocr import GeminiBackend, OCRError, RapidOCRBackend
from vnlookup.settings import Settings

logger = decky.logger

RUNTIME_DIR = decky.DECKY_PLUGIN_RUNTIME_DIR
SETTINGS_DIR = decky.DECKY_PLUGIN_SETTINGS_DIR
PLUGIN_DIR = decky.DECKY_PLUGIN_DIR
CAPTURES_DIR = os.path.join(RUNTIME_DIR, "captures")


class Plugin:
    async def _main(self):
        self.settings = Settings(SETTINGS_DIR)
        self.installer = RuntimeInstaller(RUNTIME_DIR)
        self.downloader = ModelDownloader(RUNTIME_DIR)
        self.capture = ScreenCapture(
            gst_plugin_path=os.path.join(PLUGIN_DIR, "bin", "gstreamer-1.0"),
            lib_path=os.path.join(PLUGIN_DIR, "bin"),
        )
        self.monitor = HidrawButtonMonitor()
        self.delivery = DeliveryServer(port=int(self.settings.get("texthooker_port")))
        self.anki = AnkiConnect(self.settings.get("ankiconnect_url"))

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

    async def capture_and_mine(self):
        if self._busy:
            return {"ok": False, "error": "capture already in progress"}
        self._busy = True
        try:
            return await self._run_pipeline()
        finally:
            self._busy = False

    async def _run_pipeline(self):
        ts = int(time.time() * 1000)
        full_png = os.path.join(CAPTURES_DIR, f"capture_{ts}.png")
        crop_png = os.path.join(CAPTURES_DIR, f"crop_{ts}.png")

        # 1. capture — the "capturing" event HIDES the overlay (it would be
        # photographed otherwise); give the compositor a beat to remove it
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

        # 2. OCR
        await self._emit("ocr")
        backend_name = self.settings.get("ocr_backend")
        region = None
        if self.settings.get("capture_mode") == "region":
            region = self.settings.get("region")

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
            # total OCR miss: nothing detected in the region
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

    # ---- setup / status callables -----------------------------------------

    async def get_status(self):
        anki_ok = await self.anki.is_available()
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
