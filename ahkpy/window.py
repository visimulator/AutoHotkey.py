from __future__ import annotations

import ctypes
import dataclasses as dc
import enum
from typing import Iterator, List, Optional, Tuple, Union

from . import colors
from . import sending
from .exceptions import Error
from .flow import ahk_call, global_ahk_lock
from .hotkey_context import HotkeyContext
from .settings import get_settings, optional_ms
from .unset import UNSET, UnsetType

__all__ = [
    "Control",
    "ExWindowStyle",
    "Window",
    "Windows",
    "WindowStyle",
    "all_windows",
    "visible_windows",
    "windows",
]


TITLE_MATCH_MODES = {"startswith", "contains", "exact", "regex"}
TEXT_MATCH_MODES = {"fast", "slow"}


@dc.dataclass(frozen=True)
class Windows:
    """Windows()

    The immutable object containing the criteria that is used to match the
    windows, iterate over them, do bulk actions, or to pick one window.
    """

    title: Union[str, UnsetType] = UNSET
    class_name: Union[str, UnsetType] = UNSET
    id: Union[int, UnsetType] = UNSET
    pid: Union[int, UnsetType] = UNSET
    exe: Union[str, UnsetType] = UNSET
    text: Union[str, UnsetType] = UNSET
    exclude_title: Union[str, UnsetType] = UNSET
    exclude_text: Union[str, UnsetType] = UNSET
    hidden_windows: bool = False
    hidden_text: bool = True
    title_mode: str = "startswith"
    text_mode: str = "fast"

    def filter(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """filter(title: str = UNSET, **criteria)

        Match specific windows using the given criteria. All strings are
        case-sensitive.

        :param str title: the window title to match. The matching behavior is
           specified in the *match* argument and defaults to ``"startswith"``.

        :param str class_name: the window class to match.

        :param int id: the unique ID of a window or a control; also known as
           HWND.

        :param int pid: the process identifier that is used to match the windows
           belonging to this process.

        :param str exe: the filename of the process that is used to match the
           windows belonging to this process. If *match* is ``"regex"``, the
           *exe* argument accepts a regular expression that matches the full
           path of the process.

        :param str text: the substring from a single text element of the target
           window. The matching behavior is affected by the
           :meth:`include_hidden_text` and :meth:`match_text_slow` methods.

        :param str match: sets the matching behavior. Takes one of the following
           values:

           - ``"startswith"`` – a window's title must start with the given
             *title*.
           - ``"contains"`` – a window's title must contain the given *title*.
           - ``"exact"`` – a window's title must exactly match the given
             *title*.
           - ``"regex"`` – changes *title*, *class_name*, *exe*, and *text*
             arguments to accept `PCRE regular expressions
             <https://www.autohotkey.com/docs/misc/RegEx-QuickRef.htm>`_.

           Defaults to ``"startswith"``.
        """
        return self._filter(title, class_name, id, pid, exe, text, match)

    def _filter(self, title, class_name, id, pid, exe, text, match):
        if (
            title is UNSET and class_name is UNSET and id is UNSET and pid is UNSET and exe is UNSET and
            text is UNSET and match is None
        ):
            return self

        if match is not None and match not in TITLE_MATCH_MODES:
            raise ValueError(f"{match!r} is not a valid title match mode")

        return dc.replace(
            self,
            title=title if title is not UNSET else self.title,
            class_name=class_name if class_name is not UNSET else self.class_name,
            id=id if id is not UNSET else self.id,
            pid=pid if pid is not UNSET else self.pid,
            exe=exe if exe is not UNSET else self.exe,
            text=text if text is not UNSET else self.text,
            title_mode=match if match is not None else self.title_mode,
        )

    def exclude(self, title=UNSET, *, text=UNSET, match=None):
        """exclude(title: str = UNSET, **exclude_criteria)

        Exclude windows from the match using the given criteria. All strings are
        case-sensitive.

        :param str title: exclude windows with the given title.

        :param str text: exclude windows with the given text. The matching
           behavior is affected by the :meth:`match_text_slow` method only. It's
           not affected by :meth:`include_hidden_text`.

        :param str match: sets the matching behavior. For more information refer
           to :meth:`filter`.
        """
        # TODO: Consider implementing class_name, id, pid, and exe exclusion in
        # Python.
        if title is UNSET and text is UNSET and match is None:
            return self

        if match is not None and match not in TITLE_MATCH_MODES:
            raise ValueError(f"{match!r} is not a valid title match mode")

        return dc.replace(
            self,
            exclude_title=title if title is not UNSET else self.exclude_title,
            exclude_text=text if text is not UNSET else self.exclude_text,
            title_mode=match if match is not None else self.title_mode,
        )

    def include_hidden_windows(self, include=True):
        """Change the window-matching behavior based on window visibility.

        If *include* is true, includes the hidden windows in the search.

        Default behavior is matching only visible windows while ignoring the
        hidden ones.
        """
        return dc.replace(self, hidden_windows=include)

    def exclude_hidden_windows(self):
        """Exclude hidden windows from the search.

        A shorthand for ``windows.include_hidden_windows(False)``.
        """
        return dc.replace(self, hidden_windows=False)

    def include_hidden_text(self, include=True):
        """Change whether to ignore invisible controls when matching windows
        using the *text* criterion.

        If *include* is false, ignores the invisible controls when searching for
        text in the windows.

        Default behavior is searching for visible and hidden text.
        """
        return dc.replace(self, hidden_text=include)

    def exclude_hidden_text(self):
        """Exclude hidden text from the search.

        A shorthand for ``windows.include_hidden_text(False)``.
        """
        return dc.replace(self, hidden_text=False)

    def match_text_slow(self, is_slow=True):
        """Change how windows are matched when using the *text* criterion.

        If *is_slow* is true, the matching can be much slower, but works with
        all controls which respond to the `WM_GETTEXT
        <https://msdn.microsoft.com/en-us/library/ms632627>`_ message.

        Default behavior is to use the fast mode. However, certain types of
        controls are not detected. For instance, text is typically detected
        within Static and Button controls, but not Edit controls, unless they
        are owned by the script.
        """
        # Not including the parameter in filter() because it's used very rarely.
        if is_slow:
            return dc.replace(self, text_mode="slow")
        else:
            return dc.replace(self, text_mode="fast")

    def first(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """first(title: str = UNSET, **criteria) -> ahkpy.Window

        Return the window handle of the first (top) matching window.

        If there are no matching windows, returns ``Window(None)``.

        For arguments refer to :meth:`filter`.

        :aliases: :meth:`exist`, :meth:`top`

        :command: `WinExist
           <https://www.autohotkey.com/docs/commands/WinExist.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        win_id = self._call("WinExist", *self._query())
        if not win_id:
            return Window(None)
        return Window(win_id)

    exist = first
    top = first

    def last(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """last(title: str = UNSET, **criteria) -> ahkpy.Window

        Return the window handle of the last (bottom) matching window.

        If there are no matching windows, returns ``Window(None)``.

        For arguments refer to :meth:`filter`.

        :alias: :meth:`bottom`

        :command: `WinGet, $, IDLast
           <https://www.autohotkey.com/docs/commands/WinGet.htm#IDLast>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        win_id = self._call("WinGet", "IDLast", *self._query())
        if not win_id:
            return Window(None)
        return Window(win_id)

    bottom = last

    def get_active(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """get_active(title: str = UNSET, **criteria) -> ahkpy.Window

        Return the window handle of the active matching window.

        If no criteria are given, returns the current active window. If no
        window is active, returns ``Window(None)``.

        For arguments refer to :meth:`filter`.

        :command: `WinActive
           <https://www.autohotkey.com/docs/commands/WinActive.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        query = self._query()
        if query == ("", "", "", ""):
            query = ("A", "", "", "")
        win_id = self._call("WinActive", *query)
        if not win_id:
            return Window(None)
        return Window(win_id)

    def wait(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None,
             timeout=None):
        """wait(title: str = UNSET, *, timeout=None, **criteria) -> ahkpy.Window

        Wait until the specified window exists and return it.

        Returns the first matched window. If there are no matching windows after
        *timeout* seconds, then ``Window(None)`` will be returned. If *timeout*
        is not specified or ``None``, there is no limit to the wait time.

        For other arguments refer to :meth:`filter`.

        :command: `WinWait
           <https://www.autohotkey.com/docs/commands/WinWait.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return self._wait("WinWait", timeout)

    def wait_active(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None,
                    timeout=None):
        """wait_active(title: str = UNSET, *, timeout=None, **criteria) -> ahkpy.Window

        Wait until the window is active and return it.

        For more information refer to :meth:`wait`.

        :command: `WinWaitActive
           <https://www.autohotkey.com/docs/commands/WinWaitActive.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        query = self._query()
        if query == ("", "", "", ""):
            self = dc.replace(self, title="A")
        return self._wait("WinWaitActive", timeout)

    def wait_inactive(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None,
                      timeout=None):
        """wait_inactive(title: str = UNSET, *, timeout=None, **criteria) -> ahkpy.Window

        Wait until the window is inactive and return it.

        For more information refer to :meth:`wait`.

        :command: `WinWaitNotActive
           <https://www.autohotkey.com/docs/commands/WinWaitActive.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return self._wait("WinWaitNotActive", timeout)

    def wait_close(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None,
                   timeout=None):
        """wait_close(title: str = UNSET, *, timeout=None, **criteria) -> bool

        Wait until there are no matching windows.

        Returns ``True`` if there are no matching windows. If there are still
        matching windows after *timeout* seconds, then ``False`` will be
        returned. If *timeout* is not specified or ``None``, there is no limit
        to the wait time.

        For other arguments refer to :meth:`filter`.

        :command: `WinWaitClose
           <https://www.autohotkey.com/docs/commands/WinWaitClose.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        # WinWaitClose doesn't set Last Found Window, return False if the wait
        # was timed out.
        ok = self._call("WinWaitClose", *self._include(), timeout or "", *self._exclude(), set_delay=True)
        if ok is None:
            # There are no matching windows, and that's what we are waiting for.
            return True
        return bool(ok)

    def _wait(self, cmd, timeout):
        win_id = self._call(cmd, *self._include(), timeout or "", *self._exclude(), set_delay=True)
        if not win_id:
            return Window(None)
        return Window(win_id)

    def close_all(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None,
                  timeout=None):
        """close_all(title: str = UNSET, *, timeout=None, **criteria) -> bool

        Close all matching windows.

        Returns ``True`` if all matching windows were closed. If there are still
        matching windows after *timeout* seconds, then ``False`` will be
        returned. If *timeout* is not specified or ``None``, the function
        returns immediately.

        For arguments refer to :meth:`filter`.

        :command: `WinClose
           <https://www.autohotkey.com/docs/commands/WinClose.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return self._group_action("WinClose", timeout)

    def hide_all(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """hide_all(title: str = UNSET, **criteria)

        Hide all matching windows.

        For arguments refer to :meth:`filter`.

        :command: `WinHide
           <https://www.autohotkey.com/docs/commands/WinHide.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return self._group_action("WinHide")

    def kill_all(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None,
                 timeout=None):
        """kill_all(title: str = UNSET, *, timeout=None, **criteria) -> bool

        Forces all matching windows to close.

        Returns ``True`` if all matching windows were closed. If there are still
        matching windows after *timeout* seconds, then ``False`` will be
        returned. If *timeout* is not specified or ``None``, the function
        returns immediately.

        For arguments refer to :meth:`filter`.

        :command: `WinKill
           <https://www.autohotkey.com/docs/commands/WinKill.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return self._group_action("WinKill", timeout)

    def maximize_all(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """maximize_all(title: str = UNSET, **criteria)

        Maximize all matching windows.

        For arguments refer to :meth:`filter`.

        :command: `WinMaximize
           <https://www.autohotkey.com/docs/commands/WinMaximize.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return self._group_action("WinMaximize")

    def minimize_all(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """minimize_all(title: str = UNSET, **criteria)

        Minimize all matching windows.

        For arguments refer to :meth:`filter`.

        :command: `WinMinimize
           <https://www.autohotkey.com/docs/commands/WinMinimize.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return self._group_action("WinMinimize")

    # TODO: Implement WinMinimizeAllUndo.

    def restore_all(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """restore_all(title: str = UNSET, **criteria)

        Restore all matching windows.

        For arguments refer to :meth:`filter`.

        :command: `WinRestore
           <https://www.autohotkey.com/docs/commands/WinRestore.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        self._group_action("WinRestore")

    def show_all(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """show_all(title: str = UNSET, **criteria)

        Show all matching windows.

        For arguments refer to :meth:`filter`.

        :command: `WinShow
           <https://www.autohotkey.com/docs/commands/WinShow.htm>`_
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        self._group_action("WinShow")

    def _group_action(self, cmd, timeout=UNSET):
        if self == Windows() and cmd == "WinMinimize":
            # If the filter matches all the windows, minimize everything except
            # the desktop window.
            self._call("WinMinimizeAll", set_delay=True)
            return

        query_hash = hash(self)
        query_hash_str = str(query_hash).replace("-", "m")  # AHK doesn't allow "-" in group names
        label = ""
        self._call("GroupAdd", query_hash_str, *self._include(), label, *self._exclude())
        self._call(cmd, f"ahk_group {query_hash_str}", "", timeout or "", set_delay=True)
        if timeout is not UNSET:
            return not self.exist()

    def window_context(self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """window_context(title: str = UNSET, **criteria) -> ahkpy.HotkeyContext

        Create a context for hotkeys that will work only when the matching
        windows exist.

        For arguments refer to :meth:`filter`.

        :command: `Hotkey, IfWinExist
           <https://www.autohotkey.com/docs/commands/Hotkey.htm>`_, `#IfWinExist
           <https://www.autohotkey.com/docs/commands/_IfWinActive.htm>`_.

        """
        # Not using Hotkey, IfWinActive/Exist because:
        #
        # 1. It doesn't support excluding windows.
        # 2. It doesn't set DetectHiddenWindows from the given query before
        #    enumerating the windows.
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return HotkeyContext(lambda: self.exist())

    def nonexistent_window_context(
            self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """nonexistent_window_context(title: str = UNSET, **criteria) -> ahkpy.HotkeyContext

        Create a context for hotkeys that will work only when there are no
        matching windows.

        For arguments refer to :meth:`filter`.

        :command: `Hotkey, IfWinNotExist
           <https://www.autohotkey.com/docs/commands/Hotkey.htm>`_,
           `#IfWinNotExist
           <https://www.autohotkey.com/docs/commands/_IfWinActive.htm>`_.
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return HotkeyContext(lambda: not self.exist())

    def active_window_context(
            self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """active_window_context(title: str = UNSET, **criteria) -> ahkpy.HotkeyContext

        Create a context for hotkeys that will work only when the matching
        windows are active.

        For arguments refer to :meth:`filter`.

        :command: `Hotkey, IfWinActive
           <https://www.autohotkey.com/docs/commands/Hotkey.htm>`_,
           `#IfWinActive
           <https://www.autohotkey.com/docs/commands/_IfWinActive.htm>`_.
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return HotkeyContext(lambda: self.get_active())

    def inactive_window_context(
            self, title=UNSET, *, class_name=UNSET, id=UNSET, pid=UNSET, exe=UNSET, text=UNSET, match=None):
        """inactive_window_context(title: str = UNSET, **criteria) -> ahkpy.HotkeyContext

        Create a context for hotkeys that will work only when the matching
        windows are not active.

        For arguments refer to :meth:`filter`.

        :command: `Hotkey, IfWinNotActive
           <https://www.autohotkey.com/docs/commands/Hotkey.htm>`_,
           `#IfWinNotActive
           <https://www.autohotkey.com/docs/commands/_IfWinActive.htm>`_.
        """
        self = self._filter(title, class_name, id, pid, exe, text, match)
        return HotkeyContext(lambda: not self.get_active())

    def __iter__(self) -> Iterator[Window]:
        """__iter__() -> typing.Iterator[ahkpy.Window]

        Return matching windows ordered from top to bottom.

        :command: `WinGet, $, List
           <https://www.autohotkey.com/docs/commands/WinGet.htm#List>`_
        """
        win_ids = self._call("WinGetList", *self._query())
        if win_ids is None:
            return
        for win_id in win_ids.values():
            if win_id > 0:
                yield Window(win_id)

    def __len__(self):
        """Return the number of matching windows.

        :command: `WinGet, $, Count
           <https://www.autohotkey.com/docs/commands/WinGet.htm#Count>`_
        """
        return self._call("WinGet", "Count", *self._query()) or 0

    def __repr__(self):
        field_strs = []
        for field in dc.fields(self):
            value = getattr(self, field.name)
            if value is not UNSET:
                field_strs.append(f"{field.name}={value!r}")
        return self.__class__.__qualname__ + f"({', '.join(field_strs)})"

    def _call(self, cmd, *args, set_delay=False):
        if (
            self.title is None or self.class_name is None or self.id is None or self.pid is None or self.exe is None or
            self.text is None
        ):
            # Querying a non-existent window's attributes.
            return
        with global_ahk_lock:
            if self.hidden_windows:
                ahk_call("DetectHiddenWindows", "On")
            else:
                ahk_call("DetectHiddenWindows", "Off")

            if self.text is not UNSET or self.exclude_text is not UNSET:
                if self.hidden_text:
                    ahk_call("DetectHiddenText", "On")
                else:
                    ahk_call("DetectHiddenText", "Off")

            _set_title_match_mode(self.title_mode)

            if self.text_mode == "fast":
                ahk_call("SetTitleMatchMode", "fast")
            elif self.text_mode == "slow":
                ahk_call("SetTitleMatchMode", "slow")
            else:
                raise ValueError(f"{self.text_mode!r} is not a valid text match mode")

            if set_delay:
                ahk_call("SetWinDelay", optional_ms(get_settings().win_delay))

            return ahk_call(cmd, *args)

    def _query(self):
        return (*self._include(), *self._exclude())

    def _include(self):
        parts = []
        if self.title is not UNSET:
            parts.append(str(self.title))
        if self.class_name is not UNSET:
            parts.append(f"ahk_class {self.class_name}")
        if self.id is not UNSET:
            parts.append(f"ahk_id {self.id}")
        if self.pid is not UNSET:
            parts.append(f"ahk_pid {self.pid}")
        if self.exe is not UNSET:
            parts.append(f"ahk_exe {self.exe}")

        return (
            " ".join(parts),
            str(self.text) if self.text is not UNSET else "",
        )

    def _exclude(self):
        return (
            str(self.exclude_title) if self.exclude_title is not UNSET else "",
            str(self.exclude_text) if self.exclude_text is not UNSET else "",
        )


windows = visible_windows = Windows()
all_windows = windows.include_hidden_windows()


@dc.dataclass(frozen=True)
class WindowHandle:
    """The immutable object that contains the *id* (HWND) of a window/control.
    """

    # I'd like the Window and Control classes to be hashable, and making the
    # dataclass frozen also makes it hashable. However, frozen dataclasses
    # cannot have setter properties unless it's a subclass.

    id: Optional[int]
    __slots__ = ("id",)

    def __bool__(self):
        """Check if the window/control exists.

        Returns ``True`` if the window/control exists. Returns ``False`` if the
        window/control doesn't exist or it's a ``Window(None)`` or
        ``Control(None)`` instance.
        """
        return bool(self.id) and self.exists

    @property
    def exists(self) -> bool:
        """The window/control existence (read-only).

        Returns ``True`` if the window/control exists. Returns ``False`` if the
        window/control doesn't exist or it's a ``Window(None)`` or
        ``Control(None)`` instance.

        :command: `WinExist
           <https://www.autohotkey.com/docs/commands/WinExist.htm>`_
        """
        return bool(self._call("WinExist", *self._include()))

    def _call(self, cmd, *args, hidden_windows=True, title_mode=None, set_delay=False):
        with global_ahk_lock:
            # TODO: Setting DetectHiddenWindows should not be necessary for
            # controls.
            # > Control's HWND can be used directly as an ahk_id WinTitle (this
            # > also works on hidden controls even when DetectHiddenWindows is
            # > Off).
            if hidden_windows:
                ahk_call("DetectHiddenWindows", "On")
            else:
                ahk_call("DetectHiddenWindows", "Off")

            if title_mode is not None:
                _set_title_match_mode(title_mode)

            if set_delay:
                self._set_delay()

            return ahk_call(cmd, *args)

    def _set_delay(self):
        raise NotImplementedError

    def _include(self):
        win_text = ""
        return f"ahk_id {self.id or 0}", win_text


class BaseWindow(WindowHandle):
    """Base window class that is inherited by :class:`~ahkpy.Window` and
    :class:`~ahkpy.Control` classes.
    """

    __slots__ = ("id",)

    @property
    def style(self) -> Optional[WindowStyle]:
        """The styles of the window/control.

        Returns ``None`` if the window doesn't exist.

        .. TODO: Remove :types: once
           https://github.com/sphinx-doc/sphinx/issues/7383 is resolved and
           released.

        :type: WindowStyle

        :command: `WinGet, $, Style
           <https://www.autohotkey.com/docs/commands/WinGet.htm#Style>`_,
           `WinSet, $, Style
           <https://www.autohotkey.com/docs/commands/WinSet.htm#Style>`_,
           `ControlGet, $, Style
           <https://www.autohotkey.com/docs/commands/ControlGet.htm#Style>`_,
           `Control, $, Style
           <https://www.autohotkey.com/docs/commands/Control.htm#Style>`_
        """
        style = self._get("Style")
        if style is None:
            return None
        return WindowStyle(style)

    @style.setter
    def style(self, value):
        self._set("Style", int(value))

    @property
    def ex_style(self) -> Optional[ExWindowStyle]:
        """The extended styles of the window/control.

        Returns ``None`` if the window doesn't exist.

        :type: ExWindowStyle

        :command: `WinGet, $, ExStyle
           <https://www.autohotkey.com/docs/commands/WinGet.htm#ExStyle>`_,
           `WinSet, $, ExStyle
           <https://www.autohotkey.com/docs/commands/WinSet.htm#ExStyle>`_,
           `ControlGet, $, ExStyle
           <https://www.autohotkey.com/docs/commands/ControlGet.htm#ExStyle>`_,
           `Control, $, ExStyle
           <https://www.autohotkey.com/docs/commands/Control.htm#ExStyle>`_
        """
        ex_style = self._get("ExStyle")
        if ex_style is None:
            return None
        return ExWindowStyle(ex_style)

    @ex_style.setter
    def ex_style(self, value):
        self._set("ExStyle", int(value))

    @property
    def class_name(self) -> Optional[str]:
        """The window/control class name (read-only).

        Returns ``None`` if the window doesn't exist.

        :type: str

        :command: `WinGetClass
           <https://www.autohotkey.com/docs/commands/WinGetClass.htm>`_
        """
        class_name = self._call("WinGetClass", *self._include())
        if class_name == "":
            # Windows API doesn't allow the class name to be an empty string. If
            # the window doesn't exist or there was a problem getting the class
            # name, AHK returns an empty string.
            return None
        return class_name

    @property
    def rect(self) -> Optional[Tuple[int, int, int, int]]:
        """The position and size of the window/control as a ``(x, y, width,
        height)`` tuple.

        Returns ``None`` if the window doesn't exist.

        :type: Tuple[int, int, int, int]

        :command: `WinGetPos
           <https://www.autohotkey.com/docs/commands/WinGetPos.htm>`_,
           `ControlGetPos
           <https://www.autohotkey.com/docs/commands/ControlGetPos.htm>`_,
           `WinMove <https://www.autohotkey.com/docs/commands/WinMove.htm>`_,
           `ControlMove
           <https://www.autohotkey.com/docs/commands/ControlMove.htm>`_
        """
        result = self._get_pos()
        if result is None:
            return None
        x, y, width, height = result["X"], result["Y"], result["Width"], result["Height"]
        return (
            x if x != "" else None,
            y if y != "" else None,
            width if width != "" else None,
            height if height != "" else None,
        )

    @rect.setter
    def rect(self, new_rect):
        x, y, width, height = new_rect
        self.move(x, y, width, height)

    @property
    def position(self):
        """The window/control position as a ``(x, y)`` tuple.

        Returns ``None`` if the window doesn't exist.

        :type: Tuple[int, int]

        :command: `WinGetPos
           <https://www.autohotkey.com/docs/commands/WinGetPos.htm>`_,
           `ControlGetPos
           <https://www.autohotkey.com/docs/commands/ControlGetPos.htm>`_,
           `WinMove <https://www.autohotkey.com/docs/commands/WinMove.htm>`_,
           `ControlMove
           <https://www.autohotkey.com/docs/commands/ControlMove.htm>`_
        """
        rect = self.rect
        if rect is None:
            return None
        x, y, _, _ = rect
        return x, y

    @position.setter
    def position(self, new_position):
        x, y = new_position
        self.move(x, y)

    @property
    def x(self):
        """The *x* coordinate of the window/control.

        Returns ``None`` if the window doesn't exist.

        :type: int

        :command: `WinGetPos
           <https://www.autohotkey.com/docs/commands/WinGetPos.htm>`_,
           `ControlGetPos
           <https://www.autohotkey.com/docs/commands/ControlGetPos.htm>`_,
           `WinMove <https://www.autohotkey.com/docs/commands/WinMove.htm>`_,
           `ControlMove
           <https://www.autohotkey.com/docs/commands/ControlMove.htm>`_
        """
        rect = self.rect
        if rect is None:
            return None
        x, _, _, _ = rect
        return x

    @x.setter
    def x(self, new_x):
        self.move(x=new_x)

    @property
    def y(self):
        """The *y* coordinate of the window/control.

        Returns ``None`` if the window doesn't exist.

        :type: int

        :command: `WinGetPos
           <https://www.autohotkey.com/docs/commands/WinGetPos.htm>`_,
           `ControlGetPos
           <https://www.autohotkey.com/docs/commands/ControlGetPos.htm>`_,
           `WinMove <https://www.autohotkey.com/docs/commands/WinMove.htm>`_,
           `ControlMove
           <https://www.autohotkey.com/docs/commands/ControlMove.htm>`_
        """
        rect = self.rect
        if rect is None:
            return None
        _, y, _, _ = rect
        return y

    @y.setter
    def y(self, new_y):
        self.move(y=new_y)

    @property
    def size(self):
        """The window/control size.

        Returns a ``(width, height)`` tuple. If the window doesn't exist,
        returns ``None``.

        :type: Tuple[int, int]

        :command: `WinGetPos
           <https://www.autohotkey.com/docs/commands/WinGetPos.htm>`_,
           `ControlGetPos
           <https://www.autohotkey.com/docs/commands/ControlGetPos.htm>`_,
           `WinMove <https://www.autohotkey.com/docs/commands/WinMove.htm>`_,
           `ControlMove
           <https://www.autohotkey.com/docs/commands/ControlMove.htm>`_
        """
        rect = self.rect
        if rect is None:
            return None
        _, _, width, height = rect
        return width, height

    @size.setter
    def size(self, new_size):
        width, height = new_size
        self.move(width, height)

    @property
    def width(self):
        """The window/control width.

        Returns ``None`` if the window doesn't exist.

        :type: int

        :command: `WinGetPos
           <https://www.autohotkey.com/docs/commands/WinGetPos.htm>`_,
           `ControlGetPos
           <https://www.autohotkey.com/docs/commands/ControlGetPos.htm>`_,
           `WinMove <https://www.autohotkey.com/docs/commands/WinMove.htm>`_,
           `ControlMove
           <https://www.autohotkey.com/docs/commands/ControlMove.htm>`_
        """
        rect = self.rect
        if rect is None:
            return None
        _, _, width, _ = rect
        return width

    @width.setter
    def width(self, new_width):
        self.move(width=new_width)

    @property
    def height(self):
        """The window/control height.

        Returns ``None`` if the window doesn't exist.

        :type: int

        :command: `WinGetPos
           <https://www.autohotkey.com/docs/commands/WinGetPos.htm>`_,
           `ControlGetPos
           <https://www.autohotkey.com/docs/commands/ControlGetPos.htm>`_,
           `WinMove <https://www.autohotkey.com/docs/commands/WinMove.htm>`_,
           `ControlMove
           <https://www.autohotkey.com/docs/commands/ControlMove.htm>`_
        """
        rect = self.rect
        if rect is None:
            return None
        _, _, _, height = rect
        return height

    @height.setter
    def height(self, new_height):
        self.move(height=new_height)

    def move(self, x=None, y=None, width=None, height=None):
        """Move and/or resize the window/control.

        Does nothing if the window/control doesn't exist.

        :command: `WinMove
           <https://www.autohotkey.com/docs/commands/WinMove.htm>`_,
           `ControlMove
           <https://www.autohotkey.com/docs/commands/ControlMove.htm>`_
        """
        self._move(
            int(x) if x is not None else "",
            int(y) if y is not None else "",
            int(width) if width is not None else "",
            int(height) if height is not None else "",
        )

    @property
    def is_enabled(self) -> Optional[bool]:
        """The enabled state of the window/control.

        Returns ``None`` if the window doesn't exist.

        :type: bool

        :command: `WinSet, Enable
           <https://www.autohotkey.com/docs/commands/WinSet.htm#Enable>`_,
           `ControlGet, $, Enabled
           <https://www.autohotkey.com/docs/commands/ControlGet.htm#Enabled>`_,
           `Control, Enable
           <https://www.autohotkey.com/docs/commands/Control.htm#Enable>`_
        """
        style = self.style
        if style is None:
            return None
        return WindowStyle.DISABLED not in style

    @is_enabled.setter
    def is_enabled(self, value):
        if value:
            self.enable()
        else:
            self.disable()

    def enable(self):
        """Enable the window/control.

        Does nothing if the window/control doesn't exist.

        :command: `WinSet, Enable
           <https://www.autohotkey.com/docs/commands/WinSet.htm#Enable>`_,
           `Control, Enable
           <https://www.autohotkey.com/docs/commands/Control.htm#Enable>`_
        """
        raise NotImplementedError

    def disable(self):
        """Disable the window/control.

        Does nothing if the window/control doesn't exist.

        :command: `WinSet, Disable
           <https://www.autohotkey.com/docs/commands/WinSet.htm#Disable>`_,
           `Control, Disable
           <https://www.autohotkey.com/docs/commands/Control.htm#Disable>`_
        """
        raise NotImplementedError

    @property
    def is_visible(self):
        """The visibility of the window/control.

        Returns ``False`` if the window doesn't exist.

        :type: bool

        :command: `WinShow
           <https://www.autohotkey.com/docs/commands/WinShow.htm>`_,
           `ControlGet, $, Visible
           <https://www.autohotkey.com/docs/commands/ControlGet.htm#Visible>`_,
           `Control, Show
           <https://www.autohotkey.com/docs/commands/Control.htm#Show>`_
        """
        style = self.style
        if style is None:
            return False
        return WindowStyle.VISIBLE in style

    @is_visible.setter
    def is_visible(self, value):
        if value:
            self.show()
        else:
            self.hide()

    def show(self):
        """Show the window/control.

        Does nothing if the window/control doesn't exist.

        :command: `WinShow
           <https://www.autohotkey.com/docs/commands/WinShow.htm>`_, `Control,
           Show <https://www.autohotkey.com/docs/commands/Control.htm#Show>`_
        """
        raise NotImplementedError

    def hide(self):
        """Hide the window/control.

        Does nothing if the window/control doesn't exist.

        :command: `WinHide
           <https://www.autohotkey.com/docs/commands/WinHide.htm>`_, `Control,
           Hide <https://www.autohotkey.com/docs/commands/Control.htm#Hide>`_
        """
        raise NotImplementedError

    def send(self, keys):
        """Send simulated keystrokes to the window/control.

        Unlike the :func:`~ahkpy.send` function, mouse clicks cannot be sent.

        Does nothing if the window/control doesn't exist.

        :command: `ControlSend
           <https://www.autohotkey.com/docs/commands/ControlSend.htm>`_
        """
        # TODO: Add level, key_delay, and key_duration arguments.
        with global_ahk_lock:
            # Unlike the Send command, mouse clicks cannot be sent by
            # ControlSend. Thus, no need to set mouse_delay.
            sending._set_delay(mouse_delay=UNSET)
            control = ""
            try:
                self._call("ControlSend", control, str(keys), *self._include())
            except Error as err:
                if err.message == 1:
                    # Control doesn't exist.
                    return
                raise

    # TODO: Implement ControlClick.

    def send_message(self, msg: int, w_param: int = 0, l_param: int = 0,
                     signed_int32=False, timeout=5) -> Optional[int]:
        """Send a message to the window/control and get a response.

        The *msg* argument is the message number to send. See the `message list
        <https://www.autohotkey.com/docs/misc/SendMessageList.htm>`_ for common
        numbers. The *w_param* and *l_param* arguments are the first and second
        components of the message.

        If *signed_int32* argument is true, the response is interpreted as a
        32-bit signed integer. Defaults to ``False``.

        If there is no response after *timeout* seconds, then an :exc:`Error`
        will be raised. If *timeout* is not specified or ``None``, there is no
        limit to the wait time.

        The range of possible response values depends on the target window and
        the version of AutoHotkey that is running. When using the 32-bit version
        of AutoHotkey, or if the target window is 32-bit, the result is a 32-bit
        unsigned integer between 0 and 4294967295. When using the 64-bit version
        of AutoHotkey with a 64-bit window, the result is a 64-bit signed
        integer between -9223372036854775808 and 9223372036854775807.

        Returns ``None`` if the window/control doesn't exist.

        :command: `SendMessage
           <https://www.autohotkey.com/docs/commands/PostMessage.htm>`_
        """
        control = exclude_title = exclude_text = ""
        try:
            result = self._call(
                "SendMessage", int(msg), int(w_param), int(l_param), control,
                *self._include(), exclude_title, exclude_text,
                int(timeout * 1000),
            )
            if result is None:
                return None
            if signed_int32:
                # TODO: Can we check if the target window is 32-bit and do the
                # conversion automatically?
                return ctypes.c_int32(result).value
            return result
        except Error as err:
            if err.message == "FAIL":
                if not self.exists:
                    return None
                err.message = "there was a problem sending message or response timed out"
            raise

    def post_message(self, msg: int, w_param: int = 0, l_param: int = 0) -> Optional[bool]:
        """Post a message to the window/control.

        The *msg* argument is the message number to send. See the `message list
        <https://www.autohotkey.com/docs/misc/SendMessageList.htm>`_ for common
        numbers. The *w_param* and *l_param* arguments are the first and second
        components of the message.

        Returns ``True`` if the message was received. Returns ``False`` if there
        was a problem. Returns ``None`` if the window/control doesn't exist.

        :command: `PostMessage
           <https://www.autohotkey.com/docs/commands/PostMessage.htm>`_
        """
        control = ""
        try:
            err = self._call("PostMessage", int(msg), int(w_param), int(l_param), control, *self._include())
            if err is None:
                return None
            return not err
        except Error as err:
            if err.message == 1:
                if not self.exists:
                    return None
                err.message = "there was a problem posting message"
            raise

    def _get_pos(self):
        raise NotImplementedError

    def _move(self, x, y, width, height):
        raise NotImplementedError

    def _get(self, subcmd):
        raise NotImplementedError

    def _set(self, subcmd, value=""):
        # Used mainly by Window. Also used by Control for style and ex_style
        # properties. It's OK to use 'WinSet' for controls because control delay
        # has no effect on the 'Control, Style' command and they essentially do
        # the same.
        try:
            super()._call("WinSet", subcmd, value, *self._include())
        except Error as err:
            if err.message == 1 and not super().exists:
                return
            raise


class Window(BaseWindow):
    __slots__ = ("id",)

    @property
    def is_active(self) -> bool:
        return bool(self._call("WinActive", *self._include()))

    @property
    def text(self) -> Optional[str]:
        try:
            text = self._call("WinGetText", *self._include())
            return str(text)
        except Error as err:
            if err.message == 1:
                if not self.exists:
                    return None
                err.message = "there was a problem getting the window text"
            raise

    @property
    def title(self) -> Optional[str]:
        title = self._call("WinGetTitle", *self._include())
        # If the window doesn't exist, AHK returns an empty string. Check that
        # the window exists.
        if not self.exists:
            return None
        return str(title)

    @title.setter
    def title(self, new_title):
        return self._call("WinSetTitle", *self._include(), str(new_title))

    @property
    def pid(self) -> Optional[int]:
        return self._get("PID")

    @property
    def process_name(self) -> Optional[str]:
        return self._get("ProcessName")

    exe = process_name

    @property
    def process_path(self) -> Optional[str]:
        return self._get("ProcessPath")

    @property
    def is_minimized(self) -> Optional[bool]:
        min_max = self._get("MinMax")
        if min_max is None:
            return None
        return min_max == -1

    @is_minimized.setter
    def is_minimized(self, value):
        if value:
            self.minimize()
        elif self.is_minimized:
            self.restore()

    def toggle_minimized(self):
        is_minimized = self.is_minimized
        if is_minimized is None:
            return
        if is_minimized:
            self.restore()
        else:
            self.minimize()

    def minimize(self):
        """Minimize the window.

        Does nothing if the window doesn't exist.

        :command: `WinMinimize
           <https://www.autohotkey.com/docs/commands/WinMinimize.htm>`_
        """
        self._call("WinMinimize", *self._include(), set_delay=True)

    @property
    def is_restored(self) -> Optional[bool]:
        min_max = self._get("MinMax")
        if min_max is None:
            return None
        return min_max == 0

    def restore(self):
        """Restore the window.

        Does nothing if the window doesn't exist.

        :command: `WinRestore
           <https://www.autohotkey.com/docs/commands/WinRestore.htm>`_
        """
        self._call("WinRestore", *self._include(), set_delay=True)

    @property
    def is_maximized(self) -> Optional[bool]:
        min_max = self._get("MinMax")
        if min_max is None:
            return None
        return min_max == 1

    @is_maximized.setter
    def is_maximized(self, value):
        if value:
            self.maximize()
        elif self.is_maximized:
            self.restore()

    def toggle_maximized(self):
        is_maximized = self.is_maximized
        if is_maximized is None:
            return
        if is_maximized:
            self.restore()
        else:
            self.maximize()

    def maximize(self):
        """Maximize the window.

        Does nothing if the window doesn't exist.

        :command: `WinMaximize
           <https://www.autohotkey.com/docs/commands/WinMaximize.htm>`_
        """
        self._call("WinMaximize", *self._include(), set_delay=True)

    @property
    def control_classes(self) -> Optional[List[str]]:
        names = self._get("ControlList")
        if names is None:
            return None
        return names.splitlines()

    @property
    def controls(self) -> Optional[List[Control]]:
        handles = self._get("ControlListHwnd")
        if handles is None:
            return None
        hwnds = handles.splitlines()
        return [
            Control(int(hwnd, base=16))
            for hwnd in hwnds
        ]

    def get_control(self, class_or_text, match="startswith") -> "Control":
        try:
            control_id = self._call("ControlGet", "Hwnd", "", class_or_text, *self._include(), title_mode=match)
            return Control(control_id)
        except Error as err:
            if err.message == 1:
                # Control doesn't exist.
                return Control(None)
            raise

    def get_focused_control(self) -> "Control":
        try:
            class_name = self._call("ControlGetFocus", *self._include())
        except Error as err:
            if err.message == 1:
                # None of window's controls have input focus.
                return Control(None)
            raise
        return self.get_control(class_name)

    # TODO: Implement WinMenuSelectItem.

    @property
    def always_on_top(self) -> Optional[bool]:
        ex_style = self.ex_style
        if ex_style is None:
            return None
        return ExWindowStyle.TOPMOST in ex_style

    @always_on_top.setter
    def always_on_top(self, value):
        if value:
            self.pin_to_top()
        else:
            self.unpin_from_top()

    def pin_to_top(self):
        self._set("AlwaysOnTop", "On")

    def unpin_from_top(self):
        self._set("AlwaysOnTop", "Off")

    def toggle_always_on_top(self):
        self._set("AlwaysOnTop", "Toggle")

    def send_to_bottom(self):
        self._set("Bottom")

    def bring_to_top(self):
        self._set("Top")

    def disable(self):
        self._set("Disable")

    def enable(self):
        self._set("Enable")

    def redraw(self):
        self._set("Redraw")

    def set_region(self, options):
        # TODO: Implement better options.
        self._set("Region", options)

    def reset_region(self):
        self._set("Region", "")

    @property
    def opacity(self) -> Optional[int]:
        return self._get("Transparent")

    @opacity.setter
    def opacity(self, value):
        if value is None:
            ahk_value = "Off"
        elif not 0 <= value <= 255:
            raise ValueError("opacity value must be between 0 and 255")
        else:
            ahk_value = int(value)
        self._set("Transparent", ahk_value)

    @property
    def transparent_color(self) -> Optional[Tuple[int, int, int]]:
        result = self._get("TransColor")
        if result is None:
            return None
        hex_color = hex(result)[2:]
        return colors.to_tuple(hex_color)

    @transparent_color.setter
    def transparent_color(self, value):
        if value is None:
            ahk_value = "Off"
        else:
            r, g, b = value
            ahk_value = colors.to_hex(r, g, b)
        self._set("TransColor", ahk_value)

    def hide(self):
        self._call("WinHide", *self._include(), set_delay=True)

    def show(self):
        self._call("WinShow", *self._include(), set_delay=True)

    def activate(self, timeout=None) -> bool:
        self._call("WinActivate", *self._include())
        if timeout is None:
            return self.is_active
        return self.wait_active(timeout=timeout)

    def get_status_bar_text(self, part=0) -> Optional[str]:
        try:
            text = self._call("StatusBarGetText", int(part) + 1, *self._include())
            return str(text)
        except Error as err:
            if err.message == 1:
                if not self._status_bar_exists():
                    return None
                err.message = "status bar cannot be accessed"
            raise

    def wait_status_bar(self, bar_text="", *, timeout=None, part=0, interval=0.05) -> Optional[bool]:
        try:
            ok = self._call(
                "StatusBarWait",
                bar_text,
                timeout if timeout is not None else "",
                part + 1,
                *self._include(),
                interval * 1000,
            )
            return bool(ok)
        except Error as err:
            if err.message == 2:
                if not self._status_bar_exists():
                    return None
                err.message = "status bar cannot be accessed"
            raise

    def _status_bar_exists(self):
        status_bar = self.get_control("msctls_statusbar321")
        return bool(status_bar)

    def close(self, timeout=None) -> bool:
        self._call("WinClose", *self._include(), timeout, set_delay=True)
        # TODO: Test timeout.
        return not self.exists

    def kill(self, timeout=None) -> bool:
        self._call("WinKill", *self._include(), timeout, set_delay=True)
        # TODO: Test timeout.
        return not self.exists

    def wait_active(self, timeout=None) -> bool:
        win_id = self._call("WinWaitActive", *self._include(), timeout, set_delay=True)
        return bool(win_id)

    def wait_inactive(self, timeout=None) -> bool:
        win_id = self._call("WinWaitNotActive", *self._include(), timeout, set_delay=True)
        if win_id == "":
            # Non-existent window is inactive.
            return True
        return bool(win_id)

    def wait_hidden(self, timeout=None) -> bool:
        ok = self._call("WinWaitClose", *self._include(), timeout, hidden_windows=False, set_delay=True)
        return bool(ok)

    def wait_close(self, timeout=None) -> bool:
        ok = self._call("WinWaitClose", *self._include(), timeout, set_delay=True)
        return bool(ok)

    def _move(self, x, y, width, height):
        self._call("WinMove", *self._include(), x, y, width, height, set_delay=True)

    def _get_pos(self):
        return self._call("WinGetPos", *self._include())

    def _get(self, subcmd):
        result = self._call("WinGet", subcmd, *self._include())
        if result == "":
            return None
        return result

    def _set_delay(self):
        ahk_call("SetWinDelay", optional_ms(get_settings().win_delay))


class Control(BaseWindow):
    __slots__ = ("id",)

    @property
    def is_checked(self) -> Optional[bool]:
        checked = self._get("Checked")
        if checked is None:
            return None
        return bool(checked)

    @is_checked.setter
    def is_checked(self, value):
        if value:
            self.check()
        else:
            self.uncheck()

    def check(self):
        return self._call("Control", "Check", "", "", *self._include(), set_delay=True)

    def uncheck(self):
        return self._call("Control", "Uncheck", "", "", *self._include(), set_delay=True)

    def enable(self):
        return self._call("Control", "Enable", "", "", *self._include(), set_delay=True)

    def disable(self):
        return self._call("Control", "Disable", "", "", *self._include(), set_delay=True)

    def hide(self):
        return self._call("Control", "Hide", "", "", *self._include(), set_delay=True)

    def show(self):
        return self._call("Control", "Show", "", "", *self._include(), set_delay=True)

    @property
    def text(self) -> Optional[str]:
        text = self._call("ControlGetText", "", *self._include())
        if text is None:
            return None
        return str(text)

    @text.setter
    def text(self, value):
        return self._call("ControlSetText", "", str(value), *self._include(), set_delay=True)

    @property
    def is_focused(self) -> bool:
        if not self:
            return False
        focused_control = windows.get_active().get_focused_control()
        if not focused_control:
            return False
        return self == focused_control

    def focus(self):
        return self._call("ControlFocus", "", *self._include(), set_delay=True)

    def paste(self, text):
        """Paste *text* at the caret/insert position in an Edit control.

        This does not affect the contents of the clipboard.
        """
        self._call("Control", "EditPaste", str(text), "", *self._include(), set_delay=True)

    @property
    def line_count(self) -> Optional[int]:
        """Retrieve the number of lines in an Edit control.

        All Edit controls have at least 1 line, even if the control is empty.
        """
        return self._get("LineCount")

    @property
    def current_line_number(self) -> Optional[int]:
        """Retrieve the line number in an Edit control where the caret (insert
        point) resides.

        The first line is 0. If there is text selected in the control, the
        result is set to the line number where the selection begins.
        """
        result = self._get("CurrentLine")
        if result is None:
            return None
        return result - 1

    @property
    def current_column(self) -> Optional[int]:
        """Retrieve the column number in an Edit control where the caret (text
        insertion point) resides.

        The first column is 0. If there is text selected in the control,
        the result is set to the column number where the selection begins.
        """
        result = self._get("CurrentCol")
        if result is None:
            return None
        return result - 1

    def get_line(self, lineno: int) -> Optional[str]:
        """Retrieve the text of line *lineno* in an Edit control.

        Line 0 is the first line. If the specified line number does not exist,
        an ahkpy.Error is raised.
        """
        line_count = self.line_count
        if line_count is None:
            return None
        if lineno < 0:
            lineno = line_count + lineno
        out_of_range_err = "line number out of range"
        if not 0 <= lineno < line_count:
            raise Error(out_of_range_err)

        try:
            result = self._get("Line", lineno + 1)
            if result is None:
                return None
            return str(result)
        except Error as err:
            if err.message == 1:
                if lineno < self.line_count:
                    return ""
                err.message = out_of_range_err
            raise

    @property
    def current_line(self) -> Optional[str]:
        """Retrieve the text of the line in an Edit control where the caret
        (insert point) resides.

        If there is text selected in the control, the result is set to the line
        number where the selection begins.
        """
        lineno = self.current_line_number
        if lineno is None:
            return None
        return self.get_line(lineno)

    @property
    def selected_text(self) -> Optional[str]:
        """Retrieve the selected text in an Edit control.

        If no text is selected, the result is an empty string. Certain types of
        controls, such as RichEdit20A, might not produce the correct text in
        some cases (e.g. Metapad).
        """
        result = self._get("Selected")
        if result is None:
            return None
        return str(result)

    @property
    def list_choice(self) -> Optional[str]:
        """Retrieve the name of the currently selected entry in a ListBox or
        ComboBox.
        """
        try:
            choice = self._get("Choice")
            if choice is None:
                return None
            return str(choice)
        except Error as err:
            if err.message == 1 and self.list_choice_index == -1:
                return None
            raise

    @property
    def list_choice_index(self) -> Optional[int]:
        """Retrieve or set the index of the currently selected entry in a
        ListBox or ComboBox.
        """
        class_name = self.class_name
        if class_name is None:
            return None

        class_name_lower = class_name.lower()
        if "combo" in class_name_lower:
            getcursel = CB_GETCURSEL
        elif "list" in class_name_lower:
            getcursel = LB_GETCURSEL
        else:
            return None

        result = self.send_message(getcursel, signed_int32=True, timeout=5)
        if result is None:
            return None
        return result

    @list_choice_index.setter
    def list_choice_index(self, index):
        self.choose_item_index(index)

    def choose_item_index(self, index):
        """Set the selection in a ListBox or ComboBox to be the Nth entry."""
        index = int(index)
        if index < 0:
            index = self.list_item_count + index
        try:
            self._call("Control", "Choose", index + 1, set_delay=True)
        except Error as err:
            if err.message == 1:
                if self.list_item_count < index + 1:
                    raise
            raise

    def choose_item(self, value):
        """Set the selection (choice) in a ListBox or ComboBox to be the first
        entry whose leading part matches *value*.
        """
        value = str(value)
        try:
            self._call("Control", "ChooseString", value, set_delay=True)
        except Error as err:
            if err.message == 1 and self.list_item_index(value) == -1:
                err.message = f"list item {value!r} doesn't exist"
            raise

    def list_item_index(self, value) -> Optional[int]:
        """Retrieve the entry number of a ListBox or ComboBox that is a case
        insensitive match for *value*.
        """
        # Let's implement this in Python because in AHK there's no difference
        # between "an error trying to find the string" and "no such string
        # found".
        class_name = self.class_name
        if class_name is None:
            return None

        class_name_lower = class_name.lower()
        if "combo" in class_name_lower:
            find_string_exact = CB_FINDSTRINGEXACT
        elif "list" in class_name_lower:
            find_string_exact = LB_FINDSTRINGEXACT
        else:
            return None

        value_buffer = ctypes.create_unicode_buffer(value)
        result = self.send_message(
            msg=find_string_exact,
            w_param=-1,
            l_param=ctypes.addressof(value_buffer),
            signed_int32=True,
            timeout=5,
        )
        if result is None:
            return None
        return result

    @property
    def list_items(self) -> Optional[list]:
        """Retrieve a list of items from a ListView, ListBox, ComboBox, or
        DropDownList.
        """
        try:
            items = self._get("List")
        except Error as err:
            if err.message == 1:
                err.message = "there was a problem getting list items"
            raise
        if items is None:
            return None
        # AHK separates list items with a '\n' character. Also, in case
        # of ListViews the items may have multiple columns that are
        # separated by a '\t' character. Unfortunately, AHK does not
        # escape the '\n' and '\t' characters in the list items and
        # columns, so there's no guaranteed way to split and get the
        # correct values. However, the '\n' and '\t' characters are rare
        # in these controls, so the convenience of working on a list of
        # strings is more valuable than potential corner cases.
        class_name = self.class_name
        if class_name is None:
            return None
        if "syslistview32" in class_name.lower():
            return self._split_list_items(items)
        return items.split("\n")

    @property
    def selected_list_items(self) -> Optional[List[List[str]]]:
        """Retrieve only the selected (highlighted) rows in a ListView control.
        """
        return self.get_list_items(selected=True)

    @property
    def focused_list_item(self) -> Optional[List[str]]:
        """Retrieve only the focused row in a ListView control."""
        items = self.get_list_items(focused=True)
        if items is None or len(items) == 0:
            return None
        return items[0]

    def get_list_items(self, selected=False, focused=False, column: int = None) -> Optional[list]:
        """Retrieve items from a ListView control.

        :param selected: If ``True``, returns only selected rows.
        :param focused: If ``True``, returns only the focused row.
        :param column: return rows with only the given column, indexed by its
           number. Supports negative indexing.
        :type column: int
        """
        options = []
        if selected:
            options.append("Selected")
        if focused:
            options.append("Focused")
        column_count = self.list_view_column_count
        if column_count is None:
            return None
        if column is not None:
            if column < 0:
                column = column_count + column
            options.append(f"Col{column + 1}")
        str_options = " ".join(options)
        try:
            items = self._get("List", str_options)
            if items is None:
                return None
            if column is not None:
                return items.split('\n')
            return self._split_list_items(items)
        except Error as err:
            if err.message == 1:
                class_name = self.class_name
                if class_name is None:
                    return None
                if "syslistview32" not in class_name.lower():
                    return None
                if column is not None and column_count < column + 1:
                    err.message = "column index out of range"
                else:
                    err.message = "there was a problem getting list items"
            raise err

    def _split_list_items(self, string):
        if string == "":
            return []
        return [item.split("\t") for item in string.split("\n")]

    @property
    def list_item_count(self) -> Optional[int]:
        """Retrieve a single number that is the total number of rows in a
        ListBox, ComboBox, or ListView control.
        """
        class_name = self.class_name
        if class_name is None:
            return None

        class_name_lower = class_name.lower()
        if "syslistview32" in class_name_lower:
            return self._count_list_items()

        if "combo" in class_name_lower:
            get_count = CB_GETCOUNT
        elif "list" in class_name_lower:
            get_count = LB_GETCOUNT
        else:
            return None

        result = self.send_message(get_count, timeout=5)
        if result is None:
            return None
        return result

    @property
    def selected_list_item_count(self) -> Optional[int]:
        """Retrieve the number of selected (highlighted) rows in a ListView
        control.
        """
        return self._count_list_items("Selected")

    @property
    def focused_list_item_index(self) -> Optional[int]:
        """Retrieve the row number (position) of the focused row (-1 if none)
        in a ListView control.
        """
        count = self._count_list_items("Focused")
        if count is None:
            return None
        return count - 1

    @property
    def list_view_column_count(self) -> Optional[int]:
        """Retrieve the number of columns in a ListView control (or -1 if the
        count cannot be determined).
        """
        return self._count_list_items("Col")

    def _count_list_items(self, option="") -> Optional[int]:
        try:
            return self._get("List", f"Count {option}")
        except Error as err:
            if err.message == 1:
                class_name = self.class_name
                if class_name is None:
                    return None
                if "syslistview32" not in class_name.lower():
                    return None
                err.message = "there was a problem getting list items"
            raise err

    def _get_pos(self):
        return self._call("ControlGetPos", "", *self._include())

    def _move(self, x, y, width, height):
        self._call("ControlMove", "", x, y, width, height, *self._include(), set_delay=True)

    def _get(self, subcmd, value=""):
        return self._call("ControlGet", subcmd, value, "", *self._include())

    def _set_delay(self):
        ahk_call("SetControlDelay", optional_ms(get_settings().control_delay))

    def _call(self, cmd, *args, hidden_windows=True, title_mode=None, set_delay=False):
        try:
            return super()._call(cmd, *args, hidden_windows=hidden_windows, title_mode=title_mode, set_delay=set_delay)
        except Error as err:
            if err.message == 1 and not super().exists:
                return None
            raise


def _set_title_match_mode(title_mode):
    if title_mode == "startswith":
        ahk_call("SetTitleMatchMode", 1)
    elif title_mode == "contains":
        ahk_call("SetTitleMatchMode", 2)
    elif title_mode == "exact":
        ahk_call("SetTitleMatchMode", 3)
    elif title_mode == "regex":
        ahk_call("SetTitleMatchMode", "regex")
    else:
        raise ValueError(f"{title_mode!r} is not a valid title match mode")


class WindowStyle(enum.IntFlag):
    """The object that holds the window styles.

    For more information on styles refer to `Window Styles
    <https://docs.microsoft.com/en-us/windows/win32/winmsg/window-styles>`_ on
    Microsoft Docs.
    """
    BORDER = 0x00800000
    CAPTION = 0x00C00000
    CHILD = 0x40000000
    CHILDWINDOW = 0x40000000
    CLIPCHILDREN = 0x02000000
    CLIPSIBLINGS = 0x04000000
    DISABLED = 0x08000000
    DLGFRAME = 0x00400000
    GROUP = 0x00020000
    HSCROLL = 0x00100000
    ICONIC = 0x20000000
    MAXIMIZE = 0x01000000
    MAXIMIZEBOX = 0x00010000
    MINIMIZE = 0x20000000
    MINIMIZEBOX = 0x00020000
    OVERLAPPED = 0x00000000
    POPUP = 0x80000000
    SIZEBOX = 0x00040000
    SYSMENU = 0x00080000
    TABSTOP = 0x00010000
    THICKFRAME = 0x00040000
    TILED = 0x00000000
    VISIBLE = 0x10000000
    VSCROLL = 0x00200000
    OVERLAPPEDWINDOW = (OVERLAPPED | CAPTION | SYSMENU | THICKFRAME | MINIMIZEBOX | MAXIMIZEBOX)
    POPUPWINDOW = (POPUP | BORDER | SYSMENU)
    TILEDWINDOW = (OVERLAPPED | CAPTION | SYSMENU | THICKFRAME | MINIMIZEBOX | MAXIMIZEBOX)


class ExWindowStyle(enum.IntFlag):
    """The object that holds the extended window styles.

    For more information on styles refer to `Extended Window Styles
    <https://docs.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles>`_
    on Microsoft Docs.
    """
    ACCEPTFILES = 0x00000010
    APPWINDOW = 0x00040000
    CLIENTEDGE = 0x00000200
    COMPOSITED = 0x02000000
    CONTEXTHELP = 0x00000400
    CONTROLPARENT = 0x00010000
    DLGMODALFRAME = 0x00000001
    LAYERED = 0x00080000
    LAYOUTRTL = 0x00400000
    LEFT = 0x00000000
    LEFTSCROLLBAR = 0x00004000
    LTRREADING = 0x00000000
    MDICHILD = 0x00000040
    NOACTIVATE = 0x08000000
    NOINHERITLAYOUT = 0x00100000
    NOPARENTNOTIFY = 0x00000004
    NOREDIRECTIONBITMAP = 0x00200000
    RIGHT = 0x00001000
    RIGHTSCROLLBAR = 0x00000000
    RTLREADING = 0x00002000
    STATICEDGE = 0x00020000
    TOOLWINDOW = 0x00000080
    TOPMOST = 0x00000008
    TRANSPARENT = 0x00000020
    WINDOWEDGE = 0x00000100
    OVERLAPPEDWINDOW = (WINDOWEDGE | CLIENTEDGE)
    PALETTEWINDOW = (WINDOWEDGE | TOOLWINDOW | TOPMOST)


CB_FINDSTRINGEXACT = 0x158
CB_GETCOUNT = 0x146
CB_GETCURSEL = 0x147
LB_FINDSTRINGEXACT = 0x1A2
LB_GETCOUNT = 0x18B
LB_GETCURSEL = 0x188
