# PyInstaller build definition for the Windows SafeScan viewer.
#
# This intentionally creates a one-folder distribution.  It keeps Qt's DLLs
# visible for troubleshooting and avoids the startup and antivirus surprises
# that are common with one-file Qt bundles.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH).parent
source_root = project_root / "src"

hiddenimports = collect_submodules("notescan")
datas = collect_data_files("notescan")

a = Analysis(
    [str(project_root / "packaging" / "entrypoint.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SafeScan",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    a.zipped_data,
    strip=False,
    upx=False,
    name="SafeScan",
)
