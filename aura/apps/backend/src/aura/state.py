from __future__ import annotations
import threading
from collections import defaultdict
from storage.db import get_conn

PANIC = False
RUN_CANCEL: dict[str, bool] = defaultdict(bool)
LOCK = threading.Lock()


def db_conn():
    return get_conn()


def set_panic(v: bool):
    global PANIC
    PANIC = v


def is_panic() -> bool:
    return PANIC


def cancel_run(run_id: str):
    with LOCK:
        RUN_CANCEL[run_id] = True


def is_run_cancelled(run_id: str) -> bool:
    with LOCK:
        return RUN_CANCEL.get(run_id, False) or PANIC
