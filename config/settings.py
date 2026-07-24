from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
USDT_ADDRESS = os.getenv('USDT_WALLET_ADDRESS')
ADMIN_IDS = os.getenv('ADMIN_USER_IDS', '').split(',')

# Force IPv4 connection for Supabase
if DATABASE_URL and 'supabase.co' in DATABASE_URL:
    DATABASE_URL = DATABASE_URL + "?sslmode=require&connect_timeout=10"
