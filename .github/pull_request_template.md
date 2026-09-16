## What changed

Describe the user-visible behavior and the reason for the change.

## Validation

Describe the checks you ran. Include the command and result where useful.

- [ ] `python -m ruff check .`
- [ ] `python -m mypy src` (when source exists)
- [ ] `python -m pytest -q` (when tests exist)
- [ ] Manual UI or simulator check, if applicable

## Diagnostic safety review

- [ ] This change preserves the read-only boundary and does not add ECU writes, code clearing, actuator tests, relearns, coding, reflashing, or arbitrary commands.
- [ ] Live communication remains bounded, stoppable, and explicit.
- [ ] Unsupported or missing data remains clearly labelled as unavailable.
- [ ] Session evidence remains traceable and privacy-sensitive identifiers are not added to logs or fixtures.

## Notes for reviewers

List compatibility assumptions, known limitations, migration needs, or follow-up work.
