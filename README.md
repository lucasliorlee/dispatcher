# Tower Defense Simulator Discord Bot

The root `bot.py` is the original `discord.py` bot. It is no longer actively updated, but should still function. The separate Cloudflare Worker lives in [`worker/`](worker/) and has its own setup guide at [`worker/README.md`](worker/README.md). The main use is `scrapper.py` to get data from the wiki.

## Requirements

- Python 3.12 or newer
- A Discord application and bot token

## Run the bot

From the repository root, create and activate a virtual environment, then install the dependencies:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create a `.env` file in the repository root:

```text
TOKEN=your_discord_bot_token
```

Start the bot from the repository root:

```sh
python bot.py
```

On startup, the bot syncs its slash commands with Discord. Keep `.env` private; it is ignored by Git.

## Commands

- `/tower` shows tower overviews and stats.
- `/enemy` shows an enemy overview and stats.
- `/skill` calculates skill upgrade costs.
- `/plan` suggests a skill upgrade plan.
- `/gallery` browses tower images.
- `/loadout` generates a random tower loadout.

The Worker also serves searchable tower and enemy browsers at `/towers` and `/enemies`.

## Data

The bot reads `towers.json` and `skills/skills.json` from the repository. These files are included in the project. To refresh tower, skill, and enemy data from the wiki, run:

```sh
python scrapper.py
python enemies.py
python worker/sync_data.py --source local
```

The scraper caches tower pages under `towers/`, galleries under `galleries/`, and skill data under `skills/`. Enemy pages are cached under `enemies/` and summarized into `enemies.json` for the Worker.