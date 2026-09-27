from __future__ import annotations

import numpy as np

from slysh.models import Segment

TARGET_SAMPLE_RATE = 16000


def _load_audio(source_path: str) -> np.ndarray:
    from slysh.decode import decode_pcm_16k_mono

    pcm, _sr = decode_pcm_16k_mono(source_path)
    return np.asarray(pcm, dtype=np.float32).reshape(-1)


def _band_energies(frame: np.ndarray, bands: int = 8) -> np.ndarray:
    if frame.size < 32:
        return np.zeros(bands, dtype=np.float32)
    windowed = frame * np.hanning(frame.size)
    spec = np.abs(np.fft.rfft(windowed))
    spec = spec + 1e-8
    edges = np.linspace(0, spec.size, bands + 1, dtype=int)
    out = np.zeros(bands, dtype=np.float32)
    for i in range(bands):
        chunk = spec[edges[i] : edges[i + 1]]
        out[i] = float(np.log(np.mean(chunk * chunk)))
    return out


def segment_features(pcm: np.ndarray, segments: list[Segment], sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    rows: list[np.ndarray] = []
    for segment in segments:
        start = max(0, int(segment.start_ms * sr / 1000))
        end = max(start + 1, int(segment.end_ms * sr / 1000))
        frame = pcm[start:end]
        energy = float(np.log(np.mean(np.square(frame)) + 1e-8))
        rows.append(np.concatenate([[energy], _band_energies(frame)]))
    return np.vstack(rows)


def kmeans_labels(features: np.ndarray, k: int, rounds: int = 12) -> list[int]:
    count = features.shape[0]
    k = max(1, min(k, count))
    if k == 1:
        return [0] * count
    centers = [features[0]]
    for _ in range(1, k):
        dist = np.min(
            [np.linalg.norm(features - center, axis=1) for center in centers],
            axis=0,
        )
        centers.append(features[int(dist.argmax())])
    centers = np.stack(centers)
    labels = np.zeros(count, dtype=int)
    for _ in range(rounds):
        distances = np.linalg.norm(features[:, None, :] - centers[None, :, :], axis=2)
        labels = distances.argmin(axis=1)
        for index in range(k):
            members = features[labels == index]
            if len(members):
                centers[index] = members.mean(axis=0)
    return [int(value) for value in labels]


def assign_cluster_speakers(segments: list[Segment], labels: list[int]) -> list[Segment]:
    return [
        Segment(
            segment.start_ms,
            segment.end_ms,
            segment.text,
            speaker=f"SPEAKER_{label:02d}",
        )
        for segment, label in zip(segments, labels, strict=True)
    ]


class ClusterSpeakersBackend:
    """Fallback diarization when NeMo/MSDD is not installed."""

    def label(self, source_path: str, segments: list[Segment]) -> list[Segment]:
        if not segments:
            return []
        if len(segments) == 1:
            return assign_cluster_speakers(segments, [0])
        pcm = _load_audio(source_path)
        features = segment_features(pcm, segments)
        labels = kmeans_labels(features, k=2)
        return assign_cluster_speakers(segments, labels)
