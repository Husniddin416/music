"""
main.py — MusicUz asosiy kirish nuqtasi
Uvicorn + FastAPI + aiogram bir jarayonda ishlaydi.
"""
import sys
import asyncio
import logging
import os
import socket
from pathlib import Path

# server/ paketini topish uchun
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import uvicorn
from aiogram import Bot
from server.db import init_db
from server.bot import dp, init_bot
from server.routes import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger("musicuz")


def get_local_ips() -> list[str]:
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return ips


def find_free_port(start: int = 3000, tries: int = 20) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("0.0.0.0", port)) != 0:
                return port
    return start


async def run_bot(bot: Bot):
    """aiogram polling — FastAPI bilan parallel ishlaydi"""
    logger.info("Bot polling boshlandi...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def run_server(port: int):
    """Uvicorn — async rejimda"""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    # 1. Ma'lumotlar bazasini ishga tushir
    init_db()
    logger.info("Baza tayyor ✓")

    # 2. Botni ishga tushir
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        logger.error("BOT_TOKEN topilmadi! .env faylini tekshiring.")
        return

    bot = await init_bot(token)

    # 3. Bo'sh port tanlash
    start_port = int(os.getenv("PORT", 3000))
    port = find_free_port(start_port)
    if port != start_port:
        logger.warning(f"{start_port}-port band, {port} ishlatilmoqda")

    logger.info(f"\n🎧 MusicUz ishga tushdi!")
    logger.info(f"   Kompyuterda: http://localhost:{port}")
    for ip in get_local_ips():
        logger.info(f"   Tarmoqda:    http://{ip}:{port}")
    logger.info(f"   API hujjat:  http://localhost:{port}/api/docs\n")

    # 4. Bot va server parallel ishlaydi
    await asyncio.gather(
        run_bot(bot),
        run_server(port),
    )


if __name__ == "__main__":
    asyncio.run(main())
