import _isolate  # noqa: F401
import unittest


class AppSmokeTests(unittest.TestCase):
    def test_app_constructs_pumps_events_and_destroys(self):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            self.skipTest("Tk unavailable")
        from cntag.app import CNTagApp

        try:
            app = CNTagApp()
        except tkinter.TclError as error:
            self.skipTest(f"Tk cannot start: {error}")
        try:
            for _ in range(5):
                app.root.update()
        finally:
            app.root.destroy()


if __name__ == "__main__":
    unittest.main()
