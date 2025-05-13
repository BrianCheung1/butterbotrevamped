def calculate_work_bonuses(base_value: int, level: int, tool_bonus_pct: float):
    tool_bonus = int(base_value * tool_bonus_pct)
    level_bonus = int((level * 0.05) * base_value)
    return tool_bonus, level_bonus
