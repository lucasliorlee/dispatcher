# might get 403 and that's from cloudflare
# unfortunately you can't do much about that other than using a proxy / cookies
# I just run this from my local computer

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://tds.wiki"
PROJECT_DIR = Path(__file__).resolve().parent
TOWER_CACHE_DIR = PROJECT_DIR / "towers"
GALLERY_CACHE_DIR = PROJECT_DIR / "galleries"
SKILLS_CACHE_DIR = PROJECT_DIR / "skills"
TOWER_DATA_FILE = PROJECT_DIR / "towers.json"
SKILLS_DATA_FILE = SKILLS_CACHE_DIR / "skills.json"
SKILLS_URL = f"{BASE_URL}/w/Skills"

towers = [
    "Scout", "Sniper", "Paintballer", "Demoman", "Boomerang", "Slime Trooper", "Soldier",

    "Freezer", "Assassin", "Militant", "Shotgunner", "Hunter", "Pyromancer", "Ace Pilot", "Medic", "Farm", "Electroshocker", "Rocketeer", "Trapper", "Pulse Trooper", "Military Base", "Crook Boss",

    "Commander", "Warden", "Cowboy", "DJ Booth", "Tesla", "Saboteur", "Minigunner", "Ranger", "Pursuit", "Gatling Gun", "Turret", "Mortar", "Mercenary Base",

    "Brawler", "Necromancer", "Accelerator", "Engineer", "Hacker",

    "Operator", "Enforcer", "Kingpin", "Juggernaut",

    "Golden Minigunner", "Golden Pyromancer", "Golden Crook Boss", "Golden Scout", "Golden Cowboy", "Golden Soldier", "Golden Demoman", "Golden Snowballer",

    "Gladiator", "Commando", "Slasher", "Frost Blaster", "Archer", "Swarmer", "Toxic Gunner", "Sledger", "Executioner", "Elf Camp", "Jester", "Cryomancer", "Hallow Punk", "Harvester", "Snowballer", "Elementalist", "Firework Technician", "Biologist", "Warlock", "Spotlight Tech",

    "War Machine", "Mecha Base",

    "Mine", "Sentry", "Moderator", "Railgunner", "Twitgunner", "Void Miner", "Combatant", "Crystallizer", "Time Dilator"
]

MODE_KEYS = {
    "basecost", "basesellingprice", "basedamage", "damagetype", "basefirerate", "baserange",
    "basespawnrate", "baseincome", "hidden_detection", "lead_detection", "flying_detection",
    "immune", "footprint",
}
SKIP_KEYS = {"title", "image", "image-static", "image-dynamic", "music-1"}


# Currencies are shown on the wiki only as icons (<span title="Coin"><img></span>), so plain text
# extraction would drop them and leave a bare "4,000". Cash already prints its own "$".
CURRENCIES = {"Coin": "Coins", "Gem": "Gems", "Robux": "Robux"}
CURRENCY_RE = re.compile(r"\{(" + "|".join(CURRENCIES) + r")\}\s*(\d[\d,.]*)")


def mark_currencies(soup):
    """Replace currency icons with a {Coin}/{Gem}/{Robux} marker that norm() turns into '4,000 Coins'."""
    for icon in soup.select("span[typeof='mw:File']"):
        title = icon.find("span", title=True)
        name = title["title"] if title else ""
        if name in CURRENCIES:
            icon.replace_with(f"{{{name}}}")


def norm(text):
    """Collapse whitespace, drop footnote markers like [3], tidy spacing around brackets."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\[\s*\d+\s*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = CURRENCY_RE.sub(lambda m: f"{m.group(2)} {CURRENCIES[m.group(1)]}", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\s+([,.;:%])", r"\1", text)
    return text


def cell_text(el):
    return norm(el.get_text(" ", strip=True))


def panel_names(el):
    """Names of the tab panels (outermost first) that contain `el`, e.g. ['Regular', 'Top Path']."""
    names = []
    for panel in reversed(el.find_parents(class_="tabber__panel")):
        label_id = panel.get("aria-labelledby")
        label = panel.find_previous(id=label_id) if label_id else None
        name = cell_text(label) if label else re.sub(r"^tabber-", "", panel.get("id", "")).replace("_", " ").strip()
        names.append("PvP" if name.upper() == "PVP" else name)
    return names


def mode_and_path(el):
    """Regular / PvP / Levels / Brawler ... and Top Path / Bottom Path / None."""
    mode, path = None, None
    for name in panel_names(el):
        if name.endswith("Path"):
            path = name
        elif mode is None:
            mode = name
    return mode or "Regular", path


def image_url(el):
    """Direct image URL inside `el`.

    The first <a> in a wiki figure points at the File: *page* (/w/File:X.png), not the image.
    The real file is in the hidden a.mw-file-source link; fall back to un-thumbnailing the <img>.
    """
    if el is None:
        return ""
    source = el.select_one("a.mw-file-source[href^='/images/']")
    if source:
        return BASE_URL + source["href"]
    img = el.find("img")
    if img and img.get("src"):
        src = img["src"].split("?")[0]
        thumb = re.match(r"(/images)/thumb/(.+?\.\w+)/[^/]+$", src)
        return BASE_URL + (f"{thumb.group(1)}/{thumb.group(2)}" if thumb else src)
    return ""


def parse_infobox(soup):
    info = {"general": {}, "regular": {}, "pvp": {}, "tooltips": []}
    box = soup.select_one("aside.portable-infobox")
    if box is None:
        return info
    for item in box.select("[data-source]"):
        key = item["data-source"]
        if key in SKIP_KEYS:
            continue
        value_el = item.select_one(".pi-data-value") or item
        value = cell_text(value_el)
        if key.startswith("tooltip"):
            if value:
                info["tooltips"].append(value)
            continue
        label_el = item.select_one(".pi-data-label")
        label = cell_text(label_el) if label_el else key
        if not value:
            continue
        if key.startswith("pvp_"):
            info["pvp"][label] = value
        elif key in MODE_KEYS:
            info["regular"][label] = value
        else:
            info["general"][label] = value
    return info


def parse_box(box):
    subtitle = box.select_one(".upgrade-subtitle")
    title_el = box.select_one(".upgrade-title")
    if subtitle is None or title_el is None:
        return None
    parts = [p.strip() for p in cell_text(subtitle).split("•")]
    match = re.match(r"Level\s+(\d+)([A-Za-z]?)(\+?)", parts[0])
    if not match:
        return None

    cost, extra, evolution = "", [], ""
    for part in parts[1:]:
        low = part.lower()
        if low.startswith("cost:"):
            cost = part[5:].strip().split(" - ")[-1].strip()  # "Warrior Armor - $250" -> "$250"
        elif part.startswith("$"):
            cost = part
        elif low.startswith("evolution level"):
            evolution = part.split(":", 1)[-1].strip()
        elif part:
            extra.append(part)  # cooldowns etc.
    if cost.lower() == "$unknown":
        cost = "Unknown"

    image = image_url(box.select_one(".upgrade-image-wrapper"))
    info_el = box.select_one(".upgrade-info-content")
    lines = []
    if info_el:
        paragraphs = info_el.find_all("p") or [info_el]
        lines = [t for t in (cell_text(p) for p in paragraphs) if t]

    return {
        "level": int(match.group(1)),
        "tag": match.group(1) + match.group(2) + match.group(3),  # "5", "5A+", "4+"
        "name": norm("".join(title_el.find_all(string=True, recursive=False))),
        "cost": cost,
        "evolution_level": evolution,
        # Abilities (Reposition, Toggle Reverse, ...) show up as boxes with a cooldown in the subtitle
        "ability": any("cooldown" in p.lower() for p in parts),
        "extra": extra,
        "description": lines,
        "image": image,
    }


def parse_upgrades(soup, name, info):
    # Upgrade boxes live in the "Upgrades" section, but abilities (Reposition, Toggle...) sit under
    # their own heading, so take every upgrade box on the page (they all have a Level subtitle).
    entries = []
    for box in soup.select("div.box"):
        entry = parse_box(box)
        if entry:
            entry["mode"], entry["path"] = mode_and_path(box)
            entries.append(entry)

    og_image = soup.find("meta", property="og:image")
    icon = og_image["content"].split("?")[0] if og_image else ""

    # Level 0 = the base tower, one per mode
    modes = list(dict.fromkeys(e["mode"] for e in entries if not e["ability"])) or ["Regular"]
    for mode in reversed(modes):
        source = info["pvp"] if mode == "PvP" else info["regular"]
        entries.insert(0, {
            "level": 0, "tag": "0", "name": name, "cost": source.get("Base Cost", ""),
            "evolution_level": "", "ability": False, "extra": [], "description": [],
            "image": icon, "mode": mode, "path": None,
        })
    return entries


def row_cells(tr):
    return [cell_text(c) for c in tr.find_all(["th", "td"])]


def parse_tables(soup, name):
    tables = []
    for table in soup.select("table.stats-table"):
        trs = table.find_all("tr")
        if not trs:
            continue
        first = trs[0].find_all(["th", "td"])
        if len(first) == 1:
            # Title row spanning the whole table; the real header row follows it
            title = cell_text(first[0])
            trs = trs[1:]
        else:
            title = ""
        if not trs:
            continue
        headers = row_cells(trs[0])
        rows = [r for r in (row_cells(tr) for tr in trs[1:]) if any(r)]
        if not title:
            title = "Stats" if headers[0] == "Level" else headers[0]
        mode, path = mode_and_path(table)
        if mode == "Levels": # redundant info
            continue # cause it's the same for everything
        title_path = re.search(r"(Top|Bottom) Path", title)
        tables.append({
            "mode": mode,
            "title": title,
            "path": title_path.group(0) if title_path else path,
            "headers": headers,
            "rows": rows,
            # tables with a Level + Cost column can be matched against the upgrade names/images
            "linked": headers[:1] == ["Level"] and any(h.startswith("Cost") for h in headers),
        })
    return tables


ICON_TITLES = {"Cash", "Coin", "Gem", "Robux", "Experience", "Corruption"}  # currency icons, not gallery art
MIN_IMAGE_SIDE = 64  # skip tiny inline icons


def full_image_url(img):
    """Un-thumbnail an <img> to the original file (handles lazy-loaded images too)."""
    src = ""
    for attr in ("data-src", "src"):
        value = img.get(attr, "")
        if value and not value.startswith("data:"):
            src = value
            break
    if not src:
        return ""
    src = src.split("?")[0]
    thumb = re.match(r"(/images)/thumb/(.+?\.\w+)/[^/]+$", src)
    src = f"{thumb.group(1)}/{thumb.group(2)}" if thumb else src
    return src if src.startswith("http") else BASE_URL + src


def gallery_caption(img):
    """Caption of a gallery image: gallery text / figcaption / thumb caption, else the alt text."""
    for parent in img.parents:
        classes = " ".join(parent.get("class") or [])
        if parent.name in ("figure", "li") or "gallerybox" in classes or "thumb" in classes.split():
            cap = parent.select_one(".gallerytext, figcaption, .thumbcaption, .lightbox-caption")
            if cap:
                return cell_text(cap)
    return norm(img.get("alt", ""))


def parse_gallery(path):
    """All pictures on a tower's Gallery page as [{section, panel, caption, image}].

    section = the nearest heading above the picture (e.g. "Skins", "Red"), panel = the tab it sits
    in when the page uses tabs (e.g. a skin name). Pages that don't exist are cached as empty files.
    """
    html = Path(path).read_text(encoding="utf-8")
    if not html.strip():
        return []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for sup in soup.select("sup.reference"):
        sup.decompose()
    mark_currencies(soup)  # captions like "Red Scout - 500 Coins"

    root = soup.select_one("#mw-content-text .mw-parser-output") or soup.select_one(".mw-parser-output") or soup
    items, seen, section = [], set(), ""
    for el in root.find_all(["h2", "h3", "h4", "img"]):
        if el.name != "img":
            section = norm(el.get_text(" ", strip=True)).replace("[edit]", "").strip() or section
            continue
        if el.find_parent("span", title=lambda t: t in ICON_TITLES):
            continue
        # Skip small inline icons (the wiki provides the real size as data-file-width/height)
        try:
            side = min(int(el.get("data-file-width") or 9999), int(el.get("data-file-height") or 9999))
        except ValueError:
            side = 9999
        if side < MIN_IMAGE_SIDE:
            continue
        url = full_image_url(el)
        panels = panel_names(el)
        key = (section, url)
        if not url or key in seen:
            continue
        seen.add(key)
        items.append({
            "section": section,
            "panel": " / ".join(panels),
            "caption": gallery_caption(el),
            "image": url,
        })
    return items


def download_gallery(tower, path):
    """Save /w/<Tower>/Gallery. A 404 means the tower has no gallery: cache an empty file so we don't retry."""
    url = f"{BASE_URL}/w/{tower.replace(' ', '_')}/Gallery"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    if response.status_code == 404:
        Path(path).write_text("", encoding="utf-8")
        return
    response.raise_for_status()
    Path(path).write_text(response.text, encoding="utf-8")


def slug(tower):
    return tower.lower().replace(" ", "_")


def download(url, path):
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    if response.headers.get("cf-mitigated") == "challenge" or re.search(
        r"<title>\s*Just a moment", response.text[:2048], re.IGNORECASE
    ):
        raise requests.HTTPError(f"Cloudflare challenge blocked {url}", response=response)
    response.raise_for_status()
    Path(path).write_text(response.text, encoding="utf-8")


def parse_tower(tower, path):
    try:
        soup = BeautifulSoup(Path(path).read_text(encoding="utf-8"), "lxml")
    except Exception:
        soup = BeautifulSoup(Path(path).read_text(encoding="utf-8"), "html.parser")
    for sup in soup.select("sup.reference"):  # footnote markers
        sup.decompose()
    mark_currencies(soup)

    info = parse_infobox(soup)
    og_image = soup.find("meta", property="og:image")
    return {
        "name": tower,
        "url": f"{BASE_URL}/w/{tower.replace(' ', '_')}",
        "image": og_image["content"].split("?")[0] if og_image else "",
        "info": info,
        "upgrades": parse_upgrades(soup, tower, info),
        "tables": parse_tables(soup, tower),
    }


SKILL_CATEGORY_MAP = {
    "skill-off": "Offensive",
    "skill-eco": "Economy",
    "skill-str": "Strategy",
    "skill-def": "Defense",
}


def clean_skill_text(text):
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_skill_levels(skill_box, soup):
    versions = {}
    panels = skill_box.select(".tabber__panel")
    if panels:
        version_panels = []
        for panel in panels:
            label = soup.find(id=panel.get("aria-labelledby", ""))
            version = clean_skill_text(label.get_text(" ", strip=True)) if label else "Current"
            version_panels.append((version, panel))
    else:
        cost_list = skill_box.select_one(".skill-collapsible")
        version_panels = [("Current", cost_list)] if cost_list else []

    for version, panel in version_panels:
        levels = []
        running_total = 0
        for item in panel.select("ol > li"):
            text = clean_skill_text(item.get_text(" ", strip=True))
            costs = [
                int(value.replace(",", ""))
                for value in (node.get_text(strip=True) for node in item.select(".coin-text"))
                if value.replace(",", "").isdigit()
            ]
            if not costs:
                continue
            running_total += costs[0]
            entry = {"cost": costs[0], "total_cost": costs[1] if len(costs) > 1 else running_total}
            percent_match = re.search(r"(\d+(?:\.\d+)?)%\s*total\s*increase", text, re.IGNORECASE)
            if percent_match:
                entry["total_increase_percent"] = float(percent_match.group(1))
            if len(costs) > 1:
                running_total = costs[1]
            levels.append(entry)
        if levels:
            versions[version] = levels
    return versions


def clean_numeric(value):
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", value).strip()
    cleaned = cleaned.rstrip(".")
    if cleaned in {"", ".", "-", "-."}:
        return None
    return float(cleaned) if "." in cleaned else int(cleaned)


def parse_skill_page(path):
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8"), "lxml")
    skills = []
    for box in soup.select("div.BasicBackground"):
        classes = set(box.get("class", []))
        skill_type = next((SKILL_CATEGORY_MAP[c] for c in classes if c in SKILL_CATEGORY_MAP), "Unknown")
        header = box.select_one("div.upgradeheader")
        if not header:
            continue
        header_text = clean_skill_text(header.get_text(" ", strip=True))
        name_match = re.match(r"(.+?)\s*-\s*(\d+)\s+Levels?\s*$", header_text)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        max_level = int(name_match.group(2))

        description_paragraph = box.select_one("p")
        description = clean_skill_text(description_paragraph.get_text(" ", strip=True)) if description_paragraph else ""
        unlock_match = re.search(r"requirement of reaching Level\s+(\d+)\s+in\s+(.+?)\s+before it is unlocked", description, re.IGNORECASE)
        unlock_requirement = None
        if unlock_match:
            unlock_requirement = {
                "level": int(unlock_match.group(1)),
                "skill": unlock_match.group(2).strip(),
            }

        body_text = clean_skill_text(box.get_text(" ", strip=True))
        base_cost_match = re.search(r"base cost of\s+(\d[\d,]*)", body_text, re.IGNORECASE)
        exponential_match = re.search(r"exponential value of\s+([\d.]+)", body_text, re.IGNORECASE)
        exponential_value = clean_numeric(exponential_match.group(1)) if exponential_match else None

        skill = {
            "name": name,
            "category": skill_type,
            "max_level": max_level,
            "description": description,
            "image": "",
            "unlock_requirement": unlock_requirement,
            "base_cost": int(base_cost_match.group(1).replace(",", "")) if base_cost_match else None,
            "exponential_value": exponential_value,
            "levels": [],
            "versions": parse_skill_levels(box, soup),
        }
        skill["levels"] = skill["versions"].get("Current", next(iter(skill["versions"].values()), []))

        image_anchor = box.select_one("figure a.mw-file-description")
        if image_anchor and image_anchor.get("href"):
            href = image_anchor["href"]
            if href.startswith("/w/File:"):
                filename = href.removeprefix("/w/File:")
                skill["image"] = f"{BASE_URL}/w/Special:FilePath/{filename}"
            elif href.startswith("/images/"):
                skill["image"] = f"{BASE_URL}{href}"
        skills.append(skill)

    return {"skills": skills}


if __name__ == "__main__":
    TOWER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    GALLERY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    for tower in towers:
        html_path = TOWER_CACHE_DIR / f"{slug(tower)}.html"
        if html_path.exists():
            print(f"Cached: {tower}")
        else:
            print(f"Downloading: {tower}")
            download(f"{BASE_URL}/w/{tower.replace(' ', '_')}", html_path)
        data[slug(tower)] = parse_tower(tower, html_path)

        gallery_path = GALLERY_CACHE_DIR / f"{slug(tower)}.html"
        if not gallery_path.exists():
            print(f"Downloading gallery: {tower}")
            try:
                download_gallery(tower, gallery_path)
            except requests.RequestException as error:
                print(f"  ! gallery failed for {tower}: {error}")
        data[slug(tower)]["gallery"] = parse_gallery(gallery_path) if gallery_path.exists() else []

    skills_path = SKILLS_CACHE_DIR / "skills.html"
    if skills_path.exists():
        print("Cached: Skills")
    else:
        print("Downloading: Skills")
        try:
            download(SKILLS_URL, skills_path)
        except requests.RequestException as error:
            print(f"  ! skills page failed: {error}")

    if skills_path.exists():
        skills_data = parse_skill_page(skills_path)
        SKILLS_DATA_FILE.write_text(json.dumps(skills_data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Wrote {SKILLS_DATA_FILE}")

    with open(TOWER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"Wrote {TOWER_DATA_FILE}")