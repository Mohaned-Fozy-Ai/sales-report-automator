"""
Generates realistic sample order data for the sales-report-automator demo.

Why this exists: the demo must work on a clean machine with no external data.
We generate ~600 rows across 6 months with ~20 products, deliberately injecting
~25 dirty rows of each bad category so the validation layer visibly does something.
"""

import csv
import random
import decimal
from datetime import date, timedelta

random.seed(42)

PRODUCTS = [
    ("Wireless Earbuds Pro", decimal.Decimal("79.99")),
    ("USB-C Hub 7-Port", decimal.Decimal("49.99")),
    ("Mechanical Keyboard TKL", decimal.Decimal("129.99")),
    ("Ergonomic Mouse", decimal.Decimal("64.99")),
    ("27-inch Monitor Stand", decimal.Decimal("89.99")),
    ("Laptop Sleeve 15in", decimal.Decimal("24.99")),
    ("Portable Charger 20000mAh", decimal.Decimal("44.99")),
    ("Webcam 1080p", decimal.Decimal("69.99")),
    ("HDMI Cable 2m", decimal.Decimal("12.99")),
    ("Screen Cleaning Kit", decimal.Decimal("9.99")),
    ("Cable Management Box", decimal.Decimal("19.99")),
    ("Desk Lamp LED", decimal.Decimal("34.99")),
    ("Wrist Rest Pad", decimal.Decimal("14.99")),
    ("Monitor Privacy Filter", decimal.Decimal("39.99")),
    ("Blue Light Glasses", decimal.Decimal("29.99")),
    ("Noise-Cancelling Headset", decimal.Decimal("149.99")),
    ("Smart Power Strip", decimal.Decimal("54.99")),
    ("Tablet Stand Adjustable", decimal.Decimal("22.99")),
    ("Mini Wireless Speaker", decimal.Decimal("59.99")),
    ("Thermal Paste 5g", decimal.Decimal("7.99")),
]

# Status mix mirrors a real small online store rather than a random draw.
# Published consumer-electronics return rates sit in the 5-10% band, so a
# generator that returns 25% of orders would make the demo report look wrong
# to anyone who actually sells online - and the report is the sales artefact.
# 92 completed / 5 refunded / 3 returned out of 100 keeps net revenue credible.
STATUSES = ["completed"] * 92 + ["refunded"] * 5 + ["returned"] * 3

START_DATE = date(2025, 1, 1)
END_DATE = date(2025, 6, 30)

# Orders per month follow a gentle growth curve. Uniform random dates produced
# month-over-month swings of +/-100%, which made the growth column read like
# noise instead of a trend a store owner would recognise.
MONTHLY_VOLUME = {1: 82, 2: 88, 3: 97, 4: 104, 5: 112, 6: 117}


def random_date(start, end):
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))


def generate_order_id(n):
    return f"ORD-{n:05d}"


rows = []
order_counter = 1

# --- Clean rows (600), distributed across months on a growth curve ---
import calendar

clean_dates = []
for month, volume in MONTHLY_VOLUME.items():
    last_day = calendar.monthrange(2025, month)[1]
    for _ in range(volume):
        clean_dates.append(date(2025, month, random.randint(1, last_day)))

for d in clean_dates:
    product, base_price = random.choice(PRODUCTS)
    qty = random.randint(1, 5)
    price = base_price * qty
    status = random.choice(STATUSES)
    rows.append({
        "Order ID": generate_order_id(order_counter),
        "order_date": d.strftime("%Y-%m-%d"),
        "product_name": product,
        "quantity": qty,
        "unit_price": str(base_price),
        "status": status,
    })
    order_counter += 1

# --- Dirty: missing price (~25) ---
for _ in range(25):
    product, _ = random.choice(PRODUCTS)
    d = random_date(START_DATE, END_DATE)
    rows.append({
        "Order ID": generate_order_id(order_counter),
        "order_date": d.strftime("%Y-%m-%d"),
        "product_name": product,
        "quantity": random.randint(1, 3),
        "unit_price": "",
        "status": "completed",
    })
    order_counter += 1

# --- Dirty: non-numeric quantity (~25) ---
for _ in range(25):
    product, base_price = random.choice(PRODUCTS)
    d = random_date(START_DATE, END_DATE)
    rows.append({
        "Order ID": generate_order_id(order_counter),
        "order_date": d.strftime("%Y-%m-%d"),
        "product_name": product,
        "quantity": random.choice(["N/A", "unknown", "?", "one", ""]),
        "unit_price": str(base_price),
        "status": "completed",
    })
    order_counter += 1

# --- Dirty: negative amounts (~25) ---
for _ in range(25):
    product, base_price = random.choice(PRODUCTS)
    d = random_date(START_DATE, END_DATE)
    rows.append({
        "Order ID": generate_order_id(order_counter),
        "order_date": d.strftime("%Y-%m-%d"),
        "product_name": product,
        "quantity": 1,
        "unit_price": str(-base_price),
        "status": "completed",
    })
    order_counter += 1

# --- Dirty: duplicate order IDs (~25) ---
# Reuse some IDs from the clean set
existing_ids = [generate_order_id(i) for i in range(1, 26)]
for oid in existing_ids:
    product, base_price = random.choice(PRODUCTS)
    d = random_date(START_DATE, END_DATE)
    rows.append({
        "Order ID": oid,
        "order_date": d.strftime("%Y-%m-%d"),
        "product_name": product,
        "quantity": 1,
        "unit_price": str(base_price),
        "status": "completed",
    })

# --- Dirty: future dates (~25) ---
FUTURE_START = date(2028, 1, 1)
FUTURE_END = date(2028, 12, 31)
for _ in range(25):
    product, base_price = random.choice(PRODUCTS)
    d = random_date(FUTURE_START, FUTURE_END)
    rows.append({
        "Order ID": generate_order_id(order_counter),
        "order_date": d.strftime("%Y-%m-%d"),
        "product_name": product,
        "quantity": 1,
        "unit_price": str(base_price),
        "status": "completed",
    })
    order_counter += 1

# --- Dirty: unparseable dates (~25) ---
BAD_DATES = ["not-a-date", "2025/99/99", "32-13-2025", "yesterday", "01-JAN", "2025.01.32"]
for _ in range(25):
    product, base_price = random.choice(PRODUCTS)
    rows.append({
        "Order ID": generate_order_id(order_counter),
        "order_date": random.choice(BAD_DATES),
        "product_name": product,
        "quantity": 1,
        "unit_price": str(base_price),
        "status": "completed",
    })
    order_counter += 1

random.shuffle(rows)

FIELDNAMES = ["Order ID", "order_date", "product_name", "quantity", "unit_price", "status"]

with open("/agent/workspace/portfolio/sales-report-automator/sample_data/orders_2025.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)

print(f"Generated {len(rows)} rows to sample_data/orders_2025.csv")
