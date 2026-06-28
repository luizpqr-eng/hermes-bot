import asyncio
import logging
import os
from html import escape

from aiohttp import web
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.environ.get("MODEL", "meta-llama/llama-3.3-70b-instruct:free")
ALLOWED_USERS = os.environ.get("ALLOWED_USERS", "").split(",") if os.environ.get("ALLOWED_USERS") else None
PORT = int(os.environ.get("PORT", 7860))

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)


async def start(update: Update, _context):
    await update.message.reply_text(
        "🤖 *Hermes Bot*\n\nEnvie uma mensagem e eu respondo usando IA via OpenRouter.\n\nComandos:\n/start - Esta mensagem\n/help - Ajuda\n/status - Status do bot\n/model - Modelo atual",
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, _context):
    await update.message.reply_text(
        "Envie qualquer mensagem que eu respondo com IA.\n\nModelo atual: " + MODEL
    )


async def status(update: Update, _context):
    await update.message.reply_text(f"Bot online\nModelo: {MODEL}\nProvedor: OpenRouter")


async def model_cmd(update: Update, _context):
    await update.message.reply_text(f"Modelo atual: {MODEL}")


async def handle_message(update: Update, _context):
    if ALLOWED_USERS and str(update.effective_user.id) not in ALLOWED_USERS:
        await update.message.reply_text("Acesso negado.")
        return

    user_text = update.message.text
    if not user_text:
        return

    logger.info(f"Msg from {update.effective_user.id}: {user_text[:50]}")

    await update.message.chat.send_action("typing")

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Você é um assistente útil e conciso. Responda em português.",
                },
                {"role": "user", "content": user_text},
            ],
            timeout=60,
        )

        reply = response.choices[0].message.content or "Sem resposta."
        await update.message.reply_text(reply)

    except Exception as e:
        logger.exception("Erro ao chamar OpenRouter")
        await update.message.reply_text(f"Erro: {escape(str(e))}")


async def error_handler(update: Update, context):
    logger.exception("Unhandled error: %s", context.error)


async def health_check(_request):
    return web.Response(text="ok")


async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("model", model_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    web_app = web.Application()
    web_app.router.add_get("/", health_check)
    web_app.router.add_get("/health", health_check)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"Health server on port {PORT}")

    logger.info("Bot started, polling...")
    await app.start()
    await app.updater.start_polling()

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
