import math
import random
import re
from decimal import Decimal, InvalidOperation

from emoji import Emoji


APP_CONTEXTS = [0, 1, 2]
APP_INSTALLS = [0, 1]
MAX_CONTENT = 1900
COMPONENTS_V2 = 1 << 15
CELL_MAX = 150
TABLE_GROUP_LIMIT = 15
CURRENCY_EMOJIS = {
    "coins": Emoji.Coin,
    "gems": Emoji.Gem,
    "robux": Emoji.Robux,
}
CURRENCY_PATTERN = re.compile(r"(?P<amount>\d[\d,]*)\s+(?P<currency>Coins|Gems|Robux)\b", re.IGNORECASE)
STAT_EMOJIS = {
    "Range": Emoji.Range,
    "Firerate": Emoji.Firerate,
    "Damage": Emoji.Damage,
    "Cost": Emoji.Cash,
}
DETECTION_EMOJIS = {
    "Hidden": Emoji.HiddenDetection,
    "Lead": Emoji.LeadDetection,
    "Flying": Emoji.FlyingDetection,
}
IMMUNITY_EMOJIS = {
    "Stun": Emoji.noStun,
    "Freeze": Emoji.noFreeze,
    "Debuff": Emoji.Defense,
}
PRECISION_EXCLUDED_TOWERS = {
    "accelerator", "demoman", "dj_booth", "mortar", "paintballer",
    "rocketeer", "snowballer", "trapper", "brawler", "warden",
}
FIGHT_DIRTY_HEADERS = {
    "Burn Duration", "Burn Time", "Confusion Time", "Debuff Duration",
    "Flashbang Stun Time", "Freeze Time", "Neuralyze Duration", "Poison Time",
    "Shock Time", "Slowdown Time", "Slowness Time", "Sting Time", "Stun Time",
    "Vulnerability Time",
}
GALLERY_HIDDEN = {"Update History", "Contents", "Notes"}
GALLERY_RENAMES = {
    "Skin Upgrades": "Skins",
    "Original Variants": "Previous Variants",
    "Gallery": "Other",
    "Regular Faces": "Faces",
    "Face": "Faces",
}
GALLERY_ORDER = ["Skins", "Previous Variants", "Weapons", "Faces", "Upgrade Icons"]
SKILL_PLAN_TARGETS = (
    ("Stonks", 10),
    ("Scavenger", 10),
    ("Bigger Budget", 25),
    ("Stonks", 20),
    ("Enhanced Optics", 20),
    ("Re-enforcements", 5),
    ("Accelerator", 25),
    ("Fight Dirty", 15),
    ("Improved Gunpowder", 15),
    ("Extreme Conditioning", 25),
    ("Beefed Up Minions", 25),
    ("Expanded Barracks", 10),
    ("Fight Dirty", 25),
    ("Improved Gunpowder", 25),
    ("Expanded Barracks", 20),
    ("Re-enforcements", 8),
    ("Precision", 15),
    ("Re-enforcements", 10),
    ("Scavenger", 20),
    ("Resourcefulness", 25),
    ("Fortify", 40),
    ("Bandages", 25),
    ("Over-Heal", 25),
    ("Scholar", 20),
)
PLAN_OPTIONS = {
    "stonks": "Stonks",
    "scavenger": "Scavenger",
    "bigger_budget": "Bigger Budget",
    "enhanced_optics": "Enhanced Optics",
    "reenforcements": "Re-enforcements",
    "accelerator": "Accelerator",
    "fight_dirty": "Fight Dirty",
    "improved_gunpowder": "Improved Gunpowder",
    "extreme_conditioning": "Extreme Conditioning",
    "beefed_up_minions": "Beefed Up Minions",
    "expanded_barracks": "Expanded Barracks",
    "precision": "Precision",
    "resourcefulness": "Resourcefulness",
    "fortify": "Fortify",
    "bandages": "Bandages",
    "over_heal": "Over-Heal",
    "scholar": "Scholar",
}


def _option(name, description, option_type, required=False, **extra):
    result = {
        "name": name,
        "description": description,
        "type": option_type,
        "required": required,
    }
    result.update(extra)
    return result


def _command(name, description, options):
    return {
        "name": name,
        "description": description,
        "options": options,
        "integration_types": APP_INSTALLS,
        "contexts": APP_CONTEXTS,
    }


COMMANDS = [
    _command("tower", "Look up a tower's stats", [
        _option("name", "Tower name", 3, True, autocomplete=True),
        _option("page", "Overview, abilities, or a stats table", 3, autocomplete=True),
        _option("include_changes", "Show the upgrade changes for each level", 5),
        _option("include_description", "Include the tower description", 5),
        _option("enhanced_optics", "Enhanced Optics level (0-20)", 4, min_value=0, max_value=20),
        _option("improved_gunpowder", "Improved Gunpowder level (0-25)", 4, min_value=0, max_value=25),
        _option("fight_dirty", "Fight Dirty level (0-25)", 4, min_value=0, max_value=25),
        _option("precision", "Precision level (0-15)", 4, min_value=0, max_value=15),
        _option("accelerator", "Accelerator level (0-25)", 4, min_value=0, max_value=25),
        _option("expanded_barracks", "Expanded Barracks level (0-20)", 4, min_value=0, max_value=20),
        _option("beefed_up_minions", "Beefed Up Minions level (0-25)", 4, min_value=0, max_value=25),
        _option("firerate_buff", "Percent bonus (15 means +15%)", 4, min_value=0, max_value=1000),
        _option("range_buff", "Percent bonus (15 means +15%)", 4, min_value=0, max_value=1000),
        _option("damage_buff", "Percent bonus (15 means +15%)", 4, min_value=0, max_value=1000),
    ]),
    _command("skill", "Calculate the coin cost to level a skill", [
        _option("name", "Skill name", 3, True, autocomplete=True),
        _option("current_level", "Your current skill level", 4, min_value=0),
        _option("target_level", "Target skill level; defaults to max", 4, min_value=0),
        _option("levels", "Number of levels to add to your current level", 4, min_value=0),
        _option("version", "Skill cost version", 3, choices=[
            {"name": "Current", "value": "Current"},
            {"name": "Version 1", "value": "Version 1"},
        ]),
    ]),
    _command("plan", "Suggest skill upgrades and route cost", [
        _option("coins", "Optional coin balance for a spending plan", 4, min_value=0, max_value=100000000),
        *[
            _option(name, f"Current {label} level", 4, min_value=0)
            for name, label in PLAN_OPTIONS.items()
        ],
    ]),
    _command("gallery", "Browse a tower's skins, weapons, and other art", [
        _option("name", "Tower name", 3, True, autocomplete=True),
        _option("section", "Gallery section", 3, autocomplete=True),
        _option("entry", "Gallery entry", 3, autocomplete=True),
    ]),
    _command("loadout", "Generate a random loadout", [
        _option("remove", "Comma-separated tower names to exclude", 3, autocomplete=True),
    ]),
]


def _text_display(content):
    content = re.sub(r"\n{3,}", "\n\n", str(content)).strip()
    return {"type": 10, "content": content or " "}


def _section(content, image=None):
    if not image:
        return _text_display(content)
    section = {"type": 9, "components": [_text_display(content)]}
    section["accessory"] = {
        "type": 11,
        "media": {"url": image},
    }
    return section


def _media_gallery(images):
    return {
        "type": 12,
        "items": [
            {
                "media": {"url": image.get("url", "")},
                **({"description": image["description"]} if image.get("description") else {}),
            }
            for image in images
            if image.get("url")
        ],
    }


def _select(custom_id, placeholder, options):
    return {
        "type": 3,
        "custom_id": custom_id,
        "placeholder": placeholder,
        "options": options[:25],
    }


def _select_option(label, value, default=False, emoji=None):
    option = {"label": str(label)[:100], "value": str(value)[:100], "default": default}
    if emoji:
        option["emoji"] = {"id": str(emoji.value), "name": emoji.name}
    return option


def _action_row(component):
    return {"type": 1, "components": [component]}


def _separator():
    return {"type": 14, "spacing": 2}


def _reply(content, ephemeral=False, embeds=None, children=None):
    content = str(content)
    if len(content) > MAX_CONTENT:
        content = content[: MAX_CONTENT - 30].rstrip() + "\n…response shortened"
    children = list(children or [])
    if embeds and not children:
        thumbnail = next((embed.get("thumbnail", {}).get("url") for embed in embeds if embed.get("thumbnail")), None)
        children.append(_section(content, thumbnail))
        images = [
            {
                "url": embed["image"]["url"],
                "description": embed.get("title", "")[:1024],
            }
            for embed in embeds
            if embed.get("image", {}).get("url")
        ]
        if images:
            children.append(_media_gallery(images))
    elif not children:
        children.append(_text_display(content))
    data = {
        "flags": COMPONENTS_V2 | (64 if ephemeral else 0),
        "components": [{"type": 17, "accent_color": 0x5865F2, "components": children}],
    }
    return {"type": 4, "data": data}


def _options_map(options):
    return {option["name"]: option.get("value") for option in options}


def skill_key(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def find_skill(skills, name):
    query = name.strip().lower()
    exact = next((skill for skill in skills if skill["name"].lower() == query), None)
    return exact or next((skill for skill in skills if query in skill["name"].lower()), None)


def calculate_skill_cost(skill, current_level=0, target_level=None, version="Current"):
    versions = skill.get("versions", {})
    if version not in versions:
        raise ValueError(f"{version} cost data is unavailable for {skill['name']}.")
    levels = versions[version]
    max_level = len(levels)
    current_level = max(0, int(current_level))
    target_level = max_level if target_level is None else max(0, int(target_level))
    if current_level > max_level or target_level > max_level:
        raise ValueError(f"{skill['name']} only goes to level {max_level}.")
    if target_level < current_level:
        raise ValueError("Target level must be greater than or equal to the current level.")
    return sum(level["cost"] for level in levels[current_level:target_level])


def build_skill_plan(skills, current_levels):
    levels = {}
    for skill in skills:
        current = int(current_levels.get(skill["name"], 0))
        max_level = len(skill.get("versions", {}).get("Current", []))
        if current < 0 or current > max_level:
            raise ValueError(f"{skill['name']} level must be between 0 and {max_level}.")
        levels[skill_key(skill["name"])] = current

    skill_lookup = {skill_key(skill["name"]): skill for skill in skills}
    actions = []

    def reach_level(name, target, visiting=()):
        key = skill_key(name)
        if levels.get(key, 0) >= target:
            return
        if key in visiting:
            raise ValueError(f"Circular unlock requirement found for {name}.")
        skill = skill_lookup.get(key)
        skill_levels = skill.get("versions", {}).get("Current", []) if skill else []
        if not skill_levels:
            raise ValueError(f"Current cost data is unavailable for {name}.")
        if target > len(skill_levels):
            raise ValueError(f"{name} only goes to level {len(skill_levels)}.")

        requirement = skill.get("unlock_requirement")
        if requirement and levels.get(skill_key(requirement["skill"]), 0) < requirement["level"]:
            reach_level(requirement["skill"], requirement["level"], (*visiting, key))

        current = levels[key]
        if current < target:
            cost = calculate_skill_cost(skill, current, target)
            actions.append({
                "skill": name,
                "current_level": current,
                "target_level": target,
                "cost": cost,
            })
            levels[key] = target

    for name, target in SKILL_PLAN_TARGETS:
        reach_level(name, target)
    return {"actions": actions, "levels": levels, "total_cost": sum(action["cost"] for action in actions)}


def plan_coin_spending(skills, plan, coin_balance):
    if coin_balance < 0:
        raise ValueError("Coin balance cannot be negative.")
    skill_lookup = {skill_key(skill["name"]): skill for skill in skills}
    remaining = coin_balance
    purchases = []
    next_purchase = None
    for action in plan["actions"]:
        skill = skill_lookup[skill_key(action["skill"])]
        costs = skill["versions"]["Current"]
        current_level = action["current_level"]
        funded_level = current_level
        action_cost = 0
        for level_index in range(current_level, action["target_level"]):
            cost = costs[level_index]["cost"]
            if cost > remaining:
                next_purchase = {
                    "skill": action["skill"],
                    "current_level": funded_level,
                    "target_level": funded_level + 1,
                    "cost": cost,
                }
                break
            remaining -= cost
            action_cost += cost
            funded_level = level_index + 1
        if funded_level > current_level:
            purchases.append({
                "skill": action["skill"],
                "current_level": current_level,
                "target_level": funded_level,
                "cost": action_cost,
            })
        if next_purchase:
            break
    return {
        "purchases": purchases,
        "next_purchase": next_purchase,
        "spent": coin_balance - remaining,
        "unspent": remaining,
    }


def format_skill_plan(plan, skills, coin_balance=None):
    if coin_balance is None:
        lines = ["**Next upgrades (Current):**"] if plan["actions"] else ["**All route goals reached.**"]
        for index, action in enumerate(plan["actions"][:5], 1):
            lines.append(
                f"{index}. {action['skill']}: {action['current_level']} → {action['target_level']} "
                f"({action['cost']:,} Coins)"
            )
        if len(plan["actions"]) > 5:
            lines.append(f"…and {len(plan['actions']) - 5} more steps.")
    else:
        spending = plan_coin_spending(skills, plan, coin_balance)
        lines = [f"**Recommended spending for {coin_balance:,} Coins:**"]
        if spending["purchases"]:
            lines.extend(
                f"{index}. {item['skill']}: {item['current_level']} → {item['target_level']} "
                f"({item['cost']:,} Coins)"
                for index, item in enumerate(spending["purchases"], 1)
            )
        elif spending["next_purchase"]:
            lines.append("Save your coins for the next planned upgrade.")
        if spending["next_purchase"]:
            item = spending["next_purchase"]
            lines.append(
                f"Save {spending['unspent']:,} toward {item['skill']} level {item['target_level']} "
                f"({item['cost']:,} Coins needed)."
            )
        elif spending["unspent"]:
            lines.append(f"Route complete; {spending['unspent']:,} Coins remain unspent.")
        lines.append(f"**Spent:** {spending['spent']:,} Coins")
    lines.append(f"**Coins to finish the route:** {plan['total_cost']:,}")
    return "\n".join(lines)


def _tower_slug(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _tower_pages(tower):
    pages = [("Overview", "overview", None)]
    if any(upgrade.get("ability") for upgrade in tower.get("upgrades", [])):
        pages.append(("Abilities", "abilities", None))
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
    return pages[:25]


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
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


def _format_overview_value(key, value):
    value = str(value)
    if key == "Level Requirement":
        return re.sub(r"\bLevel\b", Emoji.Level.get(), value)
    if key == "Placement Limit":
        return re.sub(
            r"(?<![\w])(?:\d+|∞)(?![\w])",
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


def _format_tower_content(tower, page, include_changes, group=0, include_description=False):
    title, kind, payload = page
    if kind == "overview":
        tower_title = f"[{tower['name']}]({tower['url']})" if tower.get("url") else tower["name"]
        lines = [f"# {tower_title}", f"## {title}"]
    else:
        lines = [f"# {title}"]
    if kind == "overview":
        info = tower.get("info", {})
        general = info.get("general", {})
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


def _tower_children(tower, pages, page_index, group, include_changes, include_description=False):
    page = pages[page_index]
    if page[1] == "table":
        children = [_section(f"# {page[0]}")]
        rows = page[2].get("rows", [])
        group_size = max(1, math.ceil(len(rows) / TABLE_GROUP_LIMIT))
        groups = [rows[index : index + group_size] for index in range(0, len(rows), group_size)]
        shown_rows = groups[group] if groups and group < len(groups) else []
        headers = page[2].get("headers", [])
        for index, row in enumerate(shown_rows):
            upgrade = _tower_upgrade(tower, page[2], row)
            heading = _row_heading(headers, row, upgrade)
            cells = [(header, value) for header, value in zip(headers[1:], row[1:]) if value]
            stat_cells = sorted(
                ((header, value) for header, value in cells if header in STAT_EMOJIS),
                key=lambda item: list(STAT_EMOJIS).index(item[0]),
            )
            stat_line = "  ".join(f"{STAT_EMOJIS[header].get()} {clean(value)}" for header, value in stat_cells)
            other_cells = [f"**{header}:** {clean(value)}" for header, value in cells if header not in STAT_EMOJIS]
            content_lines = [f"### {heading}"]
            if stat_line:
                content_lines.append(stat_line)
            content_lines.extend(other_cells)
            if include_changes and upgrade:
                content_lines.extend(f"> {clean(change, 200)}" for change in upgrade.get("description", []))
            children.extend([_separator(), _section("\n".join(content_lines), upgrade.get("image") if upgrade else None)])
    else:
        image = tower.get("image") if page[1] == "overview" else None
        children = [_section(_format_tower_content(tower, page, include_changes, group, include_description), image)]
    if page[1] == "table":
        rows = page[2].get("rows", [])
        group_size = max(1, math.ceil(len(rows) / TABLE_GROUP_LIMIT))
        groups = [rows[index : index + group_size] for index in range(0, len(rows), group_size)]
        if len(groups) > 1:
            def group_label(level_group):
                first = _row_heading(page[2].get("headers", []), level_group[0], _tower_upgrade(tower, page[2], level_group[0]))
                last = _row_heading(page[2].get("headers", []), level_group[-1], _tower_upgrade(tower, page[2], level_group[-1]))
                return first if first == last else f"{first} … {last}"

            children.append(_action_row(_select(
                f"tower|{_tower_slug(tower['name'])}|group|{page_index},{int(include_changes)},{int(include_description)}",
                "Choose a level range",
                [
                    _select_option(
                        group_label(level_group),
                        index,
                        default=(index == group),
                    )
                    for index, level_group in enumerate(groups)
                ],
            )))
    if len(pages) > 1:
        children.append(_action_row(_select(
            f"tower|{_tower_slug(tower['name'])}|page|{page_index},{int(include_changes)},{int(include_description)}",
            "Choose a page",
            [
                _select_option(
                    name,
                    index,
                    default=(index == page_index),
                    emoji=(
                        Emoji.Ability if kind == "abilities"
                        else Emoji.DamageBuff if kind == "table" and payload.get("mode") == "Regular"
                        else Emoji.Sword if kind == "table" and payload.get("mode") == "PvP"
                        else None
                    ),
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


def _gallery_children(tower, sections, section_index, entry_index):
    section_name, entries = sections[section_index]
    entry_index = max(0, min(entry_index, len(entries) - 1))
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
            f"gallery|{_tower_slug(tower['name'])}|entry|{section_index}",
            f"Choose from {section_name.lower()}",
            [_select_option(item["label"], index, default=(index == entry_index)) for index, item in enumerate(entries)],
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
    lines = [f"**{tower['name']} — {title}**" if kind == "overview" else f"**{title}**"]
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
                label += f" — {upgrade['name']}"
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
        ),
    )


def _handle_skill(options, skills):
    name = str(options.get("name", ""))
    skill = find_skill(skills, name)
    if skill is None:
        return _reply(f"Couldn't find a skill called `{name}`.", ephemeral=True)
    current = int(options.get("current_level", 0))
    target = options.get("target_level")
    levels = int(options.get("levels", 0))
    version = options.get("version", "Current")
    if levels > 0 and target is None:
        target = current + levels
    if target is None:
        target = len(skill.get("versions", {}).get(version, []))
    try:
        total = calculate_skill_cost(skill, current, target, version)
    except ValueError as error:
        return _reply(str(error), ephemeral=True)
    skill_levels = skill["versions"][version][current:target]
    target_label = "max" if target == len(skill["versions"][version]) else str(target)
    description = re.sub(r'^"\s*.*?"\s*', "", skill.get("description", "").strip())
    description = re.sub(r"\s*Has a base cost of\b.*$", "", description)
    lines = [f"**{skill['name']}** ({version})"]
    if description:
        lines.append(description)
    lines.append(f"\n{current} → {target_label} costs **{total:,} Coins**.")
    if skill_levels:
        lines.append("\n**Next level costs:**")
        lines.extend(f"Level {current + index}: {level['cost']:,} Coins" for index, level in enumerate(skill_levels, 1))
    thumbnail = skill.get("image")
    return _reply(
        "\n".join(lines) if not thumbnail else "",
        embeds=[{"thumbnail": {"url": thumbnail}}] if thumbnail else None,
        children=[_section("\n".join(lines), thumbnail)] if thumbnail else None,
    )


def _handle_plan(options, skills):
    current_levels = {
        skill_name: int(options.get(option_name, 0))
        for option_name, skill_name in PLAN_OPTIONS.items()
    }
    try:
        plan = build_skill_plan(skills, current_levels)
        return _reply(format_skill_plan(plan, skills, options.get("coins")))
    except ValueError as error:
        return _reply(str(error), ephemeral=True)


def _handle_gallery(options, towers):
    name = str(options.get("name", ""))
    tower = towers.get(_tower_slug(name))
    if tower is None:
        return _reply(f"Couldn't find a tower called `{name}`.", ephemeral=True)
    sections = _gallery_sections(tower)
    if not sections:
        return _reply(f"{tower['name']} has no gallery images.", ephemeral=True)
    section_name = str(options.get("section", sections[0][0]))
    selected = next((item for item in sections if item[0].lower() == section_name.lower()), None)
    if selected is None:
        return _reply(f"Couldn't find gallery section `{section_name}`.", ephemeral=True)
    _, entries = selected
    entry_name = str(options.get("entry", entries[0]["label"]))
    entry = next((item for item in entries if item["label"].lower() == entry_name.lower()), None)
    if entry is None:
        return _reply(f"Couldn't find gallery entry `{entry_name}` in {section_name}.", ephemeral=True)
    content = f"# {tower['name']} Gallery \n-# {section_name}: {entry['label']}"
    children = [_text_display(content)]
    images = [
        {"url": image["image"], "description": image.get("caption") or entry["label"]}
        for image in entry["images"][:10]
    ]
    if images:
        children.append(_media_gallery(images))
    section_index = next(index for index, item in enumerate(sections) if item[0] == selected[0])
    entry_index = next(index for index, item in enumerate(entries) if item is entry)
    if len(entries) > 1:
        children.append(_action_row(_select(
            f"gallery|{_tower_slug(tower['name'])}|entry|{section_index}",
            f"Choose from {section_name.lower()}",
            [_select_option(item["label"], index, default=(index == entry_index)) for index, item in enumerate(entries)],
        )))
    if len(sections) > 1:
        children.append(_action_row(_select(
            f"gallery|{_tower_slug(tower['name'])}|section|{entry_index}",
            "Choose a section",
            [_select_option(name, index, default=(index == section_index)) for index, (name, _) in enumerate(sections)],
        )))
    return _reply("", children=children)


def _handle_loadout(options, towers):
    removed = {
        _tower_slug(name)
        for name in str(options.get("remove", "")).split(",")
        if name.strip()
    }
    available = [slug for slug in towers if slug not in removed]
    if len(available) < 5:
        return _reply("Not enough towers available to generate a loadout. Remove fewer towers.", ephemeral=True)
    return _reply(", ".join(towers[slug]["name"] for slug in random.sample(available, 5)))


def handle_command(interaction, towers, skills):
    data = interaction.get("data", {})
    options = _options_map(data.get("options", []))
    handlers = {
        "tower": _handle_tower,
        "skill": _handle_skill,
        "plan": _handle_plan,
        "gallery": _handle_gallery,
        "loadout": _handle_loadout,
    }
    handler = handlers.get(data.get("name"))
    if handler is None:
        return _reply("Unknown command.", ephemeral=True)
    return handler(options, skills if data["name"] in {"skill", "plan"} else towers)


def handle_component(interaction, towers):
    data = interaction.get("data", {})
    custom_id = str(data.get("custom_id", ""))
    values = data.get("values", [])
    if not values:
        return _reply("This menu selection is empty.", ephemeral=True)

    parts = custom_id.split("|")
    if len(parts) != 4:
        return _reply("This menu has expired. Run the command again.", ephemeral=True)

    kind, slug, action, state = parts
    tower = towers.get(slug)
    if tower is None:
        return _reply("This tower could not be found. Run the command again.", ephemeral=True)

    try:
        selected = int(values[0])
        state = [int(value) for value in state.split(",")]
    except ValueError:
        return _reply("This menu selection is invalid. Run the command again.", ephemeral=True)

    if kind == "tower" and action == "page":
        pages = _tower_pages(tower)
        if selected >= len(pages):
            return _reply("This page could not be found. Run the command again.", ephemeral=True)
        include_changes = bool(state[1]) if len(state) > 1 else False
        include_description = bool(state[2]) if len(state) > 2 else False
        return _component_update(_tower_children(tower, pages, selected, 0, include_changes, include_description))

    if kind == "tower" and action == "group":
        page_index = state[0]
        include_changes = bool(state[1]) if len(state) > 1 else False
        include_description = bool(state[2]) if len(state) > 2 else False
        pages = _tower_pages(tower)
        if page_index >= len(pages) or pages[page_index][1] != "table":
            return _reply("This table could not be found. Run the command again.", ephemeral=True)
        return _component_update(_tower_children(tower, pages, page_index, selected, include_changes, include_description))

    sections = _gallery_sections(tower)
    if kind == "gallery" and action == "section":
        if selected >= len(sections):
            return _reply("This gallery section could not be found. Run the command again.", ephemeral=True)
        return _component_update(_gallery_children(tower, sections, selected, 0))
    if kind == "gallery" and action == "entry":
        section_index = state[0]
        if section_index >= len(sections) or selected >= len(sections[section_index][1]):
            return _reply("This gallery entry could not be found. Run the command again.", ephemeral=True)
        return _component_update(_gallery_children(tower, sections, section_index, selected))

    return _reply("This menu has expired. Run the command again.", ephemeral=True)


def _choices(names, query, value_for_name=None):
    query = query.lower().strip()
    return [
        {"name": name[:100], "value": (value_for_name(name) if value_for_name else name)[:100]}
        for name in names
        if query in name.lower()
    ][:25]


def handle_autocomplete(interaction, catalog):
    data = interaction.get("data", {})
    command = data.get("name", "")
    options = data.get("options", [])
    focused = next((option for option in options if option.get("focused")), {})
    option_name = focused.get("name")
    query = str(focused.get("value", ""))
    current = _options_map(options)
    choices = []
    towers = catalog.get("towers", [])
    tower_lookup = {tower["slug"]: tower for tower in towers}

    if command in {"tower", "gallery"} and option_name == "name":
        choices = _choices([tower["name"] for tower in towers], query, lambda name: next(tower["slug"] for tower in towers if tower["name"] == name))
    elif command == "tower" and option_name == "page":
        tower = tower_lookup.get(_tower_slug(str(current.get("name", ""))))
        if tower:
            choices = _choices(catalog.get("pages", {}).get(tower["slug"], []), query)
    elif command == "skill" and option_name == "name":
        choices = _choices(catalog.get("skills", []), query)
    elif command == "gallery" and option_name == "section":
        tower = tower_lookup.get(_tower_slug(str(current.get("name", ""))))
        if tower:
            sections = catalog.get("gallery", {}).get(tower["slug"], [])
            choices = _choices([section["name"] for section in sections], query)
    elif command == "gallery" and option_name == "entry":
        tower = tower_lookup.get(_tower_slug(str(current.get("name", ""))))
        section_name = str(current.get("section", ""))
        if tower:
            section = next((
                item for item in catalog.get("gallery", {}).get(tower["slug"], [])
                if item["name"].lower() == section_name.lower()
            ), {})
            choices = _choices(section.get("entries", []), query)
    elif command == "loadout" and option_name == "remove":
        previous, separator, partial = query.rpartition(",")
        entered = {_tower_slug(name) for name in previous.split(",") if name.strip()}
        matches = [
            tower["name"] for tower in towers
            if partial.strip() in tower["name"].lower() and tower["slug"] not in entered
        ][:25]
        choices = [
            {"name": (f"{previous}, {name}" if separator else name)[:100],
             "value": (f"{previous}, {name}" if separator else name)[:100]}
            for name in matches
        ]
    return {"type": 8, "data": {"choices": choices}}