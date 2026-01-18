#!/usr/bin/env python3
"""
Export receipts data to CSV files
"""
import csv
import argparse
import sqlite3
from pathlib import Path


def export_items(conn: sqlite3.Connection, output_file: str):
    """Export all items to CSV"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            i.id,
            i.name,
            i.price,
            i.count,
            c.name as category,
            r.date as receipt_date,
            r.storeName as store,
            w.weight,
            w.pricePerUnit,
            w.unit
        FROM Items i
        LEFT JOIN Categories c ON i.categoryId = c.id
        LEFT JOIN Receipts r ON i.receiptId = r.id
        LEFT JOIN WeightedItems w ON i.id = w.id
        WHERE i.price > 0
        ORDER BY r.date DESC, i.id
    """)
    
    rows = cursor.fetchall()
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'ID', 'Produktnamn', 'Pris', 'Antal', 'Kategori', 
            'Datum', 'Butik', 'Vikt', 'Pris/enhet', 'Enhet'
        ])
        
        for row in rows:
            writer.writerow([
                row[0], row[1], row[2], row[3], row[4] or '',
                row[5], row[6], row[7] or '', row[8] or '', row[9] or ''
            ])
    
    print(f"Exported {len(rows)} items to {output_file}")


def export_receipts(conn: sqlite3.Connection, output_file: str):
    """Export all receipts to CSV"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            id,
            date,
            storeName,
            total,
            cardLast4,
            (SELECT COUNT(*) FROM Items WHERE receiptId = Receipts.id) as item_count
        FROM Receipts
        ORDER BY date DESC
    """)
    
    rows = cursor.fetchall()
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'ID', 'Datum', 'Butik', 'Totalt', 'Kortnummer', 'Antal items'
        ])
        
        for row in rows:
            writer.writerow(row)
    
    print(f"Exported {len(rows)} receipts to {output_file}")


def export_categories(conn: sqlite3.Connection, output_file: str):
    """Export spending by category to CSV"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            c.name as category,
            COUNT(i.id) as item_count,
            SUM(i.price) as total_spent
        FROM Items i
        LEFT JOIN Categories c ON i.categoryId = c.id
        WHERE i.price > 0
        GROUP BY c.name
        ORDER BY total_spent DESC
    """)
    
    rows = cursor.fetchall()
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Kategori', 'Antal items', 'Total utgift'])
        
        for row in rows:
            writer.writerow([row[0] or 'Ingen kategori', row[1], row[2]])
    
    print(f"Exported {len(rows)} categories to {output_file}")


def export_monthly(conn: sqlite3.Connection, output_file: str):
    """Export monthly spending to CSV"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            strftime('%Y-%m', date) as month,
            COUNT(*) as receipt_count,
            SUM(total) as total_spent
        FROM Receipts
        GROUP BY month
        ORDER BY month DESC
    """)
    
    rows = cursor.fetchall()
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Månad', 'Antal kvitton', 'Total utgift'])
        
        for row in rows:
            writer.writerow(row)
    
    print(f"Exported {len(rows)} months to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Export receipts data to CSV files"
    )
    parser.add_argument(
        '--db-path',
        default='receipts.db',
        help='Path to SQLite database (default: receipts.db)'
    )
    parser.add_argument(
        '--output-dir',
        default='exports',
        help='Output directory for CSV files (default: exports)'
    )
    parser.add_argument(
        '--items',
        action='store_true',
        help='Export items'
    )
    parser.add_argument(
        '--receipts',
        action='store_true',
        help='Export receipts'
    )
    parser.add_argument(
        '--categories',
        action='store_true',
        help='Export categories summary'
    )
    parser.add_argument(
        '--monthly',
        action='store_true',
        help='Export monthly summary'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Export everything'
    )
    
    args = parser.parse_args()
    
    # If no specific flag, export everything
    if not any([args.items, args.receipts, args.categories, args.monthly, args.all]):
        args.all = True
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    try:
        conn = sqlite3.connect(args.db_path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        return 1
    
    try:
        if args.all or args.items:
            export_items(conn, output_dir / 'items.csv')
        
        if args.all or args.receipts:
            export_receipts(conn, output_dir / 'receipts.csv')
        
        if args.all or args.categories:
            export_categories(conn, output_dir / 'categories.csv')
        
        if args.all or args.monthly:
            export_monthly(conn, output_dir / 'monthly.csv')
        
        print(f"\nExports completed successfully in {output_dir}/")
    
    finally:
        conn.close()


if __name__ == '__main__':
    main()
