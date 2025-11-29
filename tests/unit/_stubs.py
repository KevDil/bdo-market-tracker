"""Utility helpers to install lightweight test doubles for native deps."""
from __future__ import annotations

import sys
import types


def install_dependency_stubs() -> None:
    modules: dict[str, types.ModuleType] = {}

    try:
        import numpy as real_numpy  # type: ignore
    except Exception:  # pragma: no cover - fallback stub
        real_numpy = None

    for name in ("cv2", "mss"):
        modules[name] = modules.get(name, types.ModuleType(name))

    if real_numpy is not None:
        modules["numpy"] = real_numpy
    else:
        modules["numpy"] = modules.get("numpy", types.ModuleType("numpy"))
        numpy_stub = modules["numpy"]
        numpy_stub._IS_STUB = True

        if not hasattr(numpy_stub, "uint8"):
            numpy_stub.uint8 = int

        if not hasattr(numpy_stub, "ndarray"):
            class _DummyArray(list):
                def __init__(self, data, shape, dtype):
                    super().__init__(data)
                    self.shape = shape
                    self.dtype = dtype

                def tobytes(self):
                    return bytes(int(x) & 0xFF for x in self)

                def copy(self):
                    return _DummyArray(list(self), self.shape, self.dtype)

            numpy_stub.ndarray = _DummyArray

        if not hasattr(numpy_stub, "array"):
            def _array(data, dtype=None):
                flat = list(data)
                shape = (len(flat),)
                return numpy_stub.ndarray(flat, shape, dtype or numpy_stub.uint8)

            numpy_stub.array = _array

        if not hasattr(numpy_stub, "zeros"):
            def _zeros(shape, dtype=None):
                if isinstance(shape, int):
                    total = shape
                    resolved_shape = (shape,)
                else:
                    total = 1
                    for dim in shape:
                        total *= dim
                    resolved_shape = tuple(shape)
                data = [0] * total
                return numpy_stub.ndarray(data, resolved_shape, dtype or numpy_stub.uint8)

            numpy_stub.zeros = _zeros

        if not hasattr(numpy_stub, "random"):
            class _RandomModule:
                @staticmethod
                def randint(low, high=None, size=None, dtype=None):
                    if high is None:
                        high = low
                        low = 0
                    if size is None:
                        size = 1
                    if isinstance(size, int):
                        resolved_shape = (size,)
                        total = size
                    else:
                        resolved_shape = tuple(size)
                        total = 1
                        for dim in resolved_shape:
                            total *= dim
                    span = max(high - low, 1)
                    data = [low + (idx % span) for idx in range(total)]
                    return numpy_stub.ndarray(data, resolved_shape, dtype or numpy_stub.uint8)

            numpy_stub.random = _RandomModule()

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
