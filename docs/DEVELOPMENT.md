# Development guide

SafeScan is a Windows-first diagnostic application for bounded, read-only OBD-II work. The initial product is designed around an offline simulator, an evidence viewer, and generic engine/emissions data. Vehicle communication is introduced only after the simulator and protocol parsing are well tested.

## Requirements

- Windows 10 or Windows 11
- Python 3.11, 3.12, or 3.13
- A Git checkout of this repository

The OBDLink adapter and a vehicle are not required for normal development. Keep live hardware checks separate from the automated test suite.

## Set up a local environment

From the repository root, create and activate a virtual environment, then install the project with its development tools:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell blocks activation, run the commands through an already activated environment or adjust the user-level execution policy according to your Windows administration policy.

## Run the checks

```powershell
python -m ruff check .
python -m mypy src
python -m pytest -q --cov=notescan --cov-report=term-missing
```

The commands are also run by GitHub Actions on Windows for Python 3.11 through 3.13. The workflow skips a check when its corresponding source or test directory does not exist yet, which keeps the repository usable while the application is being assembled.

## Suggested project layout

```text
src/notescan/       application package
tests/              offline unit and integration tests
fixtures/           sanitized protocol replies and simulator scenarios
docs/               development and validation notes
```

Keep transport, protocol parsing, persistence, interpretation, and UI code in separate modules. The UI should call typed application services; it should not construct raw adapter commands or decode bytes itself.

## Live viewer path

The **Live scan…** action in the viewer asks for a Windows COM port and a
stationary-vehicle confirmation before creating `SerialTransport` and
`SafeScanner` in a worker thread. A stop request is observed at scheduler
boundaries; there is no reconnect or retry loop. Completed and partial sessions
are saved below `%LOCALAPPDATA%\SafeScan\sessions` unless `run(storage_root=...)`
was given an explicit directory. The viewer never discovers or connects to a
port on its own. The default scan first asks for the standard supported-PID
bitmap, then requests only advertised live PIDs; if discovery is unavailable,
live requests are skipped and the non-live read set remains bounded. The
Metadata and Raw frames tabs expose adapter identity, supported-PID discovery,
negative-response notes, and the original request and response bytes for each
completed exchange.

## Safety boundary for contributions

Every new live operation must be explicitly allow-listed, bounded by a timeout and poll budget, cancellable, and covered by an offline test. The first release must not transmit ECU writes, clear fault codes, run actuator tests, perform relearns or coding, reflash modules, or send arbitrary CAN frames. Do not add a raw-command console as a debugging shortcut.

Store raw replies and decoded values together with timestamps, units, request identifiers, responding ECU information, software version, and completion status. Redact VINs and other identifying data from committed fixtures and issue attachments.

Hardware work should be done with the car safely parked, ignition state recorded, a charged battery, and no other diagnostic application connected to the adapter. Begin with a short generic read-only session and retain the exported evidence for comparison.
