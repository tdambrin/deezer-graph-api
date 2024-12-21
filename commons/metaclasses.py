"""
Helper metaclasses
"""

import threading
from typing import Any, Dict


class ThreadSafeSingleton(type):
    """
    Thread safe implementation of a singleton with a destroy method for reset
    """

    _instances = {}  # type: ignore
    _singleton_locks: Dict[Any, threading.Lock] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            if cls not in cls._singleton_locks:
                cls._singleton_locks[cls] = threading.Lock()
            with cls._singleton_locks[cls]:
                if cls not in cls._instances:
                    cls._instances[cls] = super(
                        ThreadSafeSingleton, cls
                    ).__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def destroy(mcs, cls):
        if cls not in cls._singleton_locks:
            cls._singleton_locks[cls] = threading.Lock()
        with cls._singleton_locks[cls]:
            if cls in mcs._instances:
                del mcs._instances[cls]
