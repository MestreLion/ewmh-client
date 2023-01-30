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

# Type vars
_T = t.TypeVar("_T")  # general-use

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
    """
    Source indication in requests.

    Some requests from Clients include type of the Client, for example the
    _NET_ACTIVE_WINDOW message.  Currently, the types can be 1 for normal applications,
    and 2 for pagers and other Clients that represent direct user actions (the Window
    Manager may decide to treat requests from applications differently than requests
    that are result of direct user actions).  Clients that support only older version
    of this spec will have 0 as their source indication, thus not specifying their
    source at all.  This also may mean that some fields in the message comply only
    with the older specification version.

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


class Orientation(enum.IntEnum):
    """Orientation cardinal used in _NET_DESKTOP_LAYOUT"""

    HORZ = 0
    VERT = 1


class Corner(enum.IntEnum):
    """Starting corner of virtual desktops' layout, used in _NET_DESKTOP_LAYOUT"""

    TOPLEFT = 0
    TOPRIGHT = 1
    BOTTOMRIGHT = 2
    BOTTOMLEFT = 3


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
        return f"<{self.__class__.__name__}({super().__repr__()}) {self.name!r}>"

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
        """
        Window title.

        If set, the Window Manager should use this in preference to WM_NAME
        """
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

    # -------------------------------------------------------------------------
    # Utility methods
    @staticmethod
    def _chunked(data: t.Sequence[_T], chunk_size: int) -> t.Iterator[t.Tuple[_T, ...]]:
        # Credit given where credit is due: https://stackoverflow.com/a/312464/624066
        return (tuple(data[i : i + chunk_size]) for i in range(0, len(data), chunk_size))

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
        """
        Indicate which hints the Window Manager supports.

        This property MUST be set by the Window Manager.

        For example: considering _NET_WM_STATE both this atom and all supported
        states e.g. _NET_WM_STATE_MODAL, _NET_WM_STATE_STICKY, would be listed.
        This assumes that backwards incompatible changes will not be made to
        the hints (without being renamed).
        """
        return list(self.get_property("_NET_SUPPORTED", Xlib.Xatom.ATOM).value)

    def get_client_list(self, _suffix: str = "") -> t.List[Window]:
        """
        List that contains all X Windows managed by the Window Manager,
        by initial mapping order, starting with the oldest window.

        This property SHOULD be set and updated by the Window Manager.
        """
        prop = self.get_property("_NET_CLIENT_LIST" + _suffix, Xlib.Xatom.WINDOW)
        return [Window(window_id=w, root=self) for w in prop.value]

    def get_client_list_stacking(self) -> t.List[Window]:
        """
        List that contains all X Windows managed by the Window Manager,
        in bottom-to-top stacking order.

        This property SHOULD be set and updated by the Window Manager.
        """
        return self.get_client_list(_suffix="_STACKING")

    def get_number_of_desktops(self) -> int:
        """
        Indicate the number of virtual desktops.

        This property SHOULD be set and updated by the Window Manager.
        """
        # In Unity, this is 1 even with 4 Workspaces enabled, possibly a bug
        return self.get_property("_NET_NUMBER_OF_DESKTOPS", Xlib.Xatom.CARDINAL).value[0]

    def set_number_of_desktops(self, new_number_of_desktops: int) -> None:
        """
        Request a change in the number of desktops.

        The Window Manager is free to honor or reject this request. If the request
        is honored _NET_NUMBER_OF_DESKTOPS MUST be set to the new number of desktops,
        _NET_VIRTUAL_ROOTS MUST be set to store the new number of desktop virtual
        root window IDs and _NET_DESKTOP_VIEWPORT and _NET_WORKAREA must also be
        changed accordingly.  The _NET_DESKTOP_NAMES property MAY remain unchanged.

        If the number of desktops is shrinking and _NET_CURRENT_DESKTOP is out of
        the new range of available desktops, then this MUST be set to the last
        available desktop from the new set. Clients that are still present on
        desktops that are out of the new range MUST be moved to the very last
        desktop from the new set. For these _NET_WM_DESKTOP MUST be updated.
        """
        self.send_message("_NET_NUMBER_OF_DESKTOPS", new_number_of_desktops)

    def get_desktop_geometry(self) -> t.Tuple[int, int]:
        """
        Tuple of two cardinals that defines the common size of all desktops.

        (this is equal to the screen size if the Window Manager doesn't support
        large desktops, otherwise it's equal to the virtual size of the desktop)

        This property SHOULD be set by the Window Manager.
        """
        # In Unity, this is the combined area of all workspaces, if enabled.
        # With 4 Workspaces in a 2x2 arrangement, it returns (3840, 2400)
        prop = self.get_property("_NET_DESKTOP_GEOMETRY", Xlib.Xatom.CARDINAL)
        return prop.value[0], prop.value[1]  # mypy dislikes tuple(prop.value[:2])

    def set_desktop_geometry(self, new_width: int, new_height: int) -> None:
        """
        Request a change in the desktop geometry.

        The Window Manager MAY choose to ignore this message, in which case
        _NET_DESKTOP_GEOMETRY property will remain unchanged.
        """
        self.send_message("_NET_DESKTOP_GEOMETRY", new_width, new_height)

    def get_desktop_viewport(self) -> t.List[t.Tuple[int, int]]:
        """
        List of pairs of cardinals that define the top left corner of each
        desktop's viewport.

        For Window Managers that don't support large desktops, this MUST always
        be set to (0,0), returned as [(0, 0)]
        """
        # Unity returns [(0, 0)] even with 4 2x2 Workspaces enabled, possibly a bug.
        prop = self.get_property("_NET_DESKTOP_VIEWPORT", Xlib.Xatom.CARDINAL)
        return list(self._chunked(prop.value, 2))  # type: ignore

    def set_desktop_viewport(self, new_vx: int, new_vy: int) -> None:
        """
        Request to change the viewport for the current desktop.

        The Window Manager MAY choose to ignore this message, in which case
        _NET_DESKTOP_VIEWPORT property will remain unchanged.
        """
        self.send_message("_NET_DESKTOP_VIEWPORT", new_vx, new_vy)

    def get_current_desktop(self) -> int:
        """
        The index of the current desktop.

        This is always an integer between 0 and _NET_NUMBER_OF_DESKTOPS - 1.
        This MUST be set and updated by the Window Manager.
        """
        return self.get_property("_NET_CURRENT_DESKTOP", Xlib.Xatom.CARDINAL).value[0]

    def set_current_desktop(
        self, new_index: int, timestamp: int = Xlib.X.CurrentTime
    ) -> None:
        """
        Request to switch to another virtual desktop.

        Note that the timestamp may be 0 for clients using an older version of
        this spec, in which case the timestamp field should be ignored.
        """
        # TODO: Use int(time.time()) timestamp as default if None
        #  here and possibly also in active_window()
        self.send_message("_NET_CURRENT_DESKTOP", new_index, timestamp)

    def get_desktop_names(self) -> t.List[str]:
        """
        The names of all virtual desktops as a list of strings.

        Note: The number of names could be different from _NET_NUMBER_OF_DESKTOPS.
        If it is less than _NET_NUMBER_OF_DESKTOPS, then the desktops with high
        numbers are unnamed. If it is larger than _NET_NUMBER_OF_DESKTOPS, then
        the excess names outside the _NET_NUMBER_OF_DESKTOPS are considered to
        be reserved in case the number of desktops is increased.

        Rationale: The name is not a necessary attribute of a virtual desktop.
        Thus, the availability or unavailability of names has no impact on virtual
        desktop functionality. Since names are set by users and users are likely
        to preset names for a fixed number of desktops, it doesn't make sense to
        shrink or grow this list when the number of available desktops changes.
        """
        text = self.get_text_property("_NET_DESKTOP_NAMES", self.UTF8_STRING)
        return text[:-1].split("\0")

    def set_desktop_names(self, desktop_names: t.Iterable[str]) -> None:
        """
        Set the names of all virtual desktops.

        See Note and Rationale in `get_desktop_names()`
        """
        text = "\0".join(desktop_names) + "\0"
        self.set_text_property("_NET_DESKTOP_NAMES", text)

    def get_active_window(self) -> Window:
        """
        The currently active window or None if no window has the focus.
        """
        # TODO: handle None and change return type to Optional, per the spec
        prop = self.get_property("_NET_ACTIVE_WINDOW", Xlib.Xatom.WINDOW)
        return Window(window_id=prop.value[0], root=self)

    def set_active_window(
        self,
        window_to_activate: Window,
        source_indication: Source = Source.USER,
        timestamp: int = Xlib.X.CurrentTime,
        requestor_window: t.Optional[Window] = None,
    ) -> None:
        """
        Request to activate another window.

        `source_indication` should be 1 when the request comes from an application,
        and 2 when it comes from a pager.  Clients using older version of this spec
        use 0 as source indication, see `Source` enum for details.

        `timestamp` is Client's last user activity timestamp (see _NET_WM_USER_TIME)
        at the time of the request.

        `requestor_window` is the Client's currently active toplevel window, if any.
         (the Window Manager may be e.g. more likely to obey the request if it will
         mean transferring focus from one active window to another).

        Depending on the information provided with the message, the Window Manager
        may decide to refuse the request (either completely ignore it, or e.g. use
        _NET_WM_STATE_DEMANDS_ATTENTION).
        """
        self.send_message(
            "_NET_ACTIVE_WINDOW",
            source_indication,
            timestamp,
            Xlib.X.NONE if requestor_window is None else requestor_window.id,
            window_id=window_to_activate.id,
        )

    def get_workarea(self) -> t.List[t.Tuple[int, int, int, int]]:
        """
        List of (x, y, width, height) geometry tuples representing the work area
        for each desktop.

        These geometries are specified relative to the viewport on each desktop
        and specify an area that is completely contained within the viewport.
        Work area SHOULD be used by desktop applications to place desktop icons
        appropriately.

        The Window Manager SHOULD calculate this space by taking the current page
        minus space occupied by dock and panel windows, as indicated by the
        _NET_WM_STRUT or _NET_WM_STRUT_PARTIAL properties set on client windows.
        """
        prop = self.get_property("_NET_WORKAREA", Xlib.Xatom.CARDINAL)
        return list(self._chunked(prop.value, 4))  # type: ignore

    # No set_workarea(), read-only per EWMH

    def get_supporting_wm_check(self) -> Window:
        """
        Child window created by the WM to indicate that a compliant WM is active.

        The Window Manager MUST set this property on the root window. The child
        window MUST also have the _NET_SUPPORTING_WM_CHECK property set to the
        ID of the child window. The child window MUST also have the _NET_WM_NAME
        property set to the name of the Window Manager.

        Rationale: The child window is used to distinguish an active Window Manager
        from a stale _NET_SUPPORTING_WM_CHECK property that happens to point to
        another window. If the _NET_SUPPORTING_WM_CHECK window on the client window
        is missing or not properly set, clients SHOULD assume that no conforming
        Window Manager is present.
        """
        # Corollary: for the name of the WM itself, use the recipe:
        # root.get_supporting_wm_check().get_wm_name() -> "Compiz"

        # Checking active and compliant WM is trickier: Root Windows's
        # _NET_SUPPORTING_WM_CHECK might not exist (no WM or not compliant),
        # it might point to a non-existing window, the child might not have
        # _NET_SUPPORTING_WM_CHECK, or it may not point to itself (inactive).
        # Also, child windows do not have the get_supporting_wm_check() method,
        # so must use the lower-level get_property() directly.
        prop = self.get_property("_NET_SUPPORTING_WM_CHECK", Xlib.Xatom.WINDOW)
        return Window(prop.value[0], root=self)

    # No set_supporting_wm_check(), read-only per EWMH

    def get_virtual_roots(self) -> t.List[Window]:
        """
        List of Windows acting as virtual root windows for WM's virtual desktops.

        To implement virtual desktops, some Window Managers re-parent client
        windows to a child of the root window. Window Managers using this technique
        MUST set this property to a list of IDs for windows that are acting as
        virtual root windows. This property allows background setting programs to
        work with virtual roots and allows clients to figure out the window manager
        frame windows of their windows.
        """
        prop = self.get_property("_NET_VIRTUAL_ROOTS", Xlib.Xatom.WINDOW)
        return [Window(window_id=w, root=self) for w in prop.value]

    # No set_virtual_roots(), read-only per EWMH

    def get_desktop_layout(self) -> t.Tuple[int, int, int, int]:
        """
        Describes the layout of virtual desktops relative to each other.

        This property is set by a Pager, not by the Window Manager. When setting this
        property, the Pager must own a manager selection (as defined in the ICCCM 2.8).
        The manager selection is called _NET_DESKTOP_LAYOUT_Sn where n is the screen
        number. The purpose of this property is to allow the Window Manager to know the
        desktop layout displayed by the Pager.

        More specifically, it describes the layout used by the owner of the manager
        selection. The Window Manager may use this layout information or may choose to
        ignore it. The property contains four values: the Pager orientation, the number
        of desktops in the X direction, the number in the Y direction, and the starting
        corner of the layout, i.e. the corner containing the first desktop.

        Note: In order to interoperate with Pagers implementing an earlier draft of this
        document, Window Managers should accept a _NET_DESKTOP_LAYOUT property of length
        3 and use _NET_WM_TOPLEFT as the starting corner in this case.

        The virtual desktops are arranged in a rectangle with `rows` rows and `columns`
        columns. If rows times columns does not match the total number of desktops as
        specified by _NET_NUMBER_OF_DESKTOPS, the highest-numbered workspaces are assumed
        to be nonexistent. Either rows or columns (but not both) may be specified as 0
        in which case its actual value will be derived from _NET_NUMBER_OF_DESKTOPS.

        When the orientation is _NET_WM_ORIENTATION_HORZ the desktops are laid out in
        rows, with the first desktop in the specified starting corner. So a layout with
        four columns and three rows starting in the _NET_WM_TOPLEFT corner looks like
        this:
         +--+--+--+--+
         | 0| 1| 2| 3|
         +--+--+--+--+
         | 4| 5| 6| 7|
         +--+--+--+--+
         | 8| 9|10|11|
         +--+--+--+--+

        With starting_corner _NET_WM_BOTTOMRIGHT, it looks like this:
         +--+--+--+--+
         |11|10| 9| 8|
         +--+--+--+--+
         | 7| 6| 5| 4|
         +--+--+--+--+
         | 3| 2| 1| 0|
         +--+--+--+--+

        When the orientation is _NET_WM_ORIENTATION_VERT the layout with four columns
        and three rows starting in the _NET_WM_TOPLEFT corner looks like:
         +--+--+--+--+
         | 0| 3| 6| 9|
         +--+--+--+--+
         | 1| 4| 7|10|
         +--+--+--+--+
         | 2| 5| 8|11|
         +--+--+--+--+

        With starting_corner _NET_WM_TOPRIGHT, it looks like:
         +--+--+--+--+
         | 9| 6| 3| 0|
         +--+--+--+--+
         |10| 7| 4| 1|
         +--+--+--+--+
         |11| 8| 5| 2|
         +--+--+--+--+

        The numbers here are the desktop numbers, as for _NET_CURRENT_DESKTOP.
        """
        prop = self.get_property("_NET_DESKTOP_LAYOUT", Xlib.Xatom.CARDINAL)
        return list(self._chunked(prop.value, 4))  # type: ignore

    def set_desktop_layout(
        self, orientation: Orientation, columns: int, rows: int, starting_corner: Corner
    ) -> None:
        self.set_property(
            "_NET_DESKTOP_LAYOUT",
            (orientation, columns, rows, starting_corner),
            Xlib.Xatom.CARDINAL,
        )

    def get_showing_desktop(self) -> bool:
        """
        If the Window Manager is in "showing the desktop" mode.

        Some Window Managers have a "showing the desktop" mode in which windows are hidden,
        and the desktop background is displayed and focused. If a Window Manager supports
        the _NET_SHOWING_DESKTOP hint, it MUST set it to a value of 1 when the Window Manager
        is in "showing the desktop" mode, and a value of zero if the Window Manager is not
        in this mode.
        """
        # Unity bug: always report True. Toggling mode with set_showing_desktop() works fine
        return bool(self.get_property("_NET_SHOWING_DESKTOP", Xlib.Xatom.CARDINAL).value[0])

    def set_showing_desktop(self, showing_desktop_mode: bool) -> None:
        """
        Request to enter or leave the "showing the desktop" mode.

        The Window Manager may choose to ignore this.
        """
        self.send_message("_NET_SHOWING_DESKTOP", showing_desktop_mode)

    # -------------------------------------------------------------------------
    # Other Root Window Messages
    def close_window(
        self,
        window_to_close: Window,
        timestamp: int = Xlib.X.CurrentTime,
        source_indication: Source = Source.USER,
    ) -> None:
        """Request the WM to close a Window"""
        # source_indication and timestamp swap position compared to active_window!
        self.send_message(
            "_NET_CLOSE_WINDOW",
            timestamp,
            source_indication,
            window_id=window_to_close.id,
        )

    # def get_moveresize_window()
    #     self.send_message("_NET_MOVERESIZE_WINDOW",

    #     _net_wm_moveresize
    #     _net_restack_window
    #     _net_request_frame_extents
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
