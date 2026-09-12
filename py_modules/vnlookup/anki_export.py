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
        "model_id": stable_id("vnlookup-model", note_type_name),
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
