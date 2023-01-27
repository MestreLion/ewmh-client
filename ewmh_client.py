# ewmh-client: EWMH (Extended Window Manager Hints) Client API
#
# Copyright (C) 2023 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. See <http://www.gnu.org/licenses/gpl.html>
"""
EWMH (Extended Window Manager Hints) Client API

References:

EWMH
- https://specifications.freedesktop.org/wm-spec/latest/

ICCCM (Inter-Client Communication Conventions Manual)
- https://en.wikipedia.org/wiki/Inter-Client_Communication_Conventions_Manual
- https://tronche.com/gui/x/icccm/

X Window System
- https://www.x.org/releases/current/doc/index.html
- https://www.x.org/releases/current/doc/xproto/x11protocol.html

Xlib (C)
- https://www.x.org/releases/current/doc/libX11/libX11/libX11.html
- https://tronche.com/gui/x/

Xlib (Python)
- https://python-xlib.github.io/
- https://github.com/python-xlib/python-xlib/tree/master/examples

Also helpful
- https://twiserandom.com/unix/x11/what-is-an-atom-in-x11/index.html
- https://twiserandom.com/unix/x11/what-is-a-property-in-x11/index.html
"""

__version__ = "0.0.1"

import enum
import typing as t

import typing_extensions as te

import Xlib.display
import Xlib.protocol
import Xlib.X
import Xlib.Xatom
import Xlib.xobject.drawable

if t.TYPE_CHECKING:
    import Xlib.error

_T = t.TypeVar("_T")

# Aliases for XLib
XWindow: te.TypeAlias = Xlib.xobject.drawable.Window  # Xlib Window
XDisplay: te.TypeAlias = Xlib.display.Display
XRId: te.TypeAlias = int  # Xlib.xobject.resource.Resource().id
XAtom: te.TypeAlias = int
XErrorHandler: te.TypeAlias = t.Callable[
    [Xlib.error.XError, t.Optional[Xlib.protocol.rq.Request]], _T
]


# Other aliases and definitions
AtomLike: te.TypeAlias = t.Union["Atom", int, str]
# Property value type is bytes if format <= 8, array.array('H' or 'I', ...) otherwise
# Can't annotate array.array in Python < 3.9, see:
# https://stackoverflow.com/a/69200620/624066
PropertyValue: te.TypeAlias = t.Union[bytes, t.Sequence[int]]


class Source(enum.IntEnum):
    """Source indication in requests

    https://specifications.freedesktop.org/wm-spec/latest/ar01s09.html#sourceindication
    """

    NONE = 0
    APPLICATION = 1
    USER = 2


class Format(enum.IntEnum):
    """Item bit size of a Property value sequence

    https://www.x.org/releases/current/doc/xproto/x11protocol.html#requests:ChangeProperty
    """

    CHAR = 8
    SHORT = 16
    INT = 32


class Mode(enum.IntEnum):
    """Mode when setting a Property

    https://www.x.org/releases/current/doc/xproto/x11protocol.html#requests:ChangeProperty
    """

    REPLACE = Xlib.X.PropModeReplace
    PREPEND = Xlib.X.PropModePrepend
    APPEND = Xlib.X.PropModeAppend


class EwmhError(Exception):
    """Base exception for this module"""

    # TODO: When bumping to 3.8, make msg a positional-only argument
    # pylint: disable=W1113
    def __init__(self, msg: object = "", *args: object):
        super().__init__((str(msg) % args) if args else msg)


# TODO: Consider distinct Property and TextProperty
#  each a subclass of array or bytes/str. Advantages:
#  - Directly return prop instead of prop.value everywhere
#  - Errors and other attributes still accessible
class Property(t.NamedTuple):
    """Window Property"""

    name: str
    handle: XWindow
    type: XAtom
    format: int
    value: PropertyValue

    def raise_on_missing(self) -> None:
        if self.type == Xlib.X.NONE:  # and/or self.format == 0
            raise EwmhError("Property %r not found in %s", self.name, self.handle)


class Atom(int):
    """X Atom, a named integer"""

    # Neither Pycharm nor mypy can infer instance attribute types from __new__,
    # so we redundantly declare them here. See:
    # https://github.com/python/mypy/issues/1021
    # https://youtrack.jetbrains.com/issue/PY-37225
    _display: XDisplay
    _name: str

    def __new__(cls, value: AtomLike, display: XDisplay, create: bool = False) -> "Atom":
        if isinstance(value, Atom):
            return value
        if isinstance(value, str):
            name = value
            value = display.get_atom(value, only_if_exists=not create)
            if value == Xlib.X.NONE:
                raise EwmhError("Atom does not exist: %s", value)
        else:  # int
            name = display.get_atom_name(value)
        self: "Atom" = super().__new__(cls, value)
        # TODO: do we _really_ need to store display? Why not request name now?
        self._display = display
        self._name = name
        return self

    @property
    def name(self) -> str:
        if not self._name:
            self._name = self.display.get_atom_name(self)
        return self._name

    @property
    def display(self) -> XDisplay:
        return self._display

    # TODO: re-think and improve equality and identity
    def __eq__(self, other: object) -> bool:
        if isinstance(other, Atom):
            return super().__eq__(other) and self._display is other._display
        if isinstance(other, int):
            return super().__eq__(other)
        if isinstance(other, str):
            return other == self.name
        return NotImplemented

    def __hash__(self) -> int:
        return super().__hash__()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({super().__repr__()}) {self.name}>"

    def __str__(self) -> str:
        return self.name


class Window:
    """Application Window Properties"""

    def __init__(self, window_id: XRId, root: "EWMH"):
        self._root: "EWMH" = root
        if root is not self:
            self._display: XDisplay = self._root.display
            self._screen_number: int = self._root.screen_number
            self._display_name: str = self._root.display_name
            self._handle: XWindow = self._display.create_resource_object("window", window_id)
            assert self.id == window_id
        else:
            # self._display and self._screen_number set by EWMH.__init__()
            self._display_name = self._root.display.get_display_name()
            self._handle = self.display.screen(self._root.screen_number).root

        # TODO: create an Enum-like self.ATOM collection of Atom()s with all predefined
        #  constants in XLib.Xatom, possibly adding new ones when known/instantiated.
        #  Add Atom.predefined(int, str, display?) to avoid an X request
        #  ... k: Atom.predefined(v, k) for k, v in vars(Xlib.Xatom).items() ...

        self.UTF8_STRING: Atom = self.Atom("UTF8_STRING")  # pylint: disable=C0103
        self.ENCODINGS: t.Dict[XAtom, str] = {  # pylint: disable=C0103
            # https://tronche.com/gui/x/icccm/sec-2.html#s-2.7.1
            Xlib.Xatom.STRING: "latin-1",
            self.UTF8_STRING: "utf-8",
        }
        # TODO: add itself to a "known windows" ID-keyed dict in root,
        #  so it returns the same instance on same IDs, allowing `is` tests

    @property
    def display(self) -> XDisplay:
        return self._display

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def screen_number(self) -> int:
        return self._screen_number

    @property
    def root(self) -> "EWMH":
        return self._root

    @property
    def handle(self) -> XWindow:
        return self._handle

    @property
    def id(self) -> XRId:  # pylint: disable=C0103
        return self._handle.id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Window):
            return NotImplemented
        # Same ID and root (same root means same display and screen)
        return self.id == other.id and self.root is other.root

    def __repr__(self) -> str:
        # Intentionally subtle difference from XWindow.__repr__()
        return f"<{self.__class__.__name__}({self.id:#010x})>"

    # pylint: disable=C0103
    def Atom(self, value: AtomLike, create: bool = False) -> Atom:  # noqa: N802
        return Atom(value, display=self.display, create=create)

    # -------------------------------------------------------------------------
    # Xlib interface methods

    # https://www.x.org/releases/current/doc/xproto/x11protocol.html#requests:GetProperty
    def get_property(
        self,
        name: AtomLike,
        expected_type: t.Union[XAtom, int] = Xlib.X.AnyPropertyType,
        size_hint: int = 256,
    ) -> Property:
        name_atom = self.Atom(name)
        xprop: t.Optional[Xlib.protocol.request.GetProperty] = self.handle.get_full_property(
            property=name_atom,
            property_type=expected_type,
            sizehint=size_hint,
        )
        if xprop is None:
            # TODO: several approaches here:
            # raise EwmhError("Property %r not found in %s", name_atom, self)
            # return None, and change *all* methods to return Optional
            # return default, and add this parameter in **all* methods
            # return dummy Property, add Property.raise_for_missing(), requests style
            # Using the latter approach for now
            return Property(
                name=str(name),
                handle=self.handle,
                type=Xlib.X.NONE,
                format=0,
                value=b"",  # make it easy for text properties
            )

        # Create our own Property object
        # Discarding from xprop: sequence_number/_serial, bytes_after
        prop = Property(
            name=str(name),  # TODO: embrace Atom!
            handle=self.handle,  # TODO: embrace Window!
            type=self.Atom(xprop.property_type),
            format=Format(xprop.format),
            value=xprop.value,
        )

        # Consistency checks
        # TODO: could be warnings instead, maybe based on a `check` argument
        # Requested type consistent with received type
        if expected_type not in (Xlib.X.AnyPropertyType, prop.type):
            # TODO: include property type atom names
            raise EwmhError(
                "Property type mismatch, expected %s and got %s: %s",
                self.Atom(expected_type),
                self.Atom(prop.type),
                prop,
            )
        # This happens if (and possibly only if) the above property_type check fails
        # See https://github.com/python-xlib/python-xlib/issues/212
        if xprop.bytes_after > 0:
            raise EwmhError("Incomplete property, %s bytes left: %s", xprop.bytes_after, prop)

        return prop

    # TODO: accept a Property instance instead/alongside of name/data/type/format?
    def set_property(
        self,
        name: AtomLike,
        data: PropertyValue,
        property_type: AtomLike,
        data_format: Format = Format.INT,
        mode: Mode = Mode.REPLACE,
        onerror: t.Optional[XErrorHandler[_T]] = None,
        immediate: bool = True,
    ) -> None:
        if isinstance(data, bytes) and data_format != Format.CHAR:
            raise EwmhError(
                "Format mismatch for bytes data: expected %s, got %s",
                Format.CHAR,
                Format(data_format),
            )

        # FIXME: provisional, for testing
        def error_handler(*args: object, **kwargs: object) -> None:
            raise EwmhError("Error in set_property(%s): %s", params, locals())

        params = locals().copy()
        self.handle.change_property(
            property=self.Atom(name),
            property_type=self.Atom(property_type),
            format=data_format,
            data=data,
            mode=mode,
            onerror=onerror or error_handler,
        )
        if immediate:
            self.display.flush()

    # TODO: consider assuming/enforcing UTF-8 for get/set_text_property(),
    #   as is the case in all EWMH Spec methods
    def get_text_property(
        self,
        name: AtomLike,
        expected_type: t.Union[XAtom, int] = Xlib.X.AnyPropertyType,
        encoding: t.Optional[str] = None,
        decode_errors: str = "strict",
    ) -> str:
        prop = self.get_property(name, expected_type)
        text = prop.value
        # Lame shortcut for missing properties.
        if text == b"":
            # TODO: same problem with get_property(): What to do?
            # Options: prop.raise_on_missing(), return None, return default, etc...
            return ""
        # `if prop.format != 8` would be more xlib-agnostic, but harder on type checkers
        if not isinstance(text, bytes):
            raise EwmhError("Not a text property: %s", prop)
        # mypy bug, can't use `encoding` itself: https://github.com/python/mypy/issues/11337
        enc: str = self.ENCODINGS.get(prop.type, "ascii") if encoding is None else encoding
        return text.decode(encoding=enc, errors=decode_errors)

    def set_text_property(
        self,
        name: AtomLike,
        text: str,
        property_type: AtomLike = "UTF8_STRING",
        encoding: t.Optional[str] = None,
        encode_errors: str = "strict",
        mode: Mode = Mode.REPLACE,
        onerror: t.Optional[XErrorHandler[_T]] = None,
        immediate: bool = True,
    ) -> None:
        type_atom = self.Atom(property_type)
        if type_atom not in self.ENCODINGS:  # lame
            raise EwmhError(
                "%r is not a text property type, must be one of %: %s",
                type_atom,
                [self.Atom(_) for _ in self.ENCODINGS],
            )

        enc: str = self.ENCODINGS.get(type_atom, "") if encoding is None else encoding
        data: bytes = text.encode(encoding=enc, errors=encode_errors)
        self.set_property(
            name=name,
            data=data,
            property_type=type_atom,
            data_format=Format.CHAR,
            mode=Mode(mode),
            onerror=onerror,
            immediate=immediate,
        )

    def send_message(self, name: str, *data: int, window_id: XRId = Xlib.X.NONE) -> None:
        """Send a Client Message event to the Root Window"""
        # https://python-xlib.github.io/python-xlib_13.html#Sending-Events
        # https://tronche.com/gui/x/xlib/events/client-communication/client-message.html

        if len(data) > 5:
            raise EwmhError(
                "Client Message data must have at most 5 items, got %s: %s",
                len(data),
                data,
            )
        ev = Xlib.protocol.event.ClientMessage(
            window=window_id,
            client_type=self.display.get_atom(name, only_if_exists=True),
            data=(32, (data + (0,) * 5)[:5]),
        )
        mask = Xlib.X.SubstructureRedirectMask | Xlib.X.SubstructureNotifyMask
        self.root.handle.send_event(ev, event_mask=mask, propagate=False)
        self.display.flush()  # TODO: should be conditioned to an `immediate` flag

    # -------------------------------------------------------------------------
    # Application Window Properties
    def get_wm_name(self) -> str:
        return self.get_text_property("_NET_WM_NAME", self.UTF8_STRING)

    def set_wm_name(self, text: str) -> None:
        self.set_text_property("_NET_WM_NAME", text, self.UTF8_STRING)

    #     _net_wm_visible_name
    #     _net_wm_icon_name
    #     _net_wm_visible_icon_name
    #     _net_wm_desktop
    #     _net_wm_window_type
    #     _net_wm_state
    #     _net_wm_allowed_actions
    #     _net_wm_strut
    #     _net_wm_strut_partial
    #     _net_wm_icon_geometry
    #     _net_wm_icon
    #     _net_wm_pid
    #     _net_wm_handled_icons
    #     _net_wm_user_time
    #     _net_wm_user_time_window
    #     _net_frame_extents
    #     _net_wm_opaque_region
    #     _net_wm_bypass_compositor

    #     _NET_WM_VISIBLE_NAME
    #     _NET_WM_ICON_NAME
    #     _NET_WM_VISIBLE_ICON_NAME
    #     _NET_WM_DESKTOP
    #     _NET_WM_WINDOW_TYPE
    #     _NET_WM_STATE
    #     _NET_WM_ALLOWED_ACTIONS
    #     _NET_WM_STRUT
    #     _NET_WM_STRUT_PARTIAL
    #     _NET_WM_ICON_GEOMETRY
    #     _NET_WM_ICON
    #     _NET_WM_PID
    #     _NET_WM_HANDLED_ICONS
    #     _NET_WM_USER_TIME
    #     _NET_WM_USER_TIME_WINDOW
    #     _NET_FRAME_EXTENTS
    #     _NET_WM_OPAQUE_REGION
    #     _NET_WM_BYPASS_COMPOSITOR

    # TODO: add some methods from root that act upon itself (close, activate, etc)


class EWMH(Window):
    """Root Window Properties (and Related Messages)

    display_name: if None, connects to $DISPLAY, usually ":0"
    screen_number: if None, uses default screen set in display_name or 0
    """

    def __init__(
        self,
        display_name: t.Optional[str] = None,
        screen_number: t.Optional[int] = None,
    ):
        self._display: XDisplay = Xlib.display.Display(display_name)
        if screen_number is None:
            self._screen_number = self._display.get_default_screen()
        else:
            self._screen_number = screen_number
        super().__init__(window_id=Xlib.X.NONE, root=self)

    def __repr__(self) -> str:
        return (
            f"<RootWindow {self.id:#010x}"
            f' connected to "{self.display_name}"'
            f" screen {self.screen_number}>"
        )

    # -------------------------------------------------------------------------
    # Root Window Properties (and Related Messages)

    def get_supported(self) -> t.List[XAtom]:
        return list(self.get_property("_NET_SUPPORTED", Xlib.Xatom.ATOM).value)

    def get_client_list(self) -> t.List[Window]:
        return [
            Window(window_id=w, root=self)
            for w in self.get_property("_NET_CLIENT_LIST", Xlib.Xatom.WINDOW).value
        ]

    def get_number_of_desktops(self) -> int:
        return self.get_property("_NET_NUMBER_OF_DESKTOPS", Xlib.Xatom.CARDINAL).value[0]

    def set_number_of_desktops(self, new_number_of_desktops: int) -> None:
        self.send_message("_NET_NUMBER_OF_DESKTOPS", new_number_of_desktops)

    #     _net_desktop_geometry
    #     _net_desktop_viewport
    #     _net_current_desktop
    #     _NET_DESKTOP_GEOMETRY
    #     _NET_DESKTOP_VIEWPORT
    #     _NET_CURRENT_DESKTOP

    def get_desktop_names(self) -> t.List[str]:
        return self.get_text_property("_NET_DESKTOP_NAMES", self.UTF8_STRING)[:-1].split("\0")

    def get_active_window(self) -> Window:
        prop = self.get_property("_NET_ACTIVE_WINDOW", Xlib.Xatom.WINDOW)
        return Window(window_id=prop.value[0], root=self)

    def set_active_window(
        self,
        window_to_activate: Window,
        source_indication: Source = Source.USER,
        timestamp: int = Xlib.X.CurrentTime,
        requestor_window: t.Optional[Window] = None,
    ) -> None:
        self.send_message(
            "_NET_ACTIVE_WINDOW",
            source_indication,
            timestamp,
            Xlib.X.NONE if requestor_window is None else requestor_window.id,
            window_id=window_to_activate.id,
        )

    #     _net_workarea
    #     _net_supporting_wm_check
    #     _net_virtual_roots
    #     _net_desktop_layout
    #     _net_showing_desktop
    #     _NET_WORKAREA
    #     _NET_SUPPORTING_WM_CHECK
    #     _NET_VIRTUAL_ROOTS
    #     _NET_DESKTOP_LAYOUT
    #     _NET_SHOWING_DESKTOP

    # -------------------------------------------------------------------------
    # Other Root Window Messages
    #     _net_close_window
    #     _net_moveresize_window
    #     _net_wm_moveresize
    #     _net_restack_window
    #     _net_request_frame_extents
    #     _NET_CLOSE_WINDOW
    #     _NET_MOVERESIZE_WINDOW
    #     _NET_WM_MOVERESIZE
    #     _NET_RESTACK_WINDOW
    #     _NET_REQUEST_FRAME_EXTENTS

    # -------------------------------------------------------------------------
    # Window Manager Protocols
    #     _net_wm_ping
    #     _net_wm_sync_request
    #     _net_wm_fullscreen_monitors
    #     _NET_WM_PING
    #     _NET_WM_SYNC_REQUEST
    #     _NET_WM_FULLSCREEN_MONITORS

    # -------------------------------------------------------------------------
    # Other Properties
    #     _net_wm_full_placement
    #     _NET_WM_FULL_PLACEMENT

    # -------------------------------------------------------------------------
    # Compositing Managers
    #     _net_wm_cm_sn manager selection
    #     wm_transient_for for override-redirect windows
    #     _NET_WM_CM_Sn Manager Selection
    #     WM_TRANSIENT_FOR for override-redirect windows


def _run_get_tests() -> None:
    ewmh = EWMH()
    print(ewmh)
    print((ewmh.display_name, ewmh.screen_number))
    print((ewmh.display, ewmh.display.display))
    print(ewmh.root is ewmh)
    print(ewmh.handle)
    print(ewmh.handle.display is ewmh.display.display)

    prop = ewmh.get_property("_NET_SUPPORTED")
    properties = ewmh.get_supported()
    print(properties == list(prop.value))
    print(f"Root Window supported properties: {len(properties)}")
    for atom in properties:
        print(f"\t{ewmh.Atom(atom)!r}")

    windows = ewmh.get_client_list()
    print(f"Client Windows: {len(windows)}")
    for window in windows:
        print(f"\t{window}")

    print(f"Number of Desktops: {ewmh.get_number_of_desktops()}")

    if ewmh.Atom("_NET_DESKTOP_NAMES") in properties:
        ...
    else:
        print("Root window does not support _NET_DESKTOP_NAMES")

    prop = ewmh.get_property("_NET_ACTIVE_WINDOW")
    print(prop)
    wid = prop.value[0]
    win = ewmh.get_active_window()
    print(win)
    print(win.handle)
    print(win.id == wid)

    name = win.get_text_property("_NET_WM_NAME")
    print(repr(name))
    print(name == win.get_wm_name())


def _run_set_tests() -> None:
    ewmh = EWMH()

    original_num = ewmh.get_number_of_desktops()
    print(f"Current number of Desktops: {original_num}")
    for expected_num in (original_num + 1, original_num + 2, original_num):
        ewmh.set_number_of_desktops(expected_num)
        time.sleep(0.1)
        start = time.time()
        actual_num = 0
        while time.time() - start < 2:
            actual_num = ewmh.get_number_of_desktops()
            if actual_num == expected_num:
                break
            time.sleep(0.5)
        if expected_num not in (actual_num, ewmh.get_number_of_desktops()):
            print("Window Manager refused to change number of desktops")
            break
        print(f"Number of Desktops: {actual_num}")

    active = ewmh.get_active_window()
    print(f"Active window: {active}")
    for win in (w for w in reversed(ewmh.get_client_list()) if not w == active):
        # TODO: notice we **must** use equality (`==`) above, NOT identity! (`is`)
        name = win.get_wm_name()
        if not name:
            continue

        print(f"Running tests on {win} {name!r}")
        ewmh.set_active_window(win)
        time.sleep(2)
        print(f"Active window: {ewmh.get_active_window()}")
        win.set_text_property("_NET_WM_NAME", "Testing set_text_property(_NET_WM_NAME)")
        time.sleep(1)
        print(win.get_wm_name())
        win.set_wm_name("Testing set_wm_name()")
        time.sleep(1)
        print(win.get_wm_name())
        print("Restoring status")
        win.set_wm_name(name)
        ewmh.set_active_window(active)
        time.sleep(1)
        print(win.get_wm_name())
        print(f"Active window: {ewmh.get_active_window()}")
        break
    else:
        print("No named window besides the active one, not running some tests")


# FIXME: temporary, for tests
def main() -> None:
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(f"EWMH Tests\nUsage: {sys.argv[0]} [-h|--help] [RUN_SET_TESTS]")
        return
    _run_get_tests()
    if args:
        _run_set_tests()


if __name__ == "__main__":
    import sys
    import time

    main()
