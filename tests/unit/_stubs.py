"""Utility helpers to install lightweight test doubles for native deps."""
from __future__ import annotations

import sys
import types


def install_dependency_stubs() -> None:
    modules: dict[str, types.ModuleType] = {}

    for name in ("cv2", "mss", "numpy"):
        modules[name] = modules.get(name, types.ModuleType(name))

    if "pytesseract" not in sys.modules:
        pytesseract_stub = types.ModuleType("pytesseract")
        pytesseract_stub.pytesseract = types.SimpleNamespace()
        modules["pytesseract"] = pytesseract_stub

    if "easyocr" not in sys.modules:
        class _DummyReader:
            def __init__(self, *args, **kwargs) -> None:
                pass

        easyocr_stub = types.ModuleType("easyocr")
        easyocr_stub.Reader = _DummyReader
        modules["easyocr"] = easyocr_stub

    if "rapidfuzz" not in sys.modules:
        def _dummy_extract(query, choices, scorer=None, limit=1):
            matches = []
            for choice in choices:
                score = 100 if choice == query else 50
                matches.append((choice, score, None))
            if limit is not None:
                matches = matches[:limit]
            return matches

        rapidfuzz_process = types.SimpleNamespace(extract=_dummy_extract)
        rapidfuzz_fuzz = types.SimpleNamespace(WRatio=lambda *_args, **_kwargs: 100)
        rapidfuzz_stub = types.ModuleType("rapidfuzz")
        rapidfuzz_stub.process = rapidfuzz_process
        rapidfuzz_stub.fuzz = rapidfuzz_fuzz
        modules["rapidfuzz"] = rapidfuzz_stub
        modules["rapidfuzz.process"] = rapidfuzz_process
        modules["rapidfuzz.fuzz"] = rapidfuzz_fuzz

    if "PIL" not in sys.modules:
        pil_stub = types.ModuleType("PIL")
        pil_image_stub = types.ModuleType("PIL.Image")
        pil_stub.Image = pil_image_stub
        modules["PIL"] = pil_stub
        modules["PIL.Image"] = pil_image_stub

    for name, module in modules.items():
        if name not in sys.modules:
            sys.modules[name] = module
