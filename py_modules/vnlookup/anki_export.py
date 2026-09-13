"""Build a .apkg file from buffered cards via a subprocess worker — genanki
runs only under the runtime venv, never imported into the Decky process.
"""

import hashlib
import json
import logging
import os

from .worker import run_json_worker

logger = logging.getLogger(__name__)

WORKER = os.path.join(os.path.dirname(__file__), "anki_export_worker.py")
EXPORT_TIMEOUT = 60

# Folded into the model_id salt so a template/CSS change (see
# anki_export_worker.py) mints a brand-new note type on export. AnkiMobile's
# .apkg import keeps an existing note type's template/CSS as-is on an ID
# match, so reusing the ID would never deliver a design update. With a new
# ID, existing notes stay on their (possibly user-customized) old note type
# and only newly-exported cards use the new one. Bump on every default
# template/CSS change.
#
# 4: reading is now enabled by default and shares the large .r-expression
# style (both the field set and the CSS changed).
TEMPLATE_VERSION = 4


class AnkiExportError(Exception):
    """apkg build failed — surface to the user."""


def stable_id(salt: str, name: str) -> int:
    """Deterministic genanki deck/model id derived from a configured name,
    so the same deck/note-type name always maps to the same id across
    exports — otherwise every export would mint a new deck/note type on
    import instead of merging into the previous one."""
    digest = hashlib.sha256(f"{salt}:{name}".encode()).hexdigest()
    return int(digest[:15], 16)


async def build_apkg(venv_python: str, cards: list[dict], deck_name: str,
                     note_type_name: str, field_map: dict, out_path: str) -> None:
    """field_map maps role -> configured field name, e.g.
    {"expression": "Front", "glossary": "Back"} — blank-named roles are
    already excluded by the caller."""
    opts = {
        "cards": cards,
        "deck_name": deck_name,
        "deck_id": stable_id("vnlookup-deck", deck_name),
        "note_type_name": note_type_name,
        "model_id": stable_id(f"vnlookup-model-v{TEMPLATE_VERSION}", note_type_name),
        "field_map": field_map,
        "out_path": out_path,
    }
    result = await run_json_worker(
        venv_python, WORKER, [],
        label="apkg worker", error_cls=AnkiExportError, timeout=EXPORT_TIMEOUT,
        stdin_bytes=json.dumps(opts, ensure_ascii=False).encode())
    if result.get("error"):
        trace = result.get("trace")
        if trace:
            logger.error(f"apkg worker trace: {trace}")
        raise AnkiExportError(result["error"])
