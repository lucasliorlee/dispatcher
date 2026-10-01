import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from commands import COMMANDS


def main():
    application_id = os.environ.get("DISCORD_APPLICATION_ID")
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not application_id or not bot_token:
        raise SystemExit("Set DISCORD_APPLICATION_ID and DISCORD_BOT_TOKEN first.")

    request = Request(
        f"https://discord.com/api/v10/applications/{application_id}/commands",
        data=json.dumps(COMMANDS).encode("utf-8"),
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urlopen(request) as response:
            registered = json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Discord command registration failed ({error.code}): {detail}") from error

    print(f"Registered {len(registered)} global commands.")


if __name__ == "__main__":
    main()