import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Card, Base
from config.settings import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=True)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db = SessionLocal()

test_cards = [
    Card(bin="414720", number="4147201234567890", expiry="12/26", cvv="123", 
         balance=500.0, country="US", billing=True, price=25.0),
    Card(bin="485460", number="4854601234567890", expiry="06/27", cvv="456", 
         balance=1000.0, country="CA", billing=True, price=35.0),
    Card(bin="471610", number="4716101234567890", expiry="03/27", cvv="789", 
         balance=300.0, country="UK", billing=False, price=20.0),
    Card(bin="400551", number="4005511234567890", expiry="09/26", cvv="321", 
         balance=750.0, country="US", billing=True, price=30.0)
]

for card in test_cards:
    db.add(card)

db.commit()
db.close()

print("✅ Test cards seeded successfully!")

