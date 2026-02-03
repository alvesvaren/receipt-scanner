"""
Hemköp API Client

This module provides a Python client for interacting with the Hemköp (hemkop.se) API.
It handles authentication and provides methods to download digital receipts.

API Documentation:
==================

Base URL: https://www.hemkop.se

Authentication Flow:
1. The login uses encrypted credentials sent to POST /login
2. Credentials are encrypted using PBKDF2-derived AES-CBC:
   - Generate a 16-digit random numeric key
   - Generate two 16-byte random values: IV and salt
   - Derive AES key using PBKDF2(password=key, salt=salt, iterations=1000, hash=SHA-1)
   - Encrypt with AES-CBC using derived key and IV
   - Format: base64(hex(iv)::hex(salt)::base64(encrypted_data))
3. Session is maintained via JSESSIONID cookie

Key Endpoints:
- POST /login - Login with encrypted credentials
  Request body: {"j_username": "encrypted", "j_username_key": "key", 
                 "j_password": "encrypted", "j_password_key": "key", "j_remember_me": true}
                 
- GET /axfood/rest/customer - Get customer information
- GET /axfood/rest/csrf-token - Get CSRF token for POST requests
- GET /axfood/rest/cart - Get shopping cart

Purchase History & Receipts:
- GET /axfood/rest/account/recentCombinedOrderHistoryDates - Get list of dates with purchases
  Returns: {combinedOrderHistoryDates: ["YYYY-MM-DD", ...]}

- GET /axfood/rest/account/pagedOrderBonusCombined - Get paginated purchase history
  Query params: page, size, fromDate (YYYY-MM-DD), toDate (YYYY-MM-DD)
  Use fromDate/toDate to fetch receipts from all months; without them only recent data is returned.
  Returns: {loyaltyTransactionsInPage: [...], paginationData: {...}}
  
- GET /axfood/rest/order/orders/digitalreceipt/{receiptReference} - Download receipt PDF
  Query params: date (YYYY-MM-DD), storeId, memberCardNumber
  Returns: PDF file

Headers Required:
- Content-Type: application/json
- Cookie: JSESSIONID=xxx (managed automatically by session)

Usage:
------
    from hemkop_api import download_all_receipts
    
    result = download_all_receipts(
        username='200012121234',  # Personal number or member number
        password='your_password',
        path_to_download_folder='./receipts'
    )
"""

import requests
import json
import base64
import hashlib
import os
import random
import string
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote as url_quote
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad


class HemkopAPI:
    """
    A Python client for the Hemköp API.
    
    This class handles authentication and provides methods to interact with
    the Hemköp grocery store API, including downloading digital receipts.
    """
    
    BASE_URL = "https://www.hemkop.se"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,sv;q=0.8",
            "Origin": "https://www.hemkop.se",
            "Referer": "https://www.hemkop.se/",
        })
        self.customer_info = None
        self.csrf_token = None
    
    def _generate_key(self, length=16):
        """Generate a random 16-digit numeric encryption key."""
        return ''.join(random.choices(string.digits, k=length))
    
    def _encrypt_credential(self, value: str) -> tuple[str, str]:
        """
        Encrypt a credential using PBKDF2-derived AES-CBC.
        
        The Hemköp login uses this encryption flow:
        1. Generate a 16-digit random numeric key
        2. Generate two 16-byte random values: IV and salt
        3. Use PBKDF2(password=key, salt=salt, iterations=1000, hash=SHA-1) to derive AES key
        4. Encrypt the value with AES-CBC using derived key and IV
        5. Return: base64(hex(iv)::hex(salt)::base64(encrypted))
        
        Returns:
            tuple: (encrypted_value, key)
        """
        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Hash import SHA1
        
        # Generate random 16-digit key
        key = self._generate_key()
        
        # Generate random 16-byte IV and salt
        iv = os.urandom(16)
        salt = os.urandom(16)
        
        # Derive AES key using PBKDF2
        aes_key = PBKDF2(
            key.encode('utf-8'),
            salt,
            dkLen=16,  # 128 bits for AES-128
            count=1000,
            hmac_hash_module=SHA1
        )
        
        # Encrypt with AES-CBC
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        padded_data = pad(value.encode('utf-8'), AES.block_size)
        encrypted = cipher.encrypt(padded_data)
        
        # Format: hex(iv)::hex(salt)::base64(encrypted)
        inner = f"{iv.hex()}::{salt.hex()}::{base64.b64encode(encrypted).decode('utf-8')}"
        
        # Encode the whole thing as base64
        encrypted_value = base64.b64encode(inner.encode('utf-8')).decode('utf-8')
        
        return encrypted_value, key
    
    def _init_session(self):
        """Initialize session by visiting the homepage to get cookies."""
        response = self.session.get(f"{self.BASE_URL}/")
        return response.status_code == 200
    
    def login(self, username: str, password: str) -> bool:
        """
        Login to Hemköp with the given credentials.
        
        Args:
            username: Personal number (personnummer) or member number
            password: Account password
            
        Returns:
            bool: True if login successful, False otherwise
        """
        # Initialize session first
        self._init_session()
        
        # Encrypt credentials
        encrypted_username, username_key = self._encrypt_credential(username)
        encrypted_password, password_key = self._encrypt_credential(password)
        
        # Prepare login payload
        login_data = {
            "j_username": encrypted_username,
            "j_username_key": username_key,
            "j_password": encrypted_password,
            "j_password_key": password_key,
            "j_remember_me": True
        }
        
        # Send login request
        response = self.session.post(
            f"{self.BASE_URL}/login",
            json=login_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            # Verify login by getting customer info
            self.customer_info = self.get_customer()
            if self.customer_info and self.customer_info.get('uid') != 'anonymous':
                # Get CSRF token for subsequent requests
                self._get_csrf_token()
                return True
        
        return False
    
    def _get_csrf_token(self):
        """Get CSRF token for authenticated requests."""
        response = self.session.get(f"{self.BASE_URL}/axfood/rest/csrf-token")
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    self.csrf_token = data.get('token')
                else:
                    # Token might be returned as plain text
                    self.csrf_token = str(data) if data else None
            except:
                # Try to get as text if JSON parsing fails
                self.csrf_token = response.text.strip() if response.text else None
            
            # Update session headers with CSRF token
            if self.csrf_token:
                self.session.headers.update({
                    "X-CSRF-TOKEN": self.csrf_token
                })
    
    def get_customer(self) -> dict:
        """
        Get current customer information.
        
        Returns:
            dict: Customer information or None if not authenticated
        """
        response = self.session.get(f"{self.BASE_URL}/axfood/rest/customer")
        if response.status_code == 200:
            return response.json()
        return None
    
    def get_recent_order_dates(self) -> list[str]:
        """
        Get list of dates that have purchase history.
        Used to determine the date range for fetching all receipts.
        
        Returns:
            list: List of date strings (YYYY-MM-DD)
        """
        response = self.session.get(
            f"{self.BASE_URL}/axfood/rest/account/recentCombinedOrderHistoryDates"
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('combinedOrderHistoryDates', [])
        return []
    
    def get_purchase_history(
        self,
        page: int = 0,
        size: int = 100,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        """
        Get paginated purchase history (transactions/receipts).
        
        Args:
            page: Page number (0-indexed)
            size: Number of items per page
            from_date: Start date (YYYY-MM-DD). If not set, API may return only recent data.
            to_date: End date (YYYY-MM-DD). If not set, API may return only recent data.
            
        Returns:
            dict: Purchase history data with keys:
                - loyaltyTransactionsInPage: List of transactions
                - paginationData: Pagination info
                - totalDiscountCurrentYear: Total discounts
        """
        # API accepts both page/size and currentPage/pageSize (website uses currentPage/pageSize=9999)
        params = {"page": page, "size": size, "currentPage": page, "pageSize": size}
        if from_date:
            params["fromDate"] = from_date
        if to_date:
            params["toDate"] = to_date
        
        response = self.session.get(
            f"{self.BASE_URL}/axfood/rest/account/pagedOrderBonusCombined",
            params=params
        )
        
        if response.status_code == 200:
            return response.json()
        return {}
    
    def get_all_transactions(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list:
        """
        Get all transactions, optionally within a date range.
        
        The website shows receipts in chunks and "Visa fler" loads older date ranges.
        We request multiple ~4-month date ranges (like the website) and aggregate,
        so we get all receipts instead of hitting a per-request limit.
        
        Args:
            from_date: Start date (YYYY-MM-DD). Optional.
            to_date: End date (YYYY-MM-DD). Optional.
            
        Returns:
            list: List of all transactions (deduplicated by digitalReceiptReference).
        """
        if not from_date or not to_date:
            dates = self.get_recent_order_dates()
            if dates:
                from_date = from_date or min(dates)
                to_date = to_date or datetime.now().strftime('%Y-%m-%d')
            else:
                from_date = from_date or (datetime.now().replace(year=datetime.now().year - 2).strftime('%Y-%m-%d'))
                to_date = to_date or datetime.now().strftime('%Y-%m-%d')
        
        # Split into ~4-month chunks (like the website: initial range + "Visa fler" range)
        chunks = self._date_range_chunks(from_date, to_date, months_per_chunk=4)
        
        all_transactions = []
        seen_refs = set()
        
        for chunk_start, chunk_end in chunks:
            page = 0
            while True:
                data = self.get_purchase_history(
                    page=page,
                    size=9999,  # Request large page like the website (pageSize=9999)
                    from_date=chunk_start,
                    to_date=chunk_end,
                )
                transactions = data.get('loyaltyTransactionsInPage', [])
                
                if not transactions:
                    break
                
                for tx in transactions:
                    ref = tx.get('digitalReceiptReference')
                    if ref and ref not in seen_refs:
                        seen_refs.add(ref)
                        all_transactions.append(tx)
                    elif not ref:
                        all_transactions.append(tx)
                
                pagination = data.get('paginationData', {})
                total_pages = pagination.get('numberOfPages', 1)
                
                if page >= total_pages - 1:
                    break
                
                page += 1
        
        return all_transactions
    
    def _date_range_chunks(
        self,
        from_date: str,
        to_date: str,
        months_per_chunk: int = 4,
    ) -> list[tuple[str, str]]:
        """Split a date range into consecutive ~4-month chunks (like the website's "Visa fler")."""
        from calendar import monthrange
        
        start = datetime.strptime(from_date, '%Y-%m-%d')
        end = datetime.strptime(to_date, '%Y-%m-%d')
        chunks = []
        current_start = start
        
        while current_start <= end:
            year, month = current_start.year, current_start.month
            month += months_per_chunk
            if month > 12:
                month -= 12
                year += 1
            last_day = monthrange(year, month)[1]
            chunk_end = datetime(year, month, last_day)
            if chunk_end > end:
                chunk_end = end
            chunks.append((current_start.strftime('%Y-%m-%d'), chunk_end.strftime('%Y-%m-%d')))
            current_start = chunk_end + timedelta(days=1)
        
        return chunks
    
    def download_receipt_pdf(self, transaction: dict, output_path: str) -> bool:
        """
        Download a receipt as PDF.
        
        Passes the transaction's receiptSource (e.g. "aws" or "axcrm") as the
        source query parameter so the server returns the full PDF content.
        
        Args:
            transaction: Transaction data containing digitalReceiptReference,
                        bookingDate, storeCustomerId, memberCardNumber
            output_path: Path to save the PDF
            
        Returns:
            bool: True if download successful, False otherwise
        """
        receipt_ref = transaction.get('digitalReceiptReference')
        if not receipt_ref:
            return False
        
        if not transaction.get('digitalReceiptAvailable', False):
            return False
        
        # Extract required parameters
        booking_date_ms = transaction.get('bookingDate')
        store_id = transaction.get('storeCustomerId')
        member_card = transaction.get('memberCardNumber')
        
        if not all([booking_date_ms, store_id, member_card]):
            return False
        
        # Convert timestamp to date string (YYYY-MM-DD)
        date_str = datetime.fromtimestamp(booking_date_ms / 1000).strftime('%Y-%m-%d')
        
        # URL-encode reference (contains : and + in aws-style refs like 2025-12-28T15:24:46.758+01:00-4504-3-0)
        ref_encoded = url_quote(receipt_ref, safe='')
        url = f"{self.BASE_URL}/axfood/rest/order/orders/digitalreceipt/{ref_encoded}"
        params = {
            'date': date_str,
            'storeId': store_id,
            'memberCardNumber': member_card
        }
        # The website passes source=aws for aws receipts; without it the API returns a blank PDF
        receipt_source = transaction.get('receiptSource')
        if receipt_source:
            params['source'] = receipt_source

        response = self.session.get(url, params=params, stream=True)
        
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        return False


def download_all_receipts(username: str, password: str, path_to_download_folder: str) -> dict:
    """
    Download all receipts for a Hemköp user.
    
    Args:
        username: Personal number (personnummer) or member number
        password: Account password
        path_to_download_folder: Path to the folder where receipts will be saved
        
    Returns:
        dict: Summary of download results with keys:
            - 'success': bool - Whether the operation was successful
            - 'total_receipts': int - Total number of receipts found
            - 'downloaded': int - Number of receipts successfully downloaded
            - 'failed': int - Number of receipts that failed to download
            - 'receipts': list - List of receipt metadata
            - 'errors': list - List of error messages
    """
    result = {
        'success': False,
        'total_receipts': 0,
        'downloaded': 0,
        'failed': 0,
        'receipts': [],
        'errors': []
    }
    
    # Create download folder if it doesn't exist
    download_path = Path(path_to_download_folder)
    download_path.mkdir(parents=True, exist_ok=True)
    
    # Create API client and login
    api = HemkopAPI()
    
    print(f"Logging in as {username}...")
    if not api.login(username, password):
        result['errors'].append("Login failed. Please check your credentials.")
        return result
    
    print(f"Logged in successfully as {api.customer_info.get('firstName', 'Unknown')} {api.customer_info.get('lastName', '')}")
    
    # Get all transactions (purchases)
    print("Fetching purchase history...")
    all_transactions = api.get_all_transactions()
    
    # Filter to only transactions with digital receipts available
    receipts_available = [tx for tx in all_transactions if tx.get('digitalReceiptAvailable', False)]
    
    result['total_receipts'] = len(receipts_available)
    print(f"Found {len(all_transactions)} transactions, {len(receipts_available)} with digital receipts available")
    
    # Download each receipt
    for i, tx in enumerate(receipts_available):
        # Create filename based on date and store
        booking_date_ms = tx.get('bookingDate')
        if booking_date_ms:
            date_obj = datetime.fromtimestamp(booking_date_ms / 1000)
            date_str = date_obj.strftime('%Y-%m-%d_%H%M')
        else:
            date_str = 'unknown'
        
        store_name = tx.get('storeName', 'unknown')
        store_name = store_name.replace(' ', '_').replace('/', '-').replace('ö', 'o').replace('ä', 'a').replace('å', 'a')[:30]
        
        receipt_ref = tx.get('digitalReceiptReference', tx.get('orderNumber', f'tx_{i}'))
        
        # Save transaction metadata as JSON
        json_filename = f"receipt_{date_str}_{store_name}_{receipt_ref[:12]}.json"
        json_filepath = download_path / json_filename
        
        try:
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(tx, f, indent=2, ensure_ascii=False)
            result['receipts'].append(tx)
        except Exception as e:
            result['errors'].append(f"Failed to save {json_filename}: {str(e)}")
        
        # Download PDF
        pdf_filename = f"receipt_{date_str}_{store_name}_{receipt_ref[:12]}.pdf"
        pdf_filepath = download_path / pdf_filename
        
        try:
            if api.download_receipt_pdf(tx, str(pdf_filepath)):
                print(f"Downloaded: {pdf_filename}")
                result['downloaded'] += 1
            else:
                result['errors'].append(f"Failed to download PDF for {date_str} at {store_name}")
                result['failed'] += 1
        except Exception as e:
            result['errors'].append(f"Error downloading {pdf_filename}: {str(e)}")
            result['failed'] += 1
    
    result['success'] = result['downloaded'] > 0 or result['total_receipts'] == 0
    
    # Print summary
    print(f"\n=== Download Summary ===")
    print(f"Total transactions: {len(all_transactions)}")
    print(f"Receipts with digital available: {result['total_receipts']}")
    print(f"Successfully downloaded PDFs: {result['downloaded']}")
    print(f"Failed: {result['failed']}")
    
    if result['errors']:
        print(f"\nErrors:")
        for error in result['errors'][:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(result['errors']) > 10:
            print(f"  ... and {len(result['errors']) - 10} more errors")
    
    return result


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python hemkop_api.py <username> <password> <download_folder>")
        print("\nExample:")
        print("  python hemkop_api.py 201212121212 'mypassword' ./receipts")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    download_folder = sys.argv[3]
    
    result = download_all_receipts(username, password, download_folder)
    
    sys.exit(0 if result['success'] else 1)
