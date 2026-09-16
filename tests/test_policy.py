import pytest

from notescan.safety import DiagnosticRequest, Operation, SafetyPolicy, encode_request
from notescan.safety.errors import PolicyViolation


def test_policy_encodes_only_allow_list_reads() -> None:
    policy = SafetyPolicy()
    live_request = policy.validate(DiagnosticRequest(Operation.LIVE_DATA, 0x0C))
    assert encode_request(live_request) == b"\x01\x0c"
    assert encode_request(policy.validate(DiagnosticRequest(Operation.STORED_CODES))) == b"\x03"
    assert encode_request(policy.validate(DiagnosticRequest(Operation.READINESS))) == b"\x01\x01"
    vin_request = policy.validate(DiagnosticRequest(Operation.VEHICLE_IDENTIFICATION))
    assert encode_request(vin_request) == b"\x09\x02"


@pytest.mark.parametrize(
    "diagnostic_request",
    [
        DiagnosticRequest(Operation.LIVE_DATA),
        DiagnosticRequest(Operation.LIVE_DATA, 0x04),
        DiagnosticRequest(Operation.STORED_CODES, 0x01),
        DiagnosticRequest(Operation.FREEZE_FRAME, 0x04),
    ],
)
def test_policy_rejects_missing_or_unapproved_arguments(
    diagnostic_request: DiagnosticRequest,
) -> None:
    with pytest.raises(PolicyViolation):
        SafetyPolicy().validate(diagnostic_request)


def test_policy_validates_batch_before_io_budget() -> None:
    policy = SafetyPolicy(max_requests_per_session=2)
    with pytest.raises(PolicyViolation):
        policy.validate_batch(
            [
                DiagnosticRequest(Operation.READINESS),
                DiagnosticRequest(Operation.READINESS),
                DiagnosticRequest(Operation.READINESS),
            ]
        )


def test_policy_is_default_deny_for_non_typed_request() -> None:
    with pytest.raises(PolicyViolation):
        SafetyPolicy().validate("01 0c")  # type: ignore[arg-type]
