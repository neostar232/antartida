# import functools
# import os
from flask import Blueprint, g, render_template, make_response, flash, request, url_for, redirect
from werkzeug.exceptions import abort
import csv
from io import StringIO, BytesIO
import pandas as pd
from .auth import login_required
from .db import get_db

bp = Blueprint("reports", __name__, url_prefix="/reports")

# Genero consultas varias, luego utilizables en las funciones
# Listado de productos
query_lp = """
            SELECT
                b.id_product AS cod_producto,
                s.tx_subcategory AS subcategoria,
                b.tx_product AS desc_producto,
                c.tx_category AS categoria,
                u.tx_unity AS presentacion,
                b.num_reorder_point AS punto_repedido
            FROM bt_product b INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            WHERE b.flag_ctrl = 1
            ORDER BY 2, 4, 3, 1
            """

# Listado de stock
query_ls = """
            SELECT
                b.id_product AS cod_producto,
                s.tx_subcategory AS subcategoria,    
                b.tx_product AS desc_producto,
                -- c.tx_category AS categoria,
                u.tx_unity AS presentacion,  
                b.num_reorder_point AS punto_repedido,
                SUM(p.q_batch_balance) AS existencias,
                CASE
                    WHEN b.num_reorder_point >= SUM(p.q_batch_balance) THEN 'Solicitar'
                    ELSE 'OK'
                END AS control_stock
            FROM bt_product b INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            INNER JOIN bt_stock p
            ON b.id_product = p.id_product
            WHERE b.flag_ctrl = 1
            AND p.id_warehouse <= 11
            GROUP BY 1, 2, 3, 4, 5
            ORDER BY 2, 3, 4, 1
            """

# Listado de stock en el punto de repedido o debajo
query_lsr = "SELECT * FROM ( " + query_ls + " ) a WHERE control_stock = 'Solicitar'"


# Consumos
query_cons = """
            SELECT
                b.id_product AS cod_producto,
                s.tx_subcategory ||': '|| b.tx_product ||' (' || u.tx_unity ||')' AS producto,
                IFNULL(SUM(CASE WHEN p.id_warehouse = 12 THEN p.q_inn END), 0) AS w12,
                IFNULL(SUM(CASE WHEN p.id_warehouse = 13 THEN p.q_inn END), 0) AS w13,
                IFNULL(SUM(CASE WHEN p.id_warehouse = 14 THEN p.q_inn END), 0) AS w14,
                IFNULL(SUM(CASE WHEN p.id_warehouse = 15 THEN p.q_inn END), 0) AS w15 
            FROM bt_product b INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            INNER JOIN bt_stock p
            ON b.id_product = p.id_product
            INNER JOIN lkp_warehouse w
            ON p.id_warehouse = w.id_warehouse
            WHERE b.flag_ctrl = 1
            AND p.id_warehouse > 11
            AND p.q_inn > 0 
            """


# Productos con diferencia entre lo solicitado y lo recibido
query_outorder = """
            SELECT
                b.id_product AS cod_producto,
                s.tx_subcategory ||': '|| b.tx_product ||' (' || u.tx_unity ||')' AS producto,
                p.id_order AS oc,
                CASE
                    WHEN cuit_supplier <> 99999999999 THEN p.q_in
                    ELSE 0
                END AS q_solicitada,
                IFNULL(CASE
                    WHEN cuit_supplier <> 99999999999 AND LENGTH(p.q_real) = 0 THEN 0
                    WHEN cuit_supplier = 99999999999 AND p.q_real = 0 THEN p.q_in
                    ELSE p.q_real
                END, 0) AS q_recibida,
                CASE
                    WHEN cuit_supplier <> 99999999999 THEN p.q_real - p.q_in
                    ELSE 0
                END AS dife,
                CASE
                    WHEN cuit_supplier = 99999999999 THEN p.q_in
                    ELSE 0
                END AS x_repo
            FROM bt_product b INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            INNER JOIN bt_in_out_prods p
            ON b.id_product = p.id_product
            LEFT JOIN lkp_warehouse w
            ON p.id_warehouse = w.id_warehouse
            WHERE b.flag_ctrl = 1
            AND p.fl_sok = 0
            OR LENGTH(p.fl_sok) = 0
            OR p.cuit_supplier = 99999999999
            ORDER BY oc DESC;
            """


query_po = """
            SELECT
                id_prod AS id_producto,
                tx_prod AS producto,
                id_category,
                q_exist AS existencias,
                nuq
            FROM temp_order
            WHERE nuq > 0
            ORDER BY tx_prod;
            """


# Listado de productos con intento fallido de transferencia
query_transfail = """
            SELECT
                t.id_io,
                t.dt_io,
                t.id_product,
                s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS producto,
                t.id_warehouse,
                t.q_prodt,
                w.tx_warehouse
            FROM temp_transfer t INNER JOIN bt_product b
            ON t.id_product = b.id_product
            INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            INNER JOIN lkp_warehouse w
            ON t.id_warehouse = w.id_warehouse
            WHERE t.q_prodt > t.q_proda
            ORDER BY producto;
            """

@bp.route("/prodlist")
@login_required
def prodlist():
    """ Listado de productos """
    db = get_db()
    prods = db.execute(query_lp).fetchall()
    return render_template("reports/prodlist.html", prods = prods)

@bp.route("/prodstock")
@login_required
def prodstock():
    """ Listado de productos en Stock """
    db = get_db()
    prstock = db.execute(query_ls).fetchall()
    return render_template("reports/prodstock.html", prstock = prstock)

@bp.route("/prodstockr")
@login_required
def prodstockr():
    """ Listado de productos a reponer """
    db = get_db()
    prstock_rep = db.execute(query_lsr).fetchall()
    return render_template("reports/prodstockr.html", prstock_rep = prstock_rep)


# Listado de productos fallidos al transferir
@bp.route("/prodstrf")
@login_required
def prodstrf():
    db = get_db()
    comprob = db.execute('SELECT COUNT(*) AS q FROM temp_transfer WHERE q_prodt > q_proda;').fetchone()[0]
    if comprob >= 1:
        prodsfail = db.execute(query_transfail).fetchall()
        return render_template("reports/prods_transfer.html", prodsfail = prodsfail)
    flash('No se encuentran productos con estas características en este momento.')
    return redirect(url_for("auth.redirectlink"))
    

@bp.route("/panel")
@login_required
def panel():
    return render_template("reports/panel.html")


@bp.route("/panelb")
@login_required
def panelb():
    return render_template("reports/panelb.html")


@bp.route("/list")
@login_required
def list():
    return render_template("reports/list.html")

# Funciones de exportacion de listados
@bp.route("/export_list")
@login_required
def export_list():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        db = get_db()
        list = pd.read_sql_query(query_lp, db)
        # result = pd.DataFrame(list)
        pd.DataFrame(list).to_excel(writer, sheet_name='Listado de Productos', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=listado_de_productos.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response


@bp.route("/export_lc")
@login_required
def export_lc():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        db = get_db()
        list = pd.read_sql_query(query_ls, db)
        # result = pd.DataFrame(list)
        pd.DataFrame(list).to_excel(writer, sheet_name='Listado de Control', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=listado_de_control.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response


@bp.route("/export_pr")
@login_required
def export_pr():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        db = get_db()
        list = pd.read_sql_query(query_lsr, db)
        # result = pd.DataFrame(list)
        pd.DataFrame(list).to_excel(writer, sheet_name='Productos a reponer', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=productos_a_reponer.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response


# Seleccion de fechas desde/hasta para visualizar consumos
@bp.route("/consumption_dates")
@login_required
def consumption_dates():
    return render_template('/reports/consumption_dates.html')


# Muestra los consumos a partir de las fechas definidas
@bp.route("/consumption", methods=["GET", "POST"])
@login_required
def consumption():
    if request.method == "POST":
        datef = request.form["date_from"]
        datet = request.form["date_to"]
        qparam = query_cons + ' AND p.dt_io BETWEEN (?) AND (?) GROUP BY 1, 2 ORDER BY 2, 1'
        db = get_db()
        prd_cons = db.execute(qparam, (datef, datet),).fetchall()
        if len(prd_cons) < 1:
            flash('No hay consumos para la fecha seleccionada. Intente nuevamente modificando el período.')
            return redirect(url_for("auth.redirectlink"))
        return render_template("reports/consumption.html", prd_cons = prd_cons)


# Muestra los productos con diferencia entre lo solicitado y lo recibido
@bp.route("/outoforder")
@login_required
def outoforder():
    db = get_db()
    prd_ooo = db.execute(query_outorder).fetchall()
    if len(prd_ooo) < 1:
        flash('No se encontraron órdenes con diferencias en las cantidades.')
        return redirect(url_for("auth.redirectlink"))
    return render_template("reports/prods_ooo.html", prd_ooo = prd_ooo)


@bp.route("/export_po")
@login_required
def export_po():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        db = get_db()
        list = pd.read_sql_query(query_po, db)
        # result = pd.DataFrame(list)
        pd.DataFrame(list).to_excel(writer, sheet_name='Detalle preorden', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=preorden.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response


# Para eliminar
@bp.route("/export_list_pd")
@login_required
def export_list_pd():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        db = get_db()
        list = pd.read_sql_query(query_lp, db)
        # result = pd.DataFrame(list)
        pd.DataFrame(list).to_excel(writer, sheet_name='Productos', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=reponer.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response