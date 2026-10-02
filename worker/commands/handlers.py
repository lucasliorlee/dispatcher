from . import base as _base, skills as _skills, towers as _towers, enemies as _enemies
for _module in (_base, _skills, _towers, _enemies):
    globals().update({k: v for k, v in vars(_module).items() if not k.startswith('__')})
import random
import re

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
    lines.append(f"\n{current} â†’ {target_label} costs **{total:,} Coins**.")
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
            f"gallery|{_tower_slug(tower['name'])}|entry|{section_index},{entry_index // 23}",
            f"Choose a {section_name.lower()} entry",
            _paged_options(entries, entry_index // 23, lambda item: item["label"]),
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
