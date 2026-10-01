# Discord bot on Cloudflare Workers

Python cloudflare worker using interaction endpoints URL.

## Requirements

- Python 3.12 or newer and [uv](https://docs.astral.sh/uv/)
- Node.js 20.19 or newer, for Wrangler through `npx`
- A Cloudflare account and a Discord application

## Local development

Run these commands from this directory:

```sh
uv sync
python sync_data.py
npx wrangler login --device
```

In a GitHub Codespace, `--device` avoids Wrangler's default redirect to `localhost`. Open the URL it prints in your browser and enter the displayed code to authorize Cloudflare.

Create a D1 database for the tracker:

```sh
npx wrangler d1 create tds-stats
```

Copy the returned database ID into the commented `[[d1_databases]]` block in `wrangler.toml`, with `binding = "DB"`, then apply the schema locally and remotely:

```sh
npx wrangler d1 migrations apply tds-stats --local
npx wrangler d1 migrations apply tds-stats --remote
```

For local OAuth testing, add the Discord application's client secret to `worker/.dev.vars`. The widget updater also needs the bot token:

```text
CLIENT_SECRET=your_discord_client_secret
BOT_TOKEN=your_discord_bot_token
```

Keep these values private. Configure `https://<worker-host>/tracker` and `https://<worker-host>/widget` as OAuth2 redirect URLs in the Discord Developer Portal. Use the Codespace's forwarded HTTPS host when testing locally.

Create a `.dev.vars` file containing your Discord application's public key:

```text
DISCORD_PUBLIC_KEY=your_discord_application_public_key
```

Then start the local Worker:

```sh
uv run pywrangler dev
```

The key is available in the Discord Developer Portal under **General Information**. `.dev.vars` is ignored by Git.

## Deploy and connect Discord

From the `worker/` directory, deploy the Worker once, then configure the public key as a Worker secret:

```sh
uv run pywrangler deploy
npx wrangler secret put DISCORD_PUBLIC_KEY
```

Use the deployed `workers.dev` URL as the Discord application's **Interactions Endpoint URL**. Discord validates it with a Ping request; this Worker responds to Ping interactions. The endpoint must be deployed and reachable over HTTPS.

Set the `CLIENT_SECRET` Worker secret for tracker OAuth. Set `BOT_TOKEN` as a Worker secret too if you use the profile widget updater:

```sh
npx wrangler secret put CLIENT_SECRET
npx wrangler secret put BOT_TOKEN
```

Register or update the slash commands using the application ID and bot token from your Discord application. These are only needed by the registration script; the running Worker does not need the bot token.

```sh
DISCORD_APPLICATION_ID=your_application_id \
DISCORD_BOT_TOKEN=your_bot_token \
uv run python register_commands.py
```

Keep the bot token private and do not commit it. The commands are registered globally, so Discord may take a little while to show updates.

## Updating tower and skill data

The Worker reads JSON files from the static asset binding. `sync_data.py` fetches the latest `towers.json` and `skills/skills.json` from the repository's `main` branch by default, then generates the autocomplete catalog. Use `--source local` to sync from the parent project directory instead. Run it from this directory before deploying:

```sh
# Choose one source:
python sync_data.py --source github
# python sync_data.py --source local
uv run pywrangler deploy
```