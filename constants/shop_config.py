SHOP_ITEMS = {
    "bank_upgrade": {
        "name": "Bank Upgrade",
        "description": "Increases your bank cap by $500,000.",
        "base_price": 500_000,
        "price_increment": 500_000,
        "effect": "bank_cap_increase",
    },
    "tools": {
        "pickaxe": {
            "wooden": {
                "name": "Wooden Pickaxe",
                "description": "Increases your mining bonus by 10%",
                "price": 10_000,
                "effect": "mining_bonus_increase",
                "level_required": 10,
                "bonus": 0.10,
            },
            "stone": {
                "name": "Stone Pickaxe",
                "description": "Increases your mining bonus by 20%",
                "price": 20_000,
                "effect": "mining_bonus_increase",
                "level_required": 20,
                "bonus": 0.20,
            },
        },
        "fishingrod": {
            "wooden": {
                "name": "Wooden Rod",
                "description": "Increases your fishing bonus by 10%",
                "price": 10_000,
                "effect": "fishing_bonus_increase",
                "level_required": 5,
                "bonus": 0.10,
            },
        },
    },
}
