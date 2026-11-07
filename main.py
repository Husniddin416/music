"""
MusicUz — FastAPI + aiogram + Neon (PostgreSQL) / SQLite
Barcha kod bitta faylda: DB, Bot, API, Server
"""
import sys, os, asyncio, logging, secrets, random, time, socket, sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

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

SECRET       = os.getenv("JWT_SECRET", "music_uz_super_jwt_secret_key_2026")
ALGORITHM    = "HS256"
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
SITE_URL     = os.getenv("SITE_URL", "https://music-l8kd.onrender.com").rstrip("/")
PORT         = int(os.getenv("PORT", 3000))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

def norm_phone(p):
    return "".join(c for c in str(p or "") if c.isdigit())

_ADMIN_ENV = [norm_phone(x) for x in os.getenv("ADMIN_PHONE","998889810206").split(",") if x.strip()]
ADMIN_PHONES = list(set(["998889810206"] + _ADMIN_ENV))

def is_admin_phone(p):
    c = norm_phone(p)
    return any(c.endswith(a) or a.endswith(c) for a in ADMIN_PHONES)

# ═══════════════════════════════════════════════════
# DATABASE (Neon PostgreSQL + SQLite fallback)
# ═══════════════════════════════════════════════════
class DBClient:
    def __init__(self):
        self.use_pg = False
        self.pool = None
        self.sqlite_conn = None
        
        if DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")):
            try:
                import psycopg2
                import psycopg2.extras
                from psycopg2.pool import ThreadedConnectionPool
                clean_url = DATABASE_URL
                if "channel_binding=" in clean_url:
                    clean_url = clean_url.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("channel_binding=require", "")
                self.pool = ThreadedConnectionPool(1, 10, clean_url)
                self.use_pg = True
                log.info("✓ Neon (PostgreSQL) bazasiga muvaffaqiyatli ulandi")
            except Exception as e:
                log.warning(f"Neon ulanish xatosi ({e}). SQLite ishlatiladi.")
                self.use_pg = False
                
        if not self.use_pg:
            self.sqlite_conn = sqlite3.connect(str(ROOT / "data.db"), check_same_thread=False)
            self.sqlite_conn.row_factory = sqlite3.Row
            self.sqlite_conn.execute("PRAGMA journal_mode=WAL")
            self.sqlite_conn.execute("PRAGMA foreign_keys=ON")
            log.info("✓ SQLite (data.db) ishlatilmoqda")

db_client = DBClient()

@contextmanager
def get_db():
    if db_client.use_pg:
        import psycopg2.extras
        conn = db_client.pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
            conn.commit()
        except Exception:
            try: conn.rollback()
            except: pass
            raise
        finally:
            db_client.pool.putconn(conn)
    else:
        conn = db_client.sqlite_conn
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

def q(sql: str) -> str:
    """Postgres %s ni SQLite uchun ? ga o'zgartiradi"""
    if not db_client.use_pg:
        return sql.replace("%s", "?")
    return sql

def fetch_one(sql: str, params=None):
    with get_db() as cur:
        cur.execute(q(sql), params or ())
        row = cur.fetchone()
        return dict(row) if row else None

def fetch_all(sql: str, params=None):
    with get_db() as cur:
        cur.execute(q(sql), params or ())
        rows = cur.fetchall()
        return [dict(r) for r in rows]

def execute(sql: str, params=None):
    with get_db() as cur:
        cur.execute(q(sql), params or ())
        return cur.rowcount

def execute_insert(sql: str, params=None):
    with get_db() as cur:
        clean = sql.strip().rstrip(";")
        if "RETURNING" not in clean.upper():
            clean += " RETURNING id"
        cur.execute(q(clean), params or ())
        row = cur.fetchone()
        if not row:
            return None
        if isinstance(row, dict):
            return row.get("id") or list(row.values())[0]
        return row[0]

def init_db():
    if db_client.use_pg:
        with get_db() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS tg_contacts (
              phone VARCHAR(32) PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              tg_name TEXT
            );
            CREATE TABLE IF NOT EXISTS users (
              id SERIAL PRIMARY KEY,
              phone VARCHAR(32) UNIQUE NOT NULL,
              name TEXT,
              chat_id BIGINT,
              is_admin INTEGER DEFAULT 0,
              is_blocked INTEGER DEFAULT 0,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS codes (
              phone VARCHAR(32) PRIMARY KEY,
              code VARCHAR(16) NOT NULL,
              expires_at BIGINT NOT NULL,
              attempts INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS songs (
              id SERIAL PRIMARY KEY,
              title TEXT NOT NULL,
              artist TEXT NOT NULL,
              genre TEXT,
              audio_url TEXT NOT NULL,
              cover_url TEXT DEFAULT '/uploads/default-cover.svg',
              plays INTEGER DEFAULT 0,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS likes (
              user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
              song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
              PRIMARY KEY (user_id, song_id)
            );
            CREATE TABLE IF NOT EXISTS saved (
              user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
              song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (user_id, song_id)
            );
            CREATE TABLE IF NOT EXISTS history (
              id SERIAL PRIMARY KEY,
              user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
              song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
              played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("SELECT COUNT(*) AS c FROM songs")
            cnt = cur.fetchone()["c"]
            if cnt == 0:
                demo = [
                    ("Tungi shahar", "Aziz Beats", "Electronic"),
                    ("Samarqand shamoli", "Silk Road", "Ethno"),
                    ("Yulduzlar ostida", "Nodir Wave", "Chill"),
                    ("Bahor kelur", "Lola Sound", "Pop"),
                    ("Tog' qo'shig'i", "Chimyon Band", "Rock"),
                    ("Sokin tong", "Malika Lo-Fi", "Lo-Fi"),
                    ("Ritm", "DJ Toshkent", "Electronic"),
                    ("Oqshom", "Javlon Jazz", "Jazz"),
                    ("Orzular", "Sevara Pop", "Pop"),
                    ("Cho'l yo'li", "Silk Road", "Ethno"),
                    ("Neon", "Aziz Beats", "Electronic"),
                    ("Yomg'ir", "Malika Lo-Fi", "Lo-Fi"),
                ]
                for i, (t, a, g) in enumerate(demo, 1):
                    cur.execute(
                        "INSERT INTO songs (title, artist, genre, audio_url, cover_url) VALUES (%s, %s, %s, %s, %s)",
                        (t, a, g, f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{i}.mp3", "/uploads/default-cover.svg")
                    )
    else:
        with get_db() as cur:
            cur.executescript("""
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
              cover_url TEXT DEFAULT '/uploads/default-cover.svg',
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
            cur.execute("SELECT COUNT(*) AS c FROM songs")
            cnt = cur.fetchone()["c"]
            if cnt == 0:
                demo = [
                    ("Tungi shahar", "Aziz Beats", "Electronic"),
                    ("Samarqand shamoli", "Silk Road", "Ethno"),
                    ("Yulduzlar ostida", "Nodir Wave", "Chill"),
                    ("Bahor kelur", "Lola Sound", "Pop"),
                    ("Tog' qo'shig'i", "Chimyon Band", "Rock"),
                    ("Sokin tong", "Malika Lo-Fi", "Lo-Fi"),
                    ("Ritm", "DJ Toshkent", "Electronic"),
                    ("Oqshom", "Javlon Jazz", "Jazz"),
                    ("Orzular", "Sevara Pop", "Pop"),
                    ("Cho'l yo'li", "Silk Road", "Ethno"),
                    ("Neon", "Aziz Beats", "Electronic"),
                    ("Yomg'ir", "Malika Lo-Fi", "Lo-Fi"),
                ]
                for i, (t, a, g) in enumerate(demo, 1):
                    cur.execute(
                        "INSERT INTO songs (title, artist, genre, audio_url, cover_url) VALUES (?, ?, ?, ?, ?)",
                        (t, a, g, f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{i}.mp3", "/uploads/default-cover.svg")
                    )

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
    execute(
        """INSERT INTO tg_contacts (phone, chat_id, tg_name) VALUES (%s, %s, %s)
        ON CONFLICT (phone) DO UPDATE SET chat_id = EXCLUDED.chat_id, tg_name = EXCLUDED.tg_name""",
        (phone, msg.chat.id, name)
    )
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

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "MusicUz Backend API",
        "version": "1.0.0",
        "database": "Neon PostgreSQL" if db_client.use_pg else "SQLite",
        "docs": "/api/docs"
    }

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
    row = fetch_one("SELECT * FROM users WHERE id=%s", (uid,))
    if not row:
        if required: raise HTTPException(401,"Foydalanuvchi topilmadi")
        return None
    if row["is_blocked"]: raise HTTPException(403,"Hisobingiz bloklangan")
    return row

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
def song_sel(uid: int):
    return f"""SELECT s.*,
      (SELECT COUNT(*) FROM likes l WHERE l.song_id = s.id) AS likes,
      EXISTS(SELECT 1 FROM likes WHERE song_id = s.id AND user_id = {int(uid)}) AS liked,
      EXISTS(SELECT 1 FROM saved WHERE song_id = s.id AND user_id = {int(uid)}) AS saved
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
    exists = fetch_one("SELECT 1 FROM users WHERE phone=%s", (phone,))
    if body.mode == "login" and not exists:
        raise HTTPException(404, {"error": "Bu raqam ro'yxatdan o'tmagan.", "needRegister": True})
    if body.mode == "register" and exists:
        raise HTTPException(409, {"error": "Bu raqam allaqachon ro'yxatdan o'tgan."})
    contact = fetch_one("SELECT * FROM tg_contacts WHERE phone=%s", (phone,))
    if not contact:
        raise HTTPException(404, {"error": "Avval botga /start bosib raqamingizni yuboring.",
                                  "needBot": True, "bot": _bot_username})
    code = str(random.randint(100000, 999999))
    exp  = int(time.time()*1000) + 5*60*1000
    execute(
        """INSERT INTO codes (phone, code, expires_at, attempts) VALUES (%s, %s, %s, 0)
        ON CONFLICT (phone) DO UPDATE SET code = EXCLUDED.code, expires_at = EXCLUDED.expires_at, attempts = 0""",
        (phone, code, exp)
    )
    try: await send_code(contact["chat_id"], code)
    except Exception as e: raise HTTPException(500, f"Kod yuborilmadi: {e}")
    return {"ok": True}

@app.post("/api/auth/verify")
async def verify(body: VerifyReq):
    phone = norm_phone(body.phone)
    row = fetch_one("SELECT * FROM codes WHERE phone=%s", (phone,))
    if not row or row["expires_at"] < int(time.time()*1000):
        raise HTTPException(400, "Kod eskirgan, qayta so'rang")
    if row["attempts"] >= 5: raise HTTPException(429, "Juda ko'p urinish")
    if str(row["code"]).strip() != str(body.code).strip():
        execute("UPDATE codes SET attempts = attempts + 1 WHERE phone=%s", (phone,))
        raise HTTPException(400, "Kod noto'g'ri")
    execute("DELETE FROM codes WHERE phone=%s", (phone,))
    
    contact = fetch_one("SELECT * FROM tg_contacts WHERE phone=%s", (phone,))
    admin0_row = fetch_one("SELECT COUNT(*) AS c FROM users WHERE is_admin=1")
    admin0 = admin0_row["c"] if admin0_row else 0
    be_admin = is_admin_phone(phone) or admin0 == 0
    
    user = fetch_one("SELECT * FROM users WHERE phone=%s", (phone,))
    if not user:
        name = str(body.name or "").strip()[:50] or (contact["tg_name"] if contact else "Foydalanuvchi")
        new_id = execute_insert(
            "INSERT INTO users (phone, name, chat_id, is_admin) VALUES (%s, %s, %s, %s)",
            (phone, name, contact["chat_id"] if contact else None, 1 if be_admin else 0)
        )
        user = fetch_one("SELECT * FROM users WHERE id=%s", (new_id,))
    elif not user["is_admin"] and be_admin:
        execute("UPDATE users SET is_admin=1 WHERE id=%s", (user["id"],))
        user = fetch_one("SELECT * FROM users WHERE id=%s", (user["id"],))
        
    if user["is_blocked"]: raise HTTPException(403, "Hisobingiz bloklangan")
    return {"token": make_token(user["id"]), "user": dict(user)}

# ── Songs ──
@app.get("/api/songs")
async def get_songs(q:str="", genre:str="", sort:str="new", request:Request=None):
    u = get_user(request, required=False)
    uid = u["id"] if u else 0
    like = f"%{q.strip()}%"
    order = "plays DESC" if sort == "popular" else "s.id DESC"
    like_op = "ILIKE" if db_client.use_pg else "LIKE"
    sql = f"""{song_sel(uid)} WHERE (s.title {like_op} %s OR s.artist {like_op} %s OR s.genre {like_op} %s)
              AND (%s = '' OR s.genre = %s) ORDER BY {order}"""
    return fetch_all(sql, (like, like, like, genre, genre))

@app.get("/api/genres")
async def get_genres(request: Request = None):
    rows = fetch_all("SELECT DISTINCT genre FROM songs WHERE genre IS NOT NULL AND genre != '' ORDER BY genre")
    return [r["genre"] for r in rows]

@app.post("/api/songs/{sid}/play")
async def play(sid:int, request:Request):
    u = get_user(request, required=False)
    execute("UPDATE songs SET plays = plays + 1 WHERE id=%s", (sid,))
    if u:
        execute("INSERT INTO history (user_id, song_id) VALUES (%s, %s)", (u["id"], sid))
    return {"ok": True}

def _toggle(table, uid, sid):
    has = fetch_one(f"SELECT 1 FROM {table} WHERE user_id=%s AND song_id=%s", (uid, sid))
    if has:
        execute(f"DELETE FROM {table} WHERE user_id=%s AND song_id=%s", (uid, sid))
    else:
        execute(f"INSERT INTO {table} (user_id, song_id) VALUES (%s, %s)", (uid, sid))
    return {"active": not bool(has)}

@app.post("/api/songs/{sid}/like")
async def toggle_like(sid:int, request:Request): return _toggle("likes", need_user(request)["id"], sid)
@app.post("/api/songs/{sid}/save")
async def toggle_save(sid:int, request:Request): return _toggle("saved", need_user(request)["id"], sid)

# ── User panel ──
@app.get("/api/me")
async def get_me(request:Request):
    u = need_user(request)
    likes_c = fetch_one("SELECT COUNT(*) AS c FROM likes WHERE user_id=%s", (u["id"],))["c"]
    saved_c = fetch_one("SELECT COUNT(*) AS c FROM saved WHERE user_id=%s", (u["id"],))["c"]
    return {**u, "stats": {
        "likes": likes_c,
        "saved": saved_c,
    }}

@app.put("/api/me")
async def update_me(body:NameReq, request:Request):
    u = need_user(request); name = body.name.strip()[:50]
    if name:
        execute("UPDATE users SET name=%s WHERE id=%s", (name, u["id"]))
    return {"ok": True}

@app.get("/api/me/likes")
async def me_likes(request:Request):
    u = need_user(request)
    return fetch_all(
        f"{song_sel(u['id'])} WHERE s.id IN (SELECT song_id FROM likes WHERE user_id=%s) ORDER BY s.id DESC",
        (u["id"],)
    )

@app.get("/api/me/history")
async def me_history(request:Request):
    u = need_user(request)
    return fetch_all(
        f"""{song_sel(u['id'])} JOIN (
            SELECT song_id, MAX(id) AS h FROM history WHERE user_id=%s GROUP BY song_id
        ) x ON x.song_id = s.id ORDER BY x.h DESC LIMIT 50""",
        (u["id"],)
    )

@app.get("/api/me/saved")
async def me_saved(request:Request):
    u = need_user(request)
    return fetch_all(
        f"{song_sel(u['id'])} WHERE s.id IN (SELECT song_id FROM saved WHERE user_id=%s) ORDER BY s.id DESC",
        (u["id"],)
    )

# ── Admin ──
@app.get("/api/admin/stats")
async def admin_stats(request:Request):
    need_admin(request)
    u_c = fetch_one("SELECT COUNT(*) AS c FROM users")["c"]
    s_c = fetch_one("SELECT COUNT(*) AS c FROM songs")["c"]
    l_c = fetch_one("SELECT COUNT(*) AS c FROM likes")["c"]
    p_c = fetch_one("SELECT COALESCE(SUM(plays), 0) AS c FROM songs")["c"]
    return {"users": u_c, "songs": s_c, "likes": l_c, "plays": p_c}

def _save_file(f: UploadFile) -> str:
    ext  = Path(f.filename).suffix
    name = f"{int(time.time()*1000)}-{secrets.token_hex(4)}{ext}"
    with open(UPLOADS/name, "wb") as out: out.write(f.file.read())
    return f"/uploads/{name}"

@app.post("/api/admin/songs")
async def admin_add(request:Request, title:str=Form(...), artist:str=Form(...),
    genre:str=Form(""), audio_url:str=Form(""), cover_url:str=Form(""),
    audio:Optional[UploadFile]=File(None), cover:Optional[UploadFile]=File(None)):
    need_admin(request)
    ap = _save_file(audio) if audio and audio.filename else audio_url.strip()
    cp = _save_file(cover) if cover and cover.filename else (cover_url.strip() or "/uploads/default-cover.svg")
    if not title.strip() or not artist.strip() or not ap:
        raise HTTPException(400, "Nomi, ijrochi va audio majburiy")
    new_id = execute_insert(
        "INSERT INTO songs (title, artist, genre, audio_url, cover_url) VALUES (%s, %s, %s, %s, %s)",
        (title.strip(), artist.strip(), genre.strip() or None, ap, cp)
    )
    return {"id": new_id}

@app.put("/api/admin/songs/{sid}")
async def admin_edit(sid:int, request:Request, title:str=Form(""), artist:str=Form(""),
    genre:str=Form(""), audio_url:str=Form(""), cover_url:str=Form(""),
    audio:Optional[UploadFile]=File(None), cover:Optional[UploadFile]=File(None)):
    need_admin(request)
    s = fetch_one("SELECT * FROM songs WHERE id=%s", (sid,))
    if not s: raise HTTPException(404, "Topilmadi")
    ap = _save_file(audio) if audio and audio.filename else (audio_url.strip() or s["audio_url"])
    cp = s["cover_url"]
    if cover and cover.filename: cp = _save_file(cover)
    elif cover_url.strip(): cp = cover_url.strip()
    execute(
        "UPDATE songs SET title=%s, artist=%s, genre=%s, audio_url=%s, cover_url=%s WHERE id=%s",
        (title.strip() or s["title"], artist.strip() or s["artist"],
         genre.strip() or s["genre"], ap, cp or "/uploads/default-cover.svg", sid)
    )
    return {"ok": True}

@app.delete("/api/admin/songs/{sid}")
async def admin_del(sid:int, request:Request):
    need_admin(request)
    execute("DELETE FROM songs WHERE id=%s", (sid,))
    return {"ok": True}

@app.get("/api/admin/users")
async def admin_users(request:Request):
    need_admin(request)
    return fetch_all(
        "SELECT u.*, (SELECT COUNT(*) FROM likes WHERE user_id=u.id) AS likes FROM users u ORDER BY u.id DESC"
    )

@app.post("/api/admin/users/{uid}/block")
async def admin_block(uid:int, request:Request):
    need_admin(request)
    u = fetch_one("SELECT * FROM users WHERE id=%s", (uid,))
    if not u or u["is_admin"]: raise HTTPException(400, "Adminni bloklab bo'lmaydi")
    new = 0 if u["is_blocked"] else 1
    execute("UPDATE users SET is_blocked=%s WHERE id=%s", (new, uid))
    return {"blocked": bool(new)}

# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
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
    init_db();        log.info(f"✓ Baza tayyor ({'Neon PostgreSQL' if db_client.use_pg else 'SQLite'})")
    await init_bot(); log.info("✓ Bot tayyor")
    ip = get_local_ip()
    db_name = "Neon PostgreSQL (Cloud)" if db_client.use_pg else "SQLite (Local)"
    log.info(f"\n🎧 MusicUz ishga tushdi! [Database: {db_name}]")
    log.info(f"   http://localhost:{PORT}")
    if ip: log.info(f"   http://{ip}:{PORT}")
    log.info(f"   Docs: http://localhost:{PORT}/api/docs\n")
    await asyncio.gather(run_bot(), run_server())

if __name__ == "__main__":
    asyncio.run(main())
