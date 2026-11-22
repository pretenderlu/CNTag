import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    project = Path(__file__).resolve().parent
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(project / "CNTag.spec")],
        cwd=project,
        check=True,
    )
    if sys.platform == "darwin":
        application = project / "dist" / "CNTag.app"
        executable = application / "Contents" / "MacOS" / "CNTag"
    else:
        application = executable = project / "dist" / "CNTag" / "CNTag.exe"
    report = project / "build" / "self-test.txt"
    report.unlink(missing_ok=True)
    result = subprocess.run([str(executable), "--self-test", str(report)], cwd=project)
    sys.stdout.reconfigure(errors="backslashreplace")
    print(report.read_text(encoding="utf-8") if report.is_file() else "The built application wrote no self-test report.")
    if result.returncode or not report.is_file():
        raise SystemExit("Self-test of the built application failed.")
    print(f"Application: {application}")
