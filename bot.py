import json
import math
import os
import random
import re

from dotenv import load_dotenv

import discord
from discord import app_commands
from discord.ui import ActionRow, Container, LayoutView, MediaGallery, Section, Separator, TextDisplay, Thumbnail

# Requires discord.py 2.6+ (Components V2: LayoutView, Container, TextDisplay)

with open("towers.json", encoding="utf-8") as f:
    DATA = json.load(f)

NAMES = {slug: tower["name"] for slug, tower in DATA.items()}
CELL_MAX = 150
MAX_OPTIONS = 25  # Discord select menus hold at most 25 options
GALLERY_PAGE_SIZE = MAX_OPTIONS - 2  # reserve select options for previous/next navigation

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


def level_traits(tower, table, level):
    mode = table.get("mode", "Regular")
    base_stats = tower.get("info", {}).get(mode.lower(), {})
    detections = set()
    immunities = set()

    for key, label in (("Hidden Detection", "Hidden"), ("Lead Detection", "Lead"), ("Flying Detection", "Flying")):
        value = base_stats.get(key, "").strip()
        if value and value.lower() not in {"n/a", "unknown"}:
            matches = list(re.finditer(r"\bLevel\s+(\d+)[A-Z]?\+?", value, re.IGNORECASE))
            if matches:
                tower_match = next(
                    (match for index, match in enumerate(matches)
                     if re.search(r"\bTower\b", value[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(value)], re.IGNORECASE)),
                    None,
                )
                match = tower_match or (matches[0] if len(matches) == 1 else None)
                if match:
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
            or upgrade.get("path") != table.get("path")
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
    label = headers[0] if headers else ""
    heading = f"{label} {first}" if first.isdigit() and label else first
    if upgrade and upgrade["name"]:
        heading += f" ({upgrade['name']})"
    return heading


def with_thumbnail(text, image):
    text = TextDisplay(text)
    return Section(text, accessory=Thumbnail(image)) if image else text


def render_row(headers, row, upgrade=None, include_changes=False, traits=None):
    """One table row as a card: heading (with level name), what the upgrade does, stats, picture."""
    lines = [f"### {clean(row_heading(headers, row, upgrade))}"]
    if upgrade and include_changes:
        lines += [f"> {clean(d, 200)}" for d in upgrade["description"]]
    for header, cell in zip(headers[1:], row[1:]):
        if cell:
            lines.append(f"**{clean(header)}:** {clean(cell)}")
    if traits is not None:
        detections, immunities = traits
        lines.append(f"**Detection:** {', '.join(detections) or 'None'}")
        lines.append(f"**Immunities:** {', '.join(immunities) or 'None'}")
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
        block_lines = [f"**{k}:** {clean(v)}" for k, v in block.items()]
        # if block_lines:
        #    items += [Separator(), TextDisplay(f"### {label} Stats\n" + "\n".join(block_lines))]
    return items


class TowerView(LayoutView):
    def __init__(self, slug, include_changes=False):
        super().__init__(timeout=300)
        self.slug = slug
        self.include_changes = include_changes
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
            size = max(1, math.ceil(len(rows) / MAX_OPTIONS))
            groups = [rows[i : i + size] for i in range(0, len(rows), size)]
            self.group = max(0, min(self.group, len(groups) - 1)) if groups else 0
            if not groups:
                container.add_item(TextDisplay("No rows in this table."))
            else:
                shown = groups[self.group]
                for i, row in enumerate(shown):
                    traits = level_traits(self.tower, payload, int(row[0])) if row and str(row[0]).isdigit() else None
                    container.add_item(render_row(
                        headers,
                        row,
                        find_upgrade(self.tower, payload, row),
                        include_changes=self.include_changes,
                        traits=traits,
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
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(name="Tower name", include_changes="Show stat changes at each level")
@app_commands.autocomplete(name=tower_autocomplete)
async def tower(interaction: discord.Interaction, name: str, include_changes: bool = False):
    slug = name.lower().replace(" ", "_")
    if slug not in DATA:
        await interaction.response.send_message(f"Couldn't find a tower called `{name}`.", ephemeral=True)
        return
    await interaction.response.send_message(view=TowerView(slug, include_changes))

@client.tree.command(name="gallery", description="Browse a tower's skins, weapons and other art")
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
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
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
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
