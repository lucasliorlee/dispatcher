import re

from .base import _action_row, _reply, _section, _select, _select_option


WAVE_SELECT_SIZE = 23
WAVE_TEXT_LIMIT = 3600
_NUMBER_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def _wave_navigation(group, group_count):
    options = []
    if group > 0:
        options.append(_select_option("Previous page", "previous"))
    if group + 1 < group_count:
        options.append(_select_option("Next page", "next"))
    return options


def _wave_options(entries, group, selected):
    start = group * WAVE_SELECT_SIZE
    chunks = (len(entries) + WAVE_SELECT_SIZE - 1) // WAVE_SELECT_SIZE
    options = _wave_navigation(group, chunks)
    options.extend(
        _select_option(
            f"Wave {entry['wave']}",
            entry["wave"],
            default=(entry["wave"] == selected),
        )
        for entry in entries[start : start + WAVE_SELECT_SIZE]
    )
    return options


def _enemy_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _enemy_health(enemies, name):
    key = _enemy_key(name)
    enemy = next(
        (
            item for item in enemies.values()
            if _enemy_key(item.get("name", "")) == key
            or _enemy_key(item.get("slug", "")) == key
        ),
        None,
    )
    if enemy is None:
        return 0
    for variant in enemy.get("variants", []):
        raw_health = variant.get("stats", {}).get("Base Health", "")
        match = _NUMBER_RE.search(str(raw_health))
        if match:
            return int(match.group().replace(",", ""))
    return 0


def _required_damage(enemies, entries):
    total = 0
    for raw_entry in entries:
        for match in re.finditer(
            r"(\d[\d,]*)x\s+(.+?)(?=\s+\d[\d,]*x\s+|$)",
            str(raw_entry),
        ):
            count = int(match.group(1).replace(",", ""))
            enemy_name = re.sub(r"\s*\(.*$", "", match.group(2)).strip()
            enemy_name = re.sub(r"^\[\s*\d+\s*\]\s*", "", enemy_name)
            total += count * _enemy_health(enemies, enemy_name)
    return total


def _wave_content(mode, version, entry, enemies=None):
    enemies = enemies or {}
    lines = [
        f"# {mode['name']} (Wave {entry['wave']})",
        f"-# Version: {version['name']}",
    ]
    if entry.get("enemies"):
        lines.extend(["", "**Enemies:**"])
        lines.extend(entry["enemies"])
        lines.extend(["", f"**Required Damage:** {_required_damage(enemies, entry['enemies']):,}"])
    if entry.get("dialogue"):
        lines.extend(["", "**Dialog:**"])
        lines.extend(f"> {dialogue}" for dialogue in entry["dialogue"])
    return "\n".join(lines)


def _wave_reply(waves, slug, wave_number=None, group=None, version=0, enemies=None):
    mode = waves.get(slug)
    if mode is None:
        return _reply("That wave mode could not be found.", ephemeral=True)
    versions = mode.get("versions", [])
    if not versions:
        return _reply("Wave data is unavailable for that mode.", ephemeral=True)
    version = max(0, min(int(version), len(versions) - 1))
    selected_version = versions[version]
    entries = selected_version.get("waves", [])
    if not entries:
        return _reply("Wave data is unavailable for that mode.", ephemeral=True)
    wave_number = int(wave_number or entries[0]["wave"])
    entry = next((item for item in entries if item["wave"] == wave_number), None)
    if entry is None:
        return _reply("That wave could not be found.", ephemeral=True)
    if group is None:
        group = (wave_number - 1) // WAVE_SELECT_SIZE
    group = max(0, min(int(group), (len(entries) - 1) // WAVE_SELECT_SIZE))
    content = _wave_content(mode, selected_version, entry, enemies)
    if len(content) > WAVE_TEXT_LIMIT:
        content = content[: WAVE_TEXT_LIMIT - 20].rsplit("\n", 1)[0].rstrip() + "\n…"
    children = [_section(content)]
    if len(versions) > 1:
        children.append(_action_row(_select(
            f"wave|{slug}|version|{group}:{version}",
            "Choose a wave layout",
            [
                _select_option(item["name"], index, default=(index == version))
                for index, item in enumerate(versions)
            ],
        )))
    children.append(_action_row(_select(
        f"wave|{slug}|wave|{group}:{version}",
        "Choose a wave",
        _wave_options(entries, group, wave_number),
    )))
    return _reply("", children=children)


def _handle_wave(options, waves, enemies=None):
    return _wave_reply(
        waves,
        str(options.get("mode", "")),
        options.get("wave"),
        enemies=enemies,
    )


def _handle_wave_component(slug, action, state, waves, value, enemies=None):
    try:
        state_parts = state.split(":")
        group = int(state_parts[0])
        version = int(state_parts[1]) if len(state_parts) > 1 else 0
    except ValueError:
        return _reply("This menu selection is invalid. Run the command again.", ephemeral=True)
    mode = waves.get(slug)
    if mode is None:
        return _reply("That wave mode could not be found. Run the command again.", ephemeral=True)
    if action == "version":
        try:
            version = int(value)
        except ValueError:
            return _reply("This menu selection is invalid. Run the command again.", ephemeral=True)
        return _component_update(_wave_reply(waves, slug, version=version, enemies=enemies)["data"])
    if action != "wave":
        return _reply("This menu has expired. Run the command again.", ephemeral=True)
    versions = mode.get("versions", [])
    if version >= len(versions):
        return _reply("This wave layout could not be found. Run the command again.", ephemeral=True)
    entries = versions[version].get("waves", [])
    group_count = (len(entries) + WAVE_SELECT_SIZE - 1) // WAVE_SELECT_SIZE
    if value == "previous":
        group = max(0, group - 1)
        selected = entries[group * WAVE_SELECT_SIZE]["wave"]
    elif value == "next":
        group = min(group_count - 1, group + 1)
        selected = entries[group * WAVE_SELECT_SIZE]["wave"]
    else:
        try:
            selected = int(value)
        except ValueError:
            return _reply("This menu selection is invalid. Run the command again.", ephemeral=True)
    data = _wave_reply(waves, slug, selected, group, version, enemies)["data"]
    return {
        "type": 7,
        "data": data,
    }


def _component_update(data):
    return {"type": 7, "data": data}
