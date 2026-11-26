import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
GITHUB_API = "https://api.github.com"
user_states = {}


def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard
    response = requests.post(f"{API}/sendMessage", json=data, timeout=15)
    response.raise_for_status()


def dispatch_story(mode, prompt=""):
    """Trigger the Reddit-story workflow in GitHub Actions."""
    url = (
        f"{GITHUB_API}/repos/{GITHUB_REPOSITORY}"
        f"/actions/workflows/main.yml/dispatches"
    )
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "ref": GITHUB_BRANCH,
        "inputs": {
            "mode": mode,
            "prompt": prompt[:4000],
            "count": "1",
            "visual_type": "video",
        },
    }
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    response.raise_for_status()


def command_name(text):
    """Return /command without an optional @botname suffix."""
    if not text.startswith("/"):
        return ""
    return text.split()[0].split("@")[0].lower()


def start_new_story(chat_id, idea=""):
    if idea:
        user_states.pop(chat_id, None)
        send_message(chat_id, "📖 Starting your new Reddit story...")
        try:
            dispatch_story("story", idea)
            send_message(chat_id, "✅ JARVIS has started your story!")
        except Exception as exc:
            send_message(chat_id, f"❌ I couldn't start the story: {exc}")
        return

    user_states[chat_id] = "new_story"
    send_message(
        chat_id,
        "📖 What should the Reddit story be about?\n\n"
        "Send a topic, situation, or genre (or type 'surprise me'). "
        "JARVIS will create a full-length story.",
    )


def request_continuation(chat_id, details=""):
    if details:
        user_states.pop(chat_id, None)
        send_message(chat_id, "➡️ Sending your continuation request to JARVIS...")
        try:
            dispatch_story("continue", details)
            send_message(
                chat_id,
                "✅ JARVIS has started the next part.\n\n"
                "Include the previous part or a detailed recap in your message "
                "so the continuation can stay consistent.",
            )
        except Exception as exc:
            send_message(chat_id, f"❌ I couldn't start the next part: {exc}")
        return

    user_states[chat_id] = "continue_story"
    send_message(
        chat_id,
        "➡️ Which story should I continue?\n\n"
        "Send the story title, the previous part (or a detailed recap), "
        "and what you'd like to happen next.\n\n"
        "JARVIS needs that context to continue the same story accurately.",
    )


def handle_message(message):
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "").strip()

    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        return

    cmd = command_name(text)

    if cmd in ("/start", "/help", "/create"):
        user_states.pop(chat_id, None)
        keyboard = {
            "keyboard": [
                [{"text": "📖 New Reddit Story"}, {"text": "➡️ Continue a Story"}],
                [{"text": "❌ Cancel"}],
            ],
            "resize_keyboard": True,
        }
        send_message(
            chat_id,
            "JARVIS Reddit Stories is ready.\n\n"
            "📖 /story — create a new full-length story\n"
            "➡️ /part — continue an existing story\n"
            "❌ /cancel — cancel the current request",
            keyboard,
        )
        return

    if cmd == "/story":
        argument = text.split(maxsplit=1)
        start_new_story(chat_id, argument[1].strip() if len(argument) > 1 else "")
        return

    if cmd == "/part":
        argument = text.split(maxsplit=1)
        request_continuation(chat_id, argument[1].strip() if len(argument) > 1 else "")
        return

    if cmd == "/cancel" or text == "❌ Cancel":
        user_states.pop(chat_id, None)
        send_message(chat_id, "❌ Request cancelled.")
        return

    if text == "📖 New Reddit Story":
        start_new_story(chat_id)
        return

    if text == "➡️ Continue a Story":
        request_continuation(chat_id)
        return

    state = user_states.get(chat_id)
    if state == "new_story":
        if not text:
            send_message(chat_id, "Please send a story idea or type 'surprise me'.")
            return
        start_new_story(chat_id, text)
        return

    if state == "continue_story":
        if not text:
            send_message(chat_id, "Please send the previous part or a recap and what should happen next.")
            return
        request_continuation(chat_id, text)
        return

    if text:
        send_message(chat_id, "Use /story to create a new Reddit story or /part to continue one. Type /help for commands.")


@app.get("/")
def home():
    return "JARVIS Reddit Stories Telegram webhook is online!"


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
        except Exception:
            app.logger.exception("Telegram update handling failed")

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
