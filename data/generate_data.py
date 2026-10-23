"""Builds data/warehouse.db with realistic *fake* warehouse data (no company data, no Faker needed).
Run:  python data/generate_data.py
"""
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

DB = Path(__file__).resolve().parent / "warehouse.db"

SCHEMA = """
CREATE TABLE warehouses (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL);
CREATE TABLE suppliers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL, rating REAL NOT NULL);
CREATE TABLE products (
    id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE, name TEXT NOT NULL, name_ar TEXT NOT NULL,
    category TEXT NOT NULL, unit_price REAL NOT NULL, reorder_level INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id));
CREATE TABLE stock_levels (
    product_id INTEGER NOT NULL REFERENCES products(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    quantity INTEGER NOT NULL, PRIMARY KEY (product_id, warehouse_id));
CREATE TABLE stock_movements (
    id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    movement_type TEXT NOT NULL CHECK (movement_type IN ('in','out')),
    quantity INTEGER NOT NULL, supplier_id INTEGER REFERENCES suppliers(id),
    movement_date TEXT NOT NULL);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY, customer TEXT NOT NULL, order_date TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE sales_order_items (
    id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES sales_orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL, unit_price REAL NOT NULL);
CREATE INDEX ix_mov_date ON stock_movements(movement_date);
CREATE INDEX ix_ord_date ON sales_orders(order_date);
"""

WAREHOUSES = [("Riyadh Central", "Riyadh"), ("Jeddah Port", "Jeddah"), ("Dammam Hub", "Dammam")]

SUPPLIERS = [  # name, city, rating (all distinct)
    ("Al-Rajhi Industrial Supply", "Riyadh", 4.8), ("Red Sea Packaging", "Jeddah", 4.6),
    ("Gulf Tools Trading", "Dammam", 4.2), ("Najd Electronics", "Riyadh", 4.4),
    ("Hijaz Safety Co.", "Jeddah", 4.9), ("Eastern Clean Chemicals", "Dammam", 3.9),
    ("Capital Office Depot", "Riyadh", 4.1), ("Yanbu Industrial Parts", "Yanbu", 4.5),
]

# category, supplier id, [(name, name_ar, price, reorder_level)]  -> 33 products, distinct counts per category
CATALOG = [
    ("Safety", 5, [
        ("Safety Helmet", "خوذة سلامة", 38.0, 60), ("Safety Gloves", "قفازات حماية", 12.5, 150),
        ("Safety Goggles", "نظارات واقية", 18.0, 80), ("High-Vis Vest", "سترة عاكسة", 22.0, 100),
        ("Steel-Toe Boots", "حذاء سلامة", 145.0, 40), ("Ear Protection", "واقي أذن", 15.0, 70),
        ("Dust Mask N95", "كمامة N95", 3.2, 500), ("First Aid Kit", "حقيبة إسعاف", 65.0, 30)]),
    ("Packaging", 2, [
        ("Cardboard Box Large", "كرتون كبير", 4.5, 400), ("Cardboard Box Small", "كرتون صغير", 2.8, 600),
        ("Stretch Wrap Roll", "رول تغليف", 24.0, 120), ("Packing Tape", "شريط لاصق", 6.5, 300),
        ("Bubble Wrap Roll", "رول فقاعات", 31.0, 90), ("Pallet Strap", "حزام طبليات", 18.0, 80),
        ("Wooden Pallet", "طبلية خشب", 42.0, 100)]),
    ("Tools", 3, [
        ("Cordless Drill", "دريل لاسلكي", 289.0, 20), ("Hammer", "مطرقة", 35.0, 40),
        ("Adjustable Wrench", "مفتاح ربط", 48.0, 40), ("Tape Measure", "شريط قياس", 19.0, 80),
        ("Hand Pallet Jack", "رافعة طبليات يدوية", 1250.0, 6), ("Box Cutter", "قاطع كرتون", 7.5, 200)]),
    ("Electronics", 4, [
        ("Barcode Scanner", "قارئ باركود", 410.0, 15), ("Label Printer", "طابعة ملصقات", 780.0, 8),
        ("Rugged Tablet", "تابلت صناعي", 1850.0, 6), ("Thermal Label Roll", "رول ملصقات حرارية", 14.0, 400),
        ("Wi-Fi Access Point", "نقطة وصول واي فاي", 520.0, 5)]),
    ("Cleaning", 6, [
        ("Floor Cleaner 5L", "منظف أرضيات 5 لتر", 28.0, 60), ("Disinfectant Spray", "بخاخ معقم", 11.0, 150),
        ("Trash Bags Roll", "رول أكياس نفايات", 9.0, 200), ("Mop Set", "طقم مسّاحة", 45.0, 40)]),
    ("Office", 7, [
        ("A4 Paper Ream", "رزمة ورق A4", 17.0, 200), ("Marker Pens Box", "علبة أقلام ماركر", 14.0, 100),
        ("Stapler", "دباسة", 16.0, 40)]),
]

CUSTOMERS = ["Desert Rose Trading", "Tuwaiq Contracting", "Oasis Retail Group", "Falcon Logistics",
             "Harbor Wholesale", "Sahara Builders", "Nakheel Markets", "Al-Noor Pharmacy"]


def build(path: Path = DB, seed: int = 42, verbose: bool = True) -> Path:
    rnd = random.Random(seed)
    today = date.today()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO warehouses(name, city) VALUES (?,?)", WAREHOUSES)
    con.executemany("INSERT INTO suppliers(name, city, rating) VALUES (?,?,?)", SUPPLIERS)

    products = []  # (id, price, reorder, supplier)
    pid = 0
    for cat, sup, items in CATALOG:
        for name, name_ar, price, reorder in items:
            pid += 1
            con.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?)",
                        (pid, f"{cat[:3].upper()}-{pid:04d}", name, name_ar, cat, price, reorder, sup))
            products.append((pid, price, reorder, sup))

    low = set(rnd.sample([p[0] for p in products], 7))        # products that are running out
    for p, price, reorder, sup in products:
        for w in (1, 2, 3):
            q = int(reorder * rnd.uniform(0.04, 0.28)) if p in low else int(reorder * rnd.uniform(0.6, 3.5))
            con.execute("INSERT INTO stock_levels VALUES (?,?,?)", (p, w, q))

    rows = []
    for _ in range(1400):
        p, price, reorder, sup = rnd.choice(products)
        d = (today - timedelta(days=rnd.randint(0, 89))).isoformat()
        if rnd.random() < 0.35:
            rows.append((p, rnd.randint(1, 3), "in", max(1, int(reorder * rnd.uniform(0.3, 1.2))), sup, d))
        else:
            rows.append((p, rnd.randint(1, 3), "out", max(1, int(reorder * rnd.uniform(0.05, 0.4))), None, d))
    rows.sort(key=lambda r: r[5])
    con.executemany(
        "INSERT INTO stock_movements(product_id, warehouse_id, movement_type, quantity, supplier_id, movement_date)"
        " VALUES (?,?,?,?,?,?)", rows)

    weights = [rnd.uniform(0.3, 3) for _ in products]
    for oid in range(1, 321):
        d = (today - timedelta(days=rnd.randint(0, 89))).isoformat()
        status = rnd.choices(["delivered", "shipped", "pending"], [70, 15, 15])[0]
        con.execute("INSERT INTO sales_orders VALUES (?,?,?,?)", (oid, rnd.choice(CUSTOMERS), d, status))
        for p, price, reorder, sup in rnd.sample(products, rnd.randint(1, 4)):
            con.execute("INSERT INTO sales_order_items(order_id, product_id, quantity, unit_price) VALUES (?,?,?,?)",
                        (oid, p, rnd.randint(1, max(2, reorder // 5)), price))
    con.commit()
    if verbose:
        for t in ("warehouses", "suppliers", "products", "stock_levels", "stock_movements",
                  "sales_orders", "sales_order_items"):
            print(f"  {t:<18} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>5} rows")
        print(f"Database ready: {path}")
    con.close()
    return path


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    build()
