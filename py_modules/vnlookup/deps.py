"""On-device OCR runtime bootstrap.

Decky-Translator ships a CI-built tarball with a portable CPython; for a
personal plugin it's simpler to build a venv on the Deck itself with the
system python and pip-install the OCR stack into the home partition
(survives SteamOS updates). ~400 MB on disk, one-time download.

The venv python is only used for the OCR worker subprocess — the Decky
backend process never imports these packages.
"""

import logging
import os
import subprocess
import threading

logger = logging.getLogger(__name__)

PACKAGES = ["rapidocr>=3.0,<4", "onnxruntime>=1.17"]
MARKER = ".vnlookup-runtime-ok"

# Lookup stack: morphological analyzer for tokenization/deinflection.
# Separate install (and marker) so OCR works without it and vice versa.
LOOKUP_PACKAGES = ["fugashi>=1.3", "unidic-lite>=1.0.8"]
LOOKUP_MARKER = ".vnlookup-lookup-ok"


class RuntimeInstaller:
    def __init__(self, runtime_dir: str):
        self.venv_dir = os.path.join(runtime_dir, "venv")
        self.log_path = os.path.join(runtime_dir, "runtime-install.log")
        self._installing = False
        self._error = None
        self._step = ""
        self._lock = threading.Lock()
        self._thread = None

    @property
    def python(self) -> str:
        return os.path.join(self.venv_dir, "bin", "python3")

    def is_installed(self) -> bool:
        return (os.path.exists(self.python)
                and os.path.exists(os.path.join(self.venv_dir, MARKER)))

    def is_lookup_installed(self) -> bool:
        return (os.path.exists(self.python)
                and os.path.exists(os.path.join(self.venv_dir, LOOKUP_MARKER)))

    def get_status(self) -> dict:
        with self._lock:
            return {
                "installed": self.is_installed(),
                "lookup_installed": self.is_lookup_installed(),
                "installing": self._installing,
                "step": self._step,
                "error": self._error,
                "venv_dir": self.venv_dir,
            }

    def _start(self, target) -> bool:
        with self._lock:
            if self._installing:
                return False
            self._installing = True
            self._error = None
            self._step = "starting"
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        return True

    def start_install(self) -> bool:
        return self._start(self._install)

    def start_install_lookup(self) -> bool:
        return self._start(self._install_lookup)

    def _set_step(self, step: str):
        with self._lock:
            self._step = step
        logger.info(f"runtime install: {step}")

    def _run(self, args, step: str):
        self._set_step(step)
        # same cleaned env the OCR worker runs with — Decky's
        # LD_LIBRARY_PATH/PYTHONPATH must not leak into venv/pip/verify
        env = {k: v for k, v in os.environ.items()
               if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD",
                            "PYTHONPATH", "PYTHONHOME")}
        env["PYTHONNOUSERSITE"] = "1"
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        with open(self.log_path, "a", encoding="utf-8") as log:
            log.write(f"\n==> {step}: {' '.join(args)}\n")
            log.flush()
            subprocess.run(
                args, stdout=log, stderr=subprocess.STDOUT,
                check=True, timeout=1800, env=env,
            )

    def _install(self):
        try:
            marker = os.path.join(self.venv_dir, MARKER)
            if os.path.exists(marker):
                os.remove(marker)
            self._run(["/usr/bin/python3", "-m", "venv", "--clear", self.venv_dir],
                      "creating venv")
            pip = [self.python, "-m", "pip"]
            self._run(pip + ["install", "--upgrade", "pip"], "upgrading pip")
            self._run(pip + ["install"] + PACKAGES, "installing OCR packages")
            # rapidocr pulls the GUI opencv build; swap for headless to save
            # ~60 MB and avoid GUI lib deps. Non-fatal if it was never pulled.
            try:
                self._run(pip + ["uninstall", "-y", "opencv-python"],
                          "removing opencv-python")
                self._run(pip + ["install", "opencv-python-headless"],
                          "installing opencv-headless")
            except subprocess.CalledProcessError:
                logger.warning("opencv headless swap failed; keeping default build")
            self._run([self.python, "-c", "import rapidocr, onnxruntime, cv2, PIL"],
                      "verifying imports")
            with open(marker, "w") as f:
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

    def _install_lookup(self):
        """Add the tokenizer stack to an existing venv (or create one)."""
        try:
            marker = os.path.join(self.venv_dir, LOOKUP_MARKER)
            if os.path.exists(marker):
                os.remove(marker)
            if not os.path.exists(self.python):
                self._run(["/usr/bin/python3", "-m", "venv", self.venv_dir],
                          "creating venv")
            pip = [self.python, "-m", "pip"]
            self._run(pip + ["install"] + LOOKUP_PACKAGES,
                      "installing tokenizer")
            self._run([self.python, "-c",
                       "from fugashi import Tagger; Tagger()('テスト')"],
                      "verifying tokenizer")
            with open(marker, "w") as f:
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
