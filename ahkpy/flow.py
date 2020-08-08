import ctypes
import os
import sys
import queue
import threading
from dataclasses import dataclass
from typing import Callable

import _ahk  # noqa

__all__ = [
    "Timer",
    "coop",
    "output_debug",
    "reload",
    "resume",
    "set_timer",
    "sleep",
    "suspend",
    "toggle_suspend",
]

global_ahk_lock = threading.RLock()


def ahk_call(cmd, *args):
    with global_ahk_lock:
        return _ahk.call(cmd, *args)


def set_timer(func=None, period=0.25, countdown=None, priority=0):
    # XXX: Should this be threading.Timer?
    if countdown is not None:
        if countdown < 0:
            raise ValueError("countdown must be positive")
        period = -countdown
    period = int(period*1000)

    def set_timer_decorator(func):
        ahk_call("SetTimer", func, period, priority)
        # TODO: Remove func from CALLBACKS after its execution if *countdown* is set.
        return Timer(func)

    if func is None:
        return set_timer_decorator
    return set_timer_decorator(func)


@dataclass(frozen=True)
class Timer:
    func: Callable
    __slots__ = tuple(__annotations__.keys())

    def start(self):
        ahk_call("SetTimer", self.func, "On")

    def stop(self):
        ahk_call("SetTimer", self.func, "Off")

    def cancel(self):
        # TODO: Remove self.func from CALLBACKS and WRAPPED_PYTHON_FUNCTIONS in AHK.
        ahk_call("SetTimer", self.func, "Delete")

    def set_priority(self, priority):
        ahk_call("SetTimer", self.func, "", priority)


def sleep(secs):
    if secs < 0:
        raise ValueError("sleep length must be non-negative")
    elif secs == 0:
        ahk_call("Sleep", -1)
    else:
        ahk_call("Sleep", int(secs * 1000))


def suspend():
    ahk_call("Suspend", "On")


def resume():
    ahk_call("Suspend", "Off")


def toggle_suspend():
    ahk_call("Suspend", "Toggle")


def reload():
    # TODO: If the new script has an error, AHK will show it and quit. Instead,
    # keep the old script running.
    ahk_call("Menu", "Tray", "NoIcon")
    args = list(map(_quote, [sys.executable, _ahk.script_full_path] + sys.argv))
    os.execv(sys.executable, args)


def _quote(s):
    return f'"{s}"'


def output_debug(*objs, sep=' '):
    if sep is None:
        # Python documentation for the print() function:
        #
        # > Both *sep* and *end* must be strings; they can also be `None`, which
        # > means to use the default values.
        sep = ' '
    debug_str = sep.join(map(str, objs))
    ctypes.windll.kernel32.OutputDebugStringW(debug_str)


def coop(func, *args, **kwargs):
    """Run the given function in a new thread and make it cooperate with AHK's
    event loop.

    The call starts a new thread and blocks the current thread until the
    function finishes. Returns the result of the function or raises the
    exception.
    """
    q = queue.Queue(maxsize=1)
    th = threading.Thread(
        target=_run_coop,
        args=(q, func, args, kwargs),
        daemon=True,
    )
    th.start()
    while True:
        try:
            if not th.is_alive():
                break
            sleep(0.01)
        except KeyboardInterrupt:
            set_async_exc = ctypes.pythonapi.PyThreadState_SetAsyncExc
            thread_id = th.ident
            kbd_interrupt = ctypes.py_object(KeyboardInterrupt)
            if th.is_alive():
                set_async_exc(thread_id, kbd_interrupt)

    val, exc = q.get()
    if exc is not None:
        raise exc
    return val


def _run_coop(queue, func, args, kwargs):
    try:
        result = func(*args, **kwargs), None
    except BaseException as exc:
        # Catch BaseException because we also want SystemExit and
        # KeyboardInterrupt.
        result = None, exc
    queue.put(result)
