from constants.shop_config import SHOP_ITEMS


def get_all_shop_items():
    items = []

    # Non-tool items (like bank_upgrade)
    for key, data in SHOP_ITEMS.items():
        if key != "tools" and key != "buffs":
            items.append((key, data))

    # Tools (flattened with prefixed keys like "pickaxe_stone")
    for tool_type, variants in SHOP_ITEMS.get("tools", {}).items():
        for variant_key, variant_data in variants.items():
            full_key = f"{tool_type}_{variant_key}"
            items.append((full_key, variant_data))

    # Buffs - Separate each buff category to make it clearer if needed
    for buff_category, buffs in SHOP_ITEMS.get("buffs", {}).items():
        for buff_key, buff_data in buffs.items():
            # Optionally, you can categorize buffs here
            items.append((f"{buff_category}_{buff_key}", buff_data))

    return items


def get_shop_item_data(item_key: str):
    if item_key in SHOP_ITEMS:
        return SHOP_ITEMS[item_key]

    if "_" in item_key:
        # Split the key to check for tool or buff
        parts = item_key.split("_", 1)
        if len(parts) > 1:
            if parts[0] == "pickaxe" or parts[0] == "fishingrod":
                tool_type, variant = parts
                return SHOP_ITEMS.get("tools", {}).get(tool_type, {}).get(variant)
            elif parts[0] == "exp" or parts[0] == "steal":
                buff_category, buff_key = parts
                return SHOP_ITEMS.get("buffs", {}).get(buff_category, {}).get(buff_key)

    return None
