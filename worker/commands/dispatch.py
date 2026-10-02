from . import base as _base, skills as _skills, towers as _towers, enemies as _enemies, handlers as _handlers, tracker as _tracker
for _module in (_base, _skills, _towers, _enemies, _handlers, _tracker):
    globals().update({k: v for k, v in vars(_module).items() if not k.startswith('__')})
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


def handle_command(interaction, towers, skills, enemies=None, tracker_user_id=None, tracker_rows=None):
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
        "enemy": _handle_enemy,
        "skill": _handle_skill,
        "plan": _handle_plan,
        "gallery": _handle_gallery,
        "loadout": _handle_loadout,
        "trials": _handle_trials,
    }
    handler = handlers.get(data.get("name"))
    if handler is None:
        return _reply("Unknown command.", ephemeral=True)
    if data["name"] == "enemy":
        return handler(options, enemies or {})
    return handler(options, skills if data["name"] in {"skill", "plan"} else towers)


def handle_component(interaction, towers, enemies=None):
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

    if kind == "enemy":
        selected_value = str(values[0])
        try:
            selected = int(selected_value)
            state = [int(value) for value in state.split(",")]
        except ValueError:
            if action not in {"history"}:
                return _reply("This menu selection is invalid. Run the command again.", ephemeral=True)
            try:
                state = [int(value) for value in state.split(",")]
            except ValueError:
                return _reply("This menu selection is invalid. Run the command again.", ephemeral=True)
            selected = selected_value
        return _handle_enemy_component(slug, action, selected, state, enemies)

    tower = towers.get(slug)
    if tower is None:
        return _reply("This tower could not be found. Run the command again.", ephemeral=True)

    selected_value = str(values[0])
    try:
        selected = int(selected_value)
        state = [int(value) for value in state.split(",")]
    except ValueError:
        if action not in {"history", "entry"}:
            return _reply("This menu selection is invalid. Run the command again.", ephemeral=True)
        selected = selected_value
        try:
            state = [int(value) for value in state.split(",")]
        except ValueError:
            return _reply("This menu selection is invalid. Run the command again.", ephemeral=True)

    if kind == "tower" and action == "page":
        pages = _tower_pages(tower)
        if selected >= len(pages):
            return _reply("This page could not be found. Run the command again.", ephemeral=True)
        include_changes, include_description, skill_tree = _unpack_state(state)
        return _component_update(_tower_children(tower, pages, selected, 0, include_changes, include_description, skill_tree))

    if kind == "tower" and action == "history":
        page_index = state[0]
        include_changes, include_description, skill_tree = _unpack_state(state)
        pages = _tower_pages(tower)
        if page_index >= len(pages) or pages[page_index][1] != "section" or pages[page_index][0] != "Update History":
            return _reply("This update history could not be found. Run the command again.", ephemeral=True)
        entries = _update_entries(pages[page_index][2])
        group = _history_group(state)
        chunks = _history_chunks(entries)
        if selected in {"previous", "next"}:
            group += -1 if selected == "previous" else 1
            selected = 0
        if group < 0 or group >= len(chunks) or selected >= len(chunks[group]):
            return _reply("This update could not be found. Run the command again.", ephemeral=True)
        return _component_update(_tower_children(
            tower, pages, page_index, 0, include_changes, include_description, skill_tree, selected, group,
        ))

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
        section_index, entry_page = (state + [0])[:2]
        entries = sections[section_index][1] if section_index < len(sections) else []
        chunks = _history_chunks(entries)
        if selected in {"previous", "next"}:
            entry_page += -1 if selected == "previous" else 1
            selected = 0
        if section_index >= len(sections) or entry_page < 0 or entry_page >= len(chunks):
            return _reply("This gallery entry could not be found. Run the command again.", ephemeral=True)
        return _component_update(_gallery_children(
            tower, sections, section_index, entry_page * 23 + selected, entry_page,
        ))

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
    enemies = catalog.get("enemies", [])

    if command in {"tower", "gallery"} and option_name == "name":
        choices = _choices([tower["name"] for tower in towers], query, lambda name: next(tower["slug"] for tower in towers if tower["name"] == name))
    elif command == "enemy" and option_name == "name":
        enemy_labels = [
            enemy["name"] + (f" ({_enemy_context(enemy)})" if _enemy_context(enemy) else "")
            for enemy in enemies
        ]
        choices = _choices(
            enemy_labels,
            query,
            lambda label: next(
                enemy["slug"]
                for enemy in enemies
                if enemy["name"] + (f" ({_enemy_context(enemy)})" if _enemy_context(enemy) else "") == label
            ),
        )
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

