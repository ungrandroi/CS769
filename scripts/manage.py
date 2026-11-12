#!/usr/bin/env python3
"""Compatibility launcher; all parsing and execution live in cs769.cli."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from cs769.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
