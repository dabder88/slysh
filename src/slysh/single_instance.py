"""Single-instance lock tied to the app data directory."""
from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    import ctypes
    import msvcrt

    _kernel32 = ctypes.windll.kernel32
    _ERROR_ALREADY_EXISTS = 183
else:
    ctypes = None  # type: ignore[assignment]
    msvcrt = None  # type: ignore[assignment]


class SingleInstanceError(RuntimeError):
    pass


class SingleInstanceLock:
    def __init__(self, app_dir: Path) -> None:
        self._path = Path(app_dir) / ".slysh-instance.lock"
        self._handle = None
        self._mutex = None

    def acquire(self) -> None:
        if sys.platform == "win32" and ctypes is not None:
            self._mutex = _kernel32.CreateMutexW(None, True, "Local\\SlyshDesktopSingleInstance")
            if _kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
                if self._mutex:
                    _kernel32.CloseHandle(self._mutex)
                    self._mutex = None
                raise SingleInstanceError(
                    "Slysh уже запущен. Закройте другое окно или дождитесь завершения."
                )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("a+b")
        if msvcrt is not None:
            try:
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise SingleInstanceError(
                    "Slysh уже запущен. Закройте другое окно или дождитесь завершения."
                ) from None
        self._handle.seek(0)
        self._handle.write(str(os.getpid()).encode("ascii"))
        self._handle.flush()

    def release(self) -> None:
        if sys.platform == "win32" and self._mutex is not None and ctypes is not None:
            _kernel32.CloseHandle(self._mutex)
            self._mutex = None
        if self._handle is None:
            return
        if msvcrt is not None:
            try:
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        try:
            self._handle.close()
        except OSError:
            pass
        self._handle = None
