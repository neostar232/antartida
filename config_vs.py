import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, make_response, session
import csv
import datetime as dt
from io import StringIO, BytesIO
# from werkzeug.exceptions import abort
import pandas as pd
from .auth import login_required
from .db import get_db

bp = Blueprint("config_vs", __name__)


# Listado de Categorías
query_categories = """SELECT * FROM lkp_categories ORDER BY tx_category"""


# Relacion entre Categorías y Subcategorías
query_relacion = """
                SELECT
                    c.id_category,
                    c.tx_category,
                    s.tx_subcategory
                FROM lkp_subcategories s INNER JOIN lkp_categories c
                ON s.id_category = c.id_category
                ORDER BY 1, 2, 3
                """

# Listado de Depósitos
query_wh = """SELECT * FROM lkp_warehouse ORDER BY tx_warehouse"""


# Utilizable para los casos de baja
query_wh2 = """SELECT * FROM lkp_warehouse WHERE flag_ctrl <> 0 AND id_warehouse NOT IN (12, 13, 14, 15) ORDER BY tx_warehouse"""


# Listado de productos vigentes
query_prods_full = """
                SELECT
                    b.id_product,
                    s.tx_subcategory ||' - '|| b.tx_product ||' x '|| u.tx_unity AS desc_product
                FROM bt_product b INNER JOIN lkp_categories c
                ON b.id_category = c.id_category
                INNER JOIN lkp_subcategories s
                ON b.id_subcategory = s.id_subcategory
                INNER JOIN lkp_units u
                ON b.id_unity = u.id_unity
                WHERE 1 = 1
                """
# Solo productos habilitados
query_prods = query_prods_full + " AND b.flag_ctrl = 1 ORDER BY 2"
# Todos los productos, habilitados o no
query_prods_ordered = query_prods_full + " ORDER BY 2"

# Productos del punto de venta
query_prods_sp = """SELECT
                    p.id_product,
                    s.tx_subcategory ||' - '|| b.tx_product ||' x '|| u.tx_unity AS desc_product
                FROM bt_product_prices p INNER JOIN bt_product b
                ON p.id_product = b.id_product
                INNER JOIN lkp_categories c
                ON b.id_category = c.id_category
                INNER JOIN lkp_subcategories s
                ON b.id_subcategory = s.id_subcategory
                INNER JOIN lkp_units u
                ON b.id_unity = u.id_unity
                WHERE p.dt_to = '2100-12-31'
                AND b.flag_ctrl = 1
                ORDER BY 2;
                """

# Enlace a la Guía de Uso (sin utilización)
@bp.route("/tda")
@login_required
def tda():
    return render_template("config_vs/user_guides.html")


@bp.route("/add_subcategory")
@login_required
def listcates():
    """ Listado de categorias para subcategorias """
    db = get_db()
    cates = db.execute(query_categories).fetchall()
    return render_template("config_vs/add_subcategory.html", cates = cates)


# Alta de Unidad de Medida
@bp.route("/add_unity", methods=["GET", "POST"])
@login_required
def add_unity():
    if request.method == "POST":
        uni = request.form["tx_uni"]
        error = None
        if not uni:
            error = "La unidad de medida es dato obligatorio"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("INSERT INTO lkp_units (tx_unity) VALUES (?)",
                       (uni,),
                       )
            db.commit()
            return redirect(url_for("auth.redirectlink"))
    return render_template("config_vs/add_unity.html")


# Alta de Categoría
@bp.route("/add_category", methods=["GET", "POST"])
@login_required
def add_category():
    if request.method == "POST":
        cate = request.form["tx_cate"]
        error = None
        if not cate:
            error = "La categoría es dato obligatorio"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("INSERT INTO lkp_categories (tx_category) VALUES (?)",
                       (cate,),
                       )
            db.commit()
            flash('La categoría fue creada exitosamente')
            return redirect(url_for("auth.redirectlink"))
    return render_template("config_vs/add_category.html")


# Alta de subategoría
@bp.route("/add_subcategory", methods=["GET", "POST"])
@login_required
def add_subcategory():
    if request.method == "POST":
        scate = request.form["tx_scate"]
        idcate = request.form["id_cate"]
        error = None
        if not scate:
            error = "La categoría es dato obligatorio"
        if not idcate:
            error = "Debe seleccionarse categoría"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("INSERT INTO lkp_subcategories (tx_subcategory, id_category) VALUES (?,?)",
                       (scate, idcate),
                       )
            db.commit()
            flash('La subcategoría fue creada exitosamente')
            return redirect(url_for("auth.redirectlink"))
    return render_template("config_vs/add_subcategory.html")


# Alta de Almacén
@bp.route("/add_wh", methods=["GET", "POST"])
@login_required
def add_wh():
    if request.method == "POST":
        nwh = request.form["tx_wh"]
        descrip = request.form["desc_wh"]
        error = None
        if not nwh:
            error = "El nombre del depósito es dato obligatorio"
        if not descrip:
            error = "La descripción/ubicacion es obligatoria"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("INSERT INTO lkp_warehouse (tx_warehouse, desc_warehouse) VALUES (?,?)",
                       (nwh, descrip),
                       )
            db.commit()
            return redirect(url_for("auth.redirectlink"))
    return render_template("config_vs/add_wh.html")


@bp.route("/del_wh")
@login_required
def listwarehouses():
    """ Listado de depositos """
    db = get_db()
    whs = db.execute(query_wh2).fetchall()
    return render_template("config_vs/del_wh.html", whs = whs)


# Inhabilitación de depósito (baja lógica)
@bp.route("/del_wh", methods=["GET", "POST"])
@login_required
def del_wh():
    if request.method == "POST":
        idwh = request.form["id_wh"]
        error = None
        if not idwh:
            error = "El nombre del depósito es dato obligatorio"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("UPDATE lkp_warehouse SET flag_ctrl = 0 WHERE id_warehouse = ?", [idwh])
            db.commit()
            flash('El depósito ya no podrá recibir movimientos.')
            return redirect(url_for("auth.redirectlink"))
    return render_template("config_vs/del_wh.html")


# Modificación de depósito
@bp.route("/mod_wh")
@login_required
def listmwarehouses():
    """ Listado de depositos """
    db = get_db()
    whs = db.execute(query_wh2).fetchall()
    return render_template("config_vs/mod_wh.html", whs = whs)


# Modificación de depósito
@bp.route("/mod_wh", methods=["GET", "POST"])
@login_required
def mod_wh():
    if request.method == "POST":
        idmwh = request.form["id_mwh"]
        tmwh = request.form["tx_mwh"]
        descmwh = request.form["desc_mwh"]
        rhmwh = request.form["r_mwh"]
        error = None
        if not idmwh:
            error = "Debe seleccionar un depósito para modificar"
        if not tmwh:
            error = "El nombre del depósito es dato obligatorio"
        if not descmwh:
            error = "Debe ingresar una descripción"
        if not rhmwh:
            error = "Debe indicarse si el depósito se va a habilitar o no"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("UPDATE lkp_warehouse SET tx_warehouse = ?, desc_warehouse = ?, flag_ctrl = ? WHERE id_warehouse = ?",
                       (tmwh, descmwh, rhmwh, idmwh)
                      )
            db.commit()
            flash('El depósito fue modificado')
            return redirect(url_for("auth.redirectlink"))
    return render_template("config_vs/mod_wh.html")


# Funciones de exportacion
@bp.route("/export_relcs")
@login_required
def export_relcs():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        db = get_db()
        list = pd.read_sql_query(query_relacion, db)
        # result = pd.DataFrame(list)
        pd.DataFrame(list).to_excel(writer, sheet_name='Relacion Cat+Subcat', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=relacion_categoria-sub.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response


# Muestro los productos en la página correspondiente
@bp.route("/add_price")
@login_required
def lcr():
    db = get_db()
    prods = db.execute(query_prods).fetchall()
    return render_template("config_vs/add_price.html", prods = prods)


# Entrada masiva de productos (recepcion de remito del proveedor)
@bp.route("/add_price", methods=["GET", "POST"])
@login_required
def add_price():
    if request.method == "POST":
        dtoday = dt.date.today()
        idpr = request.form["id_aprp"]
        prpe = request.form["nu_pe"]
        # prusdo = float(currency_rate_off.replace("$", ""))
        # prusdb = float(currency_rate_blue.replace("$", ""))
        oper = session.get("user_id")
        error = None
        if not idpr:
            error = "Debe seleccionar el producto"
        if not prpe:
            error = "Debe ingresar el precio"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("UPDATE bt_prices SET dt_to = ? WHERE id_product = ? AND dt_to = '2100-12-31'",
                       (dtoday, idpr)
                      )
            db.execute("INSERT INTO bt_prices (id_product, num_pesos, dt_from, id_user) VALUES (?,?,?,?)",
                        (idpr, prpe, dtoday, oper),
                        )
            db.commit()
            flash('El precio fue actualizado correctamente')
            return redirect(url_for("auth.redirectlink"))      
    return render_template("config_vs/add_price.html")


# Busco los productos del punto de venta
@bp.route("/sp_sel_prod")
@login_required
def sp_select():
    db = get_db()
    prods_sp = db.execute(query_prods_sp).fetchall()
    return render_template("config_vs/sp_sel_prod.html", prods_sp = prods_sp)

# Ejecuto la actualización de los precios de Venta
@bp.route("/sp_sel_prod", methods=["GET", "POST"])
@login_required
def add_price_sp():
    if request.method == "POST":
        dtoday = dt.date.today()
        idpr = request.form["id_aprp"]
        prusd = request.form["nu_usd_price"]
        oper = session.get("user_id")
        error = None
        if not idpr:
            error = "Debe seleccionar el producto"
        if not prusd:
            error = "Debe ingresar el precio"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("UPDATE bt_product_prices SET dt_to = ? WHERE id_product = ? AND dt_to = '2100-12-31'",
                       (dtoday, idpr)
                      )
            db.execute("INSERT INTO bt_product_prices (id_product, nu_price_usd, dt_from, id_user) VALUES (?,?,?,?)",
                        (idpr, prusd, dtoday, oper),
                        )
            db.commit()
            flash('El precio fue actualizado correctamente')
            return redirect(url_for("auth.redirectlink"))      
    return render_template("config_vs/sp_sel_prod.html")