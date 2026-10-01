import base64
import html
import json
import math
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

CLIENT_ID = "755049463961092178"
TOWERS_CACHE = None


def _html(body, response_class, status=200):
    return response_class(
        body,
        status=status,
        headers={"Content-Type": "text/html; charset=utf-8"},
    )


def _escape(value):
    return html.escape(str(value), quote=True)


def _json_for_script(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")


def _page_url(request):
    return urlsplit(request.url)


def _base_url(parts):
    return f"{parts.scheme}://{parts.netloc}"


def _encode_state(value):
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _decode_state(value):
    if not value:
        return {}
    try:
        return json.loads(base64.b64decode(value).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _safe_int(value, fallback=0):
    try:
        result = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return fallback
    return max(result, 0)


def _safe_float(value, fallback=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return max(result, 0.0) if math.isfinite(result) else fallback


def _exp_requirement(next_level):
    if next_level <= 0:
        return 0
    if next_level <= 10:
        return 45 + next_level * 3.5
    if next_level <= 40:
        return next_level * 8
    return 260 + next_level * 1.5


def _cumulative_progress(level, exp):
    return exp + sum(_exp_requirement(next_level) for next_level in range(1, level + 1))


def _nice_time(seconds):
    return datetime.fromtimestamp(float(seconds), timezone.utc).strftime("%Y-%m-%d %H:%M")


def _database(env):
    try:
        database = env.DB
    except Exception:
        database = None
    if database is None:
        raise RuntimeError("D1 is not configured. Add the DB binding described in worker/README.md.")
    return database


def _rows_to_python(rows):
    if hasattr(rows, "to_py"):
        rows = rows.to_py()
    return [row.to_py() if hasattr(row, "to_py") else dict(row) for row in rows]


async def _query(env, sql, *values):
    statement = _database(env).prepare(sql)
    if values:
        statement = statement.bind(*values)
    result = await statement.all()
    return _rows_to_python(result.results)


async def _insert_progress(env, user_id, level, exp):
    await _database(env).prepare(
        "INSERT INTO tds (user_id, level, exp, timestamp) VALUES (?1, ?2, ?3, ?4)"
    ).bind(user_id, level, exp, time.time()).run()


async def _load_users(env):
    rows = await _query(env, "SELECT DISTINCT user_id FROM tds ORDER BY user_id")
    return [str(row["user_id"]) for row in rows]


async def _load_progress(env, user_id=None):
    if user_id:
        return await _query(
            env,
            "SELECT user_id, level, exp, timestamp FROM tds WHERE user_id = ?1 ORDER BY timestamp ASC",
            user_id,
        )
    return await _query(
        env,
        "SELECT user_id, level, exp, timestamp FROM tds ORDER BY timestamp ASC",
    )


async def _load_scraped_towers(env):
    global TOWERS_CACHE
    if TOWERS_CACHE is None:
        response = await env.ASSETS.fetch("https://worker-assets/towers.json")
        if response.status != 200:
            raise RuntimeError("Scraped tower data could not be loaded.")
        TOWERS_CACHE = await response.json()
    return TOWERS_CACHE


async def _exchange_code(code, redirect_uri, env, fetch_function):
    client_secret = str(getattr(env, "CLIENT_SECRET", "") or "").strip()
    if not client_secret:
        raise RuntimeError("Missing CLIENT_SECRET Worker secret.")
    response = await fetch_function(
        "https://discord.com/api/v10/oauth2/token",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=urlencode({
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }),
    )
    if response.status >= 400:
        raise RuntimeError(f"Discord token exchange failed: {await response.text()}")
    token_data = await response.json()
    user_response = await fetch_function(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    if user_response.status >= 400:
        raise RuntimeError("Discord did not return the authorized user's profile.")
    user_data = await user_response.json()
    return str(user_data["id"])


def _authorize_url(redirect_uri, scope, state=None):
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
    }
    if state is not None:
        params["state"] = state
    return "https://discord.com/oauth2/authorize?" + urlencode(params)


def _root_page():
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TDS Stats</title>
<style>body{font-family:system-ui,sans-serif;background:#121214;color:#e4e4e7;max-width:440px;margin:60px auto;padding:24px;text-align:center}h1{color:#fff;font-size:24px}p{color:#a1a1aa;line-height:1.5}.links{display:grid;gap:12px;margin-top:28px}a{display:block;padding:14px;border:1px solid #35353a;border-radius:8px;background:#1c1c1f;color:#fff;text-decoration:none;font-weight:600}a:hover{background:#29292e}</style></head>
<body><h1>TDS Stats</h1><p>Tracker, widget updater, and community tower concepts.</p><nav class="links"><a href="/tracker">Tracker</a><a href="/widget">Widget</a><a href="/towers">Towers</a></nav></body></html>"""


def _tracker_page(rows, users, selected_user):
    points = []
    for row in rows:
        level = _safe_int(row.get("level"))
        exp = _safe_float(row.get("exp"))
        timestamp = _safe_float(row.get("timestamp"))
        points.append({
            "level": level,
            "exp": exp,
            "timestamp": timestamp,
            "time": _nice_time(timestamp),
            "progress": _cumulative_progress(level, exp),
        })

    user_options = "".join(
        f'<option value="{_escape(user)}"{" selected" if user == selected_user else ""}>{_escape(user)}</option>'
        for user in users
    )
    current_level = points[-1]["level"] if points else 0
    wanted_level = current_level + 1 if points else 1
    points_json = _json_for_script(points)
    page = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TDS Stats</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#121214;color:#e4e4e7;max-width:920px;margin:32px auto;padding:20px}h1,h2{color:#fff}h1{font-size:24px}h2{font-size:18px;margin-top:0}p,label{color:#a1a1aa}a{color:#aaa}.panel{margin:16px 0;padding:18px;border:1px solid #303036;border-radius:10px;background:#18181b}.stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.stat{padding:12px;border:1px solid #303036;border-radius:7px;background:#202024}.stat strong,.stat span{display:block}.stat strong{color:#fff;font-size:18px}.stat span{color:#aaa;font-size:13px}select,input[type=number],input[type=range],button{width:100%;margin-top:7px}select,input[type=number]{padding:10px;border:1px solid #36363c;border-radius:6px;background:#202024;color:#fff;font-size:16px}button{padding:11px;border:0;border-radius:6px;background:#3e5968;color:white;font-weight:600;cursor:pointer}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}svg{width:100%;height:auto;background:#141418;border-radius:8px}.note{font-size:13px;line-height:1.5}.target{margin-top:12px}@media(max-width:650px){body{margin:12px auto;padding:14px}.stats,.row{grid-template-columns:1fr}}
</style></head><body>
<h1>TDS Stats</h1><p><a href="/">&larr; back</a></p>
<form method="get"><label for="user">User</label><select id="user" name="user" onchange="this.form.submit()">__USER_OPTIONS__</select></form>
<section class="panel"><div class="stats">
<div class="stat"><strong id="records">0</strong><span>records</span></div><div class="stat"><strong id="level">0</strong><span>current level</span></div>
<div class="stat"><strong id="gained">0</strong><span>levels gained in zoom</span></div><div class="stat"><strong id="total">0</strong><span>EXP gained in zoom</span></div>
<div class="stat"><strong id="average">0</strong><span>average EXP/day</span></div><div class="stat"><strong id="next">0</strong><span>EXP until next level</span></div>
<div class="stat" style="grid-column:1/-1"><strong id="window">No data</strong><span id="span"></span></div></div>
<div class="row"><label>Zoom start<input id="start" type="range" min="0" max="__MAX__" value="0"><span id="startLabel"></span></label><label>Zoom end<input id="end" type="range" min="0" max="__MAX__" value="__MAX__"><span id="endLabel"></span></label></div>
<div style="margin-top:16px;overflow:hidden"><svg id="graph" viewBox="0 0 980 480" role="img" aria-label="Progress graph"></svg></div><p class="note">The X axis follows record order; the line shows cumulative progress.</p></section>
<section class="panel"><h2>Add Record</h2><p>Enter a level and EXP value, then authorize with Discord.</p><form method="post" action="/tracker/authorize"><div class="row"><label>Level<input name="level" type="number" min="0" step="1" value="__LEVEL__"></label><label>EXP<input name="exp" type="number" min="0" step="0.1" value="0"></label></div><button>Authorize with Discord</button></form></section>
<section class="panel"><h2>Level Target</h2><p>Estimate the time to a target using the selected graph window's average EXP/day.</p><div class="row"><label>Current level<input id="from" type="number" min="0" value="__LEVEL__"></label><label>Wanted level<input id="wanted" type="number" min="0" value="__WANTED__"></label></div><div class="stats target"><div class="stat"><strong id="needed">0</strong><span>EXP needed</span></div><div class="stat"><strong id="rate">0</strong><span>average EXP/day</span></div><div class="stat"><strong id="duration">n/a</strong><span>estimated time</span></div><div class="stat"><strong id="apart">0</strong><span>levels apart</span></div></div></section>
<script>
const points=__POINTS__,$=id=>document.getElementById(id),start=$('start'),end=$('end');
function req(n){if(n<=0)return 0;if(n<=10)return 45+n*3.5;if(n<=40)return n*8;return 260+n*1.5}function fmt(n){return Number(n).toLocaleString('en-US',{maximumFractionDigits:2})}
function render(){if(!points.length){$('graph').innerHTML='<text x="30" y="40" fill="#aaa">No data available</text>';return}let a=+start.value,b=+end.value;if(a>b)[a,b]=[b,a];let data=points.slice(a,b+1),x0=70,y0=40,w=840,h=400,lo=Math.min(...data.map(p=>p.progress)),hi=Math.max(...data.map(p=>p.progress)),span=Math.max(hi-lo,1);let coords=data.map((p,i)=>`${(x0+i/Math.max(data.length-1,1)*w).toFixed(2)},${(y0+h-(p.progress-lo)/span*h).toFixed(2)}`).join(' ');$('graph').innerHTML='<rect width="980" height="480" rx="12" fill="#141418"/><g stroke="#303036"><line x1="70" y1="40" x2="70" y2="440"/><line x1="70" y1="440" x2="910" y2="440"/><line x1="70" y1="140" x2="910" y2="140"/><line x1="70" y1="240" x2="910" y2="240"/><line x1="70" y1="340" x2="910" y2="340"/></g><polyline fill="none" stroke="#60a5fa" stroke-width="3" points="'+coords+'"/>';let first=data[0],last=data[data.length-1],seconds=Math.max(last.timestamp-first.timestamp,0),exp=last.progress-first.progress,rate=seconds?exp/(seconds/86400):0,hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60);$('records').textContent=data.length;$('level').textContent=last.level;$('gained').textContent=last.level-first.level;$('total').textContent=fmt(exp);$('average').textContent=fmt(rate);$('next').textContent=fmt(Math.max(req(last.level+1)-last.exp,0));$('window').textContent=first.time+' → '+last.time;$('span').textContent='Time span: '+hours+'h '+minutes+'m';$('startLabel').textContent='Record '+(a+1)+' / '+points.length;$('endLabel').textContent='Record '+(b+1)+' / '+points.length;let from=Math.max(0,+$('from').value||0),wanted=Math.max(0,+$('wanted').value||0),needed=0;for(let l=from+1;l<=wanted;l++)needed+=req(l);$('needed').textContent=fmt(needed);$('rate').textContent=fmt(rate);$('apart').textContent=Math.max(0,wanted-from);$('duration').textContent=rate>0?fmt(needed/rate)+' days':'n/a'}
start.addEventListener('input',render);end.addEventListener('input',render);$('from').addEventListener('input',render);$('wanted').addEventListener('input',render);render();
</script></body></html>"""
    return (
        page.replace("__USER_OPTIONS__", user_options)
        .replace("__MAX__", str(max(len(points) - 1, 0)))
        .replace("__LEVEL__", str(current_level))
        .replace("__WANTED__", str(wanted_level))
        .replace("__POINTS__", points_json)
    )


def _widget_page():
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TDS Stats Updater</title>
<style>*{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#121214;color:#e4e4e7;max-width:440px;margin:36px auto;padding:22px}h1{color:#fff;font-size:24px}p,label{color:#aaa}label{display:block;margin-top:14px;font-size:14px}input{width:100%;padding:10px;margin-top:6px;border:1px solid #36363c;border-radius:6px;background:#202024;color:white;font-size:16px}button{width:100%;padding:12px;margin-top:24px;border:0;border-radius:6px;background:#3e5968;color:#fff;font-size:16px;font-weight:600;cursor:pointer}</style></head>
<body><h1>TDS Stats</h1><p>This updater is configured for the original profile widget.</p><p><a href="/">&larr; back</a></p>
<form action="/widget/submit" method="post" id="statsForm">
<label>Level<input name="level" value="1"></label><label>Coins<input name="coins" value="0"></label><label>Gems<input name="gems" value="0"></label><label>Tower<input name="tower" value="Scout"></label><label>Wins<input name="wins" value="0"></label><label>Losses<input name="losses" value="0"></label><label>Username<input name="username" value=""></label><button>Submit and Authorize</button></form>
<script>const key='tdsStatsForm',form=document.getElementById('statsForm'),inputs=form.querySelectorAll('input');try{const saved=JSON.parse(localStorage.getItem(key)||'{}');inputs.forEach(i=>{if(saved[i.name]!==undefined)i.value=saved[i.name]})}catch(e){}function save(){const data={};inputs.forEach(i=>data[i.name]=i.value);localStorage.setItem(key,JSON.stringify(data))}inputs.forEach(i=>i.addEventListener('input',save));</script></body></html>"""


def _towers_page(towers):
    cards = []
    for slug, tower in sorted(towers.items(), key=lambda item: item[1].get("name", item[0]).lower()):
        info = tower.get("info", {})
        general = info.get("general", {})
        cards.append({
            "slug": slug,
            "name": tower.get("name", slug.replace("_", " ").title()),
            "image": tower.get("image", ""),
            "url": tower.get("url", ""),
            "role": general.get("Role", ""),
            "placement": general.get("Placement", ""),
            "description": " ".join(info.get("tooltips", [])),
        })

    page = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TDS Towers</title>
<style>*{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#121214;color:#e4e4e7;max-width:1100px;margin:32px auto;padding:20px}h1{color:#fff;font-size:24px}p{color:#aaa}.top{display:flex;gap:10px;flex-wrap:wrap}input{flex:1;min-width:200px;padding:10px;border:1px solid #36363c;border-radius:6px;background:#202024;color:#fff;font-size:16px}.status{color:#aaa;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}.card{border:1px solid #303036;border-radius:8px;background:#19191d;overflow:hidden}.card img{width:100%;height:140px;object-fit:cover;background:#222}.card-body{padding:12px}.card p{font-size:13px;line-height:1.4}.meta{display:flex;gap:8px;color:#9ca3af;font-size:12px}.foot{display:flex;justify-content:space-between;align-items:center;font-size:12px;margin-top:12px}.foot a{color:#60a5fa;text-decoration:none}@media(max-width:650px){body{padding:14px}}</style></head>
<body><h1>TDS Towers</h1><p><a href="/">&larr; back</a></p><p>Towers and details scraped from the local game data.</p><div class="top"><input id="search" type="search" placeholder="Search tower name, role, or description"></div><div class="status" id="status"></div><div class="grid" id="grid"></div>
<script>
const TOWERS=__TOWERS__,grid=document.getElementById('grid'),status=document.getElementById('status'),search=document.getElementById('search');
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function draw(){const q=search.value.toLowerCase().trim(),items=TOWERS.filter(t=>!q||[t.name,t.role,t.description].some(v=>String(v||'').toLowerCase().includes(q)));status.textContent=items.length+' of '+TOWERS.length+' towers';grid.innerHTML=items.length?items.map(t=>'<article class="card">'+(t.image?'<img loading="lazy" src="'+esc(t.image)+'" alt="'+esc(t.name)+'">':'')+'<div class="card-body"><h2>'+esc(t.name)+'</h2><div class="meta">'+(t.role?'<span>'+esc(t.role)+'</span>':'')+(t.placement?'<span>'+esc(t.placement)+'</span>':'')+'</div><p>'+esc(t.description||'No description available.')+'</p><div class="foot"><span></span>'+(t.url?'<a href="'+esc(t.url)+'" target="_blank" rel="noopener">Wiki page</a>':'')+'</div></div></article>').join(''):'<p>No towers found.</p>'}
search.addEventListener('input',draw);draw();
</script></body></html>"""
    return page.replace("__TOWERS__", _json_for_script(cards))


async def _exchange_code(code, redirect_uri, env, fetch_function):
    client_secret = str(getattr(env, "CLIENT_SECRET", "") or "").strip()
    if not client_secret:
        raise RuntimeError("Missing CLIENT_SECRET Worker secret.")
    response = await fetch_function(
        "https://discord.com/api/v10/oauth2/token",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=urlencode({
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }),
    )
    if response.status >= 400:
        raise RuntimeError(f"Discord token exchange failed: {await response.text()}")
    token_data = await response.json()
    user_response = await fetch_function(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    if user_response.status >= 400:
        raise RuntimeError("Failed to fetch the authorized Discord user.")
    return str((await user_response.json())["id"])


async def _update_widget(code, redirect_uri, stats, env, fetch_function):
    try:
        token_data = await _oauth_token(code, redirect_uri, env, fetch_function)
        user_response = await fetch_function(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        if user_response.status >= 400:
            raise RuntimeError("Failed to fetch Discord user ID.")
        user_id = str((await user_response.json())["id"])
        bot_token = str(getattr(env, "BOT_TOKEN", "") or "").strip()
        if not bot_token:
            raise RuntimeError("Missing BOT_TOKEN Worker secret.")
        auth_header = bot_token if bot_token.startswith("Bot ") else f"Bot {bot_token}"
        dynamic = [
            {"type": 1, "name": "level", "value": str(stats.get("level") or "1")},
            {"type": 1, "name": "coins", "value": str(stats.get("coins") or "0")},
            {"type": 1, "name": "gems", "value": str(stats.get("gems") or "0")},
            {"type": 1, "name": "tower", "value": str(stats.get("tower") or "None")},
            {"type": 1, "name": "wins", "value": str(stats.get("wins") or "0")},
            {"type": 1, "name": "losses", "value": str(stats.get("losses") or "0")},
            {"type": 1, "name": "user", "value": str(stats.get("username") or "None")},
        ]
        profile = await fetch_function(
            f"https://discord.com/api/v9/applications/{CLIENT_ID}/users/{user_id}/identities/0/profile",
            method="PATCH",
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            body=json.dumps({"username": user_id, "data": {"dynamic": dynamic}}),
        )
        detail = await profile.text()
        if profile.status < 400:
            return True, "Discord profile updated."
        try:
            detail = json.loads(detail).get("message", detail)
        except (ValueError, AttributeError):
            pass
        return False, f"Discord profile update failed: {detail}"
    except Exception as error:
        return False, str(error)


async def _oauth_token(code, redirect_uri, env, fetch_function):
    client_secret = str(getattr(env, "CLIENT_SECRET", "") or "").strip()
    if not client_secret:
        raise RuntimeError("Missing CLIENT_SECRET Worker secret.")
    response = await fetch_function(
        "https://discord.com/api/v10/oauth2/token",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=urlencode({
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }),
    )
    if response.status >= 400:
        raise RuntimeError(f"Discord token exchange failed: {await response.text()}")
    return await response.json()


def _error_page(title, message, response_class, status=400):
    return _html(
        f'<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f'<title>{_escape(title)}</title><body style="font-family:system-ui;background:#121214;color:#eee;max-width:720px;margin:50px auto;padding:20px">'
        f'<h1>{_escape(title)}</h1><p>{_escape(message)}</p><p><a href="/" style="color:#aaa">Back home</a></p></body></html>',
        response_class,
        status,
    )


async def handle_web_request(request, env, response_class, fetch_function):
    parts = _page_url(request)
    path = parts.path.rstrip("/") or "/"
    query = parse_qs(parts.query)
    method = str(request.method)

    if method == "GET" and path == "/":
        return _html(_root_page(), response_class)

    if path == "/tracker" and method == "GET":
        redirect_uri = f"{_base_url(parts)}/tracker"
        if query.get("code"):
            try:
                user_id = await _exchange_code(query["code"][0], redirect_uri, env, fetch_function)
                state = _decode_state(query.get("state", [""])[0])
                level = _safe_int(state.get("level"))
                exp = _safe_float(state.get("exp"))
                await _insert_progress(env, user_id, level, exp)
                return response_class.redirect(
                    f"{_base_url(parts)}/tracker?user={user_id}",
                    303,
                )
            except Exception as error:
                return _error_page("Failed to update tracker", str(error), response_class, 500)
        try:
            users = await _load_users(env)
            selected_user = query.get("user", [None])[0]
            if selected_user not in users:
                selected_user = users[0] if users else None
            rows = await _load_progress(env, selected_user)
            return _html(_tracker_page(rows, users, selected_user), response_class)
        except Exception as error:
            return _error_page("Tracker unavailable", str(error), response_class, 503)

    if path == "/tracker/authorize" and method == "POST":
        try:
            form = await request.form_data()
            level = _safe_int(form.get("level"))
            exp = _safe_float(form.get("exp"))
            redirect_uri = f"{_base_url(parts)}/tracker"
            state = _encode_state({"level": level, "exp": exp})
            location = _authorize_url(redirect_uri, "identify", state)
            return response_class.redirect(location, 303)
        except Exception as error:
            return _error_page("Could not start Discord authorization", str(error), response_class, 400)

    if path == "/widget" and method == "GET":
        redirect_uri = f"{_base_url(parts)}/widget"
        if query.get("error"):
            detail = query.get("error_description", ["Authorization was denied."])[0]
            return _error_page("Authorization failed", f"{query['error'][0]}: {detail}", response_class)
        if query.get("code"):
            stats = _decode_state(query.get("state", [""])[0])
            success, message = await _update_widget(query["code"][0], redirect_uri, stats, env, fetch_function)
            return _html(
                f'<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                f'<title>Widget update</title><body style="font-family:system-ui;background:#121214;color:#eee;max-width:720px;margin:50px auto;padding:20px">'
                f'<h1>{"Successfully updated" if success else "Update failed"}</h1><p>{_escape(message)}</p></body></html>',
                response_class,
                200 if success else 400,
            )
        return _html(_widget_page(), response_class)

    if path == "/widget/submit" and method == "POST":
        try:
            form = await request.form_data()
            stats = {}
            for key, value in form.items():
                value = str(value or "0")
                stats[key] = value.replace(",", "") if key in {"level", "coins", "gems", "wins", "losses"} else value
            state = _encode_state(stats)
            redirect_uri = f"{_base_url(parts)}/widget"
            location = _authorize_url(redirect_uri, "identify sdk.social_layer", state)
            return response_class.redirect(location, 303)
        except Exception as error:
            return _error_page("Could not start Discord authorization", str(error), response_class, 400)

    if method == "GET" and path == "/towers":
        try:
            towers = await _load_scraped_towers(env)
            return _html(_towers_page(towers), response_class)
        except Exception as error:
            return _error_page("Tower list unavailable", str(error), response_class, 503)

    return _html(
        "<!doctype html><html><meta charset=\"utf-8\"><title>Not found</title>"
        "<body style=\"font-family:system-ui;background:#121214;color:#eee;max-width:720px;margin:50px auto;padding:20px\">"
        "<h1>Not found</h1><p><a href=\"/\" style=\"color:#aaa\">Back home</a></p></body></html>",
        response_class,
        404,
    )
