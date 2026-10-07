from . import base as _base

for _module in (_base,):
    globals().update({k: v for k, v in vars(_module).items() if not k.startswith("__")})


MODE_SECTION_LIMIT = 3600


def _mode_block_text(block):
    if isinstance(block, str):
        return block
    if block.get("type") == "list":
        return "\n".join(f"- {item}" for item in block.get("items", []))
    if block.get("type") == "table":
        headers = block.get("headers", [])
        rows = block.get("rows", [])
        lines = []
        for row in rows:
            values = [
                f"**{headers[index]}:** {value}"
                for index, value in enumerate(row)
                if index < len(headers) and value
            ]
            lines.append(" • ".join(values) or " • ".join(row))
        return "\n".join(lines)
    return ""


def _mode_pages(mode):
    sections = [("Overview", f"# [{mode['name']}]({mode['url']})\n\n{mode.get('description', '')}", mode.get("image"))]
    if mode.get("infobox"):
        facts = "\n".join(
            f"**{key}:** {value}" for key, value in mode["infobox"].items()
        )
        sections.append(("Quick facts", f"## Quick facts\n{facts}", None))
    for title, blocks in mode.get("sections", {}).items():
        if title == "Description":
            continue
        content = "\n\n".join(filter(None, (_mode_block_text(block) for block in blocks)))
        if content:
            sections.append((title, f"## {title}\n{content}", None))
    return sections


def _mode_reply(modes, selected, page_index=0):
    if not modes:
        return _reply("Mode data is unavailable.", ephemeral=True)
    if selected not in modes:
        return _reply("Select a valid game mode with the `/mode` command.", ephemeral=True)
    mode = modes[selected]
    pages = _mode_pages(mode)
    page_index = max(0, min(page_index, len(pages) - 1))
    title, content, image = pages[page_index]
    if len(content) > MODE_SECTION_LIMIT:
        content = content[: MODE_SECTION_LIMIT - 20].rsplit("\n", 1)[0].rstrip() + "\n…"
    children = [_section(content, image)]
    if len(pages) > 1:
        children.append(_action_row(_select(
            f"mode|{selected}|section|{page_index}",
            "Choose a section",
            [
                _select_option(name, index, default=(index == page_index))
                for index, (name, _, _) in enumerate(pages)
            ],
        )))
    return _reply("", children=children)


def _handle_mode(options, modes):
    return _mode_reply(modes, str(options.get("mode", "")))


def _handle_mode_component(slug, action, state, modes, value):
    if action == "section":
        try:
            page_index = int(value)
        except ValueError:
            return _reply("This menu selection is invalid. Run the command again.", ephemeral=True)
    else:
        return _reply("This menu has expired. Run the command again.", ephemeral=True)
    data = _mode_reply(modes, slug, page_index)["data"]
    return {
        "type": 7,
        "data": data,
    }
