"""Steam Deck controller button monitor via /dev/hidraw.

Ported from cat-in-a-box/Decky-Translator (main.py HidrawButtonMonitor).
Reading raw HID reports is what makes the back buttons (L4/L5/R4/R5)
visible at all — Steam intercepts them before any higher-level API.

Only the Deck's built-in controller (VID 28DE / PID 1205, interface :1.2)
and the InputPlumber virtual controller (PID 12FB) are supported.
"""

import fcntl
import logging
import os
import queue
import select
import struct
import threading
import time

logger = logging.getLogger(__name__)


class HidrawButtonMonitor:
    VALVE_VID = 0x28DE
    STEAMDECK_PID = 0x1205
    INPUTPLUMBER_PID = 0x12FB
    PACKET_SIZE = 64

    # HID feature reports sent once on open. CLEAR_DIGITAL_MAPPINGS disables
    # "lizard mode" (kb/mouse emulation) on this interface; without it the
    # back buttons never appear in the report stream.
    ID_CLEAR_DIGITAL_MAPPINGS = 0x81
    ID_SET_SETTINGS_VALUES = 0x87
    SETTING_LEFT_TRACKPAD_MODE = 0x07
    SETTING_RIGHT_TRACKPAD_MODE = 0x08
    TRACKPAD_NONE = 0x07
    SETTING_STEAM_WATCHDOG_ENABLE = 0x2D

    def _hidiocsfeature(self, size):
        return 0xC0000000 | (size << 16) | (ord('H') << 8) | 0x06

    # Button masks - ButtonsL (bytes 8-11, uint32 LE)
    BUTTONS_L = {
        'R2': 0x00000001,
        'L2': 0x00000002,
        'R1': 0x00000004,
        'L1': 0x00000008,
        'Y': 0x00000010,
        'B': 0x00000020,
        'X': 0x00000040,
        'A': 0x00000080,
        'DPAD_UP': 0x00000100,
        'DPAD_RIGHT': 0x00000200,
        'DPAD_LEFT': 0x00000400,
        'DPAD_DOWN': 0x00000800,
        'SELECT': 0x00001000,
        'STEAM': 0x00002000,
        'START': 0x00004000,
        'L5': 0x00008000,
        'R5': 0x00010000,
        'LEFT_PAD_TOUCH': 0x00080000,
        'RIGHT_PAD_TOUCH': 0x00100000,
        'L3': 0x00400000,
        'R3': 0x04000000,
    }

    # Button masks - ButtonsH (bytes 12-15, uint32 LE)
    BUTTONS_H = {
        'L4': 0x00000200,
        'R4': 0x00000400,
        'QAM': 0x00040000,
    }

    def __init__(self):
        self.device_fd = None
        self.device_path = None
        self.device_pid = None
        self.running = False
        self.thread = None
        self.event_queue = queue.Queue(maxsize=100)
        self.current_buttons = set()
        self.last_buttons_l = 0
        self.last_buttons_h = 0
        self.error_count = 0
        self.initialized = False
        self.lock = threading.Lock()

    def find_device(self):
        steamdeck_candidates = []
        inputplumber_candidates = []

        for i in range(10):
            path = f'/dev/hidraw{i}'
            if not os.path.exists(path):
                continue
            uevent_path = f'/sys/class/hidraw/hidraw{i}/device/uevent'
            try:
                with open(uevent_path) as f:
                    content = f.read().upper()
                if '28DE' not in content:
                    continue
                if '1205' in content:
                    steamdeck_candidates.append((i, path))
                elif '12FB' in content:
                    inputplumber_candidates.append((i, path))
            except Exception as e:
                logger.debug(f"Cannot read uevent for hidraw{i}: {e}")

        if steamdeck_candidates:
            # The gamepad data lives on USB interface :1.2
            for i, path in steamdeck_candidates:
                try:
                    link_target = os.readlink(f'/sys/class/hidraw/hidraw{i}')
                    if ':1.2/' in link_target:
                        logger.info(f"Steam Deck gamepad interface at {path}")
                        self.device_pid = self.STEAMDECK_PID
                        return path
                except Exception:
                    pass
            # Fallback: any candidate that has data waiting
            for _i, path in steamdeck_candidates:
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                    try:
                        readable, _, _ = select.select([fd], [], [], 0.1)
                        if readable:
                            os.read(fd, 64)
                            os.close(fd)
                            self.device_pid = self.STEAMDECK_PID
                            return path
                        os.close(fd)
                    except Exception:
                        os.close(fd)
                except Exception:
                    pass
            path = steamdeck_candidates[-1][1]
            self.device_pid = self.STEAMDECK_PID
            return path

        if inputplumber_candidates:
            path = inputplumber_candidates[-1][1]
            self.device_pid = self.INPUTPLUMBER_PID
            return path

        logger.warning("No Steam Deck controller hidraw device found")
        return None

    def send_feature_report(self, data):
        if self.device_fd is None:
            return False
        try:
            buf = bytes(data) + bytes(64 - len(data))
            fcntl.ioctl(self.device_fd, self._hidiocsfeature(64), buf)
            return True
        except Exception as e:
            logger.error(f"Failed to send feature report: {e}")
            return False

    def initialize_device(self):
        if self.device_path is None:
            self.device_path = self.find_device()
            if self.device_path is None:
                return False
        try:
            self.device_fd = os.open(self.device_path, os.O_RDWR)
            if self.device_pid == self.STEAMDECK_PID:
                if not self.send_feature_report([self.ID_CLEAR_DIGITAL_MAPPINGS]):
                    logger.warning("Failed to send CLEAR_DIGITAL_MAPPINGS")
                settings_cmd = [
                    self.ID_SET_SETTINGS_VALUES,
                    3,
                    self.SETTING_LEFT_TRACKPAD_MODE, self.TRACKPAD_NONE,
                    self.SETTING_RIGHT_TRACKPAD_MODE, self.TRACKPAD_NONE,
                    self.SETTING_STEAM_WATCHDOG_ENABLE, 0,
                ]
                if not self.send_feature_report(settings_cmd):
                    logger.warning("Failed to send SET_SETTINGS_VALUES")
            self.initialized = True
            logger.info(f"Opened {self.device_path} for button monitoring")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize hidraw device: {e}")
            if self.device_fd is not None:
                try:
                    os.close(self.device_fd)
                except Exception:
                    pass
                self.device_fd = None
            return False

    def start(self):
        if self.running:
            return True
        if not self.initialize_device():
            return False
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None
        if self.device_fd is not None:
            try:
                os.close(self.device_fd)
            except Exception:
                pass
            self.device_fd = None
        self.initialized = False

    def _monitor_loop(self):
        reconnect_delay = 2.0
        max_errors = 10
        while self.running:
            try:
                if ((not self.initialized or self.device_fd is None)
                        and not self.initialize_device()):
                    time.sleep(reconnect_delay)
                    continue
                r, _, _ = select.select([self.device_fd], [], [], 0.1)
                if not r:
                    continue
                data = os.read(self.device_fd, self.PACKET_SIZE)
                if len(data) >= 16:
                    self._process_packet(data)
                    self.error_count = 0
            except OSError as e:
                self.error_count += 1
                logger.warning(f"hidraw read error ({self.error_count}): {e}")
                if self.error_count >= max_errors:
                    self._close_device()
                    time.sleep(reconnect_delay)
            except Exception as e:
                logger.error(f"Unexpected error in hidraw loop: {e}")
                self.error_count += 1
                time.sleep(0.1)

    def _close_device(self):
        if self.device_fd is not None:
            try:
                os.close(self.device_fd)
            except Exception:
                pass
            self.device_fd = None
        self.initialized = False
        self.device_path = None
        self.device_pid = None

    def _process_packet(self, data):
        buttons_l = struct.unpack('<I', data[8:12])[0]
        buttons_h = struct.unpack('<I', data[12:16])[0]
        if buttons_l == self.last_buttons_l and buttons_h == self.last_buttons_h:
            return

        timestamp = time.time()
        new_buttons = set()
        for name, mask in self.BUTTONS_L.items():
            if buttons_l & mask:
                new_buttons.add(name)
        for name, mask in self.BUTTONS_H.items():
            if buttons_h & mask:
                new_buttons.add(name)

        with self.lock:
            for button in self.current_buttons - new_buttons:
                self._enqueue({"button": button, "pressed": False, "timestamp": timestamp})
            for button in new_buttons - self.current_buttons:
                self._enqueue({"button": button, "pressed": True, "timestamp": timestamp})
            self.current_buttons = new_buttons

        self.last_buttons_l = buttons_l
        self.last_buttons_h = buttons_h

    def _enqueue(self, event):
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            try:
                self.event_queue.get_nowait()
                self.event_queue.put_nowait(event)
            except Exception:
                pass

    def get_button_state(self):
        with self.lock:
            return list(self.current_buttons)

    def get_status(self):
        with self.lock:
            return {
                "running": self.running,
                "initialized": self.initialized,
                "device_path": self.device_path,
                "error_count": self.error_count,
                "current_buttons": list(self.current_buttons),
            }
