"""
Scrape the Suitsupply custom-made wizard SSR pages and extract all embedded data.

Each wizard page at custommade.suitsupply.com/configurator?product=<Type> is a
Next.js App Router page that server-side renders the complete data payload into
self.__next_f.push(...) script tags. No auth or browser needed.

Outputs one JSON file per product type to ./data/suitsupply/.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

PRODUCT_TYPES = [
    "Suit",
    "Jacket",
    "Waistcoat",
    "Trouser",
    "Shirt",
    "Coat",
    "Tuxedo",
    "TuxedoJacket",
    "TuxedoTrouser",
    "TuxedoShirt",
]

CONFIGURATOR_URL = "https://custommade.suitsupply.com/configurator"

HEADERS = {
    "User-Agent": "tinker-tailor-spy/0.1 (data research; github.com/okalldal/tinker-tailor-spy)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# Keys we want from the big config object embedded in the RSC payload.
# The payload is a React Server Components stream; the relevant chunk is the
# one that contains "defaultSelectedFabric".
EXTRACT_KEYS = [
    # Product identity
    "defaultProduct",
    "defaultCountryCode",
    "defaultLanguage",
    "defaultClient",
    "defaultDeliveryPeriod",
    # Fabric data
    "fabricList",
    "fabricSequence",
    "fabricFilters",
    "fabricPreFilters",
    # Customization options (names, values, descriptions)
    "options",
    "optionValues",
    "translations",
    # Style presets (named configurations, e.g. Havana / Milano / Roma)
    "stylePresets",
    # Rules that drive option visibility based on fabric selection
    "businessRules",
    # Default selections and layer rendering
    "defaultSelectedFabric",
    "defaultSection",
    "defaultSelectedOptions",
    "defaultHiddenOptionsAndValues",
    "defaultSelectedMonogram",
    "defaultSelectedBaseStyle",
    "defaultValues",
    "layerDefinitions",
    # API base paths (useful for follow-up work)
    "configuratordataproviderBasePath",
    "productconfigurationBasePath",
    "productconfigurationKey",
    "productmeasurementBasePath",
    "configurationImagesBasePath",
    "addToCartWebstoreUrlTemplate",
    "cmWebstoreOrigin",
]


def fetch_page(product: str, session: requests.Session) -> str:
    resp = session.get(
        CONFIGURATOR_URL,
        params={"product": product},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def extract_rsc_payload(html: str) -> str | None:
    """Return the decoded RSC chunk that contains the configurator data."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.DOTALL)
    for chunk in chunks:
        # The RSC stream uses unicode escapes; decode once to get real JSON.
        try:
            decoded = chunk.encode().decode("unicode_escape")
        except (UnicodeDecodeError, ValueError):
            continue
        if "defaultSelectedFabric" in decoded:
            return decoded
    return None


def parse_config_object(payload: str) -> dict:
    """
    The payload is a React RSC text stream. The configurator data sits inside a
    JSX element construction that looks like:

        6:["$","$L12",null,{...big object...}]

    We find the opening of that object and use a bracket-counter to pull out
    the complete JSON object, then parse it.
    """
    marker = '"defaultSelectedFabric"'
    idx = payload.find(marker)
    if idx == -1:
        raise ValueError("defaultSelectedFabric not found in payload")

    # Walk back to find the opening '{' of the props object.
    brace_start = payload.rfind("{", 0, idx)
    if brace_start == -1:
        raise ValueError("Could not find opening brace before defaultSelectedFabric")

    # Walk forward counting braces to find the matching close.
    depth = 0
    i = brace_start
    while i < len(payload):
        if payload[i] == "{":
            depth += 1
        elif payload[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1

    raw = payload[brace_start : i + 1]
    return json.loads(raw)


def slim(obj: dict) -> dict:
    """Return only the keys we care about."""
    return {k: obj[k] for k in EXTRACT_KEYS if k in obj}


def scrape(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    for product in PRODUCT_TYPES:
        print(f"  {product}...", end=" ", flush=True)
        try:
            html = fetch_page(product, session)
            payload = extract_rsc_payload(html)
            if payload is None:
                print("SKIP — RSC payload not found")
                continue
            config = parse_config_object(payload)
            data = slim(config)
            out_path = out_dir / f"{product}.json"
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            n_fabrics = len(data.get("fabricList", {}))
            n_options = sum(
                len(ct.get("items", []))
                for ct in (data.get("options") or {}).values()
            ) if "options" in data else "?"
            print(f"ok  ({n_fabrics} fabrics, page {len(html)//1024}KB)")
        except Exception as exc:
            print(f"ERROR — {exc}")
        time.sleep(0.5)  # be polite


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/suitsupply")
    print(f"Scraping {len(PRODUCT_TYPES)} product types → {out_dir}/")
    scrape(out_dir)
    print("Done.")
