import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, session
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db

bp = Blueprint("consumption", __name__)


# Servicios y Productos
query_svcprd = """
            SELECT
                pp.id_product_price,
                pp.id_product,
                s.tx_subcategory||' - '|| p.tx_product ||' ('||u.tx_unity||')' AS producto,
                pp.nu_price_usd
            FROM bt_product_prices pp INNER JOIN bt_product p
            ON pp.id_product = p.id_product
            INNER JOIN lkp_subcategories s
            ON p.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON p.id_unity = u.id_unity
            WHERE DATE(pp.dt_to) > CURRENT_DATE
            AND p.flag_ctrl = 1
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


# Pasajeros (no se usa en ninguna funcion - candidato a borrar)
query_det_pass = """
            SELECT
                p.id_passenger,
                p.tx_name,
                p.tx_surname
            FROM bt_passenger p
            JOIN bt_cabin_occupation co ON p.id_passenger = co.id_passenger
            -- WHERE co.id_cabin = ?;
            """


# Categorias (no se usa en ninguna funcion - candidato a borrar)
query_det_cats = """
            SELECT
                id_category AS id,
                tx_category AS categoria
            FROM lkp_categories;
            """


# Selecciono trip por pasajero (no se usa en ninguna funcion - candidato a borrar)
query_trpass = """
                    SELECT
                        o.id_occupation,
                        o.id_passenger,
                        p.tx_name ||' ' || p.tx_surname AS nyap,
                        r.tx_route
                    FROM bt_cabin_occupation o INNER JOIN bt_passenger p
                    ON o.id_passenger = p.id_passenger
                    INNER JOIN lkp_campaign c
                    ON o.id_campaign = c.id_campaign
                    INNER JOIN lkp_routes r
                    ON c.id_route = r.id_route
                    WHERE c.flag_vigency = 1
                    AND o.id_passenger = (?);
                """

# Consumos por pasajero
query_consumption = """
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
                    AND c.id_passenger = (?)
                    ORDER BY 4;
                """


# Venta de Productos de Internet
@bp.route("/consumption/inet")
@login_required
def prods_inet():
    db = get_db()
    scat_select = 'AND p.id_subcategory = 93'
    sort = ' ORDER BY 3;'
    inet = db.execute(query_svcprd + scat_select + sort).fetchall()
    cabs = db.execute(query_occ_cabins).fetchall()
    return render_template("consumption/inet_service.html", inet = inet, cabs = cabs)


# Obtengo los pasajeros por cabina
@bp.route("/consumption/get_passengers_htmx", methods=["POST"])
@login_required
def get_passengers_htmx():
    cabin_id = request.form.get("cabin")  # HTMX envía los datos del formulario
    show_quantity_str = request.form.get('show_quantity', 'false')
    show_quantity = show_quantity_str.lower() == 'true'
    if cabin_id:
        db = get_db()
        psg = db.execute(query_occ_pass, (cabin_id,)).fetchall()
        return render_template("consumption/_passenger_options.html", passengers = psg, show_quantity = show_quantity)
    return "" # Devuelve una cadena vacía si no hay cabin_id


# Obtengo los productos - ver variables con condiciones
@bp.route("/consumption/get_products_htmx", methods=["GET", "POST"])
@login_required
def get_products_htmx():
    db = get_db()
    scat_select = ' AND p.id_category = 10 AND p.id_subcategory <> 93'
    sort = ' ORDER BY 3;'
    prods = db.execute(query_svcprd + scat_select + sort).fetchall()
    return render_template("consumption/_products_options.html", prods = prods)


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


# Venta de ropa: cargo las cabinas para iniciar el proceso
@bp.route('/consumption/clothes')
@login_required
def clothes():
    db = get_db()
    cabs = db.execute(query_occ_cabins).fetchall()
    return render_template('consumption/clothes.html', cabs = cabs)


# Selecciono productos por pasajero
@bp.route('/process_product_selection', methods=['POST'])
@login_required
def process_product_selection():
    selected_product_ids = request.form.getlist('selected_products') 
    passenger_id = request.form.get('passenger') 
    # cabin_id = request.form.get('cabin') 
    order_items = []
    total_order_value = 0.0
    db = get_db()
    # Si no hay productos seleccionados, devuelvo mensaje
    if not selected_product_ids:
        return render_template('consumption/_order_summary.html', order_items=[], total_order_value=0.0, message="No se seleccionó ningún producto.")
    prds = ','.join('?' for _ in selected_product_ids)
    query_selected_products_details = f"""
        SELECT
            pp.id_product,
            s.tx_subcategory||' - '|| p.tx_product ||' ('||u.tx_unity||')' AS producto,
            pp.nu_price_usd
        FROM bt_product_prices pp INNER JOIN bt_product p
        ON pp.id_product = p.id_product
        INNER JOIN lkp_subcategories s
        ON p.id_subcategory = s.id_subcategory
        INNER JOIN lkp_units u
        ON p.id_unity = u.id_unity
        WHERE DATE(pp.dt_to) > CURRENT_DATE
        AND p.flag_ctrl = 1
        AND pp.id_product IN ({prds});
    """
    # Obtengo detalles de todos los productos seleccionados
    selected_products_data = db.execute(query_selected_products_details, selected_product_ids).fetchall()
    # Diccionario para fácil acceso por id_product
    products_details_map = {p['id_product']: p for p in selected_products_data}
    for product_id_str in selected_product_ids:
        product_id = int(product_id_str)
        quantity_key = f'quantity_{product_id}'
        quantity_str = request.form.get(quantity_key, '1') # Por defecto 1 si no se envía o está vacío
        try:
            quantity = int(quantity_str)
            if quantity < 1: # para segurar que la cantidad sea al menos 1
                quantity = 1
        except ValueError:
            quantity = 1 # Indico si no es un número
        # Obtengo el detalle del producto
        product_detail = products_details_map.get(product_id)
        if product_detail:
            unit_price = product_detail['nu_price_usd']
            item_total = unit_price * quantity
            total_order_value += item_total
            order_items.append({
                'id_product': product_id,
                'producto': product_detail['producto'],
                'unit_price': unit_price,
                'quantity': quantity,
                'item_total': item_total
            })
    # Visualización de la plantilla de resumen
    return render_template('consumption/_order_summary.html',
                           order_items = order_items,
                           total_order_value = total_order_value,
                           passenger_id=passenger_id, 
                           # cabin_id=cabin_id 
                           )

# Procesar el pedido de productos seleccionados
@bp.route('/process_clothes_order', methods=["GET", "POST"])
@login_required
def process_clothes_order():
    if request.method == 'POST':
        psg = request.form['passenger_id']
        oitem = request.form.getlist('ordered_pid')
        oqty = request.form.getlist('ordered_qty')
        oupr = request.form.getlist('ordered_upr')
        dtoday = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        db = get_db()
        for oitems, oqtys, ouprs in zip (oitem, oqty, oupr):
            db.execute("INSERT INTO bt_consumption (id_product, id_passenger, dt_consumption, nu_quantity, pc_unity) VALUES (?,?,?,?,?)",
                           (oitems, psg, dtoday, oqtys, ouprs))
        db.commit()
        flash('Los productos han sido agregados a la cuenta del pasajero.')
        return redirect(url_for("auth.redirectlink"))


# Consumos por pasajero (obtengo los pasajeros con consumos del trip)
@bp.route("/consumption/consumption_passenger", methods=["GET", "POST"])
@login_required
def consumption_passenger():
    db = get_db()
    get_pcons = """
            SELECT DISTINCT
                p.id_passenger,
                '('|| cb.nu_cabin ||') '|| p.tx_name ||' '|| p.tx_surname AS tx_passenger
            FROM bt_passenger p INNER JOIN bt_cabin_occupation oc
            ON p.id_passenger = oc.id_passenger
            INNER JOIN bt_consumption co
            ON p.id_passenger = co.id_passenger
            INNER JOIN lkp_cabins cb
            ON oc.id_cabin = cb.id_cabin
            INNER JOIN lkp_campaign cp
            ON (
                oc.id_campaign = cp.id_campaign
                AND  cp.flag_vigency = 1
                )
            ORDER BY 2;
                """
    pcons = db.execute(get_pcons).fetchall()
    if not pcons:
        flash('Aún no hay pasajeros con consumos registrados para este viaje.')
        return redirect(url_for("auth.redirectlink"))
    else:
        return render_template("consumption/pass_consptn.html", pcons = pcons)


# Obtengo los consumos realizados por el pasajero seleccionado
@bp.route("/consumption/get_consumptions_htmx", methods=["GET"])
@login_required
def get_consumptions_htmx():
    db = get_db()
    passenger_id = request.args.get('id_pass')
    # Mensaje que se muestra antes de seleccionar un pasajero
    if not passenger_id:
        return "<p>Selecciona un pasajero para ver sus consumos.</p>"
    get_cons = db.execute(query_consumption, (passenger_id,)).fetchall()
    return render_template("consumption/_cons_passenger.html", get_cons = get_cons)
