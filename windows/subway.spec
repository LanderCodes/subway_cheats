# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: builds dist/subway.exe and dist/subway-gui.exe."""

datas = [("../data", "data")]

cli = Analysis(
    ["../subway_tool.py"],
    pathex=["..", "../mac"],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
cli_pyz = PYZ(cli.pure)
cli_exe = EXE(
    cli_pyz,
    cli.scripts,
    cli.binaries,
    cli.datas,
    [],
    name="subway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

gui = Analysis(
    ["../subway_gui_tk.py"],
    pathex=["..", "../mac"],
    binaries=[],
    datas=datas,
    hiddenimports=["subway_tool", "ios_backup"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
gui_pyz = PYZ(gui.pure)
gui_exe = EXE(
    gui_pyz,
    gui.scripts,
    gui.binaries,
    gui.datas,
    [],
    name="subway-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
