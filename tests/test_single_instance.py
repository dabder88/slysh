"""Wave C.5: single-instance file lock per app data dir."""
from __future__ import annotations

from slysh.single_instance import SingleInstanceError, SingleInstanceLock


def test_single_instance_lock_released_allows_reacquire(tmp_path) -> None:
    lock1 = SingleInstanceLock(tmp_path)
    lock1.acquire()
    lock1.release()
    lock2 = SingleInstanceLock(tmp_path)
    lock2.acquire()
    lock2.release()


def test_single_instance_second_acquire_fails(tmp_path) -> None:
    lock1 = SingleInstanceLock(tmp_path)
    lock1.acquire()
    lock2 = SingleInstanceLock(tmp_path)
    try:
        lock2.acquire()
        raised = False
    except SingleInstanceError:
        raised = True
    finally:
        lock1.release()
    assert raised
