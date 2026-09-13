MENU = {
    "id": "buffet",
    "label": "Фуршет",
    "emoji": "🍢",
    
    "categories": [
        {
            "key": "snacks",
            "name": "Холодные закуски",
            "emoji": "🧀",
            "filterable": True,
            "portion_norm": 5.5,
        },
        {
            "key": "salads",
            "name": "Салаты",
            "emoji": "🥗",
            "filterable": True,
            "portion_norm": 1.5,
        },
        {
            "key": "hot",
            "name": "Горячие закуски",
            "emoji": "🥩",
            "filterable": True,
            "portion_norm": 1.5,
        },
        {
            "key": "drinks",
            "name": "Напитки",
            "emoji": "🥤",
            "filterable": False,
            "portion_norm": 2.5,
        },
    ],
    
    "counts_by_duration": {
        2: {"snacks": 4, "salads": 2, "hot": 2, "drinks": 3},
        4: {"snacks": 6, "salads": 3, "hot": 3, "drinks": 4},
        6: {"snacks": 8, "salads": 4, "hot": 4, "drinks": 5},
        8: {"snacks": 10, "salads": 5, "hot": 5, "drinks": 6},
    },
}