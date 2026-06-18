from __future__ import annotations

from dataclasses import dataclass
import ctypes
import re
import sys
import time

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None

try:
    import win32gui  # type: ignore
    import win32process  # type: ignore
except Exception:  # pragma: no cover - optional Windows dependency
    win32gui = None
    win32process = None


DOMAIN_RE = re.compile(r"(?<!@)\b([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b", re.IGNORECASE)


@dataclass
class ActivitySnapshot:
    title: str
    process_name: str
    pid: int | None
    domain: str
    idle_seconds: int
    captured_at: float
    supported: bool = True


class ActivityMonitor:
    def current(self) -> ActivitySnapshot:
        title = ""
        process_name = ""
        pid: int | None = None
        supported = sys.platform == "win32" and win32gui is not None and win32process is not None

        if supported:
            try:
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd) or ""
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process_name = self._process_name(pid)
            except Exception:
                supported = False

        return ActivitySnapshot(
            title=title,
            process_name=process_name.lower(),
            pid=pid,
            domain=extract_domain(title),
            idle_seconds=get_idle_seconds(),
            captured_at=time.time(),
            supported=supported,
        )

    def _process_name(self, pid: int | None) -> str:
        if not pid or psutil is None:
            return ""
        try:
            return psutil.Process(pid).name()
        except Exception:
            return ""


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds() -> int:
    if sys.platform != "win32":
        return 0
    try:
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):  # type: ignore[attr-defined]
            return 0
        millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime  # type: ignore[attr-defined]
        return max(0, int(millis / 1000))
    except Exception:
        return 0


def extract_domain(title: str) -> str:
    text = title.lower()
    matches = [match.group(1).removeprefix("www.") for match in DOMAIN_RE.finditer(text)]
    ignored = {"microsoft.com", "google.com"}
    for domain in matches:
        if domain not in ignored:
            return domain
    return ""
