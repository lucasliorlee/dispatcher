import json
import math
import os
import random

from dotenv import load_dotenv

import discord
from discord import app_commands
from discord.ui import ActionRow, Container, LayoutView, Section, Separator, TextDisplay, Thumbnail

with open("towers.json", encoding="utf-8") as f:
    DATA = json.load(f)

NAMES = {slug: tower["name"] for slug, tower in DATA.items()}
CELL_MAX = 150
MAX_OPTIONS = 25  # Discord select menus hold at most 25 options

# Shown at the top of the overview, everything else in "general" goes under "Details"
HEADLINE_KEYS = ("Role", "Placement", "Placement Limit")


def clean(text, limit=CELL_MAX):
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


def row_heading(headers, row, upgrade=None):
    first = row[0] if row else "?"
    label = headers[0] if headers else ""
    heading = f"{label} {first}" if first.isdigit() and label else first
    if upgrade and upgrade["name"]:
        heading += f" ({upgrade['name']})"
    return heading


def with_thumbnail(text, image):
    text = TextDisplay(text)
    return Section(text, accessory=Thumbnail(image)) if image else text


def render_row(headers, row, upgrade=None):
    """One table row as a card: heading (with level name), what the upgrade does, stats, picture."""
    lines = [f"### {clean(row_heading(headers, row, upgrade))}"]
    if upgrade:
        lines += [f"> {clean(d, 200)}" for d in upgrade["description"]]
    for header, cell in zip(headers[1:], row[1:]):
        if cell:
            lines.append(f"**{clean(header)}:** {clean(cell)}")
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


def render_overview(tower):
    """Placement limit, footprint, role, base stats for Regular and PvP..."""
    info = tower["info"]
    general, regular, pvp = info["general"], info["regular"], info["pvp"]

    footprint = regular.get("Placement Footprint", "")
    if pvp.get("Placement Footprint") and pvp["Placement Footprint"] != footprint:
        footprint = f"{footprint} (Regular) / {pvp['Placement Footprint']} (PvP)"

    lines = [clean(t, 300) for t in info["tooltips"]]
    for key in HEADLINE_KEYS:
        if general.get(key):
            lines.append(f"**{key}:** {clean(general[key])}")
    if footprint:
        lines.append(f"**Placement Footprint:** {clean(footprint)}")
    items = [with_thumbnail("\n".join(lines) or "No info found.", tower["image"])]

    details = [f"**{k}:** {clean(v)}" for k, v in general.items() if k not in HEADLINE_KEYS]
    if details:
        items += [Separator(), TextDisplay("### Details\n" + "\n".join(details))]

    for label, block in (("Regular", regular), ("PvP", pvp)):
        block_lines = [f"**{k}:** {clean(v)}" for k, v in block.items() if k != "Placement Footprint"]
        # if block_lines:
        #     items += [Separator(), TextDisplay(f"### Base stats – {label}\n" + "\n".join(block_lines))]
    return items


class TowerView(LayoutView):
    def __init__(self, slug):
        super().__init__(timeout=300)
        self.slug = slug
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
            for item in render_overview(self.tower):
                container.add_item(item)
        elif kind == "abilities":
            abilities = [u for u in self.tower["upgrades"] if u["ability"]]
            for i, upgrade in enumerate(abilities):
                container.add_item(render_ability(upgrade))
                if i < len(abilities) - 1:
                    container.add_item(Separator())
        else:
            headers, rows = payload["headers"], payload["rows"]
            # One row per option; if there are more than 25 rows, each option covers a range
            # That shouldn't happen though but just to be safe cause why not
            size = max(1, math.ceil(len(rows) / MAX_OPTIONS))
            groups = [rows[i : i + size] for i in range(0, len(rows), size)]
            self.group = max(0, min(self.group, len(groups) - 1)) if groups else 0
            if not groups:
                container.add_item(TextDisplay("No rows in this table."))
            else:
                shown = groups[self.group]
                for i, row in enumerate(shown):
                    container.add_item(render_row(headers, row, find_upgrade(self.tower, payload, row)))
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
                    discord.SelectOption(label=name[:100], value=str(i), default=(i == self.page))
                    for i, (name, _, _) in enumerate(self.pages)
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
@app_commands.describe(name="Tower name")
@app_commands.autocomplete(name=tower_autocomplete)
async def tower(interaction: discord.Interaction, name: str):
    slug = name.lower().replace(" ", "_")
    if slug not in DATA:
        await interaction.response.send_message(f"Couldn't find a tower called `{name}`.", ephemeral=True)
        return
    await interaction.response.send_message(view=TowerView(slug))

@client.tree.command(name="loadout", description="Generate a random loadout")
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