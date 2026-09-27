import numpy as np

from slysh.models import Segment
from slysh.speakers_cluster import assign_cluster_speakers, kmeans_labels, segment_features
from slysh.job_time import job_duration_s


def test_kmeans_splits_two_groups():
    features = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.1, 0.0, 0.0],
            [10.0, 10.0, 10.0],
            [10.1, 10.0, 10.0],
        ],
        dtype=np.float32,
    )
    labels = kmeans_labels(features, k=2)
    assert labels[0] == labels[1]
    assert labels[2] == labels[3]
    assert labels[0] != labels[2]


def test_assign_cluster_speakers_keeps_text():
    segs = [Segment(0, 1000, "привет"), Segment(1000, 2000, "пока")]
    labeled = assign_cluster_speakers(segs, [0, 1])
    assert [s.text for s in labeled] == ["привет", "пока"]
    assert labeled[0].speaker == "SPEAKER_00"
    assert labeled[1].speaker == "SPEAKER_01"


def test_segment_features_shape():
    pcm = np.zeros(16000, dtype=np.float32)
    pcm[8000:] = 0.4
    segs = [Segment(0, 500, "a"), Segment(500, 1000, "b")]
    features = segment_features(pcm, segs)
    assert features.shape[0] == 2
    assert features.shape[1] > 1


def test_job_duration_from_started_and_finished():
    seconds = job_duration_s(
        {
            "started_at": "2026-08-16T10:00:00+00:00",
            "finished_at": "2026-08-16T10:04:12+00:00",
            "status": "completed",
        }
    )
    assert seconds == 252
