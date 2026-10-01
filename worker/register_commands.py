import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from dotenv import load_dotenv

from commands import COMMANDS
from webapp import CLIENT_ID


def main():
    load_dotenv(Path(__file__).with_name(".dev.vars"))
    application_id = os.environ.get("DISCORD_APPLICATION_ID", CLIENT_ID)
    bot_token = os.environ.get("DISCORD_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    if not application_id or not bot_token:
        raise SystemExit("Set BOT_TOKEN or DISCORD_BOT_TOKEN in worker/.dev.vars first.")

    request = Request(
        f"https://discord.com/api/v10/applications/{application_id}/commands",
        data=json.dumps(COMMANDS).encode("utf-8"),
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://discord.com, v10)",
        },
        method="PUT",
    )
    try:
        with urlopen(request) as response:
            registered = json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if "error code: 1010" in detail.lower():
            raise SystemExit(
                "Discord's edge protection blocked this request (403/1010). "
            ) from error
        raise SystemExit(f"Discord command registration failed ({error.code}): {detail}") from error

    print(f"Registered {len(registered)} global commands.")


if __name__ == "__main__":
    main()