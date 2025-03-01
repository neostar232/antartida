from datetime import datetime, timedelta
from .db import get_db

def get_datetime_argentina():
    return datetime.utcnow() - timedelta(hours=3)

def add_stock(product_id, quantity):
    """
    Suma la cantidad especificada al stock de un producto.
    Si el producto no existe en StockActual, lo crea.
    """
    conn = get_db()
    cursor = conn.cursor()
    quantity = int(quantity)

    # Buscar si el producto ya existe en stock
    cursor.execute("SELECT quantity FROM stock_actual WHERE product_id = ?", (product_id,))
    row = cursor.fetchone()

    if row:
        new_quantity = row["quantity"] + quantity
        cursor.execute("UPDATE stock_actual SET quantity = ?, last_updated = ? WHERE product_id = ?",
                       (new_quantity, get_datetime_argentina(), product_id))
    else:
        cursor.execute("INSERT INTO stock_actual (product_id, quantity, last_updated) VALUES (?, ?, ?)",
                       (product_id, quantity, get_datetime_argentina()))

    conn.commit()
    return {"product_id": product_id, "quantity": new_quantity if row else quantity}


def remove_stock(product_id, quantity):
    """
    Resta la cantidad especificada al stock de un producto.
    No permite que la cantidad quede en negativo.
    """
    conn = get_db()
    cursor = conn.cursor()
    quantity = int(quantity)
    
    # Buscar stock actual
    cursor.execute("SELECT quantity FROM stock_actual WHERE product_id = ?", (product_id,))
    row = cursor.fetchone()

    if not row:
        raise ValueError(f"No hay stock registrado para el producto con ID {product_id}")

    if row["quantity"] < quantity:
        raise ValueError(f"Stock insuficiente para el producto con ID {product_id}")

    new_quantity = row["quantity"] - quantity
    cursor.execute("UPDATE stock_actual SET quantity = ?, last_updated = ? WHERE product_id = ?",
                   (new_quantity, get_datetime_argentina(), product_id))

    conn.commit()
    return {"product_id": product_id, "quantity": new_quantity}

