# Nissan Note SafeScan

Read-only Windows diagnostic application plan for an OBDLink LX / “LX101 2.1” adapter and a user-reported 2011 Nissan Note 1.4 petrol manual.

The project starts with an offline simulator and evidence viewer. Vehicle communication is staged behind a default-deny command policy. ECU writes, code clearing, actuator tests, relearns, coding, reflashing, and arbitrary CAN frames are outside the initial scope.

The planned code will provide an offline simulator, bounded read-only OBD-II engine diagnostics, evidence-preserving session history, and guided interpretation for safer troubleshooting. Vehicle-writing operations and arbitrary diagnostic commands are outside the initial scope.
