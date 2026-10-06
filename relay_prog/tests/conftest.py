from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src/limbo_telemetry_bridge'), str(ROOT / 'tools')]
