import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, session
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db

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
                    b.id_cabin = o.id_cabin
                    AND b.id_campaign = o.id_campaign
                    )
                WHERE o.id_passenger IS NULL;
                """


# Alta de Pasajeros (direccionador)
@bp.route("/passengers/add_psgr", methods=["GET", "POST"])
@login_required
def add_psgr():
    db = get_db()
    trips = db.execute(query_trips).fetchall()
    cabins = db.execute(query_cabins).fetchall()
    return render_template("passengers/add_psngr.html", trips = trips, cabins = cabins)


# Alta de Pasajeros (procesador)
@bp.route("/passengers/addr_psgr", methods=["GET", "POST"])
@login_required
def addr_psgr():
    if request.method == "POST":
        dtoday = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        name = request.form["napa"]
        sname = request.form["surpa"]
        tid = request.form["typid"]
        nid = request.form["nuid"]
        dborn = request.form["dateb"]
        mail = request.form["maila"]
        tel = request.form["tel1"]
        telop = request.form["tel2"]
        tst = request.form["nast"]
        nst = request.form["nust"]
        # floor = request.form["flst"]
        ct = request.form["city"]
        cz = request.form["czip"]
        prv = request.form["state"]
        cou = request.form["country"]
        trip = request.form["sel_trip"]
        cab = request.form["sel_cab"]
        oper = session.get("user_id")
        db = get_db()
        db.execute("INSERT INTO bt_passenger (tx_name, tx_surname, tx_identification_type, nu_identification, dt_birth, tx_email, nu_phone_number1, nu_phone_number2, tx_street, nu_street, nu_zip, tx_city, tx_province, tx_country, id_cabin, id_campaign) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (name, sname, tid, nid, dborn, mail, tel, telop, tst, nst, cz, ct, prv, cou, cab, trip),
                   )
        db.commit()
        db.execute(query_occ).fetchall()
        db.commit()
    flash('Pasajero correctamente ingresado.')
    return redirect(url_for("auth.redirectlink"))