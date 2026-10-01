import math
import random
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from emoji import Emoji


APP_CONTEXTS = [0, 1, 2]
APP_INSTALLS = [0, 1]
MAX_CONTENT = 1900
COMPONENTS_V2 = 1 << 15
CELL_MAX = 150
TABLE_GROUP_LIMIT = 15
LEVEL_SELECT_SIZE = 25  # Discord select menus hold 25 options
TRACKER_URL = "https://tds.lucasliorleyt.workers.dev/tracker"
TRIAL_INTERVAL_SECONDS = 3 * 60 * 60
TRIAL_ANCHOR_EPOCH = 1790845200  # 2:00 AM Pacific Daylight Time on 2026-10-01; Inflation ends.
TRIAL_AFTER_ANCHOR_INDEX = 3
TRIALS = (
    ("Flying", Emoji.FlyingTrial),
    ("Limitation", Emoji.LimitationTrial),
    ("Inflation", Emoji.InflationTrial),
    ("Quarantine", Emoji.QuarantineTrial),
    ("Broke", Emoji.BrokeTrial),
    ("Fog", Emoji.FogTrial),
    ("Speedy", Emoji.SpeedyTrial),
    ("Healthy", Emoji.HealthyTrial),
    ("Committed", Emoji.CommitedTrial),
    ("Exploding", Emoji.ExplodingTrial),
    ("Glass", Emoji.GlassTrial),
    ("Hidden", Emoji.HiddenTrial),
    ("Jailed", Emoji.JailedTrial),
)
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
SKILL_LABELS = (
    ("enhanced_optics", Emoji.EnhancedOpticsSkill),
    ("improved_gunpowder", Emoji.ImprovedGunpowderSkill),
    ("fight_dirty", Emoji.FightDirtySkill),
    ("precision", Emoji.PrecisionSkill),
    ("accelerator", Emoji.AcceleratorSkill),
    ("expanded_barracks", Emoji.ExpandedBarracksSkill),
    ("beefed_up_minions", Emoji.BeefedUpMinionsSkill),
)
# Order matters: these are packed into the component custom_id after the page/flag values.
SKILL_TREE_KEYS = (
    "enhanced_optics", "improved_gunpowder", "fight_dirty", "precision", "accelerator",
    "expanded_barracks", "beefed_up_minions", "firerate_buff", "range_buff", "damage_buff",
)
TEXT_BUDGET = 3700  # Discord allows 4000 characters of text per Components V2 message
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
    _command("gallery", "Browse a tower's skins, weapons, and other stuff", [
        _option("name", "Tower name", 3, True, autocomplete=True),
        _option("section", "Gallery section", 3, autocomplete=True),
        _option("entry", "Gallery entry", 3, autocomplete=True),
    ]),
    _command("loadout", "Generate a random loadout", [
        _option("remove", "Comma-separated tower names to exclude", 3, autocomplete=True),
    ]),
    _command("track", "View or update your level and EXP history", [
        _option("level", "Your current level", 4, min_value=0),
        _option("exp", "Your current EXP", 10, min_value=0),
        _option("timestamp", "When this record happened, in UTC (YYYY-MM-DD HH:MM); defaults to now", 3),
        _option("page", "Records page to view", 4, min_value=1, max_value=1000000),
        _option("zoom_start", "First record number to include in the stats", 4, min_value=1, max_value=1000000),
        _option("zoom_end", "Last record number to include in the stats", 4, min_value=1, max_value=1000000),
    ]),
    _command("trials", "Show the upcoming modifier trials", [
        _option("view", "Show upcoming times for a specific trial", 3, choices=[
            {"name": name, "value": name.lower()}
            for name, _ in TRIALS
        ]),
        _option("count", "Number of upcoming trials or occurrences (1-14)", 4, min_value=1, max_value=14),
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


def _select(custom_id, placeholder, options, max_values=1):
    component = {
        "type": 3,
        "custom_id": custom_id,
        "placeholder": placeholder,
        "options": options[:25],
    }
    if max_values > 1:
        component["min_values"] = 1
        component["max_values"] = min(max_values, len(component["options"]))
    return component


def _select_option(label, value, default=False, emoji=None):
    option = {"label": str(label)[:100], "value": str(value)[:100], "default": default}
    if emoji:
        option["emoji"] = {"id": str(emoji.value), "name": emoji.name}
    return option


def _action_row(component):
    return {"type": 1, "components": [component]}


def _action_row_multi(components):
    return {"type": 1, "components": components}


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


def _skill_tree(options):
    return {key: int(options.get(key) or 0) for key in SKILL_TREE_KEYS}


def _pack_state(page_index, include_changes, include_description, skill_tree):
    values = [page_index, int(include_changes), int(include_description)]
    values.extend(int((skill_tree or {}).get(key, 0)) for key in SKILL_TREE_KEYS)
    return ",".join(str(value) for value in values)


def _unpack_state(state):
    """state: [page, include_changes, include_description, *skill tree values]"""
    include_changes = bool(state[1]) if len(state) > 1 else False
    include_description = bool(state[2]) if len(state) > 2 else False
    skill_tree = {
        key: state[3 + index] if len(state) > 3 + index else 0
        for index, key in enumerate(SKILL_TREE_KEYS)
    }
    return include_changes, include_description, skill_tree


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
            f"1 in {29 - precision} attacks: 1.25× damage {Emoji.PrecisionSkill.get()}"
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


def _format_tower_content(tower, page, include_changes, group=0, include_description=False, skill_tree=None):
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


def _tower_children(tower, pages, page_index, row_index, include_changes, include_description=False, skill_tree=None):
    """Build the message for one tower page. Table pages show a single level, picked from a dropdown."""
    skill_tree = skill_tree or {}
    tower_slug = _tower_slug(tower["name"])
    state = _pack_state(page_index, include_changes, include_description, skill_tree)
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
                    return first if first == last else f"{first} … {last}"

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
        image = tower.get("image") if page[1] == "overview" else None
        children = [_section(
            _format_tower_content(tower, page, include_changes, 0, include_description, skill_tree),
            image,
        )]
    if len(pages) > 1:
        children.append(_action_row(_select(
            f"tower|{tower_slug}|page|{state}",
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


def _exp_requirement(next_level):
    if next_level <= 0:
        return 0
    if next_level <= 10:
        return 45 + next_level * 3.5
    if next_level <= 40:
        return next_level * 8
    return 260 + next_level * 1.5


def _progress(level, exp):
    return exp + sum(_exp_requirement(n) for n in range(1, level + 1))


def _fmt_number(value):
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _utc_text(timestamp):
    return datetime.fromtimestamp(float(timestamp), timezone.utc).strftime("%Y-%m-%d %H:%M")


TRACK_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
TRACK_TIMESTAMP_HELP = "Invalid timestamp. Use `YYYY-MM-DD HH:MM` in UTC, for example `2026-08-29 09:06`."


def parse_track_timestamp(value):
    """Parse the optional /track timestamp ("YYYY-MM-DD HH:MM", UTC) into a unix timestamp.

    Returns None when blank. Raises ValueError for malformed or future values.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, TRACK_TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(TRACK_TIMESTAMP_HELP)
    timestamp = parsed.timestamp()
    if timestamp > time.time() + 60:
        raise ValueError("Timestamp cannot be in the future.")
    return timestamp


def _zoom_window(total, zoom_start=None, zoom_end=None):
    """1-based inclusive (start, end) record window, clamped to the available records."""
    start = int(zoom_start) if zoom_start else 1
    end = int(zoom_end) if zoom_end else total
    start = max(1, min(start, total))
    end = max(1, min(end, total))
    if start > end:
        start, end = end, start
    return start, end


def _tracker_stats(rows, zoom_start=None, zoom_end=None):
    """Summary lines matching the stats panel on the tracker web page, over the zoom window."""
    if not rows:
        return []
    ordered = sorted(rows, key=lambda row: (float(row.get("timestamp", 0)), int(row.get("id", 0))))
    total = len(ordered)
    start, end = _zoom_window(total, zoom_start, zoom_end)
    window = ordered[start - 1 : end]
    first, last = window[0], window[-1]
    first_level, last_level = int(first.get("level", 0)), int(last.get("level", 0))
    last_exp = float(last.get("exp", 0))
    first_ts, last_ts = float(first.get("timestamp", 0)), float(last.get("timestamp", 0))
    seconds = max(last_ts - first_ts, 0)
    exp_gained = _progress(last_level, last_exp) - _progress(first_level, float(first.get("exp", 0)))
    rate = exp_gained / (seconds / 86400) if seconds else 0
    until_next = max(_exp_requirement(last_level + 1) - last_exp, 0)
    return [
        f"**{len(window):,}** records",
        f"**{last_level:,}** current level",
        f"**{last_level - first_level:,}** levels gained in zoom",
        f"**{_fmt_number(exp_gained)}** EXP gained in zoom",
        f"**{_fmt_number(rate)}** average EXP/day",
        f"**{_fmt_number(until_next)}** EXP until next level",
        f"**{_utc_text(first_ts)} → {_utc_text(last_ts)}** (UTC)",
        f"Time span: {int(seconds // 3600)}h {int(seconds % 3600 // 60)}m",
        f"Zoom start: Record {start} / {total}",
        f"Zoom end: Record {end} / {total}",
    ]


def _track_state(page, zoom_start=None, zoom_end=None):
    """Packed into component custom_ids as "page,zoom_start,zoom_end" (0 means default)."""
    return f"{int(page)},{int(zoom_start or 0)},{int(zoom_end or 0)}"


def track_zoom_from_state(state):
    """(zoom_start, zoom_end) from a packed tracker state; None for default."""
    parts = str(state).split(",")

    def number(index):
        try:
            return max(0, int(parts[index])) or None
        except (IndexError, ValueError):
            return None

    return number(1), number(2)


def _track_records_reply(rows, tracker_user_id, page=1, deleted=0, update=False, zoom_start=None, zoom_end=None):
    if not tracker_user_id:
        return _reply("I couldn't identify your Discord account.", ephemeral=True)
    stats = _tracker_stats(rows, zoom_start, zoom_end)
    rows = sorted(rows, key=lambda row: (float(row.get("timestamp", 0)), int(row.get("id", 0))), reverse=True)
    page_count = max(1, math.ceil(len(rows) / 25))
    page = max(1, min(int(page), page_count))
    page_rows = rows[(page - 1) * 25 : page * 25]
    state = _track_state(page, zoom_start, zoom_end)
    lines = [f"TDS level tracker (page {page}/{page_count})"]
    if deleted:
        lines.append(f"Deleted {deleted} record{'s' if deleted != 1 else ''}.")
    if stats:
        lines.extend(["", *stats, ""])
    else:
        lines.append("No records yet. Use `/track level` and `/track exp` to add one.")
    children = [_section("\n".join(lines))]
    if page_rows:
        children.append(_action_row(_select(
            f"track|records|delete|{state}",
            f"Select records to delete ({len(page_rows)} on this page)",
            [
                _select_option(
                    f"{_utc_text(row.get('timestamp', 0))}: Level {int(row.get('level', 0))}"
                    f" ({float(row.get('exp', 0)):g} EXP #{int(row['id'])})",
                    int(row["id"]),
                )
                for row in page_rows
            ],
            max_values=len(page_rows),
        )))
    if page_count > 1:
        first_page = max(1, min(page - 12, page_count - 24))
        last_page = min(page_count, first_page + 24)
        children.append(_action_row(_select(
            f"track|records|page|{state}",
            "Choose a records page",
            [_select_option(f"Page {number}", number, default=number == page) for number in range(first_page, last_page + 1)],
        )))
    children.append(_action_row({
        "type": 2,
        "style": 5,
        "label": "Open level tracker",
        "url": f"{TRACKER_URL}?user={tracker_user_id}",
    }))
    if update:
        return _component_update(children)
    return _reply("", children=children)


def _walk_components(components):
    for component in components or []:
        yield component
        yield from _walk_components(component.get("components"))


def _select_labels(interaction, custom_id):
    for component in _walk_components(interaction.get("message", {}).get("components")):
        if component.get("custom_id") == custom_id:
            return {str(o.get("value")): str(o.get("label", "")) for o in component.get("options", [])}
    return {}


def confirmed_delete_ids(interaction):
    """Record IDs listed as '#id' in the confirmation message."""
    ids = []
    for component in _walk_components(interaction.get("message", {}).get("components")):
        if component.get("type") == 10:
            ids.extend(int(match) for match in re.findall(r"#(\d+)", str(component.get("content", ""))))
    return list(dict.fromkeys(ids))


def track_page_from_state(state):
    try:
        return max(1, int(str(state).split(",")[0]))
    except ValueError:
        return 1


def handle_track_component(interaction):
    """Handles track|records|delete (ask to confirm) and |cancel. Returns None for other actions."""
    data = interaction.get("data", {})
    custom_id = str(data.get("custom_id", ""))
    parts = custom_id.split("|")
    if len(parts) != 4 or parts[0] != "track" or parts[1] != "records":
        return None
    action, state = parts[2], parts[3]

    if action == "cancel":
        return _component_update([_section("Deletion cancelled.")])

    if action == "delete":
        ids = list(dict.fromkeys(int(v) for v in data.get("values", []) if str(v).isdigit()))
        if not ids:
            return _reply("Select at least one record to delete.", ephemeral=True)
        labels = _select_labels(interaction, custom_id)
        lines = [f"### Delete {len(ids)} record{'s' if len(ids) != 1 else ''}?"]
        for record_id in ids:
            label = labels.get(str(record_id), "")
            if f"#{record_id}" not in label:
                label = f"{label} #{record_id}".strip()
            lines.append(f"- {label}")
        lines.append("\nThis can't be undone.")
        return _component_update([
            _section("\n".join(lines)),
            _action_row_multi([
                {"type": 2, "style": 2, "label": "Cancel", "custom_id": f"track|records|cancel|{state}"},
                {"type": 2, "style": 4, "label": "Delete", "custom_id": f"track|records|confirm|{state}"},
            ]),
        ])
    return None


def _handle_track(options, tracker_user_id=None):
    try:
        timestamp = parse_track_timestamp(options.get("timestamp"))
    except ValueError as error:
        return _reply(str(error), ephemeral=True)
    has_level = options.get("level") is not None
    has_exp = options.get("exp") is not None
    if has_level != has_exp:
        return _reply("Provide both level and EXP to add a record, or omit both to view your history.", ephemeral=True)
    if not has_level:
        return _reply("A timestamp can only be used when adding a record with a level and EXP.", ephemeral=True)
    if not tracker_user_id:
        return _reply("I couldn't identify your Discord account.", ephemeral=True)
    level = int(options["level"])
    exp = float(options["exp"])
    tracker_url = TRACKER_URL
    tracker_url += f"?user={tracker_user_id}"
    saved = f"Saved **Level {level}** with **{exp:g} EXP**"
    saved += (
        f" at {_utc_text(timestamp)} UTC (<t:{int(timestamp)}:f> your time)."
        if timestamp is not None else "."
    )
    return _reply(
        "",
        children=[
            _section(saved),
            _action_row({
                "type": 2,
                "style": 5,
                "label": "Open level tracker",
                "url": tracker_url,
            }),
        ],
    )


def _handle_trials(options, towers):
    count = max(1, min(14, int(options.get("count", 14) or 14)))
    requested = str(options.get("view", "") or "").lower()
    trial_count = len(TRIALS)

    if requested:
        target_index = next(
            (index for index, (name, _) in enumerate(TRIALS)
             if name.lower() == requested),
            None
        )

        if target_index is None:
            return _reply("That trial could not be found.", ephemeral=True)

        offset = max(
            0,
            (int(time.time()) - TRIAL_ANCHOR_EPOCH) // TRIAL_INTERVAL_SECONDS
        )

        while (TRIAL_AFTER_ANCHOR_INDEX + offset) % trial_count != target_index:
            offset += 1

        step = trial_count

    else:
        now = int(time.time())
        offset = max(
            0,
            (now - TRIAL_ANCHOR_EPOCH) // TRIAL_INTERVAL_SECONDS
        )
        step = 1

    lines = []

    for _ in range(count):
        trial_index = (
            TRIAL_AFTER_ANCHOR_INDEX + offset
        ) % trial_count

        name, emoji = TRIALS[trial_index]

        timestamp = (
            TRIAL_ANCHOR_EPOCH
            + offset * TRIAL_INTERVAL_SECONDS
        )

        lines.append(f"{emoji.get()} **{name}**: <t:{timestamp}:F>")

        offset += step

    return _reply("\n".join(lines))


def handle_command(interaction, towers, skills, tracker_user_id=None, tracker_rows=None):
    data = interaction.get("data", {})
    options = _options_map(data.get("options", []))
    if data.get("name") == "track":
        adding = any(options.get(key) is not None for key in ("level", "exp", "timestamp"))
        if not adding:
            return _track_records_reply(
                tracker_rows or [],
                tracker_user_id,
                options.get("page", 1),
                zoom_start=options.get("zoom_start"),
                zoom_end=options.get("zoom_end"),
            )
        return _handle_track(options, tracker_user_id)
    handlers = {
        "tower": _handle_tower,
        "skill": _handle_skill,
        "plan": _handle_plan,
        "gallery": _handle_gallery,
        "loadout": _handle_loadout,
        "trials": _handle_trials,
    }
    handler = handlers.get(data.get("name"))
    if handler is None:
        return _reply("Unknown command.", ephemeral=True)
    return handler(options, skills if data["name"] in {"skill", "plan"} else towers)


def handle_component(interaction, towers):
    data = interaction.get("data", {})
    custom_id = str(data.get("custom_id", ""))

    parts = custom_id.split("|")
    if len(parts) != 4:
        return _reply("This menu has expired. Run the command again.", ephemeral=True)

    kind, slug, action, state = parts

    # Tracker components (select menu and buttons) are handled before the "values" check,
    # because buttons carry no values.
    if kind == "track":
        return handle_track_component(interaction) or _reply(
            "This menu has expired. Run the command again.", ephemeral=True
        )

    values = data.get("values", [])
    if not values:
        return _reply("This menu selection is empty.", ephemeral=True)

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
        include_changes, include_description, skill_tree = _unpack_state(state)
        return _component_update(_tower_children(tower, pages, selected, 0, include_changes, include_description, skill_tree))

    if kind == "tower" and action in {"group", "level"}:
        page_index = state[0]
        include_changes, include_description, skill_tree = _unpack_state(state)
        pages = _tower_pages(tower)
        if page_index >= len(pages) or pages[page_index][1] != "table":
            return _reply("This table could not be found. Run the command again.", ephemeral=True)
        row_index = selected * LEVEL_SELECT_SIZE if action == "group" else selected
        return _component_update(_tower_children(
            tower, pages, page_index, row_index, include_changes, include_description, skill_tree,
        ))

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