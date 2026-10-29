const { DatabaseSync } = require('node:sqlite');
const path = require('path');

const db = new DatabaseSync(path.join(__dirname, '..', 'data.db'));
db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');

db.exec(`
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
`);

db.exec("UPDATE songs SET cover_url = '/default-cover.svg' WHERE cover_url IS NULL OR cover_url = '';");
db.exec("UPDATE users SET is_admin = 1;");

if (Number(db.prepare('SELECT COUNT(*) c FROM songs').get().c) === 0) {
  const demo = [
    ['Tungi shahar', 'Aziz Beats', 'Electronic'],
    ['Samarqand shamoli', 'Silk Road', 'Ethno'],
    ['Yulduzlar ostida', 'Nodir Wave', 'Chill'],
    ['Bahor kelur', 'Lola Sound', 'Pop'],
    ['Tog\' qo\'shig\'i', 'Chimyon Band', 'Rock'],
    ['Sokin tong', 'Malika Lo-Fi', 'Lo-Fi'],
    ['Ritm', 'DJ Toshkent', 'Electronic'],
    ['Oqshom', 'Javlon Jazz', 'Jazz'],
    ['Orzular', 'Sevara Pop', 'Pop'],
    ['Cho\'l yo\'li', 'Silk Road', 'Ethno'],
    ['Neon', 'Aziz Beats', 'Electronic'],
    ['Yomg\'ir', 'Malika Lo-Fi', 'Lo-Fi'],
  ];
  const ins = db.prepare('INSERT INTO songs (title, artist, genre, audio_url, cover_url) VALUES (?,?,?,?,?)');
  demo.forEach((s, i) =>
    ins.run(s[0], s[1], s[2], `https://www.soundhelix.com/examples/mp3/SoundHelix-Song-${i + 1}.mp3`, '/default-cover.svg')
  );
}

module.exports = db;
