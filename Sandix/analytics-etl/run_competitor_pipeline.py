from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
SCRAPER_DIR = ROOT / "profibagr-scraper"
ANALYTICS_DIR = ROOT / "analytics-etl"
SCRAPER_PYTHON = ROOT / ".venv_scraper" / "bin" / "python"


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def build_env(competitor_env_file: str | None) -> dict[str, str]:
    shell_env = os.environ.copy()
    env: dict[str, str] = {}
    env.update(load_env_file(ANALYTICS_DIR / ".env"))
    default_competitor_env = SCRAPER_DIR / ".env"
    env.update(load_env_file(Path(competitor_env_file)) if competitor_env_file else load_env_file(default_competitor_env))
    env.update(shell_env)
    return env


def run_step(command: list[str], env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scraper + analytics ETL for one competitor")
    parser.add_argument("--scope", choices=("queue", "full"), default="queue")
    parser.add_argument("--skip-filter", action="store_true", help="Skip part-number filter ETL")
    parser.add_argument("--skip-analytics", action="store_true", help="Skip analytics ETL")
    parser.add_argument("--skip-scraper", action="store_true", help="Skip scraper step")
    parser.add_argument("--competitor-env-file", help="Optional competitor-specific .env file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = build_env(args.competitor_env_file or os.getenv("COMPETITOR_ENV_FILE"))

    competitor_code = env.get("COMPETITOR_CODE") or "PROFIBAGR"
    competitor_name = env.get("COMPETITOR_NAME") or "Profibagr"
    env["COMPETITOR_CODE"] = competitor_code
    env["COMPETITOR_NAME"] = competitor_name

    if not SCRAPER_PYTHON.exists():
        raise RuntimeError(f"Missing scraper python executable: {SCRAPER_PYTHON}")

    if not args.skip_scraper:
        run_step([str(SCRAPER_PYTHON), str(SCRAPER_DIR / "profibagr_scraper.py"), "--scope", args.scope], env)

    if not args.skip_analytics:
        run_step([str(SCRAPER_PYTHON), str(ANALYTICS_DIR / "analytics_etl.py")], env)

    if not args.skip_filter:
        run_step([str(SCRAPER_PYTHON), str(ANALYTICS_DIR / "part_number_filter_etl.py")], env)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
