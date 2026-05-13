import os
import sys


def set_music_folder_type(root_path: str) -> tuple[int, int]:
    """Apply FolderType=Music via desktop.ini to root_path and all subdirectories.

    Windows Explorer reads desktop.ini when the folder has the ReadOnly attribute
    and the desktop.ini file has Hidden+System attributes.
    Returns (processed_count, error_count).
    """
    if sys.platform != "win32":
        return 0, 0

    import ctypes
    _set = ctypes.windll.kernel32.SetFileAttributesW
    _get = ctypes.windll.kernel32.GetFileAttributesW
    INVALID = 0xFFFFFFFF
    H, S, R = 0x2, 0x4, 0x1

    ini_body = "[.ShellClassInfo]\r\n[ViewState]\r\nMode=\r\nVid=\r\nFolderType=Music\r\n"
    processed, errors = 0, 0

    for folder, _, _ in os.walk(root_path):
        try:
            ini = os.path.join(folder, "desktop.ini")
            # Strip H+S so the file is writable
            if os.path.exists(ini):
                cur = _get(ini)
                if cur != INVALID:
                    _set(ini, cur & ~H & ~S)
            with open(ini, "w", encoding="utf-8") as f:
                f.write(ini_body)
            _set(ini, H | S)
            cur = _get(folder)
            if cur != INVALID:
                _set(folder, cur | R)
            processed += 1
        except Exception:
            errors += 1

    return processed, errors
