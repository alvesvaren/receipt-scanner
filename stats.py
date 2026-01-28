#!/usr/bin/env python3
"""
Display statistics from the receipts database
"""
import argparse
import sqlite3
from typing import List, Tuple


def connect_db(db_path: str) -> sqlite3.Connection:
    """Connect to database"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def print_spending_by_category(conn: sqlite3.Connection):
    """Show spending breakdown by category"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.name, COUNT(i.id) as item_count, SUM(i.price) as total
        FROM Items i
        LEFT JOIN Categories c ON i.categoryId = c.id
        WHERE i.price > 0
        GROUP BY c.name
        ORDER BY total DESC
    """)
    
    print("\n" + "="*60)
    print("UTGIFTER PER KATEGORI")
    print("="*60)
    
    total = 0
    for row in cursor:
        category = row['name'] or 'Ingen kategori'
        count = row['item_count']
        amount = row['total']
        total += amount
        print(f"{category:20} {count:4} items  {amount:10.2f} SEK")
    
    print("-"*60)
    print(f"{'TOTALT':20}            {total:10.2f} SEK")
    print("="*60)


def print_receipts_summary(conn: sqlite3.Connection):
    """Show receipts summary"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as count, 
               SUM(total) as total,
               MIN(date) as first_date,
               MAX(date) as last_date
        FROM Receipts
    """)
    
    row = cursor.fetchone()
    
    print("\n" + "="*60)
    print("KVITTOÖVERSIKT")
    print("="*60)
    print(f"Antal kvitton: {row['count']}")
    print(f"Total utgift: {row['total']:.2f} SEK")
    print(f"Första kvitto: {row['first_date']}")
    print(f"Senaste kvitto: {row['last_date']}")
    print("="*60)


def print_monthly_spending(conn: sqlite3.Connection):
    """Show spending per month"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT strftime('%Y-%m', date) as month, 
               COUNT(*) as receipts, 
               SUM(total) as total_spent
        FROM Receipts
        GROUP BY month
        ORDER BY month DESC
    """)
    
    print("\n" + "="*60)
    print("UTGIFTER PER MÅNAD")
    print("="*60)
    print(f"{'Månad':12} {'Kvitton':>10} {'Totalt':>15}")
    print("-"*60)
    
    for row in cursor:
        print(f"{row['month']:12} {row['receipts']:10} {row['total_spent']:15.2f} SEK")
    
    print("="*60)


def print_top_items(conn: sqlite3.Connection, limit: int = 10):
    """Show most expensive items"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.name, i.price, c.name as category, r.date, SUM(i.price) - SUM(d.amount) as total
        FROM Items i
        LEFT JOIN Categories c ON i.categoryId = c.id
        LEFT JOIN Receipts r ON i.receiptId = r.id
        LEFT JOIN Discounts d ON i.id = d.id
        WHERE i.price > 0
        GROUP BY i.name
        ORDER BY total DESC
        LIMIT ?
    """, (limit,))
    
    print("\n" + "="*60)
    print(f"TOP {limit} DYRASTE ITEMS")
    print("="*60)
    
    for i, row in enumerate(cursor, 1):
        category = row['category'] or 'Ingen'
        print(f"{i:2}. {row['name']:30} {row['price']:8.2f} ({row['total']:.2f} SEK) ({category})")
    
    print("="*60)


def print_discounts_summary(conn: sqlite3.Connection):
    """Show discounts summary"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.name, d.amount, i.name as item_name, r.date
        FROM Discounts d
        JOIN Items i ON d.id = i.id
        JOIN Receipts r ON i.receiptId = r.id
        ORDER BY d.amount DESC
    """)
    
    rows = list(cursor)
    
    print("\n" + "="*60)
    print("RABATTER")
    print("="*60)
    
    if not rows:
        print("Inga rabatter hittades.")
    else:
        total_discount = 0
        for row in rows:
            total_discount += row['amount']
            print(f"{row['name']:30} -{row['amount']:7.2f} SEK")
        
        print("-"*60)
        print(f"{'TOTALT SPARAT':30} -{total_discount:7.2f} SEK")
    
    print("="*60)


def print_stores(conn: sqlite3.Connection):
    """Show spending per store"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT storeName, COUNT(*) as visits, SUM(total) as total_spent
        FROM Receipts
        GROUP BY storeName
        ORDER BY total_spent DESC
    """)
    
    print("\n" + "="*60)
    print("UTGIFTER PER BUTIK")
    print("="*60)
    
    for row in cursor:
        print(f"{row['storeName']:30} {row['visits']:3} besök  {row['total_spent']:10.2f} SEK")
    
    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Display statistics from receipts database"
    )
    parser.add_argument(
        '--db-path',
        default='receipts.db',
        help='Path to SQLite database (default: receipts.db)'
    )
    parser.add_argument(
        '--category', '-c',
        action='store_true',
        help='Show spending by category'
    )
    parser.add_argument(
        '--monthly', '-m',
        action='store_true',
        help='Show spending per month'
    )
    parser.add_argument(
        '--top', '-t',
        type=int,
        metavar='N',
        help='Show top N most expensive items'
    )
    parser.add_argument(
        '--discounts', '-d',
        action='store_true',
        help='Show discounts summary'
    )
    parser.add_argument(
        '--stores', '-s',
        action='store_true',
        help='Show spending per store'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Show all statistics'
    )
    
    args = parser.parse_args()
    
    # If no specific flag, show summary + categories
    if not any([args.category, args.monthly, args.top, args.discounts, 
                args.stores, args.all]):
        args.category = True
    
    try:
        conn = connect_db(args.db_path)
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        return 1
    
    try:
        # Always show receipts summary first
        print_receipts_summary(conn)
        
        if args.all or args.category:
            print_spending_by_category(conn)
        
        if args.all or args.monthly:
            print_monthly_spending(conn)
        
        if args.all or args.stores:
            print_stores(conn)
        
        if args.all or args.discounts:
            print_discounts_summary(conn)
        
        if args.top or args.all:
            limit = args.top if args.top else 10
            print_top_items(conn, limit)
    
    finally:
        conn.close()


if __name__ == '__main__':
    main()
