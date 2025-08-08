from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from werkzeug.security import check_password_hash
from .db import get_db

bp = Blueprint("auth_passengers", __name__, url_prefix="/passengers")

# Categorías y sus ítems
CATEGORIES = {
    'Bar': ['Café', 'Cerveza', 'Cóctel'],
    'Internet': ['1 Hora', '24 Horas', 'Semana'],
    'Ropa': ['Camiseta', 'Pantalón', 'Chaqueta'],
    'Merchandising': ['Taza', 'Llavero', 'Poster']
}

@bp.route("/auth", methods=["GET", "POST"])
def front():
    if request.method == "POST":
        tx_email = request.form["tx_email"].lower()
        password = request.form["password"]
        print(tx_email, password)
        db = get_db()
        error = None
        user = db.execute(
            "SELECT id_passenger, tx_email, tx_password, tx_name FROM bt_passenger WHERE tx_email = ?", (tx_email,)
        ).fetchone()
        print(user)
        if user is None:
            error = "Invalid user."
        #elif not check_password_hash(user["tx_password"], password):
        elif not user["tx_password"].upper() == password.strip().upper():
            print("Password error ---- ", user["tx_password"],"---", password)
            error = "Incorrect password."
        if error is None:
            session.clear()
            session["passenger_id"] = user["id_passenger"]
            session["passenger_email"] = user["tx_email"]
            session["username"] = user["tx_name"]
            return redirect(url_for("auth_passengers.menu"))
        flash(error)
    return render_template("passengers/login_passenger.html")

@bp.route("/menu")
def menu():
    username = session.get("username", "")
    return render_template("passengers/menu_passenger.html", username=username)

@bp.route("/category/<category>")
def category(category):
    items = CATEGORIES.get(category, [])
    return render_template("passengers/category_passenger.html", category=category, items=items)

@bp.route("/consumption")
def consumption():
    db = get_db()
    # Obtener el id_passenger de la sesión
    id_passenger = session.get("passenger_id")
    if not id_passenger:
        flash("No se encontró el pasajero en sesión. Por favor, vuelva a iniciar sesión.")
        return redirect(url_for("auth_passengers.front"))
    results = db.execute(
        '''
        SELECT
            c.id_passenger,
            c.id_product,
            s.tx_subcategory ||' '|| b.tx_product ||' ('||u.tx_unity||')' AS producto,
            STRFTIME('%Y-%m-%d %H:%M', c.dt_consumption) AS fc,
            c.nu_quantity,
            c.pc_unity,
            c.nu_quantity * c.pc_unity AS pc_total    
        FROM bt_consumption c INNER JOIN bt_product b
        ON c.id_product = b.id_product
        INNER JOIN lkp_subcategories s
        ON b.id_subcategory = s.id_subcategory
        INNER JOIN lkp_units u
        ON b.id_unity = u.id_unity
        WHERE b.flag_ctrl = 1
        AND c.id_passenger = ?
        ORDER BY 4;
        ''', (id_passenger,)
    ).fetchall()
    total_consumos = sum(row["pc_total"] for row in results) if results else 0
    return render_template(
        "passengers/consumption_passenger.html",
        results=results,
        total_consumos=total_consumos
    )

@bp.route("/consumption/results", methods=["POST"])
def consumption_results():
    passenger_email = request.form.get("passenger_email")
    db = get_db()
    # Obtener el id_passenger a partir del email
    passenger = db.execute("SELECT id_passenger FROM bt_passenger WHERE tx_email = ?", (passenger_email,)).fetchone()
    if not passenger:
        return render_template("passengers/consumption_passenger.html", passengers=[], results=[], error="Pasajero no encontrado")
    id_passenger = passenger["id_passenger"]
    results = db.execute(
        '''
        SELECT
            c.id_passenger,
            c.id_product,
            s.tx_subcategory ||' '|| b.tx_product ||' ('||u.tx_unity||')' AS producto,
            DATE(c.dt_consumption) AS fc,
            c.nu_quantity,
            c.pc_unity,
            c.nu_quantity * c.pc_unity AS pc_total    
        FROM bt_consumption c INNER JOIN bt_product b
        ON c.id_product = b.id_product
        INNER JOIN lkp_subcategories s
        ON b.id_subcategory = s.id_subcategory
        INNER JOIN lkp_units u
        ON b.id_unity = u.id_unity
        WHERE b.flag_ctrl = 1
        AND c.id_passenger = ?
        ORDER BY 4;
        ''', (id_passenger,)
    ).fetchall()
    # Vuelve a pasar la lista de pasajeros para el select
    passengers = [row["tx_email"] for row in db.execute("SELECT tx_email FROM bt_passenger").fetchall()]
    return render_template("passengers/consumption_passenger.html", passengers=passengers, results=results, selected=passenger_email)

@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth_passengers.front"))