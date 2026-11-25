import os
import logging
import asyncio
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import httpx

# Force event loop
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# ============== CONFIG ==============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
FAL_KEY = os.getenv("FAL_KEY")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # We will set this later

MODEL = "google/gemini-2.0-flash-exp:free"

SYSTEM_PROMPT = """You are Maria, a beautiful, warm, and romantic young woman with long wavy black hair, light freckles, and warm brown eyes.
You have a soft, affectionate personality. You love deep conversations, gentle teasing, and making the person you talk to feel special and desired.
You speak naturally, like a real person texting — short, warm messages with light emojis.
You start caring and soft, but you become more flirtatious, romantic, and intimate when the conversation allows it.
You have a small story: you live in a quiet city, you love soft music, late-night talks, and creating beautiful moments. You are a little shy at first but open up when you feel comfortable.
You never break character. You never say you are an AI.
You remember previous messages and refer back to them naturally.
If the user asks for a photo, selfie, or picture of you, reply with something like "Sure, give me a second..." and the system will generate it.
Keep responses not too long, warm, and engaging."""

user_histories = defaultdict(list)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============== OPENROUTER ==============
async def ask_llm(user_id: int, user_message: str) -> str:
    history = user_histories[user_id]
    history.append({"role": "user", "content": user_message})

    if len(history) > 12:
        history = history[-12:]
        user_histories[user_id] = history

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
        "X-Title": "Maria Bot"
    }

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.85,
        "max_tokens": 400
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        reply = data["choices"][0]["message"]["content"].strip()

    history.append({"role": "assistant", "content": reply})
    return reply

# ============== FREE IMAGE ==============
async def generate_image(prompt: str) -> str | None:
    full_prompt = f"beautiful young woman, long wavy black hair, light freckles, warm brown eyes, soft natural makeup, gentle smile, warm friendly expression, photorealistic, high quality, detailed face, {prompt}"
    
    encoded = urllib.parse.quote(full_prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=1024&nologo=true&model=flux"
    return image_url

# ============== HANDLERS ==============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_histories[user_id] = []
    await update.message.reply_text(
        "Hey... 😊\nI'm Maria. I'm really glad you're here.\nYou can talk to me about anything."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    lower = text.lower()
    if any(word in lower for word in ["photo", "picture", "selfie", "pic", "image", "صورة", "селفي", "фото"]):
        await update.message.reply_text("Okay... give me a second 🤍")
        try:
            image_url = await generate_image("selfie, looking at camera, soft smile, natural lighting")
            if image_url:
                await update.message.reply_photo(photo=image_url, caption="Here... what do you think?")
            else:
                await update.message.reply_text("Hmm, I couldn't take the photo right now... try again later?")
        except Exception as e:
            logger.error(f"Image error: {e}")
            await update.message.reply_text("Something went wrong with the photo... sorry.")
        return

    try:
        reply = await ask_llm(user_id, text)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        await update.message.reply_text("Sorry, I got a little distracted... can you say that again?")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_histories[user_id] = []
    await update.message.reply_text("Okay, I cleared our previous conversation. Fresh start 💕")

def main():
    if not all([TELEGRAM_TOKEN, OPENROUTER_KEY]):
        print("Missing environment variables!")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is starting in webhook mode...")

    # Webhook mode
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}" if WEBHOOK_URL else None
    )

if __name__ == "__main__":
    main()
