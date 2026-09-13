# ============================================================
# ХВАТИТ ВСЕМ — БЭКЕНД v3.0
# Фуршет «Вкусно!» + рандомизация + редакция блюд
# Полностью обратно совместим с v2.1
# ============================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import sqlite3
import math
import os
import random
import hashlib
from enum import Enum


# ============================================================
# 1. ИНИЦИАЛИЗАЦИЯ
# ============================================================

app = FastAPI(
    title="Хватит всем API",
    description="API для расчёта еды на мероприятия",
    version="3.0.0"
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
# 2. МОДЕЛИ
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


class RecalculateRequest(BaseModel):
    scenario_id: str
    adults: int
    children: int
    hours: int
    budget: float
    items: List[dict]


class RandomCalculationRequest(BaseModel):
    """Запрос для рандомизированного расчёта по сценарию SC100 (и другим с counts)."""
    scenario_id: str
    adults: int
    children: int
    hours: int
    budget: float
    preferences: List[str] = []
    reroll: int = 0  # 0 = детерминированный seed, >0 = reroll


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
            id TEXT PRIMARY KEY, name TEXT NOT NULL, format TEXT,
            duration INTEGER, audience TEXT, factor REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dishes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id TEXT, category TEXT NOT NULL, name TEXT NOT NULL,
            unit TEXT NOT NULL, price_per_unit REAL NOT NULL,
            adult REAL, child REAL, min REAL, max REAL, package_size REAL,
            tags TEXT DEFAULT '',
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drinks (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT,
            adult REAL, child REAL, package_size REAL, price REAL
        )
    ''')
    # 🆕 Таблица структуры меню для рандомизации (сколько блюд по времени и категории)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS menu_structure (
            scenario_id TEXT,
            category TEXT,
            duration_bucket INTEGER,
            dish_count INTEGER,
            portion_norm REAL,
            filterable INTEGER,
            PRIMARY KEY (scenario_id, category, duration_bucket)
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ БД инициализирована")


def migrate_db():
    """Добавляет колонку tags, если её нет (для старых БД)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(dishes)")
    cols = [row[1] for row in cursor.fetchall()]
    if 'tags' not in cols:
        cursor.execute("ALTER TABLE dishes ADD COLUMN tags TEXT DEFAULT ''")
        print("✅ Добавлена колонка tags в dishes")
    conn.commit()
    conn.close()


def seed_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # === 1. Сценарии (СТАРЫЕ — НЕ ТРОГАЕМ) ===
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
        # 🆕 НОВЫЙ сценарий — фуршет «Вкусно!»
        ("SC100", "Фуршет — выездной ресторан", "Фуршет", 4, "Взрослые", 1.00),
    ]
    cursor.executemany('INSERT OR REPLACE INTO scenarios VALUES (?,?,?,?,?,?)', scenarios)

    # === 2. Старые блюда (НЕ ТРОГАЕМ) ===
    old_dishes = [
        ("SC001", "Салаты", "Оливье", "кг", 320.0, 0.12, 0.08, 0.08, 0.16, 1.0, ""),
        ("SC001", "Салаты", "Цезарь с курицей", "кг", 420.0, 0.10, 0.07, 0.07, 0.14, 1.0, ""),
        ("SC001", "Холодные закуски", "Мясная нарезка", "кг", 780.0, 0.07, 0.05, 0.05, 0.10, 0.5, ""),
        ("SC001", "Холодные закуски", "Сырная тарелка", "кг", 950.0, 0.05, 0.035, 0.035, 0.08, 0.3, ""),
        ("SC001", "Холодные закуски", "Овощная тарелка", "кг", 180.0, 0.07, 0.05, 0.05, 0.10, 0.5, ""),
        ("SC001", "Хлеб", "Хлеб/лаваш", "кг", 130.0, 0.10, 0.07, 0.07, 0.15, 0.4, ""),
        ("SC001", "Горячее", "Куриное филе / рулет", "кг", 380.0, 0.18, 0.12, 0.12, 0.24, 1.0, ""),
        ("SC001", "Горячее", "Медальон из свинины", "кг", 520.0, 0.12, 0.08, 0.08, 0.18, 1.0, ""),
        ("SC001", "Гарнир", "Картофель по-деревенски", "кг", 180.0, 0.15, 0.10, 0.10, 0.20, 1.0, ""),
        ("SC001", "Десерт", "Торт", "кг", 850.0, 0.15, 0.12, 0.10, 0.20, 1.0, ""),

        ("SC003", "Салаты", "Оливье", "кг", 320.0, 0.10, 0.07, 0.07, 0.14, 1.0, ""),
        ("SC003", "Салаты", "Цезарь с курицей", "кг", 420.0, 0.10, 0.07, 0.07, 0.14, 1.0, ""),
        ("SC003", "Холодные закуски", "Мясная нарезка", "кг", 780.0, 0.08, 0.055, 0.055, 0.12, 0.5, ""),
        ("SC003", "Холодные закуски", "Сырная тарелка", "кг", 950.0, 0.06, 0.04, 0.04, 0.09, 0.3, ""),
        ("SC003", "Горячее", "Куриное филе / рулет", "кг", 380.0, 0.18, 0.12, 0.12, 0.24, 1.0, ""),
        ("SC003", "Горячее", "Медальон из свинины", "кг", 520.0, 0.12, 0.08, 0.08, 0.18, 1.0, ""),
        ("SC003", "Десерт", "Торт", "кг", 850.0, 0.12, 0.10, 0.08, 0.18, 1.0, ""),

        ("SC004", "Салаты", "Оливье", "кг", 320.0, 0.12, 0.08, 0.08, 0.16, 1.0, ""),
        ("SC004", "Салаты", "Цезарь с курицей", "кг", 420.0, 0.12, 0.08, 0.08, 0.16, 1.0, ""),
        ("SC004", "Холодные закуски", "Мясная нарезка", "кг", 780.0, 0.09, 0.06, 0.06, 0.13, 0.5, ""),
        ("SC004", "Холодные закуски", "Сырная тарелка", "кг", 950.0, 0.07, 0.05, 0.05, 0.10, 0.3, ""),
        ("SC004", "Горячее", "Куриное филе / рулет", "кг", 380.0, 0.20, 0.13, 0.13, 0.26, 1.0, ""),
        ("SC004", "Горячее", "Медальон из свинины", "кг", 520.0, 0.15, 0.10, 0.10, 0.20, 1.0, ""),
        ("SC004", "Гарнир", "Картофель по-деревенски", "кг", 180.0, 0.18, 0.12, 0.12, 0.22, 1.0, ""),
        ("SC004", "Десерт", "Торт", "кг", 850.0, 0.18, 0.14, 0.12, 0.22, 1.0, ""),

        ("SC006", "Закуски", "Мини-сэндвич", "шт", 45.0, 2, 2, 1, 4, 12, ""),
        ("SC006", "Закуски", "Мясная нарезка", "кг", 780.0, 0.08, 0.05, 0.05, 0.12, 0.5, ""),
        ("SC006", "Горячее", "Мини-пицца", "кг", 620.0, 0.15, 0.12, 0.10, 0.20, 1.0, ""),
        ("SC006", "Горячее", "Наггетсы", "кг", 480.0, 0.10, 0.08, 0.06, 0.14, 1.0, ""),
        ("SC006", "Десерт", "Торт", "кг", 850.0, 0.10, 0.10, 0.08, 0.15, 1.0, ""),

        ("SC011", "Салаты", "Оливье", "кг", 320.0, 0.12, 0.08, 0.08, 0.16, 1.0, ""),
        ("SC011", "Холодные закуски", "Мясная нарезка", "кг", 780.0, 0.07, 0.05, 0.05, 0.10, 0.5, ""),
        ("SC011", "Холодные закуски", "Сырная тарелка", "кг", 950.0, 0.05, 0.035, 0.035, 0.08, 0.3, ""),
        ("SC011", "Холодные закуски", "Овощная тарелка", "кг", 180.0, 0.07, 0.05, 0.05, 0.10, 0.5, ""),
        ("SC011", "Горячее", "Куриное филе / рулет", "кг", 380.0, 0.18, 0.12, 0.12, 0.24, 1.0, ""),
        ("SC011", "Гарнир", "Картофель по-деревенски", "кг", 180.0, 0.15, 0.10, 0.10, 0.20, 1.0, ""),
        ("SC011", "Десерт", "Торт", "кг", 850.0, 0.15, 0.12, 0.10, 0.20, 1.0, ""),
    ]
    cursor.executemany('''
        INSERT INTO dishes (scenario_id, category, name, unit, price_per_unit, adult, child, min, max, package_size, tags)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    ''', old_dishes)

    # === 3. 🆕 Блюда сценария SC100 (фуршет «Вкусно!») ===
    # adult / child / min / max / package_size для шт-позиций:
    # adult=5, child=3, min=4, max=7, package_size=1 (упаковка = 1 шт — считаем поштучно)
    # price_per_unit = цена за 1 шт (из меню)
    # Для порционной логики: "шт" и упаковка = 1 означает, что "порций" = штук.
    sc100_dishes = [
        # === Холодные закуски: канапе на шпажках кубиками ===
        ("SC100", "Холодные закуски", "Канапе с ветчиной и маслинами", "шт", 60.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Канапе с сыром и ветчиной", "шт", 60.0, 5, 3, 4, 7, 1, "meat,veg"),
        ("SC100", "Холодные закуски", "Канапе с сыром Маасдам, Фета и виноградом", "шт", 60.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Канапе овощные с черри, перцем, огурчиком и миксом салатов", "шт", 83.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Канапе фруктовые", "шт", 60.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Фруктовые шашлычки", "шт", 100.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Канапе-десерт Медовик сметанный", "шт", 85.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Канапе с цветным зефиром, бананами и виноградом", "шт", 60.0, 5, 3, 4, 7, 1, "veg"),

        # === Холодные закуски из рыбы и морепродуктов ===
        ("SC100", "Холодные закуски", "Розочка слабосолёной семги на тосте с имбирём и салатом Лолло Биондо", "шт", 130.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Тарталетка-mini с розочкой сёмги, творожным сыром, оливкой и лимоном", "шт", 150.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Волованы с королевской креветкой, красной икрой и сливочным сыром", "шт", 230.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Королевская креветка с зелёным маслом, лимоном и маслиной на тосте", "шт", 180.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Канапе на творожном сыре с лимоном, оливкой и зеленью", "шт", 190.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Канапе на пряном хлебе с грецкими орехами, мидией, цитрусом и яблоком", "шт", 115.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Волованы с красной икрой, сливочно-икорным муссом и укропом", "шт", 190.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Слоёные волованы с чёрной осетровой икрой и сыром Маскарпоне", "шт", 1700.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Волованы с красной икрой", "шт", 190.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Ломтики подкопчёного кальмара на ржаном тосте с огурцом и зеленью", "шт", 135.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Волованы с муссом из сёмги и сливочного сыра", "шт", 100.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Волованы с красной икрой, муссом из сёмги и сливочного сыра", "шт", 195.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Заварные профитроли с муссом из сёмги и сливочного сыра", "шт", 130.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Профитроли с красной икрой, муссом из сёмги и сливочного сыра", "шт", 180.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Канапе на ржаном хлебе с исландской сельдью, луком и зелёным маслом", "шт", 80.0, 5, 3, 4, 7, 1, "fish"),

        # === Холодные закуски из мяса и птицы ===
        ("SC100", "Холодные закуски", "Канапе на тостиках с варено-копчёной говядиной, черри и зеленью", "шт", 135.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Канапе на тостиках с ветчиной, зеленью и помидоркой черри", "шт", 95.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Канапе Цезарь — гренки с куриной грудкой и сырным соусом", "шт", 100.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Канапе с бужениной, помидорчиками черри, корнишонами и зеленью", "шт", 215.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Канапе с окороком, копчёной курочкой и виноградом", "шт", 95.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Канапе на тостиках с телячим языком и сливочным соусом с хреном", "шт", 140.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Канапе на тостиках с карбонатом, корнишонами и домашней горчицей", "шт", 95.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Канапе с лепестками карбоната, сыром сулугуни и маслинами", "шт", 97.0, 5, 3, 4, 7, 1, "meat,veg"),
        ("SC100", "Холодные закуски", "Канапе с прошутто, грушей и сыром Дор Блю", "шт", 150.0, 5, 3, 4, 7, 1, "meat,veg"),
        ("SC100", "Холодные закуски", "Заварные профитроли с муссом из телятины и корнишонами", "шт", 100.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Заварные профитроли с муссом из куриного филе с грибами", "шт", 90.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Заливное с телятиной, языком, подкопчёной курочкой и печёными томатами", "шт", 350.0, 5, 3, 4, 7, 1, "meat"),

        # === Холодные закуски с сыром и овощами ===
        ("SC100", "Холодные закуски", "«Изумрудные» кубики сыра Фета в рубленой зелени", "шт", 60.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Итальянская закуска с оливками и маслинами", "шт", 70.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Канапе с сыром Дор Блю, грецким орехом и виноградом", "шт", 280.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Канапе с сыром Камамбер и виноградом", "шт", 220.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Закуска с сыром Моцарелла, базиликом и помидорками черри", "шт", 130.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Закуска с сыром Моцарелла, помидорками черри и маслинами", "шт", 105.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Закуска Итальяно с Моцареллой, черри, оливками и укропом", "шт", 110.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Закуска Капрезе в шоте с оливковым маслом", "шт", 150.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Тарталетки-мини с муссом из сыра Эдам и зелёного масла", "шт", 125.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Волованы со сливочно-грибным муссом и лепестком ветчины на гриле", "шт", 130.0, 5, 3, 4, 7, 1, "meat,veg"),

        # === Мини-бутерброды ===
        ("SC100", "Холодные закуски", "Мини-бутерброд с варено-копчёной говядиной, салатом Лолло Биондо и огурцом", "шт", 116.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Мини-бутерброд с тремя сырами (Фета, Голландский, Чечил)", "шт", 145.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Мини-бутерброд с сёмгой, творожным сыром, укропом и лимоном", "шт", 170.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Мини-бутерброд на батоне с красной икрой, маслом и зеленью", "шт", 215.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Мини-бутерброд с сервелатом, салатом Лолло Биондо и маслиной", "шт", 115.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Мини-бутерброд с сельдью на бородинском хлебе, лимоном и укропом", "шт", 95.0, 5, 3, 4, 7, 1, "fish"),

        # === Мини-сэндвичи ===
        ("SC100", "Холодные закуски", "Мини-сэндвич с салями и зернистой горчицей", "шт", 150.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Мини-сэндвич с ветчиной и сыром", "шт", 115.0, 5, 3, 4, 7, 1, "meat,veg"),

        # === Брускетты ===
        ("SC100", "Холодные закуски", "Брускетта с красной рыбой, творожным сыром и огурчиком", "шт", 250.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Брускетта с паштетом из куриного филе с грибами и луком", "шт", 150.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Брускетта с шампиньонами и трюфельным маслом", "шт", 180.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Брускетта с персиками, сливочным сыром и мятой", "шт", 155.0, 5, 3, 4, 7, 1, "veg"),

        # === Мини-рулетики ===
        ("SC100", "Холодные закуски", "Рулетики из баклажанов с ореховой пастой и сыром", "шт", 100.0, 5, 3, 4, 7, 1, "veg"),
        ("SC100", "Холодные закуски", "Нежные мини-блинчики по-французски с красной икрой", "шт", 250.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Рулетики из блинчиков с семужкой, брынзой и зеленью", "шт", 130.0, 5, 3, 4, 7, 1, "fish"),
        ("SC100", "Холодные закуски", "Рулетики из блинчиков с куриным филе и грибами", "шт", 80.0, 5, 3, 4, 7, 1, "meat"),
        ("SC100", "Холодные закуски", "Рулетики из ветчины с сырным муссом и зеленью", "шт", 70.0, 5, 3, 4, 7, 1, "meat,veg"),
        ("SC100", "Холодные закуски", "Пикантный рулетик из варено-копчёной говядины с морковью по-восточному", "шт", 100.0, 5, 3, 4, 7, 1, "meat"),

        # === Салаты ===
        ("SC100", "Салаты", "Салат «Алый» (говядина, яйца, сыр, черри)", "шт", 236.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Салаты", "Салат «Европа» (сельдерей, яблоко Гренни, ананасы)", "шт", 203.0, 2, 1, 1, 3, 1, "veg"),
        ("SC100", "Салаты", "Салат «Пражский» (телятина, яблоки, майонез)", "шт", 233.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Салаты", "Салат «Куранов» (курица, кукуруза, яйцо, ананасы)", "шт", 203.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Салаты", "Салат «Королевский» (язык, шампиньоны, курица, кукуруза)", "шт", 244.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Салаты", "Салат «Английский» (курица, солёный огурец, грибы)", "шт", 218.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Салаты", "Салат «Застолье» (курица, грибы, орехи, сыр)", "шт", 206.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Салаты", "Салат «Канада» (фасоль, яблоко, перец, крабовое мясо)", "шт", 203.0, 2, 1, 1, 3, 1, "fish"),
        ("SC100", "Салаты", "Салат «Сытный» (курица, картофель, грибы, морковь)", "шт", 199.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Салаты", "Салат-коктейль «Нежность» (курочка, огурец, чернослив, сыр)", "шт", 210.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Салаты", "Салат «Овощное изобилие» (перец, помидоры, огурцы, кукуруза)", "шт", 188.0, 2, 1, 1, 3, 1, "veg"),
        ("SC100", "Салаты", "Салат «Оливье» с говядиной и языком", "шт", 225.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Салаты", "Салат «Сельдь под шубой»", "шт", 210.0, 2, 1, 1, 3, 1, "fish"),
        ("SC100", "Салаты", "Салат «Сёмга под шубой»", "шт", 360.0, 2, 1, 1, 3, 1, "fish"),
        ("SC100", "Салаты", "Салат «Гармония» (помидоры, перец, огурцы, авокадо)", "шт", 203.0, 2, 1, 1, 3, 1, "veg"),
        ("SC100", "Салаты", "Салат «Зимний вечер» (копчёная курица, помидоры, сыр, орехи)", "шт", 206.0, 2, 1, 1, 3, 1, "meat"),

        # === Горячие закуски ===
        ("SC100", "Горячие закуски", "Жюльен с курицей и грибами в тарталетке", "шт", 150.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Горячие закуски", "Королевские креветки-гриль на подушке из ананаса", "шт", 1800.0, 2, 1, 1, 3, 1, "fish"),
        ("SC100", "Горячие закуски", "Шампиньоны фаршированные говядиной под сырной шапкой", "шт", 105.0, 2, 1, 1, 3, 1, "meat,veg"),
        ("SC100", "Горячие закуски", "Шампиньоны с творожным сыром под беконом", "шт", 130.0, 2, 1, 1, 3, 1, "meat,veg"),
        ("SC100", "Горячие закуски", "Язык, запечённый с грибами и грецким орехом (мисо-подача)", "шт", 244.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Горячие закуски", "Форель «Аппетитная» под сырной шапкой с лимоном", "шт", 330.0, 2, 1, 1, 3, 1, "fish"),
        ("SC100", "Горячие закуски", "Крокеты из говядины на овощном муссе (в шотах)", "шт", 206.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Горячие закуски", "Шашлычок из сочной свинины", "шт", 250.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Горячие закуски", "Шашлычок из нежного куриного филе", "шт", 185.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Горячие закуски", "Шашлычок из куриного филе с ананасами", "шт", 220.0, 2, 1, 1, 3, 1, "meat"),
        ("SC100", "Горячие закуски", "Шашлычок из кусочков форели/семги", "шт", 550.0, 2, 1, 1, 3, 1, "fish"),

        # === Напитки (в dishes, чтобы всё было единообразно) ===
        ("SC100", "Напитки", "Морс ягодный", "шт", 70.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Домашний имбирный лимонад с мёдом и лимоном", "шт", 80.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Соки в ассортименте", "шт", 75.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Минеральная вода в ассортименте", "шт", 95.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Домашний лимонад с апельсинами и лимонами", "шт", 150.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Безалкогольный Мохито с лаймом и мятой", "шт", 170.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Холодный ягодный чай", "шт", 110.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Растворимый кофе чёрный", "шт", 70.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Натуральный кофе", "шт", 200.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Сливки порционные", "шт", 20.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Чай в ассортименте", "шт", 60.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Глинтвейн яблочный горячий", "шт", 300.0, 2, 2, 2, 4, 1, "veg"),
        ("SC100", "Напитки", "Глинтвейн классический горячий", "шт", 300.0, 2, 2, 2, 4, 1, "veg"),
    ]
    cursor.executemany('''
        INSERT INTO dishes (scenario_id, category, name, unit, price_per_unit, adult, child, min, max, package_size, tags)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    ''', sc100_dishes)

    # === 4. Старые напитки (НЕ ТРОГАЕМ) ===
    drinks = [
        ("D001", "Вода питьевая", "л", 0.30, 0.20, 1.5, 60),
        ("D002", "Сок яблочный", "л", 0.15, 0.10, 1.0, 120),
        ("D003", "Сок апельсиновый", "л", 0.15, 0.10, 1.0, 120),
        ("D004", "Газировка", "л", 0.15, 0.12, 1.5, 80),
        ("D005", "Морс клюквенный", "л", 0.10, 0.07, 0.5, 150),
        ("D006", "Чай чёрный", "л", 0.10, 0.05, 0.5, 60),
        ("D007", "Вода газированная", "л", 0.15, 0.10, 1.5, 50),
    ]
    cursor.executemany('INSERT OR REPLACE INTO drinks VALUES (?,?,?,?,?,?,?)', drinks)

    # === 5. Структура меню для SC100 (для рандомизации) ===
    # category | duration_bucket | dish_count | portion_norm | filterable
    menu_structure = [
        # 2 часа
        ("SC100", "Холодные закуски", 2, 4, 5.5, 1),
        ("SC100", "Салаты", 2, 2, 1.5, 1),
        ("SC100", "Горячие закуски", 2, 2, 1.5, 1),
        ("SC100", "Напитки", 2, 3, 2.5, 0),
        # 4 часа
        ("SC100", "Холодные закуски", 4, 6, 5.5, 1),
        ("SC100", "Салаты", 4, 3, 1.5, 1),
        ("SC100", "Горячие закуски", 4, 3, 1.5, 1),
        ("SC100", "Напитки", 4, 4, 2.5, 0),
        # 6 часов
        ("SC100", "Холодные закуски", 6, 8, 5.5, 1),
        ("SC100", "Салаты", 6, 4, 1.5, 1),
        ("SC100", "Горячие закуски", 6, 4, 1.5, 1),
        ("SC100", "Напитки", 6, 5, 2.5, 0),
        # 8 часов
        ("SC100", "Холодные закуски", 8, 10, 5.5, 1),
        ("SC100", "Салаты", 8, 5, 1.5, 1),
        ("SC100", "Горячие закуски", 8, 5, 1.5, 1),
        ("SC100", "Напитки", 8, 6, 2.5, 0),
    ]
    cursor.executemany('''
        INSERT OR REPLACE INTO menu_structure 
        (scenario_id, category, duration_bucket, dish_count, portion_norm, filterable)
        VALUES (?,?,?,?,?,?)
    ''', menu_structure)

    conn.commit()
    conn.close()
    print(f"✅ БД заполнена")


# Инициализация + миграция
init_db()
migrate_db()
seed_database()


# ============================================================
# 4. ФАКТОРЫ И УТИЛИТЫ
# ============================================================

def get_duration_factor(hours):
    if hours <= 2: return 1.00
    if hours <= 4: return 1.10
    if hours <= 6: return 1.20
    return 1.30


def get_drinks_duration_factor(hours):
    if hours <= 2: return 1.00
    if hours <= 4: return 1.00
    if hours <= 6: return 1.20
    return 1.40


def get_packages(amount, package_size):
    if not amount or amount <= 0 or not package_size:
        return 0
    return math.ceil(amount / package_size)


def duration_bucket(hours):
    if hours <= 2: return 2
    if hours <= 4: return 4
    if hours <= 6: return 6
    return 8


def make_seed(payload: dict, reroll: int = 0) -> int:
    key = "|".join([
        str(payload.get("scenario_id", "")),
        str(payload.get("hours", 0)),
        str(payload.get("adults", 0)),
        str(payload.get("children", 0)),
        str(payload.get("budget", 0)),
        ",".join(sorted(payload.get("preferences", []))),
        str(reroll),
    ])
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def active_pref_tags(preferences: list) -> Optional[set]:
    """Возвращает set активных тегов или None (= без фильтра)."""
    if not preferences or "auto" in preferences:
        return None
    mapping = {"meat": "meat", "fish": "fish", "veg": "veg"}
    tags = {mapping[p] for p in preferences if p in mapping}
    return tags if tags else None


def dish_matches_tags(tags_str: str, active_tags: Optional[set]) -> bool:
    if active_tags is None:
        return True
    if not tags_str:
        return True
    dish_tags = {t.strip() for t in tags_str.split(",") if t.strip()}
    return bool(dish_tags & active_tags)


# ============================================================
# 5. ПРОВЕРКИ (SmartChecker — как в v2.1)
# ============================================================

class SmartChecker:
    def __init__(self, result, request):
        self.result = result
        self.request = request
        self.checks = []
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
                      f"Превышение бюджета на {tc - b:.0f} ₽", None,
                      f"Увеличьте бюджет до {math.ceil(tc / 1000) * 1000} ₽")
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
                      f"Мало напитков: {drinks / tg:.2f} л/чел", None,
                      "Рекомендуется 0.5-1.0 л")

    def _check_minimum_order(self):
        tg = self.request.adults + self.request.children
        if tg < 5:
            self._add(Severity.INFO, "Маленькая компания",
                      f"Всего {tg} гостей", None, "Возможен перерасчёт упаковок")


# ============================================================
# 6. РАСЧЁТ — старый (не трогаем)
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
# 7. 🆕 РАНДОМИЗИРОВАННЫЙ РАСЧЁТ
# ============================================================

def calculate_random(request: RandomCalculationRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM scenarios WHERE id = ?', (request.scenario_id,))
    scenario = cursor.fetchone()
    if not scenario:
        conn.close()
        raise HTTPException(404, "Сценарий не найден")

    # Структура меню по времени
    bucket = duration_bucket(request.hours)
    cursor.execute('''
        SELECT category, dish_count, portion_norm, filterable
        FROM menu_structure WHERE scenario_id = ? AND duration_bucket = ?
        ORDER BY rowid
    ''', (request.scenario_id, bucket))
    structure = cursor.fetchall()

    if not structure:
        conn.close()
        raise HTTPException(400, f"Для сценария {request.scenario_id} нет структуры меню")

    # Все блюда сценария
    cursor.execute('''
        SELECT category, name, unit, price_per_unit, package_size, tags
        FROM dishes WHERE scenario_id = ?
    ''', (request.scenario_id,))
    all_dishes = cursor.fetchall()
    conn.close()

    # Индекс: {category: [dish, ...]}
    by_cat = {}
    for row in all_dishes:
        cat = row[0]
        by_cat.setdefault(cat, []).append({
            "category": cat, "name": row[1], "unit": row[2],
            "price": row[3], "package_size": row[4], "tags": row[5] or "",
        })

    # Seed
    payload = {
        "scenario_id": request.scenario_id, "hours": request.hours,
        "adults": request.adults, "children": request.children,
        "budget": request.budget, "preferences": request.preferences,
    }
    seed = make_seed(payload, request.reroll)
    rng = random.Random(seed)

    pref_tags = active_pref_tags(request.preferences)
    effective_guests = request.adults + request.children * 0.6
    if effective_guests <= 0:
        effective_guests = request.adults

    items = []

    for (cat, dish_count, portion_norm, filterable) in structure:
        pool = by_cat.get(cat, [])
        if not pool:
            continue

        # Фильтр по тегам (для фильтруемых категорий)
        if filterable:
            filtered = [d for d in pool if dish_matches_tags(d["tags"], pref_tags)]
        else:
            filtered = list(pool)

        # ВАРИАНТ В: если после фильтра меньше, чем нужно — добираем
        off_filter_ids = set()
        if len(filtered) < dish_count:
            filtered_ids = {d["name"] for d in filtered}
            extra_pool = [d for d in pool if d["name"] not in filtered_ids]
            need_extra = dish_count - len(filtered)
            extra_picked = rng.sample(extra_pool, min(need_extra, len(extra_pool)))
            for d in extra_picked:
                off_filter_ids.add(d["name"])
                filtered.append(d)

        # Рандомный выбор
        chosen = rng.sample(filtered, min(dish_count, len(filtered)))

        # Сортировка: дорогие сверху
        chosen.sort(key=lambda d: -d["price"])

        # Расчёт порций по Варианту Б
        per_dish_portions = math.ceil(effective_guests * portion_norm / max(1, len(chosen)))

        for d in chosen:
            packages = per_dish_portions
            final_amount = per_dish_portions * d["package_size"]
            total_price = packages * d["price"]

            items.append({
                "category": cat,
                "name": d["name"],
                "unit": d["unit"],
                "final_amount": round(final_amount, 2),
                "packages": packages,
                "package_size": d["package_size"],
                "total_price": round(total_price, 2),
                "cost_per_unit": d["price"],
                "off_filter": d["name"] in off_filter_ids,
            })

    total_cost = sum(i["total_price"] for i in items)

    result = {
        "items": items,
        "total_cost": round(total_cost, 2),
        "budget": request.budget,
        "is_within_budget": total_cost <= request.budget,
        "shortfall": round(max(0, total_cost - request.budget), 2),
        "remaining": round(max(0, request.budget - total_cost), 2),
        "adults": request.adults,
        "children": request.children,
        "total_guests": request.adults + request.children,
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
# 8. API ЭНДПОИНТЫ
# ============================================================

@app.get("/")
def root():
    return {"message": "Хватит всем API", "version": "3.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy", "version": "3.0.0"}


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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    result = {}
    for table in ['scenarios', 'dishes', 'drinks', 'menu_structure']:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            result[table] = cursor.fetchone()[0]
        except Exception as e:
            result[table] = f"err: {e}"
    conn.close()
    return result


@app.get("/alternatives")
def get_alternatives(category: str, exclude: str = "", preferences: str = "", scenario_id: str = ""):
    """
    Расширенная версия: 
    - фильтрует по tags (если переданы preferences)
    - сортирует от дорогих к дешёвым
    - может ограничиваться конкретным сценарием
    
    Обратно совместим: без новых параметров работает как раньше.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if scenario_id:
        cursor.execute('''
            SELECT DISTINCT name, unit, price_per_unit, package_size, tags
            FROM dishes WHERE category = ? AND name != ? AND scenario_id = ?
        ''', (category, exclude, scenario_id))
    else:
        cursor.execute('''
            SELECT DISTINCT name, unit, price_per_unit, package_size, tags
            FROM dishes WHERE category = ? AND name != ?
        ''', (category, exclude))

    rows = cursor.fetchall()
    conn.close()

    # Фильтр по предпочтениям (если переданы)
    prefs_list = [p.strip() for p in preferences.split(",") if p.strip()] if preferences else []
    pref_tags = active_pref_tags(prefs_list)

    result = []
    for r in rows:
        tags = r[4] or ""
        if not dish_matches_tags(tags, pref_tags):
            continue
        result.append({
            "name": r[0], "unit": r[1], "price_per_unit": r[2],
            "package_size": r[3], "tags": tags,
        })

    # Сортировка от дорогих к дешёвым
    result.sort(key=lambda x: -x["price_per_unit"])
    return result


@app.post("/calculate", response_model=CalculationResponse)
def calculate(request: CalculationRequest):
    return calculate_menu_with_checks(request)


@app.post("/calculate_random", response_model=CalculationResponse)
def calculate_random_endpoint(request: RandomCalculationRequest):
    """🆕 Рандомизированный расчёт. Используется для сценария SC100."""
    return calculate_random(request)


@app.post("/reroll", response_model=CalculationResponse)
def reroll_endpoint(request: RandomCalculationRequest):
    """🆕 Кнопка «🎲 Другое меню». Меняет seed → новый набор."""
    request.reroll = random.randint(1, 999999)
    return calculate_random(request)


@app.post("/recalculate", response_model=CalculationResponse)
def recalculate(request: RecalculateRequest):
    items = []
    for item in request.items:
        price = item.get("cost_per_unit", 0)
        qty = item.get("final_amount", 0)
        total_price = round(price * qty, 2)
        items.append({
            "category": item.get("category", "Прочее"),
            "name": item.get("name", ""),
            "unit": item.get("unit", "кг"),
            "final_amount": qty,
            "packages": item.get("packages", 1),
            "package_size": item.get("package_size", 1.0),
            "total_price": total_price,
            "cost_per_unit": price,
            "off_filter": item.get("off_filter", False),
        })

    total_cost = sum(i["total_price"] for i in items)
    result = {
        "items": items,
        "total_cost": round(total_cost, 2),
        "budget": request.budget,
        "is_within_budget": total_cost <= request.budget,
        "shortfall": round(max(0, total_cost - request.budget), 2),
        "remaining": round(max(0, request.budget - total_cost), 2),
        "adults": request.adults,
        "children": request.children,
        "total_guests": request.adults + request.children,
        "scenario": request.scenario_id,
        "hours": request.hours,
    }
    result["checks"] = []
    result["summary"] = {"total": 0, "errors": 0, "warnings": 0, "info": 0, "critical": 0}
    return result


# ============================================================
# 9. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Запуск на http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)