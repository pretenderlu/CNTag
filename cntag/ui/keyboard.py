"""Global keyboard shortcuts."""
from __future__ import annotations

import sys


class KeyboardMixin:
    def _bind_shortcuts(self) -> None:
        modifier = "Command" if sys.platform == "darwin" else "Control"
        self.root.bind(f"<{modifier}-o>", lambda _e: self._choose_folder())
        self.root.bind(f"<{modifier}-Return>", lambda _e: self._apply())
        self.root.bind("<F5>", lambda _e: self._start_scan())
