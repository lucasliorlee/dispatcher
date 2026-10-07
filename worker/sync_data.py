import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from commands import _enemy_context, _gallery_sections, _tower_pages


WORKER_DIR = Path(__file__).resolve().parent
PROJECT_DIR = WORKER_DIR.parent
ASSET_DIR = WORKER_DIR / "assets"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/lucasliorlee/dispatcher/main"


def download_github_file(path):
    with urlopen(f"{GITHUB_RAW_BASE}/{path}", timeout=30) as response:
        return response.read()


def load_data(source):
    if source == "local":
        return (
            (PROJECT_DIR / "towers.json").read_bytes(),
            (PROJECT_DIR / "skills" / "skills.json").read_bytes(),
            (PROJECT_DIR / "enemies.json").read_bytes(),
            (PROJECT_DIR / "modes.json").read_bytes(),
            (PROJECT_DIR / "waves.json").read_bytes(),
        )
    return (
        download_github_file("towers.json"),
        download_github_file("skills/skills.json"),
        download_github_file("enemies.json"),
        download_github_file("modes.json"),
        download_github_file("waves.json"),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sync tower and skill data into Worker assets.")
    parser.add_argument(
        "--source",
        choices=("github", "local"),
        default="github",
        help="data source (default: github)",
    )
    args = parser.parse_args(argv)

    ASSET_DIR.mkdir(exist_ok=True)
    towers_json, skills_json, enemies_json, modes_json, waves_json = load_data(args.source)
    towers = json.loads(towers_json)
    skills = json.loads(skills_json).get("skills", [])
    enemies = json.loads(enemies_json)
    modes = json.loads(modes_json)
    waves = json.loads(waves_json)
    (ASSET_DIR / "towers.json").write_bytes(towers_json)
    (ASSET_DIR / "skills.json").write_bytes(skills_json)
    (ASSET_DIR / "enemies.json").write_bytes(enemies_json)
    (ASSET_DIR / "modes.json").write_bytes(modes_json)
    (ASSET_DIR / "waves.json").write_bytes(waves_json)
    catalog = {
        "towers": [{"slug": slug, "name": tower["name"]} for slug, tower in towers.items()],
        "skills": [skill["name"] for skill in skills],
        "enemies": [
            {
                "slug": slug,
                "name": enemy["name"] + (
                    f" ({_enemy_context(enemy)})" if _enemy_context(enemy) else ""
                ),
            }
            for slug, enemy in enemies.items()
        ],
        "pages": {
            slug: [page[0] for page in _tower_pages(tower)]
            for slug, tower in towers.items()
        },
        "gallery": {
            slug: [
                {"name": name, "entries": [entry["label"] for entry in entries]}
                for name, entries in _gallery_sections(tower)
            ]
            for slug, tower in towers.items()
        },
        "modes": [{"slug": slug, "name": mode["name"]} for slug, mode in modes.items()],
        "waves": [
            {
                "slug": slug,
                "name": mode["name"],
                "count": max(
                    (len(version.get("waves", [])) for version in mode.get("versions", [])),
                    default=0,
                ),
            }
            for slug, mode in waves.items()
        ],
    }
    (ASSET_DIR / "autocomplete.json").write_text(
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()