"""PyInstaller entry point for the SafeScan desktop application."""

from notescan.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
