# Windows executable packaging

SafeScan is distributed as a one-folder Windows application. The folder contains `SafeScan.exe` and the Qt/Python runtime files that it needs. Keeping the runtime visible makes failures easier to diagnose and avoids the delayed startup and antivirus false positives that are common with one-file Qt bundles.

## Local build

Use a Windows virtual environment with the project dependencies installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[package]"
```

Build the application without contacting a package index:

```powershell
.\packaging\windows\build.ps1 -Clean -CreateZip
```

The script expects `PySide6` and `PyInstaller` to already be importable. If they are not installed, install them explicitly with `-InstallDependencies`:

```powershell
.\packaging\windows\build.ps1 -InstallDependencies -Clean -CreateZip
```

The resulting files are:

```text
dist\SafeScan\SafeScan.exe
dist\SafeScan-windows.zip
```

The zip can be unpacked and `SafeScan.exe` can be started directly. The first screen is the deterministic offline evidence viewer; it does not connect to an adapter or transmit vehicle commands.

## Reproducibility and safety

- Build on Windows using Python 3.12, which is the packaging workflow's pinned interpreter.
- Keep `packaging\SafeScan.spec` under review when adding Qt resources or importing new modules.
- Do not put VINs, registration details, live session exports, or adapter credentials in the bundle or repository.
- The builder packages the existing application only. It does not add ECU writes, code clearing, actuator tests, relearns, coding, reflashing, or arbitrary CAN access.
- Before sharing a build, run the normal Ruff, mypy, and pytest checks and start the executable once on a clean Windows machine.

## Troubleshooting

If the executable does not start, run the Python app from the same checkout to separate application errors from packaging errors:

```powershell
python -m notescan
```

For a packaging diagnostic build, temporarily change `console=False` to `console=True` in the spec and rebuild. Keep release builds windowed.
