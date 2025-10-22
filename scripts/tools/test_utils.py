import io
import os
import sys


def fix_windows_unicode():
    """Fix Unicode output issues on Windows consoles."""
    if sys.platform != "win32":
        return

    # Skip adjustments when pytest is managing the streams to avoid teardown issues
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return

    # Switch console code page to UTF-8 when possible
    try:
        os.system("chcp 65001 > nul")
    except Exception:
        pass

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        buffer = getattr(stream, "buffer", None)
        if buffer is None:
            continue
        try:
            wrapped = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")
            setattr(sys, stream_name, wrapped)
        except Exception:
            continue

    try:
        import msvcrt

        for fileno in (sys.stdout.fileno(), sys.stderr.fileno()):
            try:
                msvcrt.setmode(fileno, os.O_BINARY)
            except Exception:
                continue
    except Exception:
        pass
