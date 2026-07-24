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

# ============================================================================
# 🎨 VISUAL THEME & FORMATTERS
# ============================================================================

def format_card_display(card, index=1):
    """Format a card for beautiful display"""
    return (
        f"🎴 **Card #{index}**\n"
        f"🏦 BIN: `{card.bin}`\n"
        f"💳 ****{card.number[-4:]}\n"
        f"📅 Expiry: {card.expiry}\n"
        f"🌍 Country: 🏳️‍{card.country}\n"
        f"🏷️ Type: {'👔 CLOTHED' if card.billing else '👕 NAKED'}\n"
        f"💰 **Price: ${card.price:.2f} USDT**\n\n"
    )

def format_separator(title=""):
    """Visual separator"""
    if title:
        return f"\n{'━'*50}\n📌 **{title}**\n{'━'*50}\n"
    return f"\n{'─'*50}\n\n"

def format_success_box(message, title="✅ SUCCESS"):
    """Success message with box styling"""
    return f"""
┌──────────────────────────────────────┐
│ {title}                              │
├──────────────────────────────────────┤
│ {message}                          │
└──────────────────────────────────────┘
"""

def format_error_box(message, title="❌ ERROR"):
    """Error message with box styling"""
    return f"""
┌──────────────────────────────────────┐
│ {title}                              │
├──────────────────────────────────────┤
│ {message}                          │
└──────────────────────────────────────┘
"""

# ============================================================================
# 🚀 INITIALIZATION
# ============================================================================

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

# ============================================================================
# 👤 USER MANAGEMENT
# ============================================================================

async def get_or_create_user(telegram_id: int):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=str(telegram_id)).first()
        if not user:
            user = User(
                telegram_id=str(telegram_id), 
                username="", 
                usdt_address=USDT_ADDRESS, 
                is_admin=str(telegram_id) in ADMIN_IDS,
                balance=0.00
            )
            session.add(user)
            session.commit()
        return user
    finally:
        session.close()

# ============================================================================
# 🏠 MAIN MENU & NAVIGATION
# ============================================================================

def create_main_menu():
    """Create beautiful main menu keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="💰 Balance", callback_data="menu_balance")],
        [InlineKeyboardButton(text="📦 Shop Cards", callback_data="menu_catalog")],
        [InlineKeyboardButton(text="🔍 BIN Lookup", callback_data="menu_bin")],
        [InlineKeyboardButton(text="📜 History", callback_data="menu_history")],
        [InlineKeyboardButton(text="🔄 Top Up", callback_data="menu_topup")],
        [InlineKeyboardButton(text="❓ Help", callback_data="menu_help")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Beautiful welcome screen with main menu"""
    welcome_text = """
✨ **WELCOME TO CARDSTORE!** ✨

🎴 *Premium Credit Card Marketplace*
💰 *USDT Payments (TRC20)*
🌍 *Global Card Selection*

👇 *Tap a button below to get started:*
"""
    await update.message.reply_text(
        welcome_text, 
        reply_markup=create_main_menu(),
        parse_mode="Markdown"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance with menu"""
    user = await get_or_create_user(update.effective_user.id)
    await update.message.reply_text(
        f"""💰 **YOUR BALANCE**

┌──────────────────────────────────────┐
│ 💵 Balance: `{user.balance:.2f} USDT` │
└──────────────────────────────────────┘
""",
        parse_mode="Markdown",
        reply_markup=create_main_menu()
    )

async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show topup info with menu"""
    user = await get_or_create_user(update.effective_user.id)
    keyboard = [[InlineKeyboardButton(text="📋 Copy Address", callback_data="copy_usdt")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"💰 **USDT Deposit Address**\n\n`{user.usdt_address}`\n\n📡 Network: **TRC20 (Tron)**",
        reply_markup=reply_markup, parse_mode="Markdown"
    )

async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show catalog menu"""
    await update.message.reply_text(
        "📦 **SHOP CARDS**\n\n🎯 *Select your preferred category:*",
        parse_mode="Markdown",
        reply_markup=create_catalog_menu()
    )

async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """BIN lookup with better UX"""
    await update.message.reply_text(
        "🔍 **BIN LOOKUP**\n\n"
        "🎯 *Enter a BIN number (first 6 digits):*\n\n"
        f"💡 Example: `/bin 414720`\n\n"
        "⏳ *I'm waiting for your BIN...*",
        parse_mode="Markdown"
    )
    context.user_data['waiting_for_bin'] = True

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show history with menu"""
    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        orders = session.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(5).all()
        if not orders:
            await update.message.reply_text("📭 No purchase history yet.", reply_markup=create_main_menu())
            return
        history_text = "📋 **Purchase History**\n\n"
        for order in orders:
            history_text += f"🆔 Order #{order.id}\n💰 Amount: ${order.amount} USDT\n📊 Status: `{order.status}`\n📅 Date: {order.created_at.strftime('%Y-%m-%d')}\n\n"
        await update.message.reply_text(history_text, reply_markup=create_main_menu(), parse_mode="Markdown")
    finally:
        session.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help menu"""
    await update.message.reply_text(
        "📋 **Available Commands:**\n\n"
        "/start - Welcome message\n"
        "/balance - Check USDT balance\n"
        "/topup - Get deposit address\n"
        "/catalog - Browse cards\n"
        "/bin - BIN lookup\n"
        "/history - View purchase history\n"
        "/help - Show this message\n\n"
        "*Admin Commands:*\n"
        "/stats - View store statistics\n"
        "/upload - Bulk upload cards\n"
        "/edit_price - Edit BIN prices\n"
        "/add_price - Set default upload price\n"
        "/export - Export all cards to file",
        parse_mode="Markdown",
        reply_markup=create_main_menu()
    )

async def menu_navigator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all menu button clicks"""
    query = update.callback_query
    await query.answer()
    
    user = await get_or_create_user(update.effective_user.id)
    data = query.data
    
    if data == "menu_balance":
        await query.edit_message_text(
            f"""💰 **YOUR BALANCE**

┌──────────────────────────────────────┐
│ 💵 Balance: `{user.balance:.2f} USDT` │
└──────────────────────────────────────┘

*Quick Actions:*
""",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="💸 Top Up Now", callback_data="menu_topup")],
                [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_home")],
            ])
        )
    
    elif data == "menu_catalog":
        await query.edit_message_text(
            "📦 **SHOP CARDS**\n\n🎯 *Select your preferred category:*",
            parse_mode="Markdown",
            reply_markup=create_catalog_menu()
        )
    
    elif data == "menu_bin":
        await query.edit_message_text(
            "🔍 **BIN LOOKUP**\n\n*Enter a BIN (first 6 digits) to search:*",
            parse_mode="Markdown"
        )
        context.user_data['waiting_for_bin'] = True
    
    elif data == "menu_history":
        await query.edit_message_text(
            "📜 **PURCHASE HISTORY**\n\n*Tap to view your recent orders:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="📋 View History", callback_data="view_history")],
                [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_home")],
            ])
        )
    
    elif data == "menu_topup":
        await query.edit_message_text(
            f"💸 **TOP UP BALANCE**\n\n"
            f"📡 *Network:* **TRC20 (Tron)**\n"
            f"💎 *Minimum:* **0.01 USDT**\n\n"
            f"`{user.usdt_address}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="📋 Copy Address", callback_data="copy_usdt")],
                [InlineKeyboardButton(text="✅ Confirm Deposit", callback_data="confirm_deposit")],
                [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_home")],
            ])
        )
    
    elif data == "menu_help":
        await query.edit_message_text(
            """❓ **HELP CENTER**

📋 **Available Commands:**
/start - Welcome & Main Menu
/balance - Check Balance
/topup - Get Deposit Address
/catalog - Browse Cards
/bin - BIN Lookup
/history - View Orders
/help - Show Help

💡 **Quick Tips:**
• Use inline buttons for faster navigation
• BIN lookup shows all available cards
• Payments are automatic after order confirmation
• All cards are verified before delivery

*Need support? Contact admin!*
""",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🏠 Back to Home", callback_data="menu_home")],
            ])
        )
    
    elif data == "menu_home":
        await query.edit_message_text(
            """🏠 **MAIN MENU**

*Select an option:*""",
            parse_mode="Markdown",
            reply_markup=create_main_menu()
        )

# ============================================================================
# 📦 SHOPPING & CATALOG
# ============================================================================

def create_catalog_menu():
    """Create catalog navigation menu"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🇺🇸 USA Cards", callback_data="cat_country_US")],
        [InlineKeyboardButton(text="🇨🇦 Canada Cards", callback_data="cat_country_CA")],
        [InlineKeyboardButton(text="🇬🇧 UK Cards", callback_data="cat_country_UK")],
        [InlineKeyboardButton(text="🌍 All Countries", callback_data="cat_country_ALL")],
        [InlineKeyboardButton(text="⚡ Popular BINS", callback_data="cat_popular")],
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_home")],
    ])

async def catalog_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle catalog country selection"""
    query = update.callback_query
    await query.answer()
    
    country_code = query.data.split("_")[2]
    session = SessionLocal()
    try:
        if country_code == "ALL":
            cards = session.query(Card).filter(Card.is_sold == False).limit(10).all()
            title = "🌍 **All Countries**"
        elif country_code == "POP":
            cards = session.query(Card).filter(Card.is_sold == False).order_by(Card.price.asc()).limit(10).all()
            title = "⚡ **Popular BINS**"
        else:
            cards = session.query(Card).filter(Card.country == country_code, Card.is_sold == False).limit(10).all()
            title = f"🏳️‍{country_code} **{country_code} Cards**"
        
        if not cards:
            await query.answer(f"📭 No {country_code} cards available.", show_alert=True)
            return
        
        # Create card display with buttons
        card_text = f"{title}\n\n"
        for idx, card in enumerate(cards[:5], 1):
            card_text += format_card_display(card, idx)
        
        # Create buy buttons for each card
        keyboard = []
        for idx, card in enumerate(cards[:5], 1):
            keyboard.append([
                InlineKeyboardButton(text=f"🛒 Buy Card #{idx}", callback_data=f"buy_card_{card.id}"),
            ])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_catalog")])
        
        await query.edit_message_text(
            card_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        session.close()

async def buy_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle individual card purchase"""
    query = update.callback_query
    await query.answer()
    
    card_id = query.data.split("_")[2]
    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        card = session.query(Card).filter_by(id=card_id).first()
        if not card or card.is_sold:
            await query.answer("❌ Card no longer available!", show_alert=True)
            return
        
        # Check balance
        if user.balance < card.price:
            await query.answer(
                f"❌ Insufficient Balance!\n\n"
                f"💰 Required: ${card.price:.2f} USDT\n"
                f"💵 Your Balance: ${user.balance:.2f} USDT",
                show_alert=True
            )
            return
        
        # Confirm purchase
        await query.edit_message_text(
            f"""🛒 **PURCHASE CONFIRMATION**

🎴 **Card Details:**
🏦 BIN: `{card.bin}`
💳 ****{card.number[-4:]}
📅 Expiry: {card.expiry}
🌍 Country: 🏳️‍{card.country}
🏷️ Type: {'👔 CLOTHED' if card.billing else '👕 NAKED'}

💰 **Price: ${card.price:.2f} USDT**

*Confirm purchase?*""",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="✅ YES, Buy Now", callback_data=f"confirm_buy_{card.id}")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_catalog")],
            ])
        )
    finally:
        session.close()

async def confirm_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process confirmed purchase"""
    query = update.callback_query
    await query.answer()
    
    card_id = query.data.split("_")[2]
    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        card = session.query(Card).filter_by(id=card_id).first()
        if not card or card.is_sold:
            await query.answer("❌ Card no longer available!", show_alert=True)
            return
        
        # Process order
        order = Order(
            user_id=user.id,
            amount=card.price,
            status="completed",
            details=f"Card ID: {card.id}"
        )
        session.add(order)
        
        card.is_sold = True
        card.order_id = order.id
        user.balance -= card.price
        session.commit()
        
        # Create delivery text
        delivery_text = (
            f"🎴 **CARD DELIVERY**\n"
            f"🆔 Order #{order.id}\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"{'='*40}\n"
            f"💳 {card.number}\n"
            f"📅 {card.expiry}\n"
            f"🔐 {card.cvv}\n"
            f"{'='*40}\n\n"
            f"💰 Total: ${card.price:.2f} USDT\n"
            f"💵 New Balance: ${user.balance:.2f} USDT\n\n"
            f"✅ Card delivered instantly!"
        )
        
        await query.edit_message_text(
            format_success_box("Card Purchased Successfully!", "✅ PURCHASE COMPLETE"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🏠 Back to Home", callback_data="menu_home")],
            ])
        )
        
        await query.message.reply_text(
            delivery_text,
            parse_mode="Markdown"
        )
    finally:
        session.close()

# ============================================================================
# 🔍 BIN LOOKUP (IMPROVED)
# ============================================================================

async def handle_bin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BIN search with visual results"""
    if not context.user_data.get('waiting_for_bin'):
        return
    
    session = SessionLocal()
    try:
        command_parts = update.message.text.split(' ')
        if len(command_parts) < 2:
            await update.message.reply_text("❌ Please provide a BIN number.\n\n💡 Example: `/bin 414720`")
            return
        
        bin_number = command_parts[1].strip()
        if not bin_number.isdigit() or len(bin_number) != 6:
            await update.message.reply_text("❌ BIN must be exactly 6 digits.\n\n💡 Example: `/bin 414720`")
            return
        
        # Search results
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
        
        clothed_card = session.query(Card).filter(
            Card.bin == bin_number, 
            Card.billing == True
        ).first()
        
        naked_card = session.query(Card).filter(
            Card.bin == bin_number, 
            Card.billing == False
        ).first()
        
        clothed_price = clothed_card.price if clothed_card else DEFAULT_CLOTHED_PRICE
        naked_price = naked_card.price if naked_card else DEFAULT_NAKED_PRICE
        
        # Display results
        result_text = (
            f"🔍 **BIN: {bin_number}**\n\n"
            f"{'━'*40}\n"
            f"👔 **Clothed Cards:** {clothed_cards} @ ${clothed_price:.2f} USDT\n"
            f"👕 **Naked Cards:** {naked_cards} @ ${naked_price:.2f} USDT\n\n"
            f"📊 **Total Available:** {total_available} cards\n\n"
        )
        
        if total_available == 0:
            await update.message.reply_text(
                result_text + "📭 *No cards available for this BIN*",
                parse_mode="Markdown"
            )
            context.user_data['waiting_for_bin'] = False
            return
        
        # Order buttons
        keyboard = [
            [InlineKeyboardButton(text=f"🛒 Order Clothed (👔)", callback_data=f"order_bin_cloth_{bin_number}")],
            [InlineKeyboardButton(text=f"🛒 Order Naked (👕)", callback_data=f"order_bin_naked_{bin_number}")],
            [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_home")],
        ]
        
        await update.message.reply_text(
            result_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data['waiting_for_bin'] = False
        context.user_data['selected_bin'] = bin_number
    finally:
        session.close()

async def order_bin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BIN order with quantity selector"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    order_type = parts[2]
    bin_number = parts[3]
    
    context.user_data['selected_bin'] = bin_number
    context.user_data['order_type'] = order_type
    
    session = SessionLocal()
    try:
        if order_type == "cloth":
            available = session.query(Card).filter(
                Card.bin == bin_number,
                Card.billing == True,
                Card.is_sold == False
            ).count()
            card_type = "👔 CLOTHED"
            card_price = DEFAULT_CLOTHED_PRICE
        else:
            available = session.query(Card).filter(
                Card.bin == bin_number,
                Card.billing == False,
                Card.is_sold == False
            ).count()
            card_type = "👕 NAKED"
            card_price = DEFAULT_NAKED_PRICE
        
        order_text = (
            f"🛒 **ORDER {card_type} CARDS**\n"
            f"🎯 **BIN:** `{bin_number}`\n\n"
            f"📦 **Available:** {available} cards\n"
            f"💰 **Price:** ${card_price:.2f} USDT each\n\n"
            f"🎯 *Select quantity:*\n"
        )
        
        # Create quantity buttons (1, 5, 10, 25, 50, Custom)
        keyboard = [
            [
                InlineKeyboardButton(text="1", callback_data=f"qty_1_{bin_number}_{order_type}"),
                InlineKeyboardButton(text="5", callback_data=f"qty_5_{bin_number}_{order_type}"),
                InlineKeyboardButton(text="10", callback_data=f"qty_10_{bin_number}_{order_type}"),
            ],
            [
                InlineKeyboardButton(text="25", callback_data=f"qty_25_{bin_number}_{order_type}"),
                InlineKeyboardButton(text="50", callback_data=f"qty_50_{bin_number}_{order_type}"),
                InlineKeyboardButton(text="🔢 Custom", callback_data=f"qty_custom_{bin_number}_{order_type}"),
            ],
            [InlineKeyboardButton(text="🔙 Back", callback_data=f"order_bin_{order_type}_{bin_number}")],
        ]
        
        await query.edit_message_text(
            order_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        session.close()

async def handle_quantity_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quantity selection"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    quantity = int(parts[1])
    bin_number = parts[2]
    order_type = parts[3]
    
    context.user_data['selected_quantity'] = quantity
    
    session = SessionLocal()
    try:
        if order_type == "cloth":
            available = session.query(Card).filter(
                Card.bin == bin_number,
                Card.billing == True,
                Card.is_sold == False
            ).count()
            card_price = DEFAULT_CLOTHED_PRICE
        else:
            available = session.query(Card).filter(
                Card.bin == bin_number,
                Card.billing == False,
                Card.is_sold == False
            ).count()
            card_price = DEFAULT_NAKED_PRICE
        
        total_cost = quantity * card_price
        user = await get_or_create_user(update.effective_user.id)
        
        # Check availability and balance
        if quantity > available:
            await query.answer(
                f"❌ Only {available} cards available!",
                show_alert=True
            )
            return
        
        if user.balance < total_cost:
            await query.answer(
                f"❌ Insufficient Balance!\n\n"
                f"💰 Required: ${total_cost:.2f} USDT\n"
                f"💵 Your Balance: ${user.balance:.2f} USDT",
                show_alert=True
            )
            return
        
        # Confirm order
        await query.edit_message_text(
            f"""🛒 **ORDER SUMMARY**

🎯 **BIN:** `{bin_number}`
📦 **Quantity:** {quantity} cards
🏷️ **Type:** {'👔 CLOTHED' if order_type == 'cloth' else '👕 NAKED'}
💰 **Total:** ${total_cost:.2f} USDT
💵 **Your Balance:** ${user.balance:.2f} USDT

*Confirm order?*""",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="✅ YES, Complete Order", callback_data=f"confirm_order_{bin_number}_{order_type}_{quantity}")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"order_bin_{order_type}_{bin_number}")],
            ])
        )
    finally:
        session.close()

# ============================================================================
# 💸 TOP UP & DEPOSIT
# ============================================================================

async def copy_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Copy USDT address"""
    query = update.callback_query
    await query.answer("✅ Address copied to clipboard!", show_alert=True)

async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm deposit message"""
    query = update.callback_query
    await query.answer("✅ Deposit confirmed! Please send USDT to the address above.", show_alert=True)

# ============================================================================
# 📜 HISTORY
# ============================================================================

async def view_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View purchase history with better formatting"""
    query = update.callback_query
    await query.answer()
    
    user = await get_or_create_user(update.effective_user.id)
    session = SessionLocal()
    try:
        orders = session.query(Order).filter(
            Order.user_id == user.id
        ).order_by(Order.created_at.desc()).limit(10).all()
        
        if not orders:
            await query.edit_message_text(
                "📭 **No Purchase History Yet**\n\n"
                "*Start shopping to see your orders here!*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(text="🛍️ Shop Now", callback_data="menu_catalog")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data="menu_history")],
                ])
            )
            return
        
        history_text = "📜 **PURCHASE HISTORY**\n\n"
        for order in orders:
            history_text += (
                f"🆔 **Order #{order.id}**\n"
                f"💰 Amount: ${order.amount:.2f} USDT\n"
                f"📊 Status: `{order.status}`\n"
                f"📅 Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                f"{order.details}\n\n"
            )
        
        await query.edit_message_text(
            history_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_home")],
            ])
        )
    finally:
        session.close()

# ============================================================================
# 👑 ADMIN COMMANDS (IMPROVED)
# ============================================================================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin statistics with visual formatting"""
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
        available = total_cards - cards_sold
        
        stats_text = (
            f"📊 **STORE STATISTICS**\n\n"
            f"{'━'*40}\n"
            f"👥 **Total Users:** {total_users}\n"
            f"🎴 **Total Cards:** {total_cards}\n"
            f"✅ **Cards Sold:** {cards_sold}\n"
            f"📉 **Available:** {available}\n"
            f"📦 **Total Orders:** {total_orders}\n"
            f"{'━'*40}\n\n"
            f"📈 **Success Rate:** {(cards_sold/total_cards*100):.1f}%"
        )
        
        await update.message.reply_text(
            stats_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="📥 Export Cards", callback_data="admin_export")],
                [InlineKeyboardButton(text="📤 Upload Cards", callback_data="admin_upload")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")],
            ])
        )
    finally:
        session.close()


async def admin_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin edit BIN price"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    await update.message.reply_text(
        "📝 **Edit BIN Price**\n\n"
        "Usage: `/edit_price BIN PRICE`\n\n"
        "Example: `/edit_price 414720 25`\n\n"
        "This will update ALL cards with BIN 414720 to $25 USDT",
        parse_mode="Markdown"
    )

async def handle_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle edit price command"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    session = SessionLocal()
    try:
        parts = update.message.text.split(' ')
        if len(parts) < 3:
            await update.message.reply_text("❌ Invalid format.\n\nUsage: `/edit_price BIN PRICE`")
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
        await update.message.reply_text(
            f"✅ **BIN Price Updated!**\n\n"
            f"🎴 BIN: {bin_number}\n"
            f"💰 New Price: ${price} USDT\n"
            f"📊 Cards Updated: {count}",
            parse_mode="Markdown"
        )
    finally:
        session.close()

async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin add default price"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    await update.message.reply_text(
        "📝 **Set Default Upload Price**\n\n"
        "Usage: `/add_price PRICE`\n\n"
        "Example: `/add_price 0.50`\n\n"
        "This sets the default price for ALL new uploaded cards to $0.50 USDT\n\n"
        f"*Default is ${DEFAULT_NAKED_PRICE} for naked cards*",
        parse_mode="Markdown"
    )

async def handle_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add price command"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    session = SessionLocal()
    try:
        parts = update.message.text.split(' ')
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format.\n\nUsage: `/add_price PRICE`")
            return
        try:
            price = float(parts[1].strip())
        except ValueError:
            await update.message.reply_text("❌ Price must be a number.")
            return
        count = session.query(Card).filter(Card.is_sold == False).count()
        session.query(Card).filter(Card.is_sold == False).update({'price': price})
        session.commit()
        await update.message.reply_text(
            f"✅ **Default Price Set!**\n\n"
            f"💰 New Price: ${price} USDT\n"
            f"📊 Cards Updated: {count}\n\n"
            "*All naked cards now ready for sale!*",
            parse_mode="Markdown"
        )
    finally:
        session.close()

async def admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin upload cards"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    context.user_data['uploading'] = True
    await update.message.reply_text(
        "📦 **BULK UPLOAD CARDS**\n\n"
        "📁 *Send a card file (.txt, .csv, .dat)*\n\n"
        "**Accepted Formats:**\n"
        "• `cc|mm|yy|cvv`\n"
        "• `cc,mm,yy,cvv`\n"
        "• `cc mm yy cvv`\n\n"
        f"✅ *Default Price:* ${DEFAULT_NAKED_PRICE} USDT\n"
        "✅ *Default Country:* US\n"
        "✅ *All cards marked as NAKED*\n\n"
        "⏳ *Waiting for file...*",
        parse_mode="Markdown"
    )

async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin export cards"""
    query = update.callback_query
    await query.answer()
    
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await query.answer("🔒 Admin command only!", show_alert=True)
        return
    
    session = SessionLocal()
    try:
        cards = session.query(Card).all()
        if not cards:
            await query.answer("📭 No cards to export.", show_alert=True)
            return
        
        txt_content = f"🎴 CARD EXPORT\n"
        txt_content += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        txt_content += f"📊 Total Cards: {len(cards)}\n\n"
        for card in cards:
            txt_content += f"{card.id}|{card.bin}|{card.number}|{card.expiry}|{card.cvv}|{card.country}|{card.billing}|{card.price}|{card.is_sold}\n"
        
        file_bytes = io.BytesIO(txt_content.encode('utf-8'))
        file_bytes.name = f"cards_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        await query.message.reply_document(
            document=file_bytes, 
            caption=f"✅ **Export Complete!**\n\n📊 Total Cards: {len(cards)}"
        )
    finally:
        session.close()

# ============================================================================
# 📁 FILE UPLOAD HANDLER
# ============================================================================

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file upload with progress feedback"""
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
                    f"✅ **UPLOAD COMPLETE!**\n\n"
                    f"{'━'*40}\n"
                    f"📊 Cards Uploaded: {success_count}\n"
                    f"❌ Failed Lines: {failed_count}\n"
                    f"📈 Total Cards: {total}\n"
                    f"📉 Available: {available}\n"
                    f"{'━'*40}\n\n"
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

# ============================================================================
# 🛒 BIN ORDER HANDLER
# ============================================================================

async def handle_bin_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BIN order completion"""
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

# ============================================================================
# ⚙️ MAIN BOT SETUP
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    logging.error(f"Exception while handling an update: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ An error occurred. Please try again.\n\n"
                "If the problem persists, contact support."
            )
        except:
            pass

def main():
    """Main bot initialization"""
    print("✅ Starting bot...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("topup", topup))
    application.add_handler(CommandHandler("catalog", catalog))
    application.add_handler(CommandHandler("bin", bin_lookup))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("upload", admin_upload))
    application.add_handler(CommandHandler("edit_price", admin_edit_price))
    application.add_handler(CommandHandler("add_price", admin_add_price))
    application.add_handler(CommandHandler("export", admin_export))
    
    # Regex Handlers
    application.add_handler(MessageHandler(filters.Regex('^/bin '), handle_bin_search))
    application.add_handler(MessageHandler(filters.Regex('^/edit_price '), handle_edit_price))
    application.add_handler(MessageHandler(filters.Regex('^/add_price '), handle_add_price))
    
    # Callback Query Handlers
    application.add_handler(CallbackQueryHandler(menu_navigator, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(copy_usdt, pattern="^copy_usdt$"))
    application.add_handler(CallbackQueryHandler(confirm_deposit, pattern="^confirm_deposit$"))
    application.add_handler(CallbackQueryHandler(catalog_callback, pattern="^cat_"))
    application.add_handler(CallbackQueryHandler(buy_card_callback, pattern="^buy_card_"))
    application.add_handler(CallbackQueryHandler(confirm_buy_callback, pattern="^confirm_buy_"))
    application.add_handler(CallbackQueryHandler(country_callback, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(order_bin_callback, pattern="^order_bin_"))
    application.add_handler(CallbackQueryHandler(handle_quantity_selection, pattern="^qty_"))
    application.add_handler(CallbackQueryHandler(view_history, pattern="^view_history$"))
    application.add_handler(CallbackQueryHandler(admin_export, pattern="^admin_export$"))
    application.add_handler(CallbackQueryHandler(admin_upload, pattern="^admin_upload$"))
    
    # Message Handlers
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin_order))
    
    # Error Handler
    application.add_error_handler(error_handler)
    
    print("✅ Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
        print("✅ Bot started successfully!")
    except Exception as e:
        import traceback
        print(f"❌ Bot crashed: {e}")
        traceback.print_exc()
        sys.exit(1)

