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
                COALESCE(p.q_stock, 0) AS existencias,
                CASE
                    WHEN b.num_reorder_point >= COALESCE(p.q_stock, 0) THEN 'Solicitar'
                    ELSE 'OK'
                END AS control_stock
            FROM bt_product b INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            INNER JOIN (
                SELECT
                    id_product,
                    dt_io,
                    q_stock,
                    RANK() OVER (PARTITION BY id_product ORDER BY id_io DESC) AS stock_det
                FROM {}
                WHERE q_stock > 0
                AND id_warehouse {}
            ) p
            ON b.id_product = p.id_product
            WHERE b.flag_ctrl = 1
            AND p.stock_det = 1
            --GROUP BY 1, 2, 3, 4, 5
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
                IFNULL(SUM(CASE WHEN p.id_warehouse = 15 THEN p.q_inn END), 0) AS w15,
                IFNULL(SUM(CASE WHEN p.id_warehouse = 16 THEN p.q_inn END), 0) AS w16
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
                m.id_product AS cod_producto,
                s.tx_subcategory ||': '|| b.tx_product ||' (' || u.tx_unity ||')' AS producto,
                m.oc,
                m.q_solicitada,
                m.q_recibida,
                m.dife,
                m.x_repo
            FROM
            (
            SELECT
                id_product,
                id_order AS oc,
                q_in AS q_solicitada,
                q_real AS q_recibida,
                q_real - q_in AS dife,
                0 AS x_repo    
            FROM bt_in_out_prods
            WHERE fl_sok = 0

            UNION

            SELECT
                id_product,
                id_order AS oc,
                0 AS q_solicitada,
                0 AS q_recibida,
                0 AS dife,
                q_in AS x_repo
            FROM bt_in_out_prods
            WHERE cuit_supplier LIKE '9999%'
            ) m
            INNER JOIN bt_product b
            ON m.id_product = b.id_product
            INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            ORDER BY m.oc DESC
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


# Listado de productos
@bp.route("/prodlist")
@login_required
def prodlist():
    db = get_db()
    prods = db.execute(query_lp).fetchall()
    return render_template("reports/prodlist.html", prods = prods)


# Listado de productos en Stock
@bp.route("/prodstock", methods=["GET", "POST"])
@login_required
def prodstock():
    id_wh = request.args.get('id_wh', type=int)
    if id_wh == 1:
        ttr = 'bt_stock'
        wh_filter = '<= 11'
        template_name = "reports/prodstock.html"
    else:
        ttr = 'bt_stock_bar'
        wh_filter = '<> 16'
        template_name = "reports/prodstock_bar.html"
    query = query_ls.format(ttr, wh_filter)
    db = get_db()
    prstock = db.execute(query).fetchall()
    return render_template(template_name, prstock = prstock)


# Listado de productos a reponer
@bp.route("/prodstockr")
@login_required
def prodstockr():
    ttr = 'bt_stock'
    wh_filter = '<= 11'
    query = query_lsr.format(ttr, wh_filter)
    db = get_db()
    prstock_rep = db.execute(query).fetchall()
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


# Listado de productos del punto de venta
query_prods_sp = """
                SELECT
                    p.id_product,
                    s.tx_subcategory ||' - '|| b.tx_product ||' x '|| u.tx_unity AS desc_product,
                    p.nu_price_usd
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
                
                UNION

                SELECT
                    p.id_product,
                    'Tragos'||' - '|| d.tx_drink AS desc_product,
                    p.nu_price_usd
                FROM bt_product_prices p INNER JOIN lkp_drinks d
                ON p.id_product = d.id_drink
                WHERE p.dt_to = '2100-12-31'
                AND p.flag_price = 1
                AND p.nu_price_usd > 0
                ORDER BY 2;
                """

# Lista de precios
query_plist = """
            SELECT
                p.id_product,
                s.tx_subcategory||' - '|| p.tx_product ||' ('||u.tx_unity||')' AS producto,
                pp.nu_price_usd
            FROM bt_product_prices pp LEFT JOIN bt_product p
            ON pp.id_product = p.id_product
            LEFT JOIN lkp_subcategories s
            ON p.id_subcategory = s.id_subcategory
            LEFT JOIN lkp_units u
            ON p.id_unity = u.id_unity
            WHERE DATE(pp.dt_to) > CURRENT_DATE
            AND pp.flag_price = 1
            ORDER BY 2;
            """

# Listado de ventas por viaje (abierto)
query_sales_actual = """
            SELECT
                id_passenger,
                nu_cabin,
                tx_name||', '||tx_surname AS nm_psgr,
                flag_anullment,
                tx_anullment,
                SUM(nu_totbuys) AS total
            FROM
            (
            SELECT
                lc.nu_cabin,
                ps.id_passenger,
                ps.tx_name,
                ps.tx_surname,
                bc.nu_quantity * bc.pc_unity AS nu_totbuys,
                bc.flag_anullment,
                bc.tx_anullment
            FROM bt_passenger ps INNER JOIN bt_cabin_occupation co
            ON (
                ps.id_passenger = co.id_passenger
                AND ps.id_cabin = co.id_cabin
                AND ps.id_campaign = co.id_campaign
                )
            INNER JOIN lkp_cabins lc
            ON co.id_cabin = lc.id_cabin
            INNER JOIN bt_consumption bc
            ON ps.id_passenger = bc.id_passenger
            INNER JOIN lkp_campaign lm
            ON ps.id_campaign = lm.id_campaign
            WHERE lm.flag_vigency = 1
            ) a
            WHERE a.flag_anullment = ?
            GROUP BY 1, 2, 3, 4, 5
            """

query_coll = """
            SELECT
                c.id_passenger,
                s.id_campaign,
                m.id_trip,
                '('||b.nu_cabin||') '||s.tx_name||', '||s.tx_surname AS nya,
                COUNT(c.id_ticket) AS q_ticket,
                STRFTIME('%Y-%m-%d %H:%M', t.dt_payment) AS dt_payment,
                p.tx_pay_method,
                SUM(c.nu_quantity * c.pc_unity) AS total
            FROM bt_consumption c INNER JOIN bt_ticket_header t
            ON c.id_ticket = t.id_ticket
            INNER JOIN lkp_pay_methods p
            ON t.id_pay_method = p.id_pay_method
            INNER JOIN bt_passenger s
            ON s.id_passenger = t.id_passenger
            INNER JOIN lkp_campaign m
            ON m.id_campaign = s.id_campaign
            INNER JOIN lkp_cabins b
            ON s.id_cabin = b.id_cabin
            WHERE c.flag_anullment = 0
            AND c.flag_payment = 1
            -- AND c.id_passenger = (?)
            AND m.flag_vigency = 1
            GROUP BY 1, 2, 3, 4, 6, 7
            ORDER BY 4, 6
            """

query_collp = """
            SELECT
                m.id_trip,
                '('||b.nu_cabin||') '||s.tx_name||', '||s.tx_surname AS nya,
                COUNT(c.id_ticket) AS q_ticket,
                SUM(c.nu_quantity * c.pc_unity) AS total
            FROM bt_consumption c INNER JOIN bt_ticket_header t
            ON c.id_ticket = t.id_ticket
            INNER JOIN bt_passenger s
            ON s.id_passenger = t.id_passenger
            INNER JOIN lkp_campaign m
            ON m.id_campaign = s.id_campaign
            INNER JOIN lkp_cabins b
            ON s.id_cabin = b.id_cabin
            WHERE c.flag_anullment = 0
            AND c.flag_payment = 0
            AND m.flag_vigency = 1
            GROUP BY 1, 2
            ORDER BY 2;
            """


# Productos del punto de venta
@bp.route("/prods_sp")
@login_required
def prods_sp():
    db = get_db()
    prpv = db.execute(query_prods_sp).fetchall()    
    return render_template("reports/prods_sp.html", prpv = prpv)
    

# Genera el reporte de ventas del actual trip
@bp.route("/sales_actual")
@login_required
def sales_actual():
    db = get_db()
    ind_anul = 0
    acsales = db.execute(query_sales_actual, (ind_anul,)).fetchall()
    total_sales_act = sum(item['total'] for item in acsales) if acsales else 0
    return render_template("reports/sales_actual.html", acsales = acsales, total_sales_act = total_sales_act)


# Genera el reporte de ventas canceladas del actual trip
@bp.route("/sales_actual_cancel")
@login_required
def sales_actual_cancel():
    db = get_db()
    ind_anul = 1
    acsales = db.execute(query_sales_actual, (ind_anul,)).fetchall()
    total_sales_act = sum(item['total'] for item in acsales) if acsales else 0
    return render_template("reports/sales_actual_cancel.html", acsales = acsales, total_sales_act = total_sales_act)


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


@bp.route("/export_lc", methods=["GET", "POST"])
@login_required
def export_lc():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        id_wh = request.args.get('id_wh', type=int)
        if id_wh == 1:
            ttr = 'bt_stock'
            wh_filter = '<= 11'
            filename = 'listado_de_control.xlsx'
        else:
            ttr = 'bt_stock_bar'
            wh_filter = '<> 16'
            filename = 'listado_de_control_bar.xlsx'
        query = query_ls.format(ttr, wh_filter)
        db = get_db()
        list = pd.read_sql_query(query, db)
        pd.DataFrame(list).to_excel(writer, sheet_name='Listado de Control', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response



@bp.route("/export_pr")
@login_required
def export_pr():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        ttr = 'bt_stock' # tabla a consultar
        wh_filter = '<= 11' # almacenes involucrados
        query = query_lsr.format(ttr, wh_filter)
        db = get_db()
        # list = pd.read_sql_query(query_lsr, db) (ex ejecución)
        list = pd.read_sql_query(query, db)
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
        qparam = query_cons + ' AND DATE(p.dt_io) BETWEEN (?) AND (?) GROUP BY 1, 2 ORDER BY 2, 1'
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


# Exporto los productos del punto de venta
@bp.route("/export_list_sp")
@login_required
def export_list_sp():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        db = get_db()
        list = pd.read_sql_query(query_prods_sp, db)
        # result = pd.DataFrame(list)
        pd.DataFrame(list).to_excel(writer, sheet_name='Precios Punto de Venta', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=precios_punto_de_venta.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response
    

# Listado de cobranzas realizadas
@bp.route("/collections")
@login_required
def collections():
    db = get_db()
    coll = db.execute(query_coll).fetchall()
    total_clt = sum(item['total'] for item in coll) if coll else 0
    if len(coll) < 1:
        flash('Aún no se realizaron cobranzas en este viaje.')
        return redirect(url_for("auth.redirectlink"))
    return render_template("reports/collections.html", coll = coll, total_clt = total_clt)


# Listado de cobranzas pendientes
@bp.route("/collectionsp")
@login_required
def collectionsp():
    db = get_db()
    collp = db.execute(query_collp).fetchall()
    if len(collp) < 1:
        flash('Aún no se registraron ventas en este viaje.')
        return redirect(url_for("auth.redirectlink"))
    return render_template("reports/collectionsp.html", collp = collp)