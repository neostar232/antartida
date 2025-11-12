import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, session, send_from_directory, current_app
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db
import os
from os.path import basename
from flask_weasyprint import HTML, render_pdf
import pandas as pd
import re

bp = Blueprint("passengers", __name__)


# Listado de rutas y descripción
query_trips = """
                SELECT
                    c.id_campaign,
                    c.id_trip ||' - '|| r.tx_route AS itinerary
                FROM lkp_campaign c INNER JOIN lkp_routes r
                ON c.id_route = r.id_route
                AND c.flag_vigency = 1
                ORDER BY c.dt_from;
                """


# Listado de cabinas y tipos
query_cabins = """
                SELECT
                    id_cabin,
                    nu_cabin||' - '|| tx_cabin_type AS cabin,
                    nu_cabin
                FROM lkp_cabins
                ORDER BY 2;
                """

# Listado de cabinas con disponibilidad
query_cabins_av = """
                SELECT
                    lc.id_cabin,
                    lc.nu_cabin||' - '|| lc.tx_cabin_type AS cabin,
                    lc.nu_cabin,
                    lc.nu_capacity - COALESCE(u.qpass, 0) AS available
                FROM lkp_cabins lc LEFT JOIN
                (
                    SELECT
                        co.id_cabin,
                        COUNT(co.id_passenger) AS qpass
                    FROM bt_cabin_occupation co INNER JOIN lkp_campaign kc
                    ON (
                        co.id_campaign = kc.id_campaign
                        AND kc.flag_vigency = 1
                        )
                    GROUP BY 1
                ) u
                ON lc.id_cabin = u.id_cabin
                GROUP BY 1, 2, 3, 4
                HAVING available > 0
                ORDER BY 2;
                """


# Completo ocupación
query_occ = """
                INSERT INTO bt_cabin_occupation (id_passenger, id_cabin, id_campaign)
                SELECT
                    b.id_passenger,
                    b.id_cabin,
                    b.id_campaign
                FROM bt_passenger b LEFT JOIN bt_cabin_occupation o
                ON (
                    b.id_passenger = o.id_passenger
                    AND b.id_campaign = o.id_campaign
                    AND b.id_cabin = o.id_cabin
                    )
                WHERE o.id_passenger IS NULL;
                """


# Alta de Pasajeros (direccionador)
@bp.route("/passengers/add_psngr", methods=["GET", "POST"])
@login_required
def add_psngr():
    db = get_db()
    trips = db.execute(query_trips).fetchall()
    cabins = db.execute(query_cabins_av).fetchall()
    return render_template("passengers/add_psngr.html", trips = trips, cabins = cabins)


# Alta de Pasajeros (procesador)
@bp.route("/passengers/addr_psngr", methods=["GET", "POST"])
@login_required
def addr_psngr():
    if request.method == "POST":
        # dtoday = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        name = request.form["napa"]
        sname = request.form["surpa"]
        tid = request.form["typid"]
        nid = request.form["nuid"]
        nnid = re.sub('[^A-Za-z0-9]+', '', nid)
        dborn = request.form["dateb"]
        mail = request.form["maila"]
        tel = request.form["tel1"]
        telop = request.form["tel2"]
        tst = request.form["nast"]
        nst = request.form["nust"]
        ct = request.form["city"]
        cz = request.form["czip"]
        prv = request.form["state"]
        cou = request.form["country"]
        trip = request.form["sel_trip"]
        cab_full = request.form["sel_cab"]
        divisor = cab_full.split('|')
        cab_id = divisor[0]
        cab_nro = divisor[1]
        # genero el valro que tomará la psw
        nnid = re.sub('[^A-Za-z0-9]+', '', nid)
        scab = str(cab_nro)
        cun = '@'
        valpas = cun.join([scab, nnid])
        db = get_db()
        db.execute("INSERT INTO bt_passenger (tx_name, tx_surname, tx_identification_type, nu_identification, dt_birth, tx_email, tx_password, nu_phone_number1, nu_phone_number2, tx_street, nu_street, nu_zip, tx_city, tx_province, tx_country, id_cabin, id_campaign) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (name, sname, tid, nid, dborn, mail, valpas, tel, telop, tst, nst, cz, ct, prv, cou, cab_id, trip),
                   )
        db.commit()
        db.execute(query_occ).fetchall()
        db.commit()
    flash('Pasajero correctamente ingresado.')
    return redirect(url_for("auth.redirectlink"))


# Alta de Pasajeros (selecciona archivo)
@bp.route("/passengers/add_psngr_file", methods=["GET", "POST"])
@login_required
def add_psngr_ff():
    return render_template("passengers/add_psngr_ff.html")


# Enlace a descarga de archivo/instructivo
@bp.route("/passengers/how_to")
@login_required
def how_to():
    app_root = current_app.root_path
    # directory = os.path.join('static', 'vs')
    directory = 'static/vs'
    dirpath = os.path.join(app_root, directory)
    filename = 'Pasajeros_Buque.xlsx'
    # return send_from_directory(directory, filename, as_attachment=True)
    return send_from_directory(dirpath, filename, as_attachment=True)



# Alta de Pasajeros (bulk desde archivo)
@bp.route("/passengers/addr_psngr_ff", methods=["GET", "POST"])
@login_required
def addr_psngr_ff():
    if request.method == "POST":
        file = request.files["file"]
        if file and file.filename.endswith('.csv'):
            # Cambio la ruta absoluta para que lo lea desde cualquier estructura
            # root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../ushuaia"))
            root = current_app.root_path
            directory = 'upl_files'
            filename = os.path.join(root, directory, file.filename)
            file.save(filename)
            # Hasta acá se sube el archivo CSV para agregar los pasajeros.En adelante, se procesa el archivo CSV
            df = pd.read_csv(filename, encoding='utf-8', sep=';')
            df = df.drop(columns=['Id. de Viaje']) # Elimino columna innecesaria
            df = df.drop(df[df['IDV2'] == '#N/D'].index) # Elimino filas con IDV2 no válidos
            # Creo un diccionario con los nombres de las columnas a cambiar
            column_map = {'Nombre': 'tx_name',
                        'Apellido': 'tx_surname',
                        'Tipo de Identificación': 'tx_identification_type',
                        'Nro. de Identificación': 'nu_identification',
                        'Fecha de Nacimiento': 'dt_birth',
                        'Email': 'tx_email',
                        'Teléfono': 'nu_phone_number1',
                        'Teléfono emergencias': 'nu_phone_number2',
                        'Calle': 'tx_street',
                        'Número': 'nu_street',
                        'Cod. Postal': 'nu_zip',
                        'Ciudad': 'tx_city',
                        'Provincia/Estado': 'tx_province',
                        'País': 'tx_country',
                        'IDV2': 'id_campaign',
                        'IDC2':'id_cabin',
                        'Cabina Asignada':'cabtodel'}
            df.rename(columns=column_map, inplace=True) # aplico cambios de nombres de columnas
            # Convierte los correos a minúsculas
            df['tx_email'] = df['tx_email'].str.lower()
            # Convierto la columna de fecha a formato datetime
            df['dt_birth'] = pd.to_datetime(df['dt_birth'], format='%d/%m/%Y', errors='coerce')
            # Aplica formato de letra capital a nombres y apellidos
            df['tx_name'] = df['tx_name'].str.title()
            df['tx_surname'] = df['tx_surname'].str.title()
            # Elimino filas con fechas no válidas
            df = df.dropna(subset=['dt_birth'])
            # Cambio tipo de dato
            df['cabtodel'] = df['cabtodel'].astype(int)
            # Creo la psw de cada pasajero
            df['str_cabin'] = df['cabtodel'].astype(str)
            df['clean_nid'] = df['nu_identification'].astype(str).str.replace(r'[^A-Za-z0-9]+', '', regex=True)
            cun = '@'
            df['tx_password'] = df['str_cabin'] + cun + df['clean_nid']
            to_move = 'tx_password'
            nval = df.pop(to_move)
            df.insert(6, to_move, nval)
            df = df.drop(columns=['str_cabin', 'clean_nid', 'cabtodel'])
            # Inserto los datos en la tabla bt_passenger
            db = get_db()
            df.to_sql('bt_passenger', db, if_exists='append', index=False)
            # Ejecuto la consulta de ocupación
            db.execute(query_occ).fetchall()
            db.commit()
            flash('Archivo subido y procesado correctamente.')
        else:
            flash('Por favor, suba un archivo CSV válido.')
    else:
        flash('Método no permitido. Por favor, revisar manera para enviar el archivo.')
    return redirect(url_for("auth.redirectlink"))


# Genero info de trips para deshabilitarla
@bp.route("/passengers/enabled_trips", methods=["GET", "POST"])
@login_required
def enabled_trips():
    db = get_db()
    query_tripsx = f"""
        SELECT
            c.id_campaign,
            c.id_trip ||' - '|| r.tx_route AS itinerary,
            dt_from,
            dt_to
        FROM lkp_campaign c INNER JOIN lkp_routes r
        ON c.id_route = r.id_route
        AND c.flag_vigency = 1
        ORDER BY c.dt_from;
        """
    entrips = db.execute(query_tripsx).fetchall()
    return render_template("passengers/disable_trip.html", entrips = entrips)


# Deshabilito trip
@bp.route("/passengers/disable_trip", methods=["GET", "POST"])
@login_required
def disable_trip():
    if request.method == "POST":
        trip_id = request.form["id_trp"]
        db = get_db()
        verdeb = f"""
            SELECT
                COUNT(DISTINCT c.id_passenger) AS upp
            FROM bt_consumption c INNER JOIN bt_passenger p
            ON c.id_passenger = p.id_passenger
            INNER JOIN bt_cabin_occupation o
            ON p.id_passenger = o.id_passenger
            INNER JOIN lkp_campaign g
            ON o.id_campaign = g.id_campaign
            WHERE c.flag_payment = 0
            AND c.flag_anullment = 0
            AND g.id_campaign = (?);
            """
        qdebts = db.execute(verdeb, (trip_id,)).fetchone()
        # Obtengo el valor de upp - unpaid passengers
        debt_count = qdebts['upp']
        # Verifico si hay pasajeros con deudas pendientes
        if debt_count > 0:
            # Si hay deudas, muestro mensaje con el número de deudores
            flash(f'No se puede deshabilitar el recorrido. Aún existen {debt_count} deudas pendientes de pago.')
        else:
            # Si no hay deudas, actualizo la vigencia del viaje
            db.execute("UPDATE lkp_campaign SET flag_vigency = 0 WHERE id_campaign = ?", (trip_id,))
            db.commit()
            flash('Recorrido deshabilitado. Ya no podrá afectar a los pasajeros del mismo.')
    else:
        # Mensaje por default si la solicitud no es POST
        flash('Recorrido no deshabilitado. Por favor, revisar el recorrido.')
    return redirect(url_for("auth.redirectlink"))


# Genero Listado de pasajeros
@bp.route("/passengers/psg_list", methods=["GET", "POST"])
@login_required
def psg_list():
    db = get_db()
    rec_iti = """
            SELECT
                c.id_campaign,
                c.id_trip ||' - '|| r.tx_route AS tx_iti
            FROM lkp_campaign c INNER JOIN lkp_routes r
            ON c.id_route = r.id_route
            ORDER BY 1;
            """
    ique = db.execute(rec_iti).fetchall()
    if not ique:
        flash('Aún no recorridos cargados para este período.')
        return redirect(url_for("auth.redirectlink"))
    else:
        return render_template("passengers/psg_list.html", ique = ique)


query_ptrip = """
        SELECT
            p.tx_name||' '||p.tx_surname AS tx_name,
            p.tx_identification_type,
            p.nu_identification,
            LOWER(p.tx_email) AS email,
            a.nu_cabin,
            a.tx_cabin_type,
            p.id_campaign
        FROM bt_passenger p INNER JOIN lkp_campaign c
        ON p.id_campaign = c.id_campaign
        INNER JOIN lkp_routes r
        ON c.id_route = r.id_route
        INNER JOIN lkp_cabins a
        ON p.id_cabin = a.id_cabin
        WHERE p.id_campaign = (?)
        ORDER BY 1"""



# Obtengo los pasajeros del trip seleccionado
@bp.route("/passengers/get_passenger_htmx", methods=["GET"])
@login_required
def get_passenger_htmx():
    db = get_db()
    id_camp = request.args.get('id_campaign')
    # Mensaje que se muestra antes de seleccionar un pasajero
    if not id_camp:
        return "<p>Seleccionar itinerario para visualizar pasajero.</p>"
    get_list = db.execute(query_ptrip, (id_camp,)).fetchall()
    return render_template("passengers/_cons_psg_list.html", get_list = get_list)




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

# Mapeo de IDs de categorías a sus nombres
category_names = {
    '1': 'Bar & Drinks',
    '10': 'Clothes',
    '11': 'Books',
    '13': 'Ushuaia Ship Products',
    '14': 'Ushuaia Ship Products'
}

# Listado General de Precios de Productos y Servicios
@bp.route("/lista-precios")
def general_lp():
    db = get_db()
    # Función auxiliar para limpiar y obtener IDs
    def get_cleaned_ids(param_name):
        param_values = request.args.getlist(param_name)  
        cleaned_ids = set()
        for param_value in param_values:
            if param_value:
                cleaned = param_value.strip().replace('[', '').replace(']', '')
                ids_from_string = (id_str.strip() for id_str in cleaned.split(',') if id_str.strip())
                cleaned_ids.update(ids_from_string)
                
        return list(cleaned_ids)
    
    ids_list = []
    where_clause_column = ''
    name_map = {}
    # Subcategorías (ids)
    ids_list = get_cleaned_ids('ids')
    if ids_list:
        where_clause_column = 'a.id_subcategory'
        name_map = subcategory_names
    else:
        # Categorías (idc)
        ids_list = get_cleaned_ids('idc')
        if ids_list:
            where_clause_column = 'a.id_category'
            name_map = category_names
        else:
            # TODAS LAS CATEGORÍAS
            ids_list = list(category_names.keys()) 
            where_clause_column = 'a.id_category'
            name_map = category_names

    consolidated_ids = {}
    for id in ids_list:
        # Obtengo el nombre del grupo según el mapeo actual (category_names o subcategory_names)
        group_name = name_map.get(id, f"ID {id} (Nombre Desconocido)")
        # Agrupo los IDs bajo el mismo nombre (ej. '13' y '14' bajo 'Ushuaia Ship Products')
        if group_name not in consolidated_ids:
            consolidated_ids[group_name] = []
        consolidated_ids[group_name].append(id)


    grouped_lists = []
    # Itera sobre cada ID y genera la lista
    for group_name, ids_to_query in consolidated_ids.items():
        # Construyo la cláusula WHERE única para todos los IDs de este grupo
        id_list_str = ', '.join(f"'{id}'" for id in ids_to_query)
        where_clause = f"{where_clause_column} IN ({id_list_str})"
        # Lógica de Categorías y Casos Especiales
        if where_clause_column == 'a.id_category':
            # Exclusión global de servicios
            exclude_clause = "a.id_subcategory NOT IN ('93', '97')"
            # Caso especial para 'Bar & Drinks' (id_category = 1)
            if '1' in ids_to_query:
                # Incluyo 'Tragos' (id_subcategory = 1000)
                where_clause = f"({where_clause}) OR (a.id_subcategory = 1000)"
            where_clause = f"({where_clause}) AND {exclude_clause}"
        # Ejecuto la consulta final
        query = f'{query_svcprd} WHERE {where_clause} ORDER BY 3;'
        prods = db.execute(query).fetchall()
        # Almaceno el resultado agrupado
        if prods: 
            grouped_lists.append({
                'name': group_name,
                'products': prods
            })
    html = render_template('passengers/price_list_general.html', grouped_lists=grouped_lists)
    return render_pdf(HTML(string=html))