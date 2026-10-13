from __future__ import annotations

from slysh.api import speaker_engine_progress_fraction


def test_speaker_engine_progress_fraction_idle():
    assert speaker_engine_progress_fraction({"phase": "idle", "progress": 0.5}) is None


def test_speaker_engine_progress_fraction_speakers_start():
    assert speaker_engine_progress_fraction({"phase": "speakers", "progress": 0.05}) == 0.0


def test_speaker_engine_progress_fraction_speakers_mid():
    frac = speaker_engine_progress_fraction({"phase": "speakers", "progress": 0.525})
    assert frac is not None
    assert 0.49 < frac < 0.51


def test_speaker_engine_progress_fraction_speakers_end():
    assert speaker_engine_progress_fraction({"phase": "speakers", "progress": 1.0}) == 1.0
