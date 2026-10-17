"""List visible top-level window titles and sizes, to find an app's exact window name."""
import ctypes
from ctypes import wintypes

u = ctypes.windll.user32
out = []


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def visit(h, _):
    if u.IsWindowVisible(h):
        n = u.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            r = wintypes.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            w, ht = r.right - r.left, r.bottom - r.top
            if w > 150 and ht > 150:
                out.append((b.value, w, ht, h))
    return True


u.EnumWindows(visit, 0)
for title, w, ht, h in out:
    print(f"{w}x{ht}  hwnd={h}  {title!r}")
