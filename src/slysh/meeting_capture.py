from __future__ import annotations

import logging
import sys
import threading

import numpy as np
import sounddevice as sd

from slysh.chunking import SAMPLE_RATE
from slysh.live_buffer import LiveSession
from slysh.wasapi_loopback import (
    WasapiLoopback,
    list_render_endpoints,
    match_render_endpoint,
)

log = logging.getLogger(__name__)

NO_OUTPUT_HINT = (
    "Не найден выход звука для записи встречи. Проверьте устройства воспроизведения Windows."
)
NOT_WINDOWS_HINT = "Запись системного звука доступна только в Windows."
LOOPBACK_FAIL_HINT = (
    "Не удалось открыть запись системного звука (WASAPI loopback). "
    "Выберите наушники или динамики Windows, не Sound Mapper. "
    "Bluetooth должен быть подключён; закройте программы с эксклюзивным доступом к аудио."
)
_INACTIVE_NAME_SKIP = (
    "disabled",
    "unavailable",
    "disconnected",
    "not plugged",
    "not present",
)
_VIRTUAL_NAME_SKIP = (
    "mapper",
    "microsoft sound mapper",
    "primary sound",
    "primary driver",
    "dummy",
    "wave mapper",
    "stereo mix",
    "what u hear",
    "loopback",
)
MAX_LAG_SAMPLES = SAMPLE_RATE


class MeetingCaptureError(Exception):
    pass


def loopback_supported() -> bool:
    return sys.platform == "win32"


def refresh_audio_devices() -> None:
    """Re-scan host audio so Bluetooth devices plugged in after launch appear."""
    try:
        update = getattr(sd._lib, "PaWasapi_UpdateDeviceList", None)
        if update is not None:
            update()
    except Exception:
        log.debug("PaWasapi_UpdateDeviceList failed", exc_info=True)
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        log.warning("PortAudio reinit failed", exc_info=True)


def to_mono(frames: np.ndarray) -> np.ndarray:
    arr = np.asarray(frames, dtype=np.float32)
    if arr.size == 0:
        return np.zeros(0, dtype=np.float32)
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        return np.mean(arr, axis=1, dtype=np.float32)
    return arr.reshape(-1)


def resample_to_16k(pcm: np.ndarray, src_rate: int) -> np.ndarray:
    mono = to_mono(pcm)
    if mono.size == 0:
        return np.zeros(0, dtype=np.float32)
    rate = int(src_rate)
    if rate == SAMPLE_RATE:
        return np.asarray(mono, dtype=np.float32)
    if rate <= 0:
        return np.zeros(0, dtype=np.float32)
    n_out = int(round(mono.size * SAMPLE_RATE / rate))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    old_x = np.arange(mono.size, dtype=np.float64)
    new_x = np.linspace(0.0, float(mono.size - 1), num=n_out, dtype=np.float64)
    return np.interp(new_x, old_x, mono.astype(np.float64)).astype(np.float32)


def input_sample_rates_for_device(device_id: int | None) -> tuple[int, ...]:
    native = SAMPLE_RATE
    try:
        if device_id is not None:
            info = sd.query_devices(device_id)
        else:
            default_in = sd.default.device[0]
            info = sd.query_devices(default_in) if default_in is not None and int(default_in) >= 0 else {}
        native = int(float(info.get("default_samplerate") or SAMPLE_RATE))
    except Exception:
        native = SAMPLE_RATE
    seen: set[int] = set()
    ordered: list[int] = []
    for rate in (native, SAMPLE_RATE, 48000, 44100):
        rate_i = int(rate)
        if rate_i > 0 and rate_i not in seen:
            seen.add(rate_i)
            ordered.append(rate_i)
    return tuple(ordered)


def open_mic_input_stream(device_id: int | None, callback_for_rate):
    """Open mic InputStream; callback_for_rate(capture_rate) returns PortAudio callback."""
    last_exc: Exception | None = None
    for rate in input_sample_rates_for_device(device_id):
        try:
            stream = sd.InputStream(
                samplerate=rate,
                channels=1,
                dtype="float32",
                device=device_id,
                callback=callback_for_rate(rate),
            )
            return stream, rate
        except Exception as exc:
            last_exc = exc
    hint = "Не удалось открыть микрофон. Проверьте устройство в Windows или выберите другой микрофон."
    if last_exc is not None:
        raise MeetingCaptureError(f"{hint} ({last_exc})")
    raise MeetingCaptureError(hint)


def mix_frames(
    mic: np.ndarray,
    system: np.ndarray,
    mic_gain: float = 1.0,
    system_gain: float = 1.0,
) -> np.ndarray:
    mic_pcm = np.asarray(mic, dtype=np.float32).reshape(-1)
    sys_pcm = np.asarray(system, dtype=np.float32).reshape(-1)
    n = max(len(mic_pcm), len(sys_pcm))
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    left = np.zeros(n, dtype=np.float32)
    right = np.zeros(n, dtype=np.float32)
    if len(mic_pcm):
        left[: len(mic_pcm)] = mic_pcm * float(mic_gain)
    if len(sys_pcm):
        right[: len(sys_pcm)] = sys_pcm * float(system_gain)
    return np.clip(left + right, -1.0, 1.0)


def _name_excluded(name: str) -> bool:
    lower = name.lower()
    return any(token in lower for token in _INACTIVE_NAME_SKIP)


def _is_virtual_name(name: str) -> bool:
    lower = " ".join(str(name or "").lower().split())
    if _name_excluded(lower):
        return True
    return any(token in lower for token in _VIRTUAL_NAME_SKIP)


def _normalize_device_name(name: str) -> str:
    return " ".join(str(name or "").lower().split())


def wasapi_hostapi_index() -> int | None:
    try:
        apis = sd.query_hostapis()
    except Exception:
        return None
    for index, api in enumerate(apis):
        if "wasapi" in str(api.get("name") or "").lower():
            return index
    return None


def _hostapi_of(info: dict) -> int:
    try:
        return int(info.get("hostapi", -1))
    except (TypeError, ValueError):
        return -1


def _iter_device_infos() -> list[tuple[int, dict]]:
    try:
        count = len(sd.query_devices())
    except Exception:
        return []
    items: list[tuple[int, dict]] = []
    for index in range(count):
        try:
            info = sd.query_devices(index)
        except Exception:
            continue
        items.append((index, info))
    return items


def _prefer_wasapi(candidates: list[dict]) -> list[dict]:
    wasapi = wasapi_hostapi_index()
    if wasapi is None:
        return candidates
    filtered = [item for item in candidates if int(item.get("hostapi", -1)) == wasapi]
    return filtered or candidates


def _sort_default_first(items: list[dict], default_id) -> list[dict]:
    if default_id is None:
        return items
    preferred = [item for item in items if str(item["id"]) == str(default_id)]
    rest = [item for item in items if str(item["id"]) != str(default_id)]
    return preferred + rest


def _com_render_outputs() -> list[dict]:
    if sys.platform != "win32":
        return []
    try:
        items = list_render_endpoints()
    except Exception:
        log.exception("WASAPI render device list failed")
        return []
    out: list[dict] = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name or _is_virtual_name(name):
            continue
        out.append({"id": item["id"], "name": name})
    return out


def list_output_devices() -> list[dict]:
    com = _com_render_outputs()
    if com:
        return com
    return _list_output_devices_portaudio()


def _list_output_devices_portaudio() -> list[dict]:
    collected: list[dict] = []
    for index, info in _iter_device_infos():
        if int(info.get("max_output_channels", 0) or 0) <= 0:
            continue
        name = str(info.get("name") or f"#{index}").strip()
        if _is_virtual_name(name):
            continue
        collected.append(
            {
                "id": index,
                "name": name,
                "hostapi": _hostapi_of(info),
            }
        )
    filtered = _prefer_wasapi(collected)
    return _sort_default_first(
        [{"id": item["id"], "name": item["name"]} for item in filtered],
        default_output_device_id(from_list=filtered),
    )


def list_input_devices(probe=None) -> list[dict]:
    collected: list[dict] = []
    check = probe if probe is not None else _probe_input
    for index, info in _iter_device_infos():
        if int(info.get("max_input_channels", 0) or 0) <= 0:
            continue
        name = str(info.get("name") or f"#{index}").strip()
        if _is_virtual_name(name):
            continue
        collected.append(
            {
                "id": index,
                "name": name,
                "hostapi": _hostapi_of(info),
            }
        )
    filtered = _prefer_wasapi(collected)
    usable: list[dict] = []
    for item in filtered:
        if check is not None and not check(item["id"]):
            continue
        usable.append({"id": item["id"], "name": item["name"]})
    return _sort_default_first(usable, default_input_device_id(from_list=usable))


def _hostapi_default_device(kind: str) -> int | None:
    wasapi = wasapi_hostapi_index()
    if wasapi is None:
        return None
    key = "default_output_device" if kind == "output" else "default_input_device"
    try:
        api = sd.query_hostapis(wasapi)
        value = api.get(key)
        if value is not None and int(value) >= 0:
            return int(value)
    except Exception:
        return None
    return None


def default_output_device_id(from_list: list[dict] | None = None) -> int | None:
    items = from_list if from_list is not None else None
    default_id = _hostapi_default_device("output")
    if default_id is not None:
        if items is None:
            return default_id
        if any(str(item["id"]) == str(default_id) for item in items):
            return default_id
    if items is None:
        listed = list_output_devices()
        return listed[0]["id"] if listed else None
    return items[0]["id"] if items else None


def default_input_device_id(from_list: list[dict] | None = None) -> int | None:
    items = from_list if from_list is not None else None
    default_id = _hostapi_default_device("input")
    if default_id is not None:
        if items is None:
            return default_id
        if any(str(item["id"]) == str(default_id) for item in items):
            return default_id
    if items is None:
        listed = list_input_devices()
        return listed[0]["id"] if listed else None
    return items[0]["id"] if items else None


def resolve_loopback_device(device_id: int | None) -> int | None:
    if device_id is None:
        return default_output_device_id()
    try:
        info = sd.query_devices(device_id)
    except Exception:
        return default_output_device_id()
    name = str(info.get("name") or "")
    if _is_virtual_name(name):
        return default_output_device_id()
    wasapi = wasapi_hostapi_index()
    if wasapi is None or _hostapi_of(info) == wasapi:
        return int(device_id)
    target = _normalize_device_name(name)
    for item in list_output_devices():
        if _normalize_device_name(item["name"]) == target:
            return item["id"]
    return default_output_device_id()


def _probe_input(index: int) -> bool:
    try:
        info = sd.query_devices(index)
        rate = int(float(info.get("default_samplerate") or SAMPLE_RATE))
    except Exception:
        rate = SAMPLE_RATE
    for samplerate in (rate, SAMPLE_RATE, 48000, 44100):
        try:
            with sd.InputStream(
                device=index,
                channels=1,
                samplerate=samplerate,
                blocksize=0,
                dtype="float32",
            ):
                pass
            return True
        except Exception:
            continue
    return False


def _rms(pcm: np.ndarray) -> float:
    if pcm.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(pcm))))


class MeetingMixer:
    def __init__(self, include_mic: bool) -> None:
        self.include_mic = include_mic
        self._lock = threading.Lock()
        self._mic = np.zeros(0, dtype=np.float32)
        self._sys = np.zeros(0, dtype=np.float32)
        self.rms_mic = 0.0
        self.rms_system = 0.0

    def push_system(self, pcm: np.ndarray) -> None:
        samples = np.asarray(pcm, dtype=np.float32).reshape(-1)
        with self._lock:
            if samples.size:
                self._sys = np.concatenate([self._sys, samples])
                self.rms_system = _rms(samples)

    def push_mic(self, pcm: np.ndarray) -> None:
        samples = np.asarray(pcm, dtype=np.float32).reshape(-1)
        with self._lock:
            if samples.size:
                self._mic = np.concatenate([self._mic, samples])
                self.rms_mic = _rms(samples)

    def take_mixed(self) -> np.ndarray:
        with self._lock:
            if not self.include_mic:
                out = self._sys
                self._sys = np.zeros(0, dtype=np.float32)
                return out
            sys_len = len(self._sys)
            mic_len = len(self._mic)
            if sys_len > mic_len + MAX_LAG_SAMPLES:
                pad = sys_len - mic_len - MAX_LAG_SAMPLES
                self._mic = np.concatenate([self._mic, np.zeros(pad, dtype=np.float32)])
            elif mic_len > sys_len + MAX_LAG_SAMPLES:
                pad = mic_len - sys_len - MAX_LAG_SAMPLES
                self._sys = np.concatenate([self._sys, np.zeros(pad, dtype=np.float32)])
            n = min(len(self._mic), len(self._sys))
            if n == 0:
                return np.zeros(0, dtype=np.float32)
            mixed = mix_frames(self._mic[:n], self._sys[:n])
            self._mic = self._mic[n:]
            self._sys = self._sys[n:]
            return mixed


class MeetingCapture:
    def __init__(
        self,
        session: LiveSession,
        output_device_id: int | str | None,
        mic_device_id: int | None,
        include_mic: bool,
        rms_holder: dict,
    ) -> None:
        self.session = session
        self.output_device_id = output_device_id
        self.mic_device_id = mic_device_id
        self.include_mic = include_mic
        self.rms_holder = rms_holder
        self.mixer = MeetingMixer(include_mic=include_mic)
        self._sys_stream = None
        self._loopback: WasapiLoopback | None = None
        self._mic_stream = None
        self._sys_rate = SAMPLE_RATE
        self._mic_rate = SAMPLE_RATE
        self._paused = False

    def pause(self) -> None:
        self._paused = True
        with self.mixer._lock:
            self.mixer._mic = np.zeros(0, dtype=np.float32)
            self.mixer._sys = np.zeros(0, dtype=np.float32)
            self.mixer.rms_mic = 0.0
            self.mixer.rms_system = 0.0

    def resume(self) -> None:
        self._paused = False

    def start(self) -> None:
        if not loopback_supported():
            raise MeetingCaptureError(NOT_WINDOWS_HINT)
        endpoint_name = None
        if isinstance(self.output_device_id, int):
            try:
                endpoint_name = str(sd.query_devices(self.output_device_id).get("name") or "")
            except Exception:
                endpoint_name = None
        try:
            endpoint = match_render_endpoint(self.output_device_id, endpoint_name)
        except Exception as exc:
            log.exception("match_render_endpoint failed")
            raise MeetingCaptureError(LOOPBACK_FAIL_HINT) from exc
        if not endpoint:
            raise MeetingCaptureError(NO_OUTPUT_HINT)
        self.output_device_id = endpoint
        try:
            self._loopback = WasapiLoopback(endpoint, self._on_wasapi_system)
            self._sys_rate = self._loopback.start()
        except MeetingCaptureError:
            raise
        except Exception as exc:
            log.exception("WASAPI loopback start failed")
            self.stop()
            raise MeetingCaptureError(f"{LOOPBACK_FAIL_HINT} ({exc})") from exc
        if self.include_mic:
            try:
                self._mic_stream, self._mic_rate = self._open_mic(self.mic_device_id)
                self._mic_stream.start()
            except Exception as exc:
                self.stop()
                raise MeetingCaptureError(str(exc) or "Не удалось открыть микрофон.") from exc

    def drain(self) -> None:
        with self.mixer._lock:
            if self.include_mic:
                n = max(len(self.mixer._mic), len(self.mixer._sys))
                if n and len(self.mixer._mic) < n:
                    pad = n - len(self.mixer._mic)
                    self.mixer._mic = np.concatenate(
                        [self.mixer._mic, np.zeros(pad, dtype=np.float32)]
                    )
                if n and len(self.mixer._sys) < n:
                    pad = n - len(self.mixer._sys)
                    self.mixer._sys = np.concatenate(
                        [self.mixer._sys, np.zeros(pad, dtype=np.float32)]
                    )
        self._flush_mix()

    def stop(self) -> None:
        try:
            self.drain()
        except Exception:
            pass
        loopback = self._loopback
        self._loopback = None
        if loopback is not None:
            try:
                loopback.stop()
            except Exception:
                pass
        for stream in (self._sys_stream, self._mic_stream):
            if stream is None:
                continue
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._sys_stream = None
        self._mic_stream = None

    def _flush_mix(self) -> None:
        if self._paused:
            return
        mixed = self.mixer.take_mixed()
        self.rms_holder["rms_system"] = float(self.mixer.rms_system)
        self.rms_holder["rms_mic"] = float(self.mixer.rms_mic)
        if mixed.size:
            self.session.push(mixed)

    def _on_wasapi_system(self, frames) -> None:
        if self._paused:
            return
        pcm = resample_to_16k(frames, self._sys_rate)
        self.mixer.push_system(pcm)
        self._flush_mix()

    def _open_mic(self, device_id: int | None):
        def callback_for_rate(capture_rate: int):
            def _on_mic(indata, frames, time_info, status) -> None:
                if self._paused:
                    return
                pcm = resample_to_16k(indata, capture_rate)
                self.mixer.push_mic(pcm)
                self._flush_mix()

            return _on_mic

        return open_mic_input_stream(device_id, callback_for_rate)
