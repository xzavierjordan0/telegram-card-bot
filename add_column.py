from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL

# Create database connection
engine = create_engine(
    DATABASE_URL,
    echo=True,
    connect_args={'sslmode': 'prefer'}
)

print("🔄 Connecting to database...")

try:
    # Add order_id column if it doesn't exist
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'cards' AND column_name = 'order_id'
        """))
        
        exists = result.scalar()
        
        if exists:
            print("✅ Column 'order_id' already exists!")
        else:
            print("📝 Adding 'order_id' column to cards table...")
            conn.execute(text("""
                ALTER TABLE cards 
                ADD COLUMN order_id INTEGER REFERENCES orders(id)
            """))
            conn.commit()
            print("✅ Column 'order_id' added successfully!")
    
    # Verify all columns
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'cards' 
            ORDER BY ordinal_position
        """))
        
        print("\n📊 Cards table columns:")
        for row in result:
            print(f"  - {row[0]} ({row[1]})")
    
    print("\n✅ Done! You can now upload cards.")
    
except Exception as e:
    print(f"❌ Error: {e}")
