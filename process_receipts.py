#!/usr/bin/env python3
"""
Main script to process receipts from PDFs and store in database
"""
import os
import sys
import subprocess
from pathlib import Path
from typing import List
import argparse

from database import Database
from parser import ReceiptParser, ParsedReceipt
from categorizer import Categorizer


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using pdftotext"""
    try:
        result = subprocess.run(
            ['pdftotext', '-layout', pdf_path, '-'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""
    except FileNotFoundError:
        print("Error: pdftotext not found. Please install poppler-utils.")
        sys.exit(1)


def process_receipt_file(pdf_path: str, database: Database, parser: ReceiptParser,
                        categorizer: Categorizer, verbose: bool = False) -> bool:
    """
    Process a single receipt PDF file.
    Returns True if successful, False otherwise.
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"Processing: {pdf_path}")
        print('='*60)
    
    # Extract text from PDF
    text = extract_text_from_pdf(pdf_path)
    if not text:
        print(f"Failed to extract text from {pdf_path}")
        return False
    
    # Parse receipt
    try:
        receipt = parser.parse_receipt_text(text)
    except Exception as e:
        print(f"Error parsing {pdf_path}: {e}")
        return False
    
    if verbose:
        print(f"Store: {receipt.store_name}")
        print(f"Date: {receipt.date}")
        print(f"Total: {receipt.total:.2f} SEK")
        print(f"Items: {len(receipt.items)}")
    
    # Check if receipt already exists
    if database.receipt_exists(receipt.date, receipt.total):
        if verbose:
            print("Receipt already in database, skipping...")
        return True
    
    # Insert receipt into database
    receipt_id = database.insert_receipt(
        total=receipt.total,
        date=receipt.date,
        store_name=receipt.store_name,
        card_last4=receipt.card_last4,
        raw=receipt.raw
    )
    
    if verbose:
        print(f"\nCategorizing items...")
    
    # Categorize all items
    categorizer.categorize_all_items_in_receipt(receipt.items, verbose=verbose)
    
    # Process items
    if verbose:
        print(f"\nInserting items into database...")
    
    last_item_id = None
    for i, item in enumerate(receipt.items):
        # Skip discount items - they will be attached to previous item
        if item.is_discount:
            if last_item_id is not None:
                database.insert_discount(
                    item_id=last_item_id,
                    amount=item.discount_amount,
                    name=item.discount_name,
                    raw=item.raw
                )
                if verbose:
                    print(f"    └─ Rabatt: {item.discount_name} -{item.discount_amount:.2f} SEK")
            else:
                if verbose:
                    print(f"  Warning: Discount without previous item: {item.discount_name}")
            continue
        
        if verbose:
            print(f"  - {item.name}: {item.price:.2f} SEK")
        
        # Insert item
        item_id = database.insert_item(
            price=item.price,
            name=item.name,
            receipt_id=receipt_id,
            count=item.count,
            raw=item.raw
        )
        last_item_id = item_id
        
        # If it's a weighted item, add weight details
        if item.weight is not None:
            database.insert_weighted_item(
                item_id=item_id,
                weight=item.weight,
                price_per_unit=item.price_per_unit,
                unit=item.unit,
                raw=item.raw
            )
    
    if verbose:
        print(f"\n✓ Successfully processed {pdf_path}")
    
    return True


def get_receipt_files(receipts_dir: str) -> List[str]:
    """Get all PDF files from receipts directory, sorted by name"""
    receipts_path = Path(receipts_dir)
    if not receipts_path.exists():
        print(f"Error: Directory {receipts_dir} does not exist")
        return []
    
    pdf_files = sorted(receipts_path.glob("*.pdf"))
    return [str(f) for f in pdf_files]


def main():
    parser = argparse.ArgumentParser(
        description="Process receipt PDFs and store in database"
    )
    parser.add_argument(
        '--receipts-dir',
        default='receipts',
        help='Directory containing receipt PDFs (default: receipts)'
    )
    parser.add_argument(
        '--db-path',
        default='receipts.db',
        help='Path to SQLite database (default: receipts.db)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--file',
        help='Process a single receipt file instead of all files'
    )
    
    args = parser.parse_args()
    
    # Initialize components
    print("Initializing database...")
    database = Database(args.db_path)
    
    print("Initializing parser...")
    receipt_parser = ReceiptParser()
    
    print("Initializing categorizer...")
    categorizer = Categorizer(database)
    
    # Get files to process
    if args.file:
        files = [args.file]
    else:
        files = get_receipt_files(args.receipts_dir)
    
    if not files:
        print("No receipt files found.")
        return
    
    print(f"\nFound {len(files)} receipt(s) to process\n")
    
    # Process each file
    success_count = 0
    error_count = 0
    
    for pdf_file in files:
        # Check if already exists before processing
        text = extract_text_from_pdf(pdf_file)
        if text:
            try:
                parsed = receipt_parser.parse_receipt_text(text)
                if database.receipt_exists(parsed.date, parsed.total):
                    if not args.verbose:
                        print(f"Skipping (already in DB): {pdf_file}")
                    continue
            except Exception:
                pass  # Will be handled in process_receipt_file
        
        if process_receipt_file(pdf_file, database, receipt_parser, 
                               categorizer, verbose=args.verbose):
            success_count += 1
        else:
            error_count += 1
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total files: {len(files)}")
    print(f"Successfully processed: {success_count}")
    print(f"Errors: {error_count}")
    print("="*60)


if __name__ == '__main__':
    main()
