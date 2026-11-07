"""
MusicUz — FastAPI + aiogram
Barcha kod bitta faylda: DB, Bot, API, Server
"""
import sys, os, asyncio, logging, secrets, random, time, socket, sqlite3
from pathlib import Path
from typing import Optional

# .env yuklash
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("musicuz")

# ═══════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════
ROOT    = Path(__file__).parent
UPLOADS = ROOT / "uploads"
UPLOADS.mkdir(exist_ok=True)

SECRET     = os.getenv("JWT_SECRET", "music_uz_super_jwt_secret_key_2026")
ALGORITHM  = "HS256"
BOT_TOKEN  = os.getenv("BOT_TOKEN", "")
SITE_URL   = os.getenv("SITE_URL", "https://music-l8kd.onrender.com").rstrip("/")
PORT       = int(os.getenv("PORT", 3000))

def norm_phone(p):
    return "".join(c for c in str(p or "") if c.isdigit())

_ADMIN_ENV = [norm_phone(x) for x in os.getenv("ADMIN_PHONE","998889810206").split(",") if x.strip()]
ADMIN_PHONES = list(set(["998889810206"] + _ADMIN_ENV))

def is_admin_phone(p):
    c = norm_phone(p)
    return any(c.endswith(a) or a.endswith(c) for a in ADMIN_PHONES)

# ═══════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════
_conn = sqlite3.connect(str(ROOT / "data.db"), check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")
_conn.execute("PRAGMA foreign_keys=ON")

def db(): return _conn

def init_db():
    _conn.executescript("""
    CREATE TABLE IF NOT EXISTS tg_contacts (
      phone TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, tg_name TEXT);
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT UNIQUE NOT NULL,
      name TEXT, chat_id INTEGER, is_admin INTEGER DEFAULT 0,
      is_blocked INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS codes (
      phone TEXT PRIMARY KEY, code TEXT NOT NULL,
      expires_at INTEGER NOT NULL, attempts INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS songs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
      artist TEXT NOT NULL, genre TEXT, audio_url TEXT NOT NULL,
      cover_url TEXT DEFAULT '/default-cover.svg',
      plays INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS likes (
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
      PRIMARY KEY (user_id, song_id));
    CREATE TABLE IF NOT EXISTS saved (
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (user_id, song_id));
    CREATE TABLE IF NOT EXISTS history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
      played_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    _conn.execute("UPDATE songs SET cover_url='/default-cover.svg' WHERE cover_url IS NULL OR cover_url=''")
    _conn.commit()
    if _conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0] == 0:
        demo = [
            ("Tungi shahar","Aziz Beats","Electronic"),
            ("Samarqand shamoli","Silk Road","Ethno"),
            ("Yulduzlar ostida","Nodir Wave","Chill"),
            ("Bahor kelur","Lola Sound","Pop"),
            ("Tog' qo'shig'i","Chimyon Band","Rock"),
            ("Sokin tong","Malika Lo-Fi","Lo-Fi"),
            ("Ritm","DJ Toshkent","Electronic"),
            ("Oqshom","Javlon Jazz","Jazz"),
            ("Orzular","Sevara Pop","Pop"),
            ("Cho'l yo'li","Silk Road","Ethno"),
            ("Neon","Aziz Beats","Electronic"),
            ("Yomg'ir","Malika Lo-Fi","Lo-Fi"),
        ]
        for i,(t,a,g) in enumerate(demo,1):
            _conn.execute(
                "INSERT INTO songs (title,artist,genre,audio_url,cover_url) VALUES (?,?,?,?,?)",
                (t,a,g,f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{i}.mp3","/default-cover.svg"))
        _conn.commit()

# ═══════════════════════════════════════════════════
# TELEGRAM BOT
# ═══════════════════════════════════════════════════
bot: Bot = None
dp = Dispatcher()
_bot_username = ""

async def init_bot():
    global bot, _bot_username
    bot = Bot(token=BOT_TOKEN)
    me = await bot.get_me()
    _bot_username = me.username
    log.info(f"Bot: @{_bot_username}")
    try:
        await bot.set_my_description(description=(
            f"🎧 MusicUz — O'zbek musiqa platformasi!\n"
            f"✨ Saytga kirish kodi olish\n🎵 Qo'shiqlar tinglash\n\n"
            f"🌐 {SITE_URL}"))
        if SITE_URL.startswith("https://"):
            await bot.set_chat_menu_button(menu_button=types.MenuButtonWebApp(
                text="🎵 Saytni ochish", web_app=types.WebAppInfo(url=SITE_URL)))
    except Exception as e:
        log.warning(f"Bot setup: {e}")

async def send_code(chat_id: int, code: str):
    await bot.send_message(chat_id,
        f"🔐 MusicUz kirish kodi: <code>{code}</code>\n\n"
        f"⏳ Kod 5 daqiqa amal qiladi.\n🔗 <a href='{SITE_URL}'>{SITE_URL}</a>",
        parse_mode="HTML", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Saytga kirish", url=SITE_URL)]]))

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    await msg.answer(
        f"🎵 <b>MusicUz</b> botiga xush kelibsiz!\n\n"
        f"🌐 <a href='{SITE_URL}'>{SITE_URL}</a>\n\n"
        f"Kirish kodi olish uchun raqamingizni yuboring:",
        parse_mode="HTML", disable_web_page_preview=True,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True))

@dp.message(Command(commands=["site","link","sayt"]))
async def cmd_site(msg: types.Message):
    await msg.answer(f"🎧 <b>MusicUz:</b> <a href='{SITE_URL}'>{SITE_URL}</a>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Ochish", url=SITE_URL)]]))

@dp.message(Command("donate"))
async def cmd_donate(msg: types.Message):
    card  = os.getenv("DONATE_CARD","8600 0000 0000 0000")
    owner = os.getenv("DONATE_OWNER","MusicUz")
    await msg.answer(
        f"💜 <b>Qo'llab-quvvatlash:</b>\n💳 <code>{card}</code>\n👤 <b>{owner}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💜 Ko'rish", url=f"{SITE_URL}/#/donate")]]))

@dp.message(F.contact)
async def on_contact(msg: types.Message):
    c = msg.contact
    if c.user_id != msg.from_user.id:
        await msg.answer("❌ Faqat o'z raqamingizni yuboring.")
        return
    phone = norm_phone(c.phone_number)
    name  = " ".join(filter(None,[c.first_name or "",c.last_name or ""])) or "Foydalanuvchi"
    db().execute(
        "INSERT INTO tg_contacts (phone,chat_id,tg_name) VALUES (?,?,?) "
        "ON CONFLICT(phone) DO UPDATE SET chat_id=excluded.chat_id,tg_name=excluded.tg_name",
        (phone, msg.chat.id, name))
    db().commit()
    await msg.answer(
        f"✅ Raqam bog'landi: +{phone}\n🔗 <a href='{SITE_URL}'>{SITE_URL}</a>",
        parse_mode="HTML", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Saytga o'tish", url=SITE_URL)]]))

# ═══════════════════════════════════════════════════
# FASTAPI
# ═══════════════════════════════════════════════════
app = FastAPI(title="MusicUz API", docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")

# --- Auth helpers ---
def make_token(uid): return jwt.encode({"id": uid}, SECRET, algorithm=ALGORITHM)

def get_user(request: Request, required=True):
    token = request.headers.get("Authorization","").replace("Bearer ","").strip()
    if not token:
        if required: raise HTTPException(401,"Avval tizimga kiring")
        return None
    try:
        uid = jwt.decode(token, SECRET, algorithms=[ALGORITHM])["id"]
    except JWTError:
        raise HTTPException(401,"Token noto'g'ri")
    row = db().execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    if not row:
        if required: raise HTTPException(401,"Foydalanuvchi topilmadi")
        return None
    if row["is_blocked"]: raise HTTPException(403,"Hisobingiz bloklangan")
    return dict(row)

def need_user(r: Request):  return get_user(r, True)
def need_admin(r: Request):
    u = need_user(r)
    if not u["is_admin"]: raise HTTPException(403,"Faqat admin uchun")
    return u

# --- Pydantic ---
class PhoneReq(BaseModel):
    phone: str
    mode: Optional[str] = "login"
class VerifyReq(BaseModel):
    phone: str; code: str; name: Optional[str] = ""
class NameReq(BaseModel):
    name: str

# --- Song SELECT helper ---
def song_sel(uid):
    return f"""SELECT s.*,
      (SELECT COUNT(*) FROM likes l WHERE l.song_id=s.id) likes,
      EXISTS(SELECT 1 FROM likes WHERE song_id=s.id AND user_id={uid}) liked,
      EXISTS(SELECT 1 FROM saved WHERE song_id=s.id AND user_id={uid}) saved
    FROM songs s"""

# ── Config ──
@app.get("/api/config")
async def config():
    return {"bot": _bot_username, "donate":{
        "card":  os.getenv("DONATE_CARD","8600 0000 0000 0000"),
        "owner": os.getenv("DONATE_OWNER","MusicUz"),
        "payme": os.getenv("DONATE_PAYME",""),
        "click": os.getenv("DONATE_CLICK",""),
    }}

# ── Auth ──
@app.post("/api/auth/request-code")
async def request_code(body: PhoneReq):
    phone = norm_phone(body.phone)
    if len(phone) < 9: raise HTTPException(400,"Telefon raqam noto'g'ri")
    c = db()
    exists = c.execute("SELECT 1 FROM users WHERE phone=?",(phone,)).fetchone()
    if body.mode=="login" and not exists:
        raise HTTPException(404,{"error":"Bu raqam ro'yxatdan o'tmagan.","needRegister":True})
    if body.mode=="register" and exists:
        raise HTTPException(409,{"error":"Bu raqam allaqachon ro'yxatdan o'tgan."})
    contact = c.execute("SELECT * FROM tg_contacts WHERE phone=?",(phone,)).fetchone()
    if not contact:
        raise HTTPException(404,{"error":"Avval botga /start bosib raqamingizni yuboring.",
                                 "needBot":True,"bot":_bot_username})
    code = str(random.randint(100000,999999))
    exp  = int(time.time()*1000) + 5*60*1000
    c.execute("INSERT INTO codes (phone,code,expires_at,attempts) VALUES (?,?,?,0) "
              "ON CONFLICT(phone) DO UPDATE SET code=excluded.code,"
              "expires_at=excluded.expires_at,attempts=0",(phone,code,exp))
    c.commit()
    try: await send_code(contact["chat_id"], code)
    except Exception as e: raise HTTPException(500,f"Kod yuborilmadi: {e}")
    return {"ok": True}

@app.post("/api/auth/verify")
async def verify(body: VerifyReq):
    phone = norm_phone(body.phone)
    c = db()
    row = c.execute("SELECT * FROM codes WHERE phone=?",(phone,)).fetchone()
    if not row or row["expires_at"] < int(time.time()*1000):
        raise HTTPException(400,"Kod eskirgan, qayta so'rang")
    if row["attempts"] >= 5: raise HTTPException(429,"Juda ko'p urinish")
    if row["code"] != str(body.code).strip():
        c.execute("UPDATE codes SET attempts=attempts+1 WHERE phone=?",(phone,))
        c.commit()
        raise HTTPException(400,"Kod noto'g'ri")
    c.execute("DELETE FROM codes WHERE phone=?",(phone,))
    contact = c.execute("SELECT * FROM tg_contacts WHERE phone=?",(phone,)).fetchone()
    admin0  = c.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]
    be_admin = is_admin_phone(phone) or admin0==0
    user = c.execute("SELECT * FROM users WHERE phone=?",(phone,)).fetchone()
    if not user:
        name = str(body.name or "").strip()[:50] or (contact["tg_name"] if contact else "Foydalanuvchi")
        cur  = c.execute("INSERT INTO users (phone,name,chat_id,is_admin) VALUES (?,?,?,?)",
                         (phone, name, contact["chat_id"] if contact else None, 1 if be_admin else 0))
        c.commit()
        user = c.execute("SELECT * FROM users WHERE id=?",(cur.lastrowid,)).fetchone()
    elif not user["is_admin"] and be_admin:
        c.execute("UPDATE users SET is_admin=1 WHERE id=?",(user["id"],)); c.commit()
        user = c.execute("SELECT * FROM users WHERE id=?",(user["id"],)).fetchone()
    if user["is_blocked"]: raise HTTPException(403,"Hisobingiz bloklangan")
    c.commit()
    return {"token": make_token(user["id"]), "user": dict(user)}

# ── Songs ──
@app.get("/api/songs")
async def get_songs(q:str="",genre:str="",sort:str="new",request:Request=None):
    u = need_user(request); like=f"%{q.strip()}%"
    order = "plays DESC" if sort=="popular" else "s.id DESC"
    rows = db().execute(f"{song_sel(u['id'])} WHERE (s.title LIKE ? OR s.artist LIKE ? "
                        f"OR s.genre LIKE ?) AND (?='' OR s.genre=?) ORDER BY {order}",
                        (like,like,like,genre,genre)).fetchall()
    return [dict(r) for r in rows]

@app.get("/api/genres")
async def get_genres(request: Request):
    need_user(request)
    return [r["genre"] for r in db().execute(
        "SELECT DISTINCT genre FROM songs WHERE genre IS NOT NULL ORDER BY genre").fetchall()]

@app.post("/api/songs/{sid}/play")
async def play(sid:int, request:Request):
    u=need_user(request); c=db()
    c.execute("UPDATE songs SET plays=plays+1 WHERE id=?",(sid,))
    c.execute("INSERT INTO history (user_id,song_id) VALUES (?,?)",(u["id"],sid))
    c.commit(); return {"ok":True}

def _toggle(table,uid,sid):
    c=db()
    has=c.execute(f"SELECT 1 FROM {table} WHERE user_id=? AND song_id=?",(uid,sid)).fetchone()
    if has: c.execute(f"DELETE FROM {table} WHERE user_id=? AND song_id=?",(uid,sid))
    else:   c.execute(f"INSERT INTO {table} (user_id,song_id) VALUES (?,?)",(uid,sid))
    c.commit(); return {"active": not has}

@app.post("/api/songs/{sid}/like")
async def toggle_like(sid:int,request:Request): return _toggle("likes",need_user(request)["id"],sid)
@app.post("/api/songs/{sid}/save")
async def toggle_save(sid:int,request:Request): return _toggle("saved",need_user(request)["id"],sid)

# ── User panel ──
@app.get("/api/me")
async def get_me(request:Request):
    u=need_user(request); c=db()
    return {**u,"stats":{
        "likes": c.execute("SELECT COUNT(*) FROM likes WHERE user_id=?",(u["id"],)).fetchone()[0],
        "saved": c.execute("SELECT COUNT(*) FROM saved WHERE user_id=?",(u["id"],)).fetchone()[0],
    }}

@app.put("/api/me")
async def update_me(body:NameReq,request:Request):
    u=need_user(request); name=body.name.strip()[:50]
    if name: db().execute("UPDATE users SET name=? WHERE id=?",(name,u["id"])); db().commit()
    return {"ok":True}

@app.get("/api/me/likes")
async def me_likes(request:Request):
    u=need_user(request)
    return [dict(r) for r in db().execute(
        f"{song_sel(u['id'])} WHERE s.id IN (SELECT song_id FROM likes WHERE user_id=?) ORDER BY s.id DESC",
        (u["id"],)).fetchall()]

@app.get("/api/me/history")
async def me_history(request:Request):
    u=need_user(request)
    return [dict(r) for r in db().execute(
        f"{song_sel(u['id'])} JOIN (SELECT song_id,MAX(id) h FROM history WHERE user_id=? "
        f"GROUP BY song_id) x ON x.song_id=s.id ORDER BY x.h DESC LIMIT 50",(u["id"],)).fetchall()]

@app.get("/api/me/saved")
async def me_saved(request:Request):
    u=need_user(request)
    return [dict(r) for r in db().execute(
        f"{song_sel(u['id'])} WHERE s.id IN (SELECT song_id FROM saved WHERE user_id=?) ORDER BY s.id DESC",
        (u["id"],)).fetchall()]

# ── Admin ──
@app.get("/api/admin/stats")
async def admin_stats(request:Request):
    need_admin(request); c=db()
    return {"users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "songs": c.execute("SELECT COUNT(*) FROM songs").fetchone()[0],
            "likes": c.execute("SELECT COUNT(*) FROM likes").fetchone()[0],
            "plays": c.execute("SELECT COALESCE(SUM(plays),0) FROM songs").fetchone()[0]}

def _save_file(f: UploadFile) -> str:
    ext  = Path(f.filename).suffix
    name = f"{int(time.time()*1000)}-{secrets.token_hex(4)}{ext}"
    with open(UPLOADS/name,"wb") as out: out.write(f.file.read())
    return f"/uploads/{name}"

@app.post("/api/admin/songs")
async def admin_add(request:Request, title:str=Form(...), artist:str=Form(...),
    genre:str=Form(""), audio_url:str=Form(""), cover_url:str=Form(""),
    audio:Optional[UploadFile]=File(None), cover:Optional[UploadFile]=File(None)):
    need_admin(request)
    ap = _save_file(audio) if audio and audio.filename else audio_url.strip()
    cp = _save_file(cover) if cover and cover.filename else (cover_url.strip() or "/default-cover.svg")
    if not title.strip() or not artist.strip() or not ap:
        raise HTTPException(400,"Nomi, ijrochi va audio majburiy")
    cur = db().execute("INSERT INTO songs (title,artist,genre,audio_url,cover_url) VALUES (?,?,?,?,?)",
                       (title.strip(),artist.strip(),genre.strip() or None,ap,cp))
    db().commit(); return {"id": cur.lastrowid}

@app.put("/api/admin/songs/{sid}")
async def admin_edit(sid:int, request:Request, title:str=Form(""), artist:str=Form(""),
    genre:str=Form(""), audio_url:str=Form(""), cover_url:str=Form(""),
    audio:Optional[UploadFile]=File(None), cover:Optional[UploadFile]=File(None)):
    need_admin(request); c=db()
    s=c.execute("SELECT * FROM songs WHERE id=?",(sid,)).fetchone()
    if not s: raise HTTPException(404,"Topilmadi")
    s=dict(s)
    ap = _save_file(audio) if audio and audio.filename else (audio_url.strip() or s["audio_url"])
    cp = s["cover_url"]
    if cover and cover.filename: cp=_save_file(cover)
    elif cover_url.strip(): cp=cover_url.strip()
    c.execute("UPDATE songs SET title=?,artist=?,genre=?,audio_url=?,cover_url=? WHERE id=?",
              (title.strip() or s["title"], artist.strip() or s["artist"],
               genre.strip() or s["genre"], ap, cp or "/default-cover.svg", sid))
    c.commit(); return {"ok":True}

@app.delete("/api/admin/songs/{sid}")
async def admin_del(sid:int,request:Request):
    need_admin(request); db().execute("DELETE FROM songs WHERE id=?",(sid,)); db().commit()
    return {"ok":True}

@app.get("/api/admin/users")
async def admin_users(request:Request):
    need_admin(request)
    return [dict(r) for r in db().execute(
        "SELECT u.*,(SELECT COUNT(*) FROM likes WHERE user_id=u.id) likes "
        "FROM users u ORDER BY u.id DESC").fetchall()]

@app.post("/api/admin/users/{uid}/block")
async def admin_block(uid:int,request:Request):
    need_admin(request); c=db()
    u=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    if not u or u["is_admin"]: raise HTTPException(400,"Adminni bloklab bo'lmaydi")
    new=0 if u["is_blocked"] else 1
    c.execute("UPDATE users SET is_blocked=? WHERE id=?",(new,uid)); c.commit()
    return {"blocked":bool(new)}

# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════
def get_local_ip():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("8.8.8.8",80))
        ip=s.getsockname()[0]; s.close(); return ip
    except: return ""

async def run_bot():
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

async def run_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="warning", loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    if not BOT_TOKEN:
        log.error("BOT_TOKEN topilmadi! .env faylini tekshiring."); return
    init_db();      log.info("✓ Baza tayyor")
    await init_bot(); log.info("✓ Bot tayyor")
    ip = get_local_ip()
    log.info(f"\n🎧 MusicUz ishga tushdi!")
    log.info(f"   http://localhost:{PORT}")
    if ip: log.info(f"   http://{ip}:{PORT}")
    log.info(f"   Docs: http://localhost:{PORT}/api/docs\n")
    await asyncio.gather(run_bot(), run_server())

if __name__ == "__main__":
    asyncio.run(main())
