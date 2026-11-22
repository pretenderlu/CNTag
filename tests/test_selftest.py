import _isolate  # noqa: F401
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cntag import selftest


class SelfTestTests(unittest.TestCase):
    def test_all_checks_pass_from_source(self):
        self.assertEqual([(name, error) for name, error in selftest.run() if error], [])

    def test_missing_bundled_data_is_reported(self):
        def missing(*_args):
            raise FileNotFoundError(2, "No such file or directory", "zhcdict.json")

        with tempfile.TemporaryDirectory() as folder, patch("cntag.textutil._zh_convert", side_effect=missing),                 contextlib.redirect_stdout(io.StringIO()):
            report = Path(folder) / "report.txt"
            code = selftest.main(["--self-test", str(report)])
            text = report.read_text(encoding="utf-8")
        self.assertEqual(code, 1)
        self.assertIn("FAIL zhconv: FileNotFoundError", text)
        self.assertIn("zhcdict.json", text)
        self.assertIn("OK   pypinyin", text)

    def test_passing_run_exits_with_zero(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(selftest.main(["--self-test"]), 0)
        self.assertNotIn("FAIL", output.getvalue())


if __name__ == "__main__":
    unittest.main()
