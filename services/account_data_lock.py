"""Serialize account deletion with background snapshot persistence."""
from threading import RLock, Lock

_guard = Lock()
_locks = {}


def account_lock(usuario):
    with _guard:
        return _locks.setdefault(usuario, RLock())
