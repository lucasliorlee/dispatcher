import math
import re
from decimal import Decimal, InvalidOperation

from .base import *
from .base import _action_row, _media_gallery, _reply, _section, _select, _select_option, _separator, _text_display
from .skills import *
from .skills import _pack_state, _skill_tree


def _clip(text, limit):
    text = str(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit("\n", 1)[0] if "\n" in text[:limit] else text[: limit - 1]
    return cut.rstrip() + "\nâ€¦"
def _dps_multiplier(header, skill_tree, tower_slug, unit_row=False, row_stats=None):
    multiplier = Decimal(1) + Decimal(skill_tree.get("damage_buff", 0)) / 100
    multiplier *= Decimal(1) + Decimal(skill_tree.get("firerate_buff", 0)) / 100
    precision = skill_tree.get("precision", 0)
    if not precision or unit_row or tower_slug in PRECISION_EXCLUDED_TOWERS:
        return multiplier

    precision_increase = Decimal("0.25") / (29 - precision)
    header_lower = header.lower()
    if tower_slug == "pursuit" and "missile" in header_lower:
        precision_increase = Decimal(0)
    elif tower_slug == "pursuit" and "total dps" in header_lower:
        components = row_stats or {}
        eligible_dps = sum(
            (Decimal(raw.replace(",", "").strip()) for name, raw in components.items()
             if "dps" in name.lower() and "total dps" not in name.lower() and "missile" not in name.lower()
             and raw.replace(",", "").strip().replace(".", "", 1).isdigit()),
            Decimal(0),
        )
        base_dps = Decimal(row_stats.get(header, "0").replace(",", "").strip()) if row_stats else Decimal(0)
        if base_dps:
            precision_increase *= eligible_dps / base_dps
    return multiplier * (Decimal(1) + precision_increase)


def _adjusted_stat(header, value, skill_tree, tower_slug, unit_row=False, row_stats=None):
    value = str(value)
    is_cost_efficiency = "cost efficiency" in header.lower()
    numeric_value = value.replace("$", "") if is_cost_efficiency else value

    try:
        number = Decimal(numeric_value.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return value

    enhanced_optics = skill_tree.get("enhanced_optics", 0)
    improved_gunpowder = skill_tree.get("improved_gunpowder", 0)
    fight_dirty = skill_tree.get("fight_dirty", 0)
    accelerator = skill_tree.get("accelerator", 0)
    expanded_barracks = skill_tree.get("expanded_barracks", 0)
    beefed_up_minions = skill_tree.get("beefed_up_minions", 0)
    damage_buff = skill_tree.get("damage_buff", 0)
    range_buff = skill_tree.get("range_buff", 0)
    firerate_buff = skill_tree.get("firerate_buff", 0)

    skill_factor = Decimal(1)
    buff_factor = Decimal(1)
    header_lower = header.lower()

    if header == "Range" and not unit_row:
        skill_factor *= Decimal(1) + Decimal("0.005") * enhanced_optics
        buff_factor *= Decimal(1) + Decimal(range_buff) / 100
    elif (
        not unit_row
        and ("explosion" in header_lower or header in {"Flashbang Radius", "Neuralyze Grenade Radius", "Smite Radius"})
        and ("range" in header_lower or "radius" in header_lower)
    ):
        skill_factor *= Decimal(1) + Decimal("0.005") * improved_gunpowder

    if header in FIGHT_DIRTY_HEADERS:
        skill_factor *= Decimal(1) + Decimal("0.01") * fight_dirty
    if header == "Ability Cooldown":
        skill_factor *= Decimal(1) - Decimal("0.005") * accelerator
    if header == "Spawnrate":
        skill_factor *= Decimal(1) - Decimal("0.0075") * expanded_barracks
    if (header == "Health" and unit_row) or header == "Combined Total Health":
        skill_factor *= Decimal(1) + Decimal("0.006") * beefed_up_minions

    excluded_damage = ("damage buff", "damage taken bonus", "damage vulnerability", "damage threshold")
    if "damage" in header_lower and "buff" not in header_lower and not any(term in header_lower for term in excluded_damage):
        buff_factor *= Decimal(1) + Decimal(damage_buff) / 100

    if "firerate" in header_lower and "buff" not in header_lower:
        buff_factor *= Decimal(1) + Decimal(firerate_buff) / 100
        result = number / (skill_factor * buff_factor)
    elif is_cost_efficiency:
        result = number / _dps_multiplier(header, skill_tree, tower_slug, unit_row, row_stats)
    elif "dps" in header_lower:
        result = number * skill_factor * _dps_multiplier(header, skill_tree, tower_slug, unit_row, row_stats)
    else:
        result = number * skill_factor * buff_factor

    if result == number:
        return value
    formatted = f"{result:,.4f}".rstrip("0").rstrip(".")
    return f"${formatted}" if is_cost_efficiency and value.strip().startswith("$") else formatted


def _render_stat_changes(skill_tree, tower_slug=""):
    active_skills = [
        f"{emoji.get()} {skill_tree[key]}"
        for key, emoji in SKILL_LABELS
        if skill_tree.get(key, 0)
    ]
    active_buffs = [
        f"+{skill_tree[key]}% {emoji.get()}"
        for key, emoji in (
            ("firerate_buff", Emoji.FirerateBuff),
            ("range_buff", Emoji.RangeBuff),
            ("damage_buff", Emoji.DamageBuff),
        )
        if skill_tree.get(key, 0)
    ]
    level_bonuses = (
        ("enhanced_optics", Decimal("0.5"), Emoji.EnhancedOpticsSkill),
        ("improved_gunpowder", Decimal("0.5"), Emoji.ImprovedGunpowderSkill),
        ("fight_dirty", Decimal(1), Emoji.FightDirtySkill),
        ("accelerator", Decimal("-0.5"), Emoji.AcceleratorSkill),
        ("expanded_barracks", Decimal("-0.75"), Emoji.ExpandedBarracksSkill),
        ("beefed_up_minions", Decimal("0.6"), Emoji.BeefedUpMinionsSkill),
    )
    skill_bonuses = []
    for key, per_level, emoji in level_bonuses:
        level = skill_tree.get(key, 0)
        if level:
            amount = per_level * level
            formatted = format(amount, "f")
            if "." in formatted:
                formatted = formatted.rstrip("0").rstrip(".")
            sign = "+" if amount > 0 else ""
            skill_bonuses.append(f"{sign}{formatted}% {emoji.get()}")
    precision = skill_tree.get("precision", 0)
    if precision and tower_slug not in PRECISION_EXCLUDED_TOWERS:
        skill_bonuses.append(
            f"1 in {29 - precision} attacks: 1.25Ã— damage {Emoji.PrecisionSkill.get()}"
        )

    if not active_skills and not active_buffs:
        return ""

    lines = ["### Stat changes"]
    if active_skills:
        lines.append("**Skills:** " + ": ".join(active_skills))
    if active_buffs:
        lines.append("**Buffs:** " + ": ".join(active_buffs))
    if skill_bonuses:
        lines.append("**Skill bonuses:** " + ": ".join(skill_bonuses))
    return "\n".join(lines)


def _level_traits(tower, table, level):
    mode = table.get("mode", "Regular")
    base_stats = tower.get("info", {}).get(mode.lower(), {})
    detections = set()
    immunities = set()

    for key, label in (("Hidden Detection", "Hidden"), ("Lead Detection", "Lead"), ("Flying Detection", "Flying")):
        value = str(base_stats.get(key, "")).strip()
        if value and value.lower() not in {"n/a", "unknown"}:
            matches = list(re.finditer(r"\bLevel\s+(\d+)([A-Z])?\+?", value, re.IGNORECASE))
            if matches:
                tower_match = next(
                    (match for index, match in enumerate(matches)
                     if re.search(r"\bTower\b", value[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(value)], re.IGNORECASE)),
                    None,
                )
                match = tower_match or (matches[0] if len(matches) == 1 else None)
                if match:
                    if match.group(2):
                        continue
                    qualifier = value[match.end() : matches[matches.index(match) + 1].start() if matches.index(match) + 1 < len(matches) else len(value)]
                    unit_only = "only" in qualifier.lower() and not re.search(
                        r"\b(Tower|Collision|Splash|Burn|Poison|Bleed|Sting)\b", qualifier, re.IGNORECASE
                    )
                    if level >= int(match.group(1)) and not unit_only:
                        detections.add(label)
            else:
                detections.add(label)

    base_immunities = str(base_stats.get("Immunities", ""))
    immunity_matches = list(re.finditer(r"(Partial\s+)?(Stun|Freeze|Debuff)(?:\s+Immune)?", base_immunities, re.IGNORECASE))
    for index, match in enumerate(immunity_matches):
        tail = base_immunities[match.end() : immunity_matches[index + 1].start() if index + 1 < len(immunity_matches) else len(base_immunities)]
        if "units only" in tail.lower():
            continue
        required_level = re.search(r"\(Level\s*(\d+)", tail, re.IGNORECASE)
        if required_level and level < int(required_level.group(1)):
            continue
        label = f"Partial {match.group(2).title()}" if match.group(1) else match.group(2).title()
        immunities.add(label)

    detection_pattern = re.compile(r"\+\s*(Hidden|Lead|Flying)\s+Detection", re.IGNORECASE)
    immunity_pattern = re.compile(r"\+\s*(Stun|Freeze|Debuff)\s+Immunity", re.IGNORECASE)
    for upgrade in tower.get("upgrades", []):
        if (
            upgrade.get("mode") != mode
            or upgrade.get("path") not in (None, table.get("path"))
            or upgrade.get("ability")
            or upgrade.get("level", level + 1) > level
        ):
            continue
        for change in upgrade.get("description", []):
            detection = detection_pattern.fullmatch(change.strip())
            if detection:
                detections.add(detection.group(1).title())
            immunity = immunity_pattern.fullmatch(change.strip())
            if immunity:
                immunities.add(immunity.group(1).title())

    detection_order = ("Hidden", "Lead", "Flying")
    immunity_order = ("Stun", "Freeze", "Debuff", "Partial Stun", "Partial Freeze", "Partial Debuff")
    return (
        [name for name in detection_order if name in detections],
        [name for name in immunity_order if name in immunities],
    )


def _trait_lines(traits):
    detections, immunities = traits
    detection_icons = [DETECTION_EMOJIS[name].get() for name in detections if name in DETECTION_EMOJIS]
    immunity_icons = [
        ("~" if name.startswith("Partial ") else "") + IMMUNITY_EMOJIS[name.removeprefix("Partial ")].get()
        for name in immunities
        if name.removeprefix("Partial ") in IMMUNITY_EMOJIS
    ]
    return [
        f"**Detections:** {' '.join(detection_icons) or 'None'}",
        f"**Immunities:** {' '.join(immunity_icons) or 'None'}",
    ]


def _emojify_traits(header, value):
    """Unit tables have a plain-text "Detections" column ("Hidden, Flying"); show icons instead."""
    value = str(value)
    if header != "Detections":
        return value
    parts = [part.strip() for part in re.split(r"[,&/]|\band\b", value) if part.strip()]
    icons = [DETECTION_EMOJIS[part.title()].get() for part in parts if part.title() in DETECTION_EMOJIS]
    if not icons:
        return value
    leftovers = [part for part in parts if part.title() not in DETECTION_EMOJIS]
    return " ".join(icons + leftovers)


def _row_content(tower, tower_slug, table, row, include_changes, skill_tree):
    """(text, image) for one table row"""
    headers = table.get("headers", [])
    upgrade = _tower_upgrade(tower, table, row)
    lines = [f"### {clean(_row_heading(headers, row, upgrade))}"]
    is_unit_table = "Unit" in headers
    raw_stats = {header: str(cell) for header, cell in zip(headers[1:], row[1:])}
    cells = [
        (header, _emojify_traits(header, _adjusted_stat(header, cell, skill_tree, tower_slug, is_unit_table, raw_stats)))
        for header, cell in zip(headers[1:], row[1:])
    ]
    stat_cells = sorted(
        ((header, cell) for header, cell in cells if header in STAT_EMOJIS and cell),
        key=lambda item: list(STAT_EMOJIS).index(item[0]),
    )
    if stat_cells:
        lines.append("  ".join(f"{STAT_EMOJIS[header].get()} {clean(cell)}" for header, cell in stat_cells))
    if include_changes and upgrade:
        lines.extend(f"> {clean(change, 200)}" for change in upgrade.get("description", []))
    lines.extend(f"**{clean(header)}:** {clean(cell)}" for header, cell in cells if cell and header not in STAT_EMOJIS)
    has_stats = any(header in STAT_EMOJIS for header in headers)
    if has_stats and row and str(row[0]).isdigit():
        lines.extend(_trait_lines(_level_traits(tower, table, int(row[0]))))
    return "\n".join(lines), (upgrade.get("image") if upgrade else None)


def _tower_slug(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _tower_pages(tower):
    pages = [("Overview", "overview", None)]
    tables = tower.get("tables", [])
    has_pvp = any(table.get("mode") == "PvP" for table in tables)
    for table in tables:
        if table.get("mode") == "Levels":
            continue
        title = table.get("title", "Stats")
        mode = table.get("mode", "Regular")
        if has_pvp and mode in ("Regular", "PvP") and not title.lower().startswith(mode.lower()):
            title = f"{mode} ({title})"
        pages.append((title, "table", table))
    if any(upgrade.get("ability") for upgrade in tower.get("upgrades", [])):
        pages.append(("Abilities", "abilities", None))
    for name, lines in tower.get("sections", {}).items():
        if name not in {"Description", "Skins"} and lines:
            pages.append((name, "section", lines))
    return pages[:25]


def _tower_page_emoji(title, kind, payload):
    if title == "Overview":
        return Emoji.Logbook
    if kind == "table":
        return Emoji.DamageBuff
    return {
        "Strategy": "🏹",
        "Trivia": Emoji.TDSWikiLogo,
        "Update History": Emoji.ScholarSkill,
        "Notes": "📋",
    }.get(title)


def _tower_upgrade(tower, table, row):
    if not table.get("linked") or not row or not str(row[0]).isdigit():
        return None
    mode = table.get("mode", "Regular")
    path = table.get("path")
    return next((
        upgrade for upgrade in tower.get("upgrades", [])
        if upgrade.get("mode") == mode
        and upgrade.get("path") == path
        and not upgrade.get("ability")
        and upgrade.get("level") == int(row[0])
    ), None)


def clean(text, limit=CELL_MAX):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "â€¦"


def _row_heading(headers, row, upgrade=None):
    first = str(row[0]) if row else "?"
    if "Unit" in headers:
        unit_index = headers.index("Unit")
        unit = str(row[unit_index]) if unit_index < len(row) else ""
        if unit:
            first = unit
            label = ""
        else:
            label = headers[0] if headers else ""
    else:
        label = headers[0] if headers else ""
    heading = f"{label} {first}" if first.isdigit() and label else first
    if upgrade and upgrade.get("name"):
        heading += f" ({upgrade['name']})"
    return heading


def _level_label(tower, table, row):
    """Dropdown label for a table row: just the level (upgrade) name, e.g. "Laptop Studio"."""
    upgrade = _tower_upgrade(tower, table, row)
    if upgrade and upgrade.get("name"):
        return upgrade["name"]
    return _row_heading(table.get("headers", []), row)


def _format_overview_value(key, value):
    value = str(value)
    if key == "Level Requirement":
        return re.sub(r"\bLevel\b", Emoji.Level.get(), value)
    if key == "Placement Limit":
        return re.sub(
            r"(?<![\w])(?:\d+|âˆž)(?![\w])",
            lambda match: f"{match.group()} {Emoji.PlacementLimit.get()}",
            value,
        )
    if key == "Evolution Levels":
        return f"{Emoji.Level.get()} {value}"
    if key == "Base Exp":
        return f"{Emoji.Exp.get()} {value}"
    return CURRENCY_PATTERN.sub(
        lambda match: f"{CURRENCY_EMOJIS[match.group('currency').lower()].get()} {match.group('amount')}",
        value,
    )


def _format_tower_content(tower, page, include_changes, group=0, include_description=False, skill_tree=None):
    title, kind, payload = page
    if kind == "section":
        tower_name = f"[{tower['name']}]({tower['url']})" if tower.get("url") else tower["name"]
        heading = "Tips & Strategy" if title == "Strategy" else title
        lines = [f"# {tower_name}", f"## {heading}", "", *payload]
        return _clip("\n".join(lines), TEXT_BUDGET - 100)
    if kind == "overview":
        tower_title = f"[{tower['name']}]({tower['url']})" if tower.get("url") else tower["name"]
        lines = [f"# {tower_title}", f"## {title}"]
    else:
        lines = [f"# {title}"]
    if kind == "overview":
        info = tower.get("info", {})
        general = info.get("general", {})
        descriptions = tower.get("sections", {}).get("Description") or [tower.get("description", "")]
        descriptions = [str(text) for text in descriptions if text]
        if not descriptions:
            descriptions = [str(text) for text in info.get("tooltips", [])]
        if include_description and descriptions:
            lines.extend(["", *descriptions])
        for key in ("Role", "Placement"):
            if general.get(key):
                lines.append(f"**{key}:** {clean(_format_overview_value(key, general[key]))}")
        regular = info.get("regular", {})
        pvp = info.get("pvp", {})
        footprint = regular.get("Placement Footprint", "")
        if pvp.get("Placement Footprint") and pvp["Placement Footprint"] != footprint:
            footprint = f"{footprint} (Regular) / {pvp['Placement Footprint']} (PvP)"
        if footprint:
            lines.append(f"**Placement Footprint:** {clean(footprint)}")
        if general.get("Placement Limit"):
            lines.append(f"**Placement Limit:** {_format_overview_value('Placement Limit', general['Placement Limit'])}")
        details = [
            f"**{key}:** {clean(_format_overview_value(key, value))}"
            for key, value in general.items()
            if key not in {"Description", "Role", "Placement", "Placement Limit"}
        ]
        if details:
            lines.extend(["", "### Details", *details])
        changes = _render_stat_changes(skill_tree or {}, _tower_slug(tower["name"]))
        if changes:
            lines.extend(["", changes])
    elif kind == "abilities":
        for upgrade in (item for item in tower.get("upgrades", []) if item.get("ability")):
            lines.append(f"### {upgrade.get('name', 'Ability')}")
            if upgrade.get("mode") != "Regular":
                lines.append(f"**Mode:** {upgrade.get('mode')}")
            if upgrade.get("cost"):
                lines.append(f"**Cost:** {upgrade['cost']}")
            lines.extend(f"> {clean(change, 200)}" for change in upgrade.get("description", []))
    else:
        headers = payload.get("headers", [])
        rows = payload.get("rows", [])
        group_size = max(1, math.ceil(len(rows) / TABLE_GROUP_LIMIT))
        shown_rows = [rows[index : index + group_size] for index in range(0, len(rows), group_size)]
        rows = shown_rows[group] if shown_rows and group < len(shown_rows) else []
        for row in rows:
            upgrade = _tower_upgrade(tower, payload, row)
            heading = _row_heading(headers, row, upgrade)
            values = [
                f"{STAT_EMOJIS[header].get()} {clean(value)}" if header in STAT_EMOJIS
                else f"**{header}:** {clean(value)}"
                for header, value in zip(headers[1:], row[1:])
                if value
            ]
            lines.append(f"### {heading}")
            lines.extend(values)
            if include_changes and upgrade:
                lines.extend(f"> {clean(change, 200)}" for change in upgrade.get("description", []))
    return "\n".join(lines)


UPDATE_START = re.compile(r"^(?:-\s+)?(?:\*\*)?\d{1,2} [A-Za-z]+ \d{4}(?:\*\*)? - ")


def _update_entries(lines):
    entries = []
    for line in lines:
        if UPDATE_START.match(str(line).strip()):
            entries.append([line])
        elif entries:
            entries[-1].append(line)
    return [entry for entry in entries if entry]


def _update_label(entry):
    first = str(entry[0]).replace("**", "").lstrip("- ").strip()
    return clean(first, 95)


def _history_chunks(entries):
    # Leave room for Previous/Next options in the same Discord select.
    return [entries[index:index + 23] for index in range(0, len(entries), 23)]


def _history_navigation(group, group_count):
    options = []
    if group > 0:
        options.append(_select_option("Previous page", "previous"))
    if group + 1 < group_count:
        options.append(_select_option("Next page", "next"))
    return options


def _paged_options(items, page, label_for):
    chunks = _history_chunks(items)
    page = max(0, min(page, len(chunks) - 1)) if chunks else 0
    options = _history_navigation(page, len(chunks))
    options.extend(
        _select_option(label_for(item), index)
        for index, item in enumerate(chunks[page] if chunks else [])
    )
    return options


def _tower_children(
    tower,
    pages,
    page_index,
    row_index,
    include_changes,
    include_description=False,
    skill_tree=None,
    history_index=0,
    history_group=0,
):
    """Build the message for one tower page. Table pages show a single level, picked from a dropdown."""
    skill_tree = skill_tree or {}
    tower_slug = _tower_slug(tower["name"])
    state = _pack_state(page_index, include_changes, include_description, skill_tree, history_group)
    page = pages[page_index]
    if page[1] == "table":
        table = page[2]
        rows = table.get("rows", [])
        children = [_section(f"# {page[0]}")]
        changes = _render_stat_changes(skill_tree, tower_slug)
        if changes:
            children.append(_section(changes))
        if rows:
            row_index = max(0, min(row_index, len(rows) - 1))
            text, image = _row_content(tower, tower_slug, table, rows[row_index], include_changes, skill_tree)
            children.extend([_separator(), _section(text, image)])
            group = row_index // LEVEL_SELECT_SIZE
            start = group * LEVEL_SELECT_SIZE
            if len(rows) > LEVEL_SELECT_SIZE:
                chunks = [rows[index : index + LEVEL_SELECT_SIZE] for index in range(0, len(rows), LEVEL_SELECT_SIZE)]

                def range_label(chunk):
                    first, last = _level_label(tower, table, chunk[0]), _level_label(tower, table, chunk[-1])
                    return first if first == last else f"{first} â€¦ {last}"

                children.append(_action_row(_select(
                    f"tower|{tower_slug}|group|{state}",
                    "Choose a level range",
                    [
                        _select_option(range_label(chunk), index, default=(index == group))
                        for index, chunk in enumerate(chunks)
                    ],
                )))
            if len(rows) > 1:
                children.append(_action_row(_select(
                    f"tower|{tower_slug}|level|{state}",
                    "Choose a level",
                    [
                        _select_option(
                            _level_label(tower, table, row),
                            start + offset,
                            default=(start + offset == row_index),
                        )
                        for offset, row in enumerate(rows[start : start + LEVEL_SELECT_SIZE])
                    ],
                )))
        else:
            children.append(_section("No rows in this table."))
    else:
        if page[1] == "section" and page[0] == "Update History":
            entries = _update_entries(page[2])
            chunks = _history_chunks(entries)
            history_group = max(0, min(history_group, len(chunks) - 1)) if chunks else 0
            chunk = chunks[history_group] if chunks else []
            history_index = max(0, min(history_index, len(chunk) - 1)) if chunk else 0
            payload = chunk[history_index] if chunk else page[2]
            page = (page[0], page[1], payload)
        image = tower.get("image")
        children = [_section(
            _format_tower_content(tower, page, include_changes, 0, include_description, skill_tree),
            image,
        )]
        if page[1] == "section" and page[0] == "Update History":
            if entries:
                children.append(_action_row(_select(
                    f"tower|{tower_slug}|history|{state}",
                    "Choose an update",
                    _paged_options(entries, history_group, _update_label),
                )))
    if len(pages) > 1:
        children.append(_action_row(_select(
            f"tower|{tower_slug}|page|{state}",
            "Choose a page",
            [
                _select_option(
                    name,
                    index,
                    default=(index == page_index),
                    emoji=_tower_page_emoji(name, kind, payload),
                )
                for index, (name, kind, payload) in enumerate(pages)
            ],
        )))
    return children


def _component_update(children):
    return {
        "type": 7,
        "data": {
            "flags": COMPONENTS_V2,
            "components": [{"type": 17, "accent_color": 0x5865F2, "components": children}],
        },
    }


def _gallery_children(tower, sections, section_index, entry_index, entry_page=0):
    section_name, entries = sections[section_index]
    entry_index = max(0, min(entry_index, len(entries) - 1))
    entry_page = entry_index // 23 if entries else 0
    entry = entries[entry_index]
    children = [_text_display(f"# {tower['name']} Gallery\n-# {section_name}: {clean(entry['label'], 80)}")]
    images = [
        {"url": image["image"], "description": image.get("caption") or entry["label"]}
        for image in entry["images"][:10]
    ]
    if images:
        children.append(_media_gallery(images))
    if len(entries) > 1:
        children.append(_action_row(_select(
            f"gallery|{_tower_slug(tower['name'])}|entry|{section_index},{entry_page}",
            f"Choose a {section_name.lower()} entry",
            _paged_options(entries, entry_page, lambda item: item["label"]),
        )))
    if len(sections) > 1:
        children.append(_action_row(_select(
            f"gallery|{_tower_slug(tower['name'])}|section|{entry_index}",
            "Choose a section",
            [_select_option(name, index, default=(index == section_index)) for index, (name, _) in enumerate(sections)],
        )))
    return children


def _render_tower_page(tower, page, include_changes, include_description=False):
    title, kind, payload = page
    lines = [f"**{tower['name']}: {title}**" if kind == "overview" else f"**{title}**"]
    if kind == "overview":
        info = tower.get("info", {})
        if include_description:
            lines.extend(info.get("tooltips", []))
        general = info.get("general", {})
        for key in ("Role", "Placement", "Unlock Cost", "Level Requirement", "Placement Limit", "Evolution Levels"):
            if general.get(key):
                lines.append(f"**{key}:** {general[key]}")
        for mode in ("regular", "pvp"):
            stats = info.get(mode, {})
            if stats:
                lines.append(f"**{mode.title()} base stats**")
                lines.extend(f"{key}: {value}" for key, value in stats.items())
    elif kind == "abilities":
        abilities = [upgrade for upgrade in tower.get("upgrades", []) if upgrade.get("ability")]
        for upgrade in abilities:
            lines.append(f"**{upgrade.get('name', 'Ability')}** ({upgrade.get('mode', 'Regular')})")
            if upgrade.get("cost"):
                lines.append(f"Cost: {upgrade['cost']}")
            lines.extend(upgrade.get("description", []))
    else:
        headers = payload.get("headers", [])
        for row in payload.get("rows", []):
            upgrade = _tower_upgrade(tower, payload, row)
            label = row[0] if row else "?"
            if upgrade and upgrade.get("name"):
                label += f": {upgrade['name']}"
            values = [f"{header}: {value}" for header, value in zip(headers[1:], row[1:]) if value]
            lines.append(f"**{label}**" + (" | " + " | ".join(values) if values else ""))
            if include_changes and upgrade:
                lines.extend(f"> {change}" for change in upgrade.get("description", []))
    if kind == "overview" and tower.get("url"):
        lines.append(f"[Tower page]({tower['url']})")
    return "\n".join(lines)


def _gallery_sections(tower):
    sections = {}
    for image in tower.get("gallery", []):
        if image.get("section") in GALLERY_HIDDEN or image.get("image", "").endswith("/Transparent.png"):
            continue
        section = GALLERY_RENAMES.get(image.get("section", ""), image.get("section", "")) or "Other"
        entries = sections.setdefault(section, {})
        panel = image.get("panel", "")
        caption = image.get("caption", "")
        key = panel or (f"#{len(entries)}" if caption else "")
        entry = entries.setdefault(key, {"label": panel or caption or section, "images": []})
        entry["images"].append(image)

    def rank(name):
        if name == "Other":
            return len(GALLERY_ORDER) + 1
        return GALLERY_ORDER.index(name) if name in GALLERY_ORDER else len(GALLERY_ORDER)

    return [(name, list(entries.values())) for name, entries in sorted(sections.items(), key=lambda item: rank(item[0]))][:25]


def _handle_tower(options, towers):
    name = str(options.get("name", ""))
    tower = towers.get(_tower_slug(name))
    if tower is None:
        return _reply(f"Couldn't find a tower called `{name}`.", ephemeral=True)
    pages = _tower_pages(tower)
    requested = options.get("page", "Overview")
    page = next((item for item in pages if item[0].lower() == str(requested).lower()), None)
    if page is None:
        return _reply(f"Couldn't find page `{requested}` for {tower['name']}.", ephemeral=True)
    page_index = pages.index(page)
    return _reply(
        "",
        children=_tower_children(
            tower,
            pages,
            page_index,
            0,
            bool(options.get("include_changes", False)),
            bool(options.get("include_description", False)),
            _skill_tree(options),
        ),
    )
