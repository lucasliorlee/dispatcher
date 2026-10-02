# scrap enemy data
# will eventually be merged with scrapper.py

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

BASE_URL = "https://tds.wiki"
ENEMIES_URL = f"{BASE_URL}/w/Enemies"
PROJECT_DIR = Path(__file__).resolve().parent
ENEMY_CACHE_DIR = PROJECT_DIR / "enemies"
INDEX_CACHE_FILE = ENEMY_CACHE_DIR / "index.html"
ENEMY_DATA_FILE = PROJECT_DIR / "enemies.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": f"{BASE_URL}/",
}

IMAGE_EXTS = (".png", ".webp", ".jpg", ".jpeg", ".gif")

# Infobox fields that are not in a stats/ability tab
TOP_LEVEL_FIELDS = {"mode_appearance": "mode_appearance", "first_wave_appearance": "wave_debut"}
# Article sections that are not text worth keeping
SKIPPED_SECTIONS = {"Contents", "Gallery"}
# Direct children of the article body that are never section content
SKIPPED_BLOCKS = {"toc", "tds-navbox", "succession-table", "mw-collapsible", "clear-both", "desktop-only", "bubble-box", "notice"}

SKIP_TAGS = {"img", "picture", "source", "style", "script", "noscript", "figure"}
BLOCK_TAGS = {
    "div", "p", "ul", "ol", "li", "table", "tbody", "dl", "dt", "dd", "blockquote",
    "section", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
}


def slug(name):
    """Use the wiki page name as a stable, filesystem-safe cache filename."""
    return re.sub(r"[^a-z0-9_]+", "", name.lower().replace(" ", "_"))


def is_cloudflare_challenge(response):
    """True if the response is a Cloudflare 'Just a moment' challenge page."""
    return response.headers.get("cf-mitigated") == "challenge" or bool(
        re.search(r"<title>\s*Just a moment", response.text[:2048], re.IGNORECASE)
    )


def fetch(url, session=None):
    """GET a URL and return its HTML, raising on Cloudflare challenges or HTTP errors."""
    getter = session.get if session else requests.get
    response = getter(url, headers=HEADERS, timeout=30)
    if is_cloudflare_challenge(response):
        raise requests.HTTPError(f"Cloudflare challenge blocked {url}", response=response)
    response.raise_for_status()
    return response.text


def download(url, path, session=None):
    """Download a URL to a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fetch(url, session), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML -> text
# ---------------------------------------------------------------------------

def tab_pairs(panel):
    """(label, content element) for each tab of a wiki tabber."""
    labels = [
        " ".join(tab.get_text(" ", strip=True).split())
        for tab in panel.select(":scope > .wds-tabs__wrapper .wds-tabs__tab-label, :scope > nav .tabber__tab")
    ]
    contents = panel.select(":scope > .wds-tab__content") or panel.select(".tabber__panel")
    pairs = []
    for index, content in enumerate(contents):
        label = labels[index] if index < len(labels) else ""
        pairs.append((label or ("Regular" if len(contents) == 1 else f"Variant {index + 1}"), content))
    return pairs


def _wrap(inner, mark):
    core = inner.strip()
    if not core:
        return inner
    start = inner[: len(inner) - len(inner.lstrip())]
    end = inner[len(inner.rstrip()):]
    return f"{start}{mark}{core}{mark}{end}"


def render(node, depth=0, md=False):
    """Flatten an element's contents to text. Lists become '- ' lines, <br> and blocks become newlines."""
    return "".join(render_child(child, depth, md) for child in node.children)


def render_child(child, depth=0, md=False):
    if isinstance(child, Comment) or not isinstance(child, (NavigableString, Tag)):
        return ""
    if isinstance(child, NavigableString):
        return str(child)
    name = child.name
    classes = child.get("class", [])
    if (
        name in SKIP_TAGS
        or child.get("typeof") == "mw:File"
        or "reference" in classes
        or "mw-editsection" in classes
        or "mw-collapsible-toggle" in classes
    ):
        return ""
    if name == "br":
        return "\n"
    if "wds-tabber" in classes or "tabber" in classes:
        return "".join(
            f"\n{'**' + label + '**' if md else label}\n{render(content, depth, md)}\n"
            for label, content in tab_pairs(child)
        )
    if name in ("ul", "ol"):
        return f"\n{render(child, depth + 1, md)}\n"
    if name == "li":
        return f"\n{'  ' * max(depth - 1, 0)}- {render(child, depth, md)}\n"
    if name == "tr":
        cells = [render(cell, depth, md).strip() for cell in child.find_all(["td", "th"], recursive=False)]
        return "\n" + " | ".join(" ".join(cell.split()) for cell in cells if cell.strip()) + "\n"
    if md and name in ("b", "strong"):
        return _wrap(render(child, depth, md), "**")
    if md and name in ("i", "em"):
        return _wrap(render(child, depth, md), "*")
    if name in BLOCK_TAGS:
        return f"\n{render(child, depth, md)}\n"
    return render(child, depth, md)


def to_lines(text):
    """Split rendered text into lines, keeping list indentation and dropping empty bullets."""
    lines = []
    for raw in text.replace("\xa0", " ").split("\n"):
        stripped = raw.strip()
        if not stripped or stripped == "-":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append(" " * indent + " ".join(stripped.split()))
    return lines


def nest_under_headers(lines):
    """A list that follows a plain line belongs to it: 'Duo' then its '- 210' items."""
    result = []
    after_header = False
    for line in lines:
        is_item = line.lstrip().startswith("- ")
        if not is_item:
            after_header = True
            result.append(line)
        else:
            result.append("  " + line if after_header and not line.startswith(" ") else line)
    return result


def format_value(element):
    """Infobox value -> one string. A single line stays plain; several lines become a bullet list."""
    lines = nest_under_headers(to_lines(render(element)))
    if len(lines) <= 1:
        return lines[0].strip() if lines else ""
    return "\n".join(line if line.lstrip().startswith("- ") else f"- {line}" for line in lines)


def label_text(element):
    return " ".join(render(element).split()) if element else ""


# ---------------------------------------------------------------------------
# Page parsing
# ---------------------------------------------------------------------------

def parse_data_items(container):
    """label -> value for every infobox row inside a container (first label wins)."""
    items = {}
    for row in container.select(".pi-data"):
        label = label_text(row.select_one(".pi-data-label"))
        value = format_value(row.select_one(".pi-data-value"))
        if label and value and label not in items:
            items[label] = value
    return items


def panel_kind(panel):
    header = panel.find("h2", class_="pi-header", recursive=False)
    if header is None and panel.parent is not None:
        header = panel.parent.find("h2", class_="pi-header", recursive=False)
    title = header.get_text(" ", strip=True).lower() if header else ""
    if "stat" in title:
        return "stats"
    if "abilit" in title:
        return "abilities"
    return None


def parse_infobox(soup):
    infobox = soup.select_one("aside.portable-infobox")
    result = {"name": "", "mode_appearance": "", "wave_debut": "", "extra": {}, "variants": []}
    if infobox is None:
        return result

    title = infobox.select_one("[data-source='title1']")
    result["name"] = label_text(title)

    for row in infobox.select(".pi-data"):
        if row.find_parent("section", class_="pi-panel") is not None:
            continue
        label = label_text(row.select_one(".pi-data-label"))
        value = format_value(row.select_one(".pi-data-value"))
        key = TOP_LEVEL_FIELDS.get(row.get("data-source", ""))
        if key:
            result[key] = value
        elif label and value:
            result["extra"][label] = value

    variants = []

    def variant_for(label, index, tab_count):
        found = next((item for item in variants if item["name"] == label), None)
        if found is None and tab_count == len(variants):
            found = variants[index]
        if found is None:
            found = {"name": label, "stats": {}, "abilities": []}
            variants.append(found)
        return found

    for panel in infobox.select("section.pi-panel"):
        if panel.find_parent("section", class_="pi-panel") is not None:
            continue  # nested image tabs, not data
        kind = panel_kind(panel)
        if kind is None:
            continue
        pairs = tab_pairs(panel)
        for index, (label, content) in enumerate(pairs):
            variant = variant_for(label, index, len(pairs))
            if kind == "stats":
                variant["stats"].update(parse_data_items(content))
            else:
                for row in content.select(".pi-data"):
                    text = format_markdown(row.select_one(".pi-data-value"))
                    if text:
                        variant["abilities"].append({
                            "label": label_text(row.select_one(".pi-data-label")),
                            "text": text,
                        })
    result["variants"] = variants
    return result


def format_markdown(element):
    return "\n".join(to_lines(render(element, md=True)))


def parse_sections(soup):
    """Article text by heading: {"Strategy": ["- line", ...], ...}. Gallery and the TOC are skipped."""
    root = soup.select_one(".mw-parser-output")
    sections = {}
    if root is None:
        return sections
    current = None
    for child in root.find_all(recursive=False):
        classes = set(child.get("class", []))
        if "mw-heading2" in classes or child.name == "h2":
            current = " ".join(child.get_text(" ", strip=True).split())
            if current in SKIPPED_SECTIONS:
                current = None
            else:
                sections.setdefault(current, [])
            continue
        if current is None or classes & SKIPPED_BLOCKS:
            continue
        if classes & {"mw-heading3", "mw-heading4"} or child.name in ("h3", "h4"):
            heading = " ".join(child.get_text(" ", strip=True).split())
            if heading:
                sections[current].append(f"**{heading}**")
            continue
        sections[current].extend(to_lines(render_child(child, md=True)))
    return {name: lines for name, lines in sections.items() if lines}


def parse_debuts(soup):
    """Each 'Previous / Current / Next Debut' table on the page."""
    debuts = []
    for table in soup.select("table.succession-table"):
        head = table.select_one("th .debut-big")
        small = table.select_one("th .debut-small")
        cells = []
        for row in table.select("tr"):
            tds = row.find_all("td", recursive=False)
            if tds:
                cells = tds
        entry = {
            "title": " ".join(render(head).split()) if head else "",
            "dates": " ".join(small.get_text(" ", strip=True).split()) if small else "",
        }
        for key, cell in zip(("previous", "current", "next"), cells):
            wave = cell.select_one(".debut-small")
            wave_text = " ".join(wave.get_text(" ", strip=True).split()) if wave else ""
            copy = BeautifulSoup(str(cell), "lxml")
            for node in copy.select(".debut-small"):
                node.decompose()
            name = " ".join(copy.get_text(" ", strip=True).split())
            if name:
                entry[key] = {"name": name, "wave": wave_text}
        if entry["title"]:
            debuts.append(entry)
    return debuts


def parse_notice(soup):
    notice = soup.select_one(".mw-parser-output div.notice")
    if notice is None:
        return {}
    head = notice.select_one(".notice-head")
    body = notice.select_one(".notice-body b")
    return {
        "type": label_text(head),
        "text": " ".join(render(body).split()) if body else "",
    }


def parse_enemy(path, page):
    """Parse a cached enemy page into a dict. Returns None if the file is missing or unreadable."""
    path = Path(path)
    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"  ! Could not read {path.name}: {error}")
        return None

    try:
        soup = BeautifulSoup(html, "lxml")
        infobox = parse_infobox(soup)
        if not infobox["variants"]:
            print(f"  ! No stats found on {page}")

        description_tag = soup.select_one("meta[name='description']")
        image_tag = soup.select_one("meta[property='og:image']")
        return {
            "slug": slug(page),
            "name": infobox["name"] or page.replace("_", " "),
            "url": f"{BASE_URL}/w/{page}",
            "image": image_tag.get("content", "").split("?", 1)[0] if image_tag else "",
            "description": " ".join(description_tag.get("content", "").split()) if description_tag else "",
            "notice": parse_notice(soup),
            "mode_appearance": infobox["mode_appearance"],
            "wave_debut": infobox["wave_debut"],
            "variants": infobox["variants"],
            "extra": infobox["extra"],
            "sections": parse_sections(soup),
            "debuts": parse_debuts(soup),
        }
    except Exception as error:  # malformed HTML shouldn't kill a whole batch run
        print(f"  ! Failed to parse {page}: {error}")
        return None


# ---------------------------------------------------------------------------
# Index + downloads
# ---------------------------------------------------------------------------

def has_enemy_image(anchor):
    """Enemy links are shown with a sprite; mode/map/attribute links are plain text."""
    if anchor.find("img"):
        return True
    # Text of the link is the raw path (image didn't render as text), e.g. "/w/Normal"
    if anchor.get_text(strip=True).startswith("/w/"):
        return True
    # An adjacent link pointing at the image file (sprite + file link pair)
    for sibling in (anchor.find_next_sibling("a"), anchor.find_previous_sibling("a")):
        if sibling and sibling.get("href", "").lower().endswith(IMAGE_EXTS):
            return True
    return False


def enemy_links(soup):
    """Return unique enemy pages from every tab/sub-tab, keeping only links that have an enemy image."""
    links = {}
    roots = soup.select(".tabber__panel") or [soup]
    for root in roots:
        for anchor in root.select("a[href^='/w/']"):
            page = unquote(urlsplit(anchor["href"]).path.removeprefix("/w/"))
            if not page or ":" in page or "/" in page:
                continue
            if not has_enemy_image(anchor):
                continue
            name = page.replace("_", " ")
            links.setdefault(page, (name, f"{BASE_URL}/w/{page}"))
    return links


def download_enemies(session=None, force_refresh=False, offline=False):
    """Fetch (or load from cache) the enemies index page and return its enemy links."""
    if INDEX_CACHE_FILE.exists() and (offline or not force_refresh):
        print(f"Using cached index: {INDEX_CACHE_FILE}")
    elif offline:
        raise SystemExit(f"--parse-only needs {INDEX_CACHE_FILE}; run once without it first.")
    else:
        print(f"Downloading index: {ENEMIES_URL}")
        download(ENEMIES_URL, INDEX_CACHE_FILE, session)

    soup = BeautifulSoup(INDEX_CACHE_FILE.read_text(encoding="utf-8"), "lxml")
    return enemy_links(soup)


def download_enemy_pages(links, session=None, force_refresh=False):
    """Download individual HTML pages for each enemy."""
    ENEMY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    failed = []

    for page_name, (display_name, url) in links.items():
        html_path = ENEMY_CACHE_DIR / f"{slug(page_name)}.html"

        if html_path.exists() and not force_refresh:
            print(f"Cached: {display_name}")
            continue

        print(f"Downloading: {display_name}")
        try:
            download(url, html_path, session)
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else None
            if status == 404:
                print(f"  ! 404 Not found: {display_name}")
            else:
                print(f"  ! Error downloading {display_name}: {error}")
            failed.append(display_name)
        except requests.RequestException as error:
            print(f"  ! Network error for {display_name}: {error}")
            failed.append(display_name)

    ok = len(links) - len(failed)
    print(f"Downloaded/cached {ok}/{len(links)} enemy pages in {ENEMY_CACHE_DIR}")
    if failed:
        print(f"Failed: {', '.join(failed)}")


def build_enemy_data(links):
    """Parse every cached page into {slug: enemy}, sorted by name."""
    enemies = {}
    for page_name, (display_name, _url) in links.items():
        html_path = ENEMY_CACHE_DIR / f"{slug(page_name)}.html"
        if not html_path.exists():
            print(f"Skipping {display_name}: no cached page")
            continue
        enemy = parse_enemy(html_path, page_name)
        if enemy:
            enemies[enemy["slug"]] = enemy
    return dict(sorted(enemies.items(), key=lambda item: item[1]["name"].lower()))


def write_enemy_data(enemies, path=ENEMY_DATA_FILE):
    """One enemy per line: compact for the worker, still easy to diff."""
    lines = [
        f"{json.dumps(key, ensure_ascii=False)}:{json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
        for key, value in enemies.items()
    ]
    Path(path).write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Scrape enemy pages from tds.wiki into enemies.json")
    parser.add_argument(
        "--force-refresh", action="store_true",
        help="ignore cached files and re-download the index and every enemy page",
    )
    parser.add_argument(
        "--parse-only", action="store_true",
        help="no network: rebuild enemies.json from the cached index and pages",
    )
    args = parser.parse_args()

    if args.parse_only:
        links = download_enemies(offline=True)
    else:
        with requests.Session() as session:
            links = download_enemies(session, args.force_refresh)
            print()
            download_enemy_pages(links, session, args.force_refresh)

    print()
    enemies = build_enemy_data(links)
    write_enemy_data(enemies)
    print(f"Wrote {len(enemies)} enemies to {ENEMY_DATA_FILE}")


if __name__ == "__main__":
    main()
