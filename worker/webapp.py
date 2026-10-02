import base64
import hashlib
import hmac
import html
import json
import math
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

CLIENT_ID = "755049463961092178"
TOWERS_CACHE = None
ENEMIES_CACHE = None


def _html(body, response_class, status=200):
    return response_class(
        body,
        status=status,
        headers={"Content-Type": "text/html; charset=utf-8"},
    )


def _json_response(value, response_class, status=200):
    return response_class(
        json.dumps(value, ensure_ascii=True, separators=(",", ":")),
        status=status,
        headers={"Content-Type": "application/json; charset=utf-8"},
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


def _encode_signed_state(value, secret):
    payload = _encode_state(value)
    signature = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _decode_signed_state(value, secret):
    if not secret or "." not in value:
        return None
    payload, signature = value.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return _decode_state(payload)


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


def _parse_timestamp(value):
    """Parse an optional datetime-local value (interpreted as UTC) into a unix timestamp."""
    value = str(value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid timestamp. Use the date and time picker.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    timestamp = parsed.timestamp()
    if timestamp < 0:
        raise ValueError("Timestamp is too far in the past.")
    if timestamp > time.time() + 60:
        raise ValueError("Timestamp cannot be in the future.")
    return timestamp


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


async def _insert_progress(env, user_id, level, exp, timestamp=None):
    now = time.time()
    if not timestamp or timestamp > now:
        timestamp = now
    await _database(env).prepare(
        "INSERT INTO tds (user_id, level, exp, timestamp) VALUES (?1, ?2, ?3, ?4)"
    ).bind(user_id, level, exp, timestamp).run()


async def _delete_progress(env, user_id, record_ids):
    ids = list(dict.fromkeys(int(record_id) for record_id in record_ids if int(record_id) > 0))
    if not ids:
        return 0
    if len(ids) > 99:
        raise ValueError("Select no more than 99 records at a time.")
    placeholders = ", ".join(f"?{index + 2}" for index in range(len(ids)))
    owned_rows = await _query(
        env,
        f"SELECT rowid AS id FROM tds WHERE user_id = ?1 AND rowid IN ({placeholders})",
        user_id,
        *ids,
    )
    owned_ids = [int(row["id"]) for row in owned_rows]
    if not owned_ids:
        return 0
    delete_placeholders = ", ".join(f"?{index + 2}" for index in range(len(owned_ids)))
    await _database(env).prepare(
        f"DELETE FROM tds WHERE user_id = ?1 AND rowid IN ({delete_placeholders})"
    ).bind(user_id, *owned_ids).run()
    return len(owned_ids)


async def _load_users(env):
    rows = await _query(env, "SELECT DISTINCT user_id FROM tds ORDER BY user_id")
    return [str(row["user_id"]) for row in rows]


async def _load_progress(env, user_id=None):
    if user_id:
        return await _query(
            env,
            "SELECT rowid AS id, user_id, level, exp, timestamp FROM tds WHERE user_id = ?1 ORDER BY timestamp ASC",
            user_id,
        )
    return await _query(
        env,
        "SELECT rowid AS id, user_id, level, exp, timestamp FROM tds ORDER BY timestamp ASC",
    )


async def _load_scraped_towers(env):
    global TOWERS_CACHE
    if TOWERS_CACHE is None:
        response = await env.ASSETS.fetch("https://worker-assets/towers.json")
        if response.status != 200:
            raise RuntimeError("Scraped tower data could not be loaded.")
        TOWERS_CACHE = await response.json()
    return TOWERS_CACHE


async def _load_scraped_enemies(env):
    global ENEMIES_CACHE
    if ENEMIES_CACHE is None:
        response = await env.ASSETS.fetch("https://worker-assets/enemies.json")
        if response.status != 200:
            raise RuntimeError("Scraped enemy data could not be loaded.")
        ENEMIES_CACHE = await response.json()
    return ENEMIES_CACHE


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
<body><h1>TDS Stats</h1><p>Tracker, widget updater, tower and enemy stats.</p><nav class="links"><a href="/tracker">Tracker</a><a href="/widget">Widget</a><a href="/towers">Towers</a><a href="/enemies">Enemies</a></nav></body></html>"""


def _tracker_page(rows, users, selected_user, deleted_count=None):
    points = []
    for row in rows:
        level = _safe_int(row.get("level"))
        exp = _safe_float(row.get("exp"))
        timestamp = _safe_float(row.get("timestamp"))
        points.append({
            "id": _safe_int(row.get("id")),
            "level": level,
            "exp": exp,
            "timestamp": timestamp,
            "time": _nice_time(timestamp),
            "progress": _cumulative_progress(level, exp),
        })

    user_choices = list(users)
    if selected_user and selected_user not in user_choices:
        user_choices.insert(0, selected_user)
    user_options = "".join(
        f'<option value="{_escape(user)}"{" selected" if user == selected_user else ""}>{_escape(user)}</option>'
        for user in user_choices
    )
    current_level = points[-1]["level"] if points else 0
    wanted_level = current_level + 1 if points else 1
    points_json = _json_for_script(points)
    record_options = "".join(
        f'<option value="{point["id"]}">{_escape(point["time"])} · Lv {point["level"]} · {_escape(point["exp"])} EXP</option>'
        for point in reversed(points)
        if point["id"] > 0
    ) or '<option disabled>No records to show</option>'
    delete_notice = (
        f'<p class="note">Deleted {deleted_count} record{"s" if deleted_count != 1 else ""} after Discord authorization.</p>'
        if deleted_count is not None else ""
    )
    page = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TDS Stats</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#121214;color:#e4e4e7;max-width:920px;margin:32px auto;padding:20px;color-scheme:dark}h1,h2{color:#fff}h1{font-size:24px}h2{font-size:18px;margin-top:0}p,label{color:#a1a1aa}a{color:#aaa}.panel{margin:16px 0;padding:18px;border:1px solid #303036;border-radius:10px;background:#18181b}.stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.stat{padding:12px;border:1px solid #303036;border-radius:7px;background:#202024}.stat strong,.stat span{display:block}.stat strong{color:#fff;font-size:18px}.stat span{color:#aaa;font-size:13px}select,input[type=number],input[type=datetime-local],input[type=range],button{width:100%;margin-top:7px}select,input[type=number],input[type=datetime-local]{padding:10px;border:1px solid #36363c;border-radius:6px;background:#202024;color:#fff;font-size:16px}select[multiple]{padding:6px}select[multiple] option{padding:5px 6px;border-radius:4px}button{padding:11px;border:0;border-radius:6px;background:#3e5968;color:white;font-weight:600;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.row-full{margin-top:12px;display:block}svg{width:100%;height:auto;background:#141418;border-radius:8px}.note{font-size:13px;line-height:1.5}.target{margin-top:12px}@media(max-width:650px){body{margin:12px auto;padding:14px}.stats,.row{grid-template-columns:1fr}}
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
<section class="panel"><h2>Records</h2>__DELETE_NOTICE__<form method="post" action="/tracker/delete/authorize" id="deleteRecords"><input type="hidden" name="ids" id="selectedRecordIds"><select id="recordSelect" multiple size="8" aria-label="Tracker records">__RECORD_OPTIONS__</select><p class="note" id="deleteStatus">Select records (Ctrl/Cmd-click or Shift-click for multiple); Discord authorization is required before they are deleted.</p><button id="deleteButton" type="submit" disabled>Select records to delete</button></form></section>
<section class="panel"><h2>Add Record</h2><p>Enter a level and EXP value, then authorize with Discord.</p><form method="post" action="/tracker/authorize"><div class="row"><label>Level<input name="level" type="number" min="0" step="1" value="__LEVEL__"></label><label>EXP<input name="exp" type="number" min="0" step="0.1" value="0"></label></div><div class="row-full"><label>Timestamp (UTC, optional)<input name="timestamp" type="datetime-local" step="60"></label><p class="note">Leave blank to use the current time. Fill it in to add a previous record.</p></div><button>Authorize with Discord</button></form></section>
<section class="panel"><h2>Level Target</h2><p>Estimate the time to a target using the selected graph window's average EXP/day.</p><div class="row"><label>Current level<input id="from" type="number" min="0" value="__LEVEL__"></label><label>Wanted level<input id="wanted" type="number" min="0" value="__WANTED__"></label></div><div class="stats target"><div class="stat"><strong id="needed">0</strong><span>EXP needed</span></div><div class="stat"><strong id="rate">0</strong><span>average EXP/day</span></div><div class="stat"><strong id="duration">n/a</strong><span>estimated time</span></div><div class="stat"><strong id="apart">0</strong><span>levels apart</span></div></div></section>
<script>
const points=__POINTS__,$=id=>document.getElementById(id),start=$('start'),end=$('end');
function req(n){if(n<=0)return 0;if(n<=10)return 45+n*3.5;if(n<=40)return n*8;return 260+n*1.5}function fmt(n){return Number(n).toLocaleString('en-US',{maximumFractionDigits:2})}
function render(){if(!points.length){$('graph').innerHTML='<text x="30" y="40" fill="#aaa">No data available</text>';return}let a=+start.value,b=+end.value;if(a>b)[a,b]=[b,a];let data=points.slice(a,b+1),x0=70,y0=40,w=840,h=400,lo=Math.min(...data.map(p=>p.progress)),hi=Math.max(...data.map(p=>p.progress)),span=Math.max(hi-lo,1);let coords=data.map((p,i)=>`${(x0+i/Math.max(data.length-1,1)*w).toFixed(2)},${(y0+h-(p.progress-lo)/span*h).toFixed(2)}`).join(' ');$('graph').innerHTML='<rect width="980" height="480" rx="12" fill="#141418"/><g stroke="#303036"><line x1="70" y1="40" x2="70" y2="440"/><line x1="70" y1="440" x2="910" y2="440"/><line x1="70" y1="140" x2="910" y2="140"/><line x1="70" y1="240" x2="910" y2="240"/><line x1="70" y1="340" x2="910" y2="340"/></g><polyline fill="none" stroke="#60a5fa" stroke-width="3" points="'+coords+'"/>';let first=data[0],last=data[data.length-1],seconds=Math.max(last.timestamp-first.timestamp,0),exp=last.progress-first.progress,rate=seconds?exp/(seconds/86400):0,hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60);$('records').textContent=data.length;$('level').textContent=last.level;$('gained').textContent=last.level-first.level;$('total').textContent=fmt(exp);$('average').textContent=fmt(rate);$('next').textContent=fmt(Math.max(req(last.level+1)-last.exp,0));$('window').textContent=first.time+' → '+last.time;$('span').textContent='Time span: '+hours+'h '+minutes+'m';$('startLabel').textContent='Record '+(a+1)+' / '+points.length;$('endLabel').textContent='Record '+(b+1)+' / '+points.length;let from=Math.max(0,+$('from').value||0),wanted=Math.max(0,+$('wanted').value||0),needed=0;for(let l=from+1;l<=wanted;l++)needed+=req(l);$('needed').textContent=fmt(needed);$('rate').textContent=fmt(rate);$('apart').textContent=Math.max(0,wanted-from);$('duration').textContent=rate>0?fmt(needed/rate)+' days':'n/a'}
start.addEventListener('input',render);end.addEventListener('input',render);$('from').addEventListener('input',render);$('wanted').addEventListener('input',render);render();
</script></body></html>"""
    page = page.replace("</body>", """<script>
const recordSelect=document.getElementById('recordSelect'),selectedRecordIds=document.getElementById('selectedRecordIds'),deleteButton=document.getElementById('deleteButton'),deleteStatus=document.getElementById('deleteStatus');
function updateRecordSelection(){const selected=[...recordSelect.selectedOptions].filter(o=>!o.disabled);selectedRecordIds.value=selected.map(o=>o.value).join(',');deleteButton.disabled=selected.length===0||selected.length>99;deleteButton.textContent=selected.length?`Authorize and delete ${selected.length} selected record${selected.length===1?'':'s'}`:'Select records to delete';deleteStatus.textContent=selected.length>99?'Select 99 or fewer records at a time.':'Discord authorization is required before deletion.'}
recordSelect.addEventListener('change',updateRecordSelection);
</script></body>""", 1)
    return (
        page.replace("__USER_OPTIONS__", user_options)
        .replace("__DELETE_NOTICE__", delete_notice)
        .replace("__RECORD_OPTIONS__", record_options)
        .replace("__MAX__", str(max(len(points) - 1, 0)))
        .replace("__LEVEL__", str(current_level))
        .replace("__WANTED__", str(wanted_level))
        .replace("__POINTS__", points_json)
    )


def _widget_page():
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TDS Stats Updater</title>
<style>*{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#121214;color:#e4e4e7;max-width:440px;margin:36px auto;padding:22px}h1{color:#fff;font-size:24px}p,label{color:#aaa}label{display:block;margin-top:14px;font-size:14px}input{width:100%;padding:10px;margin-top:6px;border:1px solid #36363c;border-radius:6px;background:#202024;color:white;font-size:16px}button{width:100%;padding:12px;margin-top:24px;border:0;border-radius:6px;background:#3e5968;color:#fff;font-size:16px;font-weight:600;cursor:pointer}</style></head>
<body><h1>TDS Stats</h1><p>Don't use this if you're not me.</p><p><a href="/">&larr; back</a></p>
<form action="/widget/submit" method="post" id="statsForm">
<label>Level<input name="level" value="1"></label><label>Coins<input name="coins" value="0"></label><label>Gems<input name="gems" value="0"></label><label>Tower<input name="tower" value="Scout"></label><label>Wins<input name="wins" value="0"></label><label>Losses<input name="losses" value="0"></label><label>Username<input name="username" value=""></label><button>Submit and Authorize</button></form>
<script>const key='tdsStatsForm',form=document.getElementById('statsForm'),inputs=form.querySelectorAll('input');try{const saved=JSON.parse(localStorage.getItem(key)||'{}');inputs.forEach(i=>{if(saved[i.name]!==undefined)i.value=saved[i.name]})}catch(e){}function save(){const data={};inputs.forEach(i=>data[i.name]=i.value);localStorage.setItem(key,JSON.stringify(data))}inputs.forEach(i=>i.addEventListener('input',save));</script></body></html>"""


def _enemies_page(enemies):
    page = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>TDS Enemies</title>
<style>*{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#121214;color:#e4e4e7;max-width:1100px;margin:32px auto;padding:20px}h1{color:#fff;font-size:24px}p{color:#aaa}.top{display:flex;gap:10px;flex-wrap:wrap}.top input{flex:1;min-width:220px}input{padding:10px;border:1px solid #36363c;border-radius:6px;background:#202024;color:#fff;font-size:16px}.status{color:#aaa;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px}.card{border:1px solid #303036;border-radius:8px;background:#19191d;overflow:hidden}.card-media{display:block;width:100%;padding:0;border:0;background:#222;cursor:pointer}.card img{display:block;width:100%;height:190px;object-fit:contain}.card-body{padding:14px}.card h2{margin:0 0 8px;font-size:18px}.card-title{padding:0;border:0;background:none;color:#fff;font:inherit;text-align:left;cursor:pointer}.card-title:hover,.card-title:focus-visible{color:#8dc9ff}.card p{font-size:13px;line-height:1.45;min-height:3.8em}.meta{display:flex;gap:8px;color:#9ca3af;font-size:12px}.foot{display:flex;justify-content:space-between;align-items:center;font-size:12px;margin-top:12px}.foot a,.dialog-links a{color:#8dc9ff;text-decoration:none}.foot button,.dialog-close{padding:7px 10px;border:1px solid #444;background:#25252a;color:#eee;border-radius:5px;cursor:pointer}.card button:focus-visible,.dialog button:focus-visible{outline:2px solid #8dc9ff;outline-offset:2px}.dialog{width:min(900px,calc(100% - 28px));max-height:min(88vh,900px);padding:0;border:1px solid #45454d;border-radius:8px;background:#17171b;color:#e4e4e7}.dialog::backdrop{background:#000b}.dialog-header{position:sticky;top:0;z-index:1;display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:18px;border-bottom:1px solid #35353b;background:#17171b}.dialog-header h2{margin:0 0 6px;color:#fff;font-size:22px}.dialog-header .meta{display:grid;gap:4px;white-space:pre-line}.dialog-content{padding:18px}.detail-description{max-width:75ch;line-height:1.55;color:#d4d4d8;white-space:pre-line}.detail-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px;margin:20px 0}.detail-facts h3{margin:0 0 10px;color:#fff;font-size:15px}.fact-list{display:grid;grid-template-columns:minmax(110px,1fr) 1.2fr;gap:6px 12px;margin:0;font-size:13px}.fact-list dt{color:#a1a1aa}.fact-list dd{margin:0;overflow-wrap:anywhere;white-space:pre-line}.stats-section{border-top:1px solid #35353b;padding-top:16px;margin-top:16px}.stats-section h3{margin:0 0 10px;color:#fff;font-size:15px}.dialog-links{margin-top:16px;font-size:13px}@media(max-width:650px){body{margin:12px auto;padding:14px}.grid{grid-template-columns:1fr}.dialog{width:100%;max-height:100dvh;border-radius:0}.dialog-header,.dialog-content{padding:14px}.fact-list{grid-template-columns:1fr 1.2fr}}</style></head>
<body><h1>TDS Enemies</h1><p><a href="/">&larr; back</a></p><div class="top"><input id="search" type="search" placeholder="Search enemy name, mode, or stat" aria-label="Search enemies"></div><div class="status" id="status"></div><main class="grid" id="grid"></main>
<dialog class="dialog" id="enemyDialog" aria-labelledby="detailName"><header class="dialog-header"><div><h2 id="detailName"></h2><div class="meta" id="detailMeta"></div></div><button class="dialog-close" id="closeDialog" type="button">Close</button></header><div class="dialog-content"><p class="detail-description" id="detailDescription"></p><div class="detail-facts" id="detailFacts"></div><div id="detailStats"></div><div class="dialog-links" id="detailLinks"></div></div></dialog>
<script>
const ENEMIES=__ENEMIES__,grid=document.getElementById('grid'),status=document.getElementById('status'),search=document.getElementById('search');
function esc(value){return String(value||'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}
function formatModes(value){return String(value||'').split(/\r?\n/).map(line=>line.trim().replace(/^-\s*/,'')).filter(Boolean).join(', ')}
function formatWave(value){return formatModes(value)}
function displayName(enemy){const base=enemy.name.replaceAll('_',' '),suffix=enemy.slug.startsWith(base.toLowerCase().replaceAll(' ','_')+'_')?enemy.slug.slice(base.length+1).replaceAll('_',' '):'';return base+(suffix?' ('+suffix.replace(/\b\w/g,char=>char.toUpperCase())+')':'')}
function render(){const query=search.value.toLowerCase().trim();const items=ENEMIES.filter(enemy=>JSON.stringify(enemy).toLowerCase().includes(query));status.textContent=items.length+' of '+ENEMIES.length+' enemies';grid.innerHTML=items.length?items.map(enemy=>'<article class="card">'+(enemy.image?'<button class="card-media" type="button" data-slug="'+esc(enemy.slug)+'" aria-label="View '+esc(displayName(enemy))+' details"><img loading="lazy" src="'+esc(enemy.image)+'" alt=""></button>':'')+'<div class="card-body"><h2><button class="card-title" type="button" data-slug="'+esc(enemy.slug)+'">'+esc(displayName(enemy))+'</button></h2><div class="meta">'+(enemy.wave_debut?'<span>Wave '+esc(formatWave(enemy.wave_debut))+'</span>':'')+'</div><p>'+esc(enemy.description||'No description available.')+'</p><div class="foot"><button type="button" data-slug="'+esc(enemy.slug)+'">View details</button>'+(enemy.url?'<a href="'+esc(enemy.url)+'" target="_blank" rel="noopener">Wiki page</a>':'')+'</div></div></article>').join(''):'<p>No enemies found.</p>'}
function openEnemy(slug){const enemy=ENEMIES.find(item=>item.slug===slug);if(!enemy)return;const modes=formatModes(enemy.mode_appearance),wave=formatWave(enemy.wave_debut);detailName.textContent=displayName(enemy);detailMeta.innerHTML='';detailDescription.textContent=enemy.description||'No description available.';const facts=[['Modes',modes],['Wave debut',wave]].filter(([,value])=>value);detailFacts.innerHTML=facts.length?'<section><h3>Details</h3><dl class="fact-list">'+facts.map(([key,value])=>'<dt>'+esc(key)+'</dt><dd>'+esc(value)+'</dd>').join('')+'</dl></section>':'';detailStats.innerHTML=(enemy.variants||[]).map(variant=>'<section class="stats-section"><h3>'+esc(variant.name)+' stats</h3><dl class="fact-list">'+Object.entries(variant.stats||{}).map(([key,value])=>'<dt>'+esc(key)+'</dt><dd>'+esc(value)+'</dd>').join('')+'</dl>'+(variant.abilities&&variant.abilities.length?'<h3>Abilities</h3><div>'+variant.abilities.map(ability=>'<p>'+esc(ability.text||ability.name||ability)+'</p>').join('')+'</div>':'')+'</section>').join('');detailLinks.innerHTML=enemy.url?'<a href="'+esc(enemy.url)+'" target="_blank" rel="noopener">View wiki page</a>':'';enemyDialog.showModal()}
grid.addEventListener('click',event=>{const button=event.target.closest('[data-slug]');if(button)openEnemy(button.dataset.slug)});
document.getElementById('closeDialog').addEventListener('click',()=>enemyDialog.close());
enemyDialog.addEventListener('click',event=>{if(event.target===enemyDialog)enemyDialog.close()});
search.addEventListener('input',render);render();
</script></body></html>"""
    return page.replace("__ENEMIES__", _json_for_script(list(enemies.values())))


def _towers_page(towers):
    cards = []
    for slug, tower in towers.items():
        info = tower.get("info", {})
        general = info.get("general", {})
        cards.append({
            "slug": slug,
            "name": tower.get("name", slug.replace("_", " ").title()),
            "rarity": tower.get("rarity", ""),
            "image": tower.get("image", ""),
            "url": tower.get("url", ""),
            "role": general.get("Role", ""),
            "placement": general.get("Placement", ""),
            "description": tower.get("description") or " ".join(info.get("tooltips", [])) or general.get("Description", ""),
            "sections": tower.get("sections", {}),
            "general": {key: value for key, value in general.items() if key != "Description"},
            "regular": info.get("regular", {}),
            "pvp": info.get("pvp", {}),
            "tables": tower.get("tables", []),
        })
    rarities = list(dict.fromkeys(card["rarity"] for card in cards if card["rarity"]))
    rarity_options = '<option value="">All rarities</option>' + "".join(
        f'<option value="{_escape(rarity)}">{_escape(rarity)}</option>'
        for rarity in rarities
    )

    page = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TDS Towers</title>
<style>*{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#121214;color:#e4e4e7;max-width:1100px;margin:32px auto;padding:20px}h1{color:#fff;font-size:24px}p{color:#aaa}.top{display:flex;gap:10px;flex-wrap:wrap}input,select{min-width:200px;padding:10px;border:1px solid #36363c;border-radius:6px;background:#202024;color:#fff;font-size:16px}.top input{flex:1}.status{color:#aaa;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}.card{border:1px solid #303036;border-radius:8px;background:#19191d;overflow:hidden}.card-media{display:block;width:100%;padding:0;border:0;background:#222;cursor:pointer}.card img{display:block;width:100%;height:140px;object-fit:cover}.card-body{padding:12px}.card h2{margin:0;font-size:18px}.card-title{padding:0;border:0;background:none;color:#fff;font:inherit;text-align:left;cursor:pointer}.card-title:hover,.card-title:focus-visible{color:#8dc9ff}.card p{font-size:13px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.meta{display:flex;gap:8px;color:#9ca3af;font-size:12px}.foot{display:flex;justify-content:space-between;align-items:center;font-size:12px;margin-top:12px}.foot a{color:#8dc9ff;text-decoration:none}.foot button,.dialog-close{padding:7px 10px;border:1px solid #444;background:#25252a;color:#eee;border-radius:5px;cursor:pointer}.card button:focus-visible,.dialog button:focus-visible,.dialog select:focus-visible{outline:2px solid #8dc9ff;outline-offset:2px}.dialog{width:min(900px,calc(100% - 28px));max-height:min(88vh,900px);padding:0;border:1px solid #45454d;border-radius:8px;background:#17171b;color:#e4e4e7}.dialog::backdrop{background:#000b}.dialog-header{position:sticky;top:0;z-index:1;display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:18px;border-bottom:1px solid #35353b;background:#17171b}.dialog-header h2{margin:0 0 6px;color:#fff;font-size:22px}.dialog-content{padding:18px}.detail-description{max-width:75ch;line-height:1.55;color:#d4d4d8}.detail-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px;margin:20px 0}.detail-facts h3,.stats-section h3{margin:0 0 10px;color:#fff;font-size:15px}.fact-list{display:grid;grid-template-columns:minmax(110px,1fr) 1.2fr;gap:6px 12px;margin:0;font-size:13px}.fact-list dt{color:#a1a1aa}.fact-list dd{margin:0;overflow-wrap:anywhere}.stats-section{border-top:1px solid #35353b;padding-top:16px}.stats-section label{display:grid;gap:6px;max-width:420px;color:#aaa;font-size:13px}.table-wrap{max-width:100%;overflow:auto;margin-top:14px;border:1px solid #35353b}.stats-table{width:100%;border-collapse:collapse;font-size:13px;white-space:nowrap}.stats-table th,.stats-table td{padding:8px 10px;border-bottom:1px solid #303036;text-align:left}.stats-table th{position:sticky;top:0;background:#25252a;color:#fff}.stats-table tbody tr:nth-child(even){background:#202024}.dialog-links{margin-top:16px;font-size:13px}.dialog-links a{color:#8dc9ff}@media(max-width:650px){body{padding:14px}.dialog{width:100%;max-height:100dvh;border-radius:0}.dialog-header,.dialog-content{padding:14px}.fact-list{grid-template-columns:1fr 1.2fr}}</style></head>
<body><h1>TDS Towers</h1><p><a href="/">&larr; back</a></p><p>Towers details and stuff</p><div class="top"><input id="search" type="search" placeholder="Search tower name, role, or description"></div><div class="status" id="status"></div><div class="grid" id="grid"></div>
<dialog class="dialog" id="towerDialog" aria-labelledby="detailName"><header class="dialog-header"><div><h2 id="detailName"></h2><div class="meta" id="detailMeta"></div></div><button class="dialog-close" id="closeDialog" type="button">Close</button></header><div class="dialog-content"><p class="detail-description" id="detailDescription"></p><nav class="detail-tabs" role="tablist" aria-label="Tower details"><button class="detail-tab" id="detailsTab" type="button" role="tab" aria-selected="true" aria-controls="detailsPanel">Details</button><button class="detail-tab" id="statsTab" type="button" role="tab" aria-selected="false" aria-controls="statsPanel">Stats</button><button class="detail-tab" id="galleryTab" type="button" role="tab" aria-selected="false" aria-controls="galleryPanel">Gallery</button></nav><section id="detailsPanel" role="tabpanel" aria-labelledby="detailsTab"><div class="detail-sections" id="detailSections"></div></section><section id="statsPanel" role="tabpanel" aria-labelledby="statsTab" hidden><div class="detail-facts" id="detailFacts"></div><section class="stats-section"><h3>Level stats</h3><label for="statTableSelect">Stats table<select id="statTableSelect"></select></label><div class="table-wrap" id="statTable"></div></section><div class="dialog-links" id="detailLinks"></div></section><section id="galleryPanel" role="tabpanel" aria-labelledby="galleryTab" hidden><label for="gallerySectionSelect">Gallery section<select id="gallerySectionSelect" disabled></select></label><p class="gallery-status" id="galleryStatus" aria-live="polite">Open the Gallery tab to load images.</p><div class="gallery-grid" id="galleryGrid"></div></section></div></dialog>
<script>
const TOWERS=__TOWERS__,grid=document.getElementById('grid'),status=document.getElementById('status'),search=document.getElementById('search'),rarityFilter=document.getElementById('rarityFilter');
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
const dialog=document.getElementById('towerDialog'),detailName=document.getElementById('detailName'),detailMeta=document.getElementById('detailMeta'),detailDescription=document.getElementById('detailDescription'),detailSections=document.getElementById('detailSections'),detailFacts=document.getElementById('detailFacts'),statTableSelect=document.getElementById('statTableSelect'),statTable=document.getElementById('statTable'),detailLinks=document.getElementById('detailLinks');
function draw(){const q=search.value.toLowerCase().trim(),selected=rarityFilter.value,items=TOWERS.filter(t=>(!q||JSON.stringify(t).toLowerCase().includes(q))&&(!selected||t.rarity===selected));status.textContent=items.length+' of '+TOWERS.length+' towers';grid.innerHTML=items.length?items.map(t=>'<article class="card">'+(t.image?'<button class="card-media" type="button" data-slug="'+esc(t.slug)+'" aria-label="View '+esc(t.name)+' stats"><img loading="lazy" src="'+esc(t.image)+'" alt=""></button>':'')+'<div class="card-body"><h2><button class="card-title" type="button" data-slug="'+esc(t.slug)+'">'+esc(t.name)+'</button></h2><div class="meta">'+(t.rarity?'<span class="rarity-badge" data-rarity="'+esc(t.rarity)+'">'+esc(t.rarity)+'</span>':'')+(t.role?'<span>'+esc(t.role)+'</span>':'')+(t.placement?'<span>'+esc(t.placement)+'</span>':'')+'</div><p>'+esc(t.description||'No description available.')+'</p><div class="foot"><button type="button" data-slug="'+esc(t.slug)+'">View stats</button>'+(t.url?'<a href="'+esc(t.url)+'" target="_blank" rel="noopener">Wiki page</a>':'')+'</div></div></article>').join(''):'<p>No towers found.</p>'}
function renderStatTable(tower){const index=Number(statTableSelect.value),table=tower.tables[index];if(!table){statTable.innerHTML='<p>No level tables available.</p>';return}statTable.innerHTML='<table class="stats-table"><thead><tr>'+table.headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+table.rows.map(row=>'<tr>'+table.headers.map((_,i)=>'<td>'+esc(row[i]??'')+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function openTower(slug){const tower=TOWERS.find(t=>t.slug===slug);if(!tower)return;detailName.textContent=tower.name;detailMeta.innerHTML=[tower.rarity,tower.role,tower.placement].filter(Boolean).map(v=>'<span>'+esc(v)+'</span>').join('');detailDescription.textContent=tower.description||'No description available.';detailSections.innerHTML=Object.entries(tower.sections||{}).filter(([name,lines])=>name!=='Description'&&Array.isArray(lines)&&lines.length).map(([name,lines])=>{const heading=name==='Strategy'?'Tips & Strategy':name;return '<article class="article-section"><h3>'+esc(heading)+'</h3>'+lines.map(line=>'<p>'+esc(line)+'</p>').join('')+'</article>'}).join('')||'<p>No additional tower details available.</p>';const facts=Object.entries(tower.general||{}).filter(([key,value])=>!['Role','Placement','Description'].includes(key)&&value);detailFacts.innerHTML=['regular','pvp'].filter(mode=>Object.keys(tower[mode]||{}).length).map(mode=>'<section><h3>'+mode.toUpperCase()+' base stats</h3><dl class="fact-list">'+Object.entries(tower[mode]).map(([key,value])=>'<dt>'+esc(key)+'</dt><dd>'+esc(value)+'</dd>').join('')+'</dl></section>').join('')+(facts.length?'<section><h3>Details</h3><dl class="fact-list">'+facts.map(([key,value])=>'<dt>'+esc(key)+'</dt><dd>'+esc(value)+'</dd>').join('')+'</dl></section>':'');statTableSelect.innerHTML=(tower.tables||[]).map((table,index)=>{const label=[table.mode,table.title,table.path].filter(Boolean).filter((part,index,array)=>array.indexOf(part)===index).join(' · ');return '<option value="'+index+'">'+esc(label||'Stats')+'</option>'}).join('');statTableSelect.disabled=!(tower.tables||[]).length;renderStatTable(tower);detailLinks.innerHTML=tower.url?'<a href="'+esc(tower.url)+'" target="_blank" rel="noopener">Wiki page</a>':'';selectDetailTab('details');dialog.showModal()}
grid.addEventListener('click',event=>{const button=event.target.closest('[data-slug]');if(button)openTower(button.dataset.slug)});
statTableSelect.addEventListener('change',()=>{const tower=TOWERS.find(item=>item.name===detailName.textContent);if(tower)renderStatTable(tower)});
document.getElementById('closeDialog').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close()});
search.addEventListener('input',draw);
rarityFilter.addEventListener('change',draw);
draw();
</script></body></html>"""
    page = page.replace(
        'id="search" type="search" placeholder="Search tower name, role, or description">',
        'id="search" type="search" placeholder="Search tower name, role, or description"><select id="rarityFilter" aria-label="Filter by rarity">__RARITY_OPTIONS__</select>',
        1,
    )
    page = page.replace("</head>", """<style>
 .grid{grid-template-columns:repeat(auto-fill,minmax(320px,1fr))}
 .card{display:grid;grid-template-columns:minmax(90px,38%) minmax(0,1fr)}
 .card-media{height:auto;min-height:210px;display:grid;place-items:center}
.card-media img{width:100%;height:100%;object-fit:contain}
 .card-body{display:flex;flex-direction:column;min-width:0}
 .foot{margin-top:auto;padding-top:8px}
.rarity-badge{display:inline-flex;padding:2px 7px;border:1px solid;border-radius:4px;font-size:11px;font-weight:700}
.rarity-badge[data-rarity="Beginner"]{color:#b7bec8;border-color:#b7bec877;background:#b7bec81a}
.rarity-badge[data-rarity="Intermediate"]{color:#4ade80;border-color:#4ade8077;background:#4ade801a}
.rarity-badge[data-rarity="Advanced"]{color:#60a5fa;border-color:#60a5fa77;background:#60a5fa1a}
.rarity-badge[data-rarity="Hardcore"]{color:#c084fc;border-color:#c084fc77;background:#c084fc1a}
.rarity-badge[data-rarity="Evolved"]{color:#22d3ee;border-color:#22d3ee77;background:#22d3ee1a}
.rarity-badge[data-rarity="Exclusive"],.rarity-badge[data-rarity="Event"]{color:#f87171;border-color:#f8717177;background:#f871711a}
.rarity-badge[data-rarity="Golden"]{color:#facc15;border-color:#facc1577;background:#facc151a}
.rarity-badge[data-rarity="Unreleased"]{color:#fff;border-color:#777;background:#080808}
.detail-tabs{display:flex;gap:6px;margin:0 0 18px;border-bottom:1px solid #35353b}
.article-section{border:1px solid #35353b;border-radius:8px;background:#1d1d22;padding:16px;margin:0 0 14px}
.article-section h3{margin:0 0 10px;color:#fff;font-size:16px}
.article-section p{color:#d4d4d8;line-height:1.55;margin:0 0 10px;white-space:pre-line}
.article-section p:last-child{margin-bottom:0}
.detail-tab{padding:10px 14px;border:0;border-bottom:2px solid transparent;background:transparent;color:#aaa;font-size:14px;cursor:pointer}
.detail-tab[aria-selected="true"]{border-color:#8dc9ff;color:#fff}
.detail-tab:focus-visible{outline:2px solid #8dc9ff;outline-offset:2px}
.gallery-panel-label{display:grid;gap:6px;max-width:420px;color:#aaa;font-size:13px}
.gallery-status{font-size:13px}
.gallery-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}
.gallery-item{min-width:0;margin:0;border:1px solid #35353b;background:#202024}
.gallery-item img{display:block;width:100%;height:180px;object-fit:contain;background:#17171b}
.gallery-item figcaption{padding:8px;font-size:12px;color:#ccc;overflow-wrap:anywhere}
 @media(max-width:650px){.grid{grid-template-columns:1fr}.card{grid-template-columns:minmax(90px,34%) minmax(0,1fr)}.card-media{min-height:190px}.gallery-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.gallery-item img{height:150px}}
</style></head>""", 1)
    page = page.replace("</body>", """<script>
const detailsTab=document.getElementById('detailsTab'),detailsPanel=document.getElementById('detailsPanel'),statsTab=document.getElementById('statsTab'),galleryTab=document.getElementById('galleryTab'),statsPanel=document.getElementById('statsPanel'),galleryPanel=document.getElementById('galleryPanel'),gallerySectionSelect=document.getElementById('gallerySectionSelect'),galleryStatus=document.getElementById('galleryStatus'),galleryGrid=document.getElementById('galleryGrid');
const galleryCache=new Map();
let activeTowerSlug='';
function selectDetailTab(name){const showDetails=name==='details',showGallery=name==='gallery';detailsTab.setAttribute('aria-selected',String(showDetails));statsTab.setAttribute('aria-selected',String(!showDetails&&!showGallery));galleryTab.setAttribute('aria-selected',String(showGallery));detailsPanel.hidden=!showDetails;statsPanel.hidden=showDetails||showGallery;galleryPanel.hidden=!showGallery;if(showGallery)loadTowerGallery(activeTowerSlug)}
function renderGallerySection(){const section=gallerySectionSelect.value,items=(galleryCache.get(activeTowerSlug)||[]).filter(item=>(item.section||'Other')===section);galleryGrid.innerHTML=items.map(item=>{const caption=item.caption||item.panel||item.section||'Tower gallery image';return '<figure class="gallery-item"><img loading="lazy" src="'+esc(item.image)+'" alt="'+esc(caption)+'"><figcaption>'+esc(caption)+'</figcaption></figure>'}).join('');galleryStatus.textContent=items.length+' images'}
async function loadTowerGallery(slug){if(!slug)return;if(galleryCache.has(slug)){renderGalleryOptions();return}galleryStatus.textContent='Loading gallery...';galleryGrid.innerHTML='';gallerySectionSelect.disabled=true;try{const response=await fetch('/api/towers/'+encodeURIComponent(slug)+'/gallery');if(!response.ok)throw new Error('Gallery request failed');const items=await response.json();galleryCache.set(slug,items);renderGalleryOptions()}catch(error){galleryStatus.textContent='Gallery could not be loaded. Try again.'}}
function renderGalleryOptions(){const items=galleryCache.get(activeTowerSlug)||[],sections=[...new Set(items.map(item=>item.section||'Other'))];if(!sections.length){gallerySectionSelect.innerHTML='';gallerySectionSelect.disabled=true;galleryGrid.innerHTML='';galleryStatus.textContent='No gallery images available.';return}gallerySectionSelect.innerHTML=sections.map(section=>'<option value="'+esc(section)+'">'+esc(section)+'</option>').join('');gallerySectionSelect.disabled=sections.length<2;renderGallerySection()}
document.getElementById('grid').addEventListener('click',event=>{const button=event.target.closest('[data-slug]');if(button){activeTowerSlug=button.dataset.slug;selectDetailTab('stats')}},true);
statsTab.addEventListener('click',()=>selectDetailTab('stats'));
galleryTab.addEventListener('click',()=>selectDetailTab('gallery'));
gallerySectionSelect.addEventListener('change',renderGallerySection);
</script></body>""", 1)
    return page.replace("__TOWERS__", _json_for_script(cards)).replace("__RARITY_OPTIONS__", rarity_options)


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


async def _exchange_code(code, redirect_uri, env, fetch_function):
    token_data = await _oauth_token(code, redirect_uri, env, fetch_function)
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
                raw_state = query.get("state", [""])[0]
                payload = raw_state.rsplit(".", 1)[0] if "." in raw_state else raw_state
                state = _decode_state(payload)
                if "delete_ids" in state:
                    state = _decode_signed_state(raw_state, str(getattr(env, "CLIENT_SECRET", "") or ""))
                    if not isinstance(state, dict) or not isinstance(state.get("delete_ids"), list):
                        return _error_page("Invalid delete authorization", "The selected records could not be verified.", response_class, 400)
                    deleted_count = await _delete_progress(env, user_id, state["delete_ids"])
                    return response_class.redirect(
                        f"{_base_url(parts)}/tracker?user={user_id}&deleted={deleted_count}",
                        303,
                    )
                level = _safe_int(state.get("level"))
                exp = _safe_float(state.get("exp"))
                timestamp = _safe_float(state.get("timestamp")) or None
                await _insert_progress(env, user_id, level, exp, timestamp)
                return response_class.redirect(
                    f"{_base_url(parts)}/tracker?user={user_id}",
                    303,
                )
            except Exception as error:
                return _error_page("Failed to update tracker", str(error), response_class, 500)
        try:
            users = await _load_users(env)
            selected_user = query.get("user", [None])[0]
            if not selected_user:
                selected_user = users[0] if users else None
            rows = await _load_progress(env, selected_user)
            deleted_count = _safe_int(query["deleted"][0]) if query.get("deleted") else None
            return _html(_tracker_page(rows, users, selected_user, deleted_count), response_class)
        except Exception as error:
            return _error_page("Tracker unavailable", str(error), response_class, 503)

    if path == "/tracker/delete/authorize" and method == "POST":
        try:
            form = await request.form_data()
            raw_ids = str(form.get("ids", "") or "")
            record_ids = list(dict.fromkeys(int(value) for value in raw_ids.split(",") if value.strip()))
            record_ids = [record_id for record_id in record_ids if record_id > 0]
            if not record_ids:
                return _error_page("No records selected", "Select at least one record to delete.", response_class)
            if len(record_ids) > 99:
                return _error_page("Too many records", "Select no more than 99 records at a time.", response_class)
            redirect_uri = f"{_base_url(parts)}/tracker"
            client_secret = str(getattr(env, "CLIENT_SECRET", "") or "").strip()
            if not client_secret:
                raise RuntimeError("Missing CLIENT_SECRET Worker secret.")
            state = _encode_signed_state({"delete_ids": record_ids}, client_secret)
            location = _authorize_url(redirect_uri, "identify", state)
            return response_class.redirect(location, 303)
        except Exception as error:
            return _error_page("Could not start delete authorization", str(error), response_class, 400)

    if path == "/tracker/authorize" and method == "POST":
        try:
            form = await request.form_data()
            level = _safe_int(form.get("level"))
            exp = _safe_float(form.get("exp"))
            timestamp = _parse_timestamp(form.get("timestamp"))
            redirect_uri = f"{_base_url(parts)}/tracker"
            state_data = {"level": level, "exp": exp}
            if timestamp is not None:
                state_data["timestamp"] = timestamp
            state = _encode_state(state_data)
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

    if method == "GET" and path.startswith("/api/towers/") and path.endswith("/gallery"):
        slug = path.removeprefix("/api/towers/").removesuffix("/gallery").strip("/")
        if not slug or "/" in slug:
            return _json_response({"error": "Invalid tower"}, response_class, 404)
        try:
            towers = await _load_scraped_towers(env)
            tower = towers.get(slug)
            if tower is None:
                return _json_response({"error": "Tower not found"}, response_class, 404)
            return _json_response(tower.get("gallery", []), response_class)
        except Exception as error:
            print(f"Tower gallery could not be loaded: {error}")
            return _json_response({"error": "Gallery unavailable"}, response_class, 503)

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

    if method == "GET" and path == "/enemies":
        try:
            enemies = await _load_scraped_enemies(env)
            return _html(_enemies_page(enemies), response_class)
        except Exception as error:
            return _error_page("Enemy list unavailable", str(error), response_class, 503)

    return _html(
        "<!doctype html><html><meta charset=\"utf-8\"><title>Not found</title>"
        "<body style=\"font-family:system-ui;background:#121214;color:#eee;max-width:720px;margin:50px auto;padding:20px\">"
        "<h1>Not found</h1><p><a href=\"/\" style=\"color:#aaa\">Back home</a></p></body></html>",
        response_class,
        404,
    )