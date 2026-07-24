# services/usdt_service.py
import requests
from datetime import datetime, timedelta

class USDTService:
    def __init__(self):
        self.tron_api = "https://api.trongrid.io"
        self.min_confirmations = 1
        self.usdt_contract = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    
    async def get_user_address(self, telegram_id: str):
        """Get or create unique USDT address for user"""
        session = SessionLocal()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if user and user.usdt_address:
                return user.usdt_address
            
            # Generate unique address (or use your main wallet + memo)
            # For simplicity, use main wallet with memo system
            from config.settings import USDT_ADDRESS
            return USDT_ADDRESS
        finally:
            session.close()
    
    async def check_pending_deposits(self):
        """Check for new USDT deposits every 30 seconds"""
        session = SessionLocal()
        try:
            # Get all pending deposits
            pending = session.query(Deposit).filter(
                Deposit.status == 'pending',
                Deposit.created_at > datetime.utcnow() - timedelta(hours=1)
            ).all()
            
            for deposit in pending:
                # Check Tron blockchain
                tx_result = await self.verify_transaction(deposit.tx_hash)
                
                if tx_result['valid']:
                    # Confirm deposit
                    deposit.status = 'confirmed'
                    deposit.confirmed_at = datetime.utcnow()
                    
                    # Add to user balance
                    user = session.query(User).filter_by(telegram_id=deposit.user_id).first()
                    if user:
                        user.balance += tx_result['amount']
                        await self.notify_user(deposit.user_id, tx_result['amount'])
                    
                    session.commit()
        finally:
            session.close()
    
    async def verify_transaction(self, tx_hash: str):
        """Verify USDT transaction on Tron network"""
        try:
            response = requests.get(f"{self.tron_api}/wallet/v1/trigger/constantcontract/byid/{tx_hash}")
            tx_data = response.json()
            
            if tx_data.get('result'):
                amount = tx_data['result'] / 10**6  # Convert from suns
                return {'valid': True, 'amount': amount}
            
            return {'valid': False, 'amount': 0}
        except:
            return {'valid': False, 'amount': 0}
    
    async def notify_user(self, telegram_id: str, amount: float):
        """Notify user of successful deposit"""
        from telegram import Bot
        from config.settings import BOT_TOKEN
        
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            telegram_id,
            f"✅ **Deposit Confirmed!**\n\n"
            f"💰 Amount: {amount} USDT\n"
            f"📊 New Balance: {amount} USDT\n\n"
            f"🎴 Your funds are ready to use!",
            parse_mode="Markdown"
        )

# Start background checker
import asyncio

async def deposit_checker():
    service = USDTService()
    while True:
        await service.check_pending_deposits()
        await asyncio.sleep(30)  # Check every 30 seconds

# Run in main()
asyncio.create_task(deposit_checker())
