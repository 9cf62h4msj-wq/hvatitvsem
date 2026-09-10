# ============================================================
# ХВАТИТ ВСЕМ — БЭКЕНД v1.3 (STABLE + PRICES FIXED)
# FastAPI + SQLite
# ============================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import sqlite3
import math
import os
from enum import Enum

# ============================================================
# 1. ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ
# ============================================================

app = FastAPI(
    title="Хватит всем API",
    description="API для расчёта еды на мероприятия",
    version="1.3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'hvatit_vsem.db')

# ============================================================
# 2. МОДЕЛИ ДАННЫХ
# ============================================================

class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class CheckResult(BaseModel):
    id: str
    severity: Severity
    category: str
    message: str
    details: Optional[Dict[str, Any]] = None
    suggestion: Optional[str] = None

class CalculationRequest(BaseModel):
    scenario_id: str
    adults: int
    children: int
    hours: int
    budget: float
    preferences: List[str] = []

class CalculationResponse(BaseModel):
    items: List[dict]
    total_cost: float
    budget: float
    is_within_budget: bool
    shortfall: float
    remaining: float
    adults: int
    children: int
    total_guests: int
    scenario: str
    hours: int
    checks: List[CheckResult] = []
    summary: Dict[str, int] = {}

# ============================================================
# 3. СОЗДАНИЕ И ЗАПОЛНЕНИЕ БАЗЫ ДАННЫХ
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenarios (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, format TEXT,
            duration INTEGER, audience TEXT, factor REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS norms (
            id INTEGER PRIMARY KEY AUTOINCREMENT, scenario_id TEXT,
            category TEXT, name TEXT, unit TEXT, adult REAL, child REAL,
            min REAL, max REAL, package_size REAL,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT,
            unit TEXT, price REAL, source TEXT, date TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, dish_name TEXT,
            ingredient_id TEXT, amount REAL, unit TEXT,
            FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drinks (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT,
            adult REAL, child REAL, package_size REAL, price REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT,
            scenario_id TEXT, adults INTEGER, children INTEGER, hours INTEGER,
            calculated_cost REAL, actual_cost REAL, eaten REAL, leftover REAL,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")


def seed_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM scenarios')
    if cursor.fetchone()[0] > 0:
        conn.close()
        print("✅ Данные уже есть, пропускаем заполнение")
        return

    # === Сценарии ===
    scenarios = [
        {"id": "SC001", "name": "День рождения - банкет", "format": "Банкет", "duration": 4, "audience": "Взрослые", "factor": 1.00},
        {"id": "SC002", "name": "День рождения - домашний", "format": "Домашний", "duration": 4, "audience": "Смешанная", "factor": 0.85},
        {"id": "SC003", "name": "Корпоратив", "format": "Банкет", "duration": 5, "audience": "Взрослые", "factor": 1.05},
        {"id": "SC004", "name": "Свадьба", "format": "Банкет", "duration": 6, "audience": "Взрослые", "factor": 1.10},
        {"id": "SC005", "name": "Юбилей", "format": "Банкет", "duration": 5, "audience": "Взрослые", "factor": 1.05},
        {"id": "SC006", "name": "Выпускной", "format": "Фуршет", "duration": 4, "audience": "Молодёжь", "factor": 0.90},
        {"id": "SC007", "name": "Детский праздник", "format": "Праздник", "duration": 3, "audience": "Дети", "factor": 0.75},
        {"id": "SC008", "name": "Фуршет - аперитив", "format": "Фуршет", "duration": 2, "audience": "Взрослые", "factor": 0.45},
        {"id": "SC009", "name": "Фуршет - замена ужина", "format": "Фуршет", "duration": 3, "audience": "Взрослые", "factor": 0.85},
        {"id": "SC010", "name": "BBQ / шашлык", "format": "BBQ", "duration": 4, "audience": "Взрослые", "factor": 1.00},
        {"id": "SC011", "name": "Домашний праздник", "format": "Домашний", "duration": 4, "audience": "Смешанная", "factor": 0.95},
        {"id": "SC012", "name": "Деловое мероприятие", "format": "Банкет", "duration": 3, "audience": "Взрослые", "factor": 0.85},
        {"id": "SC013", "name": "Праздничный стол", "format": "Банкет", "duration": 4, "audience": "Взрослые", "factor": 1.00}
    ]
    for s in scenarios:
        cursor.execute('INSERT OR REPLACE INTO scenarios VALUES (?,?,?,?,?,?)',
                       (s['id'], s['name'], s['format'], s['duration'], s['audience'], s['factor']))

    # === Нормы ===
    norms = {
        "SC001": [
            ("Салаты", "Оливье", "кг", 0.12, 0.08, 0.08, 0.16, 1.0),
            ("Салаты", "Цезарь с курицей", "кг", 0.10, 0.07, 0.07, 0.14, 1.0),
            ("Холодные закуски", "Мясная нарезка", "кг", 0.07, 0.05, 0.05, 0.10, 0.5),
            ("Холодные закуски", "Сырная тарелка", "кг", 0.05, 0.035, 0.035, 0.08, 0.5),
            ("Холодные закуски", "Овощная тарелка", "кг", 0.07, 0.05, 0.05, 0.10, 0.5),
            ("Хлеб", "Хлеб/лаваш", "кг", 0.10, 0.07, 0.07, 0.15, 0.4),
            ("Горячее", "Куриное филе / рулет", "кг", 0.18, 0.12, 0.12, 0.24, 1.0),
            ("Гарнир", "Картофель по-деревенски", "кг", 0.15, 0.10, 0.10, 0.20, 1.0),
            ("Десерт", "Торт", "кг", 0.15, 0.12, 0.10, 0.20, 1.0)
        ],
        "SC003": [
            ("Салаты", "Оливье", "кг", 0.10, 0.07, 0.07, 0.14, 1.0),
            ("Салаты", "Цезарь с курицей", "кг", 0.10, 0.07, 0.07, 0.14, 1.0),
            ("Холодные закуски", "Мясная нарезка", "кг", 0.08, 0.055, 0.055, 0.12, 0.5),
            ("Холодные закуски", "Сырная тарелка", "кг", 0.06, 0.04, 0.04, 0.09, 0.5),
            ("Горячее", "Куриное филе / рулет", "кг", 0.18, 0.12, 0.12, 0.24, 1.0),
            ("Горячее", "Медальон из свинины", "кг", 0.12, 0.08, 0.08, 0.18, 1.0),
            ("Десерт", "Торт", "кг", 0.12, 0.10, 0.08, 0.18, 1.0)
        ],
        "SC004": [
            ("Салаты", "Оливье", "кг", 0.12, 0.08, 0.08, 0.16, 1.0),
            ("Салаты", "Цезарь с курицей", "кг", 0.12, 0.08, 0.08, 0.16, 1.0),
            ("Холодные закуски", "Мясная нарезка", "кг", 0.09, 0.06, 0.06, 0.13, 0.5),
            ("Холодные закуски", "Сырная тарелка", "кг", 0.07, 0.05, 0.05, 0.10, 0.5),
            ("Горячее", "Куриное филе / рулет", "кг", 0.20, 0.13, 0.13, 0.26, 1.0),
            ("Горячее", "Медальон из свинины", "кг", 0.15, 0.10, 0.10, 0.20, 1.0),
            ("Гарнир", "Картофель по-деревенски", "кг", 0.18, 0.12, 0.12, 0.22, 1.0),
            ("Десерт", "Торт", "кг", 0.18, 0.14, 0.12, 0.22, 1.0)
        ],
        "SC006": [
            ("Закуски", "Мини-сэндвич", "шт", 2, 2, 1, 4, 12),
            ("Закуски", "Мясная нарезка", "кг", 0.08, 0.05, 0.05, 0.12, 0.5),
            ("Горячее", "Мини-пицца", "кг", 0.15, 0.12, 0.10, 0.20, 1.0),
            ("Горячее", "Наггетсы", "кг", 0.10, 0.08, 0.06, 0.14, 1.0),
            ("Десерт", "Торт", "кг", 0.10, 0.10, 0.08, 0.15, 1.0)
        ],
        "SC011": [
            ("Салаты", "Оливье", "кг", 0.12, 0.08, 0.08, 0.16, 1.0),
            ("Холодные закуски", "Мясная нарезка", "кг", 0.07, 0.05, 0.05, 0.10, 0.5),
            ("Холодные закуски", "Сырная тарелка", "кг", 0.05, 0.035, 0.035, 0.08, 0.5),
            ("Холодные закуски", "Овощная тарелка", "кг", 0.07, 0.05, 0.05, 0.10, 0.5),
            ("Горячее", "Куриное филе / рулет", "кг", 0.18, 0.12, 0.12, 0.24, 1.0),
            ("Гарнир", "Картофель по-деревенски", "кг", 0.15, 0.10, 0.10, 0.20, 1.0),
            ("Десерт", "Торт", "кг", 0.15, 0.12, 0.10, 0.20, 1.0)
        ]
    }
    for scenario_id, norm_list in norms.items():
        for n in norm_list:
            cursor.execute('''
                INSERT INTO norms (scenario_id, category, name, unit, adult, child, min, max, package_size)
                VALUES (?,?,?,?,?,?,?,?,?)
            ''', (scenario_id, *n))

    # === Ингредиенты ===
    ingredients = [
        ("I001", "Картофель", "Овощи", "кг", 49.02, "База сервиса", "06.09.2026"),
        ("I002", "Куриное филе", "Мясо", "кг", 253.49, "База сервиса", "06.09.2026"),
        ("I003", "Свинина", "Мясо", "кг", 420.93, "База сервиса", "06.09.2026"),
        ("I004", "Сыр твердый", "Молочные", "кг", 912.45, "База сервиса", "06.09.2026"),
        ("I005", "Хлеб пшеничный", "Хлеб", "кг", 133.95, "База сервиса", "06.09.2026"),
        ("I006", "Масло подсолнечное", "Жиры", "кг", 163.85, "База сервиса", "06.09.2026"),
        ("I007", "Колбаса вареная", "Мясо", "кг", 541.95, "База сервиса", "06.09.2026"),
        ("I008", "Морковь", "Овощи", "кг", 55.00, "База сервиса", "06.09.2026"),
        ("I009", "Огурцы маринованные", "Овощи", "кг", 220.00, "База сервиса", "06.09.2026"),
        ("I010", "Яйца", "Молочные", "шт", 12.00, "База сервиса", "06.09.2026"),
        ("I011", "Горошек консервированный", "Консервы", "кг", 220.00, "База сервиса", "06.09.2026"),
        ("I012", "Майонез", "Соусы", "кг", 250.00, "База сервиса", "06.09.2026"),
        ("I013", "Торт готовый", "Кондитерские", "кг", 850.00, "База сервиса", "06.09.2026"),
        ("I014", "Овощи свежие (микс)", "Овощи", "кг", 180.00, "База сервиса", "06.09.2026"),
        ("I015", "Мясная нарезка (готовая)", "Мясо", "кг", 780.00, "База сервиса", "06.09.2026"),
        ("I016", "Сырная тарелка (готовая)", "Молочные", "кг", 950.00, "База сервиса", "06.09.2026"),
        ("I017", "Пицца готовая", "Готовые блюда", "кг", 620.00, "База сервиса", "06.09.2026"),
        ("I018", "Наггетсы", "Готовые блюда", "кг", 480.00, "База сервиса", "06.09.2026"),
    ]
    for i in ingredients:
        cursor.execute('INSERT OR REPLACE INTO ingredients VALUES (?,?,?,?,?,?,?)', i)

    # === РЕЦЕПТЫ (добавлены недостающие!) ===
    recipes = [
        # Оливье
        ("Оливье", "I001", 0.045, "кг"),
        ("Оливье", "I008", 0.015, "кг"),
        ("Оливье", "I009", 0.015, "кг"),
        ("Оливье", "I010", 0.12, "шт"),
        ("Оливье", "I011", 0.015, "кг"),
        ("Оливье", "I007", 0.025, "кг"),
        ("Оливье", "I012", 0.020, "кг"),
        # Куриное филе / рулет
        ("Куриное филе / рулет", "I002", 0.170, "кг"),
        ("Куриное филе / рулет", "I006", 0.005, "кг"),
        # Медальон из свинины
        ("Медальон из свинины", "I003", 0.120, "кг"),
        ("Медальон из свинины", "I006", 0.005, "кг"),
        # Картофель по-деревенски
        ("Картофель по-деревенски", "I001", 0.130, "кг"),
        ("Картофель по-деревенски", "I006", 0.008, "кг"),
        # Хлеб/лаваш
        ("Хлеб/лаваш", "I005", 0.100, "кг"),
        # Цезарь с курицей
        ("Цезарь с курицей", "I002", 0.035, "кг"),
        ("Цезарь с курицей", "I004", 0.005, "кг"),
        # Греческий (на всякий случай)
        ("Греческий", "I004", 0.015, "кг"),
        ("Греческий", "I006", 0.003, "кг"),
        # 🆕 НОВЫЕ рецепты для блюд из SC001, SC003, SC004, SC011:
        ("Мясная нарезка", "I015", 0.070, "кг"),
        ("Сырная тарелка", "I016", 0.050, "кг"),
        ("Овощная тарелка", "I014", 0.070, "кг"),
        ("Торт", "I013", 0.150, "кг"),
        ("Мини-пицца", "I017", 0.150, "кг"),
        ("Наггетсы", "I018", 0.100, "кг"),
        ("Мини-сэндвич", "I005", 0.030, "кг"),
        ("Мини-сэндвич", "I007", 0.020, "кг"),
    ]
    for r in recipes:
        cursor.execute('INSERT INTO recipes (dish_name, ingredient_id, amount, unit) VALUES (?,?,?,?)', r)

    # === Напитки ===
    drinks = [
        ("D001", "Вода питьевая", "л", 0.60, 0.40, 1.5, 60),
        ("D002", "Сок яблочный", "л", 0.25, 0.15, 1.0, 120),
        ("D003", "Сок апельсиновый", "л", 0.20, 0.15, 1.0, 120),
        ("D004", "Газировка", "л", 0.30, 0.25, 1.5, 80),
        ("D005", "Морс клюквенный", "л", 0.15, 0.10, 0.5, 150),
        ("D006", "Чай чёрный", "л", 0.10, 0.05, 0.5, 60),
        ("D007", "Вода газированная", "л", 0.30, 0.20, 1.5, 50)
    ]
    for d in drinks:
        cursor.execute('INSERT OR REPLACE INTO drinks VALUES (?,?,?,?,?,?,?)', d)

    conn.commit()
    conn.close()
    print("✅ База данных заполнена начальными данными")


# Вызываем сразу при импорте — это критично для Render
init_db()
seed_database()


# ============================================================
# 4. ФУНКЦИИ РАСЧЁТА
# ============================================================

def get_duration_factor(hours):
    if hours <= 2: return 1.00
    if hours <= 4: return 1.10
    if hours <= 6: return 1.20
    return 1.30

def get_drinks_duration_factor(hours):
    if hours <= 2: return 1.00
    if hours <= 4: return 1.30
    if hours <= 6: return 1.60
    return 2.00

def get_packages(amount, package_size):
    if not amount or amount <= 0 or not package_size:
        return 0
    return math.ceil(amount / package_size)

def get_actual_amount(packages, package_size):
    return packages * package_size


def calculate_dish_cost(dish_name, conn):
    """
    Считает стоимость блюда.
    Если рецепта нет — берёт среднюю цену ингредиентов категории "Готовые блюда".
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.amount, r.unit, i.price
        FROM recipes r
        JOIN ingredients i ON r.ingredient_id = i.id
        WHERE r.dish_name = ?
    ''', (dish_name,))
    recipe = cursor.fetchall()

    if recipe:
        total = 0.0
        for amount, unit, price in recipe:
            if price is None:
                continue
            if unit == 'кг':
                total += amount * price
            elif unit == 'г':
                total += (amount / 1000) * price
            else:
                total += amount * price
        return total

    # 🆕 ФОЛБЭК: если рецепта нет — возвращаем осмысленную цену по названию блюда
    fallback_prices = {
        "торт": 850.0, "пицца": 620.0, "наггетсы": 480.0,
        "нарезка": 780.0, "сырная": 950.0, "овощная": 180.0,
        "сэндвич": 400.0, "салат": 300.0, "закуска": 500.0,
    }
    name_lower = dish_name.lower()
    for keyword, price in fallback_prices.items():
        if keyword in name_lower:
            return price
    return 200.0  # безопасная средняя цена


# ============================================================
# 5. УМНЫЕ ПРОВЕРКИ
# ============================================================

class SmartChecker:
    def __init__(self, result: dict, request: CalculationRequest):
        self.result = result
        self.request = request
        self.checks: List[CheckResult] = []
        self.check_id_counter = 1

    def _add_check(self, severity, category, message, details=None, suggestion=None):
        self.checks.append(CheckResult(
            id=f"CHK{self.check_id_counter:04d}",
            severity=severity, category=category,
            message=message, details=details, suggestion=suggestion
        ))
        self.check_id_counter += 1

    def run_all_checks(self):
        self._check_total_food()
        self._check_food_per_person()
        self._check_category_balance()
        self._check_budget()
        self._check_package_efficiency()
        self._check_drinks_volume()
        self._check_minimum_order()
        return self.checks

    def _check_total_food(self):
        total_food = sum(i.get('final_amount', 0) for i in self.result['items']
                         if i.get('category') != 'Напитки' and i.get('unit') == 'кг')
        tg = self.request.adults + self.request.children
        if tg > 0 and total_food > 1.2 * tg:
            self._add_check(Severity.WARNING, "Объём еды",
                            f"Много еды: {total_food:.2f} кг на {tg} гостей",
                            {"per_person": total_food/tg}, "Можно уменьшить порции")

    def _check_food_per_person(self):
        total_food = sum(i.get('final_amount', 0) for i in self.result['items']
                         if i.get('category') != 'Напитки' and i.get('unit') == 'кг')
        tg = self.request.adults + self.request.children
        if tg > 0:
            per = total_food / tg
            if per < 0.4:
                self._add_check(Severity.WARNING, "Норма на человека",
                                f"Мало еды: {per:.2f} кг/чел", None,
                                "Рекомендуется 0.5-0.8 кг")

    def _check_category_balance(self):
        cats = {}
        for i in self.result['items']:
            if i.get('category') != 'Напитки':
                cats[i['category']] = cats.get(i['category'], 0) + i.get('final_amount', 0)
        if cats and 'Салаты' not in cats:
            self._add_check(Severity.WARNING, "Баланс категорий", "В меню нет салатов",
                            {"categories": list(cats.keys())}, "Добавьте салат")

    def _check_budget(self):
        tc = self.result.get('total_cost', 0)
        b = self.request.budget
        if tc > b:
            self._add_check(Severity.ERROR, "Бюджет",
                            f"Превышение бюджета на {tc-b:.0f} ₽", None,
                            f"Увеличьте бюджет до {math.ceil(tc/1000)*1000} ₽")

    def _check_package_efficiency(self):
        waste = 0
        for i in self.result['items']:
            if i.get('package_size', 0) > 0 and i.get('packages', 0) > 0:
                final = i.get('final_amount', 0)
                total = i['packages'] * i['package_size']
                if total > 0 and (total - final) / total > 0.4:
                    waste += 1
        if waste > 2:
            self._add_check(Severity.WARNING, "Упаковки",
                            f"{waste} позиций с большим остатком", None,
                            "Выберите меньшие фасовки")

    def _check_drinks_volume(self):
        drinks = sum(i.get('final_amount', 0) for i in self.result['items']
                     if i.get('category') == 'Напитки')
        tg = self.request.adults + self.request.children
        if tg > 0 and drinks / tg < 0.3:
            self._add_check(Severity.WARNING, "Напитки",
                            f"Мало напитков: {drinks/tg:.2f} л/чел", None,
                            "Рекомендуется 0.5-1.0 л")

    def _check_minimum_order(self):
        tg = self.request.adults + self.request.children
        if tg < 5:
            self._add_check(Severity.INFO, "Маленькая компания",
                            f"Всего {tg} гостей", None, "Возможен перерасчёт упаковок")


# ============================================================
# 6. ОСНОВНОЙ РАСЧЁТ
# ============================================================

def calculate_menu_with_checks(request: CalculationRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM scenarios WHERE id = ?', (request.scenario_id,))
    scenario = cursor.fetchone()
    if not scenario:
        conn.close()
        raise HTTPException(status_code=404, detail="Сценарий не найден")

    cursor.execute('''
        SELECT category, name, unit, adult, child, min, max, package_size
        FROM norms WHERE scenario_id = ?
    ''', (request.scenario_id,))
    norms = cursor.fetchall()

    cursor.execute('SELECT name, unit, adult, child, package_size, price FROM drinks')
    drinks = cursor.fetchall()

    duration_factor = get_duration_factor(request.hours)
    drinks_factor = get_drinks_duration_factor(request.hours)
    total_guests = request.adults + request.children
    scenario_factor = scenario[5]

    # Учёт предпочтений
    prefs = request.preferences or []
    has_auto = 'auto' in prefs or not prefs

    def category_allowed(cat):
        if has_auto:
            return True
        c = cat.lower()
        if 'meat' in prefs and ('горяч' in c or 'мясо' in c or 'закус' in c):
            return True
        if 'snacks' in prefs and ('закус' in c or 'холодн' in c or 'хлеб' in c):
            return True
        if 'veg' in prefs and ('салат' in c or 'овощ' in c or 'гарнир' in c):
            return True
        if 'sweet' in prefs and ('десерт' in c or 'сладк' in c):
            return True
        if 'fish' in prefs and 'рыб' in c:
            return True
        return False

    items = []

    for norm in norms:
        category, name, unit, adult_norm, child_norm, min_norm, max_norm, package_size = norm
        if not category_allowed(category):
            continue

        # Взвешенный расчёт: взрослые + дети
        if request.adults > 0 and request.children > 0:
            norm_value = (adult_norm * request.adults + child_norm * request.children) / total_guests
        elif request.adults > 0:
            norm_value = adult_norm
        else:
            norm_value = child_norm

        total_amount = total_guests * norm_value * duration_factor * scenario_factor
        min_amount = min_norm * total_guests * duration_factor * scenario_factor
        final_amount = max(total_amount, min_amount)
        packages = get_packages(final_amount, package_size)
        final_amount = get_actual_amount(packages, package_size)
        cost_per_unit = calculate_dish_cost(name, conn)
        total_price = final_amount * cost_per_unit

        items.append({
            "category": category,
            "name": name,
            "unit": unit,
            "final_amount": round(final_amount, 2),
            "packages": packages,
            "package_size": package_size,
            "min": min_norm,
            "max": max_norm,
            "total_price": round(total_price, 2),
            "cost_per_unit": round(cost_per_unit, 2)
        })

    # Напитки
    add_drinks = has_auto or 'drinks' in prefs
    if add_drinks:
        for drink in drinks:
            name, unit, adult_norm, child_norm, package_size, price = drink
            if request.adults > 0 and request.children > 0:
                norm_value = (adult_norm * request.adults + child_norm * request.children) / total_guests
            elif request.adults > 0:
                norm_value = adult_norm
            else:
                norm_value = child_norm

            total_amount = total_guests * norm_value * drinks_factor
            packages = get_packages(total_amount, package_size)
            final_amount = get_actual_amount(packages, package_size)

            if packages > 0:
                items.append({
                    "category": "Напитки",
                    "name": name,
                    "unit": unit,
                    "final_amount": round(final_amount, 2),
                    "packages": packages,
                    "package_size": package_size,
                    "min": 0, "max": 0,
                    "total_price": round(packages * price, 2),
                    "cost_per_unit": price
                })

    total_cost = sum(item["total_price"] for item in items)
    conn.close()

    result = {
        "items": items,
        "total_cost": round(total_cost, 2),
        "budget": request.budget,
        "is_within_budget": total_cost <= request.budget,
        "shortfall": round(max(0, total_cost - request.budget), 2),
        "remaining": round(max(0, request.budget - total_cost), 2),
        "adults": request.adults,
        "children": request.children,
        "total_guests": total_guests,
        "scenario": scenario[1],
        "hours": request.hours
    }

    checker = SmartChecker(result, request)
    checks = checker.run_all_checks()

    result["checks"] = checks
    result["summary"] = {
        "total": len(checks),
        "errors": sum(1 for c in checks if c.severity == Severity.ERROR),
        "warnings": sum(1 for c in checks if c.severity == Severity.WARNING),
        "info": sum(1 for c in checks if c.severity == Severity.INFO),
        "critical": 0
    }

    return result


# ============================================================
# 7. API ЭНДПОИНТЫ
# ============================================================

@app.get("/")
def root():
    return {"message": "Хватит всем API", "version": "1.3.0"}

@app.get("/health")
def health():
    return {"status": "healthy", "version": "1.3.0"}

@app.get("/scenarios")
def get_scenarios():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, format, duration, audience, factor FROM scenarios')
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "format": r[2], "duration": r[3], "audience": r[4], "factor": r[5]} for r in rows]

@app.get("/debug/db")
def debug_db():
    """Отладочный эндпоинт — показывает содержимое БД."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    result = {}
    for table in ['scenarios', 'norms', 'ingredients', 'recipes', 'drinks']:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        result[table] = cursor.fetchone()[0]
    cursor.execute('SELECT DISTINCT dish_name FROM recipes')
    result['recipe_dishes'] = [r[0] for r in cursor.fetchall()]
    cursor.execute('SELECT id, name, price FROM ingredients WHERE price > 0 LIMIT 20')
    result['ingredients_sample'] = [{"id": r[0], "name": r[1], "price": r[2]} for r in cursor.fetchall()]
    conn.close()
    return result

@app.post("/calculate", response_model=CalculationResponse)
def calculate(request: CalculationRequest):
    return calculate_menu_with_checks(request)

# ============================================================
# 8. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Запуск на http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)