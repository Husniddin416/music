require('dotenv').config();
const express = require('express');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const jwt = require('jsonwebtoken');
const multer = require('multer');
const db = require('./db');
const { sendCode, normPhone, getBotUsername } = require('./bot');

const app = express();
app.use(express.json());
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});
// BigInt ni JSON da to'g'ri raqam qilib yuborish
BigInt.prototype.toJSON = function () {
  return Number(this);
};

const ROOT = path.join(__dirname, '..');
const UPLOADS = path.join(ROOT, 'uploads');
fs.mkdirSync(UPLOADS, { recursive: true });
app.use('/uploads', express.static(UPLOADS));
app.use(express.static(path.join(ROOT, 'public')));

const ADMIN_PHONES = (process.env.ADMIN_PHONE || '').split(',').map(normPhone).filter(Boolean);
const SECRET = process.env.JWT_SECRET || 'music_uz_super_jwt_secret_key_2026';

// ---------- middleware ----------
function auth(required = true) {
  return (req, res, next) => {
    const t = (req.headers.authorization || '').replace('Bearer ', '');
    try {
      const { id } = jwt.verify(t, SECRET);
      const u = db.prepare('SELECT * FROM users WHERE id=?').get(id);
      if (!u || u.is_blocked) throw new Error();
      req.user = u;
    } catch {
      if (required) return res.status(401).json({ error: 'Avval tizimga kiring' });
    }
    next();
  };
}
const admin = (req, res, next) =>
  req.user?.is_admin ? next() : res.status(403).json({ error: 'Faqat admin uchun' });

// ---------- auth ----------
app.get('/api/config', (req, res) => res.json({
  bot: getBotUsername(),
  donate: {
    card: process.env.DONATE_CARD || '',
    owner: process.env.DONATE_OWNER || '',
    payme: process.env.DONATE_PAYME || '',
    click: process.env.DONATE_CLICK || '',
  },
}));

app.post('/api/auth/request-code', async (req, res) => {
  const phone = normPhone(req.body.phone);
  if (phone.length < 9) return res.status(400).json({ error: 'Telefon raqam noto\'g\'ri' });
  const exists = db.prepare('SELECT 1 FROM users WHERE phone=?').get(phone);
  if (req.body.mode === 'login' && !exists)
    return res.status(404).json({ error: 'Bu raqam ro\'yxatdan o\'tmagan. Avval ro\'yxatdan o\'ting.', needRegister: true });
  if (req.body.mode === 'register' && exists)
    return res.status(409).json({ error: 'Bu raqam allaqachon ro\'yxatdan o\'tgan. Kirish bo\'limidan foydalaning.' });
  const contact = db.prepare('SELECT * FROM tg_contacts WHERE phone=?').get(phone);
  if (!contact) {
    return res.status(404).json({
      error: 'Bu raqam botga bog\'lanmagan. Avval botga /start bosib, raqamingizni yuboring.',
      needBot: true, bot: getBotUsername(),
    });
  }
  const code = String(crypto.randomInt(100000, 1000000));
  db.prepare(`INSERT INTO codes (phone, code, expires_at, attempts) VALUES (?,?,?,0)
    ON CONFLICT(phone) DO UPDATE SET code=excluded.code, expires_at=excluded.expires_at, attempts=0`)
    .run(phone, code, Date.now() + 5 * 60 * 1000);
  try {
    await sendCode(contact.chat_id, code);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: 'Kod yuborilmadi: ' + e.message });
  }
});

app.post('/api/auth/verify', (req, res) => {
  const phone = normPhone(req.body.phone);
  const row = db.prepare('SELECT * FROM codes WHERE phone=?').get(phone);
  if (!row || row.expires_at < Date.now()) return res.status(400).json({ error: 'Kod eskirgan, qayta so\'rang' });
  if (row.attempts >= 5) return res.status(429).json({ error: 'Juda ko\'p urinish, qayta kod so\'rang' });
  if (row.code !== String(req.body.code).trim()) {
    db.prepare('UPDATE codes SET attempts=attempts+1 WHERE phone=?').run(phone);
    return res.status(400).json({ error: 'Kod noto\'g\'ri' });
  }
  db.prepare('DELETE FROM codes WHERE phone=?').run(phone);
  const contact = db.prepare('SELECT * FROM tg_contacts WHERE phone=?').get(phone);
  const shouldBeAdmin = ADMIN_PHONES.length === 0 || ADMIN_PHONES.includes(phone) || Number(db.prepare('SELECT COUNT(*) c FROM users WHERE is_admin=1').get().c) === 0;
  let user = db.prepare('SELECT * FROM users WHERE phone=?').get(phone);
  if (!user) {
    const r = db.prepare('INSERT INTO users (phone, name, chat_id, is_admin) VALUES (?,?,?,?)')
      .run(phone, String(req.body.name || '').trim().slice(0, 50) || contact?.tg_name || 'Foydalanuvchi', contact?.chat_id, shouldBeAdmin ? 1 : 0);
    user = db.prepare('SELECT * FROM users WHERE id=?').get(Number(r.lastInsertRowid));
  } else if (!user.is_admin && shouldBeAdmin) {
    db.prepare('UPDATE users SET is_admin=1 WHERE id=?').run(user.id);
    user.is_admin = 1;
  }
  if (user.is_blocked) return res.status(403).json({ error: 'Hisobingiz bloklangan' });
  const token = jwt.sign({ id: user.id }, SECRET, { expiresIn: '30d' });
  res.json({ token, user });
});

// ---------- songs ----------
const songSelect = (uid) => `
  SELECT s.*, (SELECT COUNT(*) FROM likes l WHERE l.song_id=s.id) likes,
  EXISTS(SELECT 1 FROM likes WHERE song_id=s.id AND user_id=${uid}) liked,
  EXISTS(SELECT 1 FROM saved WHERE song_id=s.id AND user_id=${uid}) saved
  FROM songs s`;

app.get('/api/songs', auth(true), (req, res) => {
  const uid = req.user.id;
  const q = `%${(req.query.q || '').trim()}%`;
  const genre = req.query.genre || '';
  const sort = req.query.sort === 'popular' ? 'plays DESC' : 's.id DESC';
  res.json(db.prepare(`${songSelect(uid)}
    WHERE (s.title LIKE ? OR s.artist LIKE ? OR s.genre LIKE ?) AND (?='' OR s.genre=?)
    ORDER BY ${sort}`).all(q, q, q, genre, genre));
});

app.get('/api/genres', auth(true), (req, res) =>
  res.json(db.prepare('SELECT DISTINCT genre FROM songs WHERE genre IS NOT NULL ORDER BY genre').all().map((r) => r.genre)));

app.post('/api/songs/:id/play', auth(true), (req, res) => {
  db.prepare('UPDATE songs SET plays=plays+1 WHERE id=?').run(req.params.id);
  db.prepare('INSERT INTO history (user_id, song_id) VALUES (?,?)').run(req.user.id, req.params.id);
  res.json({ ok: true });
});

function toggle(table) {
  return (req, res) => {
    const args = [req.user.id, req.params.id];
    const has = db.prepare(`SELECT 1 FROM ${table} WHERE user_id=? AND song_id=?`).get(...args);
    if (has) db.prepare(`DELETE FROM ${table} WHERE user_id=? AND song_id=?`).run(...args);
    else db.prepare(`INSERT INTO ${table} (user_id, song_id) VALUES (?,?)`).run(...args);
    res.json({ active: !has });
  };
}
app.post('/api/songs/:id/like', auth(), toggle('likes'));
app.post('/api/songs/:id/save', auth(), toggle('saved'));

// ---------- user panel ----------
app.get('/api/me', auth(), (req, res) => {
  const u = req.user;
  res.json({
    ...u,
    stats: {
      likes: db.prepare('SELECT COUNT(*) c FROM likes WHERE user_id=?').get(u.id).c,
      saved: db.prepare('SELECT COUNT(*) c FROM saved WHERE user_id=?').get(u.id).c,
    },
  });
});
app.put('/api/me', auth(), (req, res) => {
  const name = String(req.body.name || '').trim().slice(0, 50);
  if (name) db.prepare('UPDATE users SET name=? WHERE id=?').run(name, req.user.id);
  res.json({ ok: true });
});
app.get('/api/me/likes', auth(), (req, res) =>
  res.json(db.prepare(`${songSelect(req.user.id)} WHERE s.id IN (SELECT song_id FROM likes WHERE user_id=?) ORDER BY s.id DESC`).all(req.user.id)));
app.get('/api/me/history', auth(), (req, res) =>
  res.json(db.prepare(`${songSelect(req.user.id)} JOIN (SELECT song_id, MAX(id) h FROM history WHERE user_id=? GROUP BY song_id) x ON x.song_id=s.id ORDER BY x.h DESC LIMIT 50`).all(req.user.id)));
app.get('/api/me/saved', auth(), (req, res) =>
  res.json(db.prepare(`${songSelect(req.user.id)} WHERE s.id IN (SELECT song_id FROM saved WHERE user_id=?) ORDER BY s.id DESC`).all(req.user.id)));

// ---------- admin ----------
const upload = multer({
  storage: multer.diskStorage({
    destination: UPLOADS,
    filename: (req, f, cb) => cb(null, Date.now() + '-' + crypto.randomBytes(4).toString('hex') + path.extname(f.originalname)),
  }),
  limits: { fileSize: 30 * 1024 * 1024 },
});
const songFiles = upload.fields([{ name: 'audio', maxCount: 1 }, { name: 'cover', maxCount: 1 }]);

app.get('/api/admin/stats', auth(), admin, (req, res) => {
  const c = (sql) => db.prepare(sql).get().c;
  res.json({
    users: c('SELECT COUNT(*) c FROM users'),
    songs: c('SELECT COUNT(*) c FROM songs'),
    likes: c('SELECT COUNT(*) c FROM likes'),
    plays: c('SELECT COALESCE(SUM(plays),0) c FROM songs'),
  });
});

app.post('/api/admin/songs', auth(), admin, songFiles, (req, res) => {
  const { title, artist, genre, audio_url, cover_url } = req.body;
  const audio = req.files?.audio ? '/uploads/' + req.files.audio[0].filename : (audio_url || '').trim();
  const cover = req.files?.cover ? '/uploads/' + req.files.cover[0].filename : ((cover_url || '').trim() || '/default-cover.svg');
  if (!title?.trim() || !artist?.trim() || !audio) {
    return res.status(400).json({ error: 'Nomi, ijrochi va audio (fayl yoki havola) majburiy' });
  }
  const r = db.prepare('INSERT INTO songs (title, artist, genre, audio_url, cover_url) VALUES (?,?,?,?,?)')
    .run(title.trim(), artist.trim(), genre?.trim() || null, audio, cover);
  res.json({ id: Number(r.lastInsertRowid) });
});

app.put('/api/admin/songs/:id', auth(), admin, songFiles, (req, res) => {
  const s = db.prepare('SELECT * FROM songs WHERE id=?').get(req.params.id);
  if (!s) return res.status(404).json({ error: 'Topilmadi' });
  const b = req.body;
  const audio = req.files?.audio ? '/uploads/' + req.files.audio[0].filename : (b.audio_url ? b.audio_url.trim() : s.audio_url);
  let cover = s.cover_url;
  if (req.files?.cover) {
    cover = '/uploads/' + req.files.cover[0].filename;
  } else if (b.cover_url !== undefined && b.cover_url.trim()) {
    cover = b.cover_url.trim();
  }
  if (!cover) cover = '/default-cover.svg';
  db.prepare('UPDATE songs SET title=?, artist=?, genre=?, audio_url=?, cover_url=? WHERE id=?').run(
    b.title?.trim() || s.title, b.artist?.trim() || s.artist, b.genre !== undefined ? (b.genre.trim() || null) : s.genre,
    audio, cover, s.id);
  res.json({ ok: true });
});

app.delete('/api/admin/songs/:id', auth(), admin, (req, res) => {
  db.prepare('DELETE FROM songs WHERE id=?').run(req.params.id);
  res.json({ ok: true });
});

app.get('/api/admin/users', auth(), admin, (req, res) =>
  res.json(db.prepare(`SELECT u.*, (SELECT COUNT(*) FROM likes WHERE user_id=u.id) likes
    FROM users u ORDER BY u.id DESC`).all()));

app.post('/api/admin/users/:id/block', auth(), admin, (req, res) => {
  const u = db.prepare('SELECT * FROM users WHERE id=?').get(req.params.id);
  if (!u || u.is_admin) return res.status(400).json({ error: 'Adminni bloklab bo\'lmaydi' });
  db.prepare('UPDATE users SET is_blocked=? WHERE id=?').run(u.is_blocked ? 0 : 1, u.id);
  res.json({ blocked: !u.is_blocked });
});

app.get(/^\/(?!api|uploads).*/, (req, res) => res.sendFile(path.join(ROOT, 'public', 'index.html')));

function start(port, triesLeft = 20) {
  const server = app.listen(port, '0.0.0.0', () => {
    const nets = Object.values(require('os').networkInterfaces()).flat()
      .filter((n) => n && n.family === 'IPv4' && !n.internal).map((n) => n.address);
    console.log(`\n🎧 Sayt ishga tushdi:`);
    console.log(`   Kompyuterda: http://localhost:${port}`);
    nets.forEach((ip) => console.log(`   Tarmoqda:    http://${ip}:${port}`));
  });
  server.on('error', (e) => {
    if (e.code === 'EADDRINUSE' && triesLeft > 0) {
      console.log(`⚠️  ${port}-port band, ${port + 1} sinab ko'rilmoqda...`);
      start(port + 1, triesLeft - 1);
    } else throw e;
  });
}
start(Number(process.env.PORT) || 3000);
