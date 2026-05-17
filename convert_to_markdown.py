#!/usr/bin/env python3
"""Convert Suitsupply configurator JSON files to human-readable Markdown.

One .md file per product type, written to docs/.
"""

import json
from pathlib import Path

DATA_DIR = Path("data/suitsupply")
OUTPUT_DIR = Path("docs")


def ct_label(ct_id: str, layer_defs: dict) -> str:
    """Derive garment name from the layer definition fallback URL."""
    url = layer_defs["configurationTypes"][ct_id]["fallbackUrl"]
    return url.rsplit("/", 1)[-1]


def flatten_option_lookup(items: list) -> dict:
    """Return {optionId: option_name} for all options including those inside groups."""
    lookup = {}
    for item in items:
        if item["type"] == "OPTION_GROUP":
            for sub in item.get("options", []):
                lookup[sub["id"]] = sub["name"]
        elif item["type"] == "OPTION":
            lookup[item["id"]] = item["name"]
    return lookup


def format_value(val: dict) -> str:
    name = val["name"]
    code = val["code"]
    desc = (val.get("description") or "").strip()
    extra = val.get("additionalPrice")
    price_str = f" *(+€{extra['amount']})*" if extra else ""
    # Avoid repeating the name as the description
    if desc and desc != name:
        return f"- **{name}** (`{code}`){price_str} — {desc}"
    return f"- **{name}** (`{code}`){price_str}"


def render_option(item: dict, option_values: dict, h: int) -> list[str]:
    """Render a single OPTION item at heading level h."""
    lines = []
    adv = " *(advanced)*" if item.get("isAdvanced") else ""
    lines.append(f"\n{'#' * h} {item['name']}{adv}\n")
    for vid in item.get("optionValues", []):
        val = option_values.get(str(vid))
        if val:
            lines.append(format_value(val))
    return lines


def render_options_block(items: list, option_values: dict, h: int) -> list[str]:
    """Render all options for one configuration type starting at heading level h."""
    lines = []
    for item in items:
        if item["type"] == "MONOGRAM":
            continue
        if item["type"] == "OPTION_GROUP":
            lines.append(f"\n{'#' * h} {item['name']}\n")
            for sub in item.get("options", []):
                lines += render_option(sub, option_values, h + 1)
        elif item["type"] == "OPTION":
            lines += render_option(item, option_values, h)
    return lines


def render_style_presets(styles: list, option_lookup: dict, option_values: dict, h: int) -> list[str]:
    lines = [f"\n{'#' * (h - 1)} Style Presets\n"]
    for style in styles:
        lines.append(f"\n{'#' * h} {style['name'].strip()}\n")
        if style.get("description"):
            lines.append(f"*{style['description'].strip()}*\n")
        for preset in style.get("presetOptions", []):
            opt_name = option_lookup.get(preset["optionId"], f"Option {preset['optionId']}")
            val = option_values.get(str(preset["optionValueId"]))
            val_name = val["name"] if val else str(preset["optionValueId"])
            lines.append(f"- **{opt_name}:** {val_name}")
    return lines


def render_fabric_table(
    fabric_sequence: list,
    fabric_list: dict,
    ct_labels: list[tuple[str, str]],
) -> list[str]:
    price_cols = " | ".join(f"{label} Price" for _, label in ct_labels)
    header = f"| Code | Name | Color | Pattern | Composition | Weight (g/m²) | Mill | Season | Stock | {price_cols} | RTW Codes |"
    n_cols = 9 + len(ct_labels) + 1
    separator = "| " + " | ".join(["---"] * n_cols) + " |"

    lines = ["\n## Fabrics\n", header, separator]

    for fid in fabric_sequence:
        fab = fabric_list.get(str(fid))
        if fab is None:
            continue
        prices = fab.get("prices", {}).get("configurationTypes", {})
        price_cells = " | ".join(
            f"€{prices[ct_id]}" if ct_id in prices else "—"
            for ct_id, _ in ct_labels
        )
        rtw = ", ".join(fab.get("rtwProductCodes") or []) or "—"
        row = (
            f"| {fab['code']} | {fab['name']} | {fab['colorName']} | {fab['dessinName']} "
            f"| {fab['compositionText']} | {fab['weight']} | {fab['manufacturerName']} "
            f"| {fab['seasonName']} | {fab['stockStatus'].capitalize()} "
            f"| {price_cells} | {rtw} |"
        )
        lines.append(row)

    return lines


def convert(json_path: Path, output_dir: Path) -> None:
    with open(json_path) as f:
        data = json.load(f)

    product_name = data["defaultProduct"]
    delivery = data.get("defaultDeliveryPeriod", {})
    min_w = delivery.get("minDurationInWeeks")
    max_w = delivery.get("maxDurationInWeeks")

    options = data["options"]
    option_values = data["optionValues"]
    layer_defs = data["layerDefinitions"]
    fabric_list = data["fabricList"]
    fabric_sequence = data["fabricSequence"]
    style_presets = data.get("stylePresets", {}).get("configurationTypes", {})

    config_types = list(options.keys())
    ct_labels = [(ct_id, ct_label(ct_id, layer_defs)) for ct_id in config_types]
    multi = len(config_types) > 1

    lines: list[str] = [f"# {product_name}\n"]
    if min_w and max_w:
        lines.append(f"**Delivery:** {min_w}–{max_w} weeks\n")

    for ct_id, label in ct_labels:
        ct_items = options[ct_id]["items"]
        option_lookup = flatten_option_lookup(ct_items)

        if multi:
            lines.append(f"\n---\n\n## {label}\n")
            options_h = 3   # ### for options section header
            option_h = 4    # #### for individual options
            preset_h = 4    # #### for preset names (### for "Style Presets")
        else:
            options_h = 2   # ## for options section header
            option_h = 3    # ### for individual options
            preset_h = 3    # ### for preset names (## for "Style Presets")

        lines.append(f"\n{'#' * options_h} Customization Options\n")
        lines += render_options_block(ct_items, option_values, option_h)

        if ct_id in style_presets:
            styles = style_presets[ct_id].get("styles", [])
            if styles:
                lines += render_style_presets(styles, option_lookup, option_values, preset_h)

    lines += render_fabric_table(fabric_sequence, fabric_list, ct_labels)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{product_name}.md"
    out_path.write_text("\n".join(lines) + "\n")
    print(f"  {out_path}")


def main() -> None:
    print(f"Writing markdown to {OUTPUT_DIR}/")
    for json_file in sorted(DATA_DIR.glob("*.json")):
        convert(json_file, OUTPUT_DIR)
    print("Done.")


if __name__ == "__main__":
    main()
