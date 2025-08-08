import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, session, Response
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db

bp = Blueprint("consumption", __name__)


# Servicios y Productos
query_svcprd = """
            SELECT
                id_product_price,
                id_product,
                producto,
                nu_price_usd,
                id_subcategory,
                id_category
            FROM
            (
            SELECT
                p.id_product_price,
                p.id_product,
                s.tx_subcategory ||' - '|| b.tx_product|| ' x '|| u.tx_unity AS producto,
                p.nu_price_usd,
                s.id_subcategory,
                s.id_category
            FROM bt_product_prices p INNER JOIN bt_product b
            ON p.id_product = b.id_product
            INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            WHERE p.dt_to = '2100-12-31'
            AND p.flag_price = 1
                            
            UNION             

            SELECT
                p.id_product_price,
                p.id_product,
                'Tragos'||' - '|| d.tx_drink AS producto,
                p.nu_price_usd,
                1000 AS id_subcategory,
                1 AS id_category
            FROM bt_product_prices p INNER JOIN lkp_drinks d
            ON p.id_product = d.id_drink
            WHERE p.dt_to = '2100-12-31'
            AND p.flag_price = 1
            ) a
            """


# Relacion Cabina-Pasajero
query_occ_pass = """
            SELECT
                co.id_cabin,
                co.id_passenger,
                ps.tx_name||' '||ps.tx_surname AS passenger_name
            FROM bt_cabin_occupation co INNER JOIN bt_passenger ps
            ON co.id_passenger = ps.id_passenger
            INNER JOIN lkp_campaign cp -- Se agrega para filtrar por campaña vigente
            ON cp.id_campaign = co.id_campaign
            WHERE 1 = 1
            AND cp.flag_vigency = 1
            AND co.id_cabin = ?
            ;
            """


# Cabinas
query_occ_cabins = """
            SELECT id_cabin, nu_cabin||' - '||tx_cabin_type AS tx_cabin_desc FROM lkp_cabins ORDER BY 2
            """


# Pasajeros con consumos por cabina (trip vigente)
query_ocp = """
            SELECT DISTINCT
                '('||b.nu_cabin||') '||p.tx_name ||' '||p.tx_surname AS tx_passenger,
                p.id_passenger
            FROM bt_passenger p INNER JOIN bt_cabin_occupation o
            ON p.id_passenger = o.id_passenger
            INNER JOIN lkp_cabins b
            ON o.id_cabin = b.id_cabin
            LEFT JOIN bt_consumption c
            ON p.id_passenger = c.id_passenger
            INNER JOIN lkp_campaign g
            ON o.id_campaign = g.id_campaign
            WHERE g.flag_vigency = 1
            ORDER BY 1
            """

# Consumos por pasajero
query_consumption = """
                    SELECT *
                    FROM
                    (
                    SELECT
                        c.id_passenger,
                        h.id_ticket,
                        c.id_product,
                        s.tx_subcategory ||' '|| b.tx_product AS producto,
                        STRFTIME('%Y-%m-%d %H:%M', c.dt_consumption) AS fc,
                        c.nu_quantity,
                        c.pc_unity,
                        c.nu_quantity * c.pc_unity AS pc_total    
                    FROM bt_consumption c INNER JOIN bt_product b
                    ON c.id_product = b.id_product
                    INNER JOIN bt_ticket_header h
                    ON c.id_ticket = h.id_ticket
                    INNER JOIN lkp_subcategories s
                    ON b.id_subcategory = s.id_subcategory
                    WHERE b.flag_ctrl = 1
                    
                    UNION
                    
                    SELECT
                        c.id_passenger,
                        h.id_ticket,
                        c.id_product,
                        'Tragos - '|| d.tx_drink,
                        STRFTIME('%Y-%m-%d %H:%M', c.dt_consumption) AS fc,
                        c.nu_quantity,
                        c.pc_unity,
                        c.nu_quantity * c.pc_unity AS pc_total
                    FROM bt_consumption c INNER JOIN lkp_drinks d
                    ON c.id_product = d.id_drink
                    INNER JOIN bt_ticket_header h
                    ON c.id_ticket = h.id_ticket
                    WHERE d.flag_available = 1
                    ) a
                    WHERE id_passenger = (?)
                    ORDER BY 2;
                """


# Venta de Productos y Servicios
@bp.route("/consumption/services")
@login_required
def prods_services():
    db = get_db()
    id_subcategories_raw = request.args.getlist('id_scat')
    id_subcategories = []
    for s_id in id_subcategories_raw:
        if isinstance(s_id, str) and s_id.isdigit(): 
            id_subcategories.append(int(s_id))
    if not id_subcategories:
        flash('No se proporcionaron IDs de subcategoría válidos')
    scat_select = f'WHERE a.id_subcategory IN ({", ".join(map(str, id_subcategories))})'
    sort = ' AND a.id_product <> 1260 ORDER BY 3;' # Excluyo el Upgrade de Cabina
    srvc = db.execute(query_svcprd + scat_select + sort).fetchall()
    cabs = db.execute(query_occ_cabins).fetchall()
    template_name = "" # Inicializa para evitar posibles errores si ninguna condición se cumple
    # Combinación de 46 y 47 (Merchandising)
    if 46 in id_subcategories and 47 in id_subcategories:
        template_name = "consumption/merchan_service.html"
    # Subcategoría 93 (Internet)
    elif len(id_subcategories) == 1 and 93 in id_subcategories:
        template_name = "consumption/inet_service.html"
    elif len(id_subcategories) == 1 and 97 in id_subcategories:
         template_name = "consumption/laundry_service.html"
    else:
        pass
    if not template_name:
        flash('No existe una plantilla válida')
    return render_template(template_name, srvc = srvc, cabs = cabs, current_subcategories=id_subcategories)


# Agrego los servicios de adquiridos (internet y lavanderia) a la cuenta del pasajero
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
        db.execute("INSERT INTO bt_ticket_header (dt_ticket, id_passenger, id_user) VALUES (?,?,?)",
                   (dtoday, psgr, oper),
                    )
        db.commit()
        req_tkt = db.execute('SELECT MAX(id_ticket) AS mxm FROM bt_ticket_header;').fetchone()[0]
        db.execute("INSERT INTO bt_consumption (id_ticket, id_product, id_passenger, dt_consumption, nu_quantity, pc_unity) VALUES (?,?,?,?,?,?)",
                   (req_tkt, prd, psgr, dtoday, qty, prc),
                   )
        db.commit()
    flash('Se envió a la cuenta del pasajero, la compra realizada.')
    return redirect(url_for("auth.redirectlink"))


# Obtengo los pasajeros por cabina
@bp.route("/consumption/get_passengers_htmx", methods=["POST"])
@login_required
def get_passengers_htmx():
    cabin_id = request.form.get("cabin")  # HTMX envía los datos del formulario
    show_quantity_str = request.form.get('show_quantity', 'false')
    show_quantity = show_quantity_str.lower() == 'true'
    id_category = request.form.get('id_cat', type=int)
    if cabin_id:
        db = get_db()
        psg = db.execute(query_occ_pass, (cabin_id,)).fetchall()
        return render_template("consumption/_passenger_options.html",
                               passengers = psg,
                               show_quantity = show_quantity,
                               id_category=id_category)
    return "" # Devuelve una cadena vacía si no hay cabin_id


# Venta de ropa y consumos del bar: cargo las cabinas para iniciar el proceso
@bp.route('/consumption/clbar', methods=["GET", "POST"])
@login_required
def clbar():
    id_category = request.args.get('id_cat', type=int)
    db = get_db()
    cabs = db.execute(query_occ_cabins).fetchall()
    if id_category == 10:
        template_name = "consumption/clothes.html"
    else:
        template_name = "consumption/bar.html"
    return render_template(template_name, cabs = cabs, id_category=id_category)


# Obtengo los productos - ver variables con condiciones
@bp.route("/consumption/get_products_htmx", methods=["GET", "POST"])
@login_required
def get_products_htmx():
    id_category = request.args.get('id_cat', type=int)
    db = get_db()
    scat_select = f' WHERE id_category = {id_category} AND id_subcategory <> 93'
    sort = ' ORDER BY 3;'
    prods = db.execute(query_svcprd + scat_select + sort).fetchall()
    return render_template("consumption/_products_options.html", prods = prods)


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
            id_product,
            producto,
            nu_price_usd
        FROM ({query_svcprd}) AS subquery_products
        WHERE id_product IN ({prds});
    """
    try:
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
            else:
                print(f"Warning: Product ID {product_id} not found in query results.") #consola
                flash(f"Advertencia: El producto con ID {product_id} no fue encontrado o no está vigente.", "warning")
    except Exception as e:
        print(f"Error in process_product_selection: {e}") # consola
        flash("Ocurrió un error al procesar tu selección. Inténtalo de nuevo.", "error")
    # Visualización de la plantilla de resumen
    return render_template('consumption/_order_summary.html',
                           order_items = order_items,
                           total_order_value = total_order_value,
                           passenger_id=passenger_id
                           )



# Proceso el pedido de productos seleccionados -- proviene de _order_summary.html
@bp.route('/process_order', methods=["GET", "POST"])
@login_required
def process_order():
    if request.method == 'POST':
        psg = request.form['passenger_id']
        oitem = request.form.getlist('ordered_pid')
        oqty = request.form.getlist('ordered_qty')
        oupr = request.form.getlist('ordered_upr')
        dtoday = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        oper = session.get("user_id")
        db = get_db()
        db.execute("INSERT INTO bt_ticket_header (dt_ticket, id_passenger, id_user) VALUES (?,?,?)",
                   (dtoday, psg, oper),
                    )
        db.commit()
        req_tkt = db.execute('SELECT MAX(id_ticket) AS mxm FROM bt_ticket_header;').fetchone()[0]
        for oitems, oqtys, ouprs in zip (oitem, oqty, oupr):
            db.execute("INSERT INTO bt_consumption (id_ticket, id_product, id_passenger, dt_consumption, nu_quantity, pc_unity) VALUES (?,?,?,?,?,?)",
                           (req_tkt ,oitems, psg, dtoday, oqtys, ouprs),
                           )
        db.commit()
        flash('Los productos han sido agregados a la cuenta del pasajero.  Preparando impresión...')
        return redirect(url_for("print_module.print_ticket_page", ticket_id=req_tkt))
        #return redirect(url_for("auth.redirectlink"))





# Impresiones - MODIFICAR AL TENER LA IMPRESORA FUNCIONANDO
@bp.route('/get_ticket_details_for_print', methods=['POST'])
@login_required
def get_ticket_details_for_print(ticket_id):
    """
    Obtengo todos los detalles del ticket (encabezado e ítems) para su impresión.
    Retorna un diccionario con 'header' y 'items', o None si no se encuentra.
    """
    db = get_db()
    # Consulta para obtener los detalles del ticket y sus ítems
    ticket_data = db.execute(
        """SELECT
            h.id_ticket,
            h.dt_ticket,
            h.id_passenger,
            s.tx_subcategory||' - ' || p.tx_product AS product,
            c.nu_quantity,
            c.pc_unity
        FROM bt_ticket_header h INNER JOIN bt_consumption c
        ON h.id_ticket = c.id_ticket
        INNER JOIN bt_product p
        ON p.id_product = c.id_product
        INNER JOIN lkp_subcategories s
        ON s.id_subcategory = p.id_subcategory
        WHERE h.id_ticket = ?;""",
        (ticket_id,)
    ).fetchall()
    if not ticket_data:
        return None
    # Separo encabezado e ítems
    header = {
        'id_ticket': ticket_data[0]['id_ticket'],
        'dt_ticket': ticket_data[0]['dt_ticket'],
        'id_passenger': ticket_data[0]['id_passenger']
    }
    items = []
    for item in ticket_data:
        items.append({
            'product': item['product'],
            'nu_quantity': item['nu_quantity'],
            'pc_unity': item['pc_unity']
        })
    return {'header': header, 'items': items}


# Traigo el nombre del pasajero (Revisar - se usa en el proceso anterior. Simplificar)
@bp.route('/get_passenger_name_by_id', methods=['POST'])
@login_required
def get_passenger_name_by_id(passenger_id):
   # Obtengo el nombre completo de un pasajero por su ID.
    db = get_db()
    passenger = db.execute(
        "SELECT tx_name, tx_surname FROM bt_passenger WHERE id_passenger = ?",
        (passenger_id,)
    ).fetchone()
    if passenger:
        return f"{passenger['tx_name']} {passenger['tx_surname']}"
    return "Pasajero Desconocido"


# Consumos y PSW por pasajero (obtengo los pasajeros con consumos del trip) en PV
@bp.route("/consumption/info_passenger", methods=["GET", "POST"])
@login_required
def info_passenger():
    idtype = request.args.get('id_type', type=int)
    db = get_db()
    pcons = db.execute(query_ocp).fetchall()
    if not pcons:
        flash('Aún no hay pasajeros con consumos registrados para este viaje.')
        return redirect(url_for("auth.redirectlink"))
    else:
        if idtype == 1:
            template_name = "consumption/pass_consptn.html"
        else:
            template_name = "consumption/psw_passenger.html"
        return render_template(template_name, pcons = pcons)


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
    total_general = sum(item['pc_total'] for item in get_cons) if get_cons else 0
    return render_template("consumption/_cons_passenger.html", get_cons = get_cons, total_general = total_general)


# Recupero la psw del pasajero seleccionado
@bp.route("/consumption/get_psw_htmx", methods=["GET"])
@login_required
def get_psw_htmx():
    db = get_db()
    passenger_id = request.args.get('id_pass')
    # Mensaje que se muestra antes de seleccionar un pasajero
    if not passenger_id:
        return "<p>Selecciona un pasajero para ver sus consumos.</p>"
    get_psw = db.execute(
        "SELECT tx_email, tx_password FROM bt_passenger WHERE id_passenger = ?",
        (passenger_id,)
    ).fetchone()
    return render_template("consumption/_cons_psw.html", get_psw = get_psw)


# Genero listas de productos para tragos para su alta
@bp.route("/consumption/drink_ing", methods=["GET"])
@login_required
def drink_ing():
    db = get_db()
    ings = f"""
            SELECT
                p.id_product,
                s.tx_subcategory ||' - '||p.tx_product AS desc_product
            FROM bt_product p INNER JOIN lkp_subcategories s
            ON p.id_subcategory = s.id_subcategory
            WHERE p.id_category = 1
            AND p.flag_ctrl = 1
            AND p.id_subcategory NOT IN (98)
            ORDER BY 2;
            """
    drinks = db.execute(ings).fetchall()
    return render_template("consumption/drink_ing.html",
                            ing1 = drinks,
                            ing2 = drinks,
                            ing3 = drinks,
                            ing4 = drinks)


# Genero alta del trago y su precio
@bp.route("/consumption/add_drink", methods=["GET", "POST"])
@login_required
def add_drink():
    if request.method == "POST":
        dtoday = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        ndr = request.form['n_dr']
        pr1 = request.form['id_dpr1']
        qi1 = request.form['q_i1']
        pr2 = request.form['id_dpr2']
        qi2 = request.form['q_i2']
        pr3 = request.form['id_dpr3']
        qi3 = request.form['q_i3']
        pr4 = request.form['id_dpr4']
        qi4 = request.form['q_i4']
        price = request.form['nu_pr']
        oper = session.get("user_id")
        # Manejo de nulos
        pr2 = None if not pr2 or pr2 == "Seleccionar producto" else pr2
        qi2 = None if not qi2 else qi2
        pr3 = None if not pr3 or pr3 == "Seleccionar producto" else pr3
        qi3 = None if not qi3 else qi3
        pr4 = None if not pr4 or pr4 == "Seleccionar producto" else pr4
        qi4 = None if not qi4 else qi4
        db = get_db()
        db.execute("INSERT INTO lkp_drinks (tx_drink, id_ing1, qty_ing1, id_ing2, qty_ing2, id_ing3, qty_ing3, id_ing4, qty_ing4) VALUES (?,?,?,?,?,?,?,?,?)",
                   (ndr, pr1, qi1, pr2, qi2, pr3, qi3, pr4, qi4),
                    )
        db.commit()
        req_drk = db.execute('SELECT MAX(id_drink) AS mxm FROM lkp_drinks;').fetchone()[0]
        db.execute("INSERT INTO bt_product_prices (id_product, nu_price_usd, dt_from, id_user) VALUES (?,?,?,?)",
                           (req_drk, price, dtoday, oper),
                           )
        db.commit()
        flash('El trago y su respectivo precio fueron existosamente dados de alta')
        return redirect(url_for("auth.redirectlink"))