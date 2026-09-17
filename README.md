# Nissan Note SafeScan

Read-only Windows diagnostic application plan for an OBDLink LX / “LX101 2.1” adapter and a user-reported 2011 Nissan Note 1.4 petrol manual.

The project starts with an offline simulator and evidence viewer. Vehicle communication is staged behind a default-deny command policy. ECU writes, code clearing, actuator tests, relearns, coding, reflashing, and arbitrary CAN frames are outside the initial scope.

The planned code will provide an offline simulator, bounded read-only OBD-II engine diagnostics, evidence-preserving session history, and guided interpretation for safer troubleshooting. Vehicle-writing operations and arbitrary diagnostic commands are outside the initial scope.

## Current app slice

The first runnable slice includes deterministic replay and fake transports, strict request allow-listing, supported-PID bitmap and generic PID/DTC/readiness/VIN decoders, a bounded scan service that discovers supported PIDs before requesting live values, preserves raw responses, atomic JSON session storage, Markdown/HTML evidence reports, conservative observations, and a Windows desktop replay viewer. The viewer exposes metadata and raw-frame tabs for saved evidence. A separately reviewed Classic Bluetooth COM-port transport is now available for supervised integration work; the viewer still starts with synthetic data and never connects automatically.

## Run it

```powershell
python -m pip install -e ".[dev]"
python -m notescan
```

The viewer starts with a synthetic Nissan Note profile and does not connect to a vehicle. To run a live session, use **Live scan…**, enter the explicitly selected and already paired Windows COM port, and confirm the parked-vehicle prompt. The scan runs in a cancellable worker, saves evidence under the per-user SafeScan session directory, and is never started automatically or unattended.

Further implementation details are in [the development guide](docs/DEVELOPMENT.md), [the validation strategy](docs/VALIDATION.md), [the transport research](docs/RESEARCH.md), and [the Windows packaging guide](docs/PACKAGING.md).

To build the Windows folder package locally, install the packaging extra and run `.\packaging\windows\build.ps1 -Clean -CreateZip`. The same builder runs from the manual or `v*` tag workflow in GitHub Actions.
