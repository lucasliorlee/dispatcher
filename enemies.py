# scrap enemy data
# will eventually be merged with scrapper.py

import re
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://tds.wiki"
ENEMIES_URL = f"{BASE_URL}/w/Enemies"
PROJECT_DIR = Path(__file__).resolve().parent
ENEMY_CACHE_DIR = PROJECT_DIR / "enemies"
INDEX_CACHE_FILE = ENEMY_CACHE_DIR / "index.html"
ENEMY_DATA_FILE = PROJECT_DIR / "enemies.json"

MODES = {
    "Normal": ["Easy_Mode", "Casual_Mode", "Intermediate_Mode", "Molten_Mode", "Fallen_Mode", "Frost_Mode", "Challenge_Trials", "Hardcore_Mode", "Voidcore_Mode"],
    "PVP": ["Basic_Arena", "Molten_Arena", "Fallen_Arena"],
    "Special": ["Polluted_Wasteland_II", "Badlands_II", "Pizza_Party", "Tutorial"],
    "Sandbox": ["Legacy_Molten_Mode", "Golden_Mode", "Legacy_Fallen_Mode", "Brain_Rot", "Other"],
    "Event": ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019"],
    "Removed": ["Replaced", "Pre-MEGA", "Polluted_Wasteland", "Legacy_Hidden_Wave", "Other_2"]
}


def slug(name):
    """Use the wiki page name as a stable, filesystem-safe cache filename."""
    return re.sub(r"[^a-z0-9_]+", "", name.lower().replace(" ", "_"))


def download(url, path):
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    if response.headers.get("cf-mitigated") == "challenge" or re.search(
        r"<title>\s*Just a moment", response.text[:2048], re.IGNORECASE
    ):
        raise requests.HTTPError(f"Cloudflare challenge blocked {url}", response=response)
    response.raise_for_status()
    Path(path).write_text(response.text, encoding="utf-8")


def clean_text(element):
    if element is None:
        return ""
    text = element if isinstance(element, str) else element.get_text(" ", strip=True)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_enemy(path, page):
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8"), "lxml")
    infobox = soup.select_one("aside.portable-infobox")
    fields = {}
    if infobox:
        for item in infobox.select(".pi-data[data-source]"):
            key = item["data-source"]
            if key.startswith("legacy_") or key in fields:
                continue
            label = clean_text(item.select_one(".pi-data-label"))
            value = clean_text(item.select_one(".pi-data-value"))
            if label and value:
                fields[label] = value

    title = clean_text(infobox.select_one("[data-source='title1']") if infobox else None) or page.replace("_", " ")
    description = clean_text(soup.select_one("meta[name='description']").get("content")) if soup.select_one("meta[name='description']") else ""
    image = ""
    image_tag = soup.select_one("meta[property='og:image']")
    if image_tag:
        image = image_tag.get("content", "").split("?", 1)[0]
    stats = {
        label: fields[label]
        for label in (
            "Base Health", "Health Scaling", "Speed", "Defense", "Cash Given",
            "Spawned By", "Hidden?", "Flying?", "Ghost?", "Lead?", "Attributes",
        )
        if label in fields
    }
    return {
        "slug": slug(page),
        "name": title,
        "url": f"{BASE_URL}/w/{page}",
        "image": image,
        "description": description,
        "mode_appearance": fields.get("Mode Appearance", ""),
        "wave_debut": fields.get("Wave Debut", ""),
        "stats": stats,
    }


def enemy_links(soup):
    """Return unique enemy page URLs found in the Enemies page tabs."""
    links = {}
    panels = soup.select(".tabber__panel")
    roots = panels or [soup]
    for root in roots:
        for anchor in root.select("a[href]"):
            href = anchor["href"]
            if not href.startswith("/w/"):
                continue
            page = unquote(urlsplit(href).path.removeprefix("/w/"))
            if not page or page.lower() in {"enemies", "special:search"}:
                continue
            if ":" in page or "/" in page:
                continue
            name = anchor.get_text(" ", strip=True) or page.replace("_", " ")
            links.setdefault(page, (name, f"{BASE_URL}/w/{page}"))
    return links


def download_enemies():
    ENEMY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    index_response = requests.get(ENEMIES_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    if index_response.headers.get("cf-mitigated") == "challenge" or re.search(
        r"<title>\s*Just a moment", index_response.text[:2048], re.IGNORECASE
    ):
        raise requests.HTTPError(f"Cloudflare challenge blocked {ENEMIES_URL}", response=index_response)
    index_response.raise_for_status()
    INDEX_CACHE_FILE.write_text(index_response.text, encoding="utf-8")

    soup = BeautifulSoup(index_response.text, "lxml")
    links = enemy_links(soup)
    for page, (name, url) in links.items():
        html_path = ENEMY_CACHE_DIR / f"{slug(page)}.html"
        if html_path.exists():
            print(f"Cached: {name}")
            continue
        print(f"Downloading: {name}")
        try:
            download(url, html_path)
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                print(f"  ! missing page: {name}")
                continue
            raise

    data = {
        item["slug"]: item
        for page in links
        if (html_path := ENEMY_CACHE_DIR / f"{slug(page)}.html").exists()
        for item in [parse_enemy(html_path, page)]
    }
    ENEMY_DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Cached {len(links)} enemy pages in {ENEMY_CACHE_DIR}")
    print(f"Wrote {ENEMY_DATA_FILE}")


if __name__ == "__main__":
    download_enemies()

