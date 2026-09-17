# Transport and vehicle research

This note records the primary sources used for the first Windows hardware
milestone. It documents assumptions; it does not claim that every Nissan Note
module or PID is supported.

## OBDLink LX and Windows

- [OBDLink LX product page](https://www.obdlink.com/lx-bluetooth/) identifies
  the LX as a Classic Bluetooth adapter for Windows and states that it is
  backwards compatible with the ELM327 command set.
- [OBDLink Family Reference and Programming Manual](https://www.obdlink.com/frpm)
  describes the adapter serial framing, prompt-based command exchange, and
  identity commands such as `ATI`, `STDI`, `STI`, and `STMFR`.
- [OBDLink Windows setup guide](https://support.obdlink.com/support/solutions/articles/43000727094)
  requires Windows pairing before the application connects and warns that
  another OBD application can own the adapter at the same time.
- [OBDLink adapter comparison](https://support.obdlink.com/support/solutions/articles/43000713351)
  lists LX under Bluetooth v3.0. One support article contains a contradictory
  Bluetooth LE label; the product page, comparison table, and manual agree on
  Classic Bluetooth, so SafeScan uses a Windows COM-port transport and verifies
  identity at runtime.

The user-supplied `LX101 2.1` text is retained as a label. It is not treated as
an adapter firmware or capability claim.

## Serial and protocol rules

- [pySerial API](https://pyserial.readthedocs.io/en/stable/pyserial_api.html)
  documents finite read and write timeouts. SafeScan never uses an unlimited
  serial timeout.
- [ELM327 data sheet](https://www.elmelectronics.com/wp-content/uploads/2017/01/ELM327DS.pdf)
  documents the `ATZ` reset, `ATSP0` automatic protocol selection, ASCII hex
  OBD requests, and the `>` prompt.
- [OBD Solutions real-time data guide](https://www.obdsol.com/knowledgebase/obd-software-development/reading-real-time-data/)
  confirms that Mode 01 values are actively requested from the ECU.
- [OBD Solutions problem-vehicle guidance](https://www.obdsol.com/knowledgebase/obd-software-development/obd-problem-vehicles/)
  warns that unsupported requests and timing violations can make some ECUs
  stop responding. The implementation therefore uses a finite request budget,
  spacing between requests, supported-PID discovery, and no tight polling.

SafeScan treats Modes 03, 07, and 0A as read services for stored, pending, and
permanent DTCs respectively. Mode 04 (clear/reset emissions information) is
not represented by the policy or transport. A vehicle may still omit a mode or
return a negative response; those bytes are preserved and the session is marked
incomplete when the scheduler cannot finish.

## Vehicle coverage boundary

The working profile remains the facts supplied by the user: 2011 Nissan Note
E11, 1.4 petrol, 65 kW, manual transmission. The exact market, ECU identity,
protocol, supported PID bitmap, and non-engine module coverage must be learned
from the vehicle and preserved in the session evidence. No Nissan-specific
service is enabled by this research note.

## Safe live milestone

`notescan.transport.SerialTransport` is intentionally narrow: it opens one
user-selected COM port, runs a fixed adapter identity/setup sequence, accepts
only allow-listed generic read payloads, waits for the adapter prompt, applies
finite deadlines and response-size limits, and closes the port on failure. It
does not expose code clearing, ECU writes, actuator controls, firmware updates,
arbitrary frames, or a raw command console.

`notescan.diagnostics.SafeScanner` supplies the next application boundary. Its
default plan first performs one supported-PID discovery request, then executes
the bounded identification/readiness/DTC set and only the advertised live
PIDs. When discovery is negative or malformed it preserves that evidence and
skips live reads. Explicit caller-supplied plans remain finite and typed, so a
caller cannot bypass the allow-list. The scanner decodes generic responses,
retains the original request and response for each completed exchange, and
persists incomplete evidence after a transport failure. It does not retry or
reconnect automatically.
