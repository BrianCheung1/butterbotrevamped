def apply_buff(
    base_value: float, buffs: dict, buff_key: str, *, additive: bool = False
) -> float:
    """
    Apply a buff to a base value.

    Args:
        base_value (float): The value before applying the buff.
        buffs (dict): The user's active buffs.
        buff_key (str): The key of the buff to apply.
        additive (bool): If True, applies as additive bonus. Else, applies as multiplier.

    Returns:
        float: The modified value.
    """
    buff = buffs.get(buff_key)
    if not buff:
        return base_value

    if additive:
        return base_value + buff.get("bonus", 0.0)
    else:
        return base_value * (buff.get("multiplier", 1.0))
