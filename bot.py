import os
import json
import html
import logging
from datetime import datetime

from telegram import (
    Update,
    ChatJoinRequest,
    ChatMember
)

from telegram.constants import ParseMode

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

TOKEN = "8219656117:AAGhTeVBUkqlEDw6IwMr0F1QoGqUwupESI4"

DESTINATION_CHAT_ID = -1003889779689

ADMINS = [7583614563]

AUTO_DELETE = False

CHATS_FILE = "chats.json"

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# =========================================================
# STORAGE
# =========================================================

added_chats = {}

stats = {
    "today": 0,
    "total": 0,
    "date": datetime.now().date()
}

# =========================================================
# HELPERS
# =========================================================

def reset_daily():
    today = datetime.now().date()

    if stats["date"] != today:
        stats["today"] = 0
        stats["date"] = today


def load_chats():
    global added_chats

    try:
        if os.path.exists(CHATS_FILE):
            with open(CHATS_FILE, "r") as f:
                added_chats = json.load(f)

    except Exception as e:
        logger.error(f"Load chats error: {e}")
        added_chats = {}


def save_chats():
    try:
        with open(CHATS_FILE, "w") as f:
            json.dump(added_chats, f)

    except Exception as e:
        logger.error(f"Save chats error: {e}")


# =========================================================
# CLEAN CAPTION
# =========================================================

def clean_caption(text):

    if not text:
        return ""

    remove_words = [
        "http://",
        "https://",
        "t.me/",
        "@",
        "join",
        "subscribe",
        "follow",
        "like",
        "link",
        "channel",
        "group"
    ]

    lines = text.splitlines()

    cleaned = []

    for line in lines:

        low = line.lower()

        if any(word in low for word in remove_words):
            continue

        cleaned.append(line.strip())

    result = "\n".join(cleaned)

    result = result.strip()

    return result[:900]


# =========================================================
# TEMPLATE
# =========================================================

def build_caption(original_caption, source_name):

    caption = f"""
✨ <b>Premium Content</b>

{original_caption}

━━━━━━━━━━━━━━━
🎬 <b>Shared via Lufii Network</b>
📂 <b>Source:</b> {source_name}
━━━━━━━━━━━━━━━
""".strip()

    return caption[:1024]


# =========================================================
# ADMIN COMMANDS
# =========================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id not in ADMINS:
        return

    reset_daily()

    await update.message.reply_text(
        f"""
📊 <b>Bot Statistics</b>

📅 Today Forwarded: {stats['today']}
🚀 Total Forwarded: {stats['total']}
        """,
        parse_mode=ParseMode.HTML
    )


# =========================================================
# JOIN REQUEST
# =========================================================

async def approve_join(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    request: ChatJoinRequest = update.chat_join_request

    try:
        await context.bot.approve_chat_join_request(
            chat_id=request.chat.id,
            user_id=request.from_user.id
        )

    except Exception as e:
        logger.error(f"Approve error: {e}")


# =========================================================
# TRACK GROUPS
# =========================================================

async def track_chats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    result = update.my_chat_member

    if not result:
        return

    chat = result.chat
    status = result.new_chat_member.status

    try:

        if status in [
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR
        ]:

            added_chats[str(chat.id)] = chat.title

            save_chats()

            logger.info(f"Joined: {chat.title}")

        elif status in [
            ChatMember.LEFT,
            ChatMember.BANNED
        ]:

            if str(chat.id) in added_chats:
                del added_chats[str(chat.id)]

                save_chats()

                logger.info(f"Removed: {chat.title}")

    except Exception as e:
        logger.error(f"Track error: {e}")

# =========================================================
# FORWARD ENGINE
# =========================================================

async def auto_forward(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    reset_daily()

    message = update.message

    if not message:
        return

    try:

        # =================================================
        # MEDIA ONLY
        # =================================================

        if not (
            message.video
            or message.document
            or message.animation
            or message.photo
            or message.audio
        ):
            return

        # =================================================
        # CLEAN CAPTION
        # =================================================

        original_caption = clean_caption(
            message.caption or ""
        )

        source_name = html.escape(
            message.chat.title or "Private"
        )

        # =================================================
        # NEW VIRAL CAPTION
        # =================================================

        new_caption = build_caption(
            original_caption,
            source_name
        )

        # =================================================
        # COPY MESSAGE
        # =================================================

        await context.bot.copy_message(
            chat_id=DESTINATION_CHAT_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
            caption=new_caption,
            parse_mode=ParseMode.HTML
        )

        stats["today"] += 1
        stats["total"] += 1

        logger.info(
            f"✅ Forwarded "
            f"{message.chat.id}:{message.message_id}"
        )

        # =================================================
        # AUTO DELETE
        # =================================================

        if AUTO_DELETE:
            try:
                await message.delete()
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Forward error: {e}")

# =========================================================
# MAIN
# =========================================================

def main():

    load_chats()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # =====================================================
    # COMMANDS
    # =====================================================

    app.add_handler(
        CommandHandler(
            "stats",
            stats_command
        )
    )

    # =====================================================
    # JOIN
    # =====================================================

    app.add_handler(
        ChatJoinRequestHandler(
            approve_join
        )
    )

    # =====================================================
    # TRACK
    # =====================================================

    app.add_handler(
        ChatMemberHandler(
            track_chats,
            ChatMemberHandler.MY_CHAT_MEMBER
        )
    )

    # =====================================================
    # MEDIA HANDLER
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.VIDEO
            | filters.ANIMATION
            | filters.PHOTO
            | filters.AUDIO
            | filters.Document.ALL,
            auto_forward
        )
    )

    logger.info("🚀 Premium Telegram Bot Started")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
        allowed_updates=Update.ALL_TYPES
    )

# =========================================================
# ENTRY
# =========================================================

if __name__ == "__main__":
    main()
