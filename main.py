# ============================================================
# ХВАТИТ ВСЕМ — БЭКЕНД v2.0 (ФИКСИРОВАННЫЕ ЦЕНЫ)
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
    version="2.0.0"
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
    """Создаёт таблицы с фиксированными ценами блюд."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenarios (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, format TEXT,
            duration INTEGER, audience TEXT, factor REAL
        )
    ''')

    # 🆕 Новая таблица: блюда с фиксированными ценами
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dishes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id TEXT,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            unit TEXT NOT NULL,
            price_per_unit REAL NOT NULL,
            adult REAL, child REAL,
            min REAL, max REAL,
            package_size REAL,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drinks (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT,
            adult REAL, child REAL, package_size REAL, price REAL
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")


def seed_database():
    """Заполняет БД. Принудительно очищает старые данные."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Принудительная очистка
    cursor.execute('DELETE FROM dishes')
    cursor.execute('DELETE FROM scenarios')
    cursor.execute('DELETE FROM drinks')
    conn.commit()

    # === Сценарии ===
    scenarios = [
        ("SC001", "День рождения - банкет", "Банкет", 4, "Взрослые", 1.00),
        ("SC002", "День рождения - домашний", "Домашний", 4, "Смешанная", 0.85),
        ("SC003", "Корпоратив", "Банкет", 5, "Взрослые", 1.05),
        ("SC004", "Свадьба", "Банкет", 6, "Взрослые", 1.10),
        ("SC005", "Юбилей", "Банкет", 5, "Взрослые", 1.05),
        ("SC006", "Выпускной", "Фуршет", 4, "Молодёжь", 0.90),
        ("SC007", "Детский праздник", "Праздник", 3, "Дети", 0.75),
        ("SC008", "Фуршет - аперитив", "Фуршет", 2, "Взрослые", 0.45),
        ("SC009", "Фуршет - замена ужина", "Фуршет", 3, "Взрослые", 0.85),
        ("SC010", "BBQ / шашлык", "BBQ", 4, "Взрослые", 1.00),
        ("SC011", "Домашний праздник", "Домашний", 4, "Смешанная", 0.95),
        ("SC012", "Деловое мероприятие", "Банкет", 3, "Взрослые", 0.85),
        ("SC013", "Праздничный стол", "Банкет", 4, "Взрослые", 1.00),
    ]
    cursor.executemany('INSERT OR REPLACE INTO scenarios VALUES (?,?,?,?,?,?)', scenarios)

    # === Блюда с фиксированными ценами ===
    # Формат: (scenario_id, category, name, unit, price_per_unit, adult, child, min, max, package_size)
    dishes = [
        # --- SC001: День рождения - банкет ---
        ("SC001", "Салаты", "Оливье", "кг", 320.0, 0.12, 0.08, 0.08, 0.16, 1.0),
        ("SC001", "Салаты", "Цезарь с курицей", "кг", 420.0, 0.10, 0.07, 0.07, 0.14, 1.0),
        ("SC001", "Холодные закуски", "Мясная нарезка", "кг", 780.0, 0.07, 0.05, 0.05, 0.10, 0.5),
        ("SC001", "Холодные закуски", "Сырная тарелка", "кг", 950.0, 0.05, 0.035, 0.035, 0.08, 0.3),
        ("SC001", "Холодные закуски", "Овощная тарелка", "кг", 180.0, 0.07, 0.05, 0.05, 0.10, 0.5),
        ("SC001", "Хлеб", "Хлеб/лаваш", "кг", 130.0, 0.10, 0.07, 0.07, 0.15, 0.4),
        ("SC001", "Горячее", "Куриное филе / рулет", "кг", 380.0, 0.18, 0.12, 0.12, 0.24, 1.0),
        ("SC001", "Горячее", "Медальон из свинины", "кг", 520.0, 0.12, 0.08, 0.08, 0.18, 1.0),
        ("SC001", "Гарнир", "Картофель по-деревенски", "кг", 180.0, 0.15, 0.10, 0.10, 0.20, 1.0),
        ("SC001", "Десерт", "Торт", "кг", 850.0, 0.15, 0.12, 0.10, 0.20, 1.0),

        # --- SC003: Корпоратив ---
        ("SC003", "Салаты", "Оливье", "кг", 320.0, 0.10, 0.07, 0.07, 0.14, 1.0),
        ("SC003", "Салаты", "Цезарь с курицей", "кг", 420.0, 0.10, 0.07, 0.07, 0.14, 1.0),
        ("SC003", "Холодные закуски", "Мясная нарезка", "кг", 780.0, 0.08, 0.055, 0.055, 0.12, 0.5),
        ("SC003", "Холодные закуски", "Сырная тарелка", "кг", 950.0, 0.06, 0.04, 0.04, 0.09, 0.3),
        ("SC003", "Горячее", "Куриное филе / рулет", "кг", 380.0, 0.18, 0.12, 0.12, 0.24, 1.0),
        ("SC003", "Горячее", "Медальон из свинины", "кг", 520.0, 0.12, 0.08, 0.08, 0.18, 1.0),
        ("SC003", "Десерт", "Торт", "кг", 850.0, 0.12, 0.10, 0.08, 0.18, 1.0),

        # --- SC004: Свадьба ---
        ("SC004", "Салаты", "Оливье", "кг", 320.0, 0.12, 0.08, 0.08, 0.16, 1.0),
        ("SC004", "Салаты", "Цезарь с курицей", "кг", 420.0, 0.12, 0.08, 0.08, 0.16, 1.0),
        ("SC004", "Холодные закуски", "Мясная нарезка", "кг", 780.0, 0.09, 0.06, 0.06, 0.13, 0.5),
        ("SC004", "Холодные закуски", "Сырная тарелка", "кг", 950.0, 0.07, 0.05, 0.05, 0.10, 0.3),
        ("SC004", "Горячее", "Куриное филе / рулет", "кг", 380.0, 0.20, 0.13, 0.13, 0.26, 1.0),
        ("SC004", "Горячее", "Медальон из свинины", "кг", 520.0, 0.15, 0.10, 0.10, 0.20, 1.0),
        ("SC004", "Гарнир", "Картофель по-деревенски", "кг", 180.0, 0.18, 0.12, 0.12, 0.22, 1.0),
        ("SC004", "Десерт", "Торт", "кг", 850.0, 0.18, 0.14, 0.12, 0.22, 1.0),

        # --- SC006: Вечеринка / Выпускной ---
        ("SC006", "Закуски", "Мини-сэндвич", "шт", 45.0, 2, 2, 1, 4, 12),
        ("SC006", "Закуски", "Мясная нарезка", "кг", 780.0, 0.08, 0.05, 0.05, 0.12, 0.5),
        ("SC006", "Горячее", "Мини-пицца", "кг", 620.0, 0.15, 0.12, 0.10, 0.20, 1.0),
        ("SC006", "Горячее", "Наггетсы", "кг", 480.0, 0.10, 0.08, 0.06, 0.14, 1.0),
        ("SC006", "Десерт", "Торт", "кг", 850.0, 0.10, 0.10, 0.08, 0.15, 1.0),

        # --- SC011: Другое / Домашний праздник ---
        ("SC011", "Салаты", "Оливье", "кг", 320.0, 0.12, 0.08, 0.08, 0.16, 1.0),
        ("SC011", "Холодные закуски", "Мясная нарезка", "кг", 780.0, 0.07, 0.05, 0.05, 0.10, 0.5),
        ("SC011", "Холодные закуски", "Сырная тарелка", "кг", 950.0, 0.05, 0.035, 0.035, 0.08, 0.3),
        ("SC011", "Холодные закуски", "Овощная тарелка", "кг", 180.0, 0.07, 0.05, 0.05, 0.10, 0.5),
        ("SC011", "Горячее", "Куриное филе / рулет", "кг", 380.0, 0.18, 0.12, 0.12, 0.24, 1.0),
        ("SC011", "Гарнир", "Картофель по-деревенски", "кг", 180.0, 0.15, 0.10, 0.10, 0.20, 1.0),
        ("SC011", "Десерт", "Торт", "кг", 850.0, 0.15, 0.12, 0.10, 0.20, 1.0),
    ]
    cursor.executemany('''
        INSERT INTO dishes (scenario_id, category, name, unit, price_per_unit, adult, child, min, max, package_size)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    ''', dishes)

    # === Напитки ===
    drinks = [
        ("D001", "Вода питьевая", "л", 0.60, 0.40, 1.5, 60),
        ("D002", "Сок яблочный", "л", 0.25, 0.15, 1.0, 120),
        ("D003", "Сок апельсиновый", "л", 0.20, 0.15, 1.0, 120),
        ("D004", "Газировка", "л", 0.30, 0.25, 1.5, 80),
        ("D005", "Морс клюквенный", "л", 0.15, 0.10, 0.5, 150),
        ("D006", "Чай чёрный", "л", 0.10, 0.05, 0.5, 60),
        ("D007", "Вода газированная", "л", 0.30, 0.20, 1.5, 50),
    ]
    cursor.executemany('INSERT OR REPLACE INTO drinks VALUES (?,?,?,?,?,?,?)', drinks)

    conn.commit()
    conn.close()
    print(f"✅ База данных заполнена: {len(scenarios)} сценариев, {len(dishes)} блюд, {len(drinks)} напитков")


# Вызываем сразу при импорте — критично для Render
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


# ============================================================
# 5. УМНЫЕ ПРОВЕРКИ
# ============================================================

class SmartChecker:
    def __init__(self, result: dict, request: CalculationRequest):
        self.result = result
        self.request = request
        self.checks: List[CheckResult] = []
        self.counter = 1

    def _add(self, severity, category, message, details=None, suggestion=None):
        self.checks.append(CheckResult(
            id=f"CHK{self.counter:04d}", severity=severity, category=category,
            message=message, details=details, suggestion=suggestion
        ))
        self.counter += 1

    def run(self):
        self._check_budget()
        self._check_food_per_person()
        self._check_drinks_volume()
        self._check_minimum_order()
        return self.checks

    def _check_budget(self):
        tc = self.result.get('total_cost', 0)
        b = self.request.budget
        if tc > b:
            self._add(Severity.ERROR, "Бюджет",
                      f"Превышение бюджета на {tc-b:.0f} ₽", None,
                      f"Увеличьте бюджет до {math.ceil(tc/1000)*1000} ₽")
        elif b - tc > b * 0.3:
            self._add(Severity.INFO, "Бюджет",
                      f"Бюджет значительно превышает стоимость",
                      {"remaining": b - tc}, "Можно добавить блюда")

    def _check_food_per_person(self):
        total_food = sum(i.get('final_amount', 0) for i in self.result['items']
                         if i.get('category') != 'Напитки' and i.get('unit') == 'кг')
        tg = self.request.adults + self.request.children
        if tg > 0:
            per = total_food / tg
            if per < 0.4:
                self._add(Severity.WARNING, "Норма на человека",
                          f"Мало еды: {per:.2f} кг/чел", None,
                          "Рекомендуется 0.5-0.8 кг")

    def _check_drinks_volume(self):
        drinks = sum(i.get('final_amount', 0) for i in self.result['items']
                     if i.get('category') == 'Напитки')
        tg = self.request.adults + self.request.children
        if tg > 0 and drinks / tg < 0.3:
            self._add(Severity.WARNING, "Напитки",
                      f"Мало напитков: {drinks/tg:.2f} л/чел", None,
                      "Рекомендуется 0.5-1.0 л")

    def _check_minimum_order(self):
        tg = self.request.adults + self.request.children
        if tg < 5:
            self._add(Severity.INFO, "Маленькая компания",
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
        SELECT category, name, unit, price_per_unit, adult, child, min, max, package_size
        FROM dishes WHERE scenario_id = ?
    ''', (request.scenario_id,))
    dishes = cursor.fetchall()

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

    for d in dishes:
        category, name, unit, price_per_unit, adult_norm, child_norm, min_norm, max_norm, package_size = d
        if not category_allowed(category):
            continue

        # Взвешенный расчёт
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
        final_amount = packages * package_size
        total_price = final_amount * price_per_unit

        items.append({
            "category": category,
            "name": name,
            "unit": unit,
            "final_amount": round(final_amount, 2),
            "packages": packages,
            "package_size": package_size,
            "total_price": round(total_price, 2),
            "cost_per_unit": price_per_unit,
        })

    # Напитки
    if has_auto or 'drinks' in prefs:
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
            final_amount = packages * package_size

            if packages > 0:
                items.append({
                    "category": "Напитки",
                    "name": name,
                    "unit": unit,
                    "final_amount": round(final_amount, 2),
                    "packages": packages,
                    "package_size": package_size,
                    "total_price": round(packages * price, 2),
                    "cost_per_unit": price,
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
        "hours": request.hours,
    }

    checker = SmartChecker(result, request)
    checks = checker.run()
    result["checks"] = checks
    result["summary"] = {
        "total": len(checks),
        "errors": sum(1 for c in checks if c.severity == Severity.ERROR),
        "warnings": sum(1 for c in checks if c.severity == Severity.WARNING),
        "info": sum(1 for c in checks if c.severity == Severity.INFO),
        "critical": 0,
    }

    return result


# ============================================================
# 7. API ЭНДПОИНТЫ
# ============================================================

@app.get("/")
def root():
    return {"message": "Хватит всем API", "version": "2.0.0"}

@app.get("/health")
def health():
    return {"status": "healthy", "version": "2.0.0"}

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
    """Показывает содержимое БД."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    result = {}
    for table in ['scenarios', 'dishes', 'drinks']:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        result[table] = cursor.fetchone()[0]
    cursor.execute('SELECT DISTINCT name, category, price_per_unit FROM dishes LIMIT 20')
    result['dishes_sample'] = [{"name": r[0], "category": r[1], "price": r[2]} for r in cursor.fetchall()]
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