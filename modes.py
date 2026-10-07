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
WAVES_DATA_FILE = PROJECT_DIR / "waves.json"
WAVES_PAGE = "Waves"
WAVES_CACHE_FILE = MODES_DIR / f"{WAVES_PAGE}.html"
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


def load_raw_page(page, path, force_refresh=False, parse_only=False):
    if path.exists() and not force_refresh:
        html = path.read_text(encoding="utf-8")
        print(f"Using cached page: {path}")
    elif parse_only:
        raise SystemExit(f"--parse-only needs {path}; run once without it first.")
    else:
        html = fetch_html(url_for(page))
        path.write_text(html, encoding="utf-8")
        print(f"Downloaded: {path}")
    return html


def load_pages(force_refresh=False, parse_only=False):
    MODES_DIR.mkdir(parents=True, exist_ok=True)
    pages = {}
    for mode in MODES:
        pages[mode] = load_raw_page(
            mode,
            cache_path(mode),
            force_refresh,
            parse_only,
        )
    return pages


def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value).replace("\xa0", " ").replace("\ufffd", "–"),
    ).strip()


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


WAVE_PANELS = (
    ("Easy", "Easy"),
    ("Casual", "Casual"),
    ("Intermediate", "Intermediate"),
    ("Molten", "Molten"),
    ("Fallen", "Fallen"),
    ("Challenge_Trials", "Challenge Trials"),
    ("Frost", "Frost"),
    ("Hardcore", "Hardcore"),
    ("Voidcore", "Voidcore"),
    ("Polluted_Wasteland_II", "Polluted Wasteland II"),
    ("Badlands_II", "Badlands II"),
    ("Pizza_Party", "Pizza Party"),
    ("Golden", "Golden"),
    ("Pre-MEGA", "Pre-MEGA"),
)


def _cell_text(cell):
    parsed = BeautifulSoup(str(cell), "lxml")
    speakers = [
        clean_text(caption.get_text(" ", strip=True))
        for caption in parsed.select("figure figcaption")
        if clean_text(caption.get_text(" ", strip=True))
    ]
    for figure in parsed.select("figure"):
        figure.decompose()
    text = clean_text(parsed.get_text(" ", strip=True))
    if speakers and text:
        return f"{' / '.join(dict.fromkeys(speakers))}: {text}"
    if speakers:
        return " / ".join(dict.fromkeys(speakers))
    return text


def _expand_table(table):
    """Expand rowspans so each wave row has its repeated wave number."""
    grid = []
    pending = {}
    for row_index, row in enumerate(table.select("tr")):
        cells = []
        column = 0
        for cell in row.select("th, td"):
            while (row_index, column) in pending:
                cells.append(pending.pop((row_index, column)))
                column += 1
            text = _cell_text(cell)
            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))
            for offset in range(colspan):
                cells.append(text)
                if rowspan > 1:
                    for future_row in range(1, rowspan):
                        pending[(row_index + future_row, column + offset)] = text
            column += colspan
        while (row_index, column) in pending:
            cells.append(pending.pop((row_index, column)))
            column += 1
        grid.append(cells)
    return grid


def _split_enemy_entries(value):
    entries = []
    current = []
    depth = 0
    for character in str(value):
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        if character in ",\n" and depth == 0:
            if current:
                entries.append("".join(current))
                current = []
            continue
        current.append(character)
    if current:
        entries.append("".join(current))
    normalized = []
    for entry in entries:
        entry = re.sub(r"\s+", " ", entry).strip()
        entry = re.sub(r"\(\s*", "(", entry)
        entry = re.sub(r"\s*\)", ")", entry)
        entry = re.sub(r"\s*,\s*", ", ", entry)
        if entry:
            normalized.append(entry)
    return normalized


def _parse_wave_table(table):
    rows = _expand_table(table)
    if not rows:
        return []
    headers = [value.lower() for value in rows[0]]
    wave_column = next((index for index, value in enumerate(headers) if value == "wave"), 0)
    enemy_column = next(
        (index for index, value in enumerate(headers) if "enemy type" in value),
        len(headers) - 1,
    )
    dialogue_columns = [
        index for index, value in enumerate(headers)
        if "dialogue" in value or "beginning text" in value
    ]
    waves = []
    for row in rows[1:]:
        if wave_column >= len(row):
            continue
        wave = row[wave_column]
        if not wave.isdigit() or enemy_column >= len(row):
            continue
        dialogue_values = [
            row[index]
            for index in dialogue_columns
            if index < len(row) and row[index] and row[index] != "-"
        ]
        dialogue_values = list(dict.fromkeys(dialogue_values))
        if len(dialogue_values) > 1:
            dialogue = f"{dialogue_values[0]}: {' '.join(dialogue_values[1:])}"
        else:
            dialogue = dialogue_values[0] if dialogue_values else ""
        enemy_entries = _split_enemy_entries(row[enemy_column])
        wave_number = int(wave)
        if waves and waves[-1]["wave"] == wave_number:
            if dialogue and dialogue != "-" and dialogue not in waves[-1]["dialogue"]:
                waves[-1]["dialogue"].append(dialogue)
            for enemy in enemy_entries:
                if enemy not in waves[-1]["enemies"]:
                    waves[-1]["enemies"].append(enemy)
            continue
        waves.append({
            "wave": wave_number,
            "dialogue": [dialogue] if dialogue and dialogue != "-" else [],
            "enemies": enemy_entries,
        })
    return waves


def parse_waves(html):
    soup = BeautifulSoup(html, "lxml")
    waves = {}
    for panel_id, name in WAVE_PANELS:
        panel = soup.select_one(f"#tabber-{panel_id}")
        if panel is None:
            continue
        versions = []
        seen_tables = set()
        for collapsible in panel.select(".mw-collapsible"):
            table = collapsible.select_one("table")
            if table is None or id(table) in seen_tables:
                continue
            seen_tables.add(id(table))
            entries = _parse_wave_table(table)
            if entries:
                heading = collapsible.select_one(".sectionheader")
                version_name = clean_text(heading.get_text(" ", strip=True)) if heading else "Current"
                versions.append({"name": version_name, "waves": entries})
        if not versions:
            table = panel.select_one("table")
            if table is not None:
                entries = _parse_wave_table(table)
                if entries:
                    versions.append({"name": "Current", "waves": entries})
        if versions:
            waves[panel_id] = {"name": name, "versions": versions}
    return waves


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cache and parse TDS game mode pages.")
    parser.add_argument("--force-refresh", action="store_true", help="redownload every mode page")
    parser.add_argument("--parse-only", action="store_true", help="parse cached pages without network access")
    args = parser.parse_args(argv)
    pages = load_pages(args.force_refresh, args.parse_only)
    waves_html = load_raw_page(
        WAVES_PAGE,
        WAVES_CACHE_FILE,
        args.force_refresh,
        args.parse_only,
    )
    data = {mode: parse_mode(mode, html) for mode, html in pages.items()}
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    WAVES_DATA_FILE.write_text(
        json.dumps(parse_waves(waves_html), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {DATA_FILE} ({len(data)} modes)")


if __name__ == "__main__":
    main()
