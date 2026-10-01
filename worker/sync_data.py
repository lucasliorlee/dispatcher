import json
from pathlib import Path
from urllib.request import urlopen

from commands import _gallery_sections, _tower_pages


WORKER_DIR = Path(__file__).resolve().parent
ASSET_DIR = WORKER_DIR / "assets"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/lucasliorlee/dispatcher/main"


def download_github_file(path):
    with urlopen(f"{GITHUB_RAW_BASE}/{path}", timeout=30) as response:
        return response.read()


def main():
    ASSET_DIR.mkdir(exist_ok=True)
    towers_json = download_github_file("towers.json")
    skills_json = download_github_file("skills/skills.json")
    towers = json.loads(towers_json)
    skills = json.loads(skills_json).get("skills", [])
    (ASSET_DIR / "towers.json").write_bytes(towers_json)
    (ASSET_DIR / "skills.json").write_bytes(skills_json)
    catalog = {
        "towers": [{"slug": slug, "name": tower["name"]} for slug, tower in towers.items()],
        "skills": [skill["name"] for skill in skills],
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
    }
    (ASSET_DIR / "autocomplete.json").write_text(
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()