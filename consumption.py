import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, session
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db

bp = Blueprint("consumption", __name__)


# Servicio de Internet
query_internet = """
            SELECT
                pp.id_product_price,
                pr.id_product,
                s.tx_subcategory||' '||pr.tx_product AS txt_product,
                pp.nu_price_usd
            FROM bt_product_prices pp INNER JOIN bt_product pr
            ON pp.id_product = pr.id_product
            INNER JOIN lkp_subcategories s
            ON pr.id_subcategory = s.id_subcategory
            WHERE pr.id_subcategory = 93
            AND pr.flag_ctrl = 1
            AND dt_to = '2100-12-31'
            ORDER BY 3;
            """


# Relacion Cabina-Pasajero
query_occ_pass = """
            SELECT
                co.id_cabin,
                co.id_passenger,
                ps.tx_name||' '||ps.tx_surname AS passenger_name
            FROM bt_cabin_occupation co INNER JOIN bt_passenger ps
            ON co.id_passenger = ps.id_passenger
            WHERE 1= 1
            AND co.id_cabin = ?
            -- es necesario completar con la condición de fecha de viaje????
            -- ORDER BY 3;
            """


# Cabinas
query_occ_cabins = """
            SELECT id_cabin, nu_cabin||' - '||tx_cabin_type AS tx_cabin_desc FROM lkp_cabins ORDER BY 2
            """

# Pasajeros
query_det_pass = """
            SELECT
                p.id_passenger,
                p.tx_name,
                p.tx_surname
            FROM bt_passenger p
            JOIN bt_cabin_occupation co ON p.id_passenger = co.id_passenger
            WHERE co.id_cabin = ?;
            """

# Categorias
query_det_cats = """
            SELECT
                id_category AS id,
                tx_category AS categoria
            FROM lkp_categories;
            """

# Productos Internet
@bp.route("/consumption/inet")
@login_required
def prods_inet():
    db = get_db()
    inet = db.execute(query_internet).fetchall()
    cabs = db.execute(query_occ_cabins).fetchall()
    return render_template("consumption/inet_service.html", inet = inet, cabs = cabs)


# Obtengo los pasajeros por cabina
@bp.route("/consumption/get_passengers_htmx", methods=["POST"])
@login_required
def get_passengers_htmx():
    cabin_id = request.form.get("cabin")  # HTMX envía los datos del formulario
    if cabin_id:
        db = get_db()
        psg = db.execute(query_occ_pass, (cabin_id,)).fetchall()
        return render_template("consumption/_passenger_options.html", passengers = psg)
    return "" # Devuelve una cadena vacía si no hay cabin_id



# Agrego los productos de internet adquiridos
@bp.route("/consumption/enter_shop", methods=["GET", "POST"])
@login_required
def enter_shop():
    if request.method == "POST":
        # dtoday = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        dtoday = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        iplan = request.form["id_iplan"]
        niplan = iplan.replace("(", "").replace(")", "")
        prd = niplan.split(', ')[0]
        prc = niplan.split(', ')[1]
        psgr = request.form["passenger"]
        qty = request.form["qtty"]
        oper = session.get("user_id")
        db = get_db()
        db.execute("INSERT INTO bt_consumption (id_product, id_passenger, dt_consumption, nu_quantity, pc_unity) VALUES (?,?,?,?,?)",
                   (prd, psgr, dtoday, qty, prc),
                   )
        db.commit()
    flash('Se envió a la cuenta del cliente, la compra realizada.')
    return redirect(url_for("auth.redirectlink"))


def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    cur.close()

@bp.route('/consumption/inicio')
@login_required # Si requieres autenticación para ver la lista de cabinas
def index():
    db = get_db()
    cabinas = db.execute(query_occ_cabins).fetchall()
    return render_template('consumption/index.html', cabins = cabinas)

@bp.route('/pasajeros/<cabin_id>')
@login_required
def pasajeros_cabina(cabin_id):
    db = get_db()
    pasajeros = db.execute(query_det_pass, (cabin_id,))
    return render_template('consumption/pasajeros_cabina.html', pasajeros=pasajeros)


@bp.route('/productos/<passenger_id>')
@login_required
def productos_pasajero(passenger_id):
    db = get_db()
    categorias = db.execute(query_det_cats)
    return render_template('consumption/categorias_pasajero.html', categorias=categorias, pasajero_id=passenger_id)

@bp.route('/productos_categoria/<passenger_id>/<category_id>')
@login_required
def productos_categoria(passenger_id, category_id):
    db = get_db()
    productos = query_db("""
        SELECT
            pp.id_product_price AS id,
            pr.id_product,
            s.tx_subcategory||' '||pr.tx_product AS nombre,
            pp.nu_price_usd AS precio
        FROM bt_product_prices pp
        INNER JOIN bt_product pr ON pp.id_product = pr.id_product
        INNER JOIN lkp_subcategories s ON pr.id_subcategory = s.id_subcategory
        WHERE pr.id_category = ?
        AND pr.flag_ctrl = 1
        AND pp.dt_to = '2100-12-31'
        ORDER BY 3;
    """, (category_id,))
    return render_template('consumption/productos_categoria.html', productos=productos, passenger_id=passenger_id)

@bp.route('/registrar_consumo', methods=['POST'])
@login_required
def registrar_consumo():
    passenger_id = request.form['passenger_id']
    cabin_id = request.form['cabin_id']
    productos_seleccionados = {}
    for key, value in request.form.items():
        if key.startswith('producto_') and value:
            producto_id = key.split('_')[1]
            productos_seleccionados[producto_id] = int(value)

    if passenger_id and cabin_id and productos_seleccionados:
        for producto_id, cantidad in productos_seleccionados.items():
            producto = query_db("SELECT nu_price_usd FROM bt_product_prices WHERE id_product_price = ?", (producto_id,), one=True) # Usar id_product_price
            if producto:
                execute_db(
                    """
                    INSERT INTO bt_consumption (id_product, id_passenger, dt_consumption, nu_quantity, pc_unity)
                    VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
                    """,
                    (producto_id, passenger_id, cantidad, producto['nu_price_usd']) # Usar nu_price_usd
                )
        flash('Consumo registrado exitosamente.', 'success')
        return redirect(url_for('consumption.index')) # Redirigir a la lista de cabinas
    else:
        flash('Error al registrar el consumo.', 'danger')
        return redirect(request.referrer) # Redirigir de vuelta al formulario
    
