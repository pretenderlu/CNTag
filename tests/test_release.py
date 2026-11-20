import _isolate  # noqa: F401
import re
import unittest
from pathlib import Path

from cntag import __version__

PROJECT = Path(__file__).resolve().parent.parent


class ReleaseConsistencyTests(unittest.TestCase):
    def test_readme_mentions_current_version(self):
        readme = (PROJECT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"当前版本：**v{__version__}**", readme)
        self.assertIn(f"CNTagSetup-v{__version__}.exe", readme)
        self.assertEqual(set(re.findall(r"CNTagSetup-v([\d.]+)\.exe", readme)), {__version__})

    def test_license_notices_are_present(self):
        self.assertTrue((PROJECT / "LICENSE").is_file())
        self.assertTrue((PROJECT / "THIRD_PARTY_NOTICES.md").is_file())
        self.assertTrue((PROJECT / "licenses" / "GPL-2.0.txt").is_file())


class ResourcePathTests(unittest.TestCase):
    def test_assets_resolve_from_source_checkout(self):
        from cntag.ui.common import _resource_path

        self.assertTrue(_resource_path("assets/icon.png").is_file())


if __name__ == "__main__":
    unittest.main()
