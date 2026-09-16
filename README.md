# Nissan Note SafeScan

Read-only Windows diagnostic application plan for an OBDLink LX / “LX101 2.1” adapter and a user-reported 2011 Nissan Note 1.4 petrol manual.

The project starts with an offline simulator and evidence viewer. Vehicle communication is staged behind a default-deny command policy. ECU writes, code clearing, actuator tests, relearns, coding, reflashing, and arbitrary CAN frames are outside the initial scope.

See [the AI implementation specification](docs/Nissan-Note-SafeScan-AI-Implementation-Plan.md) for the staged architecture, validation gates, and coding instructions.
