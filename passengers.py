import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, session, send_from_directory
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db
import os
import pandas as pd
import re

bp = Blueprint("passengers", __name__)

# Listado de rutas y decripción
query_trips = """
                SELECT
                    c.id_campaign,
                    c.id_trip ||' - '|| r.tx_route AS itinerary
                FROM lkp_campaign c INNER JOIN lkp_routes r
                ON c.id_route = r.id_route
                -- AND c.dt_from >= CURRENT_DATE
                ORDER BY c.dt_from;
                """

# Listado de cabinas y tipos
query_cabins = """
                SELECT
                    id_cabin,
                    nu_cabin||' - '|| tx_cabin_type AS cabin
                FROM lkp_cabins
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
    cabins = db.execute(query_cabins).fetchall()
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
        cab = request.form["sel_cab"]
        # genero el valro que tomará la psw
        nnid = re.sub('[^A-Za-z0-9]+', '', nid)
        scab = str(cab)
        cun = '@'
        valpas = cun.join([scab, nnid])
        db = get_db()
        db.execute("INSERT INTO bt_passenger (tx_name, tx_surname, tx_identification_type, nu_identification, dt_birth, tx_email, tx_password, nu_phone_number1, nu_phone_number2, tx_street, nu_street, nu_zip, tx_city, tx_province, tx_country, id_cabin, id_campaign) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (name, sname, tid, nid, dborn, mail, valpas, tel, telop, tst, nst, cz, ct, prv, cou, cab, trip),
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


# Enlace a la Guía de Uso
@bp.route("/passengers/how_to")
@login_required
def how_to():
    directory = os.path.join('static', 'vs')
    filename = 'Pasajeros_Buque.xlsx'
    return send_from_directory(directory, filename, as_attachment=True)


# Alta de Pasajeros (bulk desde archivo)
@bp.route("/passengers/addr_psngr_ff", methods=["GET", "POST"])
@login_required
def addr_psngr_ff():
    if request.method == "POST":
        file = request.files["file"]
        if file and file.filename.endswith('.csv'):
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../ushuaia"))
            filename = os.path.join(root + '/upl_files/', file.filename)
            file.save(filename)
            # Hasta acá se sube el archivo CSV para agregar los pasajeros.En adelante, se procesa el archivo CSV
            df = pd.read_csv(filename, encoding='utf-8', sep=';')
            df = df.drop(columns=['Id. de Viaje', 'Cabina Asignada']) # Elimino columnas innecesarias
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
                        'IDC2':'id_cabin'}
            df.rename(columns=column_map, inplace=True) # aplico cambios de nombres de columnas
            # Convierto la columna de fecha a formato datetime
            df['dt_birth'] = pd.to_datetime(df['dt_birth'], format='%d/%m/%Y', errors='coerce')
            # Elimino filas con fechas no válidas
            df = df.dropna(subset=['dt_birth'])
            # Creo la psw de cada pasajero
            df['str_cabin'] = df['id_cabin'].astype(str)
            df['clean_nid'] = df['nu_identification'].astype(str).str.replace(r'[^A-Za-z0-9]+', '', regex=True)
            cun = '@'
            df['tx_password'] = df['str_cabin'] + cun + df['clean_nid']
            to_move = 'tx_password'
            nval = df.pop(to_move)
            df.insert(6, to_move, nval)
            df = df.drop(columns=['str_cabin', 'clean_nid'])
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