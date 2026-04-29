"""
Microtek Scanner Mapper - Bronze to Silver Layer
Production-ready mapper aligned with DDS standards
Transforms scraped Microtek scanner data into standardized silver CSV format
"""

import json
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# =================================================
# CONFIGURATION
# =================================================

INPUT_FILE = "C:\HP-DDS\Microtek\microtek_scanners_output.json"
OUTPUT_CSV = "microtek_scanners_silver.csv"
ERROR_LOG = "microtek_mapping_errors.log"

# Silver schema fields (standardized)
SILVER_FIELDS = [
    "Make", "Model", "Device Type", "Asset Class", "Product Number",
    "Date Introduced", "Status", "Device Product Family", "Product Category Name",
    "Print Technology", "Region", "Country", "Currency Symbol", "Currency Code",
    "Currency Rate", "UNSPSC",
    "European Article Number", "Supported Countries", "Supported Regions",
    "Conn Network", "Conn Network Protocols", "Conn Local", "Conn Network Standard",
    "Has Wifi", "Standards", "Width", "Width Unit", "Depth", "Depth Unit",
    "Height", "Height Unit", "Weight", "Weight Unit", "Speed Mono", "Speed Mono Unit",
    "Mono PPM Notes", "Speed Color", "Speed Color Unit", "Color PPM Notes",
    "Print DPI", "Mono Speed First Page Output", "Color Speed First Page Output",
    "Standard Input Capacity", "Maximum Input Capacity", "Auto Document Feeder Input Capacity",
    "Number Of Standard Paper Trays", "Maximum Number Of Paper Trays",
    "Standard Output Capacity", "Maximum Output Capacity", "Has A3", "Has A4", "Has A5",
    "Has Color", "Has Duplex", "Print", "Copy", "Scan", "Fax",
    "Energy Saving Certifications", "EconoMode", "Scan To Folder", "Scan To Email",
    "Scan to USB", "Scan To Share Point", "Pcl3Gui", "Pcl5E", "Pcl6", "Hpgl2",
    "Postscript", "Rpcs", "IBM Pro Printer", "Epsonfx", "Brscript3", "Direct PDF",
    "Printer Language Notes", "Rmpv Low", "Rmpv High", "Rmpv Max", "Rmpv Notes",
    "Power Active", "Power Active Unit", "Power Idle", "Power Idle Unit",
    "Power Save", "Power Save Unit", "Power Notes", "List Price",
    "List Price In Country Currency", "List Price Website", "List Price Date",
    "Street Price", "Street Price In Country Currency", "Street Price Website",
    "Street Price Date", "Record Creation Date", "Created By", "Record Updated Date",
    "Updated By", "Url", "ITT Segment", "Segment", "Comments"
]

# Constants
MAKE = "Microtek"
MAKE_SHORT = "MTK"   # Short form used in Make field
REGION = "EMEA"
COUNTRY = "United Kingdom"
CURRENCY_SYMBOL = "£"
CURRENCY_CODE = "GBP"
CURRENCY_RATE = 1.0  # Base rate (GBP); update if conversion to USD is needed
GBP_TO_USD = 1.27   # GBP → USD conversion rate (update periodically)
UNSPSC_SCANNERS = "43211711"  # UNSPSC code for scanners

# =================================================
# UTILITY FUNCTIONS
# =================================================

def log_error(message: str):
    """Log errors to file and console"""
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] {message}\n")
    print(f"  ⚠ {message}")


def clean_text(text: str) -> str:
    """Clean and normalize text"""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()


def extract_numeric(text: str) -> float:
    """Extract first numeric value from text"""
    if not text:
        return 0.0
    text_clean = str(text).replace(',', '').replace('\n', ' ')
    match = re.search(r'(\d+\.?\d*)', text_clean)
    return float(match.group(1)) if match else 0.0


def strip_price(price_str: str) -> str:
    """Remove currency symbols and formatting from price"""
    if not price_str:
        return ""
    return re.sub(r'[£$€,\s]', '', str(price_str))


# =================================================
# EXTRACTION FUNCTIONS
# =================================================

def extract_model(title: str) -> str:
    """
    Extract short model name from product title.
    Strips the 'Microtek' prefix and returns only the core model
    identifier — e.g. 'ArtixScan F2', 'ScanMaker 9800XL', 'LS-3800',
    'Bio-5050', 'Medi-6000'.
    Descriptive suffixes like 'A3 Professional Flatbed ...' are dropped.
    """
    if not title:
        return ""

    # Remove brand prefix
    title_clean = re.sub(r'^Microtek\s+', '', title, flags=re.IGNORECASE).strip()

    # Known model families — extract family + alphanumeric model code
    # Pattern captures things like: ArtixScan F2, ScanMaker 9800XL, LS-3800,
    # Bio-5000 Plus, Bio-5050, Medi-6000 Plus, ObjectScan 1600
    model_match = re.match(
        r'^([A-Za-z][A-Za-z0-9]*(?:[_\-][A-Za-z0-9]+)?'   # family: ArtixScan, LS, Bio, Medi …
        r'(?:\s+[A-Za-z0-9\-]+){0,2})',                    # up to 2 more tokens (e.g. "9800XL Plus")
        title_clean
    )

    if model_match:
        candidate = model_match.group(1).strip()
        # Drop trailing generic words that aren't part of the model number
        candidate = re.sub(
            r'\s+(A[0-9]|A[0-9]\+?|Professional|Flatbed|Large|Format|Medical|Film'
            r'|Graphics|Plus(?!\s*\d)|Specimen|Electrophoresis|High|Stability|Gel'
            r'|Imager|Bio\s*Rad|Scanner|Prepress).*$',
            '', candidate, flags=re.IGNORECASE
        ).strip()
        # Keep "Plus" only when it directly follows a model number (e.g. Bio-5000 Plus)
        return candidate

    return title_clean.split()[0] if title_clean else ""


def extract_product_number(url: str) -> str:
    """Extract product number/SKU from URL"""
    if not url:
        return ""
    
    # Extract slug from URL
    slug = url.split('/product/')[-1].rstrip('/')
    
    # Remove 'microtek-' prefix if present
    slug = re.sub(r'^microtek-', '', slug, flags=re.IGNORECASE)
    
    # Extract first meaningful part and uppercase
    product_num = slug.split('-')[0].upper()
    
    return product_num if product_num else ""


def infer_device_product_family(title: str) -> str:
    """Infer device product family from title"""
    title_lower = title.lower()
    
    if 'artixscan' in title_lower:
        return 'ArtixScan Series'
    elif 'scanmaker' in title_lower:
        return 'ScanMaker Series'
    elif 'ls-' in title_lower or 'ls ' in title_lower:
        return 'LS Series Large Format'
    elif 'medi' in title_lower:
        return 'Medical Imaging Series'
    elif 'bio' in title_lower:
        return 'Bio Imaging Series'
    elif 'objectscan' in title_lower:
        return 'ObjectScan Series'
    
    return clean_text(title)


def extract_asset_class(title: str, specs: Dict) -> str:
    """Determine asset class based on product type"""
    title_lower = title.lower()
    
    # Large format scanners are Enterprise
    if any(x in title_lower for x in ['a0', 'a1', 'large format', 'ls-']):
        return 'Enterprise'
    
    # Medical and scientific are Enterprise
    if any(x in title_lower for x in ['medi', 'bio', 'medical', 'x-ray', 'dna', 'gel']):
        return 'Enterprise'
    
    # A3 professional scanners are Workgroup
    if 'a3' in title_lower and any(x in title_lower for x in ['professional', 'prepress', 'graphics']):
        return 'Workgroup'
    
    # Default A4/A3 scanners are Personal
    return 'Personal'


def extract_resolution(specs: Dict) -> str:
    """Extract resolution in 'X x Y' format from messy spec text"""

    resolution_keys = ['Resolution', 'Optical Resolution', 'Optical']

    for key in resolution_keys:
        if key in specs:

            raw = str(specs[key])

            # 🔹 Clean text
            raw = re.sub(r'\s+', ' ', raw)              # normalize spaces
            raw = raw.replace(',', '')                 # remove commas (1,600 → 1600)
            raw = re.sub(r'[^\w\s.xX×]', ' ', raw)      # remove junk symbols

            # --------------------------------------------------
            # 1️⃣ PRIORITY: Optical resolution (if present)
            # --------------------------------------------------
            optical_match = re.search(
                r'optical\s*[:\-]?\s*(\d{3,5})\s*[xX×]\s*(\d{3,5})',
                raw, re.I
            )
            if optical_match:
                return f"{optical_match.group(1)} x {optical_match.group(2)}"

            # --------------------------------------------------
            # 2️⃣ Standard X x Y pattern
            # --------------------------------------------------
            match_xy = re.search(
                r'(\d{3,5})\s*[xX×]\s*(\d{3,5})',
                raw
            )
            if match_xy:
                return f"{match_xy.group(1)} x {match_xy.group(2)}"

            # --------------------------------------------------
            # 3️⃣ Single DPI → convert to X x X
            # --------------------------------------------------
            match_single = re.search(
                r'(\d{3,5})\s*dpi',
                raw, re.I
            )
            if match_single:
                val = match_single.group(1)
                return f"{val} x {val}"

    return ""


def parse_dimensions(specs: Dict) -> Tuple[str, str, str]:
    """
    Parse dimensions and return values in INCHES.
    Handles dual-format strings like:
      '22.3" x 15.1" x 6.3" / 567 x 385 x 158 mm'
    Also handles numbers with stray internal spaces (e.g. "627 .5") caused
    by PDF extraction — these are collapsed before matching.
    Priority: explicit inch values > mm conversion > cm conversion > bare numbers.
    Returns (width_in, depth_in, height_in)
    """
    if 'Dimensions' not in specs:
        return "", "", ""

    raw = clean_text(specs['Dimensions'])

    # Collapse stray spaces inside numbers like "627 .5" → "627.5"
    raw = re.sub(r'(\d)\s+\.(\d)', r'\1.\2', raw)
    raw = re.sub(r'(\d)\s+(\d)', lambda m: m.group(0) if re.search(r'[xX×/]', raw[max(0,raw.find(m.group(0))-2):raw.find(m.group(0))+len(m.group(0))+2]) else m.group(1)+m.group(2), raw)

    # --------------------------------------------------
    # 1. Explicit inch values  (e.g. 22.3" x 15.1" x 6.3")
    #    These are already in inches — use directly.
    # --------------------------------------------------
    inch_match = re.search(
        r'(\d+\.?\d*)\s*["\u201d\u2033]\s*[xX×]\s*(\d+\.?\d*)\s*["\u201d\u2033]\s*[xX×]\s*(\d+\.?\d*)\s*["\u201d\u2033]',
        raw
    )
    if inch_match:
        return inch_match.group(1), inch_match.group(2), inch_match.group(3)

    # --------------------------------------------------
    # 2. Explicit mm values  (e.g. "567 x 385 x 158 mm")
    #    Convert to inches (1 mm = 1/25.4 in)
    # --------------------------------------------------
    mm_match = re.search(
        r'(\d+\.?\d*)\s*[xX×]\s*(\d+\.?\d*)\s*[xX×]\s*(\d+\.?\d*)\s*mm',
        raw, re.I
    )
    if mm_match:
        width  = round(float(mm_match.group(1)) / 25.4, 1)
        depth  = round(float(mm_match.group(2)) / 25.4, 1)
        height = round(float(mm_match.group(3)) / 25.4, 1)
        return str(width), str(depth), str(height)

    # --------------------------------------------------
    # 3. cm values → convert to inches (1 cm = 0.3937 in)
    # --------------------------------------------------
    dim_text = re.sub(r'[^\d.xX×"\s/cm]', '', raw)
    cm_match = re.search(
        r'(\d+\.?\d*)\s*cm\s*[xX×]\s*(\d+\.?\d*)\s*cm\s*[xX×]\s*(\d+\.?\d*)\s*cm',
        dim_text, re.I
    )
    if cm_match:
        width  = round(float(cm_match.group(1)) * 0.3937, 1)
        depth  = round(float(cm_match.group(2)) * 0.3937, 1)
        height = round(float(cm_match.group(3)) * 0.3937, 1)
        return str(width), str(depth), str(height)

    # --------------------------------------------------
    # 4. Fallback: bare W x D x H with no unit — assume mm, convert to inches
    # --------------------------------------------------
    fallback_match = re.search(
        r'(\d+\.?\d*)\s*[xX×]\s*(\d+\.?\d*)\s*[xX×]\s*(\d+\.?\d*)',
        dim_text
    )
    if fallback_match:
        width  = round(float(fallback_match.group(1)) / 25.4, 1)
        depth  = round(float(fallback_match.group(2)) / 25.4, 1)
        height = round(float(fallback_match.group(3)) / 25.4, 1)
        return str(width), str(depth), str(height)

    return "", "", ""


def extract_weight(specs: Dict) -> str:
    """Extract weight in lbs"""
    if 'Weight' not in specs:
        return ""
    
    weight_text = clean_text(specs['Weight'])
    
    # Try lbs first
    lbs_match = re.search(r'(\d+\.?\d*)\s*lbs?', weight_text, re.I)
    if lbs_match:
        return lbs_match.group(1)
    
    # Try kg and convert to lbs (1 kg = 2.20462 lbs)
    kg_match = re.search(r'(\d+\.?\d*)\s*kg', weight_text, re.I)
    if kg_match:
        weight_lbs = round(float(kg_match.group(1)) * 2.20462, 1)
        return str(weight_lbs)
    
    return ""


def detect_connectivity(specs: Dict) -> Dict[str, str]:
    """Detect scanner connectivity options"""
    connectivity = {
        "conn_network": "False",
        "conn_network_protocols": "",
        "conn_local": "False",
        "conn_network_standard": "",
        "has_wifi": "False",
        "standards": ""
    }
    
    # Check for connectivity info
    conn_keys = ['Connectivity', 'Interface', 'Connection', 'USB']
    conn_text = ""
    
    for key in conn_keys:
        if key in specs:
            conn_text += " " + clean_text(specs[key]).lower()
    
    # USB connection
    if 'usb' in conn_text:
        connectivity["conn_local"] = "True"
        
        if 'usb 2.0' in conn_text or 'hi-speed usb' in conn_text:
            connectivity["conn_network_standard"] = "USB 2.0"
        elif 'usb 3.0' in conn_text:
            connectivity["conn_network_standard"] = "USB 3.0"
        else:
            connectivity["conn_network_standard"] = "USB"
    
    # Network connection (rare in flatbed scanners)
    if any(x in conn_text for x in ['ethernet', 'network', 'lan']):
        connectivity["conn_network"] = "True"
        connectivity["conn_network_protocols"] = "Ethernet"
    
    # WiFi (rare in professional scanners)
    if any(x in conn_text for x in ['wifi', 'wi-fi', 'wireless']):
        connectivity["has_wifi"] = "True"
        connectivity["standards"] = "WiFi"
    
    return connectivity


def detect_paper_sizes(title: str) -> Dict[str, str]:
    """Detect supported paper sizes from title/specs"""
    title_lower = title.lower()
    
    sizes = {
        "has_a3": "False",
        "has_a4": "False",
        "has_a5": "False"
    }
    
    # A3
    if 'a3' in title_lower:
        sizes["has_a3"] = "True"
        sizes["has_a4"] = "True"  # A3 scanners can do A4
    
    # A4
    if 'a4' in title_lower or not ('a3' in title_lower or 'a0' in title_lower or 'a1' in title_lower):
        sizes["has_a4"] = "True"
    
    # Large format scanners (A0/A1) can do all sizes
    if any(x in title_lower for x in ['a0', 'a1', 'large format']):
        sizes["has_a3"] = "True"
        sizes["has_a4"] = "True"
        sizes["has_a5"] = "True"
    
    return sizes


def infer_status(specs: Dict, title: str = "", raw_text: str = "") -> str:
    """
    Infer product status.
    Returns 'Discontinued' if discontinuation keywords are found,
    otherwise 'Active'.
    """
    DISCONTINUED_KEYWORDS = [
        'discontinued', 'end of life', 'eol', 'no longer available',
        'out of production', 'replaced by', 'obsolete'
    ]
    combined = (title + " " + " ".join(str(v) for v in specs.values()) + " " + raw_text).lower()
    for kw in DISCONTINUED_KEYWORDS:
        if kw in combined:
            return "Discontinued"
    return "Active"


def extract_scan_speed(specs: Dict) -> Dict[str, str]:
    """
    Extract scanner scanning speed.
    Scanners report speed as pages-per-minute (ppm) or images-per-minute (ipm).
    Maps mono (grayscale/B&W) and color speeds from spec keys.
    Returns dict with speed values and notes.
    """
    result = {
        "speed_mono": "",
        "speed_mono_unit": "",
        "mono_ppm_notes": "",
        "speed_color": "",
        "speed_color_unit": "",
        "color_ppm_notes": "",
    }

    # Keys the scraper may use for scanning speed
    MONO_KEYS = [
        'Scanning Speed', 'Scan Speed', 'Speed', 'B&W Speed',
        'Grayscale Speed', 'Mono Speed', 'Black & White Speed'
    ]
    COLOR_KEYS = [
        'Color Scanning Speed', 'Color Scan Speed', 'Color Speed',
        'Colour Speed', 'Colour Scanning Speed'
    ]

    def _parse_speed(text: str):
        """Return (value_str, unit_str, notes_str) from a speed text."""
        if not text:
            return "", "", ""
        text_clean = clean_text(text)
        # Match patterns like "3 ppm", "8 ipm", "5 pages/min"
        match = re.search(r'(\d+\.?\d*)\s*(ppm|ipm|pages?/min|img/min)', text_clean, re.I)
        # Always normalise unit to ppm regardless of what the spec says
        if match:
            return match.group(1), "ppm", text_clean
        # Bare number fallback
        num = re.search(r'(\d+\.?\d*)', text_clean)
        if num:
            return num.group(1), "ppm", text_clean
        return "", "", text_clean

    # Mono / grayscale speed
    for key in MONO_KEYS:
        if key in specs:
            val, unit, notes = _parse_speed(specs[key])
            if val:
                result["speed_mono"] = val
                result["speed_mono_unit"] = unit
                result["mono_ppm_notes"] = notes
                break

    # Color speed
    for key in COLOR_KEYS:
        if key in specs:
            val, unit, notes = _parse_speed(specs[key])
            if val:
                result["speed_color"] = val
                result["speed_color_unit"] = unit
                result["color_ppm_notes"] = notes
                break

    return result


def detect_econoMode(specs: Dict, raw_text: str = "") -> str:
    """
    Detect EconoMode (Toner Saver / Energy Saver / Cost Saver).
    Checks specs dict values and any raw scraped text for keywords.
    Returns "True" if found, "False" otherwise.
    """
    ECONO_KEYWORDS = [
        'toner saver', 'energy saver', 'cost saver', 'econoMode',
        'econo mode', 'toner save', 'draft mode', 'ink saver'
    ]
    # Combine all spec values and raw text for keyword search
    combined = " ".join(str(v) for v in specs.values()).lower()
    if raw_text:
        combined += " " + raw_text.lower()
    
    for keyword in ECONO_KEYWORDS:
        if keyword.lower() in combined:
            return "True"
    return "False"


# =================================================
# MAIN MAPPING FUNCTION
# =================================================

def map_microtek_to_silver(bronze: Dict[str, Any]) -> Dict[str, Any]:
    """Map bronze layer data to silver layer schema"""
    
    title = clean_text(bronze.get('title', ''))
    url = bronze.get('url', '')
    specs = bronze.get('specifications', {})
    price_ex_vat = bronze.get('price_ex_vat', '')
    raw_text = bronze.get('raw_text', '')  # Full scraped page text for EconoMode detection
    
    # Initialize silver row
    silver = {}
    
    # ===== BASIC INFO =====
    silver['Make'] = MAKE_SHORT   # Short brand identifier (MTK)
    silver['Model'] = extract_model(title)
    silver['Device Type'] = 'Scanner'
    silver['Asset Class'] = extract_asset_class(title, specs)
    silver['Product Number'] = silver['Model']  # Product Number mirrors Model
    
    silver['Date Introduced'] = ""
    silver['Status'] = infer_status(specs, title, raw_text)
    silver['Device Product Family'] = infer_device_product_family(title)
    silver['Product Category Name'] = 'Printer'
    
    # ===== TECHNOLOGY =====
    silver['Print Technology'] = 'Scanner'
    
    # ===== LOCATION & CURRENCY =====
    silver['Region'] = REGION
    silver['Country'] = COUNTRY
    silver['Currency Symbol'] = CURRENCY_SYMBOL
    silver['Currency Code'] = CURRENCY_CODE
    silver['Currency Rate'] = str(CURRENCY_RATE)
    silver['UNSPSC'] = UNSPSC_SCANNERS
    
    silver['European Article Number'] = "0"
    silver['Supported Countries'] = "NA"
    silver['Supported Regions'] = "NA"
    
    # ===== CONNECTIVITY =====
    connectivity = detect_connectivity(specs)
    silver['Conn Network'] = connectivity['conn_network']
    silver['Conn Network Protocols'] = connectivity['conn_network_protocols']
    silver['Conn Local'] = connectivity['conn_local']
    silver['Conn Network Standard'] = connectivity['conn_network_standard']
    silver['Has Wifi'] = connectivity['has_wifi']
    silver['Standards'] = connectivity['standards']
    
    # ===== DIMENSIONS =====
    width, depth, height = parse_dimensions(specs)
    silver['Width'] = width
    silver['Width Unit'] = 'in'   # Always in — default even when value is 0
    silver['Depth'] = depth
    silver['Depth Unit'] = 'in'
    silver['Height'] = height
    silver['Height Unit'] = 'in'
    
    # ===== WEIGHT =====
    weight = extract_weight(specs)
    silver['Weight'] = weight
    silver['Weight Unit'] = 'lbs'  # Always lbs — default even when value is 0
    
    # ===== SPEED (Scanners report scanning speed in ppm/ipm) =====
    scan_speed = extract_scan_speed(specs)
    silver['Speed Mono'] = scan_speed['speed_mono']
    silver['Speed Mono Unit'] = 'ppm'  # Always ppm for scanners
    silver['Mono PPM Notes'] = scan_speed['mono_ppm_notes']
    silver['Speed Color'] = scan_speed['speed_color']
    silver['Speed Color Unit'] = 'ppm'  # Always ppm for scanners
    silver['Color PPM Notes'] = scan_speed['color_ppm_notes']
    
    # ===== RESOLUTION =====
    silver['Print DPI'] = extract_resolution(specs)
    
    # ===== TIMING =====
    silver['Mono Speed First Page Output'] = ""
    silver['Color Speed First Page Output'] = ""
    
    # ===== CAPACITY (Not applicable for flatbed scanners) =====
    silver['Standard Input Capacity'] = ""
    silver['Maximum Input Capacity'] = ""
    silver['Auto Document Feeder Input Capacity'] = ""
    silver['Number Of Standard Paper Trays'] = ""
    silver['Maximum Number Of Paper Trays'] = ""
    silver['Standard Output Capacity'] = ""
    silver['Maximum Output Capacity'] = ""
    
    # ===== PAPER SIZES =====
    paper_sizes = detect_paper_sizes(title)
    silver['Has A3'] = paper_sizes['has_a3']
    silver['Has A4'] = paper_sizes['has_a4']
    silver['Has A5'] = paper_sizes['has_a5']
    
    # ===== COLOR & DUPLEX =====
    silver['Has Color'] = "True"  # All Microtek scanners are color
    silver['Has Duplex'] = "False"  # Flatbed scanners don't have auto-duplex
    
    # ===== FUNCTIONS =====
    silver['Print'] = "False"
    silver['Copy'] = "False"
    silver['Scan'] = "True"
    silver['Fax'] = "False"
    
    # ===== CERTIFICATIONS =====
    silver['Energy Saving Certifications'] = ""
    
    # ===== ECONO MODE =====
    silver['EconoMode'] = detect_econoMode(specs, raw_text)
    
    # ===== SCAN FEATURES =====
    silver['Scan To Folder'] = "False"
    silver['Scan To Email'] = "False"
    silver['Scan to USB'] = "False"
    silver['Scan To Share Point'] = "False"
    
    # ===== PRINTER LANGUAGES (Not applicable) =====
    silver['Pcl3Gui'] = "False"
    silver['Pcl5E'] = "False"
    silver['Pcl6'] = "False"
    silver['Hpgl2'] = "False"
    silver['Postscript'] = "False"
    silver['Rpcs'] = "False"
    silver['IBM Pro Printer'] = "False"
    silver['Epsonfx'] = "False"
    silver['Brscript3'] = "False"
    silver['Direct PDF'] = "False"
    silver['Printer Language Notes'] = "NA"
    
    # ===== RMPV (Not applicable for scanners) =====
    silver['Rmpv Low'] = ""
    silver['Rmpv High'] = ""
    silver['Rmpv Max'] = ""
    silver['Rmpv Notes'] = "NA"
    
    # ===== POWER CONSUMPTION =====
    silver['Power Active'] = ""
    silver['Power Active Unit'] = ""
    silver['Power Idle'] = ""
    silver['Power Idle Unit'] = ""
    silver['Power Save'] = ""
    silver['Power Save Unit'] = ""
    silver['Power Notes'] = ""
    
    # ===== PRICING =====
    price_gbp_str = strip_price(price_ex_vat)

    # List Price = NA (USD list price not available)
    silver['List Price'] = "NA"
    silver['List Price In Country Currency'] = "NA"
    silver['List Price Website'] = "businessdigitalmachines.co.uk"
    silver['List Price Date'] = datetime.now().strftime("%m/%d/%Y")

    # Street Price = actual scraped GBP price converted to USD
    try:
        price_usd = round(float(price_gbp_str) * GBP_TO_USD, 2) if price_gbp_str else 0
        silver['Street Price'] = str(price_usd) if price_usd else "0"
    except (ValueError, TypeError):
        silver['Street Price'] = "0"
    silver['Street Price In Country Currency'] = price_gbp_str if price_gbp_str else "0"
    silver['Street Price Website'] = "NA"
    silver['Street Price Date'] = datetime.now().strftime("%m/%d/%Y")
    
    # ===== METADATA =====
    silver['Record Creation Date'] = datetime.now().strftime('%m/%d/%Y')
    silver['Created By'] = 'DDS Automation'
    silver['Record Updated Date'] = datetime.now().strftime('%m/%d/%Y')
    silver['Updated By'] = 'DDS Automation'
    
    silver['Url'] = url
    
    # ===== SEGMENTS =====
    silver['ITT Segment'] = 'Scanner'
    silver['Segment'] = 'Scanner'
    
    # ===== COMMENTS =====
    empty_fields = [
        f for f in SILVER_FIELDS 
        if f != "Comments"
        and (silver.get(f) in ["", "NA", None] or silver.get(f) == 0 or silver.get(f) == "False")
    ]
    
    if empty_fields:
        silver['Comments'] = f"Missing data for: {', '.join(empty_fields[:10])}"  # Limit to first 10
    else:
        silver['Comments'] = "All fields populated"
    
    return silver


def normalize_silver_row(silver: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize silver row for CSV output"""
    # Numeric fields that should default to 0 when empty
    NUMERIC_FIELDS = {
        "European Article Number",
        "Width", "Depth", "Height", "Weight",
        "Speed Mono", "Speed Color",
        "Print DPI", "Mono Speed First Page Output", "Color Speed First Page Output",
        "Standard Input Capacity", "Maximum Input Capacity",
        "Auto Document Feeder Input Capacity",
        "Number Of Standard Paper Trays", "Maximum Number Of Paper Trays",
        "Standard Output Capacity", "Maximum Output Capacity",
        "Rmpv Low", "Rmpv High", "Rmpv Max",
        "Power Active", "Power Idle", "Power Save",
        "Street Price", "Street Price In Country Currency",
        "Currency Rate"
    }

    # Fields that must always keep their literal set value and never be
    # overridden by the NA / 0 defaults (unit fields, fixed-string fields)
    PRESERVE_FIELDS = {
        "Width Unit", "Depth Unit", "Height Unit", "Weight Unit",
        "Speed Mono Unit", "Speed Color Unit",
    }

    # Ensure all fields exist
    for field in SILVER_FIELDS:
        if field not in silver:
            silver[field] = ""

    # Apply NA / 0 defaults and convert to string
    for field in SILVER_FIELDS:
        val = silver[field]
        if field in PRESERVE_FIELDS:
            # Keep whatever was set — never override with NA/0
            silver[field] = str(val) if val is not None else ""
        elif val is None or val == "":
            if field in NUMERIC_FIELDS:
                silver[field] = "0"
            else:
                silver[field] = "NA"
        else:
            silver[field] = str(val)

    return silver


# =================================================
# MAIN PROCESSING
# =================================================

def main():
    """Main function to process Microtek bronze to silver mapping"""
    
    print("=" * 80)
    print("MICROTEK SCANNERS - BRONZE TO SILVER MAPPER")
    print("=" * 80)
    
    # Load bronze JSON
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        bronze_rows = data.get('products', [])
        print(f"[OK] Loaded {len(bronze_rows)} scanner products from {INPUT_FILE}\n")
    except FileNotFoundError:
        print(f"\n[ERROR] Bronze file not found: {INPUT_FILE}")
        print("Please ensure the scraper output file is in the same directory.")
        return
    except Exception as e:
        log_error(f"Failed to load bronze JSON: {str(e)}")
        return
    
    # Process each scanner
    silver_rows = []
    processed = 0
    skipped = 0
    
    for idx, bronze in enumerate(bronze_rows, 1):
        try:
            product_name = bronze.get('title', 'Unknown')
            print(f"[{idx}/{len(bronze_rows)}] Processing: {product_name}... ", end="")
            
            # Map to silver
            silver = map_microtek_to_silver(bronze)
            
            if not silver.get('Model'):
                print("SKIPPED (no model name)")
                skipped += 1
                continue
            
            # Normalize
            silver = normalize_silver_row(silver)
            silver_rows.append(silver)
            processed += 1
            print("DONE")
            
        except Exception as e:
            product = bronze.get('title', 'Unknown')
            error_msg = f"Error mapping {product} (row {idx}): {str(e)}"
            log_error(error_msg)
            skipped += 1
            print(f"ERROR")
    
    # Write output CSV
    print("\n" + "=" * 80)
    print("WRITING OUTPUT CSV...")
    print("=" * 80)
    
    try:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=SILVER_FIELDS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(silver_rows)
        
        print(f"[OK] Successfully wrote {len(silver_rows)} scanners to {OUTPUT_CSV}")
        
    except Exception as e:
        error_msg = f"Failed to write CSV: {str(e)}"
        log_error(error_msg)
        print(f"[ERROR] {error_msg}")
    
    # Summary
    print("\n" + "=" * 80)
    print("MAPPING COMPLETE")
    print("=" * 80)
    print(f"Total products: {len(bronze_rows)}")
    print(f"Successfully mapped: {processed}")
    print(f"Skipped: {skipped}")
    print(f"Conversion rate: {(processed/len(bronze_rows)*100) if len(bronze_rows) > 0 else 0:.1f}%")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    main()