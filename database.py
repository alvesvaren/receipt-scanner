"""
Database schema and operations for receipt scanner
"""
import sqlite3
from typing import Optional, Dict, Any
from contextlib import contextmanager


class Database:
    def __init__(self, db_path: str = "receipts.db"):
        self.db_path = db_path
        self._init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Categories table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
            """)
            
            # Receipts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total REAL NOT NULL,
                    date TEXT NOT NULL,
                    storeName TEXT,
                    cardLast4 TEXT,
                    raw TEXT NOT NULL
                )
            """)
            
            # Items table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    price REAL NOT NULL,
                    name TEXT NOT NULL,
                    receiptId INTEGER NOT NULL,
                    categoryId INTEGER,
                    count INTEGER DEFAULT 1,
                    raw TEXT NOT NULL,
                    FOREIGN KEY (receiptId) REFERENCES Receipts(id),
                    FOREIGN KEY (categoryId) REFERENCES Categories(id)
                )
            """)
            
            # WeightedItems table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS WeightedItems (
                    id INTEGER PRIMARY KEY,
                    weight REAL NOT NULL,
                    pricePerUnit REAL NOT NULL,
                    unit TEXT NOT NULL,
                    raw TEXT NOT NULL,
                    FOREIGN KEY (id) REFERENCES Items(id)
                )
            """)
            
            # Discounts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Discounts (
                    id INTEGER PRIMARY KEY,
                    amount REAL NOT NULL,
                    name TEXT NOT NULL,
                    raw TEXT NOT NULL,
                    FOREIGN KEY (id) REFERENCES Items(id)
                )
            """)
            
            # CategoriesForItemNames - cache for item name -> category mapping
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS CategoriesForItemNames (
                    name TEXT PRIMARY KEY,
                    categoryId INTEGER NOT NULL,
                    FOREIGN KEY (categoryId) REFERENCES Categories(id)
                )
            """)
            
    
    def get_or_create_category(self, name: str) -> int:
        """Get existing category or create new one"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Categories WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return row[0]
            cursor.execute("INSERT INTO Categories (name) VALUES (?)", (name,))
            return cursor.lastrowid
    
    def get_cached_category(self, item_name: str) -> Optional[int]:
        """Get cached category for an item name"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT categoryId FROM CategoriesForItemNames WHERE name = ?",
                (item_name,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    
    def cache_category_for_item_name(self, item_name: str, category_id: int):
        """Cache category for an item name"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO CategoriesForItemNames (name, categoryId) 
                   VALUES (?, ?)""",
                (item_name, category_id)
            )
    
    def insert_receipt(self, total: float, date: str, store_name: str, 
                      card_last4: str, raw: str) -> int:
        """Insert a receipt and return its id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO Receipts (total, date, storeName, cardLast4, raw)
                   VALUES (?, ?, ?, ?, ?)""",
                (total, date, store_name, card_last4, raw)
            )
            return cursor.lastrowid
    
    def insert_item(self, price: float, name: str, receipt_id: int,
                   category_id: Optional[int], count: int, raw: str) -> int:
        """Insert an item and return its id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO Items (price, name, receiptId, categoryId, count, raw)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (price, name, receipt_id, category_id, count, raw)
            )
            return cursor.lastrowid
    
    def insert_weighted_item(self, item_id: int, weight: float, 
                           price_per_unit: float, unit: str, raw: str):
        """Insert weighted item details"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO WeightedItems (id, weight, pricePerUnit, unit, raw)
                   VALUES (?, ?, ?, ?, ?)""",
                (item_id, weight, price_per_unit, unit, raw)
            )
    
    def insert_discount(self, item_id: int, amount: float, name: str, raw: str):
        """Insert a discount"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO Discounts (id, amount, name, raw)
                   VALUES (?, ?, ?, ?)""",
                (item_id, amount, name, raw)
            )
    
    def receipt_exists(self, date: str, total: float) -> bool:
        """Check if a receipt already exists (to avoid duplicates)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM Receipts WHERE date = ? AND total = ?",
                (date, total)
            )
            return cursor.fetchone() is not None
