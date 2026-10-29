const TelegramBot = require('node-telegram-bot-api');
const db = require('./db');

const normPhone = (p) => String(p || '').replace(/\D/g, '');

const bot = new TelegramBot(process.env.BOT_TOKEN, { polling: true });
bot.on('polling_error', (err) => {
  if (err.code !== 'EFATAL') return;
  console.error('Bot polling xatosi:', err.message);
});
let botUsername = '';
bot.getMe().then((me) => { botUsername = me.username; console.log('Bot ishga tushdi: @' + me.username); })
  .catch((e) => console.error('Bot xatosi:', e.message));

bot.onText(/\/start/, (msg) => {
  bot.sendMessage(msg.chat.id,
    '🎵 <b>MusicUz</b> botiga xush kelibsiz!\n\nSaytga kirish kodlarini olish uchun pastdagi tugma orqali telefon raqamingizni yuboring.',
    {
      parse_mode: 'HTML',
      reply_markup: {
        keyboard: [[{ text: '📱 Raqamni yuborish', request_contact: true }]],
        resize_keyboard: true, one_time_keyboard: true,
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
  bot.sendMessage(msg.chat.id,
    `✅ Raqamingiz bog'landi: +${phone}\n\nEndi saytda shu raqamni kiriting — kirish kodi shu yerga keladi.`,
    { reply_markup: { remove_keyboard: true } });
});

function sendCode(chatId, code) {
  return bot.sendMessage(chatId,
    `🔐 MusicUz kirish kodi: <code>${code}</code>\n\nKod 5 daqiqa amal qiladi. Hech kimga bermang!`,
    { parse_mode: 'HTML' });
}

module.exports = { sendCode, normPhone, getBotUsername: () => botUsername };
