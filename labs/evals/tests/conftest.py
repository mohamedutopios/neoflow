import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(LAB), str(LAB / "mesure")]
