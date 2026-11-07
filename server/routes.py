"""
FastAPI backend — MusicUz
Barcha endpointlar Node.js versiyasi bilan bir xil ishlaydi.
"""
import os
import secrets
import random
import time
from pathlib import Path
from typing import Optional

from fastapi import (
    FastAPI, HTTPException, UploadFile, File, Form,
    Request, status
)
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from pydantic import BaseModel

from server.db import db

ROOT = Path(__file__).parent.parent
UPLOADS = ROOT / "uploads"
UPLOADS.mkdir(exist_ok=True)

SECRET = os.getenv("JWT_SECRET", "music_uz_super_jwt_secret_key_2026")
ALGORITHM = "HS256"
ADMIN_PHONES_ENV = os.getenv("ADMIN_PHONE", "998889810206")
DEFAULT_ADMINS = ["998889810206"]


def norm_phone(p: str) -> str:
    return "".join(c for c in str(p or "") if c.isdigit())


ADMIN_PHONES = list(set(
    DEFAULT_ADMINS +
    [norm_phone(x) for x in ADMIN_PHONES_ENV.split(",") if x.strip()]
))


def is_phone_admin(phone: str) -> bool:
    clean = norm_phone(phone)
    return any(clean.endswith(a) or a.endswith(clean) for a in ADMIN_PHONES)


# ---- JWT auth ----

def make_token(user_id: int) -> str:
    return jwt.encode({"id": user_id}, SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        return payload["id"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Avval tizimga kiring")


def get_user(request: Request, required: bool = True):
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if not token:
        if required:
            raise HTTPException(status_code=401, detail="Avval tizimga kiring")
        return None
    uid = decode_token(token)
    c = db()
    row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        if required:
            raise HTTPException(status_code=401, detail="Avval tizimga kiring")
        return None
    if row["is_blocked"]:
        raise HTTPException(status_code=403, detail="Hisobingiz bloklangan")
    return dict(row)


def require_user(request: Request):
    return get_user(request, required=True)


def require_admin(request: Request):
    user = require_user(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Faqat admin uchun")
    return user


# ---- App ----

app = FastAPI(title="MusicUz API", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static fayllar
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")


# ---- Pydantic modellari ----

class PhoneRequest(BaseModel):
    phone: str
    mode: Optional[str] = "login"


class VerifyRequest(BaseModel):
    phone: str
    code: str
    name: Optional[str] = ""


class NameRequest(BaseModel):
    name: str


# ---- Config ----

@app.get("/api/config")
async def config():
    from server.bot import get_bot_username
    return {
        "bot": get_bot_username(),
        "donate": {
            "card":  os.getenv("DONATE_CARD",  "8600 0000 0000 0000"),
            "owner": os.getenv("DONATE_OWNER", "MusicUz"),
            "payme": os.getenv("DONATE_PAYME", ""),
            "click": os.getenv("DONATE_CLICK", ""),
            "uzum":  os.getenv("DONATE_UZUM",  ""),
        },
    }


# ---- Auth ----

@app.post("/api/auth/request-code")
async def request_code(body: PhoneRequest):
    from server.bot import send_code
    phone = norm_phone(body.phone)
    if len(phone) < 9:
        raise HTTPException(400, "Telefon raqam noto'g'ri")

    c = db()
    exists = c.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone()

    if body.mode == "login" and not exists:
        raise HTTPException(404, detail={
            "error": "Bu raqam ro'yxatdan o'tmagan. Avval ro'yxatdan o'ting.",
            "needRegister": True
        })
    if body.mode == "register" and exists:
        raise HTTPException(409, detail={
            "error": "Bu raqam allaqachon ro'yxatdan o'tgan. Kirish bo'limidan foydalaning."
        })

    contact = c.execute(
        "SELECT * FROM tg_contacts WHERE phone=?", (phone,)
    ).fetchone()
    if not contact:
        from server.bot import get_bot_username
        raise HTTPException(404, detail={
            "error": "Bu raqam botga bog'lanmagan. Avval botga /start bosib, raqamingizni yuboring.",
            "needBot": True,
            "bot": get_bot_username(),
        })

    code = str(random.randint(100000, 999999))
    expires_at = int(time.time() * 1000) + 5 * 60 * 1000
    c.execute(
        "INSERT INTO codes (phone, code, expires_at, attempts) VALUES (?,?,?,0) "
        "ON CONFLICT(phone) DO UPDATE SET code=excluded.code, "
        "expires_at=excluded.expires_at, attempts=0",
        (phone, code, expires_at)
    )
    c.commit()

    try:
        await send_code(contact["chat_id"], code)
    except Exception as e:
        raise HTTPException(500, f"Kod yuborilmadi: {e}")

    return {"ok": True}


@app.post("/api/auth/verify")
async def verify(body: VerifyRequest):
    phone = norm_phone(body.phone)
    c = db()
    row = c.execute("SELECT * FROM codes WHERE phone=?", (phone,)).fetchone()
    now_ms = int(time.time() * 1000)

    if not row or row["expires_at"] < now_ms:
        raise HTTPException(400, "Kod eskirgan, qayta so'rang")
    if row["attempts"] >= 5:
        raise HTTPException(429, "Juda ko'p urinish, qayta kod so'rang")
    if row["code"] != str(body.code).strip():
        c.execute("UPDATE codes SET attempts=attempts+1 WHERE phone=?", (phone,))
        c.commit()
        raise HTTPException(400, "Kod noto'g'ri")

    c.execute("DELETE FROM codes WHERE phone=?", (phone,))
    contact = c.execute(
        "SELECT * FROM tg_contacts WHERE phone=?", (phone,)
    ).fetchone()

    admin_count = c.execute(
        "SELECT COUNT(*) FROM users WHERE is_admin=1"
    ).fetchone()[0]
    should_be_admin = is_phone_admin(phone) or admin_count == 0

    user = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    if not user:
        name = str(body.name or "").strip()[:50] or (
            contact["tg_name"] if contact else "Foydalanuvchi"
        )
        chat_id = contact["chat_id"] if contact else None
        cur = c.execute(
            "INSERT INTO users (phone, name, chat_id, is_admin) VALUES (?,?,?,?)",
            (phone, name, chat_id, 1 if should_be_admin else 0)
        )
        c.commit()
        user = c.execute(
            "SELECT * FROM users WHERE id=?", (cur.lastrowid,)
        ).fetchone()
    else:
        if not user["is_admin"] and should_be_admin:
            c.execute("UPDATE users SET is_admin=1 WHERE id=?", (user["id"],))
            c.commit()
            user = c.execute(
                "SELECT * FROM users WHERE id=?", (user["id"],)
            ).fetchone()

    if user["is_blocked"]:
        raise HTTPException(403, "Hisobingiz bloklangan")

    token = make_token(user["id"])
    c.commit()
    return {"token": token, "user": dict(user)}


# ---- Songs ----

def song_select(uid: int) -> str:
    return f"""
    SELECT s.*,
      (SELECT COUNT(*) FROM likes l WHERE l.song_id=s.id) likes,
      EXISTS(SELECT 1 FROM likes WHERE song_id=s.id AND user_id={uid}) liked,
      EXISTS(SELECT 1 FROM saved WHERE song_id=s.id AND user_id={uid}) saved
    FROM songs s
    """


@app.get("/api/songs")
async def get_songs(
    q: str = "",
    genre: str = "",
    sort: str = "new",
    request: Request = None,
):
    user = require_user(request)
    uid = user["id"]
    like = f"%{q.strip()}%"
    order = "plays DESC" if sort == "popular" else "s.id DESC"
    c = db()
    rows = c.execute(
        f"{song_select(uid)} WHERE (s.title LIKE ? OR s.artist LIKE ? OR s.genre LIKE ?) "
        f"AND (?='' OR s.genre=?) ORDER BY {order}",
        (like, like, like, genre, genre)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/genres")
async def get_genres(request: Request):
    require_user(request)
    c = db()
    rows = c.execute(
        "SELECT DISTINCT genre FROM songs WHERE genre IS NOT NULL ORDER BY genre"
    ).fetchall()
    return [r["genre"] for r in rows]


@app.post("/api/songs/{song_id}/play")
async def play_song(song_id: int, request: Request):
    user = require_user(request)
    c = db()
    c.execute("UPDATE songs SET plays=plays+1 WHERE id=?", (song_id,))
    c.execute(
        "INSERT INTO history (user_id, song_id) VALUES (?,?)",
        (user["id"], song_id)
    )
    c.commit()
    return {"ok": True}


@app.post("/api/songs/{song_id}/like")
async def toggle_like(song_id: int, request: Request):
    user = require_user(request)
    return _toggle("likes", user["id"], song_id)


@app.post("/api/songs/{song_id}/save")
async def toggle_save(song_id: int, request: Request):
    user = require_user(request)
    return _toggle("saved", user["id"], song_id)


def _toggle(table: str, uid: int, sid: int):
    c = db()
    has = c.execute(
        f"SELECT 1 FROM {table} WHERE user_id=? AND song_id=?", (uid, sid)
    ).fetchone()
    if has:
        c.execute(
            f"DELETE FROM {table} WHERE user_id=? AND song_id=?", (uid, sid)
        )
    else:
        c.execute(
            f"INSERT INTO {table} (user_id, song_id) VALUES (?,?)", (uid, sid)
        )
    c.commit()
    return {"active": not has}


# ---- User panel ----

@app.get("/api/me")
async def get_me(request: Request):
    user = require_user(request)
    uid = user["id"]
    c = db()
    likes = c.execute("SELECT COUNT(*) FROM likes WHERE user_id=?", (uid,)).fetchone()[0]
    saved = c.execute("SELECT COUNT(*) FROM saved WHERE user_id=?", (uid,)).fetchone()[0]
    return {**user, "stats": {"likes": likes, "saved": saved}}


@app.put("/api/me")
async def update_me(body: NameRequest, request: Request):
    user = require_user(request)
    name = body.name.strip()[:50]
    if name:
        c = db()
        c.execute("UPDATE users SET name=? WHERE id=?", (name, user["id"]))
        c.commit()
    return {"ok": True}


@app.get("/api/me/likes")
async def me_likes(request: Request):
    user = require_user(request)
    uid = user["id"]
    c = db()
    rows = c.execute(
        f"{song_select(uid)} WHERE s.id IN "
        f"(SELECT song_id FROM likes WHERE user_id=?) ORDER BY s.id DESC",
        (uid,)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/me/history")
async def me_history(request: Request):
    user = require_user(request)
    uid = user["id"]
    c = db()
    rows = c.execute(
        f"{song_select(uid)} JOIN "
        f"(SELECT song_id, MAX(id) h FROM history WHERE user_id=? GROUP BY song_id) x "
        f"ON x.song_id=s.id ORDER BY x.h DESC LIMIT 50",
        (uid,)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/me/saved")
async def me_saved(request: Request):
    user = require_user(request)
    uid = user["id"]
    c = db()
    rows = c.execute(
        f"{song_select(uid)} WHERE s.id IN "
        f"(SELECT song_id FROM saved WHERE user_id=?) ORDER BY s.id DESC",
        (uid,)
    ).fetchall()
    return [dict(r) for r in rows]


# ---- Admin ----

@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    require_admin(request)
    c = db()
    return {
        "users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "songs": c.execute("SELECT COUNT(*) FROM songs").fetchone()[0],
        "likes": c.execute("SELECT COUNT(*) FROM likes").fetchone()[0],
        "plays": c.execute("SELECT COALESCE(SUM(plays),0) FROM songs").fetchone()[0],
    }


def save_upload(file: UploadFile, folder: Path) -> str:
    ext = Path(file.filename).suffix
    fname = f"{int(time.time()*1000)}-{secrets.token_hex(4)}{ext}"
    dest = folder / fname
    with open(dest, "wb") as f:
        f.write(file.file.read())
    return f"/uploads/{fname}"


@app.post("/api/admin/songs")
async def admin_add_song(
    request: Request,
    title: str = Form(...),
    artist: str = Form(...),
    genre: str = Form(""),
    audio_url: str = Form(""),
    cover_url: str = Form(""),
    audio: Optional[UploadFile] = File(None),
    cover: Optional[UploadFile] = File(None),
):
    require_admin(request)
    audio_path = (
        save_upload(audio, UPLOADS) if audio and audio.filename
        else audio_url.strip()
    )
    cover_path = (
        save_upload(cover, UPLOADS) if cover and cover.filename
        else (cover_url.strip() or "/default-cover.svg")
    )
    if not title.strip() or not artist.strip() or not audio_path:
        raise HTTPException(400, "Nomi, ijrochi va audio (fayl yoki havola) majburiy")

    c = db()
    cur = c.execute(
        "INSERT INTO songs (title, artist, genre, audio_url, cover_url) VALUES (?,?,?,?,?)",
        (title.strip(), artist.strip(), genre.strip() or None, audio_path, cover_path)
    )
    c.commit()
    return {"id": cur.lastrowid}


@app.put("/api/admin/songs/{song_id}")
async def admin_edit_song(
    song_id: int,
    request: Request,
    title: str = Form(""),
    artist: str = Form(""),
    genre: str = Form(""),
    audio_url: str = Form(""),
    cover_url: str = Form(""),
    audio: Optional[UploadFile] = File(None),
    cover: Optional[UploadFile] = File(None),
):
    require_admin(request)
    c = db()
    s = c.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    if not s:
        raise HTTPException(404, "Topilmadi")
    s = dict(s)

    audio_path = (
        save_upload(audio, UPLOADS) if audio and audio.filename
        else (audio_url.strip() or s["audio_url"])
    )
    cover_path = s["cover_url"]
    if cover and cover.filename:
        cover_path = save_upload(cover, UPLOADS)
    elif cover_url.strip():
        cover_path = cover_url.strip()
    if not cover_path:
        cover_path = "/default-cover.svg"

    c.execute(
        "UPDATE songs SET title=?, artist=?, genre=?, audio_url=?, cover_url=? WHERE id=?",
        (
            title.strip() or s["title"],
            artist.strip() or s["artist"],
            genre.strip() or s["genre"],
            audio_path,
            cover_path,
            song_id,
        )
    )
    c.commit()
    return {"ok": True}


@app.delete("/api/admin/songs/{song_id}")
async def admin_delete_song(song_id: int, request: Request):
    require_admin(request)
    c = db()
    c.execute("DELETE FROM songs WHERE id=?", (song_id,))
    c.commit()
    return {"ok": True}


@app.get("/api/admin/users")
async def admin_users(request: Request):
    require_admin(request)
    c = db()
    rows = c.execute(
        "SELECT u.*, (SELECT COUNT(*) FROM likes WHERE user_id=u.id) likes "
        "FROM users u ORDER BY u.id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/users/{user_id}/block")
async def admin_block(user_id: int, request: Request):
    require_admin(request)
    c = db()
    u = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u or u["is_admin"]:
        raise HTTPException(400, "Adminni bloklab bo'lmaydi")
    new_state = 0 if u["is_blocked"] else 1
    c.execute("UPDATE users SET is_blocked=? WHERE id=?", (new_state, user_id))
    c.commit()
    return {"blocked": bool(new_state)}



