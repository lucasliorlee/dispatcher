"""Run all wiki scrapers in dependency order."""

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SCRAPER_DIR = PROJECT_DIR / "scrapper"


def run_scraper(name, *arguments):
    command = [sys.executable, str(SCRAPER_DIR / name), *arguments]
    subprocess.run(command, cwd=PROJECT_DIR, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scrape tower, skill, and enemy data from tds.wiki.")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="ignore cached pages and redownload supported scraper inputs",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="rebuild data from cached pages without making network requests",
    )
    args = parser.parse_args(argv)

    if args.parse_only:
        run_scraper("towers.py", "--parse-only")
        run_scraper("enemies.py", "--parse-only")
    else:
        tower_args = ["--force-refresh"] if args.force_refresh else []
        run_scraper("towers.py", *tower_args)
        enemy_args = ["--force-refresh"] if args.force_refresh else []
        run_scraper("enemies.py", *enemy_args)


if __name__ == "__main__":
    main()
