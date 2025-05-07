from utils.shop_helpers import get_shop_item_data


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


def format_tool_display_name(raw_name: str) -> str:
    try:
        tool_type, material = raw_name.lower().split("_", 1)
    except ValueError:
        return raw_name  # fallback if format doesn't match

    material = material.capitalize()

    if tool_type == "pickaxe":
        return f"{material} Pickaxe"
    elif tool_type == "fishingrod":
        return f"{material} Fishing Rod"
    else:
        return raw_name
