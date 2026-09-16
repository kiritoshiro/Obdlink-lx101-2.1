# Validation strategy

Validation proceeds from deterministic offline behavior to a short, controlled live read-only session. A passing result must show what was checked, what was unavailable, and which evidence supports each interpretation.

## Validation layers

1. **Static checks.** Run Ruff and mypy on every change. Keep type errors and lint warnings at zero.
2. **Unit tests.** Test byte parsing, PID decoding, units, timestamps, state transitions, timeout handling, and persistence with deterministic inputs.
3. **Simulator tests.** Feed known-good, unsupported, malformed, delayed, truncated, and disconnected replies through the same application services used by the UI. Missing values must remain unavailable rather than becoming zero.
4. **Evidence tests.** Verify that a session preserves raw exchanges, decoded values, metadata, completion status, and an audit-friendly export. Interrupted sessions must be marked incomplete and remain readable.
5. **UI checks.** Confirm that scan state, cancellation, errors, unsupported parameters, units, and data freshness are visible without requiring a live adapter.
6. **Hardware smoke test.** After offline checks pass, test one short generic OBD-II session with the car stationary and safely parked. Close other software that could own the adapter, record the adapter identity, and stop immediately on unexpected behavior.

## Minimum acceptance checks for a read-only scan

- The adapter connection can be opened and closed cleanly.
- An explicit allow-list controls every transmitted request.
- Requests have finite timeouts and a total session budget.
- A disconnect or cancellation stops polling and leaves a recoverable session record.
- Multiple ECU replies are retained with their source information.
- Unsupported PIDs and absent freeze-frame data are shown as unavailable.
- Stored, pending, and permanent code categories remain distinct.
- Readiness state includes the monitor status and the conditions under which it was observed.
- Exported reports identify the session time, software version, adapter identity, vehicle profile fields that are known, and coverage gaps.
- No write, clear, actuator, relearn, coding, reflashing, or arbitrary-frame operation is reachable from the first-release UI or service API.

## Hardware test record

Record live checks in a local, uncommitted session export. Do not commit VINs, registration details, location data, or other identifying information.

| Field | Value |
| --- | --- |
| Date and time | |
| SafeScan version/commit | |
| Windows version | |
| Adapter label and firmware | |
| Vehicle profile fields known | |
| Ignition/engine state | |
| Requests attempted | |
| Completion status | |
| Unexpected behavior | |
| Export path | |

Nissan-specific modules or proprietary requests require separate evidence: the exact responding ECU, a documented request/response definition, an offline fixture, and a controlled compatibility test. Until all four exist, the feature should report that coverage is unavailable.

