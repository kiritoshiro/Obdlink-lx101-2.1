"""Nissan Note SafeScan package.

The package is intentionally usable offline.  Vehicle I/O is supplied through
an explicit transport implementation and is guarded by the read-only policy.
"""

__all__ = ["safety", "transport"]
