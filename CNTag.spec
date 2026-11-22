import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project = Path(SPECPATH)
version = re.search(r'__version__\s*=\s*"([^"]+)"', (project / "cntag" / "__init__.py").read_text(encoding="utf-8")).group(1)

icon = project / "assets" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")

a = Analysis(
    [str(project / "main.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[
        *(
            (str(asset), "assets")
            for asset in (project / "assets").iterdir()
            if sys.platform == "darwin" or asset.name != "icon.icns"
        ),
        (str(project / "LICENSE"), "."),
        (str(project / "THIRD_PARTY_NOTICES.md"), "."),
        (str(project / "licenses"), "licenses"),
        *collect_data_files("zhconv"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy",
        "cryptography",
        "bcrypt",
        "setuptools",
        "pkg_resources",
        "wheel",
        "pip",
        "psutil",
        "yaml",
        "win32com",
        "pythonwin",
        "brotli",
        "brotlicffi",
        "zstandard",
        "PIL.AvifImagePlugin",
        "PIL._avif",
        "PIL.ImageCms",
        "PIL._imagingcms",
        "PIL.ImageQt",
        "unittest",
        "doctest",
        "pydoc",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CNTag",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CNTag",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="CNTag.app",
        icon=str(icon),
        bundle_identifier="app.cntag.desktop",
        info_plist={
            "CFBundleDisplayName": "CNTag",
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "NSHighResolutionCapable": True,
        },
    )
