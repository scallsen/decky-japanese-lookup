"""Removing what the plugin downloaded — on request, and on uninstall.

Decky only deletes ~/homebrew/plugins/<folder> when a plugin is removed;
the data, settings and log dirs it hands the plugin are left for the
plugin's own _uninstall() to clean up. Two Decky behaviors shape how:

- Updating also runs _uninstall(): "Install from zip"/store updates
  uninstall the old copy right before unzipping the new one, so deleting
  data there would throw away ~800 MB of downloads on every update.
- The plugin process is SIGKILLed 5s after being asked to stop — not enough
  to reliably delete a venv with tens of thousands of files.

So _uninstall() only spawns a detached watcher (this file, run standalone
under the system python) that outlives the plugin process and watches the
plugins folder: if the plugin goes away and stays gone, it was an
uninstall and everything is deleted; if it comes back, it was an update
and nothing is touched.

Must stay runnable standalone: stdlib only at module level, no relative
imports outside spawn_uninstall_cleanup().
"""

import json
import os
import shutil
import subprocess
import sys
import time

# Runtime-dir entries "Delete downloaded data" leaves alone: the Anki queue
# is the user's own work, not a download.
KEEP_ON_DATA_DELETE = frozenset({"anki_buffer.json"})

POLL_S = 0.5
# Continuous absence this long means uninstall. This plugin isn't on the
# Decky store, so "update" in practice means a human manually re-running
# Install from zip. 15s was calibrated for a store-style atomic swap and
# measurably too short: it mistook a real reinstall for an uninstall and
# deleted live data mid-install. A real reinstall on a Deck measures ~5s
# end to end (old copy gone -> new copy loaded); 30s gives a comfortable
# 6x margin over that without leaving data exposed to the reboot-during-
# the-window edge case (a real reboot/shutdown kills the detached watcher
# before it can act) any longer than it needs to.
GONE_CONFIRM_S = 30.0
# Never seeing the plugin gone within this long means either a reinstall
# that's taking unusually long, or an uninstall that failed — keep the
# data in both cases (silently keeping data too long is recoverable via
# "Delete downloaded data"; wrongly deleting it isn't).
MAX_WAIT_S = 150.0

# Filled in lazily by spawn_uninstall_cleanup(), never referenced at module
# scope (this file's own source is also exec()'d verbatim in the detached
# child process via `python -c "exec(sys.stdin.read())"`, where __file__
# isn't defined at all — keeping this None-until-needed avoids ever
# touching __file__ from that context).
_OWN_SOURCE: str | None = None


def downloaded_data_paths(runtime_dir: str) -> list[str]:
    """Everything in the runtime dir except what the user created."""
    try:
        names = sorted(os.listdir(runtime_dir))
    except FileNotFoundError:
        return []
    return [os.path.join(runtime_dir, n) for n in names if n not in KEEP_ON_DATA_DELETE]


def disk_usage(paths: list[str]) -> int:
    total = 0
    for path in paths:
        if os.path.isdir(path) and not os.path.islink(path):
            for root, _dirs, files in os.walk(path):
                for name in files:
                    try:
                        total += os.lstat(os.path.join(root, name)).st_size
                    except OSError:
                        pass
        else:
            try:
                total += os.lstat(path).st_size
            except OSError:
                pass
    return total


def remove_paths(paths: list[str]) -> list[tuple[str, str]]:
    """Best-effort delete. Previously used shutil.rmtree(..., ignore_errors=True),
    which silently swallows any failure (permission error, a file still open,
    one bad entry among tens of thousands in a venv) — the caller would log
    "removed" regardless of whether anything on disk actually changed.
    Returns (path, error) for anything left behind, so callers can tell a
    real success from one that only looked like one."""
    failures = []
    for path in paths:
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            failures.append((path, str(e)))
    return failures


def plugin_installed(plugins_root: str, plugin_name: str) -> bool:
    """Whether any folder under plugins_root has a plugin.json naming us.

    Matched by name rather than folder, so a reinstall into a differently
    named folder still counts as "still installed". An unreadable plugins
    folder also counts as installed: when unsure, keep the data.
    """
    try:
        entries = os.listdir(plugins_root)
    except OSError:
        return True
    for entry in entries:
        try:
            with open(os.path.join(plugins_root, entry, "plugin.json"), encoding="utf-8") as f:
                if json.load(f).get("name") == plugin_name:
                    return True
        except (OSError, ValueError, AttributeError):
            # not a plugin, or mid-unzip — the confirm window covers the latter
            continue
    return False


def was_uninstalled(is_installed, *, poll_s: float = POLL_S,
                    confirm_s: float = GONE_CONFIRM_S, max_wait_s: float = MAX_WAIT_S,
                    sleep=time.sleep, clock=time.monotonic) -> bool:
    """Watch the plugin after _uninstall(): True only if it disappears and
    stays gone for confirm_s. Reappearing, or never disappearing within
    max_wait_s, means it's still installed."""
    start = clock()
    gone_since = None
    while True:
        now = clock()
        if is_installed():
            if gone_since is not None:
                return False  # came back: update or reinstall
            if now - start >= max_wait_s:
                return False
        elif gone_since is None:
            gone_since = now
        elif now - gone_since >= confirm_s:
            return True
        sleep(poll_s)


def cleanup_after_uninstall(cfg: dict) -> str:
    """The detached watcher's job; returns a line for its log."""
    uninstalled = was_uninstalled(
        lambda: plugin_installed(cfg["plugins_root"], cfg["plugin_name"]),
        **cfg.get("timings", {}))
    if not uninstalled:
        return "plugin still installed (update or reinstall), kept its data"
    failures = remove_paths(cfg["paths"])
    if failures:
        detail = "; ".join(f"{p}: {e}" for p, e in failures)
        return f"plugin uninstalled, but FAILED to fully remove some paths: {detail}"
    return "plugin uninstalled, removed " + ", ".join(cfg["paths"])


def spawn_uninstall_cleanup(*, plugin_name: str, plugins_root: str, paths: list[str],
                            log_path: str, python: str | None = None,
                            timings: dict | None = None) -> subprocess.Popen:
    """Start the watcher in its own session, so it survives Decky killing
    the plugin process. The source is piped in over stdin rather than run
    from this file, because Decky deletes this file with the plugin folder."""
    from .deps import SYSTEM_PYTHON
    from .worker import worker_env

    global _OWN_SOURCE
    if _OWN_SOURCE is None:
        # Read once, as early as possible (first real call, normally right
        # after plugin startup) — this file may no longer exist on disk by
        # the time a later call needs it, if Decky has already removed the
        # plugin folder.
        with open(__file__, encoding="utf-8") as f:
            _OWN_SOURCE = f.read()

    cfg = {"plugin_name": plugin_name, "plugins_root": plugins_root,
           "paths": paths, "timings": timings or {}}
    with open(log_path, "a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [python or SYSTEM_PYTHON, "-c", "import sys; exec(sys.stdin.read())",
             json.dumps(cfg)],
            stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True, cwd="/", env=worker_env())
    # a few KB: fits the pipe buffer, so this never blocks on the child
    proc.stdin.write(_OWN_SOURCE.encode())
    proc.stdin.close()
    return proc


if __name__ == "__main__":
    config = json.loads(sys.argv[1])
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "watching", config["plugins_root"], flush=True)
    outcome = cleanup_after_uninstall(config)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), outcome, flush=True)
