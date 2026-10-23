"""Rule-based SQL writer used when no LLM key is configured, so the project runs out of the box.
It understands a fixed set of warehouse questions (Arabic + English). For anything else, set an API key.
For write requests ("delete ...") it emits the literal statement on purpose: that lets you watch
the safety gate block it. A real LLM goes through exactly the same gate."""
import re

_TASHKEEL = re.compile(r"[\u064B-\u0652\u0640]")


def norm(s: str) -> str:
    s = _TASHKEEL.sub("", s.lower())
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    return s


def _has(t: str, *words: str) -> bool:
    return any(norm(w) in t for w in words)


SQL = {
    "low_stock": """SELECT p.name, p.category, SUM(sl.quantity) AS in_stock, p.reorder_level
FROM products p JOIN stock_levels sl ON sl.product_id = p.id
GROUP BY p.id
HAVING SUM(sl.quantity) <= p.reorder_level
ORDER BY SUM(sl.quantity) * 1.0 / p.reorder_level""",
    "top_supplier": """SELECT s.name AS supplier, SUM(m.quantity) AS units_received, COUNT(*) AS deliveries
FROM stock_movements m JOIN suppliers s ON s.id = m.supplier_id
WHERE m.movement_type = 'in' AND m.movement_date >= date('now', '-30 day')
GROUP BY s.id
ORDER BY units_received DESC""",
    "inventory_value": """SELECT w.name AS warehouse, ROUND(SUM(sl.quantity * p.unit_price), 2) AS inventory_value
FROM stock_levels sl
JOIN products p ON p.id = sl.product_id
JOIN warehouses w ON w.id = sl.warehouse_id
GROUP BY w.id
ORDER BY inventory_value DESC""",
    "best_sellers": """SELECT p.name, SUM(i.quantity) AS units_sold
FROM sales_order_items i
JOIN sales_orders o ON o.id = i.order_id
JOIN products p ON p.id = i.product_id
WHERE o.order_date >= date('now', '-30 day')
GROUP BY p.id
ORDER BY units_sold DESC
LIMIT 10""",
    "revenue": """SELECT ROUND(SUM(i.quantity * i.unit_price), 2) AS revenue_last_30_days
FROM sales_order_items i JOIN sales_orders o ON o.id = i.order_id
WHERE o.order_date >= date('now', '-30 day')""",
    "movements": """SELECT movement_date AS day, movement_type AS type, SUM(quantity) AS units
FROM stock_movements
WHERE movement_date >= date('now', '-7 day')
GROUP BY movement_date, movement_type
ORDER BY movement_date DESC, movement_type""",
    "categories": """SELECT category, COUNT(*) AS products
FROM products GROUP BY category ORDER BY products DESC""",
    "count_products": "SELECT COUNT(*) AS total_products FROM products",
}


def sql_for(question: str):
    t = norm(question)
    if _has(t, "احذف", "امسح", "delete", "drop ", "truncate", "update ", "عدل"):
        return "DROP TABLE products" if _has(t, "جدول", "table") else "DELETE FROM stock_movements"
    if _has(t, "مورد", "supplier") and _has(t, "اكثر", "most", "top", "افضل", "best"):
        return SQL["top_supplier"]
    if _has(t, "اكثر مبيع", "الاكثر مبيع", "best sell", "best-sell", "top sell", "selling", "افضل المنتجات"):
        return SQL["best_sellers"]
    if _has(t, "revenue", "ايراد", "اجمالي المبيعات", "total sales"):
        return SQL["revenue"]
    if _has(t, "قيمه", "value") and _has(t, "مخزون", "مستودع", "inventory", "stock", "warehouse"):
        return SQL["inventory_value"]
    if _has(t, "تخلص", "يخلص", "نفد", "ناقص", "اعاده الطلب", "حد الطلب", "reorder", "low stock",
            "running out", "run out", "below", "shortage"):
        return SQL["low_stock"]
    if _has(t, "حركه", "حركات", "movement", "this week", "هالاسبوع", "الاسبوع"):
        return SQL["movements"]
    if _has(t, "فئه", "فئات", "تصنيف", "categor"):
        return SQL["categories"]
    if _has(t, "كم", "how many", "count") and _has(t, "منتج", "صنف", "اصناف", "product"):
        return SQL["count_products"]
    return None
