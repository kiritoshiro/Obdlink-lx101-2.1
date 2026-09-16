# Nissan Note SafeScan

Read-only Windows diagnostic application plan for an OBDLink LX / “LX101 2.1” adapter and a user-reported 2011 Nissan Note 1.4 petrol manual.

The project starts with an offline simulator and evidence viewer. Vehicle communication is staged behind a default-deny command policy. ECU writes, code clearing, actuator tests, relearns, coding, reflashing, and arbitrary CAN frames are outside the initial scope.

The planned code will provide an offline simulator, bounded read-only OBD-II engine diagnostics, evidence-preserving session history, and guided interpretation for safer troubleshooting. Vehicle-writing operations and arbitrary diagnostic commands are outside the initial scope.

## Current app slice

The first runnable slice includes deterministic replay and fake transports, strict request allow-listing, generic PID/DTC/readiness decoders, atomic JSON session storage, Markdown/HTML evidence reports, conservative observations, and a Windows desktop replay viewer. It uses synthetic data until a separately reviewed hardware transport is added.

## Run it

```powershell
python -m pip install -e ".[dev]"
python -m notescan
```

The viewer starts with a synthetic Nissan Note profile and does not connect to a vehicle. Live adapter support will be introduced only after the offline protocol and safety checks have a complete test record.
