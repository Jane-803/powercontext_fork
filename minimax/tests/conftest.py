import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = os.environ.get("CATALOG_SOURCE", "sample_app")
sys.path.insert(0, str(ROOT / source))
