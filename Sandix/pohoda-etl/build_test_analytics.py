"""Compatibility wrapper for the first usable analytics ETL.

Prefer running `../analytics-etl/analytics_etl.py` directly.
"""

from pathlib import Path
import runpy


if __name__ == "__main__":
    script = Path(__file__).resolve().parents[1] / "analytics-etl" / "analytics_etl.py"
    runpy.run_path(str(script), run_name="__main__")
