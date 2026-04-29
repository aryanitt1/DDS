"""
Microtek Scanner Scraper
Scrapes product information and specifications from businessdigitalmachines.co.uk
Saves checkpoints every 2 products and final output as JSON

FIXES:
  - Variant pricing: WooCommerce products with .woovr-variation[data-pricehtml] 
    (e.g. ScanMaker 9800XL Plus) now captured as a 'variants' list instead of null.
  - Chrome runs in visible (non-headless) mode so you can watch it scrape live.
"""

import json
import os
import time
import re
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
try:
    import PyPDF2
except ImportError:
    # pypdf is the modern successor to PyPDF2; create a shim so existing code works
    import types as _types
    from pypdf import PdfReader as _PdfReader
    PyPDF2 = _types.SimpleNamespace(PdfReader=_PdfReader)
from io import BytesIO

# Configuration
BASE_URL = "https://businessdigitalmachines.co.uk"
MAIN_PAGE = f"{BASE_URL}/microtek-scanners/"
CHECKPOINT_FILE = "checkpoint.json"
OUTPUT_FILE = "microtek_scanners_output.json"
PDF_DOWNLOAD_DIR = "downloaded_pdfs"
CHECKPOINT_INTERVAL = 2  # Save checkpoint every 2 products

# Create PDF download directory
os.makedirs(PDF_DOWNLOAD_DIR, exist_ok=True)


class MicrotekScraper:
    def __init__(self):
        self.driver = None
        self.products_data = []
        self.checkpoint_data = {
            "last_processed_index": -1,
            "total_products": 0,
            "products_scraped": [],
            "timestamp": None
        }
        self.setup_driver()
        
    def setup_driver(self):
        """Initialize Selenium WebDriver with Chrome (visible window so you can watch)"""
        chrome_options = Options()
        # ✅ REMOVED: --headless  →  Chrome now opens visibly so you can see every page load
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1400,900')
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        print("✓ WebDriver initialized (visible window)")
    
    def load_checkpoint(self):
        """Load checkpoint data if exists"""
        if os.path.exists(CHECKPOINT_FILE):
            try:
                with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                    self.checkpoint_data = json.load(f)
                print(f"✓ Loaded checkpoint: {self.checkpoint_data['last_processed_index'] + 1} products already scraped")
                return True
            except Exception as e:
                print(f"⚠ Error loading checkpoint: {e}")
                return False
        return False
    
    def save_checkpoint(self, index, product_data):
        """Save checkpoint after every 2 products"""
        self.checkpoint_data["last_processed_index"] = index
        self.checkpoint_data["products_scraped"].append(product_data)
        self.checkpoint_data["timestamp"] = datetime.now().isoformat()
        
        try:
            with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.checkpoint_data, f, indent=2, ensure_ascii=False)
            print(f"✓ Checkpoint saved at product {index + 1}")
        except Exception as e:
            print(f"✗ Error saving checkpoint: {e}")
    
    def get_product_links(self):
        """Extract all Microtek scanner product links from main page"""
        print(f"\n📡 Fetching product links from: {MAIN_PAGE}")
        
        try:
            self.driver.get(MAIN_PAGE)
            time.sleep(3)  # Wait for page to load
            
            # Get page source and parse with BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            product_links = []
            seen_urls = set()
            
            # Exclusion list - URLs to skip (navigation, software, accessories, etc.)
            exclude_patterns = [
                '/software/',
                '/smartfix',
                '/product-category/',
                '/brand/',
                '/contact',
                '/about',
                'nextimage',
                'scanwizard',
                'silverfast',
                'leasing',
                'installation',
                'training'
            ]
            
            print("\n🔍 Scanning page for product links...")
            
            # Method 1: Find images that link to products (most reliable for product cards)
            for img in soup.find_all('img'):
                parent_link = img.find_parent('a', href=True)
                if parent_link:
                    href = parent_link.get('href', '')
                    if '/product/' in href:
                        if any(exclude in href.lower() for exclude in exclude_patterns):
                            continue
                        full_url = urljoin(BASE_URL, href)
                        clean_url = full_url.split('?')[0].split('#')[0]
                        if clean_url not in seen_urls:
                            seen_urls.add(clean_url)
                            product_links.append(clean_url)
                            product_slug = clean_url.split('/product/')[-1].rstrip('/')
                            print(f"  ✓ Found: {product_slug}")
            
            # Method 2: Find product links in headings (h2, h3, h4)
            for heading in soup.find_all(['h2', 'h3', 'h4']):
                link = heading.find('a', href=True)
                if link:
                    href = link.get('href', '')
                    if '/product/' in href:
                        if any(exclude in href.lower() for exclude in exclude_patterns):
                            continue
                        full_url = urljoin(BASE_URL, href)
                        clean_url = full_url.split('?')[0].split('#')[0]
                        if clean_url not in seen_urls:
                            seen_urls.add(clean_url)
                            product_links.append(clean_url)
                            product_slug = clean_url.split('/product/')[-1].rstrip('/')
                            print(f"  ✓ Found: {product_slug}")
            
            # Method 3: Find product links with price information nearby
            price_containers = soup.find_all(['div', 'p'], class_=re.compile(r'price|product'))
            for container in price_containers:
                links = container.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    if '/product/' in href:
                        if any(exclude in href.lower() for exclude in exclude_patterns):
                            continue
                        full_url = urljoin(BASE_URL, href)
                        clean_url = full_url.split('?')[0].split('#')[0]
                        if clean_url not in seen_urls:
                            seen_urls.add(clean_url)
                            product_links.append(clean_url)
                            product_slug = clean_url.split('/product/')[-1].rstrip('/')
                            print(f"  ✓ Found: {product_slug}")
            
            print(f"\n✅ Found {len(product_links)} Microtek scanner products")
            
            if product_links:
                print(f"\n📋 Products to scrape:")
                for i, url in enumerate(product_links):
                    product_name = url.split('/product/')[-1].rstrip('/')
                    print(f"  {i+1}. {product_name}")
            else:
                print("\n⚠ No products found! The page structure may have changed.")
            
            return product_links
            
        except Exception as e:
            print(f"✗ Error fetching product links: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def download_pdf(self, pdf_url, product_name):
        """Download PDF datasheet"""
        try:
            safe_name = re.sub(r'[^\w\s-]', '', product_name).strip().replace(' ', '_')
            pdf_filename = f"{safe_name}.pdf"
            pdf_path = os.path.join(PDF_DOWNLOAD_DIR, pdf_filename)
            
            response = requests.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            with open(pdf_path, 'wb') as f:
                f.write(response.content)
            
            print(f"  ✓ PDF downloaded: {pdf_filename}")
            return pdf_path, response.content
            
        except Exception as e:
            print(f"  ✗ Error downloading PDF: {e}")
            return None, None
    
    def extract_bio5050_specifications(self, pdf_content):
        """
        Dedicated parser for the Bio-5050 PDF only.

        The Bio-5050 datasheet uses a two-column spec table that PyPDF2 reads as:
          - All LEFT-column labels first (Scanner Type … Scanning Area)
          - All RIGHT-column values next  (Flatbed scanner … Transmissive : max…)
          - Then remaining LEFT-column labels (CV … Power Supply)
          - Then remaining RIGHT-column values (0.5% @ 1.0D … AC 100~240V…)

        Multi-line values (Scanning Area = 2 lines, Dimensions = 2 lines) are
        handled explicitly via VALUE_LINES_PER_LABEL.
        """
        specifications = {}
        try:
            try:
                from pypdf import PdfReader
            except ImportError:
                from PyPDF2 import PdfReader

            reader = PdfReader(BytesIO(pdf_content))
            full_text = ""
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"

            if not full_text.strip():
                return specifications

            # ── Locate the spec block: everything after "Specifications" ──────
            m = re.search(r'Speci.{0,5}cations\s+System Requirement\s*\n(.*)', full_text, re.DOTALL)
            if not m:
                m = re.search(r'Speci.{0,5}cations\s*\n(.*)', full_text, re.DOTALL)
            if not m:
                return specifications

            spec_block = m.group(1)

            # Stop before boilerplate
            stop = re.search(r'PC with Windows|Microtek International|Bio-5050 Application', spec_block)
            if stop:
                spec_block = spec_block[:stop.start()]

            raw_lines = [l.strip() for l in spec_block.split('\n') if l.strip()]

            # ── Known labels in their exact printed order ─────────────────────
            LABELS = [
                "Scanner Type", "Scanning Mode", "Sensor Type", "Resolution",
                "Bit Depth", "Light Source", "Absorbance Range", "Interface",
                "Scanning Area",
                "CV", "Range(R)", "Scan Speed", "Warm up Time",
                "Dimensions", "Net Weight", "Power Supply",
            ]
            # How many raw lines each label's value occupies
            VALUE_LINES = {
                "Scanner Type": 1, "Scanning Mode": 1, "Sensor Type": 1,
                "Resolution": 1, "Bit Depth": 1, "Light Source": 1,
                "Absorbance Range": 1, "Interface": 1,
                "Scanning Area": 2,   # Reflective line + Transmissive line
                "CV": 1, "Range(R)": 1, "Scan Speed": 1, "Warm up Time": 1,
                "Dimensions": 2,      # inches line + mm line
                "Net Weight": 1, "Power Supply": 1,
            }

            label_set = {l.strip().lower() for l in LABELS}

            # Separate label lines from value lines (preserve order)
            label_lines = []
            value_lines = []
            for line in raw_lines:
                if line.strip().lower() in label_set:
                    label_lines.append(line.strip())
                else:
                    value_lines.append(line)

            # Zip labels → values respecting multi-line counts
            vi = 0
            for lbl in label_lines:
                n = VALUE_LINES.get(lbl, 1)
                chunk = value_lines[vi:vi + n]
                vi += n
                if chunk:
                    val = ' '.join(chunk)
                    # Clean up PDF font ligature artifacts
                    val = val.replace('/f_l', 'fl').replace('/f_i', 'fi')
                    # 'd' used as separator between numbers/units (e.g. "240Vd50")
                    val = re.sub(r'([A-Za-z0-9])d(\d)', r'\1, \2', val)
                    # Normalise label: "Warm up Time" → "Warm-up Time"
                    key = "Warm-up Time" if lbl.lower() == "warm up time" else lbl
                    specifications[key] = val.strip()

            print(f"  ✓ Bio-5050: extracted {len(specifications)} specifications")
        except Exception as e:
            print(f"  ✗ Bio-5050 spec extraction error: {e}")

        return specifications

    def extract_specifications_from_pdf(self, pdf_content):
        """Extract specifications from PDF datasheet"""
        specifications = {}
        
        if not pdf_content:
            return specifications
        
        try:
            pdf_file = BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            full_text = ""
            for page in pdf_reader.pages:
                full_text += page.extract_text() + "\n"
            
            spec_patterns = {
                'Scanner Type': r'Scanner Type[:\s]+([^\n]+)',
                'Image Sensor': r'Image Sensor[:\s]+([^\n]+)',
                'Light Source': r'Light Source[:\s]+([^\n]+)',
                'Resolution': r'(?:Resolution|Optical)[:\s]+([^\n]+dpi[^\n]*)',
                'Optical Density': r'Optical Density[:\s]+([^\n]+)',
                'Scanning Modes': r'Scanning Modes[:\s]+([^\n]+)',
                'Scanning Area': r'Scanning Area[:\s]+([^\n]+)',
                'Connectivity': r'Connectivity[:\s]+([^\n]+)',
                'Dimensions': r'Dimensions[:\s\(LxWxH\)]*[:\s]+([^\n]+)',
                'Weight': r'Weight[:\s]+([^\n]+)',
                'Operating Temperature': r'Operating Temperature[:\s]+([^\n]+)',
                'Relative Humidity': r'(?:Relative [Hh]umidity|Humidity)[:\s]+([^\n]+)',
            }
            
            for key, pattern in spec_patterns.items():
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    specifications[key] = match.group(1).strip()
            
            lines = full_text.split('\n')
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                if ':' in line and len(line) < 200:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        attr = parts[0].strip()
                        value = parts[1].strip()
                        if attr and value and attr not in specifications:
                            if len(attr) < 50 and not attr.lower().startswith(('page', 'www', 'http')):
                                specifications[attr] = value
            
            print(f"  ✓ Extracted {len(specifications)} specifications from PDF")
            
        except Exception as e:
            print(f"  ✗ Error extracting PDF specifications: {e}")
        
        return specifications

    # ─────────────────────────────────────────────────────────────────────────
    # FIX: Parse WooCommerce product variations (woovr-variation divs)
    # These hold prices in data-price / data-pricehtml / data-attrs attributes.
    # Products like the ScanMaker 9800XL Plus use this pattern instead of a
    # plain <p class="price">, which is why they returned null prices before.
    # ─────────────────────────────────────────────────────────────────────────
    def extract_variant_prices(self, soup):
        """
        Extract pricing from WooCommerce variation swatches (woovr plugin).
        Returns a list of variant dicts, e.g.:
          [
            {"name": "Scanner Only",            "price_ex_vat": "£1,952.00", "price_inc_vat": "£2,342.40"},
            {"name": "Scanner with TMA",         "price_ex_vat": "£2,354.00", "price_inc_vat": "£2,824.80"},
            {"name": "Scanner with TMA & SilverFast software", ...},
          ]
        Returns [] if no variants found.
        """
        variants = []
        variation_divs = soup.find_all('div', class_=re.compile(r'woovr-variation\b'))

        for div in variation_divs:
            # Skip the wrapper div (woovr-variations); we only want individual items
            classes = div.get('class', [])
            if 'woovr-variations' in classes and 'woovr-variation-radio' not in classes:
                continue

            price_html_raw = div.get('data-pricehtml', '')
            if not price_html_raw:
                continue

            # The data-pricehtml attribute contains HTML – parse it to pull prices
            price_soup = BeautifulSoup(price_html_raw, 'html.parser')
            price_text = price_soup.get_text()

            # Variant label from data-attrs JSON  e.g. {"attribute_model":"Scanner Only"}
            label = ''
            attrs_raw = div.get('data-attrs', '{}')
            try:
                attrs = json.loads(attrs_raw)
                label = next(iter(attrs.values()), '')
            except Exception:
                pass

            # Fallback label: look inside the div for .woovr-variation-name
            if not label:
                name_el = div.find(class_='woovr-variation-name')
                if name_el:
                    label = name_el.get_text(strip=True)

            ex_vat = None
            inc_vat = None
            currency = None

            ex_match = re.search(r'([£$€]\s*[\d,]+\.?\d*)\s*ex\.\s*VAT', price_text)
            if ex_match:
                ex_vat = ex_match.group(1).strip()
                currency = ex_vat[0]

            inc_match = re.search(r'\(([£$€]\s*[\d,]+\.?\d*)\s*inc\.\s*VAT\)', price_text)
            if inc_match:
                inc_vat = inc_match.group(1).strip()

            # Also try stock/availability
            availability_html = div.get('data-availability', '')
            avail_soup = BeautifulSoup(availability_html, 'html.parser')
            availability = avail_soup.get_text(strip=True) or 'Unknown'

            variants.append({
                "name":         label,
                "price_ex_vat":  ex_vat,
                "price_inc_vat": inc_vat,
                "currency":      currency,
                "availability":  availability,
            })

        return variants

    def scrape_product(self, product_url, index):
        """Scrape individual product details"""
        print(f"\n[{index + 1}] Scraping: {product_url}")
        
        product_data = {
            "url": product_url,
            "title": None,
            # For simple (non-variant) products these hold the single price
            "price_ex_vat": None,
            "price_inc_vat": None,
            "currency": None,
            # ✅ NEW: populated when a product has WooCommerce variants
            "variants": [],
            "pdf_url": None,
            "pdf_downloaded": False,
            "specifications": {},
            "scraped_at": datetime.now().isoformat()
        }
        
        try:
            self.driver.get(product_url)
            time.sleep(2)
            
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # ── Title ──────────────────────────────────────────────────────
            title_tag = soup.find('h1')
            if title_tag:
                product_data["title"] = title_tag.get_text(strip=True)
                print(f"  ✓ Title: {product_data['title']}")
            
            # ── Price: simple product ──────────────────────────────────────
            price_tag = soup.find('p', class_='price')
            if price_tag:
                price_text = price_tag.get_text()
                
                currency_tag = price_tag.find('span', class_='woocommerce-Price-currencySymbol')
                if currency_tag:
                    product_data["currency"] = currency_tag.get_text(strip=True)
                
                ex_vat_match = re.search(r'([£$€]\s*[\d,]+\.?\d*)\s*ex\.\s*VAT', price_text)
                if ex_vat_match:
                    product_data["price_ex_vat"] = ex_vat_match.group(1).strip()
                
                inc_vat_match = re.search(r'\(([£$€]\s*[\d,]+\.?\d*)\s*inc\.\s*VAT\)', price_text)
                if inc_vat_match:
                    product_data["price_inc_vat"] = inc_vat_match.group(1).strip()
                
                print(f"  ✓ Price: {product_data['price_ex_vat']} ex. VAT ({product_data['price_inc_vat']} inc. VAT)")

            # ── FIX: Price: variant / WooCommerce WOOVR product ───────────
            # Run this whether or not a simple price was found; some pages show
            # both a "from" price tag AND the variation swatches.
            variants = self.extract_variant_prices(soup)
            if variants:
                product_data["variants"] = variants
                # Set top-level price to the cheapest available variant so the
                # field is never null for variant products
                available = [v for v in variants if 'out of stock' not in v.get('availability', '').lower()]
                cheapest = available[0] if available else variants[0]
                if not product_data["price_ex_vat"]:
                    product_data["price_ex_vat"]  = cheapest["price_ex_vat"]
                    product_data["price_inc_vat"] = cheapest["price_inc_vat"]
                    product_data["currency"]      = cheapest["currency"]
                print(f"  ✓ Variants found ({len(variants)}): "
                      + ", ".join(v["name"] for v in variants))
            
            # ── PDF datasheet ──────────────────────────────────────────────
            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
            for link in pdf_links:
                link_text = link.get_text(strip=True).lower()
                if 'datasheet' in link_text or 'download' in link_text:
                    pdf_url = link.get('href')
                    product_data["pdf_url"] = urljoin(BASE_URL, pdf_url)
                    print(f"  ✓ PDF URL: {product_data['pdf_url']}")
                    
                    pdf_path, pdf_content = self.download_pdf(
                        product_data["pdf_url"], 
                        product_data["title"] or f"product_{index}"
                    )
                    
                    if pdf_content:
                        product_data["pdf_downloaded"] = True
                        # Bio-5050 has a non-standard two-column PDF layout —
                        # use its dedicated parser; all other products use the
                        # existing generic extractor unchanged.
                        if 'bio-5050' in product_data["pdf_url"].lower():
                            product_data["specifications"] = self.extract_bio5050_specifications(pdf_content)
                        else:
                            product_data["specifications"] = self.extract_specifications_from_pdf(pdf_content)
                    
                    break
            
            # ── Fallback: scrape specs table from page ─────────────────────
            if not product_data["specifications"]:
                print("  ℹ No PDF found or specifications not extracted, checking page...")
                spec_tables = soup.find_all(['table', 'div'], class_=re.compile(r'spec|attribute|feature', re.IGNORECASE))
                for table in spec_tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) == 2:
                            attr = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            if attr and value:
                                product_data["specifications"][attr] = value
            
            print(f"  ✓ Product scraped successfully!")
            
        except Exception as e:
            print(f"  ✗ Error scraping product: {e}")
        
        return product_data
    
    def run(self):
        """Main scraping process"""
        print("=" * 80)
        print("🔍 MICROTEK SCANNER SCRAPER")
        print("=" * 80)
        
        checkpoint_exists = self.load_checkpoint()
        product_links = self.get_product_links()
        
        if not product_links:
            print("✗ No products found. Exiting.")
            return
        
        self.checkpoint_data["total_products"] = len(product_links)
        start_index = self.checkpoint_data["last_processed_index"] + 1 if checkpoint_exists else 0
        
        if start_index > 0:
            print(f"\n▶ Resuming from product {start_index + 1}")
            self.products_data = self.checkpoint_data.get("products_scraped", [])
        
        for i in range(start_index, len(product_links)):
            product_url = product_links[i]
            product_data = self.scrape_product(product_url, i)
            self.products_data.append(product_data)
            
            if (i + 1) % CHECKPOINT_INTERVAL == 0 or i == len(product_links) - 1:
                self.save_checkpoint(i, product_data)
            
            time.sleep(2)
        
        self.save_output()
        self.driver.quit()
        print("\n" + "=" * 80)
        print("✓ SCRAPING COMPLETED!")
        print("=" * 80)
    
    def save_output(self):
        """Save final output JSON"""
        output_data = {
            "scraped_at": datetime.now().isoformat(),
            "total_products": len(self.products_data),
            "source": MAIN_PAGE,
            "products": self.products_data
        }
        
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"\n✓ Output saved to: {OUTPUT_FILE}")
            print(f"  Total products scraped: {len(self.products_data)}")
        except Exception as e:
            print(f"✗ Error saving output: {e}")


if __name__ == "__main__":
    try:
        scraper = MicrotekScraper()
        scraper.run()
    except KeyboardInterrupt:
        print("\n\n⚠ Scraping interrupted by user")
        print("  Checkpoint saved. Run again to resume.")
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()