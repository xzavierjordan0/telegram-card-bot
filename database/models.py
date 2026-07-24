from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), unique=True, index=True)
    username = Column(String(100))
    balance = Column(Float, default=0.0)
    usdt_address = Column(String(100))
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    orders = relationship("Order", back_populates="user")

class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True)
    bin = Column(String(6), index=True)
    number = Column(String(16))
    expiry = Column(String(5))
    cvv = Column(String(3))
    balance = Column(Float, default=0.0)
    country = Column(String(2), index=True)
    billing = Column(Boolean, default=True)
    is_sold = Column(Boolean, default=False)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    sold_at = Column(DateTime)
    
    __table_args__ = (
        Index('idx_bin_country', 'bin', 'country'),
        Index('idx_country_sold', 'country', 'is_sold'),
    )

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    card_id = Column(Integer, ForeignKey("cards.id"))
    amount = Column(Float)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="orders")
