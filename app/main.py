"""Application entry point: assemble bot, dispatcher, and dependencies."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is in sys.path when running app/main.py directly
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiohttp import web

from app.bot.callbacks.downloader_callbacks import downloader_callback_router
from app.bot.callbacks.router import callback_router
from app.bot.handlers.commands import command_router
from app.bot.handlers.downloader_handler import downloader_router
from app.bot.middleware.db_middleware import DatabaseMiddleware
from app.bot.middleware.logging_middleware import LoggingMiddleware
from app.bot.middleware.rate_limit_middleware import RateLimitMiddleware
from app.config import Config
from app.database.database import Database
from app.logging_config import configure_logging, get_logger
from app.providers.kkphim.client import KKPhimClient
from app.services.cache_service import CacheService
from app.services.movie_service import MovieService

logger = get_logger(__name__)


def create_bot(config: Config) -> Bot:
    """Create and configure the Telegram bot instance."""
    session = None
    timeout_sec = max(30.0, float(config.request_timeout_seconds))
    if config.telegram_proxy or config.telegram_api_server:
        api = (
            TelegramAPIServer.from_base(config.telegram_api_server)
            if config.telegram_api_server
            else None
        )
        session = AiohttpSession(
            proxy=config.telegram_proxy,
            api=api,
            timeout=timeout_sec,
        )
    else:
        session = AiohttpSession(timeout=timeout_sec)

    return Bot(
        token=config.telegram_bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(
    config: Config,
    database: Database,
    movie_service: MovieService | None = None,
) -> Dispatcher:
    """Create dispatcher with middleware and dependency injection."""
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register middlewares
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(RateLimitMiddleware(config))
    dp.update.outer_middleware(DatabaseMiddleware(database))

    # Inject dependencies
    dp["config"] = config
    dp["database"] = database
    if movie_service:
        dp["movie_service"] = movie_service

    dp.include_router(downloader_router)
    dp.include_router(command_router)
    dp.include_router(downloader_callback_router)
    dp.include_router(callback_router)

    return dp


async def setup_bot_commands(bot: Bot) -> None:
    """Register bot commands shown in the Telegram menu."""
    commands = [
        BotCommand(command="start", description="🏠 Menu chính & Hướng dẫn"),
        BotCommand(command="help", description="📖 Hướng dẫn chi tiết"),
        BotCommand(command="tim", description="🔍 Tìm kiếm phim (/tim <tên>)"),
        BotCommand(command="phimmoi", description="🆕 Phim mới cập nhật"),
        BotCommand(command="chieurap", description="🔥 Phim chiếu rạp nổi bật"),
        BotCommand(command="phimbo", description="📺 Phim bộ nhiều tập"),
        BotCommand(command="phimle", description="🎬 Phim lẻ / điện ảnh"),
        BotCommand(command="hoathinh", description="🧸 Phim hoạt hình"),
        BotCommand(command="theloai", description="🎭 Chọn theo Thể loại"),
        BotCommand(command="quocgia", description="🌍 Chọn theo Quốc gia"),
        BotCommand(command="nam", description="📅 Chọn theo Năm phát hành"),
        BotCommand(command="yeuthich", description="❤️ Phim đã lưu Yêu thích"),
        BotCommand(command="mycookie", description="🍪 Xem trạng thái YouTube Cookie"),
        BotCommand(command="delcookie", description="🗑️ Xóa YouTube Cookie"),
    ]
    try:
        await bot.set_my_commands(commands, request_timeout=15.0)
        logger.info("Bot commands registered successfully.")
    except Exception as exc:
        logger.warning("Could not register bot commands with Telegram: %s", exc)


async def handle_health(request: web.Request) -> web.Response:
    """Respond 200 OK for UptimeRobot or cloud health checks."""
    return web.Response(text="KKPhim Bot is running OK!", content_type="text/plain")


async def start_health_server(port: int) -> web.AppRunner:
    """Start lightweight background HTTP server for Web Service keep-alive."""
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health check HTTP server listening on port %d", port)
    return runner


async def main() -> None:
    """Run the bot in Long Polling mode with optional health check web server."""
    config = Config.from_env()
    configure_logging(config.log_level)

    logger.info("Initializing bot in Long Polling mode (env=%s)...", config.environment)

    # Setup database
    database = Database(config)
    await database.create_tables()

    # Setup services
    http_session = aiohttp.ClientSession()
    kkphim_client = KKPhimClient(config, session=http_session)
    cache_service = CacheService.from_config(config)
    movie_service = MovieService(kkphim_client, cache_service, config)

    bot = create_bot(config)
    dp = create_dispatcher(config, database, movie_service)

    # Start optional background HTTP health check server if PORT environment variable is present
    import os
    port_str = os.environ.get("PORT")
    web_runner: web.AppRunner | None = None
    if port_str:
        try:
            web_runner = await start_health_server(int(port_str))
        except Exception as exc:
            logger.warning("Failed to start health check server on port %s: %s", port_str, exc)

    try:
        await setup_bot_commands(bot)
        # Clear webhook and any pending updates to prevent conflicts
        try:
            await bot.delete_webhook(drop_pending_updates=True, request_timeout=15.0)
        except Exception as exc:
            logger.warning("Could not delete webhook: %s", exc)

        logger.info("Bot started in Long Polling mode. Waiting for updates...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    except Exception as exc:
        logger.error("Polling error: %s", exc, exc_info=True)
    finally:
        logger.info("Shutting down bot services...")
        if web_runner:
            await web_runner.cleanup()
        await cache_service.close()
        await kkphim_client.close()
        await http_session.close()
        await database.close()
        await bot.session.close()
        logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())

