"""Screen capture inside gamescope, via the PipeWire video source.

Ported from cat-in-a-box/Decky-Translator. The plugin backend runs under
plugin_loader.service with no graphical environment, so we synthesize one
(XDG_RUNTIME_DIR / WAYLAND_DISPLAY / DBUS address) and read frames from
gamescope's PipeWire Video/Source node with gst-launch-1.0.

Primary path: gst pngenc writes a PNG directly. Fallback (no pngenc in the
system GStreamer): dump one raw RGB frame to stdout and let the caller
encode it — encoding needs Pillow, which lives in the OCR venv, not here.
"""

import asyncio
import contextlib
import glob
import json
import logging
import os
import signal
from asyncio.subprocess import PIPE

logger = logging.getLogger(__name__)

MIN_VALID_SIZE = 30_000  # real captures run 100KB+; tiny PNGs are corrupt frames
MAX_ATTEMPTS = 3
GST_TIMEOUT = 2.5


class CaptureError(Exception):
    """Capture failed in a way the user should see."""


class ScreenCapture:
    def __init__(self, gst_plugin_path: str = "", lib_path: str = ""):
        # Optional dirs with bundled gstreamer plugins/libs; ignored if absent.
        self._gst_plugin_path = gst_plugin_path if os.path.isdir(gst_plugin_path) else ""
        self._lib_path = lib_path if os.path.isdir(lib_path) else ""
        self._session_env = None
        self._has_pngenc = None
        self._source_dims = None

    # -- environment -----------------------------------------------------

    def _load_session_env(self):
        uid = os.getuid()
        desktop_comms = {'plasmashell', 'kwin_wayland', 'kwin_x11', 'gnome-shell', 'sway', 'Hyprland'}
        for proc_path in glob.glob('/proc/[0-9]*'):
            try:
                if os.stat(proc_path).st_uid != uid:
                    continue
                with open(os.path.join(proc_path, 'comm')) as f:
                    if f.read().strip() not in desktop_comms:
                        continue
                with open(os.path.join(proc_path, 'environ'), 'rb') as f:
                    data = f.read()
            except (OSError, PermissionError):
                continue
            result = {}
            for entry in data.split(b'\0'):
                if not entry:
                    continue
                k, _, v = entry.decode(errors='ignore').partition('=')
                if k:
                    result[k] = v
            return result
        return {}

    def build_env(self):
        if self._session_env is None:
            self._session_env = self._load_session_env()
        uid = os.getuid()
        xdg_runtime = f"/run/user/{uid}"
        env = os.environ.copy()
        for k, v in self._session_env.items():
            env.setdefault(k, v)
        env.setdefault("XDG_RUNTIME_DIR", xdg_runtime)
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={xdg_runtime}/bus")
        env.setdefault("WAYLAND_DISPLAY", "gamescope-0")
        env["XDG_SESSION_TYPE"] = "wayland"
        if self._gst_plugin_path:
            env["GST_PLUGIN_PATH"] = self._gst_plugin_path
        if self._lib_path:
            env["LD_LIBRARY_PATH"] = self._lib_path
        return env

    # -- probes -----------------------------------------------------------

    async def probe(self):
        """Return diagnostics: pipewire source present, pngenc present, dims."""
        env = self.build_env()
        has_source = False
        dims = None
        try:
            proc = await asyncio.create_subprocess_exec(
                '/usr/bin/pw-dump', stdout=PIPE, stderr=PIPE, env=env)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
            nodes = json.loads(out)
            gamescope_dims = None
            first_dims = None
            for n in nodes:
                info = n.get('info') or {}
                props = info.get('props') or {}
                if props.get('media.class') != 'Video/Source':
                    continue
                has_source = True
                for fmt in (info.get('params') or {}).get('EnumFormat', []):
                    sz = fmt.get('size') or {}
                    w, h = sz.get('width'), sz.get('height')
                    if not (w and h):
                        continue
                    if props.get('node.name') == 'gamescope':
                        gamescope_dims = (w, h)
                    if first_dims is None:
                        first_dims = (w, h)
                    break
            dims = gamescope_dims or first_dims
        except Exception as e:
            logger.warning(f"pw-dump probe failed: {e}")

        if self._has_pngenc is None:
            try:
                probe = await asyncio.create_subprocess_exec(
                    '/usr/bin/gst-inspect-1.0', '--exists', 'pngenc',
                    stdout=PIPE, stderr=PIPE, env=env)
                await asyncio.wait_for(probe.communicate(), timeout=2.0)
                self._has_pngenc = (probe.returncode == 0)
            except Exception as e:
                logger.warning(f"pngenc probe failed ({e})")
                self._has_pngenc = False

        self._source_dims = dims
        return {
            "pipewire_source": has_source,
            "pngenc": self._has_pngenc,
            "dims": dims,
        }

    # -- capture ----------------------------------------------------------

    async def capture_png(self, screenshot_path: str) -> str:
        """Capture a full frame to `screenshot_path` (PNG). Returns the path.

        Raises CaptureError with a human-readable message on failure.
        """
        env = self.build_env()
        if self._has_pngenc is None:
            await self.probe()

        if not self._has_pngenc:
            raise CaptureError(
                "GStreamer pngenc not available — raw capture fallback "
                "requires the OCR runtime (install it in plugin settings)")

        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        last_error = "unknown error"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if attempt > 1:
                await asyncio.sleep(0.3)
            if os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                except OSError:
                    pass

            proc = await asyncio.create_subprocess_exec(
                'gst-launch-1.0', '-e',
                'pipewiresrc', 'do-timestamp=true', 'num-buffers=5', '!',
                'videoconvert', '!',
                'pngenc', 'snapshot=true', '!',
                'filesink', f'location={screenshot_path}',
                stdout=PIPE, stderr=PIPE, env=env)
            try:
                _, err = await asyncio.wait_for(proc.communicate(), timeout=GST_TIMEOUT)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.send_signal(signal.SIGINT)
                try:
                    _, err = await asyncio.wait_for(proc.communicate(), timeout=1)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
                    _, err = await proc.communicate()

            stderr_output = err.decode().strip()
            if "target not found" in stderr_output:
                # source node is gone (mode switch); retrying won't help
                raise CaptureError("PipeWire video source not found — is a game running?")

            if not os.path.exists(screenshot_path):
                last_error = f"no file produced (gst: {stderr_output[-200:] or 'no output'})"
                continue
            size = os.path.getsize(screenshot_path)
            if size < MIN_VALID_SIZE:
                last_error = f"frame too small ({size} bytes) — corrupt capture"
                continue
            return screenshot_path

        raise CaptureError(f"Capture failed after {MAX_ATTEMPTS} attempts: {last_error}")

    async def capture_raw_rgb(self):
        """Fallback: one raw RGB frame. Returns (bytes, (w, h))."""
        env = self.build_env()
        if self._source_dims is None:
            await self.probe()
        if self._source_dims is None:
            raise CaptureError("Could not determine screen resolution from PipeWire")
        w, h = self._source_dims
        expected = w * h * 3

        for attempt in range(1, MAX_ATTEMPTS + 1):
            # 5 buffers like the PNG path: the first pipewiresrc frames are
            # warmup garbage. We keep only the final frame from stdout.
            proc = await asyncio.create_subprocess_exec(
                'gst-launch-1.0', '-q', '-e',
                'pipewiresrc', 'do-timestamp=true', 'num-buffers=5', '!',
                'videoconvert', '!', 'video/x-raw,format=RGB', '!',
                'fdsink', 'fd=1',
                stdout=PIPE, stderr=PIPE, env=env)
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=GST_TIMEOUT)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                out, err = await proc.communicate()

            if b"target not found" in err:
                raise CaptureError("PipeWire video source not found — is a game running?")
            if len(out) >= expected and len(out) % expected == 0:
                return out[-expected:], (w, h)
            # resolution may have changed (dock/undock) — reprobe
            self._source_dims = None
            await self.probe()
            if self._source_dims is None:
                break
            w, h = self._source_dims
            expected = w * h * 3

        raise CaptureError("Raw frame capture failed (unexpected frame size)")
