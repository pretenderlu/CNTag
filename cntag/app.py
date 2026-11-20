"""CNTag main window: startup, threading helpers, settings and shutdown."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox

from . import i18n
from .i18n import tr
from .settings import load_settings
from .ui.common import BACKGROUND, LATEST_RELEASE_URL, _settings_path
from .ui.layout import LayoutMixin
from .ui.theme import ThemeMixin
from .ui.updates import UpdateMixin
from .windowing import apply_native_window_style, configure_native_window


class CNTagApp(ThemeMixin, LayoutMixin, UpdateMixin):
    def __init__(self):
        self.ui_font = "SF Pro Text" if sys.platform == "darwin" else "Segoe UI"
        self.ui_semibold = "SF Pro Display" if sys.platform == "darwin" else "Segoe UI Semibold"
        self.cjk_font = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"
        self._enable_dpi_awareness()
        self.root = tk.Tk()
        try:
            self.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.root.title(tr("CNTag — 中文音乐标签还原工具"))
        self.ui_scale = 1.0
        if sys.platform == "win32":
            pixels_per_inch = self.root.winfo_fpixels("1i")
            self.ui_scale = max(1.0, pixels_per_inch / 96)
            self.root.tk.call("tk", "scaling", pixels_per_inch / 72)
        self._configure_window()
        configure_native_window(self.root, "#1D1C31")
        self.root.configure(bg=BACKGROUND)
        self.settings = self._load_settings()
        self.language_setting = self.settings.get("language", "auto")
        self.icon_image = None
        self.latest_release_url = LATEST_RELEASE_URL
        self.latest_update = None
        self.updating = False
        self.update_dialog = None
        self._ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self.library_var = tk.StringVar(value=tr("尚未选择音乐库文件夹"))
        self.status_var = tk.StringVar(value=tr("就绪"))
        self._configure_styles()
        self._load_icon()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(50, self._drain_ui_queue)
        self.root.after(300, self._check_for_updates)
        self._reveal()

    def _reveal(self) -> None:
        self.root.update()
        try:
            apply_native_window_style(self.root, "#1D1C31")
        except (OSError, AttributeError):
            pass
        self.root.update_idletasks()
        try:
            self.root.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

    @staticmethod
    def _enable_dpi_awareness() -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes

            if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                raise OSError("Unable to enable per-monitor DPI awareness")
        except (AttributeError, OSError):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass

    def _configure_window(self) -> None:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        minimum_width = min(self._px(1179), int(screen_width * 0.96))
        minimum_height = min(self._px(880), int(screen_height * 0.94))
        width = max(minimum_width, min(self._px(1440), int(screen_width * 0.92)))
        height = max(minimum_height, min(self._px(1100), int(screen_height * 0.92)))
        self.root.minsize(minimum_width, minimum_height)
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _px(self, value: float) -> int:
        return max(1, round(value * self.ui_scale))

    def run(self) -> None:
        self.root.mainloop()

    def _run_async(self, work, done, failed) -> threading.Thread:
        def runner():
            try:
                result = work()
            except Exception as exc:
                self._post(lambda error=exc: failed(error))
            else:
                self._post(lambda: done(result))

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        return thread

    def _post(self, callback) -> None:
        """Queues a callback for the Tk main thread; Tk itself must only be touched from that thread."""
        self._ui_queue.put(callback)

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                callback = self._ui_queue.get_nowait()
                try:
                    callback()
                except Exception:
                    import traceback

                    traceback.print_exc()
        except queue.Empty:
            pass
        try:
            self.root.after(30, self._drain_ui_queue)
        except tk.TclError:
            pass

    def _close(self) -> None:
        self._close_update_dialog()
        self._save_settings()
        self.root.destroy()

    def _switch_language(self) -> None:
        target = "en" if i18n.language() == "zh" else "zh"
        if self.updating:
            messagebox.showwarning(
                tr("无法切换语言"), tr("请等待更新完成后再切换语言。"), parent=self.root
            )
            return
        # 提示用目标语言书写，方便看不懂当前界面语言的用户确认。
        prompt = "Switch CNTag to English? CNTag will restart." if target == "en" else "切换为中文界面？CNTag 将重新启动。"
        if not messagebox.askyesno("Language / 语言", prompt, parent=self.root):
            return
        self.language_setting = target
        self._save_settings()
        self._restart()

    def _restart(self) -> None:
        command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, *sys.argv]
        try:
            subprocess.Popen(command)
        except OSError as exc:
            messagebox.showerror(tr("无法重新启动"), tr("语言已保存，请手动重新打开 CNTag。\n\n{0}", exc), parent=self.root)
            return
        self._close_update_dialog()
        self.root.destroy()

    def _load_settings(self) -> dict:
        return load_settings()

    def _save_settings(self) -> None:
        settings = {
            "language": getattr(self, "language_setting", "auto"),
        }
        try:
            path = _settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, path)
        except OSError:
            pass
