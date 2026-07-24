import sys
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import User, Card, Order, Base
from config.settings import BOT_TOKEN, USDT_ADDRESS, ADMIN_IDS, DATABASE_URL
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Database
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True, pool_recycle=3600)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def get_or_create_user(telegram_id: int):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=str(telegram_id)).first()
        if not user:
            user = User(
                telegram_id=str(telegram_id),
                username="",
                usdt_address=USDT_ADDRESS,
                is_admin=str(telegram_id) in ADMIN_IDS
            )
            session.add(user)
            session.commit()
        return user
    finally:
        session.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ /start received from {update.effective_user.username}")
    await update.message.reply_text(
        "🎴 **Welcome to CardStore!**\n\n"
        "💰 USDT Payments | 🌍 Global Cards\n\n"
        "📋 *Commands:*\n"
        "/balance - Check your balance\n"
        "/topup - Get USDT deposit address\n"
        "/catalog - Browse cards\n"
        "/history - View purchases\n"
        "/help - Show all commands",
        parse_mode="Markdown"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ /balance received from {update.effective_user.username}")
    user = await get_or_create_user(update.effective_user.id)
    await update.message.reply_text(
        f"💰 **Your Balance:** `{user.balance} USDT`",
        parse_mode="Markdown"
    )

async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ /topup received from {update.effective_user.username}")
    user = await get_or_create_user(update.effective_user.id)
    keyboard = [[InlineKeyboardButton(text="📋 Copy Address", callback_data="copy_usdt")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💰 **USDT Deposit Address**\n\n"
        f"`{user.usdt_address}`\n\n"
        f"📡 Network: **TRC20 (Tron)**\n"
        f"🕐 Confirmation: **1-5 minutes**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def copy_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Address copied to clipboard!", show_alert=True)

async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ /catalog received from {update.effective_user.username}")
    keyboard = [
        [InlineKeyboardButton(text="🇺🇸 USA", callback_data="country_US")],
        [InlineKeyboardButton(text="🇨🇦 Canada", callback_data="country_CA")],
        [InlineKeyboardButton(text="🇬🇧 UK", callback_data="country_UK")],
        [InlineKeyboardButton(text="🌍 All", callback_data="country_ALL")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎴 **Select Country:**", reply_markup=reply_markup)

async def country_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    country_code = query.data.split("_")[1]
    
    session = SessionLocal()
    try:
        if country_code == "ALL":
            cards = session.query(Card).filter(Card.is_sold == False).limit(5).all()
        else:
            cards = session.query(Card).filter(Card.country == country_code, Card.is_sold == False).limit(5).all()
        
        if not cards:
            await query.answer(f"📭 No {country_code} cards available.", show_alert=True)
            return
        
        card_text = f"🎴 **{country_code} Cards Available**\n\n"
        for card in cards:
            card_text += (
                f"🆔 ID: `{card.id}`\n"
                f"🏦 BIN: `{card.bin}`\n"
                f"💳 ****{card.number[-4:]}\n"
                f"🏷️ Price: ${card.price} USDT\n\n"
            )
        
        await query.edit_message_text(card_text, parse_mode="Markdown")
    finally:
        session.close()

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ /history received from {update.effective_user.username}")
    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        orders = session.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(5).all()
        if not orders:
            await update.message.reply_text("📭 No purchase history yet.")
            return
        
        history_text = "📋 **Purchase History**\n\n"
        for order in orders:
            history_text += (
                f"🆔 Order #{order.id}\n"
                f"💰 Amount: ${order.amount} USDT\n"
                f"📊 Status: `{order.status}`\n"
                f"📅 Date: {order.created_at.strftime('%Y-%m-%d')}\n\n"
            )
        
        await update.message.reply_text(history_text, parse_mode="Markdown")
    finally:
        session.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ /help received from {update.effective_user.username}")
    await update.message.reply_text(
        "📋 **Available Commands:**\n\n"
        "/start - Welcome message\n"
        "/balance - Check USDT balance\n"
        "/topup - Get deposit address\n"
        "/catalog - Browse cards by country\n"
        "/history - View purchase history\n"
        "/help - Show this message\n\n"
        "*Admin Commands:*\n"
        "/stats - View store statistics\n"
        "/countries - View cards by country\n"
        "/users - View all users\n"
        "/add_card - Add single card\n"
        "/upload - Bulk upload cards",
        parse_mode="Markdown"
    )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View store statistics"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    
    session = SessionLocal()
    try:
        total_cards = session.query(Card).count()
        cards_sold = session.query(Card).filter(Card.is_sold == True).count()
        total_users = session.query(User).count()
        total_orders = session.query(Order).count()
        
        await update.message.reply_text(
            f"📊 **Store Statistics**\n\n"
            f"👥 Total Users: {total_users}\n"
            f"🎴 Total Cards: {total_cards}\n"
            f"✅ Cards Sold: {cards_sold}\n"
            f"📉 Available: {total_cards - cards_sold}\n"
            f"📦 Total Orders: {total_orders}",
            parse_mode="Markdown"
        )
    finally:
        session.close()

async def admin_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View cards by country"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    
    session = SessionLocal()
    try:
        country_stats = session.query(Card.country).group_by(Card.country).all()
        
        stats_text = "🌍 **Cards by Country**\n\n"
        for country, count in country_stats:
            stats_text += f"🏳️ {country}: {count} cards\n"
        
        stats_text += f"\n📊 **Total:** {session.query(Card).count()} cards"
        
        await update.message.reply_text(stats_text, parse_mode="Markdown")
    finally:
        session.close()

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all users (admin only)"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    
    session = SessionLocal()
    try:
        users = session.query(User).order_by(User.created_at.desc()).limit(20).all()
        
        if not users:
            await update.message.reply_text("📭 No users found.")
            return
        
        users_text = "👥 **All Users** (Latest 20)\n\n"
        for u in users:
            users_text += (
                f"🆔 `{u.telegram_id}`\n"
                f"👤 @{u.username or 'N/A'}\n"
                f"💰 ${u.balance} USDT\n"
                f"📅 Joined: {u.created_at.strftime('%Y-%m-%d')}\n\n"
            )
        
        await update.message.reply_text(users_text, parse_mode="Markdown")
    finally:
        session.close()

async def admin_add_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add single card via command"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    
    await update.message.reply_text(
        "📝 **Add Card Format:**\n"
        "Usage: /add_card BIN|NUMBER|EXPIRY|CVV|COUNTRY|BILLING|PRICE\n\n"
        "Example: /add_card 414720|4147201234567890|12/26|123|US|yes|25"
    )

async def admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start file upload process"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    
    await update.message.reply_text(
        "📦 **Bulk Upload via Telegram**\n\n"
        "📁 Send a card file (.txt, .csv, .dat, .log)\n"
        "✅ Any format supported (auto-detected)\n"
        "✅ Cards will be sorted automatically\n\n"
        "⏳ Waiting for file...",
        parse_mode="Markdown"
    )
    context.user_data['uploading'] = True

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process uploaded card file"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        return
    
    if not context.user_data.get('uploading'):
        return
    
    document = update.message.document
    filename = document.file_name
    
    if filename.endswith(('.txt', '.csv', '.dat', '.log', '.tsv')):
        await update.message.reply_text("⏳ Downloading file...")
        
        try:
            # Download file
            file_path = f"uploads\\{filename}"
            file = await context.bot.get_file(document.file_id)
            await file.download_to_drive(file_path)
            
            # Process file (manual parsing for now)
            session = SessionLocal()
            try:
                cards = []
                success_count = 0
                
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        # Auto-detect delimiter
                        delimiters = [',', '|', '\t', ' ']
                        delimiter = max(delimiters, key=lambda d: line.count(d))
                        
                        parts = [p.strip() for p in line.split(delimiter)]
                        if len(parts) >= 7:
                            try:
                                card = Card(
                                    bin=parts[0],
                                    number=parts[1],
                                    expiry=parts[2],
                                    cvv=parts[3],
                                    country=parts[4] if len(parts) > 4 else 'US',
                                    billing=parts[5] in ['1', 'True', 'yes', 'true'] if len(parts) > 5 else True,
                                    price=float(parts[6]) if len(parts) > 6 else 25.0,
                                    is_sold=False
                                )
                                cards.append(card)
                                success_count += 1
                            except:
                                continue
                
                session.bulk_insert_mappings(Card, [c.__dict__ for c in cards])
                session.commit()
                
                # Get stats
                total = session.query(Card).count()
                available = session.query(Card).filter(Card.is_sold == False).count()
                
                await update.message.reply_text(
                    f"✅ **Upload Complete!**\n\n"
                    f"📊 Cards Uploaded: {success_count}\n"
                    f"📈 Total Cards: {total}\n"
                    f"📉 Available for Sale: {available}\n\n"
                    f"🔄 Cards auto-sorted by country/BIN",
                    parse_mode="Markdown"
                )
                context.user_data['uploading'] = False
            
            finally:
                session.close()
        
        except Exception as e:
            await update.message.reply_text(f"❌ Upload error: {e}")
            context.user_data['uploading'] = False
    else:
        await update.message.reply_text("❌ Unsupported file format. Use .txt or .csv")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    logging.error(f"Exception while handling an update: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ An error occurred. Please try again.")
        except:
            pass

def main():
    print("✅ Starting bot...")
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add all handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("topup", topup))
    application.add_handler(CommandHandler("catalog", catalog))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(copy_usdt, pattern="^copy_usdt$"))
    application.add_handler(CallbackQueryHandler(country_callback, pattern="^country_"))
    
    # Admin handlers
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("countries", admin_countries))
    application.add_handler(CommandHandler("users", admin_users))
    application.add_handler(CommandHandler("add_card", admin_add_card))
    application.add_handler(CommandHandler("upload", admin_upload))
    
    # File upload handler (must be after command handlers)
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    print("✅ Bot is running...")
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
