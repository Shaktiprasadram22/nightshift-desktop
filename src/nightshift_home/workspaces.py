"""Use the window manager's standard X11 workspace API; never move user windows."""
import ctypes as C

NAMES = ('Coding', 'Research', 'Personal')


def switch_workspace(index):
    if index not in range(len(NAMES)):
        raise ValueError('Unknown workspace.')
    _send(b'_NET_CURRENT_DESKTOP',index)


def show_desktop(visible):
    _send(b'_NET_SHOWING_DESKTOP',int(visible))


def _send(atom,value):
    x = C.CDLL('libX11.so.6')
    x.XOpenDisplay.argtypes = [C.c_char_p]
    x.XOpenDisplay.restype = C.c_void_p
    x.XDefaultRootWindow.argtypes = [C.c_void_p]
    x.XDefaultRootWindow.restype = C.c_ulong
    x.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
    x.XInternAtom.restype = C.c_ulong
    x.XSendEvent.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.c_void_p]
    x.XFlush.argtypes = [C.c_void_p]
    x.XCloseDisplay.argtypes = [C.c_void_p]

    class Data(C.Union):
        _fields_ = [('b', C.c_char * 20), ('s', C.c_short * 10), ('l', C.c_long * 5)]

    class Message(C.Structure):
        _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int),
                    ('display', C.c_void_p), ('window', C.c_ulong), ('message_type', C.c_ulong),
                    ('format', C.c_int), ('data', Data)]

    class Event(C.Union):
        _fields_ = [('message', Message), ('pad', C.c_long * 24)]

    display = x.XOpenDisplay(None)
    if not display:
        raise RuntimeError('The desktop display is unavailable.')
    try:
        root = x.XDefaultRootWindow(display)
        event = Event()
        event.message = Message(33, 0, 1, display, root,
                                x.XInternAtom(display, atom, 0), 32, Data())
        event.message.data.l[0] = value
        event.message.data.l[1] = 0
        if not x.XSendEvent(display, root, False, (1 << 20) | (1 << 19), C.byref(event)):
            raise RuntimeError('The workspace could not be selected.')
        x.XFlush(display)
    finally:
        x.XCloseDisplay(display)
