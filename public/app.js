// ================= helpers =================
const $ = (s, r = document) => r.querySelector(s);
const view = $('#view');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let token = localStorage.getItem('token');
let me = null;
let BASE = (location.hostname && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1')
  ? ''
  : (localStorage.getItem('apiBase') || '');
const media = (u) => (u && u.startsWith('/') ? BASE + u : u);

// Backend qaysi portda bo'lsa ham topadi
async function findBackend() {
  const isLiveSite = location.protocol.startsWith('http') && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1';
  if (isLiveSite) {
    BASE = '';
    return true;
  }
  const ok = async (b) => {
    try {
      const c = new AbortController(); setTimeout(() => c.abort(), 1200);
      const r = await fetch(b + '/api/config', { signal: c.signal });
      return r.ok && (await r.json()).hasOwnProperty('bot');
    } catch { return false; }
  };
  const host = location.hostname || 'localhost';
  const cands = [];
  if (location.protocol.startsWith('http')) cands.push('');
  if (BASE) cands.push(BASE);
  for (let p = 3000; p <= 3020; p++) cands.push(`http://${host}:${p}`);
  if (host !== 'localhost') for (let p = 3000; p <= 3020; p++) cands.push(`http://localhost:${p}`);
  for (let i = 0; i < cands.length; i += 7) {
    const batch = cands.slice(i, i + 7);
    const res = await Promise.all(batch.map(ok));
    const hit = batch[res.indexOf(true)];
    if (hit !== undefined) { BASE = hit; localStorage.setItem('apiBase', hit); return true; }
  }
  return false;
}

async function api(url, opts = {}) {
  const headers = opts.body instanceof FormData ? {} : { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = 'Bearer ' + token;
  const res = await fetch(BASE + url, {
    ...opts, headers,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(data.error || 'Xatolik'); e.data = data; e.status = res.status; throw e; }
  return data;
}
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2600);
}
function coverStyle(s) {
  const url = (s && s.cover_url) ? s.cover_url : '/default-cover.svg';
  return `background-image:url('${esc(media(url))}');background-size:cover;background-position:center;`;
}
const initials = () => '';
const fmt = (t) => isFinite(t) ? `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}` : '0:00';

// ================= player =================
const audio = $('#audio');
let queue = [], qi = -1;
audio.volume = 0.8;

function playList(list, i) {
  queue = list; qi = i;
  const s = queue[qi];
  if (!s) return;
  audio.src = media(s.audio_url); audio.play().catch(() => {});
  $('#p-title').textContent = s.title;
  $('#p-artist').textContent = s.artist;
  $('#p-cover').setAttribute('style', coverStyle(s));
  $('#p-cover').innerHTML = initials(s);
  api(`/api/songs/${s.id}/play`, { method: 'POST' }).catch(() => {});
  markPlaying();
}
function markPlaying() {
  document.querySelectorAll('.card').forEach((c) => {
    const on = queue[qi] && +c.dataset.id === queue[qi].id;
    c.classList.toggle('playing', on);
    const f = c.querySelector('.fab'); if (f) f.textContent = on && !audio.paused ? '⏸' : '▶';
  });
}
$('#btn-play').onclick = () => { if (!audio.src) return; audio.paused ? audio.play() : audio.pause(); };
$('#btn-next').onclick = () => queue.length && playList(queue, (qi + 1) % queue.length);
$('#btn-prev').onclick = () => queue.length && playList(queue, (qi - 1 + queue.length) % queue.length);
audio.onplay = audio.onpause = () => { $('#btn-play').textContent = audio.paused ? '▶' : '⏸'; markPlaying(); };
audio.onended = () => $('#btn-next').click();
audio.ontimeupdate = () => {
  $('#p-cur').textContent = fmt(audio.currentTime); $('#p-dur').textContent = fmt(audio.duration);
  if (audio.duration) {
    const p = (audio.currentTime / audio.duration) * 100;
    $('#p-seek').value = p; $('#p-seek').style.setProperty('--pct', p + '%');
  }
};
$('#p-seek').oninput = (e) => audio.duration && (audio.currentTime = (e.target.value / 100) * audio.duration);
$('#p-vol').oninput = (e) => (audio.volume = e.target.value);

// ================= song grid =================
function renderGrid(el, songs, emptyMsg = 'Qo\'shiqlar topilmadi') {
  if (!songs.length) { el.innerHTML = `<div class="empty">🎵 ${emptyMsg}</div>`; return; }
  el.innerHTML = songs.map((s, i) => `
    <article class="card glass" data-id="${s.id}" data-i="${i}" style="animation-delay:${i * 40}ms">
      <div class="cover" style="${coverStyle(s)}">${initials(s)}</div>
      <button class="fab" data-act="play">▶</button>
      <h3>${esc(s.title)}</h3>
      <div class="muted">${esc(s.artist)}${s.genre ? ' · ' + esc(s.genre) : ''}</div>
      <div class="row">
        <span class="muted">❤ ${s.likes} · ▶ ${s.plays}</span>
        <div class="acts">
          <button class="icon-btn" data-act="like" title="Layk">${s.liked ? '❤️' : '🤍'}</button>
          <button class="icon-btn" data-act="save" title="Saqlash">${s.saved ? '🔖' : '📑'}</button>
        </div>
      </div>
    </article>`).join('');
  el.onclick = async (e) => {
    const card = e.target.closest('.card'); if (!card) return;
    const s = songs[card.dataset.i];
    const act = e.target.dataset.act;
    if (act === 'like' || act === 'save') {
      if (!me) { toast('Avval tizimga kiring'); location.hash = '#/login'; return; }
      const r = await api(`/api/songs/${s.id}/${act}`, { method: 'POST' });
      if (act === 'like') { s.liked = r.active; s.likes += r.active ? 1 : -1; e.target.textContent = r.active ? '❤️' : '🤍'; card.querySelector('.row .muted').textContent = `❤ ${s.likes} · ▶ ${s.plays}`; }
      else { s.saved = r.active; e.target.textContent = r.active ? '🔖' : '📑'; toast(r.active ? 'Saqlandi' : 'Saqlanganlardan olindi'); }
      e.target.classList.remove('on'); void e.target.offsetWidth; e.target.classList.add('on');
      return;
    }
    if (queue[qi]?.id === s.id) $('#btn-play').click(); else playList(songs, +card.dataset.i);
  };
  markPlaying();
}

// ================= views =================
async function homeView() {
  const genres = await api('/api/genres');
  view.innerHTML = `
    <section class="hero glass">
      <h1>Musiqa bilan <span class="g">nafas oling</span></h1>
      <p class="muted">Minglab qo'shiqlarni qidiring, tinglang va sevimlilaringizni saqlang.</p>
      ${me ? '' : '<div style="display:flex;gap:10px;margin-top:18px;position:relative;z-index:1"><a href="#/register" class="btn" id="hero-register">🚀 Bepul ro\'yxatdan o\'tish</a><a href="#/login" class="btn ghost" id="hero-login">Kirish</a></div>'}
      <div class="search">
        <input id="q" placeholder="🔍 Qo'shiq, ijrochi yoki janr..." autocomplete="off" />
        <select id="sort"><option value="new">Yangilari</option><option value="popular">Ommaboplari</option></select>
      </div>
      <div class="chips" id="chips"><span class="chip on" data-g="">Barchasi</span>${genres.map((g) => `<span class="chip" data-g="${esc(g)}">${esc(g)}</span>`).join('')}</div>
    </section>
    <h2 id="list-title">🔥 Barcha qo'shiqlar</h2>
    <div class="grid" id="grid"></div>`;
  let genre = '', timer;
  const load = async () => {
    const q = $('#q').value;
    const songs = await api(`/api/songs?q=${encodeURIComponent(q)}&genre=${encodeURIComponent(genre)}&sort=${$('#sort').value}`);
    $('#list-title').textContent = q ? `🔍 "${q}" bo'yicha natijalar (${songs.length})` : '🔥 Barcha qo\'shiqlar';
    renderGrid($('#grid'), songs);
  };
  $('#q').oninput = () => { clearTimeout(timer); timer = setTimeout(load, 300); };
  $('#sort').onchange = load;
  $('#chips').onclick = (e) => {
    if (!e.target.dataset || e.target.dataset.g === undefined) return;
    document.querySelectorAll('.chip').forEach((c) => c.classList.remove('on'));
    e.target.classList.add('on'); genre = e.target.dataset.g; load();
  };
  load();
}

const loginView = () => authView('login');
const registerView = () => authView('register');

async function authView(mode) {
  if (me) return (location.hash = '#/');
  const { bot } = await api('/api/config');
  const botLink = bot ? `https://t.me/${bot}` : '#';
  const reg = mode === 'register';
  view.innerHTML = `
    <section class="auth glass">
      <div class="auth-tabs">
        <a href="#/register" class="${reg ? 'on' : ''}" id="tab-register">Ro'yxatdan o'tish</a>
        <a href="#/login" class="${reg ? '' : 'on'}" id="tab-login">Kirish</a>
      </div>
      <h1>${reg ? 'Ro\'yxatdan <span class="g">o\'tish</span>' : 'Tizimga <span class="g">kirish</span>'}</h1>
      <p class="muted">${reg ? 'Musiqalarni tinglash uchun avval ro\'yxatdan o\'tish majburiy 🎧' : 'Hisobingizga Telegram kodi orqali kiring 🔐'}</p>
      <div class="step"><b>1</b><div><a class="g" href="${botLink}" target="_blank" id="bot-link">@${esc(bot || 'bot')}</a> ga kirib <b class="kbd">/start</b> bosing va raqamingizni yuboring</div></div>
      <div class="step"><b>2</b><div>${reg ? 'Ismingiz va raqamingizni' : 'Raqamingizni'} kiriting — kod botga keladi</div></div>
      <div class="step"><b>3</b><div>Kodni kiriting va tayyor 🎉</div></div>
      <form id="f-phone">
        ${reg ? '<input id="reg-name" placeholder="👤 Ismingiz" required maxlength="50" autocomplete="name" />' : ''}
        <input id="phone" type="tel" placeholder="📱 +998 90 123 45 67" required autocomplete="tel" />
        <button class="btn" id="btn-send">Kod olish ✈️</button>
      </form>
      <form id="f-code" class="hidden">
        <p class="muted">Telegram botga kelgan 6 xonali kodni kiriting</p>
        <input id="code" class="code" maxlength="6" inputmode="numeric" placeholder="••••••" required autocomplete="one-time-code" />
        <button class="btn" id="btn-verify">${reg ? 'Tasdiqlash va Kirish' : 'Kirish'}</button>
        <button type="button" class="btn ghost" id="btn-back">← Raqamni o'zgartirish</button>
      </form>
      <p class="muted" style="margin-top:18px">${reg ? 'Hisobingiz bormi? <a class="g" href="#/login">Kirish</a>' : 'Yangi foydalanuvchimisiz? <a class="g" href="#/register">Ro\'yxatdan o\'ting</a>'}</p>
    </section>`;
  let phone = '';
  $('#f-phone').onsubmit = async (e) => {
    e.preventDefault(); phone = $('#phone').value;
    $('#btn-send').disabled = true;
    try {
      await api('/api/auth/request-code', { method: 'POST', body: { phone, mode } });
      toast('Kod Telegram botga yuborildi ✈️');
      $('#f-phone').classList.add('hidden'); $('#f-code').classList.remove('hidden'); $('#code').focus();
    } catch (err) {
      toast(err.message);
      if (err.data?.needBot && bot) window.open(botLink, '_blank');
      if (err.data?.needRegister) setTimeout(() => (location.hash = '#/register'), 1200);
    } finally { $('#btn-send').disabled = false; }
  };
  $('#f-code').onsubmit = async (e) => {
    e.preventDefault();
    try {
      const r = await api('/api/auth/verify', { method: 'POST', body: { phone, code: $('#code').value, name: $('#reg-name')?.value } });
      token = r.token;
      localStorage.setItem('token', token);
      if (r.user) {
        me = r.user;
        localStorage.setItem('currentUser', JSON.stringify(r.user));
      }
      await loadMe();
      toast(`Xush kelibsiz, ${r.user?.name || ''}! 🎉`);
      location.hash = r.user?.is_admin ? '#/admin' : '#/';
    } catch (err) { toast(err.message); }
  };
  $('#btn-back').onclick = () => { $('#f-code').classList.add('hidden'); $('#f-phone').classList.remove('hidden'); };
}

async function profileView() {
  if (!me) return (location.hash = '#/login');
  const u = await api('/api/me');
  view.innerHTML = `
    <h1>Salom, <span class="g">${esc(u.name)}</span> 👋</h1>
    <p class="muted">+${esc(u.phone)} · A'zo: ${esc(u.created_at.slice(0, 10))} ${u.is_admin ? '<span class="badge pur">Admin</span>' : ''}</p>
    <div class="stats" style="margin-top:24px">
      <div class="stat glass"><div class="muted">Layklar</div><div class="n g">${u.stats.likes}</div></div>
      <div class="stat glass"><div class="muted">Saqlanganlar</div><div class="n g">${u.stats.saved}</div></div>
      <div class="stat glass"><div class="muted">Ismni o'zgartirish</div>
        <form id="f-name" style="display:flex;gap:8px;margin-top:8px"><input id="name" value="${esc(u.name)}" style="flex:1;min-width:0;padding:8px 12px" /><button class="btn sm">✓</button></form></div>
    </div>
    <div class="tabs">
      <button class="chip on" data-t="likes" id="tab-likes">❤️ Layk bosilganlar</button>
      <button class="chip" data-t="saved" id="tab-saved">🔖 Saqlanganlar</button>
      <button class="chip" data-t="history" id="tab-history">🕘 Tinglanganlar</button>
    </div>
    <div class="grid" id="grid"></div>`;
  const load = async (t) => renderGrid($('#grid'), await api('/api/me/' + t), { likes: 'Hali layk bosilmagan', saved: 'Hali hech narsa saqlanmagan', history: 'Hali hech narsa tinglanmagan' }[t]);
  document.querySelector('.tabs').onclick = (e) => {
    if (!e.target.dataset.t) return;
    document.querySelectorAll('.tabs .chip').forEach((c) => c.classList.remove('on'));
    e.target.classList.add('on'); load(e.target.dataset.t);
  };
  $('#f-name').onsubmit = async (e) => {
    e.preventDefault(); await api('/api/me', { method: 'PUT', body: { name: $('#name').value } });
    await loadMe(); toast('Saqlandi'); profileView();
  };
  load('likes');
}

async function adminView() {
  if (!me?.is_admin) return (location.hash = '#/');
  const st = await api('/api/admin/stats');
  view.innerHTML = `
    <h1>Admin <span class="g">panel</span></h1>
    <div class="stats" style="margin-top:24px">
      ${[['👥 Foydalanuvchilar', st.users], ['🎵 Qo\'shiqlar', st.songs], ['❤️ Layklar', st.likes], ['▶ Tinglashlar', st.plays]]
        .map(([l, n]) => `<div class="stat glass"><div class="muted">${l}</div><div class="n g">${n}</div></div>`).join('')}
    </div>
    <div class="tabs">
      <button class="chip on" data-t="songs" id="atab-songs">🎵 Qo'shiqlar</button>
      <button class="chip" data-t="users" id="atab-users">👥 Foydalanuvchilar</button>
    </div>
    <div id="admin-body"></div>`;
  document.querySelector('.tabs').onclick = (e) => {
    if (!e.target.dataset.t) return;
    document.querySelectorAll('.tabs .chip').forEach((c) => c.classList.remove('on'));
    e.target.classList.add('on'); e.target.dataset.t === 'songs' ? adminSongs() : adminUsers();
  };
  adminSongs();
}

async function adminSongs(edit = null) {
  const body = $('#admin-body');
  const songs = await api('/api/songs');
  body.innerHTML = `
    <form class="panel glass" id="f-song">
      <h2 style="margin-top:0">${edit ? '✏️ Tahrirlash: ' + esc(edit.title) : '➕ Yangi qo\'shiq qo\'shish'}</h2>
      
      <div class="form-grid">
        <label>🎵 Qo'shiq nomi *<input name="title" value="${esc(edit?.title)}" required placeholder="Masalan: Lola" /></label>
        <label>👤 Ijrochi (Artist) *<input name="artist" value="${esc(edit?.artist)}" required placeholder="Masalan: Yulduz Usmonova" /></label>
        <label>🏷 Janr (Ixtiyoriy)<input name="genre" value="${esc(edit?.genre)}" placeholder="Pop, Retro, Chill..." /></label>
      </div>

      <div style="margin-top:16px;padding:16px;border-radius:14px;background:hsla(0,0%,100%,0.04);border:1px solid var(--border)">
        <div style="font-weight:600;margin-bottom:8px">🎧 Audio manbasi (Fayl yoki Havola):</div>
        <div class="form-grid">
          <label>📁 MP3 / Audio fayl yuklash
            <input type="file" name="audio" accept="audio/*" />
          </label>
          <label>🔗 Yoki Audio internet havolasi (URL)
            <input name="audio_url" value="${esc(edit?.audio_url && !edit.audio_url.startsWith('/uploads') ? edit.audio_url : '')}" placeholder="https://.../music.mp3" />
          </label>
        </div>
        <div class="muted" style="font-size:0.82rem;margin-top:6px">💡 Ikkisidan biri yetarli: kompyuterdan mp3 yuklash yoki internet linkini yozish mumkin.</div>
      </div>

      <div style="margin-top:14px;padding:16px;border-radius:14px;background:hsla(0,0%,100%,0.04);border:1px solid var(--border)">
        <div style="font-weight:600;margin-bottom:8px">🖼 Muqova rasmi (Ixtiyoriy):</div>
        <div class="form-grid">
          <label>📁 Rasm fayl yuklash (.jpg, .png)
            <input type="file" name="cover" accept="image/*" />
          </label>
          <label>🔗 Yoki Rasm havolasi (URL)
            <input name="cover_url" value="${esc(edit?.cover_url && !edit.cover_url.startsWith('/uploads') && edit.cover_url !== '/default-cover.svg' ? edit.cover_url : '')}" placeholder="https://.../cover.jpg" />
          </label>
        </div>
        <div class="muted" style="font-size:0.82rem;margin-top:6px">✨ Rasm kiritish ixtiyoriy. Agar bo'sh qoldirilsa, avtomatik bir xil MusicUz rasmi qo'yiladi.</div>
      </div>

      <div style="display:flex;gap:10px;margin-top:18px">
        <button class="btn" id="btn-save-song">${edit ? '💾 Saqlash' : '➕ Qo\'shiqni qo\'shish'}</button>
        ${edit ? '<button type="button" class="btn ghost" id="btn-cancel">Bekor qilish</button>' : ''}
      </div>
    </form>
    <div class="panel glass" style="margin-top:20px">
      <table><thead><tr><th>Muqova</th><th>Nomi</th><th>Ijrochi</th><th>Janr</th><th>❤</th><th>▶</th><th></th></tr></thead>
      <tbody>${songs.map((s) => `<tr>
        <td><div class="cover sm" style="${coverStyle(s)}"></div></td>
        <td>${esc(s.title)}</td><td>${esc(s.artist)}</td><td>${esc(s.genre || '—')}</td><td>${s.likes}</td><td>${s.plays}</td>
        <td style="white-space:nowrap"><button class="btn sm ghost" data-edit="${s.id}">✏️</button> <button class="btn sm danger" data-del="${s.id}">🗑</button></td>
      </tr>`).join('')}</tbody></table>
    </div>`;
  $('#f-song').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const audioFile = fd.get('audio');
    const audioUrl = (fd.get('audio_url') || '').trim();
    if (!edit && (!audioFile || !audioFile.size) && !audioUrl) {
      toast('Iltimos, audio fayl tanlang yoki audio linkini kiriting!');
      return;
    }
    const btn = $('#btn-save-song');
    btn.disabled = true;
    try {
      await api(edit ? `/api/admin/songs/${edit.id}` : '/api/admin/songs', { method: edit ? 'PUT' : 'POST', body: fd });
      toast(edit ? 'Musiqa yangilandi ✅' : 'Qo\'shiq qo\'shildi 🎉');
      adminSongs();
    } catch (err) { toast(err.message); }
    finally { btn.disabled = false; }
  };
  if (edit) $('#btn-cancel').onclick = () => adminSongs();
  body.querySelector('table').onclick = async (e) => {
    const d = e.target.dataset;
    if (d.edit) { adminSongs(songs.find((s) => s.id == d.edit)); window.scrollTo({ top: 0, behavior: 'smooth' }); }
    if (d.del && confirm('O\'chirilsinmi?')) { await api('/api/admin/songs/' + d.del, { method: 'DELETE' }); toast('O\'chirildi'); adminSongs(); }
  };
}

async function adminUsers() {
  const users = await api('/api/admin/users');
  $('#admin-body').innerHTML = `<div class="panel glass"><table>
    <thead><tr><th>#</th><th>Ism</th><th>Telefon</th><th>Layklar</th><th>Sana</th><th>Holat</th><th></th></tr></thead>
    <tbody>${users.map((u) => `<tr>
      <td>${u.id}</td><td>${esc(u.name)}</td><td>+${esc(u.phone)}</td><td>${u.likes}</td><td>${esc(u.created_at.slice(0, 10))}</td>
      <td>${u.is_admin ? '<span class="badge pur">Admin</span>' : u.is_blocked ? '<span class="badge red">Bloklangan</span>' : '<span class="badge">Faol</span>'}</td>
      <td>${u.is_admin ? '' : `<button class="btn sm ${u.is_blocked ? 'ghost' : 'danger'}" data-block="${u.id}">${u.is_blocked ? 'Blokdan chiqarish' : 'Bloklash'}</button>`}</td>
    </tr>`).join('')}</tbody></table></div>`;
  $('#admin-body table').onclick = async (e) => {
    if (!e.target.dataset.block) return;
    await api(`/api/admin/users/${e.target.dataset.block}/block`, { method: 'POST' }); adminUsers();
  };
}

// ================= auth state & router =================
async function loadMe() {
  if (!token) {
    me = null;
    localStorage.removeItem('currentUser');
  } else {
    // 1. Avval keshdan o'qiymiz — sahifa yangilanganda ro'yxatdan o'tishga otib yubormasligi uchun
    try {
      const cached = localStorage.getItem('currentUser');
      if (cached) me = JSON.parse(cached);
    } catch {}

    // 2. Serverdan yangi profil ma'lumotlarini tekshiramiz
    try {
      const fresh = await api('/api/me');
      me = fresh;
      localStorage.setItem('currentUser', JSON.stringify(fresh));
    } catch (err) {
      // FAQAT server "401 - Token eskirgan/noto'g'ri" desa tizimdan chiqaramiz.
      // Server sekinlashsa yoki vaqtincha xatolik bersa token saqlanib qoladi!
      if (err.status === 401) {
        me = null;
        token = null;
        localStorage.removeItem('token');
        localStorage.removeItem('currentUser');
      }
    }
  }

  const isGuest = !me;
  document.body.classList.toggle('guest', isGuest);
  $('#player').classList.toggle('hidden', isGuest);
  $('nav').classList.toggle('hidden', isGuest);
  $('#nav-admin').classList.toggle('hidden', !me?.is_admin);

  $('#user-box').innerHTML = me
    ? `<div>👤 <b>${esc(me.name)}</b></div><div class="muted">+${esc(me.phone)}</div><button class="btn sm ghost" id="btn-logout" style="margin-top:10px;width:100%">Chiqish</button>`
    : `<div class="muted" style="text-align:center;font-size:0.85rem">Ro'yxatdan o'tish majburiy</div>`;

  if (me) {
    $('#btn-logout').onclick = () => {
      token = null;
      me = null;
      localStorage.removeItem('token');
      localStorage.removeItem('currentUser');
      if (audio) { audio.pause(); audio.src = ''; }
      loadMe();
      location.hash = '#/register';
      toast('Tizimdan chiqdingiz');
    };
  }
}

async function donateView() {
  const cfg = await api('/api/config');
  const d = cfg.donate || {};
  const rawCard = String(d.card || '8600000000000000').replace(/\D/g, '');
  const fmtCard = rawCard.replace(/(\d{4})/g, '$1 ').trim();
  const brand = rawCard.startsWith('8600') ? 'UZCARD' : rawCard.startsWith('9860') ? 'HUMO' : 'BANK KARTA';
  const botLink = cfg.bot ? `https://t.me/${cfg.bot}` : 'https://t.me';

  view.innerHTML = `
    <section class="donate-page">
      <div class="donate-header">
        <div class="donate-pill">💜 Loyihani qo'llab-quvvatlash</div>
        <h1>Musiqani birga <span class="g">rivojlantiramiz</span></h1>
        <p class="muted">Sizning kichik donatingiz ham sayt serverlari va yangi musiqalar uchun katta hissa qo'shadi ✨</p>
      </div>

      <div class="donate-grid">
        <!-- Chap: Realistic Bank Card & Presets -->
        <div class="donate-col">
          <div class="bank-card" id="bank-card" title="Nusxalash uchun bosing">
            <div class="bc-top">
              <div class="bc-chip">
                <span></span><span></span><span></span>
              </div>
              <div class="bc-brand">${brand}</div>
            </div>
            <div class="bc-number" id="bc-num-txt">${esc(fmtCard)}</div>
            <div class="bc-bottom">
              <div>
                <div class="bc-label">Karta egasi</div>
                <div class="bc-name">${esc(d.owner || 'MusicUz')}</div>
              </div>
              <button class="bc-copy-btn" id="bc-copy-btn" type="button">📋 Nusxalash</button>
            </div>
          </div>

          <div class="panel glass" style="margin-top:18px">
            <div style="font-weight:600;margin-bottom:12px">⚡ Tezkor xayriya miqdori:</div>
            <div class="preset-amounts" id="preset-amounts">
              <div class="preset-card" data-amt="5 000">
                <span class="pr-emoji">☕</span>
                <span class="pr-sum">5 000</span>
                <span class="pr-desc">Choy</span>
              </div>
              <div class="preset-card on" data-amt="15 000">
                <span class="pr-emoji">🍦</span>
                <span class="pr-sum">15 000</span>
                <span class="pr-desc">Muzqaymoq</span>
              </div>
              <div class="preset-card" data-amt="30 000">
                <span class="pr-emoji">🍕</span>
                <span class="pr-sum">30 000</span>
                <span class="pr-desc">Pitsa</span>
              </div>
              <div class="preset-card" data-amt="50 000">
                <span class="pr-emoji">🎧</span>
                <span class="pr-sum">50 000</span>
                <span class="pr-desc">Server</span>
              </div>
              <div class="preset-card" data-amt="100 000">
                <span class="pr-emoji">🚀</span>
                <span class="pr-sum">100 000</span>
                <span class="pr-desc">Homiy</span>
              </div>
            </div>
          </div>
        </div>

        <!-- O'ng: Apps & Perks -->
        <div class="donate-col">
          <div class="panel glass">
            <h3 style="margin-bottom:6px">💳 To'lov ilovalari:</h3>
            <p class="muted" style="font-size:0.86rem;margin-bottom:14px">Qulay to'lov tizimini tanlang va kartaga o'tkazing:</p>

            <div class="pay-apps">
              <a class="pay-app-btn payme" id="btn-payme" href="${d.payme ? esc(d.payme) : 'javascript:void(0)'}" ${d.payme ? 'target="_blank"' : ''}>
                <span class="pa-name">payme</span>
                <span class="pa-hint">${d.payme ? 'To\'lov qilish →' : 'Karta nusxalanadi'}</span>
              </a>
              <a class="pay-app-btn click" id="btn-click" href="${d.click ? esc(d.click) : 'javascript:void(0)'}" ${d.click ? 'target="_blank"' : ''}>
                <span class="pa-name">click</span>
                <span class="pa-hint">${d.click ? 'To\'lov qilish →' : 'Karta nusxalanadi'}</span>
              </a>
              <a class="pay-app-btn uzum" id="btn-uzum" href="${d.uzum ? esc(d.uzum) : 'javascript:void(0)'}" ${d.uzum ? 'target="_blank"' : ''}>
                <span class="pa-name">uzum</span>
                <span class="pa-hint">${d.uzum ? 'To\'lov qilish →' : 'Karta nusxalanadi'}</span>
              </a>
            </div>

            <div class="donate-why">
              <h4>🎯 Mablag' nimalarga sarflanadi?</h4>
              <ul>
                <li>⚡ <b>Tezkor serverlar:</b> Sayt va pleyer 24/7 uzluksiz, chaqqon ishlashi uchun</li>
                <li>🎵 <b>Yangi musiqalar:</b> Har kuni sara va sifatli qo'shiqlar bazasini kengaytirish</li>
                <li>🤖 <b>Telegram bot:</b> Kirish kodlarini 1 soniyada bepul yetkazib berish</li>
              </ul>
            </div>

            <div class="donate-perk">
              <div>💬 Donat yubordingizmi? Chekni botga yuboring — profilingizga maxsus <b>Homiy 💜</b> nishoni beriladi!</div>
              <a href="${botLink}" target="_blank" class="btn sm" style="margin-top:12px;display:inline-block">✈️ Botga xabar yuborish</a>
            </div>
          </div>
        </div>
      </div>
    </section>`;

  const copyCard = () => {
    navigator.clipboard.writeText(rawCard).then(() => {
      const btn = $('#bc-copy-btn');
      if (btn) btn.textContent = 'Nusxalandi! ✓';
      setTimeout(() => { if (btn) btn.textContent = '📋 Nusxalash'; }, 2000);
      toast(`Karta raqami nusxalandi: ${fmtCard} ✅`);
    }).catch(() => toast('Karta: ' + fmtCard));
  };

  $('#bank-card').onclick = copyCard;
  $('#bc-copy-btn').onclick = (e) => { e.stopPropagation(); copyCard(); };

  if (!d.payme) $('#btn-payme').onclick = () => { copyCard(); toast('Karta nusxalandi! Payme ilovasiga o\'tib o\'tkazing 📱'); };
  if (!d.click) $('#btn-click').onclick = () => { copyCard(); toast('Karta nusxalandi! Click ilovasiga o\'tib o\'tkazing 📱'); };
  if (!d.uzum) $('#btn-uzum').onclick = () => { copyCard(); toast('Karta nusxalandi! Uzum ilovasiga o\'tib o\'tkazing 📱'); };

  $('#preset-amounts').onclick = (e) => {
    const card = e.target.closest('.preset-card');
    if (!card) return;
    document.querySelectorAll('.preset-card').forEach((c) => c.classList.remove('on'));
    card.classList.add('on');
    copyCard();
    toast(`${card.dataset.amt} so'm tanlandi! Karta nusxalandi, ilovadan o'tkazishingiz mumkin 💜`);
  };
}

const routes = { '': homeView, login: loginView, register: registerView, profile: profileView, admin: adminView, donate: donateView };
function router() {
  const r = location.hash.replace(/^#\/?/, '');
  
  // Agar foydalanuvchi tizimga kirmagan bo'lsa — faqat ro'yxatdan o'tish yoki kirish mumkin!
  if (!me) {
    if (r !== 'login' && r !== 'register') {
      location.hash = '#/register';
      return;
    }
  } else {
    // Agar foydalanuvchi allaqachon kirgan bo'lsa va login/register ga borsa, bosh sahifaga yo'naltirish
    if (r === 'login' || r === 'register') {
      location.hash = '#/';
      return;
    }
  }

  document.querySelectorAll('nav a').forEach((a) => a.classList.toggle('active', a.dataset.route === r));
  (routes[r] || homeView)().catch((e) => toast(e.message));
}
window.addEventListener('hashchange', router);
view.innerHTML = '<div class="empty">⏳ Server qidirilmoqda...</div>';
findBackend().then((found) => {
  if (found) return loadMe().then(router);
  view.innerHTML = `<section class="auth glass"><h1>Server <span class="g">topilmadi</span></h1>
    <p class="muted" style="margin-top:12px">Backend ishga tushmagan. Papkada terminal oching:</p>
    <div class="step"><b>1</b><div><b class="kbd">npm install</b></div></div>
    <div class="step"><b>2</b><div><b class="kbd">npm start</b></div></div>
    <div class="step"><b>3</b><div>Sahifani yangilang (F5)</div></div></section>`;
});
