from telegram import Update, ChatJoinRequest, ChatMember
import json
import os
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)
from datetime import datetime
import asyncio
import html

# ================= CONFIG =================
TOKEN = "8219656117:AAGhTeVBUkqlEDw6IwMr0F1QoGqUwupESI4"
DESTINATION_CHAT_ID = -1003889779689

KEYWORDS = []          # Example: ["movie", "link"]
ALLOWED_USERS = []     # Example: [123456789]
DELAY_SECONDS = 5
AUTO_DELETE = False
WATERMARK_TEXT = ""
WATERMARK_TEXT = ""
# CUSTOM_CAPTION removed in favor of dynamic logic
DESTINATION_INFO = {"title": None, "link": None}

ADMINS = [7583614563]
CHATS_FILE = "chats.json"
added_chats = {}

# ================= STATS =================
stats = {
    "today": 0,
    "total": 0,
    "date": datetime.now().date()
}

# ================= HELPERS =================
def reset_daily():
    today = datetime.now().date()
    if stats["date"] != today:
        stats["today"] = 0
        stats["date"] = today


async def get_destination_info(bot):
    global DESTINATION_INFO
    if DESTINATION_INFO["title"]:
        return DESTINATION_INFO

    try:
        chat = await bot.get_chat(DESTINATION_CHAT_ID)
        title = chat.title
        link = None
        
        if chat.username:
            link = f"https://t.me/{chat.username}"
        elif chat.invite_link:
            link = chat.invite_link
        
        # If no link found, try to export one (requires admin rights)
        if not link:
            try:
                link = await bot.export_chat_invite_link(DESTINATION_CHAT_ID)
            except Exception:
                link = None

        DESTINATION_INFO = {"title": title, "link": link}
    except Exception as e:
        print(f"Error fetching destination info: {e}")
        DESTINATION_INFO = {"title": "Channel", "link": None}
    
    return DESTINATION_INFO


def load_chats():
    global added_chats
    if os.path.exists(CHATS_FILE):
        try:
            with open(CHATS_FILE, "r") as f:
                added_chats = json.load(f)
        except Exception as e:
            print("Error loading chats:", e)
            added_chats = {}

def save_chats():
    try:
        with open(CHATS_FILE, "w") as f:
            json.dump(added_chats, f)
    except Exception as e:
        print("Error saving chats:", e)


# ================= ADMIN COMMANDS =================
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    reset_daily()
    await update.message.reply_text(
        f"📊 Statistics\n\n"
        f"📅 Today: {stats['today']}\n"
        f"📦 Total: {stats['total']}"
    )


async def repost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    if update.message.reply_to_message:
        msg = update.message.reply_to_message
        await context.bot.copy_message(
            chat_id=DESTINATION_CHAT_ID,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id
        )


async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    
    if not added_chats:
        await update.message.reply_text("No groups joined yet.")
        return

    message = "📋 **Joined Groups:**\n\n"
    for chat_id, title in added_chats.items():
        message += f"• {title} (`{chat_id}`)\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def leave_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    try:
        chat_id = int(context.args[0])
        await context.bot.leave_chat(chat_id)
        if str(chat_id) in added_chats:
            del added_chats[str(chat_id)]
            save_chats()
        await update.message.reply_text(f"✅ Left group {chat_id}")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Usage: /leave <chat_id>")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")



# ================= AUTO APPROVE JOIN =================
async def approve_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request: ChatJoinRequest = update.chat_join_request
    await context.bot.approve_chat_join_request(
        chat_id=request.chat.id,
        user_id=request.from_user.id
    )


async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    
    chat = result.chat
    new_status = result.new_chat_member.status
    
    # Check if bot is member or admin
    if new_status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
        added_chats[str(chat.id)] = chat.title
        save_chats()
    
    # Check if bot was kicked or left
    elif new_status in [ChatMember.BANNED, ChatMember.LEFT]:
        if str(chat.id) in added_chats:
            del added_chats[str(chat.id)]
            save_chats()



# ================= FORWARD LOGIC =================
async def auto_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_daily()

    message = update.message
    if not message:
        return

    # USER FILTER
    if ALLOWED_USERS and message.from_user.id not in ALLOWED_USERS:
        return

    # KEYWORD FILTER
    if KEYWORDS:
        text_content = message.text or message.caption or ""
        if not any(word.lower() in text_content.lower() for word in KEYWORDS):
            return

    # DELAY
    # await asyncio.sleep(DELAY_SECONDS)

    try:
        # MEDIA MESSAGES
        if message.photo or message.video or message.document or message.audio:
            # Custom Caption Logic
            original_caption = html.escape(message.caption or "")
            source_name = html.escape(message.chat.title or "Private")
            
            caption_parts = [original_caption]
            
            # Add Source
            caption_parts.append(f"<b>📂 Source:</b> {source_name}")
            
            # --- Dynamic Destination Caption ---
            dest_info = await get_destination_info(context.bot)
            dest_title = html.escape(dest_info.get("title") or "Channel")
            dest_link = dest_info.get("link")

            if dest_link:
                custom_caption = f"📢 Join <a href='{dest_link}'>{dest_title}</a>"
            else:
                custom_caption = f"📢 Join <b>{dest_title}</b>"
            
            caption_parts.append(custom_caption)
            # -----------------------------------
            
            # Join with newlines, filtering out empty strings
            new_caption = "\n\n".join(filter(None, caption_parts))

            await context.bot.copy_message(
                chat_id=DESTINATION_CHAT_ID,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
                caption=new_caption,
                parse_mode='HTML' # Ensure HTML parsing is used if tags are present in CUSTOM_CAPTION
            )

        stats["today"] += 1
        stats["total"] += 1

        # AUTO DELETE ORIGINAL
        if AUTO_DELETE:
            await message.delete()

    except Exception as e:
        print("Forward Error:", e)


# ================= MAIN =================
def main():

    load_chats()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("repost", repost))
    app.add_handler(CommandHandler("list", list_groups))
    app.add_handler(CommandHandler("leave", leave_group))
    app.add_handler(ChatJoinRequestHandler(approve_join))
    app.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))

    # Better filter (faster + stable)
    app.add_handler(
        MessageHandler(
            filters.PHOTO
            | filters.VIDEO
            | filters.Document.ALL
            | filters.AUDIO,
            auto_forward
        )
    )

    print("🔥 Lufii Pro Bot Running...")

    # AUTO RESTART LOOP (best for free hosting)
    while True:
        try:
            app.run_polling(drop_pending_updates=True)
        except Exception as e:
            print("Bot crashed, restarting...", e)


if __name__ == "__main__":
    main()
