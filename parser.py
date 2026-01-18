"""
Receipt parser for extracting items, prices, and discounts
"""
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ParsedItem:
    """Represents a parsed item from a receipt"""
    name: str
    price: float
    count: int
    raw: str
    weight: Optional[float] = None
    price_per_unit: Optional[float] = None
    unit: Optional[str] = None
    is_discount: bool = False
    discount_name: Optional[str] = None
    discount_amount: Optional[float] = None


@dataclass
class ParsedReceipt:
    """Represents a fully parsed receipt"""
    items: List[ParsedItem]
    total: float
    date: str
    store_name: str
    card_last4: str
    raw: str


class ReceiptParser:
    # Pattern for standard items: NAME    PRICE
    ITEM_PATTERN = re.compile(r'^([A-ZÅÄÖ0-9\s\-\*%/]+?)\s{2,}([\d,\.]+)\s*$')
    
    # Pattern for items with count: NAME    Nst*PRICE    TOTAL
    COUNT_PATTERN = re.compile(r'^([A-ZÅÄÖ0-9\s\-\*%/]+?)\s+(\d+)st\*[\d,\.]+\s+([\d,\.]+)\s*$')
    
    # Pattern for weighted items: NAME
    #                              WEIGHT*PRICE/UNIT    TOTAL
    WEIGHT_LINE1_PATTERN = re.compile(r'^([A-ZÅÄÖ0-9\s\-\*%/]+?)\s*$')
    WEIGHT_LINE2_PATTERN = re.compile(
        r'^\s+([\d,\.]+)(kg|g|st)\*([\d,\.]+)kr/(kg|g|st)\s+([\d,\.]+)\s*$'
    )
    
    # Pattern for discounts (indented, starts with spaces or "Rabatt:")
    DISCOUNT_PATTERN = re.compile(
        r'^\s+(Rabatt:)?([A-ZÅÄÖ0-9\s\-]+?)\s+\-?([\d,\.]+)\s*$'
    )
    
    # Pattern for total
    TOTAL_PATTERN = re.compile(r'^\s*Totalt\s+([\d,\.]+)\s+SEK\s*$', re.IGNORECASE)
    
    # Pattern for date/time
    DATE_PATTERN = re.compile(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})')
    
    # Pattern for card number
    CARD_PATTERN = re.compile(r'\*+(\d{4})')
    
    def __init__(self):
        pass
    
    @staticmethod
    def _parse_float(value: str) -> float:
        """Parse Swedish number format (comma as decimal separator)"""
        return float(value.replace(',', '.'))
    
    def parse_receipt_text(self, text: str) -> ParsedReceipt:
        """Parse receipt text and extract all information"""
        lines = text.split('\n')
        
        # Extract metadata
        store_name = self._extract_store_name(lines)
        date = self._extract_date(lines)
        card_last4 = self._extract_card(lines)
        total = self._extract_total(lines)
        
        # Parse items
        items = self._parse_items(lines)
        
        return ParsedReceipt(
            items=items,
            total=total,
            date=date,
            store_name=store_name,
            card_last4=card_last4,
            raw=text
        )
    
    def _extract_store_name(self, lines: List[str]) -> str:
        """Extract store name from first few lines"""
        # Usually the first non-empty line
        for line in lines[:5]:
            line = line.strip()
            if line and not line.startswith('-'):
                return line
        return "Unknown"
    
    def _extract_date(self, lines: List[str]) -> str:
        """Extract date from receipt"""
        for line in lines:
            match = self.DATE_PATTERN.search(line)
            if match:
                # Return in ISO format: YYYY-MM-DD HH:MM:SS
                return f"{match.group(1)}-{match.group(2)}-{match.group(3)} " \
                       f"{match.group(4)}:{match.group(5)}:{match.group(6)}"
        return datetime.now().isoformat()
    
    def _extract_card(self, lines: List[str]) -> str:
        """Extract last 4 digits of card"""
        for line in lines:
            if 'MASTERCARD' in line or 'VISA' in line or '*' in line:
                match = self.CARD_PATTERN.search(line)
                if match:
                    return match.group(1)
        return "0000"
    
    def _extract_total(self, lines: List[str]) -> float:
        """Extract total from receipt"""
        for line in lines:
            match = self.TOTAL_PATTERN.search(line)
            if match:
                return self._parse_float(match.group(1))
        return 0.0
    
    def _parse_items(self, lines: List[str]) -> List[ParsedItem]:
        """Parse all items from receipt lines"""
        items = []
        i = 0
        last_item = None
        
        while i < len(lines):
            line = lines[i].rstrip()
            
            # Skip separator lines and empty lines
            if not line or line.strip().startswith('-') or 'Totalt' in line:
                i += 1
                continue
            
            # Check for discount (indented or starts with "Rabatt:")
            if line.startswith(' ') and ('Rabatt:' in line or '-' in line):
                discount_match = self.DISCOUNT_PATTERN.match(line)
                if discount_match:
                    discount_name = discount_match.group(2).strip()
                    discount_amount = self._parse_float(discount_match.group(3))
                    
                    # Create a discount item linked to the previous item
                    discount_item = ParsedItem(
                        name=discount_name,
                        price=-discount_amount,
                        count=1,
                        raw=line,
                        is_discount=True,
                        discount_name=discount_name,
                        discount_amount=discount_amount
                    )
                    items.append(discount_item)
                    i += 1
                    continue
            
            # Check for item with count
            count_match = self.COUNT_PATTERN.match(line)
            if count_match:
                name = count_match.group(1).strip()
                count = int(count_match.group(2))
                total_price = self._parse_float(count_match.group(3))
                
                item = ParsedItem(
                    name=name,
                    price=total_price,
                    count=count,
                    raw=line
                )
                items.append(item)
                last_item = item
                i += 1
                continue
            
            # Check for weighted item (2 lines)
            if i + 1 < len(lines):
                next_line = lines[i + 1].rstrip()
                weight_match = self.WEIGHT_LINE2_PATTERN.match(next_line)
                
                if weight_match:
                    name = line.strip()
                    weight = self._parse_float(weight_match.group(1))
                    weight_unit = weight_match.group(2)
                    price_per_unit = self._parse_float(weight_match.group(3))
                    total_price = self._parse_float(weight_match.group(5))
                    
                    item = ParsedItem(
                        name=name,
                        price=total_price,
                        count=1,
                        raw=line + '\n' + next_line,
                        weight=weight,
                        price_per_unit=price_per_unit,
                        unit=weight_unit
                    )
                    items.append(item)
                    last_item = item
                    i += 2
                    continue
            
            # Check for standard item
            item_match = self.ITEM_PATTERN.match(line)
            if item_match:
                name = item_match.group(1).strip()
                price = self._parse_float(item_match.group(2))
                
                # Skip empty names or lines that aren't items
                if not name or any(skip in name for skip in ['Mottaget', 'KÖP', 'Butik', 
                                                   'Ref:', 'TVR:', 'Kontaktlös',
                                                   'Moms%', 'Poänggrundande',
                                                   'Medlemsnummer']):
                    i += 1
                    continue
                
                item = ParsedItem(
                    name=name,
                    price=price,
                    count=1,
                    raw=line
                )
                items.append(item)
                last_item = item
                i += 1
                continue
            
            i += 1
        
        return items
