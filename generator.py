import hashlib
import math
import random

PREF_TAGS = {
    "meat": "meat",
    "fish": "fish",
    "veg":  "veg",
}


def make_seed(payload: dict, reroll: int = 0) -> int:
    key = "|".join([
        str(payload.get("event_type", "")),
        str(payload.get("duration_hours", 0)),
        str(payload.get("adults", 0)),
        str(payload.get("children", 0)),
        str(payload.get("budget", 0)),
        ",".join(sorted(payload.get("preferences", []))),
        str(reroll),
    ])
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def active_tags(preferences: list) -> set:
    """Возвращает множество активных тегов. Если auto или пусто — None (без фильтра)."""
    if not preferences or "auto" in preferences:
        return None
    tags = set()
    for p in preferences:
        if p in PREF_TAGS:
            tags.add(PREF_TAGS[p])
    return tags if tags else None


def filter_by_tags(dishes: list, tags: set) -> list:
    """Оставляет блюда, у которых есть хотя бы один из тегов. Блюда без тегов — всегда."""
    if tags is None:
        return list(dishes)
    return [d for d in dishes if (set(d["tags"]) & tags) or not d.get("tags")]


def weighted_pick(pool: list, k: int, rng: random.Random) -> list:
    """Выбор k блюд без повторов (у всех вес 1 — равномерно)."""
    pool = list(pool)
    chosen = []
    for _ in range(min(k, len(pool))):
        pick = rng.choice(pool)
        chosen.append(pick)
        pool.remove(pick)
    return chosen


def generate_menu(menu_config: dict, dishes: dict, payload: dict, reroll: int = 0) -> dict:
    seed = make_seed(payload, reroll)
    rng = random.Random(seed)
    
    duration = payload["duration_hours"]
    # нормализуем в 2/4/6/8
    if duration <= 2:
        dur_key = 2
    elif duration <= 4:
        dur_key = 4
    elif duration <= 6:
        dur_key = 6
    else:
        dur_key = 8
    
    counts = menu_config["counts_by_duration"][dur_key]
    effective_guests = payload["adults"] + payload["children"] * 0.6
    
    pref_tags = active_tags(payload.get("preferences", []))
    
    categories_out = []
    total = 0
    
    for cat in menu_config["categories"]:
        cat_key = cat["key"]
        need_count = counts[cat_key]
        
        # Пул блюд категории
        pool = dishes.get(cat_key, [])
        
        # Фильтр по предпочтениям (если категория фильтруемая)
        if cat["filterable"]:
            filtered = filter_by_tags(pool, pref_tags)
        else:
            filtered = list(pool)
        
        # ВАРИАНТ В: если фильтр дал меньше, чем нужно — добираем и помечаем
        extra_items = []
        if len(filtered) < need_count:
            filtered_ids = {d["id"] for d in filtered}
            extra_pool = [d for d in pool if d["id"] not in filtered_ids]
            need_extra = need_count - len(filtered)
            extra_items = weighted_pick(extra_pool, need_extra, rng)
            # помечаем
            extra_items = [{**d, "off_filter": True} for d in extra_items]
        
        # Основной выбор
        main_picked = weighted_pick(filtered, need_count - len(extra_items), rng) if filtered else []
        chosen = main_picked + extra_items
        
        # Сортировка: дорогие сверху
        chosen.sort(key=lambda d: -d["price"])
        
        # Расчёт порций (Вариант Б)
        portion_count = math.ceil(effective_guests * cat["portion_norm"] / max(1, need_count))
        
        items = []
        cat_total = 0
        for d in chosen:
            line_total = portion_count * d["price"]
            items.append({
                "id": d["id"],
                "name": d["name"],
                "sub": d.get("sub", ""),
                "tags": d.get("tags", []),
                "price": d["price"],
                "portions": portion_count,
                "total": line_total,
                "off_filter": d.get("off_filter", False),
            })
            cat_total += line_total
        
        categories_out.append({
            "key": cat_key,
            "name": cat["name"],
            "emoji": cat["emoji"],
            "items": items,
            "subtotal": cat_total,
        })
        total += cat_total
    
    return {
        "categories": categories_out,
        "total": total,
        "seed": seed,
        "duration_bucket": dur_key,
    }