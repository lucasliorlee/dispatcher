from emoji import Emoji

from .base import _action_row, _reply, _section, _select, _select_option
from .towers import (
    _component_update,
    _history_chunks,
    _paged_options,
    _tower_slug,
    _update_entries,
    _update_label,
)
ENEMY_TEXT_LIMIT = 3300  # Components V2 allows 4000 characters of text per message; TEXT_BUDGET is 3700
ENEMY_SECTION_ORDER = ("Appearance", "Strategy", "Trivia", "Update History")
ENEMY_TRAITS = (
    ("Hidden?", "Hidden", Emoji.HiddenDetection),
    ("Flying?", "Flying", Emoji.FlyingDetection),
    ("Lead?", "Lead", Emoji.LeadDetection),
    ("Ghost?", "Ghost", None),
)
ENEMY_TRAIT_LABELS = {label for label, _, _ in ENEMY_TRAITS}
ENEMY_ATTRIBUTE_EMOJIS = (
    ("Splash Damage Immune", Emoji.noSplash),
    ("Boss Immunities", Emoji.Boss),
    ("Health Regen", Emoji.HealthRegen),
    ("Neutralized", Emoji.Neutralized),
    ("No Target", Emoji.NoTarget),
    ("Stun Immune", Emoji.noStun),
    ("Stun Immunity", Emoji.noStun),
    ("Freeze Immune", Emoji.noFreeze),
    ("Freeze Immunity", Emoji.noFreeze),
    ("Burn Immune", Emoji.noBurn),
    ("Burn Immunity", Emoji.noBurn),
    ("Hidden", Emoji.HiddenDetection),
    ("Flying", Emoji.FlyingDetection),
    ("Lead", Emoji.LeadDetection),
    ("Ghost", Emoji.Ghost),
    ("Bloated", Emoji.Bloated),
    ("Nimble", Emoji.Nimble),
    ("Slime", Emoji.Slime),
    ("Tank", Emoji.Tank),
    ("Aggro", Emoji.Aggro),
    ("Corpse", Emoji.Corpse),
    ("Blessed", Emoji.Blessed),
)


def _clip(text, limit):
    text = str(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit("\n", 1)[0] if "\n" in text[:limit] else text[: limit - 1]
    return cut.rstrip() + "\nâ€¦"


def _enemy_field(label, value):
    """Single-line values stay inline; bullet lists go under the label."""
    value = str(value)
    return f"**{label}:**\n{value}" if "\n" in value else f"**{label}:** {value}"


def _enemy_attribute_field(label, value):
    value = str(value)
    if label != "Attributes" or value.strip().lower() == "none":
        return _enemy_field(label, value)
    lines = []
    skip_boss_immunity_details = False
    for line in value.splitlines():
        indentation = line[:len(line) - len(line.lstrip())]
        content = line.lstrip()
        if skip_boss_immunity_details:
            if indentation:
                continue
            skip_boss_immunity_details = False
        if content.removeprefix("- ").startswith("Boss Immunities"):
            content = "- Boss Immunities" if content.startswith("- ") else "Boss Immunities"
            skip_boss_immunity_details = True
        bullet = "- " if content.startswith("- ") else ""
        content = content[2:] if bullet else content
        emoji = next(
            (emoji for name, emoji in ENEMY_ATTRIBUTE_EMOJIS if content.startswith(name)),
            None,
        )
        if emoji:
            content = f"{emoji.get()} {content}"
        lines.append(f"{indentation}{bullet}{content}")
    return f"**{label}:**\n" + "\n".join(lines)


def _fit_groups(lines, limit, from_end=False):
    """Keep whole top-level bullets (with their sub-bullets) up to `limit` characters.

    from_end=True keeps the newest entries, which is what you want for Update History.
    Returns (text, number_of_entries_left_out).
    """
    groups = []
    for line in lines:
        if line.startswith(" ") and groups:
            groups[-1].append(line)
        else:
            groups.append([line])
    chosen, used = [], 0
    for group in (reversed(groups) if from_end else groups):
        text = "\n".join(group)
        if chosen and used + len(text) + 1 > limit:
            break
        chosen.append(_clip(text, limit))
        used += len(text) + 1
    if from_end:
        chosen.reverse()
    return "\n".join(chosen), len(groups) - len(chosen)


def _enemy_pages(enemy):
    pages = [("Overview", "overview", None)]
    variants = enemy.get("variants", [])
    if any(variant.get("stats") or variant.get("abilities") for variant in variants):
        pages.append(("Stats", "stats", None))
    if enemy.get("debuts"):
        pages.append(("Debuts", "debuts", None))
    sections = {name: lines for name, lines in enemy.get("sections", {}).items() if name != "Description"}
    ordered = [name for name in ENEMY_SECTION_ORDER if name in sections]
    ordered += [name for name in sections if name not in ENEMY_SECTION_ORDER]
    pages.extend((name, "section", sections[name]) for name in ordered)
    return pages[:25]


def _enemy_page_emoji(title, kind):
    if title == "Description":
        return Emoji.Logbook
    if title == "Appearance":
        return Emoji.Abnormal
    if title == "Debuts":
        return Emoji.NarratorTalk
    if kind == "stats":
        return Emoji.DamageBuff
    return {
        "Strategy": "🏹",
        "Trivia": Emoji.TDSWikiLogo,
        "Update History": Emoji.ScholarSkill,
        "Notes": "📋",
    }.get(title)


def _enemy_context(enemy):
    slug = enemy.get("slug", "")
    base_slug = _tower_slug(enemy.get("name", ""))
    if slug.startswith(base_slug + "_"):
        return slug[len(base_slug) + 1:].replace("_", " ").title()
    return ""


def _enemy_title(enemy, subtitle=None):
    context = _enemy_context(enemy)
    display_name = enemy["name"] + (f" ({context})" if context else "")
    title_name = f"[{display_name}]({enemy['url']})" if enemy.get("url") else display_name
    title = f"# {title_name}"
    return f"{title}\n## {subtitle}" if subtitle else title


def _enemy_overview_text(enemy):
    lines = [_enemy_title(enemy)]
    description = "\n".join(enemy.get("sections", {}).get("Description", [])) or enemy.get("description", "")
    if description:
        lines.extend(["", description])
    return "\n".join(lines)


def _enemy_stats_text(enemy, variant, show_variant):
    lines = [_enemy_title(enemy, f"Stats ({variant['name']})" if show_variant else "Stats")]
    traits_done = False
    for label, value in variant.get("stats", {}).items():
        if label in ENEMY_TRAIT_LABELS:
            if not traits_done:
                traits_done = True
                shown = [
                    f"{emoji.get()} {name}" if emoji else name
                    for key, name, emoji in ENEMY_TRAITS
                    if str(variant["stats"].get(key, "")).strip().lower().startswith("yes")
                ]
                lines.append(f"**Traits:** {' '.join(shown) or 'None'}")
            continue
        lines.append(_enemy_attribute_field(label, value))
    if variant.get("abilities"):
        lines.extend(["", "### Abilities"])
        lines.extend(ability["text"] for ability in variant["abilities"])
    return _clip("\n".join(lines), ENEMY_TEXT_LIMIT)


def _enemy_debuts_text(enemy):
    lines = [_enemy_title(enemy, "Debuts")]
    for label in ("mode_appearance", "wave_debut"):
        if enemy.get(label):
            display_label = "Mode Appearance" if label == "mode_appearance" else "Wave Debut"
            lines.append(_enemy_field(display_label, enemy[label]))
    for debut in enemy.get("debuts", []):
        lines.append(f"### {debut['title']}" + (f"\n-# {debut['dates']}" if debut.get("dates") else ""))
        steps = []
        for key in ("previous", "current", "next"):
            step = debut.get(key)
            if not step:
                continue
            text = step["name"] + (f" ({step['wave']})" if step.get("wave") else "")
            steps.append(f"**{text}**" if key == "current" else text)
        lines.append(" â†’ ".join(steps))
    return _clip("\n".join(lines), ENEMY_TEXT_LIMIT)


def _enemy_section_text(enemy, title, section_lines):
    newest = title == "Update History"
    if newest and section_lines:
        update_heading = str(section_lines[0]).replace("**", "").lstrip("- ").strip()
        body, left_out = _fit_groups(section_lines[1:], ENEMY_TEXT_LIMIT - 300, from_end=False)
        lines = [_enemy_title(enemy), f"## {update_heading}", body]
    else:
        body, left_out = _fit_groups(section_lines, ENEMY_TEXT_LIMIT - 300, from_end=newest)
        lines = [_enemy_title(enemy, title), body]
    if left_out:
        lines.append(f"-# {left_out} {'older ' if newest else 'more '}entr{'ies' if left_out != 1 else 'y'} on the wiki page")
    return "\n".join(lines)


def _enemy_children(enemy, pages, page_index, variant_index=0, history_index=0, history_group=0):
    """The message for one enemy page. Stats has a variant dropdown when the wiki page has several tabs."""
    page_index = max(0, min(page_index, len(pages) - 1))
    variants = enemy.get("variants", [])
    variant_index = max(0, min(variant_index, len(variants) - 1)) if variants else 0
    state = f"{page_index},{variant_index},{history_index},{history_group}"
    slug = enemy["slug"]
    title, kind, payload = pages[page_index]

    if kind == "stats":
        variant = variants[variant_index]
        children = [_section(_enemy_stats_text(enemy, variant, len(variants) > 1), enemy.get("image"))]
        if len(variants) > 1:
            children.append(_action_row(_select(
                f"enemy|{slug}|variant|{state}",
                "Choose a version",
                [_select_option(item["name"], index, default=(index == variant_index)) for index, item in enumerate(variants)],
            )))
    elif kind == "debuts":
        children = [_section(_enemy_debuts_text(enemy), enemy.get("image"))]
    elif kind == "section":
        if title == "Update History":
            entries = _update_entries(payload)
            chunks = _history_chunks(entries)
            history_group = max(0, min(history_group, len(chunks) - 1)) if chunks else 0
            chunk = chunks[history_group] if chunks else []
            history_index = max(0, min(history_index, len(chunk) - 1)) if chunk else 0
            selected_payload = chunk[history_index] if chunk else payload
            children = [_section(_enemy_section_text(enemy, title, selected_payload), enemy.get("image"))]
            if entries:
                children.append(_action_row(_select(
                    f"enemy|{slug}|history|{state}",
                    "Choose an update",
                    _paged_options(entries, history_group, _update_label),
                )))
        else:
            children = [_section(_enemy_section_text(enemy, title, payload), enemy.get("image"))]
    else:
        children = [_section(_enemy_overview_text(enemy), enemy.get("image"))]

    if len(pages) > 1:
        children.append(_action_row(_select(
            f"enemy|{slug}|page|{state}",
            "Choose a page",
            [
                _select_option(
                    name,
                    index,
                    default=(index == page_index),
                    emoji=_enemy_page_emoji(name, kind),
                )
                for index, (name, kind, _) in enumerate(pages)
            ],
        )))
    return children


def _handle_enemy(options, enemies):
    name = str(options.get("name", ""))
    enemy = enemies.get(_tower_slug(name))
    if enemy is None:
        enemy = next((item for item in enemies.values() if item.get("name", "").lower() == name.lower()), None)
    if enemy is None:
        return _reply(f"Couldn't find an enemy called `{name}`.", ephemeral=True)
    return _reply("", children=_enemy_children(enemy, _enemy_pages(enemy), 0))


def _handle_enemy_component(slug, action, selected, state, enemies):
    enemy = (enemies or {}).get(slug)
    if enemy is None:
        return _reply("This enemy could not be found. Run the command again.", ephemeral=True)
    pages = _enemy_pages(enemy)
    page_index, variant_index, history_index, history_group = (list(state) + [0, 0, 0, 0])[:4]
    if action == "page":
        if selected >= len(pages):
            return _reply("This page could not be found. Run the command again.", ephemeral=True)
        page_index = selected
    elif action == "variant":
        variant_index = selected
    elif action == "history":
        if selected in {"previous", "next"}:
            history_group += -1 if selected == "previous" else 1
            history_index = 0
        else:
            history_index = selected
    else:
        return _reply("This menu has expired. Run the command again.", ephemeral=True)
    return _component_update(_enemy_children(
        enemy, pages, page_index, variant_index, history_index, history_group,
    ))
