import json
from urllib.parse import urlsplit

from commands import handle_autocomplete, handle_command, handle_component
from js import Uint8Array, crypto
from pyodide.ffi import to_js
from workers import Response, WorkerEntrypoint, fetch
from webapp import handle_web_request

DATA_CACHE = None
AUTOCOMPLETE_CACHE = None


def _uint8(data):
    result = Uint8Array.new(len(data))
    for index, value in enumerate(data):
        result[index] = value
    return result


def _json_response(payload, status=200):
    return Response.from_json(payload, status=status)


async def _load_data(env):
    global DATA_CACHE
    if DATA_CACHE is None:
        towers_response = await env.ASSETS.fetch("https://worker-assets/towers.json")
        skills_response = await env.ASSETS.fetch("https://worker-assets/skills.json")
        if towers_response.status != 200 or skills_response.status != 200:
            raise RuntimeError("Worker data assets could not be loaded.")
        DATA_CACHE = (await towers_response.json(), (await skills_response.json())["skills"])
    return DATA_CACHE


async def _load_autocomplete(env):
    global AUTOCOMPLETE_CACHE
    if AUTOCOMPLETE_CACHE is None:
        response = await env.ASSETS.fetch("https://worker-assets/autocomplete.json")
        if response.status != 200:
            raise RuntimeError("Worker autocomplete data could not be loaded.")
        AUTOCOMPLETE_CACHE = await response.json()
    return AUTOCOMPLETE_CACHE


class Default(WorkerEntrypoint):
    async def _finish_interaction(self, interaction):
        try:
            towers, skills = await _load_data(self.env)
            if interaction["type"] == 3:
                response = handle_component(interaction, towers)
            else:
                response = handle_command(interaction, towers, skills)
            payload = response.get("data", {})
        except Exception as error:
            print(f"Discord interaction failed: {error}")
            payload = {
                "flags": 1 << 15,
                "components": [{
                    "type": 17,
                    "components": [{
                        "type": 10,
                        "content": "The command failed. Check the Worker logs for details.",
                    }],
                }],
            }

        application_id = interaction.get("application_id")
        token = interaction.get("token")
        if not application_id or not token:
            print("Cannot edit the deferred Discord response: application ID or interaction token is missing.")
            return

        payload["flags"] = payload.get("flags", 0) & ~(1 << 6)
        payload["flags"] |= 1 << 15
        try:
            edit_response = await fetch(
                f"https://discord.com/api/v10/webhooks/{application_id}/{token}/messages/@original",
                method="PATCH",
                headers={"Content-Type": "application/json"},
                body=json.dumps(payload),
            )
            if edit_response.status >= 400:
                detail = await edit_response.text()
                print(
                    f"Discord rejected the interaction response edit with status "
                    f"{edit_response.status}: {detail[:1500]}"
                )
        except Exception as error:
            print(f"Could not edit the deferred Discord response: {error}")

    async def fetch(self, request):
        path = urlsplit(request.url).path.rstrip("/") or "/"
        if request.method == "GET" or path != "/":
            return await handle_web_request(request, self.env, Response, fetch)

        if request.method != "POST":
            return Response("Method Not Allowed", status=405)

        signature = request.headers.get("X-Signature-Ed25519")
        timestamp = request.headers.get("X-Signature-Timestamp")
        if not signature or not timestamp:
            return Response("Unauthorized", status=401)

        body = await request.text()
        public_key = getattr(self.env, "DISCORD_PUBLIC_KEY", "")
        try:
            if len(public_key) != 64:
                print(f"Discord public key has length {len(public_key)}; expected 64 hex characters.")
            key = await crypto.subtle.importKey(
                "raw",
                _uint8(bytes.fromhex(public_key)),
                to_js({"name": "Ed25519"}),
                False,
                to_js(["verify"]),
            )
            valid = await crypto.subtle.verify(
                to_js({"name": "Ed25519"}),
                key,
                _uint8(bytes.fromhex(signature)),
                _uint8((timestamp + body).encode("utf-8")),
            )
        except Exception as error:
            print(f"Discord signature verification error: {type(error).__name__}: {error}")
            valid = False

        if not valid:
            print("Discord signature verification failed. Confirm the endpoint and public key belong to the same application.")
            return Response("Unauthorized", status=401)

        try:
            interaction = json.loads(body)
        except json.JSONDecodeError:
            return Response("Bad Request", status=400)

        if interaction.get("type") == 1:
            return _json_response({"type": 1})

        if interaction.get("type") == 4:
            try:
                catalog = await _load_autocomplete(self.env)
                response = handle_autocomplete(interaction, catalog)
                return _json_response(response)
            except Exception as error:
                print(f"Discord interaction failed: {error}")
                return _json_response({
                    "type": 8,
                    "data": {"choices": []},
                })

        if interaction.get("type") in (2, 3):
            self.ctx.waitUntil(self._finish_interaction(interaction))
            if interaction["type"] == 3:
                return _json_response({"type": 6})
            return _json_response({"type": 5, "data": {"flags": 1 << 15}})

        return _json_response({
            "type": 4,
            "data": {"content": "This interaction type is not supported yet.", "flags": 64},
        })