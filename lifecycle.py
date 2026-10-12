"""Windows handles scoped to this project and login session."""
import ctypes
from ctypes import wintypes as w
import hashlib
from pathlib import Path

k = ctypes.WinDLL("kernel32", use_last_error=True)
for name, args in (("CreateMutexW", [w.LPVOID, w.BOOL, w.LPCWSTR]),
                   ("CreateEventW", [w.LPVOID, w.BOOL, w.BOOL, w.LPCWSTR]),
                   ("OpenEventW", [w.DWORD, w.BOOL, w.LPCWSTR])):
    getattr(k, name).argtypes = args
    getattr(k, name).restype = w.HANDLE
k.SetEvent.argtypes = [w.HANDLE]
k.SetEvent.restype = w.BOOL
k.ResetEvent.argtypes = [w.HANDLE]
k.ResetEvent.restype = w.BOOL
k.CloseHandle.argtypes = [w.HANDLE]
k.CloseHandle.restype = w.BOOL
k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
k.WaitForSingleObject.restype = w.DWORD
NAME = "Local\\VLCGesture_" + hashlib.sha256(str(Path(__file__).resolve().parent).casefold().encode()).hexdigest()[:24]


class Instance:
    def __init__(self):
        self.mutex = self.event = self.done = None

    def acquire(self):
        ctypes.set_last_error(0)
        self.mutex = k.CreateMutexW(None, False, NAME)
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            self.close()
            return False
        self.done = k.CreateEventW(None, True, False, NAME + "_done")
        if self.done:
            self.event = k.CreateEventW(None, True, False, NAME + "_stop")
        if not self.done or not self.event:
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)
        # A finishing stop helper may briefly retain handles from the prior run.
        if not k.ResetEvent(self.done) or not k.ResetEvent(self.event):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)
        return True

    def stopping(self, seconds=0):
        result = k.WaitForSingleObject(self.event, max(0, int(seconds * 1000)))
        if result == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        return result == 0

    def close(self):
        for handle in (self.event, self.done, self.mutex):
            if handle:
                k.CloseHandle(handle)
        self.event = self.done = self.mutex = None

    def finished(self):
        if self.done and not k.SetEvent(self.done):
            raise ctypes.WinError(ctypes.get_last_error())


def request_stop():
    event = k.OpenEventW(2, False, NAME + "_stop")
    if not event:
        error = ctypes.get_last_error()
        if error == 2:
            print("No controller running in this Windows session.")
            return 0
        raise ctypes.WinError(error)
    done = None
    try:
        done = k.OpenEventW(0x00100000, False, NAME + "_done")
        if not done:
            raise ctypes.WinError(ctypes.get_last_error())
        if not k.SetEvent(event):
            raise ctypes.WinError(ctypes.get_last_error())
        print("Shutdown requested; waiting for resource cleanup...")
        result = k.WaitForSingleObject(done, 10000)
        if result == 0:
            print("Controller cleanup completed and logs flushed.")
            return 0
        if result == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        print("Shutdown is still pending; a camera/model call may be blocked. No process was forcibly terminated.")
        return 1
    finally:
        if done:
            k.CloseHandle(done)
        k.CloseHandle(event)
