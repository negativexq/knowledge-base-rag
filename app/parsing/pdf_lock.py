"""Serialize in-process PDF operations, including PyMuPDF table finder globals."""

from collections.abc import Callable
from functools import wraps
from threading import RLock
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")
_lock = RLock()


def serialized_pdf(function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def run(*args: P.args, **kwargs: P.kwargs) -> T:
        with _lock:
            return function(*args, **kwargs)

    return run
