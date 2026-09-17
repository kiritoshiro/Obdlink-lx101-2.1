# Supervised hardware smoke test

Use this checklist only after the offline checks and Windows packaging workflow
are green. The first session is a short, generic, read-only check. The vehicle
must remain stationary; SafeScan has no write, clear, actuator, relearn,
coding, reflashing, or arbitrary-frame features.

## Before connecting

- Park the 2011 Nissan Note E11 securely, apply the parking brake, and record
  whether the ignition is on and whether the engine is running.
- Charge the vehicle battery and the Windows laptop. Do not perform the test
  while driving or while another scan tool is connected.
- Pair the OBDLink LX in Windows Bluetooth settings and note the COM port. The
  viewer requires that explicit port; it does not discover or connect to ports
  automatically.
- Close OBDLink software and every other application that could own the
  adapter's COM port.
- Start SafeScan and confirm that the displayed vehicle profile is only the
  known information: Nissan Note E11, 2011, 1.4 petrol, 65 kW, manual.

## First session: ignition on, engine off

1. Open **Live scan…**, enter the paired COM port, and accept the stationary
   vehicle confirmation.
2. Let the default scan run once. It first discovers supported PIDs, then reads
   only the bounded identification/readiness/DTC set and advertised live PIDs.
3. Confirm that the session finishes or is clearly marked partial, and inspect
   the Metadata and Raw frames tabs for adapter identity, request/response
   bytes, negative responses, and supported-PID evidence.
4. Save or copy the session export locally. Redact the VIN before sharing it;
   do not commit live exports to Git.

## Unverified assumptions to check on the first real session

These are the places where the offline fixtures cannot stand in for the adapter.
Record what actually happened for each one, whether or not the scan succeeded.

- **Adapter reset timing.** `ATZ` is sent with the same two-second
  `command_timeout_s` as every other setup command, and a slower reset fails the
  whole `open()` with `adapter initialisation exceeded its time budget` or
  `adapter did not return its prompt before timeout`. If the first connection
  attempt fails that way, note the elapsed time before raising
  `SerialConfig.command_timeout_s`; do not raise it pre-emptively.
- **Multi-frame responses.** `SerialTransport` returns everything received
  before the `>` prompt as one byte string, and the decoders join surviving
  lines with spaces. That is correct for single-frame replies but has never been
  exercised against a real multi-frame one. Watch the Mode 09 VIN read in
  particular, and any read where more than one ECU answers. Keep the Raw frames
  tab for any response that spans several lines, and compare the decoded VIN
  against the one on the vehicle.
- **Protocol-search chatter.** The first request after `ATSP0` may be prefixed
  with `SEARCHING...`. This is stripped before decoding, so supported-PID
  discovery should succeed on the first attempt. If the session instead reports
  `Supported-PID discovery was unavailable`, capture the exact raw bytes.
- **Stored-code framing.** On CAN the Mode 03/07/0A responses carry a DTC count
  byte, which is detected from the payload length. Compare any decoded codes
  against a trusted reference tool before acting on them.

## Optional second session: engine idling

Run this only when the first session completed without transport errors. Keep
the car stationary, record that the engine is running, and repeat one scan. Do
not rev the engine or add repeated polling. Compare the timestamped live values
with the engine state and retain both sessions for review.

## Stop criteria

Cancel the scan and switch off the ignition if the adapter repeatedly
disconnects, the vehicle shows a warning, the transport reports a timeout or
unexpected protocol response, the adapter becomes unusually hot, or anything
else behaves unexpectedly. Keep the partial session; it is diagnostic evidence.

## Test record

Record date/time, SafeScan commit, Windows version, adapter label/firmware,
COM port, ignition/engine state, completion status, unexpected behavior, and
the local export path. Also record the outcome of each item under *Unverified
assumptions* above. Keep VIN, registration, and location data out of GitHub
issues and committed fixtures.
