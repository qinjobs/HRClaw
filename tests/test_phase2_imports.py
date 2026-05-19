from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening.phase2_imports import PaddleOCRBackend


class PaddleOCRBackendTests(unittest.TestCase):
    def test_extract_text_retries_with_compat_mode_on_pir_runtime_error(self):
        calls: list[dict[str, object]] = []

        class _FakePaddleOCR:
            def __init__(self, **kwargs):
                calls.append(dict(kwargs))
                self._call_index = len(calls)

            def predict(self, *, input):
                _ = input
                if self._call_index == 1:
                    raise RuntimeError(
                        "(Unimplemented) ConvertPirAttribute2RuntimeAttribute not support "
                        "[pir::ArrayAttribute<pir::DoubleAttribute>] "
                        "(at ..\\paddle\\fluid\\framework\\new_executor\\instruction\\onednn\\onednn_instruction.cc:118)"
                    )
                return [{"rec_text": ["李四", "4年测试经验"]}]

        fake_module = type("FakePaddleModule", (), {"PaddleOCR": _FakePaddleOCR})()
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "scanned.pdf"
            file_path.write_bytes(b"%PDF-1.4 fake scanned pdf")
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("src.screening.phase2_imports.importlib.import_module", return_value=fake_module):
                    backend = PaddleOCRBackend()
                    text = backend.extract_text(file_path)

        self.assertIn("李四", text)
        self.assertEqual(len(calls), 2)
        second_kwargs = calls[1]
        self.assertEqual(second_kwargs.get("ocr_version"), "PP-OCRv4")
        self.assertEqual(second_kwargs.get("text_detection_model_name"), "PP-OCRv4_mobile_det")
        self.assertEqual(second_kwargs.get("text_recognition_model_name"), "PP-OCRv4_mobile_rec")
        self.assertEqual(second_kwargs.get("enable_mkldnn"), False)

    def test_load_module_sets_windows_runtime_compat_flags(self):
        fake_module = object()
        flags: tuple[str | None, str | None, str | None]
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("src.screening.phase2_imports.os.name", "nt"):
                with mock.patch("src.screening.phase2_imports.importlib.import_module", return_value=fake_module):
                    backend = PaddleOCRBackend()
                    loaded = backend._load_module()
                    flags = (
                        os.getenv("FLAGS_use_mkldnn"),
                        os.getenv("FLAGS_use_onednn"),
                        os.getenv("FLAGS_enable_pir_api"),
                    )
        self.assertIs(loaded, fake_module)
        self.assertEqual(flags[0], "0")
        self.assertEqual(flags[1], "0")
        self.assertEqual(flags[2], "0")

    def test_apply_runtime_compat_flags_sets_project_cache_home_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            expected_cache = Path(tmpdir) / "ocr-cache"
            with mock.patch.dict(
                os.environ,
                {"SCREENING_RESUME_OCR_CACHE_DIR": str(expected_cache)},
                clear=True,
            ):
                backend = PaddleOCRBackend()
                backend._apply_runtime_compat_flags()
                self.assertEqual(os.getenv("PADDLE_PDX_CACHE_HOME"), str(expected_cache))
                self.assertTrue(expected_cache.exists())

    def test_apply_runtime_compat_flags_preserves_explicit_paddlex_cache_home(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            explicit_cache = Path(tmpdir) / "explicit-cache"
            explicit_cache.mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(
                os.environ,
                {"PADDLE_PDX_CACHE_HOME": str(explicit_cache)},
                clear=True,
            ):
                backend = PaddleOCRBackend()
                backend._apply_runtime_compat_flags()
                self.assertEqual(os.getenv("PADDLE_PDX_CACHE_HOME"), str(explicit_cache))


if __name__ == "__main__":
    unittest.main()
