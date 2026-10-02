from . import base as _base
_globals = {k: v for k, v in vars(_base).items() if not k.startswith('__')}
globals().update(_globals)
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
        f"**{_utc_text(first_ts)} â†’ {_utc_text(last_ts)}** (UTC)",
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



