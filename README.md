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
- `/skill` calculates skill upgrade costs.
- `/plan` suggests a skill upgrade plan.
- `/gallery` browses tower images.
- `/loadout` generates a random tower loadout.

## Data

The bot reads `towers.json` and `skills/skills.json` from the repository. These files are included in the project. To refresh tower and skill data from the wiki, run:

```sh
python scrapper.py
```

The scraper caches tower pages under `towers/`, galleries under `galleries/`, and skill data under `skills/`.