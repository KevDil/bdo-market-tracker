from pathlib import Path


def pytest_ignore_collect(path, config):
    parts = Path(str(path)).parts
    if "scripts" in parts:
        if "archive" in parts or "archived" in parts:
            return True
    return False
