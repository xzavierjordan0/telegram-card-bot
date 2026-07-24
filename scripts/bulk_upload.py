import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import csv
import re
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Card, Base
from config.settings import DATABASE_URL

# Database connection
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True, pool_recycle=3600)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def detect_delimiter(sample_lines):
    """Auto-detect delimiter (comma, pipe, space, tab)"""
    delimiters = [',', '|', '\t', ' ']
    counts = {}
    
    for delimiter in delimiters:
        count = sum(line.count(delimiter) for line in sample_lines[:10])
        counts[delimiter] = count
    
    return max(counts, key=counts.get) if counts else ','

def identify_field_pattern(value):
    """Identify what type of field this value represents"""
    value = str(value).strip()
    
    # BIN: 6 digits, starts with 3, 4, 5, or 6
    if re.match(r'^[3456]\d{5}$', value):
        return 'bin'
    
    # Card Number: 13-19 digits
    if re.match(r'^\d{13,19}$', value) and len(value) > 6:
        return 'number'
    
    # Expiry: MM/YY or MM-YY or MMYY
    if re.match(r'^\d{2}[/\-]?\d{2}$', value):
        return 'expiry'
    
    # CVV: 3-4 digits (but not 6-digit BIN)
    if re.match(r'^\d{3,4}$', value):
        return 'cvv'
    
    # Country: 2 uppercase letters
    if re.match(r'^[A-Z]{2}$', value):
        return 'country'
    
    # Billing: yes/no/1/0/true/false
    if value.lower() in ['yes', 'no', '1', '0', 'true', 'false']:
        return 'billing'
    
    # Balance/Price: Positive number
    if re.match(r'^\d+\.?\d*$', value):
        return 'price'  # We'll use this as price
    
    return 'unknown'

def map_fields_to_columns(parts):
    """Map detected fields to database columns"""
    field_map = {
        'bin': None,
        'number': None,
        'expiry': None,
        'cvv': None,
        'country': None,
        'billing': True,  # Default to True
        'price': 25.0    # Default to 25 USDT
    }
    
    seen_fields = {'bin', 'number', 'expiry', 'cvv', 'country', 'billing', 'price'}
    price_count = 0
    
    for value in parts:
        value = value.strip()
        if not value:
            continue
            
        field_type = identify_field_pattern(value)
        
        # Priority mapping (first match wins for most fields)
        if field_type in seen_fields and field_map.get(field_type) is None:
            if field_type == 'price':
                price_count += 1
                if price_count == 1:  # First number = price
                    field_map['price'] = float(value)
            elif field_type == 'billing':
                field_map['billing'] = value.lower() in ['1', 'true', 'yes', 't']
            else:
                field_map[field_type] = value
            seen_fields.discard(field_type)
    
    return field_map

def parse_expiry(expiry_str):
    """Convert various expiry formats to MM/YY"""
    expiry_str = str(expiry_str).strip()
    
    # If already MM/YY
    if re.match(r'^\d{2}/\d{2}$', expiry_str):
        return expiry_str
    
    # If MM-YY
    if re.match(r'^\d{2}-\d{2}$', expiry_str):
        return expiry_str.replace('-', '/')
    
    # If MMYY
    if re.match(r'^\d{4}$', expiry_str):
        return f"{expiry_str[:2]}/{expiry_str[2:]}"
    
    # If MM YYYY (e.g., "12 2026")
    if re.match(r'^\d{2} \d{4}$', expiry_str):
        parts = expiry_str.split()
        return f"{parts[0]}/{parts[1][2:]}"
    
    # If YYYY/MM (e.g., "2026/12")
    if re.match(r'^\d{4}/\d{2}$', expiry_str):
        parts = expiry_str.split('/')
        return f"{parts[1]}/{parts[0][2:]}"
    
    return expiry_str

def load_file(filepath):
    """Load card file and auto-detect format"""
    print(f"📂 Loading file: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
    
    if not lines:
        print("❌ File is empty!")
        return []
    
    # Detect delimiter
    delimiter = detect_delimiter(lines[:10])
    print(f"🔍 Detected delimiter: '{delimiter}'")
    
    # Parse each line
    parsed_cards = []
    for line in lines:
        parts = [p.strip() for p in line.split(delimiter)]
        if len(parts) < 4:
            continue
        
        field_map = map_fields_to_columns(parts)
        
        # Validate required fields
        if field_map['bin'] and field_map['number'] and field_map['expiry']:
            parsed_cards.append(field_map)
    
    return parsed_cards

def bulk_upload_smart(filepath):
    """Smart bulk upload with auto-detection and sorting"""
    db = SessionLocal()
    
    try:
        # Load and parse cards
        cards_data = load_file(filepath)
        
        if not cards_data:
            print("❌ No valid cards found!")
            return
        
        print(f"📊 Detected {len(cards_data)} cards")
        
        # Insert into database
        cards = []
        success_count = 0
        error_count = 0
        duplicates = 0
        
        for i, data in enumerate(cards_data):
            try:
                # Parse expiry
                expiry = parse_expiry(data.get('expiry', '01/25'))
                
                # Create card with defaults
                card = Card(
                    bin=data.get('bin', '000000'),
                    number=data.get('number', ''),
                    expiry=expiry,
                    cvv=data.get('cvv', '000'),
                    country=data.get('country', 'US'),
                    billing=data.get('billing', True),
                    price=float(data.get('price', 25)),
                    is_sold=False
                )
                
                # Check for duplicates
                existing = db.query(Card).filter_by(bin=card.bin).first()
                if existing:
                    duplicates += 1
                    continue
                
                cards.append(card)
                success_count += 1
                
                if (i + 1) % 100 == 0:
                    print(f"⏳ Processed {i + 1} cards...")
            
            except Exception as e:
                error_count += 1
                print(f"⚠️ Error on card {i + 1}: {e}")
        
        # Bulk insert
        db.bulk_insert_mappings(Card, [c.__dict__ for c in cards])
        db.commit()
        
        # Auto-sort cards by country and BIN
        print(f"\n🔄 Auto-sorting cards by country and BIN...")
        
        # Count by country
        country_stats = db.query(Card.country).group_by(Card.country).all()
        print(f"\n📊 Cards by Country:")
        for country, count in country_stats:
            print(f"   🏳️ {country}: {count} cards")
        
        print(f"\n✅ Upload Complete!")
        print(f"📊 Successful: {success_count}")
        print(f"❌ Errors: {error_count}")
        print(f"🔁 Duplicates: {duplicates}")
        print(f"📈 Total in DB: {db.query(Card).count()}")
        print(f"📉 Available for sale: {db.query(Card).filter(Card.is_sold == False).count()}")
    
    except Exception as e:
        print(f"❌ Upload failed: {e}")
    
    finally:
        db.close()

def upload_all_from_folder(folder_path):
    """Upload all card files from a folder"""
    print(f"📂 Scanning folder: {folder_path}")
    
    valid_extensions = ['.txt', '.csv', '.dat', '.log', '.tsv']
    files = [f for f in os.listdir(folder_path) 
             if any(f.lower().endswith(ext) for ext in valid_extensions)]
    
    if not files:
        print("❌ No card files found!")
        return
    
    print(f"📁 Found {len(files)} card files")
    
    total_uploaded = 0
    for filename in files:
        filepath = os.path.join(folder_path, filename)
        print(f"\n{'='*50}")
        print(f"📄 Uploading: {filename}")
        print('='*50)
        bulk_upload_smart(filepath)
        total_uploaded += 1
    
    print(f"\n{'='*50}")
    print(f"✅ BATCH COMPLETE: {total_uploaded} files processed")
    print('='*50)

if __name__ == "__main__":
    import sys
    
    print("="*50)
    print("🎴 SMART CARD BULK UPLOAD")
    print("="*50)
    
    if len(sys.argv) > 1:
        # File specified via command line
        upload_single_file(sys.argv[1])
    else:
        # Interactive mode
        print("\n📋 Upload Options:")
        print("1. Upload single file")
        print("2. Upload all files from folder")
        
        choice = input("\nEnter choice (1 or 2): ").strip()
        
        if choice == '1':
            filename = input("Enter filename: ").strip()
            bulk_upload_smart(filename)
        elif choice == '2':
            folder = input("Enter folder path (e.g., uploads): ").strip()
            if not folder:
                folder = "uploads"
            upload_all_from_folder(folder)
        else:
            print("❌ Invalid choice!")
