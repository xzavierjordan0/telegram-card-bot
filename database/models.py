from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database.db import Base
from datetime import datetime

class Card(Base):
    __tablename__ = "cards"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bin = Column(String(6), nullable=False)
    number = Column(String(19), nullable=False)
    expiry = Column(String(5), nullable=False)
    cvv = Column(String(4), nullable=False)
    country = Column(String(2), nullable=False, default="US")
    billing = Column(Boolean, nullable=False, default=True)
    price = Column(Float, nullable=False, default=25.0)
    is_sold = Column(Boolean, nullable=False, default=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    order = relationship("Order", back_populates="cards")
    
    def __repr__(self):
        return f"<Card {self.id}: {self.bin} ****{self.number[-4:]}>"

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    details = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="orders")
    cards = relationship("Card", back_populates="order")
    
    def __repr__(self):
        return f"<Order {self.id}: ${self.amount}>"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String(50), unique=True, nullable=False)
    username = Column(String(100), nullable=True)
    balance = Column(Float, nullable=False, default=0.0)
    usdt_address = Column(String(100), nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    orders = relationship("Order", back_populates="user")
    
    def __repr__(self):
        return f"<User {self.telegram_id}: ${self.balance}>"
