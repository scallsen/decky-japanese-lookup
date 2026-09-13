"""Build a .apkg file from buffered cards via a subprocess worker — genanki
runs only under the runtime venv, never imported into the Decky process
(mirrors ocr.py's worker-invocation convention).
"""

import asyncio
import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

WORKER = os.path.join(os.path.dirname(__file__), "anki_export_worker.py")
EXPORT_TIMEOUT = 60

# Folded into the model_id salt so a deliberate template/CSS change (see
# anki_export_worker.py) mints a brand-new note type on export instead of
# colliding with whatever's already in the user's collection. This turned
# out to be necessary, not just defensive: AnkiMobile's package import
# keeps an existing note type's template/CSS as-is on an ID match — it
# does not appear to consult the model's mod-time for plain .apkg imports
# (that comparison, if it happens at all, is a sync-only thing) — so the
# frozen-timestamp trick alone does not get a shipped design update into
# an already-imported collection. A new ID sidesteps needing to know
# either way: existing notes/cards stay exactly as they are (on the old
# note type, however the user may have since customized it), and only
# newly-exported cards land on the new one. Bump this — any change is
# fine — every time the default template/CSS changes.
TEMPLATE_VERSION = 3


class AnkiExportError(Exception):
    """apkg build failed — surface to the user."""


def stable_id(salt: str, name: str) -> int:
    """Deterministic genanki deck/model id derived from a configured name,
    so the same deck/note-type name always maps to the same id across
    exports — otherwise every export would mint a new deck/note type on
    import instead of merging into the previous one."""
    digest = hashlib.sha256(f"{salt}:{name}".encode()).hexdigest()
    return int(digest[:15], 16)


def _worker_env():
    # Clean env: Decky's LD_LIBRARY_PATH/PYTHONPATH must not leak into the
    # venv interpreter or the wrong shared libs get loaded.
    env = {k: v for k, v in os.environ.items()
           if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME")}
    env["PYTHONNOUSERSITE"] = "1"
    return env


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
    proc = await asyncio.create_subprocess_exec(
        venv_python, WORKER,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_worker_env(),
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input=json.dumps(opts, ensure_ascii=False).encode()),
            timeout=EXPORT_TIMEOUT)
    except TimeoutError as e:
        proc.kill()
        await proc.communicate()
        raise AnkiExportError(f"apkg export timed out after {EXPORT_TIMEOUT}s") from e
    if not out.strip():
        tail = err.decode(errors="replace").strip()[-400:]
        raise AnkiExportError(f"apkg worker produced no output: {tail or 'no stderr'}")
    last_line = out.strip().splitlines()[-1]
    try:
        result = json.loads(last_line)
    except json.JSONDecodeError as e:
        raise AnkiExportError(f"apkg worker output not JSON: {last_line[:200]!r}") from e
    if result.get("error"):
        trace = result.get("trace", "")
        if trace:
            logger.error(f"apkg worker trace: {trace}")
        raise AnkiExportError(result["error"])
