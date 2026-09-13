"""On-device runtime bootstrap.

Decky-Translator ships a CI-built tarball with a portable CPython; this
plugin instead builds a venv on the Deck itself with the system python and
pip-installs each stack into the home partition (survives SteamOS updates).

The venv python is only used for worker subprocesses (see worker.py) — the
Decky backend process never imports these packages.
"""

import logging
import os
import subprocess
import threading

from .worker import worker_env

logger = logging.getLogger(__name__)

SYSTEM_PYTHON = "/usr/bin/python3"

# OCR stack (~400 MB). Installed with `venv --clear`, so it also resets the
# other stacks' markers.
PACKAGES = ["rapidocr>=3.0,<4", "onnxruntime>=1.17"]
MARKER = ".vnlookup-runtime-ok"

# Lookup stack: morphological analyzer for tokenization/deinflection.
# Separate install (and marker) so OCR works without it and vice versa.
LOOKUP_PACKAGES = ["fugashi>=1.3", "unidic-lite>=1.0.8"]
LOOKUP_MARKER = ".vnlookup-lookup-ok"

# Anki export stack: builds .apkg files from the buffered-cards list.
ANKI_PACKAGES = ["genanki>=0.13,<0.14"]
ANKI_MARKER = ".vnlookup-anki-ok"


class RuntimeInstaller:
    def __init__(self, runtime_dir: str):
        self.venv_dir = os.path.join(runtime_dir, "venv")
        self.log_path = os.path.join(runtime_dir, "runtime-install.log")
        self._installing = False
        self._error = None
        self._step = ""
        self._lock = threading.Lock()

    @property
    def python(self) -> str:
        return os.path.join(self.venv_dir, "bin", "python3")

    def _has_marker(self, marker: str) -> bool:
        return (os.path.exists(self.python)
                and os.path.exists(os.path.join(self.venv_dir, marker)))

    def is_installed(self) -> bool:
        return self._has_marker(MARKER)

    def is_lookup_installed(self) -> bool:
        return self._has_marker(LOOKUP_MARKER)

    def is_anki_installed(self) -> bool:
        return self._has_marker(ANKI_MARKER)

    def get_status(self) -> dict:
        with self._lock:
            return {
                "installed": self.is_installed(),
                "lookup_installed": self.is_lookup_installed(),
                "anki_installed": self.is_anki_installed(),
                "installing": self._installing,
                "step": self._step,
                "error": self._error,
                "venv_dir": self.venv_dir,
            }

    # ---- entry points (each returns False if an install is already running)

    def start_install(self) -> bool:
        return self._start(MARKER, self._install_ocr)

    def start_install_lookup(self) -> bool:
        return self._start(LOOKUP_MARKER, lambda: self._install_extra(
            LOOKUP_PACKAGES, "installing tokenizer",
            "from fugashi import Tagger; Tagger()('テスト')", "verifying tokenizer"))

    def start_install_anki(self) -> bool:
        return self._start(ANKI_MARKER, lambda: self._install_extra(
            ANKI_PACKAGES, "installing genanki",
            "import genanki", "verifying genanki"))

    # ---- internals ---------------------------------------------------------

    def _start(self, marker: str, install) -> bool:
        with self._lock:
            if self._installing:
                return False
            self._installing = True
            self._error = None
            self._step = "starting"
        threading.Thread(target=self._guarded_install, args=(marker, install),
                         daemon=True).start()
        return True

    def _guarded_install(self, marker: str, install):
        """Run `install`, then write `marker` — only if every step succeeded."""
        marker_path = os.path.join(self.venv_dir, marker)
        try:
            if os.path.exists(marker_path):
                os.remove(marker_path)
            install()
            with open(marker_path, "w") as f:
                f.write("ok\n")
            self._set_step("done")
        except subprocess.CalledProcessError as e:
            with self._lock:
                self._error = (f"install step failed ({self._step}), "
                               f"see {self.log_path}: {e}")
            logger.error(self._error)
        except Exception as e:
            with self._lock:
                self._error = f"install failed during {self._step}: {e}"
            logger.error(self._error)
        finally:
            with self._lock:
                self._installing = False

    def _set_step(self, step: str):
        with self._lock:
            self._step = step
        logger.info(f"runtime install: {step}")

    def _run(self, args, step: str):
        self._set_step(step)
        env = worker_env()
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        with open(self.log_path, "a", encoding="utf-8") as log:
            log.write(f"\n==> {step}: {' '.join(args)}\n")
            log.flush()
            subprocess.run(
                args, stdout=log, stderr=subprocess.STDOUT,
                check=True, timeout=1800, env=env,
            )

    def _install_ocr(self):
        self._run([SYSTEM_PYTHON, "-m", "venv", "--clear", self.venv_dir],
                  "creating venv")
        pip = [self.python, "-m", "pip"]
        self._run([*pip, "install", "--upgrade", "pip"], "upgrading pip")
        self._run([*pip, "install", *PACKAGES], "installing OCR packages")
        # rapidocr pulls the GUI opencv build; swap for headless to save
        # ~60 MB and avoid GUI lib deps. Non-fatal if it was never pulled.
        try:
            self._run([*pip, "uninstall", "-y", "opencv-python"],
                      "removing opencv-python")
            self._run([*pip, "install", "opencv-python-headless"],
                      "installing opencv-headless")
        except subprocess.CalledProcessError:
            logger.warning("opencv headless swap failed; keeping default build")
        self._run([self.python, "-c", "import rapidocr, onnxruntime, cv2, PIL"],
                  "verifying imports")

    def _install_extra(self, packages: list[str], install_step: str,
                       verify_code: str, verify_step: str):
        """Add a package stack to the existing venv (creating one if needed)."""
        if not os.path.exists(self.python):
            self._run([SYSTEM_PYTHON, "-m", "venv", self.venv_dir], "creating venv")
        self._run([self.python, "-m", "pip", "install", *packages], install_step)
        self._run([self.python, "-c", verify_code], verify_step)
