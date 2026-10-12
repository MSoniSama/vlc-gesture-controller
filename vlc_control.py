"""Foreground-guarded keyboard injection and targeted volume wheel messages."""
import ctypes
from ctypes import wintypes as w
import logging
import ntpath
import config as c

log = logging.getLogger(__name__)
user = ctypes.WinDLL("user32", use_last_error=True)
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
user.GetForegroundWindow.argtypes = []
user.GetForegroundWindow.restype = w.HWND
user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
user.GetWindowThreadProcessId.restype = w.DWORD
kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel.OpenProcess.restype = w.HANDLE
kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
kernel.QueryFullProcessImageNameW.restype = w.BOOL
kernel.CloseHandle.argtypes = [w.HANDLE]
kernel.CloseHandle.restype = w.BOOL
user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user.PostMessageW.restype = w.BOOL
user.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
user.GetWindowRect.restype = w.BOOL
user.MapVirtualKeyW.argtypes = [w.UINT, w.UINT]
user.MapVirtualKeyW.restype = w.UINT
user.GetAsyncKeyState.argtypes = [ctypes.c_int]
user.GetAsyncKeyState.restype = ctypes.c_short


class KeyboardInput(ctypes.Structure):
    _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("extra", ctypes.c_size_t)]


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("data", w.DWORD),
                ("flags", w.DWORD), ("time", w.DWORD), ("extra", ctypes.c_size_t)]


class HardwareInput(ctypes.Structure):
    _fields_ = [("message", w.DWORD), ("low", w.WORD), ("high", w.WORD)]


class InputUnion(ctypes.Union):
    _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput), ("hardware", HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("data", InputUnion)]


user.SendInput.argtypes = [w.UINT, ctypes.POINTER(Input), ctypes.c_int]
user.SendInput.restype = w.UINT


def key_event(key, up=False):
    # Virtual-key mode honors N/P in the active keyboard layout; arrows are extended.
    flags = (2 if up else 0) | (1 if key in (0x25, 0x26, 0x27, 0x28) else 0)
    return Input(1, InputUnion(keyboard=KeyboardInput(key, user.MapVirtualKeyW(key, 0), flags, 0, 0)))


def keyboard(hwnd, key, shift, description):
    # Don't modify keys the user is currently holding, or combine with their modifiers.
    if any(user.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, key)):
        log.info("Keyboard %s suppressed: user key/modifier already held", description)
        return False
    sequence = ([key_event(0xA0)] if shift else []) + [key_event(key), key_event(key, True)] + ([key_event(0xA0, True)] if shift else [])
    events = (Input * len(sequence))(*sequence)
    if foreground_vlc() != hwnd:
        log.info("Keyboard %s suppressed: VLC lost foreground", description)
        return False
    ctypes.set_last_error(0)
    accepted = user.SendInput(len(events), events, ctypes.sizeof(Input))
    error = ctypes.get_last_error()
    log.info("Keyboard %s: Windows accepted %s/%s input events (VLC action unconfirmed)", description, accepted, len(events))
    if accepted != len(events):
        # Release only keydowns in the accepted prefix which lack an accepted keyup.
        pressed = []
        for event in sequence[:accepted]:
            item = event.data.keyboard
            if item.flags & 2:
                if item.vk in pressed:
                    pressed.remove(item.vk)
            else:
                pressed.append(item.vk)
        if pressed:
            releases = (Input * len(pressed))(*(key_event(vk, True) for vk in reversed(pressed)))
            released = user.SendInput(len(releases), releases, ctypes.sizeof(Input))
            if released != len(releases):
                log.error("Keyboard modifier cleanup incomplete: %s/%s keyups accepted", released, len(releases))
        log.error("Keyboard dispatch failed for %s; Win32 error=%s (check privilege level/UIPI)", description, error)
        raise RuntimeError(f"SendInput failed for {description}: {accepted}/{len(events)} events")
    return True


def foreground_vlc():
    hwnd = user.GetForegroundWindow()
    if not hwnd:
        return None
    pid = w.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = kernel.OpenProcess(0x1000, False, pid.value)
    if not process:
        return None
    try:
        path, size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
            return None
        return hwnd if ntpath.basename(path.value).lower() == "vlc.exe" else None
    finally:
        kernel.CloseHandle(process)


def post(hwnd, message, wp, lp):
    # Even if focus changes after this check, messages still target this HWND.
    if foreground_vlc() != hwnd:
        log.info("Command suppressed: VLC lost foreground")
        return False
    if not user.PostMessageW(hwnd, message, wp, lp):
        raise ctypes.WinError(ctypes.get_last_error())
    return True


def execute(hwnd, action):
    seek_shift = action.startswith("seek") and c.SEEK_MODE == "shift_arrows"
    volume_wheel = action.startswith("volume") and c.VOLUME_MODE == "wheel"
    if volume_wheel:
        rect = w.RECT()
        if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        x, y = (rect.left + rect.right)//2, (rect.top + rect.bottom)//2
        sign = 1 if action == "volume_up" else -1
        delta = c.WHEEL_DELTA * sign
        wp = (delta & 0xffff) << 16
        ok = post(hwnd, 0x020A, wp, (x & 0xffff) | ((y & 0xffff) << 16))
    else:
        navigation = {"chapter_next": (0x4E, True, "Shift+N / next chapter"),
                      "chapter_previous": (0x50, True, "Shift+P / previous chapter"),
                      "video_next": (0x4E, False, "N / next video"),
                      "video_previous": (0x50, False, "P / previous video")}
        if action in navigation:
            key, shift, description = navigation[action]
        elif seek_shift:
            key, shift = (0x27 if action == "seek_right" else 0x25), True
            description = "Shift+Right" if action == "seek_right" else "Shift+Left"
        else:
            key, shift, description = c.KEYS[action], False, f"{action} (VK {c.KEYS[action]:#x})"
        return keyboard(hwnd, key, shift, description)
    if ok:
        log.info("%s: wheel message queued to VLC (action unconfirmed)", action)
    return ok
