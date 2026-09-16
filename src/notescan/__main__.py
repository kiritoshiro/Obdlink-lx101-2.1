"""Run the offline SafeScan replay viewer with ``python -m notescan``."""

from __future__ import annotations

from .ui.app import run


def main() -> int:
    """Application entry point used by the console script."""

    return run()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
