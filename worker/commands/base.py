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
    _command("enemy", "Look up an enemy's stats", [
        _option("name", "Enemy name", 3, True, autocomplete=True),
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
        content = content[: MAX_CONTENT - 30].rstrip() + "\nâ€¦response shortened"
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



