# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules, copy_metadata

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules("subtitleyc")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("fastapi")
hiddenimports += collect_submodules("starlette")
hiddenimports += collect_submodules("pydantic")
hiddenimports += collect_submodules("webview")
hiddenimports += collect_submodules("av")
hiddenimports += collect_submodules("PIL")
hiddenimports += collect_submodules("tkinter")
hiddenimports += [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtPrintSupport",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "shiboken6",
]
hiddenimports += ["multipart", "yt_dlp"]

binaries = []
binaries += collect_dynamic_libs("av")
binaries += collect_dynamic_libs("PIL")

datas = [
    ("static", "static"),
    ("assets", "assets"),
    ("README.md", "."),
    ("README.CN.md", "."),
    ("LICENSE", "."),
    ("THIRD-PARTY-NOTICES.txt", "."),
    ("licenses", "licenses"),
]
for package in ("fastapi", "uvicorn", "starlette", "pydantic", "pywebview", "yt_dlp", "av", "pillow", "PySide6", "shiboken6"):
    try:
        datas += copy_metadata(package)
    except Exception:
        pass


a = Analysis(
    ["subtitleyc/desktop.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SubtitleYC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/SubtitleYC.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SubtitleYC",
)
