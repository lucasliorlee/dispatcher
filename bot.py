import json
import math
import os
import random
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv

import discord
from discord import app_commands
from discord.ui import ActionRow, Container, LayoutView, MediaGallery, Section, Separator, TextDisplay, Thumbnail

from config import Emoji

PROJECT_DIR = Path(__file__).resolve().parent
TOWER_DATA_FILE = PROJECT_DIR / "towers.json"
SKILLS_DATA_FILE = PROJECT_DIR / "skills" / "skills.json"

with TOWER_DATA_FILE.open(encoding="utf-8") as f:
    DATA = json.load(f)

NAMES = {slug: tower["name"] for slug, tower in DATA.items()}
CELL_MAX = 150
MAX_OPTIONS = 25  # Discord select menus hold at most 25 options
GALLERY_PAGE_SIZE = MAX_OPTIONS - 2  # reserve select options for previous/next navigation

# Shown at the top of the overview, everything else in "general" goes under "Details"
HEADLINE_KEYS = ("Role", "Placement")
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
SKILL_LABELS = (
    ("enhanced_optics", Emoji.EnhancedOpticsSkill),
    ("improved_gunpowder", Emoji.ImprovedGunpowderSkill),
    ("fight_dirty", Emoji.FightDirtySkill),
    ("precision", Emoji.PrecisionSkill),
    ("accelerator", Emoji.AcceleratorSkill),
    ("expanded_barracks", Emoji.ExpandedBarracksSkill),
    ("beefed_up_minions", Emoji.BeefedUpMinionsSkill),
)

with SKILLS_DATA_FILE.open(encoding="utf-8") as f:
    SKILL_DATA = json.load(f)


def skill_key(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


SKILL_LOOKUP = {skill_key(skill["name"]): skill for skill in SKILL_DATA.get("skills", [])}
SKILL_NAMES = [skill["name"] for skill in SKILL_DATA.get("skills", [])]
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


def get_skill(name):
    key = skill_key(name)
    if key in SKILL_LOOKUP:
        return SKILL_LOOKUP[key]
    match = next((skill for skill in SKILL_DATA.get("skills", []) if name.lower() in skill["name"].lower()), None)
    if match:
        SKILL_LOOKUP[skill_key(match["name"])] = match
    return match


def calculate_skill_cost(name, current_level=0, target_level=None, version="Current"):
    skill = get_skill(name)
    if skill is None:
        raise ValueError(f"Couldn't find a skill called `{name}`.")

    versions = skill.get("versions", {})
    if version not in versions:
        raise ValueError(f"{version} cost data is unavailable for {skill['name']}.")
    levels = versions[version]
    max_level = len(levels)
    current_level = max(0, int(current_level))
    if target_level is None:
        target_level = max_level
    target_level = max(0, int(target_level))

    if current_level > max_level or target_level > max_level:
        raise ValueError(f"{skill['name']} only goes to level {max_level}.")
    if target_level < current_level:
        raise ValueError("Target level must be greater than or equal to the current level.")

    return sum(level["cost"] for level in levels[current_level:target_level])


def build_skill_plan(current_levels):
    levels = {}
    for skill in SKILL_DATA.get("skills", []):
        name = skill["name"]
        skill_levels = skill.get("versions", {}).get("Current", [])
        current = int(current_levels.get(name, 0))
        if current < 0 or current > len(skill_levels):
            raise ValueError(f"{name} level must be between 0 and {len(skill_levels)}.")
        levels[skill_key(name)] = current

    actions = []

    def reach_level(name, target, visiting=()):
        key = skill_key(name)
        current = levels.get(key, 0)
        if current >= target:
            return
        if key in visiting:
            raise ValueError(f"Circular unlock requirement found for {name}.")

        skill = get_skill(name)
        if skill is None or not skill.get("versions", {}).get("Current"):
            raise ValueError(f"Current cost data is unavailable for {name}.")
        max_level = len(skill["versions"]["Current"])
        if target > max_level:
            raise ValueError(f"{name} only goes to level {max_level}.")

        requirement = skill.get("unlock_requirement")
        if requirement and levels.get(skill_key(requirement["skill"]), 0) < requirement["level"]:
            reach_level(requirement["skill"], requirement["level"], (*visiting, key))

        current = levels[key]
        if current < target:
            cost = calculate_skill_cost(name, current, target)
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


def plan_coin_spending(plan, coin_balance):
    coin_balance = int(coin_balance)
    if coin_balance < 0:
        raise ValueError("Coin balance cannot be negative.")

    remaining = coin_balance
    purchases = []
    next_purchase = None
    for action in plan["actions"]:
        skill = get_skill(action["skill"])
        levels = skill["versions"]["Current"]
        current_level = action["current_level"]
        funded_level = current_level
        action_cost = 0
        for level_index in range(current_level, action["target_level"]):
            cost = levels[level_index]["cost"]
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


def format_skill_plan_response(plan, step_limit=5):
    actions = plan["actions"]
    lines = ["**Next upgrades (Current):**"] if actions else ["**All route goals reached.**"]
    for index, action in enumerate(actions[:step_limit], 1):
        lines.append(
            f"{index}. {action['skill']}: {action['current_level']} → {action['target_level']} "
            f"({action['cost']:,} Coins)"
        )
    if len(actions) > step_limit:
        lines.append(f"…and {len(actions) - step_limit} more steps.")
    lines.append(f"**Coins to finish the route:** {plan['total_cost']:,}")
    return "\n".join(lines)


def format_skill_budget_response(plan, coin_balance):
    spending = plan_coin_spending(plan, coin_balance)
    lines = [f"**Recommended spending for {coin_balance:,} Coins:**"]
    if spending["purchases"]:
        lines.extend(
            f"{index}. {purchase['skill']}: {purchase['current_level']} → {purchase['target_level']} "
            f"({purchase['cost']:,} Coins)"
            for index, purchase in enumerate(spending["purchases"], 1)
        )
    elif spending["next_purchase"]:
        lines.append("Save your coins for the next planned upgrade.")

    next_purchase = spending["next_purchase"]
    if next_purchase:
        lines.append(
            f"Save {spending['unspent']:,} toward {next_purchase['skill']} level "
            f"{next_purchase['target_level']} ({next_purchase['cost']:,} Coins needed)."
        )
    elif spending["unspent"]:
        lines.append(f"Route complete; {spending['unspent']:,} Coins remain unspent.")

    lines.append(f"**Spent:** {spending['spent']:,} Coins")
    lines.append(f"**Coins to finish the route:** {plan['total_cost']:,}")
    return "\n".join(lines)


def format_skill_response(skill, current_level, target_label, total, version, level_costs):
    description = skill.get("description", "").strip()
    description = re.sub(r'^"\s*.*?"\s*', "", description)
    description = re.sub(r"\s*Has a base cost of\b.*$", "", description)
    details = f"\n{description}" if description else ""
    costs = "\n".join(
        f"Level {current_level + index}: {cost:,} Coins"
        for index, cost in enumerate(level_costs, 1)
    )
    cost_details = f"\n\n**Next level costs:**\n{costs}" if costs else ""
    return (
        f"**{skill['name']}** ({version}){details}\n\n"
        f"{current_level} → {target_label} costs **{total:,} Coins**.{cost_details}"
    )


def clean(text, limit=CELL_MAX):
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_overview_value(key, value):
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


def find_upgrade(tower, table, row):
    """Level name/image/description for a stats row (only tables with Level + Cost columns are linked)."""
    if not table.get("linked") or not row or not row[0].isdigit():
        return None
    upgrades = tower["upgrades"]
    modes = {u["mode"] for u in upgrades}
    mode = table["mode"] if table["mode"] in modes else "Regular"  # e.g. Archer's arrow tabs
    for upgrade in upgrades:
        if (
            upgrade["mode"] == mode
            and upgrade["path"] == table["path"]
            and not upgrade["ability"]
            and upgrade["level"] == int(row[0])
        ):
            return upgrade
    return None


def level_traits(tower, table, level):
    mode = table.get("mode", "Regular")
    base_stats = tower.get("info", {}).get(mode.lower(), {})
    detections = set()
    immunities = set()

    for key, label in (("Hidden Detection", "Hidden"), ("Lead Detection", "Lead"), ("Flying Detection", "Flying")):
        value = base_stats.get(key, "").strip()
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
            elif value.lower() not in {"n/a", "unknown"}:
                detections.add(label)

    base_immunities = base_stats.get("Immunities", "")
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


def row_heading(headers, row, upgrade=None):
    first = row[0] if row else "?"
    if "Unit" in headers:
        unit = row[headers.index("Unit")] if headers.index("Unit") < len(row) else ""
        if unit:
            first = unit
            label = ""
        else:
            label = headers[0] if headers else ""
    else:
        label = headers[0] if headers else ""
    heading = f"{label} {first}" if first.isdigit() and label else first
    if upgrade and upgrade["name"]:
        heading += f" ({upgrade['name']})"
    return heading


def dps_multiplier(header, skill_tree, tower_slug, unit_row=False, row_stats=None):
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


def adjusted_stat(header, value, skill_tree, tower_slug, unit_row=False, row_stats=None):
    is_cost_efficiency = "cost efficiency" in header.lower()
    numeric_value = value.replace("$", "") if is_cost_efficiency else value

    try:
        number = Decimal(numeric_value.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return value

    enhanced_optics = skill_tree.get("enhanced_optics", 0)
    improved_gunpowder = skill_tree.get("improved_gunpowder", 0)
    fight_dirty = skill_tree.get("fight_dirty", 0)
    precision = skill_tree.get("precision", 0)
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
        result = number / dps_multiplier(header, skill_tree, tower_slug, unit_row, row_stats)
    elif "dps" in header_lower:
        result = number * skill_factor * dps_multiplier(header, skill_tree, tower_slug, unit_row, row_stats)
    else:
        result = number * skill_factor * buff_factor

    if result == number:
        return value
    formatted = f"{result:,.4f}".rstrip("0").rstrip(".")
    return f"${formatted}" if is_cost_efficiency and value.strip().startswith("$") else formatted


def with_thumbnail(text, image):
    text = TextDisplay(text)
    return Section(text, accessory=Thumbnail(image)) if image else text


class SkillView(LayoutView):
    def __init__(self, skill, current_level, target_label, total, version, level_costs):
        super().__init__(timeout=300)
        container = Container(accent_colour=discord.Colour.blurple())
        container.add_item(with_thumbnail(
            format_skill_response(skill, current_level, target_label, total, version, level_costs),
            skill.get("image", ""),
        ))
        self.add_item(container)


def render_row(headers, row, upgrade=None, include_changes=False, traits=None, skill_tree=None, tower_slug=""):
    """One table row as a card: heading (with level name), what the upgrade does, stats, picture."""
    lines = [f"### {clean(row_heading(headers, row, upgrade))}"]
    is_unit_table = "Unit" in headers
    raw_stats = dict(zip(headers[1:], row[1:]))
    cells = [
        (header, adjusted_stat(header, cell, skill_tree or {}, tower_slug, is_unit_table, raw_stats))
        for header, cell in zip(headers[1:], row[1:])
    ]
    stat_cells = [(header, cell) for header, cell in cells if header in STAT_EMOJIS and cell]
    stat_cells.sort(key=lambda item: list(STAT_EMOJIS).index(item[0]))
    if stat_cells:
        lines.append("  ".join(f"{STAT_EMOJIS[header].get()} {clean(cell)}" for header, cell in stat_cells))
    if upgrade and include_changes:
        lines += [f"> {clean(d, 200)}" for d in upgrade["description"]]
    for header, cell in cells:
        if cell and header not in STAT_EMOJIS:
            lines.append(f"**{clean(header)}:** {clean(cell)}")
    if traits is not None:
        detections, immunities = traits
        detection_icons = [DETECTION_EMOJIS[name].get() for name in detections if name in DETECTION_EMOJIS]
        immunity_icons = [
            ("~" if name.startswith("Partial ") else "")
            + IMMUNITY_EMOJIS[name.removeprefix("Partial ")].get()
            for name in immunities
            if name.removeprefix("Partial ") in IMMUNITY_EMOJIS
        ]
        lines.append(f"**Detections:** {' '.join(detection_icons) or 'None'}")
        lines.append(f"**Immunities:** {' '.join(immunity_icons) or 'None'}")
    return with_thumbnail("\n".join(lines), upgrade["image"] if upgrade else "")


def render_ability(upgrade):
    heading = f"### {upgrade['name']}"
    if upgrade["mode"] != "Regular":
        heading += f" ({upgrade['mode']})"
    lines = [heading]
    if upgrade["cost"]:
        lines.append(f"**Cost:** {upgrade['cost']}")
    lines += [f"**Unlocks at:** Level {upgrade['tag'].rstrip('+')}"]
    lines += [f"**{clean(extra)}**" for extra in upgrade["extra"]]
    lines += [f"> {clean(d, 200)}" for d in upgrade["description"]]
    return with_thumbnail("\n".join(lines), upgrade["image"])


def render_stat_changes(skill_tree, tower_slug=""):
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
            f"1 in {29 - precision} attacks: 1.25× damage {Emoji.PrecisionSkill.get()}"
        )

    if not active_skills and not active_buffs:
        return ""

    lines = ["### Stat changes"]
    if active_skills:
        lines.append("**Skills:** " + " · ".join(active_skills))
    if active_buffs:
        lines.append("**Buffs:** " + " · ".join(active_buffs))
    if skill_bonuses:
        lines.append("**Skill bonuses:** " + " · ".join(skill_bonuses))
    return "\n".join(lines)


def render_overview(tower, skill_tree=None, tower_slug=""):
    """Placement limit, footprint, role, base stats for Regular and PvP..."""
    info = tower["info"]
    general, regular, pvp = info["general"], info["regular"], info["pvp"]

    footprint = regular.get("Placement Footprint", "")
    if pvp.get("Placement Footprint") and pvp["Placement Footprint"] != footprint:
        footprint = f"{footprint} (Regular) / {pvp['Placement Footprint']} (PvP)"

    lines = [clean(t, 300) for t in info["tooltips"]]
    for key in HEADLINE_KEYS:
        if general.get(key):
            lines.append(f"**{key}:** {clean(format_overview_value(key, general[key]))}")
    if footprint:
        lines.append(f"**Placement Footprint:** {clean(footprint)}")
    if general.get("Placement Limit"):
        lines.append(
            f"**Placement Limit:** {clean(format_overview_value('Placement Limit', general['Placement Limit']))}"
        )
    items = [with_thumbnail("\n".join(lines) or "No info found.", tower["image"])]

    details = [
        f"**{key}:** {clean(format_overview_value(key, value))}"
        for key, value in general.items()
        if key not in (*HEADLINE_KEYS, "Placement Limit")
    ]
    if details:
        items += [Separator(), TextDisplay("### Details\n" + "\n".join(details))]

    changes = render_stat_changes(skill_tree or {}, tower_slug)
    if changes:
        items += [Separator(), TextDisplay(changes)]

    for label, block in (("Regular", regular), ("PvP", pvp)):
        block_lines = [f"**{k}:** {clean(v)}" for k, v in block.items()]
        # if block_lines:
        #    items += [Separator(), TextDisplay(f"### {label} Stats\n" + "\n".join(block_lines))]
    return items


class TowerView(LayoutView):
    def __init__(self, slug, include_changes=False, skill_tree=None):
        super().__init__(timeout=300)
        self.slug = slug
        self.include_changes = include_changes
        self.skill_tree = skill_tree or {}
        self.tower = DATA[slug]
        self.pages = self.make_pages()
        self.page = 0  # selected page
        self.group = 0  # selected level (or range of levels if a table has >25 rows)
        self.build()

    def make_pages(self):
        pages = [("Overview", "overview", None)]
        if any(u["ability"] for u in self.tower["upgrades"]):
            pages.append(("Abilities", "abilities", None))
        tables = self.tower["tables"]
        has_pvp = any(t["mode"] == "PvP" for t in tables)
        for table in tables:
            if table["mode"] == "Levels": # for old data
                continue
            title = table["title"]
            if has_pvp and table["mode"] in ("Regular", "PvP") and not title.lower().startswith(table["mode"].lower()):
                title = f"{table['mode']} ({title})"
            pages.append((title, "table", table))
        return pages[:MAX_OPTIONS]

    def build(self):
        self.clear_items()
        container = Container(accent_colour=discord.Colour.blurple())
        label, kind, payload = self.pages[self.page]

        container.add_item(TextDisplay(label))
        container.add_item(Separator(spacing=discord.SeparatorSpacing.large))

        groups, headers = [], []
        if kind == "overview":
            for item in render_overview(self.tower, self.skill_tree, self.slug):
                container.add_item(item)
        elif kind == "abilities":
            abilities = [u for u in self.tower["upgrades"] if u["ability"]]
            for i, upgrade in enumerate(abilities):
                container.add_item(render_ability(upgrade))
                if i < len(abilities) - 1:
                    container.add_item(Separator())
        else:
            headers, rows = payload["headers"], payload["rows"]
            changes = render_stat_changes(self.skill_tree, self.slug)
            if changes:
                container.add_item(TextDisplay(changes))
                container.add_item(Separator())
            # One row per option; if there are more than 25 rows, each option covers a range
            size = max(1, math.ceil(len(rows) / MAX_OPTIONS))
            groups = [rows[i : i + size] for i in range(0, len(rows), size)]
            self.group = max(0, min(self.group, len(groups) - 1)) if groups else 0
            if not groups:
                container.add_item(TextDisplay("No rows in this table."))
            else:
                shown = groups[self.group]
                for i, row in enumerate(shown):
                    has_stats = any(header in STAT_EMOJIS for header in headers)
                    traits = level_traits(self.tower, payload, int(row[0])) if has_stats and row and str(row[0]).isdigit() else None
                    container.add_item(render_row(
                        headers,
                        row,
                        find_upgrade(self.tower, payload, row),
                        include_changes=self.include_changes,
                        traits=traits,
                        skill_tree=self.skill_tree,
                        tower_slug=self.slug,
                    ))
                    if i < len(shown) - 1:
                        container.add_item(Separator())

        container.add_item(Separator(spacing=discord.SeparatorSpacing.large))

        if len(groups) > 1:
            def group_label(group):
                first = row_heading(headers, group[0], find_upgrade(self.tower, payload, group[0]))
                if len(group) == 1:
                    return first
                last = row_heading(headers, group[-1], find_upgrade(self.tower, payload, group[-1]))
                return f"{first} … {last}"

            level_select = discord.ui.Select(
                placeholder="Choose a level",
                options=[
                    discord.SelectOption(label=group_label(g)[:100], value=str(i), default=(i == self.group))
                    for i, g in enumerate(groups)
                ],
            )
            level_select.callback = self.on_level
            level_row = ActionRow()
            level_row.add_item(level_select)
            container.add_item(level_row)

        if len(self.pages) > 1:
            page_select = discord.ui.Select(
                placeholder="Choose a page",
                options=[
                    discord.SelectOption(
                        label=name[:100],
                        value=str(i),
                        default=(i == self.page),
                        emoji=(
                            discord.PartialEmoji.from_str(Emoji.Ability.get())
                            if kind == "abilities"
                            else discord.PartialEmoji.from_str(Emoji.DamageBuff.get())
                            if kind == "table" and payload["mode"] == "Regular"
                            else discord.PartialEmoji.from_str(Emoji.Sword.get())
                            if kind == "table" and payload["mode"] == "PvP"
                            else None
                        ),
                    )
                    for i, (name, kind, payload) in enumerate(self.pages)
                ],
            )
            page_select.callback = self.on_page
            page_row = ActionRow()
            page_row.add_item(page_select)
            container.add_item(page_row)

        self.add_item(container)

    async def on_level(self, interaction: discord.Interaction):
        self.group = int(interaction.data["values"][0])
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_page(self, interaction: discord.Interaction):
        self.page = int(interaction.data["values"][0])
        self.group = 0
        self.build()
        await interaction.response.edit_message(view=self)


GALLERY_HIDDEN = {"Update History", "Contents", "Notes"}
# The wiki names the same section differently from tower to tower
GALLERY_RENAMES = {
    "Skin Upgrades": "Skins",
    "Original Variants": "Previous Variants",
    "Gallery": "Other",
    "Regular Faces": "Faces",
    "Face": "Faces",
}
GALLERY_ORDER = ["Skins", "Previous Variants", "Weapons", "Faces", "Upgrade Icons"]  # anything else, then "Other"
GALLERY_ROW = 10  # a media gallery holds at most 10 images
GALLERY_MAX_IMAGES = 2 * GALLERY_ROW  # largest entry in the data is 16


def gallery_sections(tower):
    """[(section name, [entry, ...])] where an entry is one thing to look at: {label, images: [{caption, sub, image}]}.

    Images that sit in the same tab (\"Red\", \"Red / Version 2\", \"Red / Top Path\") are merged into one entry,
    so a skin is one entry holding all of its pictures. Images without a tab are their own entry, labelled by caption.
    """
    sections = {}
    for item in tower.get("gallery", []):
        if item["section"] in GALLERY_HIDDEN or item["image"].endswith("/Transparent.png"):
            continue
        name = GALLERY_RENAMES.get(item["section"], item["section"]) or "Other"
        entries = sections.setdefault(name, {})
        panel = item["panel"]
        # No tab: captioned images stay separate, uncaptioned ones are pooled into one entry per section
        key = panel or (f"#{len(entries)}" if item["caption"] else "")
        entry = entries.setdefault(key, {"label": panel or item["caption"] or name, "images": []})
        entry["images"].append({"caption": item["caption"], "sub": "", "image": item["image"]})

    def rank(name):
        if name == "Other":
            return len(GALLERY_ORDER) + 1
        return GALLERY_ORDER.index(name) if name in GALLERY_ORDER else len(GALLERY_ORDER)

    def split(entry):
        """Entries with more images than fit in one message become "Default (1/3)", "Default (2/3)"..."""
        images = entry["images"]
        if len(images) <= GALLERY_MAX_IMAGES:
            return [entry]
        parts = math.ceil(len(images) / GALLERY_MAX_IMAGES)
        return [
            {"label": f"{entry['label']} ({n}/{parts})", "images": images[(n - 1) * GALLERY_MAX_IMAGES : n * GALLERY_MAX_IMAGES]}
            for n in range(1, parts + 1)
        ]

    ordered = sorted(sections.items(), key=lambda kv: rank(kv[0]))  # stable, so the page order is kept otherwise
    return [(name, [part for e in entries.values() for part in split(e)]) for name, entries in ordered][:MAX_OPTIONS]


def render_gallery_entry(entry):
    """Text under the title: a numbered list of what each picture is (only if the pictures are labelled)."""
    tags = [image["sub"] or image["caption"] for image in entry["images"]]
    if not any(tags):
        return None
    lines = [f"**{n}.** {clean(tag)}" for n, tag in enumerate(tags, 1) if tag]
    return TextDisplay("\n".join(lines))


class GalleryView(LayoutView):
    def __init__(self, slug):
        super().__init__(timeout=600)
        self.slug = slug
        self.sections = gallery_sections(DATA[slug])
        self.section = 0  # selected section
        self.entry = 0  # selected entry inside the section
        self.chunk = 0  # which block of entries the select menu shows
        self.build()

    def build(self):
        self.clear_items()
        name, entries = self.sections[self.section]
        self.entry = max(0, min(self.entry, len(entries) - 1))
        self.chunk = self.entry // GALLERY_PAGE_SIZE
        entry = entries[self.entry]

        container = Container(accent_colour=discord.Colour.blurple())
        title = f"# {NAMES[self.slug]} Gallery\n-# {name} • {clean(entry['label'], 80)}"
        if len(entries) > 1:
            title += f" ({self.entry + 1}/{len(entries)})"
        container.add_item(TextDisplay(title))
        container.add_item(Separator(spacing=discord.SeparatorSpacing.large))

        tags = render_gallery_entry(entry)
        if tags:
            container.add_item(tags)
        images = entry["images"]
        for i in range(0, len(images), GALLERY_ROW):
            container.add_item(MediaGallery(*[
                discord.MediaGalleryItem(image["image"], description=clean(image["caption"], 1024) or None)
                for image in images[i : i + GALLERY_ROW]
            ]))

        container.add_item(Separator(spacing=discord.SeparatorSpacing.large))

        if len(entries) > 1:
            start = self.chunk * GALLERY_PAGE_SIZE
            chunks = math.ceil(len(entries) / GALLERY_PAGE_SIZE)
            options = [
                discord.SelectOption(label=clean(e["label"], 100), value=str(i), default=(i == self.entry))
                for i, e in enumerate(entries[start : start + GALLERY_PAGE_SIZE], start)
            ]
            if self.chunk > 0:
                options.append(discord.SelectOption(label=f"← Previous page ({self.chunk}/{chunks})", value="__previous__"))
            if self.chunk < chunks - 1:
                options.append(discord.SelectOption(label=f"Next page ({self.chunk + 2}/{chunks}) →", value="__next__"))
            entry_select = discord.ui.Select(
                placeholder=f"Choose from {name.lower()}",
                options=options,
            )
            entry_select.callback = self.on_entry
            entry_row = ActionRow()
            entry_row.add_item(entry_select)
            container.add_item(entry_row)

        if len(self.sections) > 1:
            section_select = discord.ui.Select(
                placeholder="Choose a section",
                options=[
                    discord.SelectOption(label=name[:100], value=str(i), default=(i == self.section))
                    for i, (name, _) in enumerate(self.sections)
                ],
            )
            section_select.callback = self.on_section
            section_row = ActionRow()
            section_row.add_item(section_select)
            container.add_item(section_row)

        self.add_item(container)

    async def show(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_entry(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if value == "__previous__":
            self.entry = (self.chunk - 1) * GALLERY_PAGE_SIZE
        elif value == "__next__":
            self.entry = (self.chunk + 1) * GALLERY_PAGE_SIZE
        else:
            self.entry = int(value)
        await self.show(interaction)

    async def on_section(self, interaction: discord.Interaction):
        self.section = int(interaction.data["values"][0])
        self.entry = 0
        await self.show(interaction)

class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


client = Bot()


async def tower_autocomplete(interaction: discord.Interaction, current: str):
    current = current.lower()
    matches = [(slug, name) for slug, name in NAMES.items() if current in name.lower()]
    return [app_commands.Choice(name=name, value=slug) for slug, name in matches[:25]]

async def remove_autocomplete(interaction: discord.Interaction, current: str):
    previous, separator, partial = current.rpartition(",")

    entered = {
        tower.strip().lower()
        for tower in previous.split(",")
        if tower.strip()
    }

    partial = partial.strip().lower()

    matches = [
        (slug, name)
        for slug, name in NAMES.items()
        if partial in name.lower()
        and name.lower() not in entered
    ]

    return [
        app_commands.Choice(
            name=f"{previous}, {name}" if separator else name,
            value=f"{previous}, {name}" if separator else name
        )
        for slug, name in matches[:25]
    ]

@client.tree.command(name="tower", description="Look up a tower's stats")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(
    name="Tower name",
    include_changes="Show stat changes at each level",
    enhanced_optics="Enhanced Optics level (0-20)",
    improved_gunpowder="Improved Gunpowder level (0-25)",
    fight_dirty="Fight Dirty level (0-25)",
    precision="Precision level (0-15)",
    accelerator="Accelerator level (0-25)",
    expanded_barracks="Expanded Barracks level (0-20)",
    beefed_up_minions="Beefed Up Minions level (0-25)",
    firerate_buff="Percent bonus (15 means +15%)",
    range_buff="Percent bonus (15 means +15%)",
    damage_buff="Percent bonus (15 means +15%)",
)
@app_commands.autocomplete(name=tower_autocomplete)
async def tower(
    interaction: discord.Interaction,
    name: str,
    include_changes: bool = False,
    enhanced_optics: app_commands.Range[int, 0, 20] = 0,
    improved_gunpowder: app_commands.Range[int, 0, 25] = 0,
    fight_dirty: app_commands.Range[int, 0, 25] = 0,
    precision: app_commands.Range[int, 0, 15] = 0,
    accelerator: app_commands.Range[int, 0, 25] = 0,
    expanded_barracks: app_commands.Range[int, 0, 20] = 0,
    beefed_up_minions: app_commands.Range[int, 0, 25] = 0,
    firerate_buff: app_commands.Range[int, 0, 1000] = 0,
    range_buff: app_commands.Range[int, 0, 1000] = 0,
    damage_buff: app_commands.Range[int, 0, 1000] = 0,
):
    slug = name.lower().replace(" ", "_")
    if slug not in DATA:
        await interaction.response.send_message(f"Couldn't find a tower called `{name}`.", ephemeral=True)
        return
    skill_tree = {
        "enhanced_optics": enhanced_optics,
        "improved_gunpowder": improved_gunpowder,
        "fight_dirty": fight_dirty,
        "precision": precision,
        "accelerator": accelerator,
        "expanded_barracks": expanded_barracks,
        "beefed_up_minions": beefed_up_minions,
        "firerate_buff": firerate_buff,
        "range_buff": range_buff,
        "damage_buff": damage_buff,
    }
    await interaction.response.send_message(view=TowerView(slug, include_changes, skill_tree))


async def skill_autocomplete(interaction: discord.Interaction, current: str):
    current = current.lower()
    matches = [name for name in SKILL_NAMES if current in name.lower()]
    return [app_commands.Choice(name=name, value=name) for name in matches[:25]]


@client.tree.command(name="skill", description="Calculate how many coins it costs to level a skill")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(
    name="Skill name",
    current_level="Your current skill level",
    target_level="Target skill level; defaults to the skill's max level",
    levels="Optional number of levels to add on top of your current level",
    version="Skill cost version",
)
@app_commands.choices(version=[
    app_commands.Choice(name="Current", value="Current"),
    app_commands.Choice(name="Version 1", value="Version 1"),
])
@app_commands.autocomplete(name=skill_autocomplete)
async def skill(
    interaction: discord.Interaction,
    name: str,
    current_level: int = 0,
    target_level: int | None = None,
    levels: int = 0,
    version: str = "Current",
):
    skill_data = get_skill(name)
    if skill_data is None:
        await interaction.response.send_message(f"Couldn't find a skill called `{name}`.", ephemeral=True)
        return

    versions = skill_data.get("versions", {})
    if version not in versions:
        await interaction.response.send_message(
            f"{version} cost data is unavailable for {skill_data['name']}.",
            ephemeral=True,
        )
        return
    skill_levels = versions[version]
    max_level = len(skill_levels)
    current_level = max(0, int(current_level))

    if levels > 0 and target_level is None:
        target_level = current_level + levels
    if target_level is None:
        target_level = max_level

    if current_level > max_level or target_level > max_level:
        await interaction.response.send_message(
            f"{skill_data['name']} only goes to level {max_level}.",
            ephemeral=True,
        )
        return
    if target_level < current_level:
        await interaction.response.send_message(
            "Target level must be greater than o/skill name: Extreme Conditioning version: Version 1r equal to the current level.",
            ephemeral=True,
        )
        return

    total = calculate_skill_cost(skill_data["name"], current_level, target_level, version)
    level_costs = [level["cost"] for level in skill_levels[current_level:target_level]]
    target_label = "max" if target_level == max_level else str(target_level)
    if current_level == target_level:
        total = 0
        target_label = str(target_level)

    await interaction.response.send_message(
        view=SkillView(skill_data, current_level, target_label, total, version, level_costs)
    )


@client.tree.command(name="plan", description="Suggest upcoming skill upgrades and route cost")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(
    coins="Your current coins",
    stonks="Current Stonks level",
    scavenger="Current Scavenger level",
    bigger_budget="Current Bigger Budget level",
    enhanced_optics="Current Enhanced Optics level",
    reenforcements="Current Re-enforcements level",
    accelerator="Current Accelerator level",
    fight_dirty="Current Fight Dirty level",
    improved_gunpowder="Current Improved Gunpowder level",
    extreme_conditioning="Current Extreme Conditioning level",
    beefed_up_minions="Current Beefed Up Minions level",
    expanded_barracks="Current Expanded Barracks level",
    precision="Current Precision level",
    resourcefulness="Current Resourcefulness level",
    fortify="Current Fortify level",
    bandages="Current Bandages level",
    over_heal="Current Over-Heal level",
    scholar="Current Scholar level",
)
async def skillplan(
    interaction: discord.Interaction,
    coins: app_commands.Range[int, 0, 100_000_000] | None = None,
    stonks: app_commands.Range[int, 0, 20] = 0,
    scavenger: app_commands.Range[int, 0, 20] = 0,
    bigger_budget: app_commands.Range[int, 0, 25] = 0,
    enhanced_optics: app_commands.Range[int, 0, 20] = 0,
    reenforcements: app_commands.Range[int, 0, 10] = 0,
    accelerator: app_commands.Range[int, 0, 25] = 0,
    fight_dirty: app_commands.Range[int, 0, 25] = 0,
    improved_gunpowder: app_commands.Range[int, 0, 25] = 0,
    extreme_conditioning: app_commands.Range[int, 0, 25] = 0,
    beefed_up_minions: app_commands.Range[int, 0, 25] = 0,
    expanded_barracks: app_commands.Range[int, 0, 20] = 0,
    precision: app_commands.Range[int, 0, 15] = 0,
    resourcefulness: app_commands.Range[int, 0, 25] = 0,
    fortify: app_commands.Range[int, 0, 40] = 0,
    bandages: app_commands.Range[int, 0, 25] = 0,
    over_heal: app_commands.Range[int, 0, 25] = 0,
    scholar: app_commands.Range[int, 0, 20] = 0,
):
    current_levels = {
        "Stonks": stonks,
        "Scavenger": scavenger,
        "Bigger Budget": bigger_budget,
        "Enhanced Optics": enhanced_optics,
        "Re-enforcements": reenforcements,
        "Accelerator": accelerator,
        "Fight Dirty": fight_dirty,
        "Improved Gunpowder": improved_gunpowder,
        "Extreme Conditioning": extreme_conditioning,
        "Beefed Up Minions": beefed_up_minions,
        "Expanded Barracks": expanded_barracks,
        "Precision": precision,
        "Resourcefulness": resourcefulness,
        "Fortify": fortify,
        "Bandages": bandages,
        "Over-Heal": over_heal,
        "Scholar": scholar,
    }
    try:
        plan = build_skill_plan(current_levels)
    except ValueError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return

    response = (
        format_skill_budget_response(plan, coins)
        if coins is not None
        else format_skill_plan_response(plan)
    )
    await interaction.response.send_message(response)


@client.tree.command(name="gallery", description="Browse a tower's skins, weapons and other art")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(name="Tower name")
@app_commands.autocomplete(name=tower_autocomplete)
async def gallery(interaction: discord.Interaction, name: str):
    slug = name.lower().replace(" ", "_")
    if slug not in DATA:
        await interaction.response.send_message(f"Couldn't find a tower called `{name}`.", ephemeral=True)
        return
    view = GalleryView(slug)
    if not view.sections:
        await interaction.response.send_message(f"{NAMES[slug]} has no gallery images.", ephemeral=True)
        return
    await interaction.response.send_message(view=view)

@client.tree.command(name="loadout", description="Generate a random loadout")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(remove="Towers to remove from the loadout seperated by commas")
@app_commands.autocomplete(remove=remove_autocomplete)
async def loadout(interaction: discord.Interaction, remove: str = ""):
    remove_slugs = {r.strip().lower().replace(" ", "_") for r in remove.split(",") if r.strip()}
    available_slugs = [slug for slug in DATA if slug not in remove_slugs]

    if len(available_slugs) < 5:
        await interaction.response.send_message(
            f"Not enough towers available to generate a loadout. Remove fewer towers.", ephemeral=True
        )
        return

    selected_slugs = random.sample(available_slugs, 5)
    selected_names = [NAMES[slug] for slug in selected_slugs]
    await interaction.response.send_message(', '.join(selected_names))

if __name__ == "__main__":
    load_dotenv()
    client.run(os.getenv("TOKEN"))
