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
        return SHOP_ITEMS.get("tools", {}).get(tool_type, {}).get(variant)

    return None


def get_tool_bonus(item_key: str) -> float:
    """
    Retrieves the bonus percentage for an equipped tool like 'pickaxe_stone'.

    :param item_key: The full item key (e.g., 'pickaxe_stone')
    :return: The bonus as a float (e.g., 0.2), or 0.0 if not found
    """
    item_data = get_shop_item_data(item_key)
    if item_data and "bonus" in item_data:
        return item_data["bonus"]
    return 0.0
