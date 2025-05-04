from constants.shop_config import SHOP_ITEMS


def get_all_shop_items():
    items = []

    # Non-tool items (like bank_upgrade)
    for key, data in SHOP_ITEMS.items():
        if key != "tools":
            items.append((key, data))

    # Tools (flattened with prefixed keys like "pickaxe_stone")
    for tool_type, variants in SHOP_ITEMS.get("tools", {}).items():
        for variant_key, variant_data in variants.items():
            full_key = f"{tool_type}_{variant_key}"
            items.append((full_key, variant_data))

    return items


def get_shop_item_data(item_key: str):
    if item_key in SHOP_ITEMS:
        return SHOP_ITEMS[item_key]

    if "_" in item_key:
        tool_type, variant = item_key.split("_", 1)
        print(tool_type, variant)
        return SHOP_ITEMS.get("tools", {}).get(tool_type, {}).get(variant)

    return None
