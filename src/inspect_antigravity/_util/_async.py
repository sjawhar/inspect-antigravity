import inspect
from typing import Any


def is_callable_coroutine(func_or_cls: Any) -> bool:
    if inspect.iscoroutinefunction(func_or_cls):
        return True
    if callable(func_or_cls):
        return inspect.iscoroutinefunction(func_or_cls.__call__)
    return False
