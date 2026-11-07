import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data.db"

def get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

# Yagona global ulanish (thread-safe WAL rejimida yaxshi ishlaydi)
conn = get_conn()

def db():
    return conn

def init_db():
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS tg_contacts (
      phone TEXT PRIMARY KEY,
      chat_id INTEGER NOT NULL,
      tg_name TEXT
    );
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      phone TEXT UNIQUE NOT NULL,
      name TEXT,
      chat_id INTEGER,
      is_admin INTEGER DEFAULT 0,
      is_blocked INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS codes (
      phone TEXT PRIMARY KEY,
      code TEXT NOT NULL,
      expires_at INTEGER NOT NULL,
      attempts INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS songs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      artist TEXT NOT NULL,
      genre TEXT,
      audio_url TEXT NOT NULL,
      cover_url TEXT DEFAULT '/default-cover.svg',
      plays INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS likes (
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
      PRIMARY KEY (user_id, song_id)
    );
    CREATE TABLE IF NOT EXISTS saved (
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (user_id, song_id)
    );
    CREATE TABLE IF NOT EXISTS history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
      played_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.execute("UPDATE songs SET cover_url='/default-cover.svg' WHERE cover_url IS NULL OR cover_url=''")
    conn.commit()

    # Demo qo'shiqlar
    count = conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    if count == 0:
        demo = [
            ("Tungi shahar",      "Aziz Beats",    "Electronic"),
            ("Samarqand shamoli", "Silk Road",      "Ethno"),
            ("Yulduzlar ostida",  "Nodir Wave",     "Chill"),
            ("Bahor kelur",       "Lola Sound",     "Pop"),
            ("Tog' qo'shig'i",   "Chimyon Band",   "Rock"),
            ("Sokin tong",        "Malika Lo-Fi",   "Lo-Fi"),
            ("Ritm",              "DJ Toshkent",    "Electronic"),
            ("Oqshom",            "Javlon Jazz",    "Jazz"),
            ("Orzular",           "Sevara Pop",     "Pop"),
            ("Cho'l yo'li",      "Silk Road",      "Ethno"),
            ("Neon",              "Aziz Beats",     "Electronic"),
            ("Yomg'ir",          "Malika Lo-Fi",   "Lo-Fi"),
        ]
        for i, (title, artist, genre) in enumerate(demo, 1):
            conn.execute(
                "INSERT INTO songs (title, artist, genre, audio_url, cover_url) VALUES (?,?,?,?,?)",
                (title, artist, genre,
                 f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{i}.mp3",
                 "/default-cover.svg")
            )
        conn.commit()
