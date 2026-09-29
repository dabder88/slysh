"""Lazy import of sounddevice (PortAudio) — avoids native init at UI startup."""
from __future__ import annotations

from typing import Any


class _SoundDeviceProxy:
    _mod: Any = None

    def _module(self):
        if self._mod is None:
            import sounddevice as sd

            self._mod = sd
        return self._mod

    def __getattr__(self, name: str):
        return getattr(self._module(), name)


sd = _SoundDeviceProxy()
