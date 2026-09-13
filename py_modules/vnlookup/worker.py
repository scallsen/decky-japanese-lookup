"""Running helper scripts under the runtime venv's python.

Everything heavy (RapidOCR, fugashi, genanki) lives in the venv, never in
the Decky process. The *_worker.py scripts are spawned as subprocesses and
report back with a single JSON object on the last line of stdout.
"""

import asyncio
import json
import os


def worker_env() -> dict[str, str]:
    """os.environ minus Decky's library/python paths.

    Decky's LD_LIBRARY_PATH/PYTHONPATH must not leak into the venv
    interpreter (or pip), or the wrong shared libs get loaded.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME")}
    env["PYTHONNOUSERSITE"] = "1"
    return env


async def run_json_worker(venv_python: str, script: str, args: list[str], *,
                          label: str, error_cls: type[Exception], timeout: float,
                          stdin_bytes: bytes | None = None) -> dict:
    """Run `script` under the venv and return its JSON result.

    Raises `error_cls` (messages prefixed with `label`) on timeout, empty
    output, or unparseable output. A JSON result carrying an "error" key is
    returned as-is for the caller to interpret.
    """
    # (no -S here: the venv's site-packages are resolved by the site module)
    proc = await asyncio.create_subprocess_exec(
        venv_python, script, *args,
        stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=worker_env(),
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(input=stdin_bytes), timeout)
    except TimeoutError as e:
        proc.kill()
        await proc.communicate()
        raise error_cls(f"{label} timed out after {timeout}s") from e
    if not out.strip():
        tail = err.decode(errors="replace").strip()[-400:]
        raise error_cls(f"{label} produced no output: {tail or 'no stderr'}")
    # onnxruntime/opencv sometimes print banners to stdout on load; the
    # worker's JSON is always the last line
    last_line = out.strip().splitlines()[-1]
    try:
        return json.loads(last_line)
    except json.JSONDecodeError as e:
        raise error_cls(f"{label} output not JSON: {last_line[:200]!r}") from e
