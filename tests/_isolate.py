"""Imported by every test module: keeps settings, history and cache out of the real user config dir."""
import os
import tempfile

if "CNTAG_CONFIG_DIR" not in os.environ:
    os.environ["CNTAG_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cntag-tests-")
