"""
Item categorizer using local Ollama instance
"""
import requests
import json
from typing import Optional
from database import Database


# Ollama configuration
OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
OLLAMA_MODEL = "gemma3:12b-it-qat"


# Predefined categories
CATEGORIES = [
    "mejeri",           # Dairy products (ost, mjölk, yoghurt, etc)
    "kött & chark",     # Meat & cold cuts
    "fisk & skaldjur",  # Fish & seafood
    "frukt & grönt",    # Fruit & vegetables
    "bröd & bakverk",   # Bread & bakery
    "konserver",        # Canned goods
    "pasta & ris",      # Pasta & rice
    "snacks",           # Snacks
    "godis & choklad",  # Candy & chocolate
    "drycker",          # Beverages (kaffe, te, juice, etc)
    "kryddor & såser",  # Spices & sauces
    "fryst",            # Frozen foods
    "hygien",           # Personal hygiene
    "hushåll",          # Household items
    "veganskt",         # Vegan products
    "övrigt"            # Other
]


class Categorizer:
    def __init__(self, database: Database):
        self.database = database
        self.ollama_url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/generate"
        
        # Initialize categories in database
        self._init_categories()
    
    def _init_categories(self):
        """Initialize all predefined categories in database"""
        for category in CATEGORIES:
            self.database.get_or_create_category(category)
        # Also create "unknown" category for failed categorizations
        self.database.get_or_create_category("unknown")
    
    def _call_ollama(self, item_name: str) -> Optional[str]:
        """Call Ollama to categorize an item"""
        prompt = f"""Du är en AI som kategoriserar matvaror och hushållsprodukter från kvitton.

Produktnamn: {item_name}

Välj EN kategori från följande lista:
- mejeri (ost, mjölk, yoghurt, smör, grädde, etc)
- kött & chark (kött, korv, skinka, etc)
- fisk & skaldjur
- frukt & grönt (grönsaker, sallad, frukt)
- bröd & bakverk
- konserver (burkar, konserver)
- pasta & ris
- snacks (chips, nötter, etc)
- godis & choklad
- drycker (kaffe, te, juice, läsk, mjölk, etc)
- kryddor & såser (kryddor, senap, ketchup, etc)
- fryst (frysta varor)
- hygien (tandkräm, schampo, etc)
- hushåll (rengöring, pappersprodukter, plastpåsar, etc)
- veganskt (veganska specialprodukter)
- övrigt

Svara ENDAST med kategorins namn, inget annat. Till exempel: "mejeri" eller "snacks".

Kategori:"""
        
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temperature for consistent results
                        "num_predict": 20     # We only need one word
                    }
                },
                timeout=100
            )
            
            if response.status_code == 200:
                result = response.json()
                category = result.get("response", "").strip().lower()
                
                # Clean up the response - sometimes the model adds extra text
                # Only accept exact matches from our predefined categories
                category_clean = category.strip().lower()
                for cat in CATEGORIES:
                    if cat == category_clean or cat in category_clean:
                        return cat
                
                # If no match from our list, default to "unknown"
                print(f"Warning: Ollama returned unknown category '{category}', using 'unknown'")
                return "unknown"
            else:
                print(f"Ollama error: {response.status_code}")
                return "övrigt"
        
        except requests.exceptions.RequestException as e:
            print(f"Failed to connect to Ollama: {e}")
            return "unknown"
        except Exception as e:
            print(f"Error calling Ollama: {e}")
            return "unknown"
    
    def categorize_item(self, item_name: str, verbose: bool = False) -> int:
        """
        Categorize an item and return the category ID.
        Uses cache if available, otherwise calls Ollama.
        """
        # Check cache first
        cached_category_id = self.database.get_cached_category(item_name)
        if cached_category_id is not None:
            if verbose:
                print(f"  [{item_name}] -> cached category ID: {cached_category_id}")
            return cached_category_id
        
        # Not in cache, call Ollama
        if verbose:
            print(f"  [{item_name}] -> calling Ollama...")
        
        category_name = self._call_ollama(item_name)
        
        # Get or create category ID
        category_id = self.database.get_or_create_category(category_name)
        
        # Cache the result
        self.database.cache_category_for_item_name(item_name, category_id)
        
        if verbose:
            print(f"  [{item_name}] -> {category_name} (ID: {category_id})")
        
        return category_id
    
    def categorize_all_items_in_receipt(self, items: list, verbose: bool = False) -> dict:
        """
        Categorize all items in a receipt.
        Returns a mapping of item index to category ID.
        """
        categories = {}
        
        for i, item in enumerate(items):
            # Skip discount items - they don't need categories
            if item.is_discount:
                categories[i] = None
            else:
                categories[i] = self.categorize_item(item.name, verbose=verbose)
        
        return categories
