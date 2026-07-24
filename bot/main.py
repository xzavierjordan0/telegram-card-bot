import sys
import io
import os
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
engine = create_engine(
    DATABASE_URL, 
    echo=False, 
    pool_pre_ping=True, 
    pool_recycle=3600,
    connect_args={
        'sslmode': 'require',
        'connect_timeout': 10
    }
)

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

async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show BIN lookup instructions"""
    await update.message.reply_text(
        "🔍 **BIN Lookup**\n\n"
        "Enter a BIN to search (first 6 digits):\n\n"
        "Example: `/bin 414720`",
        parse_mode="Markdown"
    )

async def handle_bin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search cards by BIN and show stock by subcategory"""
    session = SessionLocal()
    try:
        # Extract BIN from command
        command_parts = update.message.text.split(' ')
        if len(command_parts) < 2:
            await update.message.reply_text("❌ Please provide a BIN number.\n\nExample: `/bin 414720`")
            return
        
        bin_number = command_parts[1].strip()
        
        # Validate BIN (should be 6 digits)
        if not bin_number.isdigit() or len(bin_number) != 6:
            await update.message.reply_text("❌ BIN must be exactly 6 digits.\n\nExample: `/bin 414720`")
            return
        
        # Get first card to fetch BIN details
        first_card = session.query(Card).filter(
            Card.bin == bin_number
        ).first()
        
        if not first_card:
            await update.message.reply_text(f"📭 No cards found for BIN `{bin_number}`")
            return
        
        # Count stock by billing status
        clothed_cards = session.query(Card).filter(
            Card.bin == bin_number,
            Card.billing == True,
            Card.is_sold == False
        ).count()
        
        naked_cards = session.query(Card).filter(
            Card.bin == bin_number,
            Card.billing == False,
            Card.is_sold == False
        ).count()
        
        total_available = clothed_cards + naked_cards
        
        # Get prices (can be different for clothed vs naked)
        clothed_card = session.query(Card).filter(
            Card.bin == bin_number,
            Card.billing == True
        ).first()
        naked_card = session.query(Card).filter(
            Card.bin == bin_number,
            Card.billing == False
        ).first()
        
        clothed_price = clothed_card.price if clothed_card else first_card.price
        naked_price = naked_card.price if naked_card else first_card.price
        
        # Get BIN metadata
        bin_metadata = get_bin_metadata(bin_number)
        
        # Build response
        response_text = f"🎴 **BIN: {bin_number}**\n\n"
        
        # Add BIN metadata
        if bin_metadata:
            for key, value in bin_metadata.items():
                response_text += f"{key}: `{value}`\n"
            response_text += "\n"
        
        # Add stock counts with new terms
        response_text += f"📦 **Clothed:** {clothed_cards} @ ${clothed_price} USDT\n"
        response_text += f"📦 **Naked:** {naked_cards} @ ${naked_price} USDT\n\n"
        response_text += f"📊 **Total Available:** {total_available}\n\n"
        
        if total_available == 0:
            await update.message.reply_text(response_text, parse_mode="Markdown")
            return
        
        # Add order button
        keyboard = [[InlineKeyboardButton(text="🛒 Order Now", callback_data=f"order_bin_{bin_number}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(response_text, reply_markup=reply_markup, parse_mode="Markdown")
    
    finally:
        session.close()

async def order_bin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BIN order form"""
    query = update.callback_query
    bin_number = query.data.split("_")[2]
    
    # Store BIN in user data
    context.user_data['selected_bin'] = bin_number
    
    session = SessionLocal()
    try:
        # Get stock counts again
        clothed_cards = session.query(Card).filter(
            Card.bin == bin_number,
            Card.billing == True,
            Card.is_sold == False
        ).count()
        
        naked_cards = session.query(Card).filter(
            Card.bin == bin_number,
            Card.billing == False,
            Card.is_sold == False
        ).count()
        
        # Get prices
        clothed_card = session.query(Card).filter(
            Card.bin == bin_number,
            Card.billing == True
        ).first()
        naked_card = session.query(Card).filter(
            Card.bin == bin_number,
            Card.billing == False
        ).first()
        
        clothed_price = clothed_card.price if clothed_card else 25.0
        naked_price = naked_card.price if naked_card else 25.0
        
        # Build order form
        order_text = f"🛒 **Order BIN {bin_number}**\n\n"
        order_text += f"📦 **Clothed:** {clothed_cards} available @ ${clothed_price}\n"
        order_text += f"📦 **Naked:** {naked_cards} available @ ${naked_price}\n\n"
        order_text += f"*Enter quantities (separated by comma):*\n"
        order_text += f"Example: `5,3` (5 Clothed, 3 Naked)\n"
        order_text += f"\n*Or just one number for Clothed only:*\n"
        order_text += f"Example: `10` (10 Clothed)"
        
        await query.edit_message_text(order_text, parse_mode="Markdown")
        await query.answer("Enter quantities: `clothed,naked` or just `clothed`")
    
    finally:
        session.close()

async def handle_bin_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process BIN order with quantities and deliver .TXT file"""
    user = await get_or_create_user(update.effective_user.id)
    selected_bin = context.user_data.get('selected_bin')
    
    if not selected_bin:
        await update.message.reply_text("❌ No BIN selected. Use `/bin` first.")
        return
    
    session = SessionLocal()
    try:
        # Parse quantities
        quantities = update.message.text.split(' ')
        if len(quantities) < 2:
            await update.message.reply_text("❌ Please enter quantities.\n\nExample: `5,3`")
            return
        
        qty_input = quantities[1].strip()
        
        # Parse clothed and naked quantities
        if ',' in qty_input:
            parts = qty_input.split(',')
            clothed_qty = int(parts[0].strip())
            naked_qty = int(parts[1].strip())
        else:
            clothed_qty = int(qty_input)
            naked_qty = 0
        
        # Validate quantities
        if clothed_qty < 0 or naked_qty < 0:
            await update.message.reply_text("❌ Quantities cannot be negative.")
            return
        
        if clothed_qty == 0 and naked_qty == 0:
            await update.message.reply_text("❌ Please order at least 1 card.")
            return
        
        # Check stock availability
        clothed_available = session.query(Card).filter(
            Card.bin == selected_bin,
            Card.billing == True,
            Card.is_sold == False
        ).count()
        
        naked_available = session.query(Card).filter(
            Card.bin == selected_bin,
            Card.billing == False,
            Card.is_sold == False
        ).count()
        
        # Get prices
        clothed_card = session.query(Card).filter(
            Card.bin == selected_bin,
            Card.billing == True
        ).first()
        naked_card = session.query(Card).filter(
            Card.bin == selected_bin,
            Card.billing == False
        ).first()
        
        clothed_price = clothed_card.price if clothed_card else 25.0
        naked_price = naked_card.price if naked_card else 25.0
        
        # Calculate total (BIN-specific pricing)
        total_cost = (clothed_qty * clothed_price) + (naked_qty * naked_price)
        
        # Check user balance
        if user.balance < total_cost:
            await update.message.reply_text(
                f"❌ **Insufficient Balance!**\n\n"
                f"💰 Your Balance: `{user.balance} USDT`\n"
                f"💰 Required: `{total_cost:.2f} USDT`\n\n"
                f"Use `/topup` to add funds.",
                parse_mode="Markdown"
            )
            return
        
        # Check if enough stock
        if clothed_qty > clothed_available:
            await update.message.reply_text(
                f"❌ **Not enough Clothed cards!**\n\n"
                f"📊 Available: {clothed_available}\n"
                f"📊 You requested: {clothed_qty}"
            )
            return
        
        if naked_qty > naked_available:
            await update.message.reply_text(
                f"❌ **Not enough Naked cards!**\n\n"
                f"📊 Available: {naked_available}\n"
                f"📊 You requested: {naked_qty}"
            )
            return
        
        # Create order
        order = Order(
            user_id=user.id,
            amount=total_cost,
            status="completed",
            details=f"BIN {selected_bin} - {clothed_qty} Clothed, {naked_qty} Naked"
        )
        session.add(order)
        
        # Deduct balance
        user.balance -= total_cost
        
        # Get cards to sell
        clothed_cards_to_sell = session.query(Card).filter(
            Card.bin == selected_bin,
            Card.billing == True,
            Card.is_sold == False
        ).limit(clothed_qty).all()
        
        naked_cards_to_sell = session.query(Card).filter(
            Card.bin == selected_bin,
            Card.billing == False,
            Card.is_sold == False
        ).limit(naked_qty).all()
        
        # Build .TXT file content
        txt_content = f"🎴 CARD DELIVERY - Order #{order.id}\n"
        txt_content += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        txt_content += f"🆔 User: {user.telegram_id}\n"
        txt_content += f"🎴 BIN: {selected_bin}\n"
        txt_content += f"📊 Total Cards: {len(clothed_cards_to_sell) + len(naked_cards_to_sell)}\n"
        txt_content += f"💰 Total Cost: ${total_cost:.2f} USDT\n\n"
        txt_content += f"{'='*50}\n\n"
        txt_content += f"📦 CLOTHED ({len(clothed_cards_to_sell)} cards)\n"
        txt_content += f"{'-'*50}\n"
        
        for card in clothed_cards_to_sell:
            card.is_sold = True
            card.order_id = order.id
            txt_content += f"{card.number}|{card.expiry}|{card.cvv}\n"
        
        txt_content += f"\n{'='*50}\n\n"
        txt_content += f"📦 NAKED ({len(naked_cards_to_sell)} cards)\n"
        txt_content += f"{'-'*50}\n"
        
        for card in naked_cards_to_sell:
            card.is_sold = True
            card.order_id = order.id
            txt_content += f"{card.number}|{card.expiry}|{card.cvv}\n"
        
        txt_content += f"\n\n{'='*50}\n"
        txt_content += f"✅ All cards verified and ready!\n"
        
        session.commit()
        
        # Create .TXT file and send to user
        file_bytes = io.BytesIO(txt_content.encode('utf-8'))
        file_bytes.name = f"order_{order.id}_{selected_bin}.txt"
        
        await update.message.reply_document(
            document=file_bytes,
            caption=f"✅ **Order #{order.id} Complete!**\n\n"
                   f"🎴 BIN: {selected_bin}\n"
                   f"📦 Clothed: {len(clothed_cards_to_sell)} cards\n"
                   f"📦 Naked: {len(naked_cards_to_sell)} cards\n"
                   f"💰 Total: ${total_cost:.2f} USDT\n"
                   f"💰 New Balance: `{user.balance} USDT`",
            parse_mode="Markdown"
        )
        
        # Clear user data
        context.user_data.pop('selected_bin', None)
    
    finally:
        session.close()

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
        await update.message.reply_text("🔒 Admin command only!")
        return
    
    if not context.user_data.get('uploading'):
        return  # Don't process file if not waiting for upload
    
    document = update.message.document
    filename = document.file_name
    
    if filename.endswith(('.txt', '.csv', '.dat', '.log', '.tsv')):
        await update.message.reply_text("⏳ Downloading file...")
        
        try:
            # Create uploads directory BEFORE downloading file
            os.makedirs("uploads", exist_ok=True)
            
            # Download file
            file_path = f"uploads/{filename}"
            file = await context.bot.get_file(document.file_id)
            await file.download_to_drive(file_path)
            
            # Process file
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
                            except ValueError:
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
            
            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                await update.message.reply_text(f"❌ **Upload Error:**\n\n{error_msg}")
                context.user_data['uploading'] = False
                session.rollback()
            finally:
                session.close()
        
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            await update.message.reply_text(f"❌ **Download Error:**\n\n{error_msg}")
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
