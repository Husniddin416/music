const TelegramBot = require('node-telegram-bot-api');
const db = require('./db');

const normPhone = (p) => String(p || '').replace(/\D/g, '');

const bot = new TelegramBot(process.env.BOT_TOKEN, { polling: true });
bot.on('polling_error', (err) => {
  if (err.code !== 'EFATAL') return;
  console.error('Bot polling xatosi:', err.message);
});
let botUsername = '';
bot.getMe().then(async (me) => {
  botUsername = me.username;
  console.log('Bot ishga tushdi: @' + me.username);
  await initBotInfo();
}).catch((e) => console.error('Bot xatosi:', e.message));

const getSiteUrl = () => (process.env.SITE_URL || 'https://music-l8kd.onrender.com').trim().replace(/\/+$/, '');

async function initBotInfo() {
  try {
    const siteUrl = getSiteUrl();
    const description =
`🎧 MusicUz — Zamonaviy o'zbek musiqa platformasi!

Bu bot orqali siz:
✨ Saytga kirish va ro'yxatdan o'tish uchun kod olasiz
🎵 Minglab yangi va sevimli taronalarni tinglaysiz
❤️ Yoqtirgan musiqalarga layk bosib, saqlab qo'yasiz
🔍 Qo'shiqlar, ijrochilar va janrlar bo'yicha qidirasiz

🌐 Rasmiy saytimiz:
${siteUrl}

Pastdagi "Start" (Boshlash) tugmasini bosing 👇`;

    const shortDescription = `MusicUz — Sevimli qo'shiqlaringizni tinglang. Sayt: ${siteUrl}`;

    if (typeof bot.setMyDescription === 'function') {
      await bot.setMyDescription({ description }).catch(() => {});
    } else {
      await bot._request('setMyDescription', { form: { description } }).catch(() => {});
    }

    if (typeof bot.setMyShortDescription === 'function') {
      await bot.setMyShortDescription({ short_description: shortDescription }).catch(() => {});
    } else {
      await bot._request('setMyShortDescription', { form: { short_description: shortDescription } }).catch(() => {});
    }

    if (siteUrl.startsWith('https://')) {
      if (typeof bot.setChatMenuButton === 'function') {
        await bot.setChatMenuButton({
          menu_button: {
            type: 'web_app',
            text: '🎵 Saytni ochish',
            web_app: { url: siteUrl }
          }
        }).catch(() => {});
      }
    }
  } catch (err) {
    // Info setup is optional, do not crash
  }
}

bot.onText(/\/start/, (msg) => {
  const siteUrl = getSiteUrl();
  bot.sendMessage(msg.chat.id,
    `🎵 <b>MusicUz</b> botiga xush kelibsiz!\n\n` +
    `🌐 Sayt: <a href="${siteUrl}">${siteUrl}</a>\n\n` +
    `Saytga kirish kodini olish uchun pastdagi tugma orqali telefon raqamingizni yuboring:`,
    {
      parse_mode: 'HTML',
      disable_web_page_preview: true,
      reply_markup: {
        keyboard: [[{ text: '📱 Raqamni yuborish', request_contact: true }]],
        resize_keyboard: true, one_time_keyboard: true,
      },
    });
});

bot.onText(/\/(site|link|sayt)/, (msg) => {
  const siteUrl = getSiteUrl();
  bot.sendMessage(msg.chat.id,
    `🎧 <b>MusicUz rasmiy sayti:</b>\n\n🔗 <a href="${siteUrl}">${siteUrl}</a>`,
    {
      parse_mode: 'HTML',
      reply_markup: {
        inline_keyboard: [[{ text: '🌐 Saytni ochish', url: siteUrl }]],
      },
    });
});

bot.onText(/\/donate/, (msg) => {
  const card = process.env.DONATE_CARD;
  bot.sendMessage(msg.chat.id, card
    ? `💜 Loyihani qo'llab-quvvatlash:\n\nKarta: <code>${card}</code>\n${process.env.DONATE_OWNER || ''}`
    : '💜 Donat hozircha sozlanmagan.', { parse_mode: 'HTML' });
});

bot.on('contact', (msg) => {
  const c = msg.contact;
  if (c.user_id !== msg.from.id) {
    return bot.sendMessage(msg.chat.id, '❌ Iltimos, faqat o\'zingizning raqamingizni yuboring.');
  }
  const phone = normPhone(c.phone_number);
  const name = [c.first_name, c.last_name].filter(Boolean).join(' ');
  db.prepare(`INSERT INTO tg_contacts (phone, chat_id, tg_name) VALUES (?,?,?)
    ON CONFLICT(phone) DO UPDATE SET chat_id=excluded.chat_id, tg_name=excluded.tg_name`)
    .run(phone, msg.chat.id, name);
  const siteUrl = getSiteUrl();
  bot.sendMessage(msg.chat.id,
    `✅ Raqamingiz bog'landi: +${phone}\n\n` +
    `Endi quyidagi havola orqali saytga kiring va raqamingizni kiriting:\n🔗 <a href="${siteUrl}">${siteUrl}</a>`,
    {
      parse_mode: 'HTML',
      disable_web_page_preview: true,
      reply_markup: {
        inline_keyboard: [[{ text: '🌐 Saytga o\'tish', url: siteUrl }]],
      },
    });
});

function sendCode(chatId, code) {
  const siteUrl = getSiteUrl();
  return bot.sendMessage(chatId,
    `🔐 MusicUz kirish kodi: <code>${code}</code>\n\n` +
    `⏳ Kod 5 daqiqa amal qiladi. Saytga kirib kodni kiriting:\n🔗 <a href="${siteUrl}">${siteUrl}</a>`,
    {
      parse_mode: 'HTML',
      disable_web_page_preview: true,
      reply_markup: {
        inline_keyboard: [[{ text: '🌐 Saytga kirish', url: siteUrl }]],
      },
    });
}

module.exports = { sendCode, normPhone, getBotUsername: () => botUsername };
