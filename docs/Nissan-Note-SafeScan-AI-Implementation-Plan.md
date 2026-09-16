# Nissan Note SafeScan — AI implementation specification

Prepared 16 September 2026. This is a development plan, not vehicle-tested software or a confirmed Nissan enhanced-diagnostics database.

## 1. Objective and confirmed scope

Build a Windows laptop application for the user's 2011 Nissan Note, 1.4 petrol, 65 kW, manual transmission, using their Bluetooth scanner labelled both “OBDLink LX” and “LX101 2.1”.

The product should preserve diagnostic evidence, show reliable measurements, explain patterns with uncertainty, and guide sensible next checks. Its advantage should be diagnostic workflow and traceability, not the number of commands it can transmit.

User-confirmed: Windows first; manual gearbox; the two adapter labels above.

Provisional: European-market Note E11 with CR14DE engine. A period Nissan UK brochure lists the 1.4 petrol as CR14DE, 1,386 cc, 65 kW, five-speed manual. Confirm the individual car's market, engine and identifiers rather than treating the brochure as identification of this car. [Nissan brochure, technical specification, PDF page 23](https://xr793.com/wp-content/uploads/2022/10/2011-Nissan-Note-Uk.pdf).

Unknown until inspected: exact adapter hardware/firmware, ECU identity/calibration, actual diagnostic protocol, supported PIDs and monitors, and access to non-engine modules. “2.1” must not be assumed to mean a particular firmware, chip or capability.

## 2. Compatibility findings and changes to the supplied plan

The genuine OBDLink LX supports Windows and Android, ELM327-compatible commands, and standard OBD-II protocols. It is not an iOS adapter. Generic engine/emissions diagnostics are the sensible first target; hardware protocol support alone does not establish Nissan enhanced-module coverage. [OBDLink LX](https://www.obdlink.com/lx-bluetooth/).

OBDLink says enhanced add-ons primarily cover vehicles sold in North America. The published coverage document inspected lists Versa Note 2014–2019; it does not establish coverage for this 2011 European Note. Do not select a Versa profile as a substitute. This is a coverage gap, not proof that enhanced access is impossible. [OBDLink coverage guidance](https://support.obdlink.com/support/solutions/articles/43000705533), [published coverage PDF](https://www.obdlink.com/wp-content/uploads/2020/09/oem-specific_coverage.pdf).

| Supplied proposal | Safer replacement |
|---|---|
| One-button scan of every module | “Scan supported systems”, with an explicit coverage and omissions table |
| Our own Nissan PID database | Versioned, sourced definitions validated against exact ECU families; initially empty |
| Experiment with custom PIDs on the car | Research offline; validate documented requests in a simulator/bench setup first |
| Known-safe actuator tests | Excluded from this application |
| Relearns and BCM settings | Excluded; they change state and need a separate service-tool project |
| Clear all codes after backup | Excluded; evidence preservation does not make clearing harmless |
| CVT health screen | Removed: the user confirmed a manual gearbox |
| Automatic fault diagnosis | Evidence-based hypotheses, missing information and next checks |
| Same app everywhere initially | Windows MVP, with a transport boundary for possible future ports |

“Read-only” means the app intentionally requests data without requesting ECU writes or control. It still transmits diagnostic traffic and can wake modules. It is a risk reduction, not a zero-risk guarantee or passive listening mode.

## 3. Product stages

### Release A: simulator and evidence viewer

Fully usable without a vehicle: replay example sessions, view DTCs and graphs, compare recordings, generate reports, and test the command policy. Every synthetic screen and export is labelled SIMULATED. No transport to the car is opened automatically.

### Release B: generic engine/emissions diagnostics

Provide adapter identification, detected protocol, supported parameter discovery, readiness/MIL status, stored and pending DTCs, freeze frames, selected live measurements, session storage and exports. Read permanent DTCs and vehicle information when supported. Optional monitor-result decoding comes only after the protocol-specific decoder is validated.

### Release C: useful guided interpretation

Add recording workflows for cold-start temperature plausibility, normal warm-up, warm idle, fuel-trim context and supply-voltage observations. Add before/after comparisons with operating-condition matching.

### Release D: verified Nissan read-only extension

Add one documented ECU feature at a time. This stage may remain unavailable if legitimate documentation and matching hardware cannot be obtained. Releases A–C remain useful and complete without it.

## 4. Non-negotiable command policy

Implement a default-deny policy below the UI, directly in the component that owns the Bluetooth serial connection. Higher layers submit typed operations, never raw command strings.

Allowed categories:

1. Explicitly reviewed adapter identity/status queries.
2. A fixed, reviewed set of temporary adapter configuration operations needed for communication.
3. Individually registered standard OBD reads with validated argument lengths, response schema and capability checks.
4. Later, individually approved enhanced reads matched to a verified ECU profile.

Never permit a command simply because it begins with `AT`, `ST`, `01`, `21`, `22`, or some other prefix. Adapter commands can change persistent settings; an apparently read-oriented vehicle service is not permission to enumerate every identifier.

Prohibit in the production build:

- Clearing emissions or manufacturer DTCs, including OBD service $04.
- OBD service $08 controls; actuator tests; injector or cylinder cut-out; fan, pump, throttle, brake, steering or airbag activation.
- ECU resets, security access, programming/download/upload, coding, adaptation and relearn routines.
- Changes to immobilizer, keys, mileage, VIN, emissions behavior or BCM convenience settings.
- Arbitrary CAN/K-line frames, header/address sweeps, DID/PID brute force, bus fuzzing, and undocumented initialization sequences.
- Raw command consoles, script hooks, network endpoints or “expert overrides” that can bypass policy.
- Adapter firmware updates, factory reset, voltage calibration, programmable-parameter writes and persistent settings changes.

Do not implement dangerous operations and merely hide their buttons. Do not include a “clear codes” API. Firmware maintenance, if ever needed, is a separate manufacturer-tool workflow.

The serializer must build the entire permitted command from typed values. Reject embedded carriage returns/newlines, multiple commands, trailing bytes, malformed hex, unknown enum values and excessive lengths before any bytes are written. Append exactly one framing terminator internally. Never emit a blank command that may repeat the previous adapter command.

Policy applies to the complete communication context: protocol, addressing, adapter formatting, active operation, arguments and ECU profile. Route/header changes cannot silently transform an approved generic read into a different exchange.

Only the transport worker may access the serial handle. UI, report generation, plugins and any language model have no direct transport access. Imported files and replay data are data only and cannot trigger transmissions. This protects against application mistakes; it does not claim to sandbox arbitrary malicious Python running on the same computer.

## 5. Recommended implementation stack

Use Python with PySide6 for the Windows application, pySerial for the paired Bluetooth serial port, SQLite for local structured storage, and pytest for meaningful protocol and safety tests. Select and pin mutually compatible supported versions at implementation time; record them in a lock file and build manifest.

pySerial provides the Windows serial backend; PySide6 is Qt's Python binding. Keep a thin transport interface so the domain model and recorded fixtures remain reusable. [pySerial documentation](https://pyserial.readthedocs.io/en/latest/pyserial.html), [Qt for Python](https://doc.qt.io/qtforpython-6/).

Pair the LX using Windows Bluetooth settings and select its outgoing serial port where available. First prove this transport on the user's laptop. If Windows does not expose a usable serial port, resolve that transport issue explicitly; do not switch to a BLE library merely because the device uses Bluetooth.

Keep the app local and offline. No account, server, telemetry or language-model API is required for scanning. Start with deterministic interpretation rules. Package a Windows executable only after the replay and transport milestones pass. Linux and Android are later projects; sharing data definitions does not imply that a desktop UI automatically ports to phones.

Suggested repository layout:

```text
src/notescan/
  domain/        # typed operations, observations, faults, findings
  safety/        # allowlist, validation, operating constraints
  transport/     # serial owner, fake transport, isolated replay transport
  adapter/       # identity, approved setup, prompt framing, state machine
  obd/           # capability maps, services, protocol-specific response parsing
  profiles/      # verified declarative vehicle and ECU definitions
  diagnostics/   # rules, recording workflows, comparison logic
  storage/       # SQLite schema, migrations, raw-session journal
  reports/       # escaped HTML, CSV and JSON export
  ui/            # connection, scan, live data, history, report screens
tests/
  policy/
  framing/
  parsing/
  scheduler/
  fixtures/
  acceptance/
docs/
  COMMAND_POLICY.md
  COMPATIBILITY.md
  VALIDATION.md
  KNOWN_LIMITATIONS.md
```

## 6. Adapter identification and connection lifecycle

Use the actual device's documented identification commands. Candidate identity queries include `ATI`, `STI` and `STDI`; the latter two identify STN firmware and hardware when implemented. Record replies verbatim. A compatible-looking response is not cryptographic proof of authenticity. An unsupported ST query must not produce repeated probing. [OBDLink programming manual, device-ID section](https://www.scantool.net/scantool/downloads/682/obdlink_frpm_f.pdf).

Before sending vehicle requests, establish known adapter state from a reviewed initialization recipe appropriate to the detected implementation. Record the recipe ID. Account for settings left by another app, including headers, filters, formatting and protocol choice. If state cannot be established confidently, stop.

Review setup commands individually against the adapter manual. Prefer temporary protocol selection with memory disabled where documented; do not assume “try protocol” cannot persist a choice. Distinguish adapter initialization from an ECU reset. A reviewed adapter-only initialization may be acceptable; ECU resets remain prohibited. [ELM327 datasheet, protocol and memory commands](https://www.scantool.net/scantool/downloads/103/elm327dsh.pdf).

Lifecycle:

```text
DISCONNECTED
  -> PORT_OPEN
  -> ADAPTER_IDENTIFIED
  -> ADAPTER_READY
  -> USER_STARTED_SESSION
  -> PROTOCOL_DETECTED
  -> CAPABILITIES_DISCOVERED
  -> READY
  -> SNAPSHOT or RECORDING
  -> STOPPING
  -> DISCONNECTED

Any communication or policy failure -> HALTED
HALTED requires an explicit user action to start a fresh session.
```

The adapter may perform standard protocol detection for an approved generic request. Do not assume CAN from the model year; support only protocols for which the app has tested parsing. A detected but unimplemented protocol yields an honest unsupported result.

Stop behavior: cancel unsent work immediately, terminate polling/keepalives, bound completion of any in-flight exchange, close the link using the reviewed cleanup procedure, and save the partial session. Do not promise to retract an already transmitted request. Check for adapter-side periodic activity in validation; app shutdown must not leave a diagnostic loop running.

On connection loss, never replay queued requests or auto-resume a scan. Invalidate prior capability state and identify the connection again. Permit only one application to use the adapter at a time; close OBDwiz/OBDLink before opening this app.

## 7. Generic OBD scope and capability discovery

These are candidate standard services, not a blanket transmit allowlist. The implementation must register the exact legal forms and validate them against applicable J1979/J1979-DA definitions and representative captures. Mode $06 formats differ by protocol. [SAE J1979, 2010 edition listing](https://saemobilus.sae.org/standards/j1979_201009-e-e-diagnostic-test-modes).

| Service | Intended use | Initial handling |
|---|---|---|
| $01 | Current engine/emissions data and readiness | Supported PIDs only; standard support-map discovery permitted |
| $02 | Freeze-frame data | Preserve frame number, associated DTC and responding ECU |
| $03 | Stored emissions DTCs | Read once per snapshot; do not relabel as necessarily active now |
| $07 | Pending emissions DTCs | Read once per snapshot |
| $0A | Permanent emissions DTCs | Bounded supported/availability check; lack of support is normal |
| $09 | Vehicle information | Discover supported items; VIN/calibration may be absent |
| $06 | On-board monitor results | Later milestone; unknown definitions stay undecoded |
| $05 | Legacy oxygen-sensor test results | Defer until a relevant non-CAN decoder is validated |

Discover support maps separately per responding ECU and service. Follow standard continuation bits; do not scan all possible numeric PIDs. Do not reuse live-data support as proof of freeze-frame support. Standard services without support bitmaps use a bounded, registered request and explicit availability result.

Start the live-data registry with supported examples: RPM ($0C), vehicle speed ($0D), coolant ($05), intake-air temperature ($0F), fuel-system status ($03), calculated load ($04), bank-1 short/long fuel trims ($06/$07), MAF ($10), throttle position ($11), and ECU voltage ($42). Sensor presence/type determines whether oxygen-sensor or equivalence-ratio data is useful. MAP and other readings are optional. [PID definitions and decoding reference from hardware manufacturer CSS Electronics](https://www.csselectronics.com/pages/obd2-pid-table-on-board-diagnostics-j1979).

Treat this list as optional readings, not a promise that this car supplies them. Do not invent oil pressure, oil temperature, fuel pressure, wheel speeds, fan command, mileage or cylinder-specific misfire counts.

Keep adapter supply voltage and ECU-reported voltage as different measurements, with different sources and timestamps. Neither is a battery capacity test. [ELM327 datasheet, voltage-reading command](https://www.scantool.net/scantool/downloads/103/elm327dsh.pdf).

## 8. Framing, parsing and traffic limits

The following limits are proposed conservative software defaults for validation, not Nissan-approved safety thresholds:

- One request in flight across the entire connection.
- Start at no more than one vehicle request per second. Permit up to two per second only after stable communication on a validated profile. Keep these as total rates, not rates per PID.
- Rotate a small set of useful readings; show the actual achieved rate and age for every signal. A higher screen refresh rate does not imply fresher samples.
- Snapshot DTCs, identity and readiness; never repeatedly poll the entire scan in a live-data loop.
- Set finite protocol-aware deadlines, including a separate longer initial protocol-detection deadline. Document actual values in the connection recipe and test them; do not truncate legitimate initialization to fit a generic timeout.
- At most one retry after synchronization is positively restored; three consecutive communication failures halt the session. Do not retry unsupported, policy-rejected or malformed commands.
- Maximum five-minute ignition-on/engine-off capture by default, with an explicit user restart. Engine-running recordings also have finite duration and request budgets.

At these rates, oxygen-sensor waveforms may be undersampled. Show trends only; do not judge switching speed or transient behavior unless measured timing and sampling are adequate for that specific analysis.

Parse incrementally: Bluetooth reads may contain part of a line or several replies. Support command echo, CR/LF variation, prompts, status lines, multiple ECUs and protocol-specific framing. Recognize adapter errors as errors, never payload hex. Correlate replies to the requested service/PID and responding address.

Preserve CAN identifiers or legacy source headers. Do not discard every header or assume every first response is the engine ECU. Use exactly one validated approach to multi-frame handling: adapter-reassembled payloads or explicitly parsed frames, as configured. Never reassemble already reassembled data. Do not inject arbitrary flow-control frames; approved adapter handling is part of the protocol recipe.

After a timeout, quarantine late bytes and restore a known request boundary before further traffic. If this cannot be proven, halt. Never assign a late response to the next request. Detect truncation, impossible lengths, invalid sequence order and buffer overruns.

Differentiate these outcomes:

```text
valid | not_supported | not_available_now | no_response |
invalid_response | communication_error | policy_blocked | not_attempted
```

Missing data is null plus a reason, never numeric zero. Incomplete data must not yield “no faults” or “healthy”. A previously valid signal becomes visibly stale after a documented age limit.

## 9. Data model and evidence preservation

Store a session before requesting vehicle data. Persist a request-attempt record before transmit and record the actual outcome afterward. If durable recording fails, halt acquisition instead of silently continuing without evidence.

Minimum entities:

| Entity | Required fields |
|---|---|
| Vehicle | local ID, user-entered model/year/fuel/gearbox, verification state, optional VIN, engine/market evidence |
| Adapter | raw identity replies, hardware/firmware if decoded, transport settings, identification confidence |
| Session | UUID, UTC times, monotonic origin, app/build/policy/profile versions, capture phase, user notes, completion state |
| Exchange | operation ID, request/response bytes, source address, monotonic send/receive times, protocol, outcome/error |
| Observation | parameter ID, value/unit, source ECU, decoder version, quality, exchange reference, effective timestamp/age |
| DTC | code bytes/text, service/status category, ECU, definition source/version, snapshot membership |
| Freeze frame | ECU, frame ID, triggering code if supplied, original fields, decoded values and availability |
| Finding | rule ID/version, evidence references, conditions, result, confidence category, alternatives, next check |
| Coverage | feature/module, attempted operation, result, unsupported/unverified reason |

Store raw exchanges in an append-only journal and structured data in SQLite with a crash-recovery strategy. Do not overwrite raw evidence when parsers improve; store a new decoding version. Use monotonic time for intervals and UTC for human history.

Before/after comparisons require matching vehicle, ECU, units and operating context. A missing DTC after an incomplete scan is not a resolved DTC. A code disappearing is an observation, not proof of repair.

VIN and adapter serial numbers remain local by default. Offer redacted exports that sanitize raw as well as decoded identifiers. Reports escape all imported text; CSV export must prevent spreadsheet formula execution in text cells. Importers enforce size/schema bounds and never evaluate profile formulas or scripts.

Exports: readable HTML report, CSV measurements and versioned JSON session bundle. HTML should be printable using the user's browser; built-in PDF export is optional later. Always include coverage gaps, sampling limitations and incomplete-session status.

## 10. Guided observations and interpretation rules

These workflows request data only. The app cannot operate pedals, fans, brakes or engine speed. Initial live validation and Release B use a stationary vehicle only.

### A. Baseline snapshot

Record warning-light observations, symptoms and manually entered mileage if needed. Read standard DTCs, readiness and available freeze frames. Identify which systems were actually checked. Do not imply inspection of ABS/SRS/BCM from generic engine results.

### B. Cold-start temperature plausibility

Let the user record a genuine cold-soak condition and approximate ambient temperature. Compare available intake-air and coolant readings in that context. Differences can prompt a sensor/wiring or heat-soak question; the app must not invent a universal Nissan pass/fail tolerance. Then record an ordinary start if the user chooses.

### C. Warm-up observation

Track coolant, RPM, elapsed time and load during normal operation. Identify missing data or an unusual trend for review. Do not command the fan, deliberately overheat the engine, require extended idling until a fan starts, or declare a thermostat failed from one recording. Precise manufacturer temperature limits require verified service documentation.

### D. Warm-idle and fuel-trim observation

Require adequate warm-up evidence, appropriate fuel-system status and a reasonably steady operating window. Record RPM, load, fuel trims, available airflow and oxygen/equivalence data. Missing prerequisites produce “insufficient evidence”. Distinguish open-loop conditions from a fuel-control fault.

Illustrative result: “Fuel correction is elevated in this warm-idle recording. Intake leakage, airflow measurement error and fuel-delivery issues are possible explanations. The data does not identify a failed part.” Only say a value is elevated when the rule has a documented threshold or a clearly labelled same-car baseline comparison.

An optional later guided comparison at a different engine speed requires a sourced procedure and explicit user participation. Do not hard-code the supplied plan's 2,500 RPM routine as a universal requirement. No throttle actuation or relearn sequence is part of this app.

### E. Voltage observation

Display adapter and ECU voltage separately across engine-off and ordinary running conditions. Mark load changes entered by the user. Treat observed drops as prompts for confirmation with appropriate electrical testing, not a conclusive battery/alternator diagnosis. Slow Bluetooth polling cannot guarantee capture of the cranking minimum.

### F. Oxygen and catalyst context

Identify the actual available sensor data type before choosing graphs. Do not impose narrowband voltage expectations on wideband/equivalence-ratio data. Compare operating conditions and supported monitor results. Neither a rear-sensor trace nor a DTC alone proves a catalyst needs replacement.

For every rule store: identifier, version, prerequisites, evidence window, units, threshold source, minimum sample count, allowed sample gaps, alternative explanations and output text. Rules run deterministically and can be replayed.

Use confidence labels such as “measurement confirmed”, “pattern suggests”, “insufficient evidence”. Never fabricate numerical probabilities. Fault severity and confidence are different fields. Do not infer historical fault timing from today's scan time or claim that old ABS and engine faults occurred together unless the ECU evidence establishes it.

## 11. Vehicle-use safeguards

Provide a clear Start and immediately available Stop. Before stationary engine-running work, ask the operator to confirm outdoor/adequately extracted ventilation, secured vehicle, neutral and parking brake. A zero speed PID is supporting evidence, not proof that the vehicle is safely secured.

For Release B, stop the capture if movement is detected. If speed is unavailable, retain the stationary-only instruction and record the inability to verify it. No road-test workflow is required for the first release.

Monitor supply voltage as an acquisition condition. The implementer must document and validate a conservative pause threshold and sustained-duration rule before live release; do not invent a Nissan battery-health threshold. Until validated, use short attended sessions and stop on voltage instability or communication resets. The adapter's operating-voltage specification is not a battery-drain safety threshold.

If warning lights newly appear, the engine runs abnormally, overheating is suspected or communication repeatedly fails, stop the diagnostic session and assess the vehicle. Stopping polling does not stop the engine or eliminate an existing mechanical fault.

Preserve manufacturer sleep behavior, cease traffic at session end and do not rely on an advertised sleep feature to protect against an app that keeps sending requests. Do not implement unattended overnight scanning.

## 12. Gate for Nissan-specific features

An enhanced definition needs all of the following before production use:

1. Exact scope: chassis generation, market, model years, engine, ECU family and identifying part/calibration evidence.
2. Legitimate technical source with document/version/page reference; standard service semantics alone are insufficient.
3. Verified physical network/pin/protocol reachability using the LX without improvised rewiring.
4. Exact documented request, addressing, prerequisites, legal response formats, units/scaling and timing.
5. A review of side effects and any required session initialization. If it needs security access, an undocumented session transition or a state-changing routine, exclude it from this plan.
6. Offline parser fixtures including positive, negative, malformed and absent-data cases.
7. Controlled bench or suitable simulator validation of the transaction. A simulator validates implementation behavior, not actual vehicle support.
8. Supervised parked-car validation and comparison with a trusted reference tool on the same ECU variant.
9. A reproducible approval record tied to the profile hash and exact validated scope.

Use declarative profiles with trusted, built-in decoder IDs. No executable Python, `eval`, arbitrary expressions or downloaded command packs. Sideloaded definitions stay disabled for live traffic. A profile update requires review and a release; the app does not learn new commands from internet content or AI output.

Initial Nissan profile status:

```yaml
profile_id: nissan_note_e11_cr14de_candidate
scope:
  user_reported_year: 2011
  fuel: petrol
  power_kw: 65
  transmission: manual
  engine_candidate: CR14DE
  market: unverified
verified_ecu_fingerprints: []
enhanced_operations: []
live_enhanced_enabled: false
```

Never fill empty fields by borrowing commands from a Micra, Juke, Leaf, Versa or another Note generation. Shared branding or engines are research clues, not compatibility proof.

SRS, ABS, EPS, BCM and other systems remain “not checked: verified read profile unavailable” unless this gate is met. Their presence in a generic Nissan module list does not mean they are reachable on this car. Do not report a module as absent merely because it did not answer.

## 13. Optional AI explanation layer

AI is unnecessary for reliable scanning. If added later, feed it a sanitized structured report after acquisition, not a serial connection. It may explain measurements, summarize uncertainty or draft mechanic questions. It cannot choose commands, create profiles, modify thresholds, start tests or trigger another scan.

Keep measured facts, rule-generated findings and AI commentary visibly distinct. Require evidence references for each diagnostic claim and withhold unsupported statements. Treat DTC descriptions, notes and imported documents as untrusted text. Cloud upload is off by default and requires the user's explicit choice for the particular report.

## 14. Implementation sequence and completion gates

### Milestone 0 — establish the evidence folder

Write the confirmed/provisional/unknown compatibility record. Catalogue adapter and protocol manuals, lawful DTC/PID definition sources, platform assumptions and outstanding questions. Set Windows/manual as confirmed. Record the scanner's two reported labels verbatim.

Done when: no manufacturer-specific support or hardware version is presented as verified without evidence.

### Milestone 1 — domain model, fake transport and command policy

Implement typed operations, a small explicit registry, default-deny validation and a fake byte transport. Make replay the default launch mode. Add the cancellation path and request budget before serial access.

Done when: every unregistered operation is rejected before the write boundary, including command injection and malformed arguments; zero test requires a car.

### Milestone 2 — framing and decoders

Implement incremental prompt framing, request correlation, protocol-specific source addressing and optional multi-frame responses. Build capability, DTC, freeze-frame and initial PID decoders from documented definitions. Keep error and availability states distinct.

Done when: normal, multi-ECU, fragmented, delayed, malformed and unsupported captures decode correctly or fail explicitly without producing false measurements.

### Milestone 3 — storage, reports and replay

Implement the session journal, SQLite migrations, observation provenance, crash recovery, redaction and HTML/CSV/JSON outputs. Build the evidence viewer before real-car UI polish.

Done when: an interrupted session is recoverable, re-decoding is traceable, simulated data cannot be mistaken for live data, and exports correctly show coverage gaps.

### Milestone 4 — Windows adapter transport

Validate pairing/port selection, identity-only communication, a reviewed initialization recipe, read/write timeouts and exclusive port ownership. Exercise the scheduler and shutdown against a suitable simulator or bench setup.

Done when: no uncontrolled retry loops, queued-request replay, background polling after Stop or persistent adapter changes are observed. All identity strings and setup operations are recorded.

### Milestone 5 — first supervised generic read

Before custom traffic, save a read-only baseline using OBDwiz/OBDLink, without clearing anything; close it afterward. Start a short parked, ignition-on engine-off session with custom software. Establish supported generic capabilities, read a small snapshot, then disconnect. Compare the result to the reference tool sequentially, not concurrently.

Done when: DTCs/readiness and available identity information agree or discrepancies are explained; no unexpected commands appear in the transmit audit; the report does not imply whole-car coverage.

### Milestone 6 — stationary live data

With the operator attending the car, record a short ordinary idle session using a few supported readings. Validate values, units, stale-data behavior, voltage handling, request rates and Stop. Compare steady-state readings with the reference tool, accounting for different capture times.

Done when: communication remains stable, failures stop cleanly, sampling limits are visible, and every displayed measurement links to a valid exchange.

### Milestone 7 — guided observations and Windows package

Add deterministic workflows and comparisons, then a usable Windows executable with installation/run instructions and an offline demo. Test packaging on a clean Windows environment.

Done when: prerequisites block invalid analyses, unknowns stay unknown, the app works offline, and actual hardware validation is distinguished from simulator-only tests in the release notes.

### Milestone 8 — optional enhanced ECU feature

Apply section 12 to one candidate feature. Do not start with a scan of every address. Stop this milestone if exact definitions or reference validation are unavailable; ship the completed generic application honestly.

Done when: one bounded feature has documented compatibility, policy approval, fixtures and matching-vehicle evidence. A broader coverage claim requires separate evidence.

## 15. Mandatory acceptance tests

- Policy: reject all unknown services, altered headers, illegal lengths and newline injection; assert the fake transport received zero bytes for each rejection.
- Capability: skip unsupported PIDs; keep different ECU support maps separate; a missing response does not prove absence or health.
- Framing: handle partial prompts, echo, split lines, multiple responses, late replies and Bluetooth disconnects.
- Parsing: verify units, source addressing, payload lengths, multi-frame completeness, status distinctions and unavailable sentinels.
- State: Stop cancels queued work; restart requires explicit user action; old responses cannot satisfy new requests.
- Rate limits: use an injected clock to prove total request caps, finite budgets, bounded retries and backoff.
- Storage: disk-full and mid-session crash preserve available evidence and halt further acquisition when journaling fails.
- Interpretation: missing prerequisites or sparse samples produce insufficient evidence, never an invented normal value or definitive diagnosis.
- Reports: clearly separate stored/pending/permanent categories, show unavailable modules, redact identifiers throughout, and escape imported content.
- Profile isolation: wrong vehicle/ECU, modified profile, unapproved definition or imported transcript cannot enable live enhanced requests.
- Hardware: compare sequentially with a trusted tool; report what was physically tested, on which adapter/firmware/ECU, and what remains untested.

Do not create faults on the car to test the software. Do not disconnect safety components, deliberately discharge the battery, clear real evidence, induce overheating or interrupt power during writes. Inject failures into the fake transport or simulator instead.

## 16. Copy-and-paste instruction for the coding AI

```text
Build Nissan Note SafeScan according to this specification.

Confirmed target: Windows laptop; user-reported 2011 Nissan Note,
1.4 petrol, 65 kW, manual; Bluetooth adapter label says OBDLink LX
and LX101 2.1. CR14DE/E11 and European market are candidate profile
details until verified. Do not infer hardware/firmware from “2.1”.

Implement milestones 0–3 first, entirely offline. Use Python,
PySide6, pySerial, SQLite and pytest with pinned compatible versions.
The first runnable deliverable is a simulator/replay application,
not a car-connected scanner.

Before serial work, implement default-deny typed operations and
enforce validation in the sole owner of the transport. No raw-command
UI/API, no bypass, no clearing codes, no actuation, resets, security
access, coding, reflashing, relearns or arbitrary frame generation.
Review adapter configuration separately from vehicle services.

Keep one request in flight; use bounded deadlines, retries and total
request rates. Stop cancels pending work. Lost connections never
auto-resume. Record raw evidence, source ECU, units, timestamps,
availability and decoder versions. Never substitute zero for missing
data, and never describe incomplete coverage as a healthy vehicle.

Only use documented generic requests with tested decoders initially.
Discover standard support maps; do not brute-force identifiers.
No Nissan-specific commands may be invented or borrowed by analogy.
Keep the enhanced profile empty until the evidence gate is met.

Implement deterministic findings that state prerequisites, evidence,
uncertainty and alternative explanations. No runtime AI is required.
Any later AI receives exported data and has no vehicle access.

After each milestone, provide changed files, commands to run, test
results, limitations and the next milestone. Do not claim real-device
validation when only fixtures were used. When hardware or verified
documentation is missing, finish all independent offline work and
state the precise remaining validation dependency.

Deliver source, runnable offline demo, tests, versioned schemas,
command-policy documentation, compatibility matrix, sample reports,
and eventually a Windows package. Follow the staged validation plan
before any supervised connection to the user's car.
```

## 17. Definition of a successful first release

The user can connect a verified compatible adapter, perform a bounded read-only engine/emissions scan, see supported measurements, understand what remains unchecked, preserve the evidence, compare appropriate sessions and export a useful mechanic report. The app never offers a command that changes vehicle settings or clears diagnostic history.

This specification has been researched against the linked sources. No connection to the user's scanner or vehicle was made, and no enhanced Nissan command has been verified here.
