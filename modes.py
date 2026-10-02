"""Cache and parse game mode pages from the Official TDS Wiki."""

import argparse
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://tds.wiki"
PROJECT_DIR = Path(__file__).resolve().parent
MODES_DIR = PROJECT_DIR / "modes"
DATA_FILE = PROJECT_DIR / "modes.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}
MODES = [
    "Easy_Mode",
    "Casual_Mode",
    "Intermediate_Mode",
    "Molten_Mode",
    "Fallen_Mode",
    "Hidden_Wave",
    "Challenge_Trials",
    "Frost_Mode",
    "Hardcore_Mode",
    "Voidcore_Mode",
    "Pizza_Party",
    "Badlands_II",
    "Polluted_Wasteland_II",
    "Sandbox_Mode",
    "Legacy_Molten_Mode",
    "Golden_Mode",
    "Legacy_Fallen_Mode",
    "Story_Mode",
    "PVP",
    "Pre-MEGA_Modes",
    "Versus",
    "Hidden_Wave_(Legacy)",
    "PVP_Test",
]


def url_for(mode):
    return f"{BASE_URL}/w/{mode}"


def fetch_html(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    if response.headers.get("cf-mitigated") == "challenge" or re.search(
        r"<title>\s*Just a moment", response.text[:2048], re.IGNORECASE
    ):
        raise requests.HTTPError(f"Cloudflare challenge blocked {url}", response=response)
    response.raise_for_status()
    return response.text


def cache_path(mode):
    return MODES_DIR / f"{mode}.html"


def load_pages(force_refresh=False, parse_only=False):
    MODES_DIR.mkdir(parents=True, exist_ok=True)
    pages = {}
    for mode in MODES:
        path = cache_path(mode)
        if path.exists() and not force_refresh:
            html = path.read_text(encoding="utf-8")
            print(f"Using cached page: {path}")
        elif parse_only:
            raise SystemExit(f"--parse-only needs {path}; run once without it first.")
        else:
            html = fetch_html(url_for(mode))
            path.write_text(html, encoding="utf-8")
            print(f"Downloaded: {path}")
        pages[mode] = html
    return pages


def clean_text(value):
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def text_lines(element):
    return [
        clean_text(line)
        for line in element.get_text("\n", strip=True).splitlines()
        if clean_text(line)
    ]


def parse_infobox(soup):
    infobox = {}
    for item in soup.select(".portable-infobox .pi-data"):
        label = item.select_one(".pi-data-label")
        value = item.select_one(".pi-data-value")
        if label and value:
            infobox[clean_text(label.get_text(" ", strip=True))] = clean_text(
                value.get_text(" ", strip=True)
            )
    return infobox


def table_block(table):
    rows = []
    for row in table.select("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.select("th, td")]
        if cells:
            rows.append(cells)
    if not rows:
        return None
    headers = rows[0] if table.find("th") else []
    return {
        "type": "table",
        "headers": headers,
        "rows": rows[1:] if headers else rows,
    }


def content_block(element):
    if element.name == "p":
        text = clean_text(element.get_text(" ", strip=True))
        return text or None
    if element.name in {"ul", "ol"}:
        items = [
            clean_text(item.get_text(" ", strip=True))
            for item in element.find_all("li", recursive=False)
        ]
        return {"type": "list", "items": [item for item in items if item]} if items else None
    if element.name == "table":
        return table_block(element)
    if element.name == "div":
        tables = [table_block(table) for table in element.find_all("table", recursive=False)]
        tables = [table for table in tables if table]
        return tables[0] if len(tables) == 1 else ({"type": "group", "items": tables} if tables else None)
    return None


def parse_sections(root):
    """Preserve article paragraphs, lists, and tables in their wiki order."""
    sections = {}
    headings = root.find_all("div", class_="mw-heading", recursive=False)
    for index, heading in enumerate(headings):
        title = heading.find(["h2", "h3"])
        if title is None:
            continue
        name = clean_text(title.get_text(" ", strip=True))
        if name == "Contents":
            continue
        end = len(headings)
        for next_index in range(index + 1, len(headings)):
            end = next_index
            break
        blocks = []
        stop_heading = headings[end] if end < len(headings) else None
        sibling = heading.find_next_sibling()
        while sibling is not None and sibling is not stop_heading:
            block = content_block(sibling)
            if block:
                blocks.append(block)
            sibling = sibling.find_next_sibling()
        if blocks:
            sections[name] = blocks
    return sections


def parse_mode(mode, html):
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("#mw-content-text .mw-parser-output") or soup.select_one(".mw-parser-output")
    if root is None:
        raise ValueError(f"Could not find article content for {mode}")
    for element in root.select("sup.reference, style, script"):
        element.decompose()
    title = soup.select_one("meta[property='og:title']")
    image = soup.select_one("meta[property='og:image']")
    parsed_sections = parse_sections(root)
    description_blocks = parsed_sections.get("Description", [])
    description = " ".join(
        block for block in description_blocks if isinstance(block, str)
    )
    return {
        "slug": mode,
        "name": clean_text(title.get("content", mode.replace("_", " "))) if title else mode.replace("_", " "),
        "url": url_for(mode),
        "image": image.get("content", "") if image else "",
        "description": description,
        "infobox": parse_infobox(soup),
        "sections": parsed_sections,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cache and parse TDS game mode pages.")
    parser.add_argument("--force-refresh", action="store_true", help="redownload every mode page")
    parser.add_argument("--parse-only", action="store_true", help="parse cached pages without network access")
    args = parser.parse_args(argv)
    pages = load_pages(args.force_refresh, args.parse_only)
    data = {mode: parse_mode(mode, html) for mode, html in pages.items()}
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {DATA_FILE} ({len(data)} modes)")


if __name__ == "__main__":
    main()
