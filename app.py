import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]
ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
user_states = {}

def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard
    requests.post(f"{API}/sendMessage", json=data, timeout=15)

def dispatch_video(mode, prompt=""):
    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPOSITORY}/actions/workflows/main.yml/dispatches"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    data = {
        "ref": "main",
        "inputs": {
            "mode": mode,
            "prompt": prompt,
            "count": "1"
        }
    }

    response = requests.post(
        url, headers=headers, json=data, timeout=20
    )
    response.raise_for_status()

def handle_message(message):
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "").strip()

    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        return

    if text == "/start" or text == "/create":
        user_states[chat_id] = "choice"

        keyboard = {
            "keyboard": [
                [{"text": "🔥 Trending"}, {"text": "✍️ Custom prompt"}],
                [{"text": "❌ Cancel"}]
            ],
            "resize_keyboard": True
        }

        send_message(
            chat_id,
            "JARVIS Studio is ready. What would you like to create?",
            keyboard
        )
        return

    state = user_states.get(chat_id)

    if text == "❌ Cancel":
        user_states.pop(chat_id, None)
        send_message(chat_id, "Creation cancelled.")
        return

    if state == "choice":
        if text == "🔥 Trending":
            user_states.pop(chat_id, None)
            send_message(chat_id, "🔥 Starting your trending video...")
            try:
                dispatch_video("trending")
                send_message(chat_id, "✅ JARVIS has started creating your video!")
            except Exception as e:
                send_message(chat_id, f"❌ Could not start video: {e}")

        elif text == "✍️ Custom prompt":
            user_states[chat_id] = "custom"
            send_message(chat_id, "What video would you like JARVIS to create?")

        else:
            send_message(chat_id, "Please choose Trending or Custom prompt.")
        return

    if state == "custom":
        if not text:
            send_message(chat_id, "Please send a video idea.")
            return

        user_states.pop(chat_id, None)
        send_message(chat_id, "✍️ Your idea has been received. Starting JARVIS...")

        try:
            dispatch_video("custom", text[:500])
            send_message(chat_id, "✅ JARVIS has started creating your video!")
        except Exception as e:
            send_message(chat_id, f"❌ Could not start video: {e}")

@app.get("/")
def home():
    return "JARVIS Telegram Webhook is online!"

@app.post("/webhook")
def webhook():
    if WEBHOOK_SECRET:
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if supplied != WEBHOOK_SECRET:
            return "Unauthorized", 403

    update = request.get_json(silent=True) or {}
    message = update.get("message")

    if message:
        try:
            handle_message(message)
        except Exception as e:
            print("Update error:", e)

    return jsonify({"ok": True})
