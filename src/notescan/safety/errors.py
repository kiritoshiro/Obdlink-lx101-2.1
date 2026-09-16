"""Exceptions raised when a diagnostic action cannot be made safely."""


class SafetyError(Exception):
    """Base class for safety and execution failures."""


class PolicyViolation(SafetyError, ValueError):
    """A request is not an explicitly approved read-only operation."""


class SessionLimitExceeded(SafetyError):
    """A scan would exceed its configured finite request budget."""


class TransportError(SafetyError):
    """The transport could not complete a request."""


class ReplayMismatch(TransportError):
    """A replay received a request different from its next recorded request."""
