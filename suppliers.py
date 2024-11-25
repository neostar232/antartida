import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
# from werkzeug.exceptions import abort

from .auth import login_required
from .db import get_db

bp = Blueprint("suppliers", __name__)

@bp.route("/add_supp", methods=["GET", "POST"])
@login_required
def add_supp():
    # Alta de proveedor
    if request.method == "POST":
        supp = request.form["tx_supp"]
        cuit = request.form["nu_cuit"]
        tax = request.form["sit_imp"]
        calle = request.form["calle"]
        nro = request.form["nro"]
        loca = request.form["localidad"]
        cp = request.form["cp"]
        pvcia = request.form["tx_province"]
        error = None

        if not supp:
            error = "El nombre del Proveedor es dato obligatorio"
        elif not cuit:
            error = "CUIT es dato obligatorio"
        elif not tax:
            error = "La Situación Impositiva es obligatoria"
        elif not calle:
            error = "La Calle es obligatoria"
        elif not nro:
            error = "El nro del domicilio es obligatorio"
        elif not loca:
            error = "La Localidad es obligatoria"
        elif not cp:
            error = "El CP es obligatorio"
        elif not pvcia:
            error = "La Provincia es obligatoria"

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                "INSERT INTO bt_suppliers (num_cuit_supplier, tx_name_supplier, tx_add_street_sp, "
                "tx_add_num_sp, tx_add_location_sp, tx_add_zip_sp, id_province, id_tax_inscript) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (cuit, supp, calle, nro, loca, cp, pvcia, tax),
            )
            db.commit()
            return redirect(url_for("auth.redirectlink"))

    return render_template("suppliers/add_supp.html")
