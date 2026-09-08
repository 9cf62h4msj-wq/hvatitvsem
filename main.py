# ============================================================
# ХВАТИТ ВСЕМ — БЭКЕНД v1.1
# FastAPI + SQLite
# ============================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import sqlite3
import math
import os
from datetime import datetime
from enum import Enum

# ============================================================
# 1. ИНИЦИАЛИЗАЦИЯ
# ============================================================
from fastapi.middleware.cors import CORSMiddleware

from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI

# Создаем приложение
app = FastAPI()  # <--- ВОТ ЗДЕСЬ создается "app"

# Добавляем CORS (это можно делать сразу после создания app)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app = FastAPI(
    title="Хватит всем API",
    description="API для расчёта еды на мероприятия",
    version="1.1.0"
)

# CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = 'hvatit_vsem.db'

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
# 3. БАЗА ДАННЫХ
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenarios (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            format TEXT,
            duration INTEGER,
            audience TEXT,
            factor REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS norms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id TEXT,
            category TEXT,
            name TEXT,
            unit TEXT,
            adult REAL,
            child REAL,
            min REAL,
            max REAL,
            package_size REAL,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            unit TEXT,
            price REAL,
            source TEXT,
            date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_name TEXT,
            ingredient_id TEXT,
            amount REAL,
            unit TEXT,
            FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drinks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            unit TEXT,
            adult REAL,
            child REAL,
            package_size REAL,
            price REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            scenario_id TEXT,
            adults INTEGER,
            children INTEGER,
            hours INTEGER,
            calculated_cost REAL,
            actual_cost REAL,
            eaten REAL,
            leftover REAL,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# ============================================================
# 4. ЗАГРУЗКА ДАННЫХ
# ============================================================

def load_scenarios():
    return [
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

def load_norms():
    return {
        "SC001": [
            {"category": "Салаты", "name": "Оливье", "unit": "кг", "adult": 0.12, "child": 0.08, "min": 0.08, "max": 0.16, "package_size": 1.0},
            {"category": "Салаты", "name": "Цезарь с курицей", "unit": "кг", "adult": 0.10, "child": 0.07, "min": 0.07, "max": 0.14, "package_size": 1.0},
            {"category": "Холодные закуски", "name": "Мясная нарезка", "unit": "кг", "adult": 0.07, "child": 0.05, "min": 0.05, "max": 0.10, "package_size": 0.5},
            {"category": "Холодные закуски", "name": "Сырная тарелка", "unit": "кг", "adult": 0.05, "child": 0.035, "min": 0.035, "max": 0.08, "package_size": 0.5},
            {"category": "Холодные закуски", "name": "Овощная тарелка", "unit": "кг", "adult": 0.07, "child": 0.05, "min": 0.05, "max": 0.10, "package_size": 0.5},
            {"category": "Хлеб", "name": "Хлеб/лаваш", "unit": "кг", "adult": 0.10, "child": 0.07, "min": 0.07, "max": 0.15, "package_size": 0.4},
            {"category": "Горячее", "name": "Куриное филе / рулет", "unit": "кг", "adult": 0.18, "child": 0.12, "min": 0.12, "max": 0.24, "package_size": 1.0},
            {"category": "Гарнир", "name": "Картофель по-деревенски", "unit": "кг", "adult": 0.15, "child": 0.10, "min": 0.10, "max": 0.20, "package_size": 1.0},
            {"category": "Десерт", "name": "Торт", "unit": "кг", "adult": 0.15, "child": 0.12, "min": 0.10, "max": 0.20, "package_size": 1.0}
        ],
        "SC003": [
            {"category": "Салаты", "name": "Оливье", "unit": "кг", "adult": 0.10, "child": 0.07, "min": 0.07, "max": 0.14, "package_size": 1.0},
            {"category": "Салаты", "name": "Цезарь с курицей", "unit": "кг", "adult": 0.10, "child": 0.07, "min": 0.07, "max": 0.14, "package_size": 1.0},
            {"category": "Салаты", "name": "Греческий", "unit": "кг", "adult": 0.08, "child": 0.055, "min": 0.055, "max": 0.12, "package_size": 1.0},
            {"category": "Холодные закуски", "name": "Мясная нарезка", "unit": "кг", "adult": 0.08, "child": 0.055, "min": 0.055, "max": 0.12, "package_size": 0.5},
            {"category": "Холодные закуски", "name": "Сырная тарелка", "unit": "кг", "adult": 0.06, "child": 0.04, "min": 0.04, "max": 0.09, "package_size": 0.5},
            {"category": "Холодные закуски", "name": "Овощная тарелка", "unit": "кг", "adult": 0.07, "child": 0.05, "min": 0.05, "max": 0.10, "package_size": 0.5},
            {"category": "Хлеб", "name": "Хлеб/лаваш", "unit": "кг", "adult": 0.10, "child": 0.07, "min": 0.07, "max": 0.15, "package_size": 0.4},
            {"category": "Горячее", "name": "Куриное филе / рулет", "unit": "кг", "adult": 0.18, "child": 0.12, "min": 0.12, "max": 0.24, "package_size": 1.0},
            {"category": "Горячее", "name": "Медальон из свинины", "unit": "кг", "adult": 0.12, "child": 0.08, "min": 0.08, "max": 0.18, "package_size": 1.0},
            {"category": "Гарнир", "name": "Картофель по-деревенски", "unit": "кг", "adult": 0.15, "child": 0.10, "min": 0.10, "max": 0.20, "package_size": 1.0},
            {"category": "Десерт", "name": "Торт", "unit": "кг", "adult": 0.12, "child": 0.08, "min": 0.08, "max": 0.16, "package_size": 1.0}
        ],
        "SC007": [
            {"category": "Закуски", "name": "Мини-сэндвич", "unit": "шт", "adult": 2, "child": 2, "min": 1, "max": 4, "package_size": 12},
            {"category": "Горячее", "name": "Мини-пицца", "unit": "кг", "adult": 0.15, "child": 0.15, "min": 0.10, "max": 0.20, "package_size": 1.0},
            {"category": "Горячее", "name": "Наггетсы", "unit": "кг", "adult": 0.08, "child": 0.08, "min": 0.05, "max": 0.12, "package_size": 1.0},
            {"category": "Гарнир", "name": "Картофель фри", "unit": "кг", "adult": 0.08, "child": 0.08, "min": 0.05, "max": 0.12, "package_size": 1.0},
            {"category": "Фрукты", "name": "Фрукты ассорти", "unit": "кг", "adult": 0.12, "child": 0.12, "min": 0.08, "max": 0.16, "package_size": 1.0},
            {"category": "Десерт", "name": "Торт", "unit": "кг", "adult": 0.10, "child": 0.10, "min": 0.07, "max": 0.14, "package_size": 1.0},
            {"category": "Десерт", "name": "Капкейк", "unit": "шт", "adult": 1, "child": 1, "min": 0, "max": 2, "package_size": 6}
        ],
        "SC010": [
            {"category": "Мясо", "name": "Свинина для шашлыка", "unit": "кг", "adult": 0.30, "child": 0.20, "min": 0.20, "max": 0.45, "package_size": 1.0},
            {"category": "Мясо", "name": "Куриное филе для гриля", "unit": "кг", "adult": 0.15, "child": 0.10, "min": 0.10, "max": 0.20, "package_size": 1.0},
            {"category": "Овощи", "name": "Овощи гриль", "unit": "кг", "adult": 0.15, "child": 0.10, "min": 0.10, "max": 0.22, "package_size": 1.0},
            {"category": "Закуски", "name": "Овощная тарелка", "unit": "кг", "adult": 0.08, "child": 0.06, "min": 0.06, "max": 0.12, "package_size": 0.5},
            {"category": "Закуски", "name": "Соленья", "unit": "кг", "adult": 0.07, "child": 0.05, "min": 0.05, "max": 0.10, "package_size": 0.5},
            {"category": "Хлеб", "name": "Лаваш", "unit": "кг", "adult": 0.08, "child": 0.06, "min": 0.06, "max": 0.12, "package_size": 0.4},
            {"category": "Соусы", "name": "Соусы", "unit": "кг", "adult": 0.05, "child": 0.035, "min": 0.035, "max": 0.075, "package_size": 0.5},
            {"category": "Фрукты", "name": "Фрукты ассорти", "unit": "кг", "adult": 0.10, "child": 0.07, "min": 0.07, "max": 0.14, "package_size": 1.0}
        ]
    }

def load_drinks():
    return [
        {"id": "D001", "name": "Вода питьевая", "unit": "л", "adult": 0.60, "child": 0.40, "package_size": 1.5, "price": 60},
        {"id": "D002", "name": "Сок яблочный", "unit": "л", "adult": 0.25, "child": 0.15, "package_size": 1.0, "price": 120},
        {"id": "D003", "name": "Сок апельсиновый", "unit": "л", "adult": 0.20, "child": 0.15, "package_size": 1.0, "price": 120},
        {"id": "D004", "name": "Газировка", "unit": "л", "adult": 0.30, "child": 0.25, "package_size": 1.5, "price": 80},
        {"id": "D005", "name": "Морс клюквенный", "unit": "л", "adult": 0.15, "child": 0.10, "package_size": 0.5, "price": 150},
        {"id": "D006", "name": "Чай чёрный", "unit": "л", "adult": 0.10, "child": 0.05, "package_size": 0.5, "price": 60},
        {"id": "D007", "name": "Вода газированная", "unit": "л", "adult": 0.30, "child": 0.20, "package_size": 1.5, "price": 50}
    ]

def load_ingredients():
    return [
        {"id": "I001", "name": "Картофель", "category": "Овощи", "unit": "кг", "price": 49.02, "source": "Росстат/Пермстат", "date": "06.09.2026"},
        {"id": "I002", "name": "Куриное филе", "category": "Мясо", "unit": "кг", "price": 253.49, "source": "Росстат/Пермстат", "date": "06.09.2026"},
        {"id": "I003", "name": "Свинина", "category": "Мясо", "unit": "кг", "price": 420.93, "source": "Росстат/Пермстат", "date": "06.09.2026"},
        {"id": "I004", "name": "Сыр твердый", "category": "Молочные", "unit": "кг", "price": 912.45, "source": "Росстат/Пермстат", "date": "06.09.2026"},
        {"id": "I005", "name": "Хлеб пшеничный", "category": "Хлеб", "unit": "кг", "price": 133.95, "source": "Росстат/Пермстат", "date": "06.09.2026"},
        {"id": "I006", "name": "Масло подсолнечное", "category": "Жиры", "unit": "кг", "price": 163.85, "source": "Росстат/Пермстат", "date": "06.09.2026"},
        {"id": "I007", "name": "Колбаса вареная", "category": "Мясо", "unit": "кг", "price": 541.95, "source": "Росстат/Пермстат", "date": "06.09.2026"},
        {"id": "I008", "name": "Морковь", "category": "Овощи", "unit": "кг", "price": 55.00, "source": "Рабочая цена MVP", "date": "06.09.2026"},
        {"id": "I009", "name": "Огурцы маринованные", "category": "Овощи", "unit": "кг", "price": 220.00, "source": "Рабочая цена MVP", "date": "06.09.2026"},
        {"id": "I010", "name": "Яйца", "category": "Молочные", "unit": "шт", "price": 12.00, "source": "Рабочая цена MVP", "date": "06.09.2026"},
        {"id": "I011", "name": "Горошек консервированный", "category": "Консервы", "unit": "кг", "price": 220.00, "source": "Рабочая цена MVP", "date": "06.09.2026"},
        {"id": "I012", "name": "Майонез", "category": "Соусы", "unit": "кг", "price": 250.00, "source": "Рабочая цена MVP", "date": "06.09.2026"},
    ]

def load_recipes():
    return [
        {"dish_name": "Оливье", "ingredient_id": "I001", "amount": 0.045, "unit": "кг"},
        {"dish_name": "Оливье", "ingredient_id": "I008", "amount": 0.015, "unit": "кг"},
        {"dish_name": "Оливье", "ingredient_id": "I009", "amount": 0.015, "unit": "кг"},
        {"dish_name": "Оливье", "ingredient_id": "I010", "amount": 0.12, "unit": "шт"},
        {"dish_name": "Оливье", "ingredient_id": "I011", "amount": 0.015, "unit": "кг"},
        {"dish_name": "Оливье", "ingredient_id": "I007", "amount": 0.025, "unit": "кг"},
        {"dish_name": "Оливье", "ingredient_id": "I012", "amount": 0.020, "unit": "кг"},
        
        {"dish_name": "Куриное филе / рулет", "ingredient_id": "I002", "amount": 0.170, "unit": "кг"},
        {"dish_name": "Куриное филе / рулет", "ingredient_id": "I006", "amount": 0.005, "unit": "кг"},
        
        {"dish_name": "Медальон из свинины", "ingredient_id": "I003", "amount": 0.120, "unit": "кг"},
        {"dish_name": "Медальон из свинины", "ingredient_id": "I006", "amount": 0.005, "unit": "кг"},
        
        {"dish_name": "Картофель по-деревенски", "ingredient_id": "I001", "amount": 0.130, "unit": "кг"},
        {"dish_name": "Картофель по-деревенски", "ingredient_id": "I006", "amount": 0.008, "unit": "кг"},
        
        {"dish_name": "Хлеб/лаваш", "ingredient_id": "I005", "amount": 0.100, "unit": "кг"},
        
        {"dish_name": "Цезарь с курицей", "ingredient_id": "I002", "amount": 0.035, "unit": "кг"},
        {"dish_name": "Цезарь с курицей", "ingredient_id": "I004", "amount": 0.005, "unit": "кг"},
        
        {"dish_name": "Греческий", "ingredient_id": "I004", "amount": 0.015, "unit": "кг"},
        {"dish_name": "Греческий", "ingredient_id": "I006", "amount": 0.003, "unit": "кг"},
    ]

def seed_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM scenarios')
    cursor.execute('DELETE FROM norms')
    cursor.execute('DELETE FROM ingredients')
    cursor.execute('DELETE FROM recipes')
    cursor.execute('DELETE FROM drinks')
    
    for s in load_scenarios():
        cursor.execute('''
            INSERT OR REPLACE INTO scenarios (id, name, format, duration, audience, factor)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (s['id'], s['name'], s['format'], s['duration'], s['audience'], s['factor']))
    
    norms = load_norms()
    for scenario_id, norm_list in norms.items():
        for n in norm_list:
            cursor.execute('''
                INSERT INTO norms (scenario_id, category, name, unit, adult, child, min, max, package_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (scenario_id, n['category'], n['name'], n['unit'], n['adult'], n['child'], n['min'], n['max'], n['package_size']))
    
    for i in load_ingredients():
        cursor.execute('''
            INSERT OR REPLACE INTO ingredients (id, name, category, unit, price, source, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (i['id'], i['name'], i['category'], i['unit'], i['price'], i['source'], i['date']))
    
    for r in load_recipes():
        cursor.execute('''
            INSERT INTO recipes (dish_name, ingredient_id, amount, unit)
            VALUES (?, ?, ?, ?)
        ''', (r['dish_name'], r['ingredient_id'], r['amount'], r['unit']))
    
    for d in load_drinks():
        cursor.execute('''
            INSERT OR REPLACE INTO drinks (id, name, unit, adult, child, package_size, price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (d['id'], d['name'], d['unit'], d['adult'], d['child'], d['package_size'], d['price']))
    
    conn.commit()
    conn.close()
    print("✅ База данных заполнена")

# ============================================================
# 5. БИЗНЕС-ЛОГИКА
# ============================================================

def get_duration_factor(hours):
    rules = {2: 1.00, 4: 1.10, 6: 1.20, 8: 1.30}
    if hours <= 2: return rules[2]
    if hours <= 4: return rules[4]
    if hours <= 6: return rules[6]
    return rules[8]

def get_drinks_duration_factor(hours):
    rules = {2: 1.00, 4: 1.30, 6: 1.60, 8: 2.00}
    if hours <= 2: return rules[2]
    if hours <= 4: return rules[4]
    if hours <= 6: return rules[6]
    return rules[8]

def get_packages(amount, package_size):
    if not amount or amount <= 0 or not package_size:
        return 0
    return math.ceil(amount / package_size)

def get_actual_amount(packages, package_size):
    return packages * package_size

def calculate_dish_cost(dish_name, conn):
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.amount, r.unit, i.price 
        FROM recipes r
        JOIN ingredients i ON r.ingredient_id = i.id
        WHERE r.dish_name = ?
    ''', (dish_name,))
    recipe = cursor.fetchall()
    if not recipe:
        return 0.0
    
    total_cost = 0.0
    for amount, unit, price in recipe:
        if price is None:
            continue
        if unit == 'кг':
            total_cost += amount * price
        elif unit == 'г':
            total_cost += (amount / 1000) * price
        else:
            total_cost += amount * price
    return total_cost

# ============================================================
# 6. УМНЫЕ ПРОВЕРКИ
# ============================================================

class SmartChecker:
    def __init__(self, result: dict, request: CalculationRequest):
        self.result = result
        self.request = request
        self.checks: List[CheckResult] = []
        self.check_id_counter = 1
    
    def _add_check(self, severity: Severity, category: str, message: str, 
                   details: Optional[Dict] = None, suggestion: Optional[str] = None):
        check = CheckResult(
            id=f"CHK{self.check_id_counter:04d}",
            severity=severity,
            category=category,
            message=message,
            details=details,
            suggestion=suggestion
        )
        self.checks.append(check)
        self.check_id_counter += 1
    
    def run_all_checks(self) -> List[CheckResult]:
        self._check_total_food()
        self._check_food_per_person()
        self._check_category_balance()
        self._check_budget()
        self._check_package_efficiency()
        self._check_drinks_volume()
        self._check_price_sources()
        self._check_norm_limits()
        self._check_minimum_order()
        return self.checks
    
    def _check_total_food(self):
        total_food = sum(item.get('final_amount', 0) for item in self.result['items'] 
                        if item.get('category') != 'Напитки')
        total_guests = self.request.adults + self.request.children
        
        if total_food < 0.3 * total_guests:
            self._add_check(
                Severity.ERROR,
                "Объём еды",
                f"Слишком мало еды: {total_food:.2f} кг на {total_guests} гостей",
                {"total_food": total_food, "guests": total_guests, "per_person": total_food/total_guests},
                "Увеличьте нормы или добавьте блюда"
            )
        elif total_food > 1.2 * total_guests:
            self._add_check(
                Severity.WARNING,
                "Объём еды",
                f"Много еды: {total_food:.2f} кг на {total_guests} гостей",
                {"total_food": total_food, "guests": total_guests, "per_person": total_food/total_guests},
                "Можно уменьшить нормы или убрать часть блюд"
            )
    
    def _check_food_per_person(self):
        total_food = sum(item.get('final_amount', 0) for item in self.result['items'] 
                        if item.get('category') != 'Напитки')
        total_guests = self.request.adults + self.request.children
        
        if total_guests > 0:
            per_person = total_food / total_guests
            if per_person < 0.4:
                self._add_check(
                    Severity.WARNING,
                    "Норма на человека",
                    f"Мало еды на человека: {per_person:.2f} кг",
                    {"per_person": per_person, "recommended": "0.5-0.8 кг"},
                    "Рекомендуемая норма 0.5-0.8 кг на человека"
                )
            elif per_person > 1.0:
                self._add_check(
                    Severity.INFO,
                    "Норма на человека",
                    f"Много еды на человека: {per_person:.2f} кг",
                    {"per_person": per_person, "recommended": "0.5-0.8 кг"},
                    "Возможно, часть еды останется"
                )
    
    def _check_category_balance(self):
        categories = {}
        for item in self.result['items']:
            if item.get('category') != 'Напитки':
                cat = item.get('category', 'Другое')
                categories[cat] = categories.get(cat, 0) + item.get('final_amount', 0)
        
        if not categories:
            return
        
        if 'Салаты' not in categories or categories['Салаты'] == 0:
            self._add_check(
                Severity.WARNING,
                "Баланс категорий",
                "В меню нет салатов",
                {"categories": list(categories.keys())},
                "Добавьте хотя бы один салат"
            )
        
        hot_categories = ['Горячее', 'Горячие закуски', 'Мясо']
        has_hot = any(cat in categories and categories[cat] > 0 for cat in hot_categories)
        if not has_hot:
            self._add_check(
                Severity.WARNING,
                "Баланс категорий",
                "В меню нет горячих блюд",
                {"categories": list(categories.keys())},
                "Добавьте горячее блюдо"
            )
        
        if 'Десерт' not in categories or categories['Десерт'] == 0:
            self._add_check(
                Severity.INFO,
                "Баланс категорий",
                "В меню нет десерта",
                {"categories": list(categories.keys())},
                "Добавьте десерт для завершения"
            )
    
    def _check_budget(self):
        total_cost = self.result.get('total_cost', 0)
        budget = self.request.budget
        
        if total_cost > budget:
            difference = total_cost - budget
            percent = (difference / budget) * 100
            self._add_check(
                Severity.ERROR,
                "Бюджет",
                f"Превышение бюджета на {difference:.2f} ₽ ({percent:.1f}%)",
                {"over_budget": difference, "percent": percent, "total_cost": total_cost, "budget": budget},
                f"Увеличьте бюджет до {math.ceil(total_cost / 1000) * 1000} ₽ или уменьшите количество блюд"
            )
        elif budget - total_cost > budget * 0.3:
            self._add_check(
                Severity.INFO,
                "Бюджет",
                f"Бюджет значительно превышает стоимость",
                {"remaining": budget - total_cost, "percent": ((budget - total_cost) / budget) * 100},
                "Можно добавить более дорогие блюда или увеличить порции"
            )
    
    def _check_package_efficiency(self):
        package_waste = 0
        for item in self.result['items']:
            if 'package_size' in item and item.get('package_size', 0) > 0:
                final = item.get('final_amount', 0)
                packages = item.get('packages', 0)
                if packages > 0 and final > 0:
                    waste = (packages * item['package_size'] - final) / (packages * item['package_size'])
                    if waste > 0.4:
                        package_waste += 1
        
        if package_waste > 2:
            self._add_check(
                Severity.WARNING,
                "Упаковки",
                f"{package_waste} товаров имеют большой остаток при округлении (>40%)",
                {"waste_count": package_waste},
                "Выберите товары с меньшей фасовкой или используйте другие упаковки"
            )
    
    def _check_drinks_volume(self):
        total_drinks = sum(item.get('final_amount', 0) for item in self.result['items'] 
                          if item.get('category') == 'Напитки')
        total_guests = self.request.adults + self.request.children
        
        if total_guests > 0:
            per_person = total_drinks / total_guests
            if per_person < 0.3:
                self._add_check(
                    Severity.WARNING,
                    "Напитки",
                    f"Мало напитков: {per_person:.2f} л на человека",
                    {"per_person": per_person, "guests": total_guests, "total_drinks": total_drinks},
                    "Рекомендуемая норма 0.5-1.0 л на человека"
                )
            elif per_person > 1.5:
                self._add_check(
                    Severity.INFO,
                    "Напитки",
                    f"Много напитков: {per_person:.2f} л на человека",
                    {"per_person": per_person},
                    "Возможно, часть напитков останется"
                )
    
    def _check_price_sources(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, source FROM ingredients WHERE source LIKE "%рабочая%" OR source LIKE "%MVP%"')
        unchecked = cursor.fetchall()
        conn.close()
        
        if unchecked:
            self._add_check(
                Severity.WARNING,
                "Цены",
                f"{len(unchecked)} ингредиентов имеют непроверенные цены",
                {"unchecked": [{"id": u[0], "name": u[1], "source": u[2]} for u in unchecked[:3]]},
                "Замените рабочие цены на реальные от поставщиков"
            )
    
    def _check_norm_limits(self):
        for item in self.result['items']:
            if 'min' in item and 'max' in item:
                final = item.get('final_amount', 0)
                if item.get('unit') == 'кг':
                    if final < item.get('min', 0):
                        self._add_check(
                            Severity.WARNING,
                            "Нормы",
                            f"Количество '{item.get('name')}' ниже минимума",
                            {"name": item.get('name'), "current": final, "min": item.get('min')},
                            "Увеличьте порцию"
                        )
                    elif final > item.get('max', 0):
                        self._add_check(
                            Severity.INFO,
                            "Нормы",
                            f"Количество '{item.get('name')}' превышает максимум",
                            {"name": item.get('name'), "current": final, "max": item.get('max')},
                            "Можно уменьшить порцию"
                        )
    
    def _check_minimum_order(self):
        total_guests = self.request.adults + self.request.children
        if total_guests < 5:
            self._add_check(
                Severity.INFO,
                "Маленькая компания",
                f"Всего {total_guests} гостей - возможен перерасчёт",
                {"guests": total_guests},
                "Для маленьких компаний можно уменьшить упаковки или выбрать меньшие фасовки"
            )

# ============================================================
# 7. ОСНОВНОЙ РАСЧЁТ
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
    drinks_duration_factor = get_drinks_duration_factor(request.hours)
    total_guests = request.adults + request.children
    scenario_factor = scenario[5]
    
    items = []
    
    for norm in norms:
        category, name, unit, adult_norm, child_norm, min_norm, max_norm, package_size = norm
        norm_value = adult_norm if request.adults > 0 else child_norm
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
    
    for drink in drinks:
        name, unit, adult_norm, child_norm, package_size, price = drink
        norm_value = adult_norm if request.adults > 0 else child_norm
        total_amount = total_guests * norm_value * drinks_duration_factor
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
                "min": 0,
                "max": 0,
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
    
    summary = {
        "total": len(checks),
        "errors": sum(1 for c in checks if c.severity == Severity.ERROR),
        "warnings": sum(1 for c in checks if c.severity == Severity.WARNING),
        "info": sum(1 for c in checks if c.severity == Severity.INFO),
        "critical": sum(1 for c in checks if c.severity == Severity.CRITICAL)
    }
    
    result["checks"] = checks
    result["summary"] = summary
    
    return result

# ============================================================
# 8. API ЭНДПОИНТЫ
# ============================================================

@app.get("/")
def root():
    return {"message": "Хватит всем API", "version": "1.1.0"}

@app.get("/scenarios")
def get_scenarios():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, format, duration, audience, factor FROM scenarios')
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "format": r[2], "duration": r[3], "audience": r[4], "factor": r[5]}
        for r in rows
    ]

@app.post("/calculate", response_model=CalculationResponse)
def calculate(request: CalculationRequest):
    return calculate_menu_with_checks(request)

@app.get("/health")
def health():
    return {"status": "healthy", "version": "1.1.0"}

# ============================================================
# 9. ЗАПУСК
# ============================================================
# ============================================================
# 10. ЛОГГИРОВАНИЕ (НОВОЕ!)
# ============================================================

import logging
from datetime import datetime
import json
import os

# Настройка логирования
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Лог-файл с датой
log_filename = f"{LOG_DIR}/hvatit_vsem_{datetime.now().strftime('%Y%m%d')}.log"

# Настройка форматирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()  # Вывод в консоль
    ]
)

logger = logging.getLogger(__name__)

# ============================================================
# 11. СОХРАНЕНИЕ В ИСТОРИЮ
# ============================================================

HISTORY_FILE = "history.json"

def save_to_history(data: dict):
    """Сохраняет результат расчёта в историю"""
    try:
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        # Добавляем timestamp
        record = {
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        history.append(record)
        
        # Оставляем только последние 1000 записей
        if len(history) > 1000:
            history = history[-1000:]
        
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ История сохранена. Всего записей: {len(history)}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения истории: {e}")

# ============================================================
# 12. СОХРАНЕНИЕ В БАЗУ ДАННЫХ (СТАТИСТИКА)
# ============================================================

def save_to_statistics(request: CalculationRequest, result: dict):
    """Сохраняет расчёт в таблицу статистики"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO statistics (
                date, scenario_id, adults, children, hours,
                calculated_cost, actual_cost, eaten, leftover
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            request.scenario_id,
            request.adults,
            request.children,
            request.hours,
            result.get('total_cost', 0),
            0,  # actual_cost пока не известно
            0,  # eaten пока не известно
            0   # leftover пока не известно
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Статистика сохранена в БД")
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения статистики: {e}")

# ============================================================
# 13. ОБНОВЛЁННЫЙ ЭНДПОИНТ /calculate С ЛОГИРОВАНИЕМ
# ============================================================

@app.post("/calculate", response_model=CalculationResponse)
def calculate(request: CalculationRequest):
    """Расчёт меню с логированием"""
    
    # Логируем входящий запрос
    logger.info("=" * 60)
    logger.info("📥 НОВЫЙ РАСЧЁТ")
    logger.info(f"📋 Сценарий: {request.scenario_id}")
    logger.info(f"👥 Взрослых: {request.adults}, Детей: {request.children}")
    logger.info(f"⏱ Длительность: {request.hours} ч")
    logger.info(f"💰 Бюджет: {request.budget} ₽")
    logger.info(f"🍽 Предпочтения: {request.preferences}")
    logger.info("-" * 60)
    
    # Выполняем расчёт
    result = calculate_menu_with_checks(request)
    
    # Логируем результат
    logger.info(f"💰 Итоговая стоимость: {result['total_cost']} ₽")
    logger.info(f"📊 В пределах бюджета: {result['is_within_budget']}")
    logger.info(f"📦 Количество блюд: {len(result['items'])}")
    
    # Логируем проверки
    if result.get('checks'):
        logger.info("🔍 УМНЫЕ ПРОВЕРКИ:")
        for check in result['checks']:
            logger.info(f"   {check.severity.upper()}: {check.message}")
    
    logger.info("=" * 60)
    
    # Сохраняем в историю
    save_to_history({
        "request": {
            "scenario_id": request.scenario_id,
            "adults": request.adults,
            "children": request.children,
            "hours": request.hours,
            "budget": request.budget,
            "preferences": request.preferences
        },
        "result": {
            "total_cost": result['total_cost'],
            "is_within_budget": result['is_within_budget'],
            "items_count": len(result['items'])
        }
    })
    
    # Сохраняем в статистику
    save_to_statistics(request, result)
    
    return result

# ============================================================
# 14. НОВЫЙ ЭНДПОИНТ ДЛЯ ПРОСМОТРА ИСТОРИИ
# ============================================================

@app.get("/history")
def get_history(limit: int = 50):
    """Возвращает последние расчёты из истории"""
    try:
        if not os.path.exists(HISTORY_FILE):
            return {"history": [], "total": 0}
        
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        # Возвращаем последние записи
        return {
            "history": history[-limit:],
            "total": len(history)
        }
    except Exception as e:
        logger.error(f"Ошибка чтения истории: {e}")
        return {"history": [], "total": 0, "error": str(e)}

# ============================================================
# 15. НОВЫЙ ЭНДПОИНТ ДЛЯ СТАТИСТИКИ
# ============================================================

@app.get("/statistics")
def get_statistics():
    """Возвращает статистику расчётов"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_calculations,
                AVG(calculated_cost) as avg_cost,
                MIN(calculated_cost) as min_cost,
                MAX(calculated_cost) as max_cost,
                AVG(adults + children) as avg_guests
            FROM statistics
        ''')
        
        stats = cursor.fetchone()
        conn.close()
        
        return {
            "total_calculations": stats[0] or 0,
            "average_cost": round(stats[1] or 0, 2),
            "min_cost": round(stats[2] or 0, 2),
            "max_cost": round(stats[3] or 0, 2),
            "average_guests": round(stats[4] or 0, 1)
        }
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return {"error": str(e)}

# ============================================================
# 16. НОВЫЙ ЭНДПОИНТ ДЛЯ ТЕСТА ЛОГГИРОВАНИЯ
# ============================================================

@app.get("/test-log")
def test_log():
    """Тестовый эндпоинт для проверки логирования"""
    logger.info("🧪 Тестовое сообщение в лог")
    logger.warning("⚠️ Тестовое предупреждение")
    logger.error("❌ Тестовое сообщение об ошибке")
    return {"message": "Логирование работает! Проверьте консоль и файл logs/hvatit_vsem_*.log"}
if __name__ == "__main__":
    import uvicorn
    
    if not os.path.exists(DB_PATH):
        print("📦 Создание базы данных...")
        init_db()
        print("🌱 Заполнение данными...")
        seed_database()
    
    print("🚀 Запуск сервера на http://localhost:8000")
    print("📖 Документация: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)