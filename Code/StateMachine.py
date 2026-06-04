"""Compatibility wrapper for the modular StationLogic implementation."""

from __future__ import annotations

import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from station_config import *
from station_helpers import *
from station_logic import StationLogic


if __name__ == "__main__":
    print("Este archivo es un m?dulo. Ejecuta Main.py para iniciar la aplicaci?n.")
