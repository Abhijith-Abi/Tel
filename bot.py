import os
import json
import html
import asyncio
import logging
from datetime import datetime

import redis

from telegram import (
    Update,
    ChatJoinRequest,
    ChatMember
)

from telegram.constants import ParseMode

from telegram.error import RetryAfter

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

DESTINATION_CHAT_ID = -1001234567890

ADMINS = [123456789]

AUTO_DELETE = False

CHATS_FILE = "chats.json"

REDIS_HOST = "localhost"

REDIS_PORT = 6379

# =========================================================
# REDIS
# =========================================================

REDIS = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)

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
# CAPTION
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
# SAFE COPY
# =========================================================

async def safe_copy(
    context,
    chat_id,
    from_chat_id,
    message_id,
    caption=None
):

    retries = 5

    for attempt in range(retries):

        try:

            await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                caption=caption,
                parse_mode=ParseMode.HTML
            )

            return True

        except RetryAfter as e:

            logger.warning(
                f"FloodWait: sleeping {e.retry_after}"
            )

            await asyncio.sleep(e.retry_after)

        except Exception as e:

            logger.error(
                f"Copy failed attempt {attempt+1}: {e}"
            )

            await asyncio.sleep(2)

    return False

# =========================================================
# MEDIA GROUP PROCESSOR
# =========================================================

async def process_media_group(
    group_id,
    context
):

    await asyncio.sleep(3)

    key = f"media_group:{group_id}"

    raw_messages = REDIS.lrange(key, 0, -1)

    if not raw_messages:
        return

    messages = [
        json.loads(x)
        for x in raw_messages
    ]

    messages.sort(
        key=lambda x: x["message_id"]
    )

    first = messages[0]

    original_caption = clean_caption(
        first.get("caption", "")
    )

    source_name = html.escape(
        first.get("chat_title", "Private")
    )

    new_caption = build_caption(
        original_caption,
        source_name
    )

    success_count = 0

    for idx, msg in enumerate(messages):

        caption = new_caption if idx == 0 else None

        ok = await safe_copy(
            context=context,
            chat_id=DESTINATION_CHAT_ID,
            from_chat_id=msg["chat_id"],
            message_id=msg["message_id"],
            caption=caption
        )

        if ok:
            success_count += 1

        await asyncio.sleep(0.4)

    logger.info(
        f"✅ Media Group Done "
        f"{group_id} "
        f"{success_count}/{len(messages)}"
    )

    REDIS.delete(key)

# =========================================================
# ADMIN COMMAND
# =========================================================

async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id not in ADMINS:
        return

    reset_daily()

    await update.message.reply_text(
        f"""
📊 <b>Bot Statistics</b>

📅 Today: {stats['today']}
🚀 Total: {stats['total']}
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
# TRACK CHATS
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
# MAIN FORWARD ENGINE
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
        # MEDIA FILTER
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
        # MEDIA GROUP
        # =================================================

        if message.media_group_id:

            group_id = message.media_group_id

            key = f"media_group:{group_id}"

            data = {
                "chat_id": message.chat_id,
                "message_id": message.message_id,
                "caption": message.caption,
                "chat_title": message.chat.title
            }

            REDIS.rpush(
                key,
                json.dumps(data)
            )

            REDIS.expire(key, 120)

            if REDIS.llen(key) == 1:

                asyncio.create_task(
                    process_media_group(
                        group_id,
                        context
                    )
                )

            return

        # =================================================
        # SINGLE MESSAGE
        # =================================================

        original_caption = clean_caption(
            message.caption or ""
        )

        source_name = html.escape(
            message.chat.title or "Private"
        )

        new_caption = build_caption(
            original_caption,
            source_name
        )

        ok = await safe_copy(
            context=context,
            chat_id=DESTINATION_CHAT_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
            caption=new_caption
        )

        if ok:

            stats["today"] += 1
            stats["total"] += 1

            logger.info(
                f"✅ Forwarded "
                f"{message.chat.id}:{message.message_id}"
            )

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
        .concurrent_updates(20)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "stats",
            stats_command
        )
    )

    app.add_handler(
        ChatJoinRequestHandler(
            approve_join
        )
    )

    app.add_handler(
        ChatMemberHandler(
            track_chats,
            ChatMemberHandler.MY_CHAT_MEMBER
        )
    )

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

    logger.info("🚀 Telegram Bot Started")

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
