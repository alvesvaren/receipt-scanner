# Receipt Scanner

Ett Python-script för att processa kvitton från PDF-filer, extrahera items och priser, och lagra informationen i en SQLite-databas. Använder lokal Ollama för automatisk kategorisering av produkter.

## Funktioner

- 📄 Läser kvitton i PDF-format
- 🔍 Parsear ut items, priser, antal och vikter
- 💰 Identifierar rabatter och kopplar dem till rätt items
- 🗄️ Sparar allt i en strukturerad SQLite-databas
- 🤖 Automatisk kategorisering med Ollama (med caching)
- ♻️ Intelligent caching - samma produktnamn behöver bara kategoriseras en gång

## Databasschema

### Tables

**Categories**
- `id` (PRIMARY KEY)
- `name` (UNIQUE)

**Receipts**
- `id` (PRIMARY KEY)
- `total` - Total summa
- `date` - Datum och tid
- `storeName` - Butiksnamn
- `cardLast4` - Sista 4 siffror på kortet
- `raw` - Rå kvittots text

**Items**
- `id` (PRIMARY KEY)
- `price` - Pris
- `name` - Produktnamn
- `receiptId` -> Receipts.id
- `count` - Antal (default: 1)
- `raw` - Rå textraden

**WeightedItems** (för viktbaserade produkter)
- `id` (PRIMARY KEY) -> Items.id
- `weight` - Vikt
- `pricePerUnit` - Pris per enhet
- `unit` - Enhet (kg, g, st)
- `raw` - Rå textraden

**Discounts**
- `id` (PRIMARY KEY) -> Items.id
- `amount` - Rabattbelopp
- `name` - Rabattnamn
- `raw` - Rå textraden

**CategoriesForItemNames** (cache för kategorisering)
- `name` (PRIMARY KEY) - Produktnamn
- `categoryId` -> Categories.id (source of truth för kategori per produktnamn)

## Installation

### 1. Installera systempaket

För PDF-extraktion behöver du `poppler-utils`:

```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils

# macOS
brew install poppler

# Fedora
sudo dnf install poppler-utils
```

### 2. Installera Python-paket

```bash
pip install -r requirements.txt
```

### 3. Starta Ollama

Se till att din lokala Ollama-instans körs:

```bash
# Kontrollera att Ollama körs på rätt port
curl http://127.0.0.1:11434/api/tags
```

Modellen som används: `gemma3:12b-it-qat`

Om modellen inte finns:
```bash
ollama pull gemma3:12b-it-qat
```

## Användning

### Processa alla kvitton

```bash
python process_receipts.py
```

### Processa med verbose output

```bash
python process_receipts.py --verbose
```

### Processa en specifik fil

```bash
python process_receipts.py --file receipts/2025-09-24T15_53_57.pdf --verbose
```

### Ange annan databas eller kvittomapp

```bash
python process_receipts.py --receipts-dir /path/to/receipts --db-path myreceipts.db
```

## Kategorier

Systemet använder följande fördefinierade kategorier:

- **mejeri** - Mejeriprodukter
- **kött & chark** - Kött och charkuterier
- **fisk & skaldjur** - Fisk och skaldjur
- **frukt & grönt** - Frukt och grönsaker
- **bröd & bakverk** - Bröd och bakverk
- **konserver** - Konserver
- **pasta & ris** - Pasta och ris
- **snacks** - Snacks
- **godis & choklad** - Godis och choklad
- **drycker** - Drycker
- **kryddor & såser** - Kryddor och såser
- **fryst** - Frysta varor
- **hygien** - Personlig hygien
- **hushåll** - Hushållsprodukter
- **veganskt** - Veganska produkter
- **övrigt** - Övrigt

## Konfiguration

Ollama-konfigurationen finns i `categorizer.py`:

```python
OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
OLLAMA_MODEL = "gemma3:12b-it-qat"
```

## Hur det fungerar

1. **PDF-extraktion**: Använder `pdftotext` för att extrahera text från PDF:er
2. **Parsing**: Identifierar items, priser, rabatter, och metadata med regex-patterns
3. **Kategorisering**: 
   - Kollar först i cache (CategoriesForItemNames)
   - Om inte i cache: frågar Ollama
   - Cachar resultatet för framtida användning
4. **Lagring**: Sparar allt i SQLite-databasen

## Visa statistik

### Grundläggande statistik

```bash
# Visa översikt och utgifter per kategori
python stats.py

# Visa all statistik
python stats.py --all

# Visa utgifter per månad
python stats.py --monthly

# Visa top 20 dyraste items
python stats.py --top 20

# Visa rabatter
python stats.py --discounts

# Visa utgifter per butik
python stats.py --stores
```

### Flaggor för stats.py

- `-c, --category` - Visa utgifter per kategori
- `-m, --monthly` - Visa utgifter per månad
- `-t N, --top N` - Visa top N dyraste items
- `-d, --discounts` - Visa rabatter
- `-s, --stores` - Visa utgifter per butik
- `-a, --all` - Visa all statistik

## Manuell korrigering av kategorier

Om Ollama kategoriserar något fel kan du korrigera det direkt i databasen:

```bash
sqlite3 receipts.db

-- Se alla kategorier
SELECT * FROM Categories;

-- Uppdatera kategorimappningen (påverkar statistik/export och framtida kvitton)
UPDATE CategoriesForItemNames SET categoryId = 1 WHERE name = 'PORT SALUT 26%';

-- Exempel: Hitta mejeri-kategorins ID
SELECT id FROM Categories WHERE name = 'mejeri';  -- t.ex. 1

-- Uppdatera alla "MELLANROST" till drycker-kategorin
UPDATE CategoriesForItemNames SET categoryId = (SELECT id FROM Categories WHERE name = 'drycker')
WHERE name LIKE 'MELLANROST%';
```

## Exempel på SQL-queries

```sql
-- Totalt spenderat per kategori
SELECT c.name, SUM(i.price) as total
FROM Items i
JOIN CategoriesForItemNames cin ON i.name = cin.name
JOIN Categories c ON cin.categoryId = c.id
GROUP BY c.name
ORDER BY total DESC;

-- Items med rabatter
SELECT i.name, i.price, d.amount as discount
FROM Items i
JOIN Discounts d ON i.id = d.id;

-- Viktbaserade produkter
SELECT i.name, w.weight, w.unit, w.pricePerUnit, i.price
FROM Items i
JOIN WeightedItems w ON i.id = w.id;

-- Kvitton per månad
SELECT strftime('%Y-%m', date) as month, COUNT(*) as receipts, SUM(total) as total_spent
FROM Receipts
GROUP BY month
ORDER BY month DESC;

-- Alla items från en specifik butik
SELECT i.name, i.price, c.name as category
FROM Items i
JOIN Receipts r ON i.receiptId = r.id
LEFT JOIN CategoriesForItemNames cin ON i.name = cin.name
LEFT JOIN Categories c ON cin.categoryId = c.id
WHERE r.storeName LIKE '%GULDHEDEN%'
ORDER BY i.price DESC;
```

## Förbättringsförslag

Några möjliga förbättringar:

1. **Bättre felhantering**: Logga fel till fil istället för bara print
2. **Batch-processing**: Skicka flera items till Ollama på en gång
3. **GUI**: Ett enkelt webgränssnitt för att se statistik
4. **Export**: Exportera till CSV/Excel
5. **Manuell korrigering**: Möjlighet att manuellt korrigera kategorier
6. **Duplicate detection**: Mer sofistikerad dubblettdetektering
7. **OCR support**: Stöd för skannade bilder (inte bara PDF med text)


## Disclaimer

Detta projekt är "personal software" som jag delat med mig av om något eventuellt har samma idé som mig. Projektet är vibe-codeat med min guidning till att skapa ett enkelt sätt att på detaljnivå hålla bra koll på vad jag spenderar pengar på utan att det tar extra tid för mig.
