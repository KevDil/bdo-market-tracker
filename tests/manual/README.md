# Manual / Heavyweight Tests

The files in this directory exercise end-to-end scenarios that require
native dependencies (EasyOCR, OpenCV, CUDA), real database snapshots, or
network access. They are **not** part of the automated regression suite.

Run them only when the full Windows capture environment is available.
Each script documents its original regression scenario and expected output.
