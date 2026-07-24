import re
from typing import Optional

class CardParser:
    """Smart card parser for raw data files"""
    
    # Common country codes and names
    COUNTRY_MAP = {
        'US': ['UNITED STATES', 'USA', 'AMERICA', 'CALIFORNIA', 'TEXAS', 'NEW YORK', 'FLORIDA', 'GEORGIA', 'OHIO', 'PENNSYLVANIA'],
        'FR': ['FRANCE', 'FR', 'PARIS', 'LYON', 'MARSEILLE'],
        'UK': ['UNITED KINGDOM', 'UK', 'ENGLAND', 'LONDON', 'SCOTLAND', 'WALES'],
        'CA': ['CANADA', 'CA', 'TORONTO', 'VANCOUVER', 'MONTREAL'],
        'DE': ['GERMANY', 'DE', 'BERLIN', 'MUENCHEN'],
        'IT': ['ITALY', 'IT', 'ROMA', 'MILANO'],
        'ES': ['SPAIN', 'ES', 'MADRID', 'BARCELONA'],
        'AU': ['AUSTRALIA', 'AU', 'SYDNEY', 'MELBOURNE'],
        'NL': ['NETHERLANDS', 'NL', 'AMSTERDAM'],
        'BE': ['BELGIUM', 'BE', 'BRUSSELS'],
        'AT': ['AUSTRIA', 'AT', 'VIENNA'],
        'CH': ['SWITZERLAND', 'CH', 'ZURICH'],
        'SE': ['SWEDEN', 'SE', 'STOCKHOLM'],
        'NO': ['NORWAY', 'NO', 'OSLO'],
        'DK': ['DENMARK', 'DK', 'COPENHAGEN'],
        'FI': ['FINLAND', 'FI', 'HELSINKI'],
        'PL': ['POLAND', 'PL', 'WARSAW'],
        'PT': ['PORTUGAL', 'PT', 'LISBON'],
        'GR': ['GREECE', 'GR', 'ATHENS'],
        'IE': ['IRELAND', 'IE', 'DUBLIN'],
        'NZ': ['NEW ZEALAND', 'NZ', 'AUCKLAND'],
        'MX': ['MEXICO', 'MX', 'CDMX'],
        'BR': ['BRAZIL', 'BR', 'SAO PAULO', 'RIO'],
        'AR': ['ARGENTINA', 'AR', 'BUENOS AIRES'],
        'CL': ['CHILE', 'CL', 'SANTIAGO'],
        'CO': ['COLOMBIA', 'CO', 'BOGOTA'],
        'PE': ['PERU', 'PE', 'LIMA'],
        'RU': ['RUSSIA', 'RU', 'MOSCOW'],
        'TR': ['TURKEY', 'TR', 'ISTANBUL'],
        'IN': ['INDIA', 'IN', 'MUMBAI', 'DELHI'],
        'SG': ['SINGAPORE', 'SG'],
        'AE': ['UAE', 'AE', 'DUBAI'],
        'ZA': ['SOUTH AFRICA', 'ZA', 'JOHANNESBURG'],
        'JP': ['JAPAN', 'JP', 'TOKYO'],
        'KR': ['KOREA', 'KR', 'SEOUL'],
        'CN': ['CHINA', 'CN', 'BEIJING', 'SHANGHAI']
    }
    
    # Regex patterns
    CARD_NUMBER_PATTERN = re.compile(r'\b\d{13,19}\b')
    EXPIRY_PATTERN = re.compile(r'\b(?:0[1-9]|1[0-2])(?:\/|\-|)\d{2}\b')
    CVV_PATTERN = re.compile(r'\b\d{3,4}\b')
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    PHONE_PATTERN = re.compile(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b')
    POSTAL_CODE_PATTERN = re.compile(r'\b\d{4,6}\b')
    PRICE_PATTERN = re.compile(r'\$(?:[\d,]+\.)?[\d]{2}')
    
    def __init__(self):
        self.cards = []
        self.stats = {
            'total_lines': 0,
            'cards_found': 0,
            'cards_failed': 0,
            'clothed_count': 0,
            'naked_count': 0
        }
    
    def parse_line(self, line: str, default_price: float = 25.0, default_country: str = 'US') -> Optional[dict]:
        """Parse a single line and extract card data"""
        line = line.strip()
        if not line or line.startswith('#'):
            return None
        
        # Find card number (16 digits typically)
        card_numbers = self.CARD_NUMBER_PATTERN.findall(line)
        if not card_numbers:
            return None
        
        # Use the first valid card number (13-19 digits)
        card_number = None
        for num in card_numbers:
            if len(num) >= 13 and len(num) <= 19:
                card_number = num
                break
        
        if not card_number:
            return None
        
        # Extract BIN (first 6 digits)
        bin_number = card_number[:6]
        
        # Find expiry date (MM/YY or MM-YY or MMYY)
        expiry_match = self.EXPIRY_PATTERN.search(line)
        expiry = expiry_match.group() if expiry_match else '12/25'
        
        # Clean expiry format
        expiry = expiry.replace('-', '/')
        if len(expiry) == 4:
            expiry = f"{expiry[:2]}/{expiry[2:]}"
        
        # Find CVV (3-4 digits, usually near expiry or at end)
        cvv = self._extract_cvv(line, card_number)
        cvv = cvv or '123'
        
        # Extract price from line
        price = self._extract_price(line, default_price)
        
        # Detect country
        country = self._detect_country(line, default_country)
        
        # Detect billing info (clothed vs naked)
        has_billing = self._has_billing_info(line)
        
        # Extract name if available
        name = self._extract_name(line)
        
        # Extract email if available
        email = self._extract_email(line)
        
        # Extract phone if available
        phone = self._extract_phone(line)
        
        return {
            'bin': bin_number,
            'number': card_number,
            'expiry': expiry,
            'cvv': cvv,
            'country': country,
            'billing': has_billing,
            'price': price,
            'name': name,
            'email': email,
            'phone': phone
        }
    
    def _extract_cvv(self, line: str, card_number: str) -> Optional[str]:
        """Extract CVV from line"""
        # Look for 3-4 digit numbers that could be CVV
        # Typically after expiry or near end of line
        parts = line.split('|')
        
        for i, part in enumerate(parts):
            part = part.strip()
            # CVV is usually 3-4 digits, not part of card number
            if len(part) == 3 or len(part) == 4:
                if part.isdigit() and part != card_number:
                    # Check if it's not the card number
                    if part not in card_number:
                        return part
        
        # Fallback: find any 3-digit number
        cvv_matches = self.CVV_PATTERN.findall(line)
        for match in cvv_matches:
            if len(match) == 3 and match not in card_number:
                return match
        
        return None
    
    def _extract_price(self, line: str, default: float = 25.0) -> float:
        """Extract price from line"""
        price_matches = self.PRICE_PATTERN.findall(line)
        if price_matches:
            try:
                price = float(price_matches[0].replace('$', '').replace(',', ''))
                return price
            except ValueError:
                pass
        
        # Look for price in format like $0.6 or $1.5
        for match in re.findall(r'\$([\d.]+)', line):
            try:
                return float(match)
            except ValueError:
                pass
        
        return default
    
    def _detect_country(self, line: str, default: str = 'US') -> str:
        """Detect country from line"""
        line_upper = line.upper()
        
        # Check for country codes first
        for code in self.COUNTRY_MAP:
            if code in line_upper.split('|'):
                return code
        
        # Check for country names
        for code, keywords in self.COUNTRY_MAP.items():
            for keyword in keywords:
                if keyword in line_upper:
                    return code
        
        # Check for postal codes (can indicate country)
        postal = self.POSTAL_CODE_PATTERN.search(line)
        if postal:
            code = postal.group()
            if code.startswith('0') and len(code) == 5:
                return 'US'  # US postal codes start with 0-9
            elif len(code) == 5 and code.isdigit():
                return 'US'
        
        return default
    
    def _has_billing_info(self, line: str, threshold: int = 2) -> bool:
        """Check if line has billing information"""
        score = 0
        
        # Check for email
        if self.EMAIL_PATTERN.search(line):
            score += 3
        
        # Check for phone
        if self.PHONE_PATTERN.search(line):
            score += 2
        
        # Check for postal code
        if self.POSTAL_CODE_PATTERN.search(line):
            score += 1
        
        # Check for street address indicators
        address_keywords = ['RUE', 'STREET', 'AVE', 'AVENUE', 'BLVD', 'BOULEVARD', 'ROAD', 'LANE', 'PLACE', 'CARRER']
        for keyword in address_keywords:
            if keyword in line.upper():
                score += 1
                break
        
        # Check for name (first and last name pattern)
        if self._extract_name(line):
            score += 2
        
        return score >= threshold
    
    def _extract_name(self, line: str) -> Optional[str]:
        """Extract name from line"""
        parts = line.split('|')
        
        # Look for a part that looks like a name (2+ words, contains letters)
        for part in parts:
            part = part.strip()
            if len(part) > 3 and any(c.isalpha() for c in part):
                # Check if it contains common name patterns
                if re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', part):
                    return part
                if re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', part):
                    return part
        
        return None
    
    def _extract_email(self, line: str) -> Optional[str]:
        """Extract email from line"""
        matches = self.EMAIL_PATTERN.findall(line)
        return matches[0] if matches else None
    
    def _extract_phone(self, line: str) -> Optional[str]:
        """Extract phone from line"""
        matches = self.PHONE_PATTERN.findall(line)
        return matches[0] if matches else None
    
    def parse_file(self, file_path: str, default_price: float = 25.0, default_country: str = 'US'):
        """Parse entire file and return list of cards"""
        self.cards = []
        self.stats = {
            'total_lines': 0,
            'cards_found': 0,
            'cards_failed': 0,
            'clothed_count': 0,
            'naked_count': 0
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    self.stats['total_lines'] += 1
                    card = self.parse_line(line, default_price, default_country)
                    if card:
                        self.cards.append(card)
                        self.stats['cards_found'] += 1
                        if card['billing']:
                            self.stats['clothed_count'] += 1
                        else:
                            self.stats['naked_count'] += 1
                    else:
                        self.stats['cards_failed'] += 1
            
            return self.cards, self.stats
        except Exception as e:
            print(f"Error parsing file: {e}")
            return [], self.stats
    
    def get_summary(self) -> str:
        """Get parsing summary"""
        return (
            f"📊 **Parsing Summary**\n\n"
            f"📝 Total Lines: {self.stats['total_lines']}\n"
            f"✅ Cards Found: {self.stats['cards_found']}\n"
            f"❌ Failed: {self.stats['cards_failed']}\n"
            f"📦 Clothed: {self.stats['clothed_count']}\n"
            f"📦 Naked: {self.stats['naked_count']}\n\n"
            f"🎯 Success Rate: {(self.stats['cards_found']/self.stats['total_lines']*100):.1f}%"
        )
