from flask import Blueprint, render_template, request, flash, redirect, url_for, session, send_from_directory, current_app
from werkzeug.security import check_password_hash
from .db import get_db
from .send_email import send_mail
from flask_weasyprint import HTML, render_pdf
import os
from os.path import basename


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

@bp.route("/send_password_reset_email", methods=["POST"])
def send_password_reset_email():
    print("Hola")
    data = request.get_json()
    email = data.get('email', '').lower()
    if not email:
        return {"message": "Email requerido."}, 400
    db = get_db()
    user = db.execute(
        "SELECT tx_password, tx_name FROM bt_passenger WHERE tx_email = ?", (email,)
    ).fetchone()
    print(user['tx_name'])

    if user:
        password = user["tx_password"]
        username = user["tx_name"]
        try:
            send_mail(username, email, password)
            return {"message": "An email with your password has been sent. Check spam folder also."}, 200
        except Exception as e:
            print(f"Error al enviar correo: {e}")
            return {"message": "Error sending the email."}, 500
    else:
        return {"message": "Your email has not been registered. Please go to the ship's counter."}, 404


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
        SELECT * FROM(
        SELECT
            c.id_passenger,
            c.id_product,
            CASE
                    WHEN c.flag_anullment = 1 THEN 'CANCELLED - ' || s.tx_subcategory || ' ' || b.tx_product || ' '
                    ELSE s.tx_subcategory || ' ' || b.tx_product || ' (' || u.tx_unity || ')'
            END AS producto,
            STRFTIME('%Y-%m-%d %H:%M', c.dt_consumption) AS fc,
            c.nu_quantity,
            CASE WHEN c.flag_anullment = 1 THEN 0 ELSE c.pc_unity END AS pc_unity,
            CASE WHEN c.flag_anullment = 1 THEN 0 ELSE c.nu_quantity * c.pc_unity END AS pc_total,
            CASE
                WHEN c.flag_anullment = 1 THEN 'Cancel'
                WHEN c.flag_payment = 0 THEN 'Unpaid'
                WHEN c.flag_payment = 1 THEN 'Paid'
            END AS res_flag
        FROM bt_consumption c INNER JOIN bt_product b
        ON c.id_product = b.id_product
        INNER JOIN lkp_subcategories s
        ON b.id_subcategory = s.id_subcategory
        INNER JOIN lkp_units u
        ON b.id_unity = u.id_unity
        WHERE b.flag_ctrl = 1
        AND c.id_passenger = ?
        UNION
        SELECT
        c.id_passenger,
        c.id_product,
        'Drink - '|| d.tx_drink,
        STRFTIME('%Y-%m-%d %H:%M', c.dt_consumption) AS fc,
        c.nu_quantity,
        CASE WHEN c.flag_anullment = 1 THEN 0 ELSE c.pc_unity END AS pc_unity,
        CASE WHEN c.flag_anullment = 1 THEN 0 ELSE c.nu_quantity * c.pc_unity END AS pc_total,
        CASE
                WHEN c.flag_anullment = 1 THEN 'Cancel'
                WHEN c.flag_payment = 0 THEN 'Unpaid'
                WHEN c.flag_payment = 1 THEN 'Paid'
        END AS res_flag
        FROM bt_consumption c INNER JOIN lkp_drinks d
        ON c.id_product = d.id_drink
        INNER JOIN bt_ticket_header h
        ON c.id_ticket = h.id_ticket
        WHERE d.flag_available = 1
        ) a
        WHERE a.id_passenger = ?
        ORDER BY 4;
        ''', (id_passenger, id_passenger)
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
        SELECT * FROM(
        SELECT
            c.id_passenger,
            c.id_product,
            CASE
                    WHEN c.flag_anullment = 1 THEN 'CANCELLED - ' || s.tx_subcategory || ' ' || b.tx_product || ' '
                    ELSE s.tx_subcategory || ' ' || b.tx_product || ' (' || u.tx_unity || ')'
            END AS producto,
            STRFTIME('%Y-%m-%d %H:%M', c.dt_consumption) AS fc,
            c.nu_quantity,
            CASE WHEN c.flag_anullment = 1 THEN 0 ELSE c.pc_unity END AS pc_unity,
            CASE WHEN c.flag_anullment = 1 THEN 0 ELSE c.nu_quantity * c.pc_unity END AS pc_total

        FROM bt_consumption c INNER JOIN bt_product b
        ON c.id_product = b.id_product
        INNER JOIN lkp_subcategories s
        ON b.id_subcategory = s.id_subcategory
        INNER JOIN lkp_units u
        ON b.id_unity = u.id_unity
        WHERE b.flag_ctrl = 1
        -- AND c.id_passenger = ?
        UNION
        SELECT
        c.id_passenger,
        c.id_product,
        'Drink - '|| d.tx_drink,
        STRFTIME('%Y-%m-%d %H:%M', c.dt_consumption) AS fc,
        c.nu_quantity,
        CASE WHEN c.flag_anullment = 1 THEN 0 ELSE c.pc_unity END AS pc_unity,
        CASE WHEN c.flag_anullment = 1 THEN 0 ELSE c.nu_quantity * c.pc_unity END AS pc_total
        FROM bt_consumption c INNER JOIN lkp_drinks d
        ON c.id_product = d.id_drink
        INNER JOIN bt_ticket_header h
        ON c.id_ticket = h.id_ticket
        WHERE d.flag_available = 1
        ) a
        WHERE a.id_passenger = ?
        ORDER BY 4;
        ''', (id_passenger, id_passenger)
    ).fetchall()
    # Vuelve a pasar la lista de pasajeros para el select
    passengers = [row["tx_email"] for row in db.execute("SELECT tx_email FROM bt_passenger").fetchall()]
    return render_template("passengers/consumption_passenger.html", passengers=passengers, results=results, selected=passenger_email)

@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth_passengers.front"))





query_svcprd = """
        SELECT
            a.id_product_price,
            a.id_product,
            a.producto,
            a.nu_price_usd,
            a.id_subcategory,
            a.id_category
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
            AND p.nu_price_usd > 0
            AND b.flag_ctrl = 1

            UNION ALL

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
            AND p.nu_price_usd > 0
            ) a
            """



# Mapeo de IDs de subcategorías a sus nombres
subcategory_names = {
    '97': 'Laundry Service',
    '93': 'Internet Service'
}

# Mapeo de IDs de categorías a sus nombres (para el título del PDF)
category_names = {
    '1': 'Bar & Drinks',
    '10': 'Clothes',
    '11': 'Books',
    '13': 'Ushuaia Ship Products',
    '14': 'Ushuaia Ship Products'
}

# Listado de Precios de Productos y Servicios
@bp.route("/lista-precios")
def generar_lista_precios():
    db = get_db()
    ids_list = []
    cat_name = 'Price List'
    where_clause_column = ''
    # Función auxiliar para limpiar y obtener IDs
    def get_cleaned_ids(param_name):
        param_value = request.args.get(param_name)
        if param_value:
            cleaned = param_value.strip().replace('[', '').replace(']', '')
            return [id_str.strip() for id_str in cleaned.split(',') if id_str.strip()]
        return []

    # Determinar el modo de filtrado (ids / Subs o idc 7 Cats)
    ids_list = get_cleaned_ids('ids')
    if ids_list:
        where_clause_column = 'a.id_subcategory'
    else:
        ids_list = get_cleaned_ids('idc')
        if ids_list:
            where_clause_column = 'a.id_category'
        else:
            # Valor por default: Bar & Drinks (id_category = 1)
            ids_list = ['1']
            where_clause_column = 'a.id_category'
            cat_name = 'Bar & Drinks'

    # Construir la cláusula WHERE final
    id_list_str = ', '.join(f"'{id}'" for id in ids_list)
    where_clause = f"{where_clause_column} IN ({id_list_str})"
    # Solo aplica a categorias
    if where_clause_column == 'a.id_category':
        if '1' in ids_list:
            where_clause = f"({where_clause_column} IN ({id_list_str})) OR (a.id_subcategory = 1000)"
        where_clause = f"({where_clause}) AND a.id_subcategory NOT IN ('93', '97')"
    # Ejecuto la consulta final
    query = f'{query_svcprd} WHERE {where_clause} ORDER BY 3;'
    prods = db.execute(query).fetchall()
    html = render_template('passengers/price_list.html', prods = prods, cat_name=cat_name)
    return render_pdf(HTML(string=html))


# Abro el archivo de Menu o Actividades (desde archivo pdf)
@bp.route("/upl_files/files", methods=["GET"])
def open_information():
    redirect_url = request.referrer # redirecciona a la página de la cuál proviene la solicitud
    fito = request.args.get('fto')
    if fito == '1':
        filename = 'menu.pdf'
    elif fito == '2':
        filename = 'activities.pdf'
    else:
        flash("Parámetro 'fto' inválido o faltante.")
        return redirect(redirect_url)
    directory = os.path.join(current_app.root_path, 'upl_files')
    try:
        return send_from_directory(
            directory=directory,
            path=filename
            # as_attachment=True -- descomentar para poder descargarlo
        )
    except FileNotFoundError:
        flash(f"El destino '{filename}' no fue encontrado. Por favor, asegúrese de haberlo subido.")
        return redirect(redirect_url)