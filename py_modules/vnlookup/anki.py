"""AnkiConnect client (stdlib urllib, async via to_thread).

Yomitan creates the card; we enrich it afterwards with the game screenshot
(and the sentence, if Yomitan left the field empty). Note IDs are creation
timestamps in ms, which is how we find "cards created after this capture".
"""

import asyncio
import base64
import json
import logging
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class AnkiError(Exception):
    pass


class AnkiConnect:
    def __init__(self, url: str = "http://127.0.0.1:8765"):
        self.url = url

    def _invoke_sync(self, action: str, **params):
        body = json.dumps({"action": action, "version": 6,
                           "params": params}).encode()
        req = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("error"):
            raise AnkiError(data["error"])
        return data.get("result")

    async def invoke(self, action: str, **params):
        try:
            return await asyncio.to_thread(self._invoke_sync, action, **params)
        except (urllib.error.URLError, OSError) as e:
            raise AnkiError(f"AnkiConnect unreachable: {e}") from e

    async def is_available(self) -> bool:
        try:
            await self.invoke("version")
            return True
        except AnkiError:
            return False

    async def add_note(self, deck: str, model: str, fields: dict,
                       picture_path: str = None, picture_field: str = None) -> int:
        """Create a note directly (native lookup path — no Yomitan).

        Returns the new note id. The screenshot rides along at creation
        time, so no watcher round-trip is needed for these cards.
        """
        note = {
            "deckName": deck,
            "modelName": model,
            "fields": fields,
            "options": {"allowDuplicate": True},
        }
        if picture_path and picture_field and picture_field in fields:
            try:
                with open(picture_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                note["fields"] = {k: v for k, v in fields.items()
                                  if k != picture_field}
                note["picture"] = [{
                    "filename": f"vnlookup_{int(time.time() * 1000)}.png",
                    "data": b64,
                    "fields": [picture_field],
                }]
            except OSError as e:
                logger.warning(f"screenshot unreadable, card without it: {e}")
        result = await self.invoke("addNote", note=note)
        if not result:
            raise AnkiError("addNote returned no note id")
        return int(result)

    async def notes_created_after(self, since_ms: int):
        ids = await self.invoke("findNotes", query="added:1")
        return sorted(i for i in ids if i > since_ms)

    async def enrich_note(self, note_id: int, screenshot_path: str,
                          sentence: str, picture_field: str = "Picture",
                          sentence_field: str = "Sentence") -> dict:
        """Attach screenshot to `picture_field`; fill `sentence_field` if empty.

        Returns {"picture": bool, "sentence": bool} for what was written.
        """
        info = await self.invoke("notesInfo", notes=[note_id])
        if not info:
            raise AnkiError(f"note {note_id} not found")
        fields = info[0].get("fields", {})
        wrote = {"picture": False, "sentence": False}

        if picture_field in fields and screenshot_path:
            try:
                with open(screenshot_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
            except OSError as e:
                raise AnkiError(f"screenshot unreadable: {e}") from e
            fname = f"vnlookup_{note_id}_{int(time.time())}.png"
            await self.invoke("storeMediaFile", filename=fname, data=b64)
            await self.invoke("updateNoteFields", note={
                "id": note_id,
                "fields": {picture_field: f'<img src="{fname}">'},
            })
            wrote["picture"] = True
        elif screenshot_path:
            logger.warning(
                f"note {note_id} has no field named '{picture_field}' — "
                f"available: {list(fields.keys())}")

        if (sentence and sentence_field in fields
                and not fields[sentence_field]["value"].strip()):
            await self.invoke("updateNoteFields", note={
                "id": note_id,
                "fields": {sentence_field: sentence},
            })
            wrote["sentence"] = True

        return wrote
