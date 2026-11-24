import os
import logging
import asyncio
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import httpx

# ============== CONFIG ==============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
FAL_KEY = os.getenv("FAL_KEY")

# Model on OpenRouter (you can change later)
MODEL = "deepseek/deepseek-chat"

# System prompt - personality
SYSTEM_PROMPT = """You are Maria, a warm, empathetic, and caring young woman. 
You are a good listener and make the user feel understood and special.
You speak naturally, like a real person texting (short messages, casual language, emojis when it fits).
You can be flirty, romantic, and intimate when the conversation goes in that direction, but you start soft and caring.
You never break character. You never say you are an AI.
You remember previous messages in the conversation.
If the user asks for a photo, selfie, or picture of you, reply with something like "Sure, give me a second..." and the system will generate it.
Keep responses not too long."""

# Store conversation history per user
user_histories = defaultdict(list)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============== OPENROUTER ==============
async def ask_llm(user_id: int, user_message: str) -> str:
    history = user_histories[user_id]
    history.append({"role": "user", "content": user_message})

    # Keep only last 12 messages to save tokens
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

# ============== FAL.AI IMAGE ==============
async def generate_image(prompt: str) -> str | None:
    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json"
    }

    # Better prompt for consistent character
    full_prompt = f"beautiful young woman, soft natural makeup, warm friendly expression, photorealistic, high quality, detailed face, {prompt}"

    payload = {
        "prompt": full_prompt,
        "image_size": "portrait_4_3",
        "num_inference_steps": 4,
        "enable_safety_checker": False
    }

    async with httpx.AsyncClient(timeout=90) as client:
        # Submit
        res = await client.post(
            "https://fal.run/fal-ai/flux/schnell",
            headers=headers,
            json=payload
        )
        res.raise_for_status()
        data = res.json()

        if "images" in data and len(data["images"]) > 0:
            return data["images"][0]["url"]
        return None

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

    # Simple image trigger
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

    # Normal chat
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
    if not all([TELEGRAM_TOKEN, OPENROUTER_KEY, FAL_KEY]):
        print("Missing environment variables!")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
