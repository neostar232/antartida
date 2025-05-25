import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, jsonify
# from werkzeug.exceptions import abort
from .auth import login_required
from .db import get_db

bp = Blueprint("bar_sp", __name__)

# Creo las consultas para las listas desplegables
# Cabinas
query_occ_cabins = """
            SELECT DISTINCT
                co.id_cabin,
                cl.tx_cabin_desc
            FROM bt_cabin_occupation co INNER JOIN lkp_cabins cl
            ON co.id_cabin = cl.id_cabin
            ORDER BY 2;
            """

query_occ_pass = """
            SELECT
                co.id_cabin,
                co.id_passenger,
                ps.tx_name||' '||ps.tx_surname AS passenger_name
            FROM bt_cabin_occupation co INNER JOIN bt_passenger ps
            ON co.id_passenger = ps.id_passenger
            WHERE co.id_cabin = ?
            -- completar con la condición de fecha de viaje
            -- ORDER BY 3;
            """


# Ropa
query_subcat_clothes = """
            SELECT
                pp.id_product_price,
                pr.id_product,
                s.tx_subcategory||' '||pr.tx_product AS txt_product,
                pp.nu_price_usd
            FROM bt_product_prices pp INNER JOIN bt_product pr
            ON pp.id_product = pr.id_product
            INNER JOIN lkp_subcategories s
            ON pr.id_subcategory = s.id_subcategory
            WHERE pr.id_category = 10
            AND pr.flag_ctrl = 1
            AND dt_to = '2100-12-31'
            ORDER BY 3;
            """

# Productos de la subcategoría
@bp.route("/bar_sp/scat_clothes")
@login_required
def prods_cl():
    db = get_db()
    prcl = db.execute(query_subcat_clothes).fetchall()
    cabs = db.execute(query_occ_cabins).fetchall()
    # psgs = db.execute(query_occ_pass).fetchall()
    return render_template("bar_sp/scat_clothes.html", prcl = prcl, cabs = cabs) #, psgs = psgs)

@bp.route("/bar_sp/obtener_pasajeros_htmx", methods=["POST"])
@login_required
def obtener_pasajeros_htmx():
    cabin_id = request.form.get("cabin")  # HTMX envía los datos del formulario

    if cabin_id:
        db = get_db()
        psg = db.execute(query_occ_pass, (cabin_id,)).fetchall()
        return render_template("bar_sp/_passenger_options.html", pasajeros=psg)
    return "" # Devuelve una cadena vacía si no hay cabin_id

