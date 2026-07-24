import sys
import io
import os
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database.models import User, Card, Order, Base
from config.settings import BOT_TOKEN, USDT_ADDRESS, ADMIN_IDS, DATABASE_URL
from datetime import datetime

# Default prices
DEFAULT_NAKED_PRICE = 0.33
DEFAULT_CLOTHED_PRICE = 25.0

print("🔄 Starting bot initialization...")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def timeout_handler(signum, frame):
    print("❌ Startup timeout!")
    sys.exit(1)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(45)

print("🔄 Connecting to database...")
engine = create_engine(
    DATABASE_URL, 
    echo=False, 
    pool_pre_ping=True, 
    pool_recycle=3600,
    connect_args={'sslmode': 'prefer', 'connect_timeout': 10}
)

try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("✅ Database connected successfully!")
    signal.alarm(0)
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    sys.exit(1)

print("🔄 Checking database tables...")
if not Base.metadata.reflect(bind=engine):
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created!")
else:
    print("✅ Database tables already exist!")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Path("uploads").mkdir(exist_ok=True)
print("✅ Uploads directory ready!")

async def get_or_create_user(telegram_id: int):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=str(telegram_id)).first()
        if not user:
            user = User(telegram_id=str(telegram_id), username="", usdt_address=USDT_ADDRESS, is_admin=str(telegram_id) in ADMIN_IDS)
            session.add(user)
            session.commit()
        return user
    finally:
        session.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎴 **Welcome to CardStore!**\n\n"
        "💰 USDT Payments | 🌍 Global Cards\n\n"
        "📋 *Commands:*\n"
        "/balance - Check your balance\n"
        "/topup - Get USDT deposit address\n"
        "/catalog - Browse cards\n"
        "/bin - BIN lookup\n"
        "/history - View purchases\n"
        "/help - Show all commands",
        parse_mode="Markdown"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    await update.message.reply_text(f"💰 **Your Balance:** `{user.balance} USDT`", parse_mode="Markdown")

async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    keyboard = [[InlineKeyboardButton(text="📋 Copy Address", callback_data="copy_usdt")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"💰 **USDT Deposit Address**\n\n`{user.usdt_address}`\n\n📡 Network: **TRC20 (Tron)**",
        reply_markup=reply_markup, parse_mode="Markdown"
    )

async def copy_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Address copied to clipboard!", show_alert=True)

async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            card_text += f"🆔 ID: `{card.id}`\n🏦 BIN: `{card.bin}`\n💳 ****{card.number[-4:]}\n🏷️ Price: ${card.price} USDT\n\n"
        await query.edit_message_text(card_text, parse_mode="Markdown")
    finally:
        session.close()

async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 **BIN Lookup**\n\nEnter a BIN to search (first 6 digits):\n\nExample: `/bin 414720`", parse_mode="Markdown")

async def handle_bin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    try:
        command_parts = update.message.text.split(' ')
        if len(command_parts) < 2:
            await update.message.reply_text("❌ Please provide a BIN number.\n\nExample: `/bin 414720`")
            return
        bin_number = command_parts[1].strip()
        if not bin_number.isdigit() or len(bin_number) != 6:
            await update.message.reply_text("❌ BIN must be exactly 6 digits.\n\nExample: `/bin 414720`")
            return
        first_card = session.query(Card).filter(Card.bin == bin_number).first()
        if not first_card:
            await update.message.reply_text(f"📭 No cards found for BIN `{bin_number}`")
            return
        clothed_cards = session.query(Card).filter(Card.bin == bin_number, Card.billing == True, Card.is_sold == False).count()
        naked_cards = session.query(Card).filter(Card.bin == bin_number, Card.billing == False, Card.is_sold == False).count()
        total_available = clothed_cards + naked_cards
        clothed_card = session.query(Card).filter(Card.bin == bin_number, Card.billing == True).first()
        naked_card = session.query(Card).filter(Card.bin == bin_number, Card.billing == False).first()
        clothed_price = clothed_card.price if clothed_card else DEFAULT_CLOTHED_PRICE
        naked_price = naked_card.price if naked_card else DEFAULT_NAKED_PRICE
        response_text = f"🎴 **BIN: {bin_number}**\n\n"
        response_text += f"📦 **Clothed:** {clothed_cards} @ ${clothed_price} USDT\n"
        response_text += f"📦 **Naked:** {naked_cards} @ ${naked_price} USDT\n\n"
        response_text += f"📊 **Total Available:** {total_available}\n\n"
        if total_available == 0:
            await update.message.reply_text(response_text, parse_mode="Markdown")
            return
        keyboard = [[InlineKeyboardButton(text="🛒 Order Now", callback_data=f"order_bin_{bin_number}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(response_text, reply_markup=reply_markup, parse_mode="Markdown")
    finally:
        session.close()

async def order_bin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    bin_number = query.data.split("_")[2]
    context.user_data['selected_bin'] = bin_number
    session = SessionLocal()
    try:
        clothed_cards = session.query(Card).filter(Card.bin == bin_number, Card.billing == True, Card.is_sold == False).count()
        naked_cards = session.query(Card).filter(Card.bin == bin_number, Card.billing == False, Card.is_sold == False).count()
        clothed_card = session.query(Card).filter(Card.bin == bin_number, Card.billing == True).first()
        naked_card = session.query(Card).filter(Card.bin == bin_number, Card.billing == False).first()
        clothed_price = clothed_card.price if clothed_card else DEFAULT_CLOTHED_PRICE
        naked_price = naked_card.price if naked_card else DEFAULT_NAKED_PRICE
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
    user = await get_or_create_user(update.effective_user.id)
    selected_bin = context.user_data.get('selected_bin')
    if not selected_bin:
        await update.message.reply_text("❌ No BIN selected. Use `/bin` first.")
        return
    session = SessionLocal()
    try:
        quantities = update.message.text.split(' ')
        if len(quantities) < 2:
            await update.message.reply_text("❌ Please enter quantities.\n\nExample: `5,3`")
            return
        qty_input = quantities[1].strip()
        if ',' in qty_input:
            parts = qty_input.split(',')
            clothed_qty = int(parts[0].strip())
            naked_qty = int(parts[1].strip())
        else:
            clothed_qty = int(qty_input)
            naked_qty = 0
        if clothed_qty < 0 or naked_qty < 0:
            await update.message.reply_text("❌ Quantities cannot be negative.")
            return
        if clothed_qty == 0 and naked_qty == 0:
            await update.message.reply_text("❌ Please order at least 1 card.")
            return
        clothed_available = session.query(Card).filter(Card.bin == selected_bin, Card.billing == True, Card.is_sold == False).count()
        naked_available = session.query(Card).filter(Card.bin == selected_bin, Card.billing == False, Card.is_sold == False).count()
        clothed_card = session.query(Card).filter(Card.bin == selected_bin, Card.billing == True).first()
        naked_card = session.query(Card).filter(Card.bin == selected_bin, Card.billing == False).first()
        clothed_price = clothed_card.price if clothed_card else DEFAULT_CLOTHED_PRICE
        naked_price = naked_card.price if naked_card else DEFAULT_NAKED_PRICE
        total_cost = (clothed_qty * clothed_price) + (naked_qty * naked_price)
        if user.balance < total_cost:
            await update.message.reply_text(f"❌ **Insufficient Balance!**\n\n💰 Your Balance: `{user.balance} USDT`\n💰 Required: `{total_cost:.2f} USDT`\n\nUse `/topup` to add funds.", parse_mode="Markdown")
            return
        if clothed_qty > clothed_available:
            await update.message.reply_text(f"❌ **Not enough Clothed cards!**\n\n📊 Available: {clothed_available}\n📊 You requested: {clothed_qty}")
            return
        if naked_qty > naked_available:
            await update.message.reply_text(f"❌ **Not enough Naked cards!**\n\n📊 Available: {naked_available}\n📊 You requested: {naked_qty}")
            return
        order = Order(user_id=user.id, amount=total_cost, status="completed", details=f"BIN {selected_bin} - {clothed_qty} Clothed, {naked_qty} Naked")
        session.add(order)
        user.balance -= total_cost
        clothed_cards_to_sell = session.query(Card).filter(Card.bin == selected_bin, Card.billing == True, Card.is_sold == False).limit(clothed_qty).all()
        naked_cards_to_sell = session.query(Card).filter(Card.bin == selected_bin, Card.billing == False, Card.is_sold == False).limit(naked_qty).all()
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
        file_bytes = io.BytesIO(txt_content.encode('utf-8'))
        file_bytes.name = f"order_{order.id}_{selected_bin}.txt"
        await update.message.reply_document(document=file_bytes, caption=f"✅ **Order #{order.id} Complete!**\n\n🎴 BIN: {selected_bin}\n📦 Clothed: {len(clothed_cards_to_sell)} cards\n📦 Naked: {len(naked_cards_to_sell)} cards\n💰 Total: ${total_cost:.2f} USDT\n💰 New Balance: `{user.balance} USDT`", parse_mode="Markdown")
        context.user_data.pop('selected_bin', None)
    finally:
        session.close()

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        orders = session.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(5).all()
        if not orders:
            await update.message.reply_text("📭 No purchase history yet.")
            return
        history_text = "📋 **Purchase History**\n\n"
        for order in orders:
            history_text += f"🆔 Order #{order.id}\n💰 Amount: ${order.amount} USDT\n📊 Status: `{order.status}`\n📅 Date: {order.created_at.strftime('%Y-%m-%d')}\n\n"
        await update.message.reply_text(history_text, parse_mode="Markdown")
    finally:
        session.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 **Available Commands:**\n\n/start - Welcome message\n/balance - Check USDT balance\n/topup - Get deposit address\n/catalog - Browse cards by country\n/bin - BIN lookup\n/history - View purchase history\n/help - Show this message\n\n*Admin Commands:*\n/stats - View store statistics\n/upload - Bulk upload cards\n/edit_price - Edit BIN prices\n/add_price - Set default upload price\n/export - Export all cards to file", parse_mode="Markdown")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(f"📊 **Store Statistics**\n\n👥 Total Users: {total_users}\n🎴 Total Cards: {total_cards}\n✅ Cards Sold: {cards_sold}\n📉 Available: {total_cards - cards_sold}\n📦 Total Orders: {total_orders}", parse_mode="Markdown")
    finally:
        session.close()

async def admin_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    await update.message.reply_text("📝 **Edit BIN Price**\n\nUsage: /edit_price BIN PRICE\n\nExample: /edit_price 414720 25\n\nThis will update ALL cards with BIN 414720 to $25 USDT")

async def handle_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    session = SessionLocal()
    try:
        parts = update.message.text.split(' ')
        if len(parts) < 3:
            await update.message.reply_text("❌ Invalid format.\n\nUsage: /edit_price BIN PRICE")
            return
        bin_number = parts[1].strip()
        try:
            price = float(parts[2].strip())
        except ValueError:
            await update.message.reply_text("❌ Price must be a number.")
            return
        count = session.query(Card).filter(Card.bin == bin_number).count()
        if count == 0:
            await update.message.reply_text(f"❌ No cards found with BIN {bin_number}")
            return
        session.query(Card).filter(Card.bin == bin_number).update({'price': price})
        session.commit()
        await update.message.reply_text(f"✅ **BIN Price Updated!**\n\n🎴 BIN: {bin_number}\n💰 New Price: ${price} USDT\n📊 Cards Updated: {count}", parse_mode="Markdown")
    finally:
        session.close()

async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    await update.message.reply_text("📝 **Set Default Upload Price**\n\nUsage: /add_price PRICE\n\nExample: /add_price 0.50\n\nThis sets the default price for ALL new uploaded cards to $0.50 USDT\n\n*Default is $0.33 for naked cards*")

async def handle_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    session = SessionLocal()
    try:
        parts = update.message.text.split(' ')
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format.\n\nUsage: /add_price PRICE")
            return
        try:
            price = float(parts[1].strip())
        except ValueError:
            await update.message.reply_text("❌ Price must be a number.")
            return
        count = session.query(Card).filter(Card.is_sold == False).count()
        session.query(Card).filter(Card.is_sold == False).update({'price': price})
        session.commit()
        await update.message.reply_text(f"✅ **Default Price Set!**\n\n💰 New Price: ${price} USDT\n📊 Cards Updated: {count}\n\n*All naked cards now ready for sale!*", parse_mode="Markdown")
    finally:
        session.close()

async def admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    context.user_data['uploading'] = True
    await update.message.reply_text(
        "📦 **Bulk Upload Cards**\n\n"
        "📁 Send a card file (.txt, .csv, .dat)\n\n"
        "**Accepted Formats:**\n"
        "- cc|mm|yy|cvv\n"
        "- cc,mm,yy,cvv\n"
        "- cc mm yy cvv\n"
        "- Any format with 4+ fields\n\n"
        "✅ Auto-detects format\n"
        f"✅ Default Price: ${DEFAULT_NAKED_PRICE} USDT\n"
        "✅ Default Country: US\n"
        "✅ All cards marked as Naked (no billing)\n"
        "\n⏳ Waiting for file...",
        parse_mode="Markdown"
    )

async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    session = SessionLocal()
    try:
        cards = session.query(Card).all()
        if not cards:
            await update.message.reply_text("📭 No cards to export.")
            return
        txt_content = "🎴 CARD EXPORT\n"
        txt_content += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        txt_content += f"📊 Total Cards: {len(cards)}\n\n"
        for card in cards:
            txt_content += f"{card.id}|{card.bin}|{card.number}|{card.expiry}|{card.cvv}|{card.country}|{card.billing}|{card.price}|{card.is_sold}\n"
        file_bytes = io.BytesIO(txt_content.encode('utf-8'))
        file_bytes.name = f"cards_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        await update.message.reply_document(document=file_bytes, caption=f"✅ **Export Complete!**\n\n📊 Total Cards: {len(cards)}")
    finally:
        session.close()

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    if not context.user_data.get('uploading'):
        return
    document = update.message.document
    filename = document.file_name
    if filename.endswith(('.txt', '.csv', '.dat', '.log', '.tsv')):
        await update.message.reply_text("⏳ Downloading file...")
        print(f"📁 Downloading file: {filename}")
        try:
            os.makedirs("uploads", exist_ok=True)
            file_path = f"uploads/{filename}"
            file = await context.bot.get_file(document.file_id)
            await file.download_to_drive(file_path)
            print(f"✅ File downloaded to: {file_path}")
            
            if not os.path.exists(file_path):
                await update.message.reply_text(f"❌ File not found at: {file_path}")
                context.user_data['uploading'] = False
                return
            file_size = os.path.getsize(file_path)
            print(f"📊 File size: {file_size} bytes")
            
            session = SessionLocal()
            try:
                cards = []
                success_count = 0
                failed_count = 0
                total_lines = 0
                
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        total_lines += 1
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        delimiters = [',', '|', '\t', ' ']
                        delimiter = max(delimiters, key=lambda d: line.count(d))
                        parts = [p.strip() for p in line.split(delimiter)]
                        
                        print(f"📝 Line {line_num}: {len(parts)} parts, delimiter: '{delimiter}'")
                        
                        if len(parts) >= 4:
                            try:
                                card_number = parts[0]
                                expiry_month = parts[1]
                                expiry_year = parts[2]
                                cvv = parts[3]
                                
                                if not card_number.isdigit() or len(card_number) < 13 or len(card_number) > 19:
                                    failed_count += 1
                                    print(f"⚠️ Line {line_num}: Invalid card number")
                                    continue
                                
                                expiry = f"{expiry_month}/{expiry_year}"
                                bin_number = card_number[:6]
                                
                                # Default values
                                country = parts[4] if len(parts) > 4 and len(parts[4]) == 2 else 'US'
                                billing = parts[5] in ['1', 'True', 'yes', 'true'] if len(parts) > 5 else False
                                # Default price is $0.33 for naked cards
                                price = float(parts[6]) if len(parts) > 6 and parts[6].replace('.', '').isdigit() else DEFAULT_NAKED_PRICE
                                
                                card = Card(
                                    bin=bin_number,
                                    number=card_number,
                                    expiry=expiry,
                                    cvv=cvv,
                                    country=country,
                                    billing=billing,
                                    price=price,
                                    is_sold=False
                                )
                                cards.append(card)
                                success_count += 1
                            except (ValueError, IndexError) as e:
                                failed_count += 1
                                print(f"❌ Line {line_num} parse error: {e}")
                        else:
                            failed_count += 1
                            print(f"⚠️ Line {line_num}: Only {len(parts)} parts (need 4+)")
                
                print(f"✅ Cards to insert: {success_count}")
                print(f"❌ Failed lines: {failed_count}")
                
                if success_count > 0:
                    session.bulk_insert_mappings(Card, [c.__dict__ for c in cards])
                    session.commit()
                
                total = session.query(Card).count()
                available = session.query(Card).filter(Card.is_sold == False).count()
                
                await update.message.reply_text(
                    f"✅ **Upload Complete!**\n\n"
                    f"📊 Cards Uploaded: {success_count}\n"
                    f"❌ Failed Lines: {failed_count}\n"
                    f"📈 Total Cards: {total}\n"
                    f"📉 Available: {available}\n\n"
                    f"💰 Default Price: ${DEFAULT_NAKED_PRICE} USDT\n"
                    f"📁 File: `{filename}`\n"
                    f"📊 File Size: {file_size} bytes",
                    parse_mode="Markdown"
                )
                context.user_data['uploading'] = False
            
            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                print(f"❌ Upload error: {error_msg}")
                if len(error_msg) > 3900:
                    error_msg = error_msg[:3900] + "...\n[Truncated]"
                await update.message.reply_text(f"❌ **Upload Error:**\n\n{error_msg}")
                context.user_data['uploading'] = False
                session.rollback()
            finally:
                session.close()
        
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            print(f"❌ Download error: {error_msg}")
            if len(error_msg) > 3900:
                error_msg = error_msg[:3900] + "...\n[Truncated]"
            await update.message.reply_text(f"❌ **Download Error:**\n\n{error_msg}")
            context.user_data['uploading'] = False
    else:
        await update.message.reply_text("❌ Unsupported file format. Use .txt or .csv")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Exception while handling an update: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ An error occurred. Please try again.")
        except:
            pass

def main():
    print("✅ Starting bot...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("topup", topup))
    application.add_handler(CommandHandler("catalog", catalog))
    application.add_handler(CommandHandler("bin", bin_lookup))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Regex('^/bin '), handle_bin_search))
    application.add_handler(MessageHandler(filters.Regex('^/edit_price '), handle_edit_price))
    application.add_handler(MessageHandler(filters.Regex('^/add_price '), handle_add_price))
    application.add_handler(CallbackQueryHandler(copy_usdt, pattern="^copy_usdt$"))
    application.add_handler(CallbackQueryHandler(country_callback, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(order_bin_callback, pattern="^order_bin_"))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin_order))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("upload", admin_upload))
    application.add_handler(CommandHandler("edit_price", admin_edit_price))
    application.add_handler(CommandHandler("add_price", admin_add_price))
    application.add_handler(CommandHandler("export", admin_export))
    application.add_error_handler(error_handler)
    print("✅ Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
        print("✅ Bot started successfully!")
