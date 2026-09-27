"""WASAPI loopback capture via Windows Core Audio (ctypes).

python-sounddevice 0.5.x ships PortAudio without a loopback stream flag, so
system audio has to be opened through IAudioClient + AUDCLNT_STREAMFLAGS_LOOPBACK.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from ctypes import (
    POINTER,
    WINFUNCTYPE,
    Structure,
    byref,
    c_byte,
    c_int,
    c_uint,
    c_uint64,
    c_ulong,
    c_void_p,
    c_wchar_p,
    cast,
    string_at,
)
from ctypes import wintypes

import numpy as np

if sys.platform == "win32":
    from ctypes import windll
else:
    windll = None

log = logging.getLogger(__name__)

AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
DEVICE_STATE_ACTIVE = 0x1
STGM_READ = 0
CLSCTX_ALL = 0x17
COINIT_MULTITHREADED = 0x0
COINIT_APARTMENTTHREADED = 0x2
RPC_E_CHANGED_MODE = 0x80010106
S_OK = 0
S_FALSE = 1
E_RENDER = 0
E_CONSOLE = 0
WAVE_FORMAT_PCM = 1
WAVE_FORMAT_IEEE_FLOAT = 3
WAVE_FORMAT_EXTENSIBLE = 0xFFFE
VT_LPWSTR = 31
REFTIMES_PER_SEC = 10_000_000

CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IMMDevice = "{D666063F-1587-4E43-81F1-B948E807363F}"
IID_IAudioClient = "{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}"
IID_IAudioCaptureClient = "{C8ADBD64-E71E-48a0-A4DE-185C395CD317}"
IID_IPropertyStore = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"
PKEY_Device_FriendlyName = ("{A45C254E-DF1C-4EFD-8020-67D146A850E0}", 14)
KSDATAFORMAT_SUBTYPE_IEEE_FLOAT = "{00000003-0000-0010-8000-00AA00389B71}"
KSDATAFORMAT_SUBTYPE_PCM = "{00000001-0000-0010-8000-00AA00389B71}"


class GUID(Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class PROPERTYKEY(Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(Structure):
    _fields_ = [
        ("vt", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
        ("wReserved2", wintypes.WORD),
        ("wReserved3", wintypes.WORD),
        ("data", c_uint64),
    ]


class WAVEFORMATEX(Structure):
    _pack_ = 1
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


def _ole32():
    if windll is None:
        raise OSError("WASAPI only on Windows")
    ole32 = windll.ole32
    ole32.CoInitializeEx.argtypes = [c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = c_int
    ole32.CoUninitialize.argtypes = []
    ole32.CoCreateInstance.argtypes = [
        POINTER(GUID),
        c_void_p,
        wintypes.DWORD,
        POINTER(GUID),
        POINTER(c_void_p),
    ]
    ole32.CoCreateInstance.restype = c_int
    ole32.CoTaskMemFree.argtypes = [c_void_p]
    ole32.PropVariantClear.argtypes = [POINTER(PROPVARIANT)]
    ole32.PropVariantClear.restype = c_int
    return ole32


def _guid(text: str) -> GUID:
    hexpart = text.strip("{}").replace("-", "")
    data4 = (wintypes.BYTE * 8)(*[int(hexpart[16 + i * 2 : 18 + i * 2], 16) for i in range(8)])
    return GUID(
        int(hexpart[0:8], 16),
        int(hexpart[8:12], 16),
        int(hexpart[12:16], 16),
        data4,
    )


def _guid_str(guid: GUID) -> str:
    d4 = "".join(f"{b:02X}" for b in guid.Data4)
    return (
        f"{{{guid.Data1:08X}-{guid.Data2:04X}-{guid.Data3:04X}-"
        f"{d4[0:4]}-{d4[4:]}}}"
    )


def _vtbl(obj: c_void_p):
    return cast(cast(obj, POINTER(c_void_p))[0], POINTER(c_void_p))


def _method(obj: c_void_p, index: int, restype, *argtypes):
    proto = WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(_vtbl(obj)[index])


def _hr(value: int, what: str) -> None:
    code = value & 0xFFFFFFFF
    if code not in (S_OK, S_FALSE):
        raise OSError(f"{what} failed, HRESULT=0x{code:08X}")


def _release(obj: c_void_p | None) -> None:
    if not obj:
        return
    try:
        _method(obj, 2, c_ulong)(obj)
    except Exception:
        log.debug("COM Release failed", exc_info=True)


class _ComApartment:
    def __init__(self, sta: bool = False) -> None:
        self._uninit = False
        self._sta = sta

    def __enter__(self) -> _ComApartment:
        if sys.platform != "win32":
            raise OSError("WASAPI only on Windows")
        ole32 = _ole32()
        flag = COINIT_APARTMENTTHREADED if self._sta else COINIT_MULTITHREADED
        hr = ole32.CoInitializeEx(None, flag) & 0xFFFFFFFF
        if hr == S_OK:
            self._uninit = True
        elif hr in (S_FALSE, RPC_E_CHANGED_MODE):
            self._uninit = False
        else:
            raise OSError(f"CoInitializeEx failed, HRESULT=0x{hr:08X}")
        return self

    def __exit__(self, *exc) -> None:
        if self._uninit:
            _ole32().CoUninitialize()


def _create_enumerator() -> c_void_p:
    enumerator = c_void_p()
    hr = _ole32().CoCreateInstance(
        byref(_guid(CLSID_MMDeviceEnumerator)),
        None,
        CLSCTX_ALL,
        byref(_guid(IID_IMMDeviceEnumerator)),
        byref(enumerator),
    )
    _hr(hr, "CoCreateInstance(MMDeviceEnumerator)")
    return enumerator


def _device_id(device: c_void_p) -> str:
    raw = c_wchar_p()
    _hr(_method(device, 5, c_int, POINTER(c_wchar_p))(device, byref(raw)), "IMMDevice.GetId")
    try:
        return raw.value or ""
    finally:
        if raw:
            _ole32().CoTaskMemFree(raw)


def _device_name(device: c_void_p) -> str:
    store = c_void_p()
    _hr(
        _method(device, 4, c_int, wintypes.DWORD, POINTER(c_void_p))(
            device, STGM_READ, byref(store)
        ),
        "IMMDevice.OpenPropertyStore",
    )
    try:
        key = PROPERTYKEY(_guid(PKEY_Device_FriendlyName[0]), PKEY_Device_FriendlyName[1])
        prop = PROPVARIANT()
        _hr(
            _method(store, 5, c_int, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))(
                store, byref(key), byref(prop)
            ),
            "IPropertyStore.GetValue",
        )
        try:
            if prop.vt == VT_LPWSTR and prop.data:
                return c_wchar_p(prop.data).value or ""
            return ""
        finally:
            _ole32().PropVariantClear(byref(prop))
    finally:
        _release(store)


def _default_render_id(enumerator: c_void_p) -> str | None:
    device = c_void_p()
    hr = _method(enumerator, 4, c_int, c_int, c_int, POINTER(c_void_p))(
        enumerator, E_RENDER, E_CONSOLE, byref(device)
    )
    if hr & 0xFFFFFFFF != S_OK:
        return None
    try:
        return _device_id(device)
    finally:
        _release(device)


def _get_device(enumerator: c_void_p, endpoint_id: str) -> c_void_p:
    device = c_void_p()
    _hr(
        _method(enumerator, 5, c_int, c_wchar_p, POINTER(c_void_p))(
            enumerator, endpoint_id, byref(device)
        ),
        "IMMDeviceEnumerator.GetDevice",
    )
    return device


def list_render_endpoints() -> list[dict]:
    if sys.platform != "win32":
        return []
    with _ComApartment():
        enumerator = _create_enumerator()
        try:
            default_id = _default_render_id(enumerator)
            collection = c_void_p()
            _hr(
                _method(enumerator, 3, c_int, c_int, wintypes.DWORD, POINTER(c_void_p))(
                    enumerator, E_RENDER, DEVICE_STATE_ACTIVE, byref(collection)
                ),
                "EnumAudioEndpoints",
            )
            try:
                count = c_uint()
                _hr(_method(collection, 3, c_int, POINTER(c_uint))(collection, byref(count)), "GetCount")
                items: list[dict] = []
                for index in range(int(count.value)):
                    device = c_void_p()
                    hr = _method(collection, 4, c_int, c_uint, POINTER(c_void_p))(
                        collection, index, byref(device)
                    )
                    if hr & 0xFFFFFFFF != S_OK:
                        continue
                    try:
                        endpoint_id = _device_id(device)
                        name = _device_name(device).strip() or endpoint_id
                        items.append(
                            {
                                "id": endpoint_id,
                                "name": name,
                                "is_default": bool(default_id and endpoint_id == default_id),
                            }
                        )
                    finally:
                        _release(device)
                items.sort(key=lambda item: (not item["is_default"], item["name"].lower()))
                return items
            finally:
                _release(collection)
        finally:
            _release(enumerator)


def match_render_endpoint(device_id: str | int | None, name: str | None = None) -> str | None:
    endpoints = list_render_endpoints()
    if not endpoints:
        return None
    if isinstance(device_id, str) and device_id:
        for item in endpoints:
            if item["id"] == device_id:
                return item["id"]
    wanted = " ".join(str(name or "").lower().split())
    if wanted:
        for item in endpoints:
            if " ".join(item["name"].lower().split()) == wanted:
                return item["id"]
        for item in endpoints:
            current = " ".join(item["name"].lower().split())
            if wanted in current or current in wanted:
                return item["id"]
    for item in endpoints:
        if item["is_default"]:
            return item["id"]
    return endpoints[0]["id"]


def _pcm_from_wasapi(data_ptr: int, frames: int, fmt: WAVEFORMATEX, silent: bool, is_float: bool) -> np.ndarray:
    channels = max(1, int(fmt.nChannels))
    if silent or not data_ptr or frames <= 0:
        return np.zeros(max(0, frames) * channels, dtype=np.float32)
    nbytes = frames * int(fmt.nBlockAlign)
    raw = string_at(data_ptr, nbytes)
    bits = int(fmt.wBitsPerSample)
    if is_float or (int(fmt.wFormatTag) in (WAVE_FORMAT_IEEE_FLOAT, WAVE_FORMAT_EXTENSIBLE) and bits == 32):
        pcm = np.frombuffer(raw, dtype=np.float32)
    elif bits == 16:
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif bits == 32:
        pcm = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        pcm = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        pcm = (pcm - 128.0) / 128.0
    return np.asarray(pcm, dtype=np.float32)


def _mix_format_is_float(fmt_ptr: c_void_p) -> bool:
    fmt = cast(fmt_ptr, POINTER(WAVEFORMATEX)).contents
    if fmt.wFormatTag == WAVE_FORMAT_IEEE_FLOAT:
        return True
    if fmt.wFormatTag != WAVE_FORMAT_EXTENSIBLE:
        return False
    blob = string_at(fmt_ptr, 40)
    sub = GUID.from_buffer_copy(blob[24:40])
    return _guid_str(sub).upper() == KSDATAFORMAT_SUBTYPE_IEEE_FLOAT.upper()


class WasapiLoopback:
    def __init__(self, endpoint_id: str, on_frames) -> None:
        self.endpoint_id = endpoint_id
        self.on_frames = on_frames
        self.sample_rate = 48000
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._started = threading.Event()

    def start(self) -> int:
        self._stop.clear()
        self._error = None
        self._started.clear()
        self._thread = threading.Thread(target=self._run, name="wasapi-loopback", daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=8.0):
            self.stop()
            raise OSError(self._error or "WASAPI loopback не запустился.")
        if self._error:
            raise self._error
        return int(self.sample_rate)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        self._thread = None

    def _run(self) -> None:
        client = c_void_p()
        capture = c_void_p()
        mix_ptr = c_void_p()
        try:
            with _ComApartment(sta=True):
                enumerator = _create_enumerator()
                try:
                    device = _get_device(enumerator, self.endpoint_id)
                    try:
                        _hr(
                            _method(device, 3, c_int, POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p))(
                                device,
                                byref(_guid(IID_IAudioClient)),
                                CLSCTX_ALL,
                                None,
                                byref(client),
                            ),
                            "IMMDevice.Activate(IAudioClient)",
                        )
                    finally:
                        _release(device)
                finally:
                    _release(enumerator)

                _hr(
                    _method(client, 8, c_int, POINTER(c_void_p))(client, byref(mix_ptr)),
                    "IAudioClient.GetMixFormat",
                )
                fmt = WAVEFORMATEX.from_buffer_copy(string_at(mix_ptr, 18))
                self.sample_rate = int(fmt.nSamplesPerSec)
                init = _method(
                    client,
                    3,
                    c_int,
                    c_int,
                    wintypes.DWORD,
                    c_uint64,
                    c_uint64,
                    c_void_p,
                    c_void_p,
                )
                hr = init(
                    client,
                    AUDCLNT_SHAREMODE_SHARED,
                    AUDCLNT_STREAMFLAGS_LOOPBACK,
                    int(0.2 * REFTIMES_PER_SEC),
                    0,
                    mix_ptr,
                    None,
                )
                if hr & 0xFFFFFFFF != S_OK:
                    flags = (
                        AUDCLNT_STREAMFLAGS_LOOPBACK
                        | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM
                        | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY
                    )
                    _hr(
                        init(
                            client,
                            AUDCLNT_SHAREMODE_SHARED,
                            flags,
                            int(0.2 * REFTIMES_PER_SEC),
                            0,
                            mix_ptr,
                            None,
                        ),
                        "IAudioClient.Initialize(loopback)",
                    )
                _hr(
                    _method(client, 14, c_int, POINTER(GUID), POINTER(c_void_p))(
                        client, byref(_guid(IID_IAudioCaptureClient)), byref(capture)
                    ),
                    "IAudioClient.GetService(IAudioCaptureClient)",
                )
                default_period = c_uint64()
                min_period = c_uint64()
                _method(client, 9, c_int, POINTER(c_uint64), POINTER(c_uint64))(
                    client, byref(default_period), byref(min_period)
                )
                wait_s = max(0.005, float(default_period.value or 100000) / REFTIMES_PER_SEC / 2.0)
                _hr(_method(client, 10, c_int)(client), "IAudioClient.Start")
                self._started.set()
                is_float = _mix_format_is_float(mix_ptr)
                empty_polls = 0
                while not self._stop.is_set():
                    packet = c_uint()
                    hr = _method(capture, 5, c_int, POINTER(c_uint))(capture, byref(packet))
                    if (hr & 0xFFFFFFFF) != S_OK or packet.value == 0:
                        empty_polls += 1
                        if empty_polls in (1, 50, 200):
                            log.debug(
                                "WASAPI loopback empty poll hr=0x%08X packet=%s",
                                hr & 0xFFFFFFFF,
                                packet.value,
                            )
                        time.sleep(wait_s)
                        continue
                    empty_polls = 0
                    data = POINTER(c_byte)()
                    frames = c_uint()
                    flags_out = wintypes.DWORD()
                    hr = _method(
                        capture,
                        3,
                        c_int,
                        POINTER(POINTER(c_byte)),
                        POINTER(c_uint),
                        POINTER(wintypes.DWORD),
                        c_void_p,
                        c_void_p,
                    )(capture, byref(data), byref(frames), byref(flags_out), None, None)
                    if (hr & 0xFFFFFFFF) != S_OK:
                        log.debug("WASAPI GetBuffer hr=0x%08X", hr & 0xFFFFFFFF)
                        time.sleep(wait_s)
                        continue
                    try:
                        silent = bool(int(flags_out.value) & AUDCLNT_BUFFERFLAGS_SILENT)
                        ptr = cast(data, c_void_p).value or 0
                        pcm = _pcm_from_wasapi(ptr, int(frames.value), fmt, silent, is_float)
                        if pcm.size:
                            self.on_frames(pcm.reshape(-1, max(1, int(fmt.nChannels))))
                    finally:
                        _method(capture, 4, c_int, c_uint)(capture, int(frames.value))
                _method(client, 11, c_int)(client)
        except Exception as exc:
            self._error = exc
            log.exception("WASAPI loopback thread failed")
            self._started.set()
        finally:
            _release(capture)
            _release(client)
            if mix_ptr:
                _ole32().CoTaskMemFree(mix_ptr)
