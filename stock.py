from flask import Blueprint, g, flash, redirect, render_template, url_for, make_response, request, session
from .auth import login_required
from .db import get_db
from io import StringIO, BytesIO
from datetime import datetime
import pytz as tz
import pandas as pd
import numpy as np

bp = Blueprint("stock", __name__)

#Listado de productos vigentes
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

# Listado de existencias
query_exist_base = """
                SELECT
                    b.id_product AS cod_producto,
                    s.tx_subcategory ||': '|| b.tx_product ||' (' || u.tx_unity ||')' AS producto,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 1 THEN p.q_batch_balance END), 0) AS w01,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 2 THEN p.q_batch_balance END), 0) AS w02,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 3 THEN p.q_batch_balance END), 0) AS w03,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 4 THEN p.q_batch_balance END), 0) AS w04,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 5 THEN p.q_batch_balance END), 0) AS w05,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 6 THEN p.q_batch_balance END), 0) AS w06,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 7 THEN p.q_batch_balance END), 0) AS w07,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 8 THEN p.q_batch_balance END), 0) AS w08,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 9 THEN p.q_batch_balance END), 0) AS w09,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 10 THEN p.q_batch_balance END), 0) AS w10,
                    IFNULL(SUM(CASE WHEN p.id_warehouse = 11 THEN p.q_batch_balance END), 0) AS w11
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
                AND p.id_warehouse < 12
                """

# Listado de existencias
query_exist = query_exist_base + "GROUP BY 1, 2 ORDER BY 2, 1"

# Listado de existencias proximas a vencer
query_exist_expiry = query_exist_base + " AND p.dt_expiry <= DATE('NOW','+1 MONTHS') GROUP BY 1, 2 ORDER BY 2, 1"

# Listado de atributos de alta fijos: categorías, subcategorías, unidad de medida
query_cat = """SELECT * FROM lkp_categories ORDER BY tx_category"""

query_scat = """SELECT * FROM lkp_subcategories ORDER BY tx_subcategory"""

query_units = """SELECT * FROM lkp_units ORDER BY tx_unity"""

query_wh = """SELECT * FROM lkp_warehouse WHERE flag_ctrl = 1"""

# Ordenes de compra con posibilidad de ingresar productos
query_sel_oc = """
            SELECT
                h.id_order,
                h.dt_order,
                COUNT(p.id_product) AS Q
            FROM bt_in_out_prods p INNER JOIN bt_order_header h
            ON p.id_order = h.id_order
            WHERE h.fl_close_order = 0
            GROUP BY 1, 2
            ORDER BY 1;
            """

# Productos de la Orden de Compra
query_oc = """
            SELECT
                o.id_movement,
                o.id_order,
                b.id_product,
                s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS producto,
                o.q_in
            FROM bt_in_out_prods o INNER JOIN bt_product b
            ON o.id_product = b.id_product
            INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            INNER JOIN bt_order_header h
            ON o.id_order = h.id_order
            WHERE b.flag_ctrl = 1
            AND h.fl_close_order = 0
            AND o.fl_sok <> 1
            AND o.q_real >= 0
            """

# Productos para transferir entre depositos
query_transf = """
            SELECT
                -- t.id_io,
                t.id_product,
                s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS producto,
                t.id_warehouse,
                w.tx_warehouse,
                -- t.dt_expiry,
                SUM(t.q_batch_balance) AS q_batch_balance
            FROM bt_stock t INNER JOIN bt_product b
            ON t.id_product = b.id_product
            INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            INNER JOIN lkp_warehouse w
            ON t.id_warehouse = w.id_warehouse
            WHERE t.q_batch_balance > 0
            AND t.q_stock > 0
            AND w.id_warehouse < 12
            GROUP BY 1, 2, 3, 4
            ORDER BY producto, t.dt_expiry
            """

# Agrego productos por transferencia
query_add_transf = """
            INSERT INTO bt_stock (dt_io, id_product, id_warehouse, dt_expiry, q_inn)
            SELECT
                -- t.dt_io, -- Modificado 20250103
                DATETIME('NOW') AS dt_io,
                t.id_product,
                t.id_warehouse,
                b.dt_expiry,
                t.q_prodt
            FROM temp_transfer t INNER JOIN bt_stock b
            ON t.id_io = b.id_io
            WHERE t.id_warehouse <> ''
            AND t.q_proda >= t.q_prodt;
            """

# Actualizo el stock (partida por partida)
query_us = """
            SELECT
                id_io,
                id_product,
                id_warehouse,
                q_batch_balance,
                SUM(q_batch_balance)
                    OVER(PARTITION BY id_product, id_warehouse
                    ORDER BY id_io, dt_expiry ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS stock_av
            FROM bt_stock
            WHERE q_batch_balance > 0
            AND id_warehouse <= 12
            AND (q_stock > 0 OR q_stock IS NULL)
            """

# Creo temporal para agregar las confirmaciones de la OC en el stock
query_insocs = """
            CREATE TEMPORARY TABLE ttis (
                dt_io TEXT,
                id_product INTEGER,
                id_warehouse INTEGER,
                dt_expiry TEXT,
                q_inn INTEGER,
                q_inn_real INTEGER,
                fl_ok INTEGER
            );
            """

# Ingreso de productos confirmados de la OC al stock
query_addocst = """
            INSERT INTO bt_stock (dt_io, id_product, id_warehouse, dt_expiry, q_inn, q_batch_balance)
            SELECT
                dt_io, id_product, id_warehouse, dt_expiry,
                CASE
                    WHEN fl_ok = 1 THEN q_inn
                    ELSE q_inn_real
                END AS q_inn,
                CASE
                    WHEN fl_ok = 1 THEN q_inn
                    ELSE q_inn_real
                END AS q_batch_balance
            FROM ttis
            WHERE fl_ok = 1
            OR LENGTH(q_inn_real) > 0;
            """

# Actualizo las salidas de depósitos por transferencias internas
query_upd_out = """
            UPDATE bt_stock
            SET q_out = (IFNULL(q_out, 0) + trf.q_prodt)
            FROM
            (
				SELECT
					q_prodt,
					id_io
				FROM temp_transfer
				WHERE q_proda >= q_prodt
			) AS trf
            WHERE bt_stock.id_io = trf.id_io;
            """

# Query para movimientos entre almacenes
query_movebwh = """
                SELECT
                    id_io,
                    id_product,
                    id_warehouse,
                    q_batch_balance
                FROM bt_stock
                WHERE q_batch_balance > 0
                AND q_stock > 0
                AND id_warehouse < 12
                ORDER BY id_product, id_io
                """

# Query para actualizar el stock de los productos en la tabla bt_products (no en todos los casos)
query_jafc = """
                UPDATE bt_product SET q_stock = a.q_stock
                FROM (
                SELECT
                    s.id_product,
                    s.q_stock,
                    RANK() OVER (PARTITION BY s.id_product ORDER BY s.id_io DESC) AS stock_det
                FROM bt_stock s INNER JOIN ttis t
                ON s.id_product = t.id_product
                WHERE s.id_warehouse <= 11
                ) a
                WHERE a.stock_det = 1
                AND bt_product.id_product = a.id_product;
            """


# Ejecuto los listados de atributos para que se direccionen a las páginas dónde deben utilizarse
@bp.route("/stock/listadd_prods")
@login_required
def listadd_prods():
    db = get_db()
    cates = db.execute(query_cat).fetchall()
    subcates = db.execute(query_scat).fetchall()
    units = db.execute(query_units).fetchall()
    return render_template("stock/add_product.html", cates = cates, subcates = subcates, units = units)


@bp.route("/stock/add_product", methods=["GET", "POST"])
@login_required
def add_product():
    # Alta de producto
    if request.method == "POST":
        nomprod = request.form["tx_prod"]
        idcate = request.form["id_cate"]
        idscate = request.form["id_scate"]
        idunit = request.form["id_unit"]
        prep = request.form["tx_prep"]
        apl = request.form.get("tx_apl")
        dtodayfull = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        oper = session.get("user_id")
        error = None
        if not nomprod:
            error = "La categoría es dato obligatorio"
        if not idcate:
            error = "Debe seleccionarse categoría"
        if not idscate:
            error = "Debe seleccionarse subcategoría"
        if not idunit:
            error = "Debe seleccionarse categoría"
        if not prep:
            error = "El punto de repedido es dato obligatorio"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("INSERT INTO bt_product (tx_product, id_category, id_subcategory, id_unity, num_reorder_point) VALUES (?,?,?,?,?)",
                       (nomprod, idcate, idscate, idunit, prep),
                       )
            db.commit()

            if apl:
                req_prd = db.execute('SELECT MAX(id_product) AS mxm FROM bt_product;').fetchone()[0]
                db.execute("INSERT INTO bt_product_prices (id_product, dt_from, id_user, flag_price) VALUES (?,?,?,?)",
                   (req_prd, dtodayfull, oper, '1'),
                   )
                db.commit()
                flash('El producto ha sido dado de alta exitosamente. El precio actual es 0, recuerde actualizarlo','warning')
                return redirect(url_for("auth.redirectlink"))
            else:
                flash('El producto ha sido dado de alta exitosamente')
                return redirect(url_for("auth.redirectlink"))
    return render_template("stock/add_product.html")


# Completa la lista desplegable de productos para dar de baja
@bp.route("/stock/del_sp")
@login_required
def list_del_single_prod():
    db = get_db()
    prods = db.execute(query_prods).fetchall()
    return render_template("stock/del_single_product.html", prods = prods)


# Realiza la accion de inhabilitación sobre el producto seleccionado
@bp.route("/stock/del_sp", methods=["GET", "POST"])
@login_required
def del_sp():
    # Inhabilitación de productos
    if request.method == "POST":
        iddsp = request.form["id_dsp"]
        error = None
        if not iddsp:
            error = "Debe seleccionarse un producto para inhabilitar"
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute("UPDATE bt_product SET flag_ctrl = 0 WHERE id_product = ?", (iddsp,)).fetchall()
            db.commit()
            return redirect(url_for("auth.redirectlink"))
    return render_template("stock/del_single_product.html")


# Alimenta el cuadro de productos para el deshabilitado masivo
@bp.route("/stock/del_mp")
@login_required
def list_del_multi_prod():
    db = get_db()
    prods = db.execute(query_prods).fetchall()
    return render_template("stock/del_multi_products.html", prods = prods)


# Realiza la accion de inhabilitación sobre los productos seleccionados
@bp.route("/stock/del_mp", methods=["GET", "POST"])
@login_required
def del_mp():
    # Inhabilitación de productos
    if request.method == "POST":
        iddmp = request.form.getlist("id_dmp")
        error = None
        if not iddmp:
            error = "Debe seleccionarse al menos un producto para inhabilitar"
        if error is not None:
            flash(error)
        else:
            for prd in iddmp:
                db = get_db()
                db.execute("UPDATE bt_product SET flag_ctrl = 0 WHERE id_product = (?)", [prd])
                db.commit()
            return redirect(url_for("auth.redirectlink"))
    return render_template("stock/del_multi_products.html")


# Inicialmente no tiene funcionalidad (form_dates.html no existe)
@bp.route("/stock/moves", methods=["GET", "POST"])
@login_required
def moves():
    return render_template("stock/form_dates.html")


# Listado de productos en existencia (link: Disponibilidad)
@bp.route("/stock/exist")
@login_required
def prodsexist():
    db = get_db()
    prd_exist = db.execute(query_exist).fetchall()
    return render_template("stock/exist.html", prd_exist = prd_exist)


# Exportacion de las existencias por almacen
@bp.route("/stock/export_we")
@login_required
def export_we():
    io = BytesIO()
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        db = get_db()
        list = pd.read_sql_query(query_exist, db)
        list.columns= ['Código', 'Producto', 'Cam. Lacteos', 'Cam. Secos', 'Cam. Verduras', 'Cám. Carnes',
                       'Pañol Limpieza', 'Pañol Bebidas', 'Dep. Máquinas', 'Dep. Merchandising', 'Dep. Hospital',
                       'Pañol Elem. Cocina', 'Pañol Comedor']
        pd.DataFrame(list).to_excel(writer, sheet_name='Existencias_por_deposito', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=existencias_por_deposito.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response


# Detalle de los almacenes para seleccionar en el alta masiva
@bp.route("/stock/add_massive")
@login_required
def list_masive_add_prods():
    db = get_db()
    whexc = ' AND id_warehouse < 14 ORDER BY tx_warehouse'
    whs = db.execute(query_wh + whexc ).fetchall()
    prods = db.execute(query_prods).fetchall()
    return render_template("stock/in_multi_products.html", whs = whs, prods = prods)


# Entrada de productos fuera de la OC
@bp.route("/stock/add_massive", methods=["GET", "POST"])
@login_required
def add_massive_product():
    if request.method == "POST":
        dtodayfull = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        dtoday = datetime.now().strftime('%Y-%m-%d') # Modificado 20250103
        iddmp = request.form.getlist("id_dmp")
        idwh = request.form["id_wh"]
        odate = request.form["order_date"]
        ordernum = request.form["order_num"]
        expdate = request.form["expiry_date"]
        qin = request.form["quantity_in"]
        oc = request.form["id_oc"]
        csup = '99999999999'
        flg = 1
        qexit = 0
        oper = session.get("user_id")
        error = None
        if not idwh:
            error = "Debe seleccionar el almacén destino"
        if not odate:
            error = "Debe ingresarse la fecha de remito"
        if not ordernum:
            error = "El nro. de remito es obligatorio"
        if not expdate:
            error = "Debe ingresarse fecha de vencimiento"
        if not qin:
            error = "La cantidad es dato obligatorio"
        if error is not None:
            flash(error)
        else:
            for prd in iddmp:
                db = get_db()
                db.execute("INSERT INTO bt_in_out_prods (dt_movement, cuit_supplier, id_order, dt_num_order, num_order, id_product, dt_expiry, id_warehouse, q_in, fl_sok, id_user) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (dtoday, csup, oc, odate, ordernum, prd, expdate, idwh, qin, flg, oper),
                            )
                # Agrego productos ingresados al stock
                db.execute("INSERT INTO bt_stock (dt_io, id_product, id_warehouse, dt_expiry, q_inn, q_out, q_batch_balance) VALUES (?,?,?,?,?,?,?)",
                           (dtodayfull, prd, idwh, expdate, qin, qexit, qin)
                           )
                # Actualizo las partidas y el stock general en bt_stock
                db.execute("""UPDATE bt_stock SET q_out = 0 WHERE q_out IS NULL""")
                db.execute('UPDATE bt_stock SET q_stock = a.stock_av FROM (' + query_us + ') a WHERE bt_stock.id_io = a.id_io').fetchall()
                # Actualizo la tabla de productos con el stock actualizado y la hora de la actualización
                ptu = """
                    UPDATE bt_product SET q_stock = a.q_stock, dt_last_update = (?)
                    FROM (
                    SELECT
                        id_product,
                        dt_io,
                        q_stock,
                        RANK() OVER (PARTITION BY id_product ORDER BY id_io DESC) AS stock_det
                    FROM bt_stock
                    WHERE id_warehouse <= 11
                    AND id_product = (?)
                    ) a
                    WHERE a.stock_det = 1
                    AND bt_product.id_product = a.id_product;
                    """
                db.execute(ptu, (dtodayfull, prd,)).fetchall()
                # Compruebo si el producto está en la PO y de existir, actualizo el stock que se indica en PO
                sppo = db.execute(f"""SELECT COUNT(*) AS quantity FROM temp_order""").fetchone()[0]
                if sppo > 0:
                    tou = """
                        UPDATE temp_order SET q_exist = a.q_stock
                        FROM (
                        SELECT
                            id_product,
                            dt_io,
                            q_stock,
                            RANK() OVER (PARTITION BY id_product ORDER BY id_io DESC) AS stock_det
                        FROM bt_stock
                        WHERE id_warehouse <= 11
                        AND id_product = (?)
                        ) a
                        WHERE a.stock_det = 1
                        AND temp_order.id_prod = a.id_product;
                        """
                    db.execute(tou, (prd,)).fetchall()
                else:
                    pass
                db.commit()
            flash('Productos ingresados correctamente')
            return redirect(url_for("auth.redirectlink"))
    return render_template("stock/in_multi_products.html")


# Exporto a excel, las existencias a vencer por almacen
@bp.route("/stock/export_wee")
@login_required
def export_wee():
    io = BytesIO()
    with pd.ExcelWriter(io, engine='openpyxl') as writer:
        db = get_db()
        list = pd.read_sql_query(query_exist_expiry, db)
        pd.DataFrame(list).to_excel(writer, sheet_name='Existencias a vencer', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=Existencias_a_vencer_por_deposito.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response


# Muestra las OC con posibilidad de ingresar los productos
@bp.route("/stock/select_oc")
@login_required
def select_oc():
    db = get_db()
    ocd = db.execute(query_sel_oc).fetchall()
    if len(ocd) < 1:
        flash('No hay órdenes de compra en las cuáles operar. Por favor espere hasta que las mismas hayan sido cargadas.')
        return redirect(url_for("auth.redirectlink"))
    return render_template("stock/select_oc.html", ocd = ocd)


# Envío a un formulario, los productos de la OC a ingresar a depósito
@bp.route("/stock/enter_prods", methods=["GET", "POST"])
@login_required
def enter_prods():
    if request.method == "POST":
        orselec = request.form["seloc"]
        lphrase = ' GROUP BY 1, 2, 3, 4, 5 HAVING (IFNULL(o.fl_sok, 0) + IFNULL(o.q_real, 0)) < 1'
        db = get_db()
        whexc = ' AND id_warehouse NOT IN (13, 14, 15, 16) ORDER BY tx_warehouse'
        whs = db.execute(query_wh + whexc).fetchall()
        query_occ = query_oc + ' AND h.id_order = ' + orselec + lphrase
        ocp = db.execute(query_occ).fetchall()
        if len(ocp) < 1:
            flash('La orden de compra no posee productos pendientes de asignación. Por favor, indique que la carga de la misma ha sido completada.')
            return redirect(url_for("auth.redirectlink"))
        return render_template("stock/enter_products.html", whs = whs, ocp = ocp)


# Agrego los productos de la OC a la tabla de movimientos y de stock
@bp.route("/stock/enter_wprods", methods=["GET", "POST"])
@login_required
def enter_wprods():
    if request.method == "POST":
        dtodayfull = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        idmv = request.form.getlist("id_move")
        odate = request.form["odt"]
        onum = request.form["nuo"]
        idprod = request.form.getlist("id_prodh") # Agregado
        expdate = request.form.getlist("exdt")
        flv = request.form.getlist("okq")
        qsol = request.form.getlist("q_qs") # Agregado
        qreal = request.form.getlist("q_rec")
        wdest = request.form.getlist("id_wh")
        # oper = session.get("user_id")
        for expdates, flvs, qreals, wdests, idmvs, idprods, qsols in zip (expdate, flv, qreal, wdest, idmv, idprod, qsol):
            db = get_db()
            upd_inn = """UPDATE bt_in_out_prods SET dt_num_order =(?), num_order =(?), dt_expiry =(?), fl_sok =(?), q_real =(?), id_warehouse =(?) WHERE id_movement =(?)"""
            db.execute(upd_inn, (odate, onum, expdates, flvs, qreals, wdests, idmvs,)).fetchall()
            # Creo tabla temporal donde ingreso los productos ingresados de la OC
            db.execute("""DROP TABLE IF EXISTS ttis""")
            db.execute(query_insocs).fetchall()
            # Agrego los prods ingresados de la OC a tabla temporal
            db.execute("INSERT INTO ttis (dt_io, id_product, id_warehouse, dt_expiry, q_inn, q_inn_real, fl_ok) VALUES (?,?,?,?,?,?,?)",
                       (dtodayfull, idprods, wdests, expdates, qsols, qreals, flvs),
                       )
            # Inserto los productos de la temporal en la tabla de stock (bt_stock)
            db.execute(query_addocst).fetchall()
            # Actualizo las partidas y el stock general
            db.execute('UPDATE bt_stock SET q_out = 0 WHERE q_out IS NULL').fetchall()
            db.execute('UPDATE bt_stock SET q_stock = a.stock_av FROM (' + query_us + ') a WHERE bt_stock.id_io = a.id_io').fetchall()
            # Actualizo en la bt_product, el stock de los productos ingresados
            db.execute(query_jafc).fetchall()
            # Actualizo en la bt_product, la fecha de los productos ingresados
            uld = ('UPDATE bt_product SET dt_last_update = (?) WHERE id_product = (?)')
            if flvs != '':
                db.execute(uld, (dtodayfull, idprods,)).fetchall()
            else:
                pass
            # Compruebo si el producto está en la PO y de existir, actualizo el stock que se indica en PO
            sppo = db.execute(f"""SELECT COUNT(*) AS quantity FROM temp_order""").fetchone()[0]
            if sppo > 0:
                upd_tmpordr = """UPDATE temp_order SET q_exist = a.stock_av"""
                db.execute(upd_tmpordr + ' FROM (' + query_us + ') a WHERE temp_order.id_prod = (?)', (idprods,)).fetchall()
            else:
                pass
            db.commit()
        flash('Los productos ingresados se actualizaron correctamente')
        return redirect(url_for("auth.redirectlink"))


# Operaciones entre depósitos
# Disponibilidad de productos
@bp.route("/stock/available_ptt")
@login_required
def available_ptt():
    db = get_db()
    aptt = db.execute(query_transf).fetchall()
    whs = db.execute(query_wh + ' AND id_warehouse NOT IN (15, 16) ORDER BY tx_warehouse;').fetchall()
    return render_template("stock/move_stock.html", whs = whs, aptt = aptt)


# Agrego los productos transferidos a la tabla de stock
@bp.route("/stock/enter_transf", methods=["GET", "POST"])
@login_required
def enter_transf():
    if request.method == "POST":
        dtodayfull = str(datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None))
        prod = request.form.getlist('idprodh')
        # print('Productos en lista idprodh: ', prod) # Punto de Control
        qtr = request.form.getlist('q_trf')
        # print('Cantidades en lista q_trf: ', qtr)
        # qav = request.form.getlist('avai')
        wdest = request.form.getlist('id_wh')
        # print('Depositos en lista wdest: ', wdest)
        # Creo DF's con los datos recibidos desde el formulario de carga - Disponible y a Transferir
        dict_transf = {'dt_io': dtodayfull, 'id_product': prod, 'id_warehouse': wdest, 'q_prodt': qtr}
        transx = pd.DataFrame(dict_transf)
        # Creo dataframe con los valores obtenidos de las listas y tuplas
        transf = pd.DataFrame(transx, columns=['id_product', 'id_warehouse', 'q_prodt'])
        # 20250524transf[['id_io', 'id_product', 'id_warehouse', 'q_proda', 'q_prodt']] = transf[['id_io', 'id_product', 'id_warehouse', 'q_proda', 'q_prodt']].apply(pd.to_numeric)
        transf[['id_product', 'id_warehouse', 'q_prodt']] = transf[['id_product', 'id_warehouse', 'q_prodt']].apply(pd.to_numeric)
        # Obtengo los índices de las filas a eliminar, que son aquellas en la que la q a transferir es 0
        indexNum = transf[transf['q_prodt'] == 0].index
        # Elimino los índices
        transf.drop(indexNum, inplace = True)
        # Regenero los indices
        transf.reset_index(drop=True, inplace=True)
        # Agrego columna con valor 0 para el campo q_out, valor de la existencia en el lote y fecha
        transf['q_out'] = 0
        transf = transf.assign(q_batch_balance=transf['q_prodt'])
        transf.insert(loc=0, column='dt_io', value=dtodayfull, allow_duplicates=False)
        # Comienzo a operar sobre los datos obtenidos
        # Si hay transferencias hacia el bar, las envio a la tabla correspondiente
        if (transf['id_warehouse'] == 12).sum() > 0:
            transf_12 = transf[transf['id_warehouse'] == 12]
            transf_to_ins_bar = [tuple(row) for row in transf_12.values]
            db = get_db()
            query_ins_bts_bar = """INSERT INTO bt_stock_bar (dt_io, id_product, id_warehouse, q_inn, q_out, q_batch_balance) VALUES (?,?,?,?,?,?)"""
            prods_tt = tuple(transf_12['id_product'].tolist())
            ids_str = ', '.join(map(str, prods_tt))
            qry_updexistbar = f"""
                    UPDATE bt_stock_bar SET q_stock = a.stock_av
                    FROM
                    (
                    SELECT
                        id_io,
                        id_product,
                        id_warehouse,
                        q_batch_balance,
                        SUM(q_batch_balance) OVER(PARTITION BY id_product ORDER BY id_io, dt_expiry ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS stock_av
                    FROM bt_stock_bar
                    WHERE q_batch_balance >= 0
                    AND id_warehouse = 12
                    AND (
                        q_stock >= 0
                        OR q_stock IS NULL
                        )
                    AND id_product IN ({ids_str})
                    ) a  
                    WHERE bt_stock_bar.id_io = a.id_io
                    """
            db.executemany(query_ins_bts_bar, transf_to_ins_bar)
            db.execute(qry_updexistbar).fetchall()
            db.commit()
        else:
            pass
        db = get_db()
        query_ins_bts = """INSERT INTO bt_stock (dt_io, id_product, id_warehouse, q_inn, q_out, q_batch_balance) VALUES (?,?,?,?,?,?)"""
        transf_to_ins = [tuple(row) for row in transf.values]
        db.executemany(query_ins_bts, transf_to_ins)
        db.commit()
        # Genero lista con los productos que se van a transferir
        df2 = transf.loc[:, ['id_product', 'q_prodt']]
        df2 = df2.rename(columns={'q_prodt': 'q_substract'}) # No necesario, solo para dejarlo como JN
        l2 = df2.values.tolist()
        # Tomo los productos para luego incorporarlos como condicion a la consulta sobre el stock existente
        only_prods = [sublist[0] for sublist in l2]
        # Convirtiendo la lista resultante a una tupla
        res_only_prods = tuple(only_prods)
        # Traigo los productos existentes, para operar sobre ellos
        df1 = pd.read_sql_query(query_us + ' AND id_product IN (' + (', '.join(map(str, res_only_prods))) + ')', db)
        df1.columns = ['id_io', 'id_product', 'id_warehouse', 'q_batch_balance', 'stock_av']
        l1 = df1.values.tolist()
        # Defino los valores a comparar para actualizar el stock; comienzan los calculos
        pl1 = 1  # Posición del ID de producto en l1
        pl2 = 0  # Posición del ID de producto en l2
        pl13 = 3 # Posición de la cantidad en stock en l1
        pl21 = 1 # Posición de la cantidad a transferir en l2
        # Se itera sobre CADA solicitud de transferencia en l2
        for i, transfer_request in enumerate(l2):
            if len(transfer_request) > pl2 and len(transfer_request) > pl21:
                product_to_transfer = transfer_request[pl2]
                requested_transfer_quantity = transfer_request[pl21]

                # Realizo seguimiento de cuanto se ha transferido realmente para el producto actual
                current_transferred_quantity = 0

                # Itero sobre l1 para encontrar stock disponible del producto
                for j in range(len(l1)):
                    inventory_item = l1[j] # Obtenemos la sublista actual de l1

                    # Validacion del formato del inventario
                    if len(inventory_item) > pl1 and len(inventory_item) > pl13:
                        product_in_stock = inventory_item[pl1]
                        quantity_in_stock = inventory_item[pl13]
                        batch_id = inventory_item[0] # El primer elemento es el nro de lote; se usaba para comprobar

                        # Comprueba si los id_product coinciden y hay stock disponible en este lote
                        if product_in_stock == product_to_transfer and quantity_in_stock > 0:
                            remaining_to_transfer = requested_transfer_quantity - current_transferred_quantity

                            # Caso 1: la cantidad en el lote es suficiente
                            if quantity_in_stock >= remaining_to_transfer:
                                quantity_to_take_from_batch = remaining_to_transfer
                                l1[j][pl13] -= quantity_to_take_from_batch # Deduce del stock
                                current_transferred_quantity += quantity_to_take_from_batch
                                # Agrega la cantidad transferida a la sublist l1
                                l1[j].append(quantity_to_take_from_batch)

                                # print(f" - Lote {batch_id} (Prod: {product_in_stock}, Stock ant.: {quantity_in_stock}). Transferido {quantity_to_take_from_batch}. Nuevo stock: {l1[j][pl13]}. Agregado: {quantity_to_take_from_batch}.")

                                # Si el total a transferir es suficiente, detiene el proceso para el producto tratado
                                if current_transferred_quantity == requested_transfer_quantity:
                                    # print(f"  -> Transferencia completa para id_product ID {product_to_transfer}.")
                                    break # Sale del loop (sobre l1)

                            # Caso 2: La cantidad en el lote no es suficiente para la transferencia
                            else:
                                quantity_to_take_from_batch = quantity_in_stock # Toma todo el stock del lote
                                l1[j][pl13] = 0 # El lote esta agotado
                                current_transferred_quantity += quantity_to_take_from_batch
                                # Agrega la cantidad transferida a la sublist l1
                                l1[j].append(quantity_to_take_from_batch)

                                # print(f" - Lote {batch_id} (Prod: {product_in_stock}, Stock ant: {quantity_in_stock}). Transferido {quantity_to_take_from_batch}. Nuevo stock: 0. (Batch depleted). Agregado: {quantity_to_take_from_batch}.")

                                # Continue to the next batch in l1 to find more stock for the same product
                    else:
                        pass # print(f" - Cuidado: El producto {inventory_item} en l1 No tieen suficiente cantidad. Salteando este item.")

                # Luego de intentar satisfacer el total a transferir con la totalidad de lotes disponibles en l1
                if current_transferred_quantity < requested_transfer_quantity:
                    pass # print(f" !!! Atencion: No se completo la transferencia de {product_to_transfer}. Faltan {requested_transfer_quantity - current_transferred_quantity} unidades.")
            else:
                pass # print(f"--- Cuidado: La cantidad a transferir {transfer_request} en l2 no tiene la cantidad necesaria de elementos. Se saltea la transferencia. ---")

        # Genero un DF para poder trabajarlo en la BD
        dfx = pd.DataFrame(l1, columns=['id_io', 'id_product', 'id_warehouse', 'q_batch_balance', 'stock_acum', 'transfer']).fillna(0)
        # Actualizo los datos de las transferencias de salida
        qry_udp_bts = """
                        UPDATE bt_stock
                        SET q_batch_balance = ?, q_out = COALESCE(q_out, 0) + ?
                        WHERE id_io = ? AND id_product = ?;
                        """
        data_update = []
        for index, row in dfx.iterrows():
            q_batch_balance_val = int(row['q_batch_balance'])
            transfer_val = int(row['transfer'])
            id_io_val = int(row['id_io'])
            id_product_val = int(row['id_product'])
            
            data_update.append((
                q_batch_balance_val,
                transfer_val,
                id_io_val,
                id_product_val
            ))
        try:
            db.executemany(qry_udp_bts, data_update)
            db.commit()
        except Exception as e:
            db.rollback()
        # Concateno para realizar el update del campo q_stock (acumulado) en bt_stock
        qry_str1 = """
                    UPDATE bt_stock SET q_stock = a.stock_av
                    FROM
                    (
                    SELECT
                        id_io,
                        id_product,
                        id_warehouse,
                        q_batch_balance,
                        SUM(q_batch_balance) OVER(PARTITION BY id_product ORDER BY id_io, dt_expiry ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS stock_av
                    FROM bt_stock
                    WHERE q_batch_balance >= 0
                    AND id_warehouse < 12
                    AND q_stock >= 0
                    """
        qry_str2 = " ) a  WHERE bt_stock.id_io = a.id_io"
        squpd = (qry_str1 + ' AND id_product IN (' + (', '.join(map(str, res_only_prods))) + ') ' + qry_str2)
        # Fin concatenacion
        db.execute(squpd)
        # Actualizo - concatenando - los productos con movimientos en bt_product
        ptu = """
            UPDATE bt_product SET q_stock = a.q_stock
            FROM (
            SELECT
                id_product,
                q_stock,
                RANK() OVER (PARTITION BY id_product ORDER BY id_io DESC) AS stock_det
            FROM bt_stock
            WHERE id_warehouse <= 11
            """
        end_string = ") a WHERE a.stock_det = 1 AND bt_product.id_product = a.id_product"
        run_str = (ptu + end_string + ' AND a.id_product IN (' + (', '.join(map(str, res_only_prods))) + ') ')
        db.execute(run_str)
        # Actualizo la fecha de actualización de los productos
        uld = ('UPDATE bt_product SET dt_last_update = (?) WHERE id_product IN (' + (', '.join(map(str, res_only_prods))) + ')')
        db.execute(uld, (dtodayfull,)).fetchall()
        # Verifico existencia de preorden para actualizar las existencias
        sppo = db.execute(f"""SELECT COUNT(*) AS quantity FROM temp_order""").fetchone()[0]
        if sppo > 0:
            tou = """
            UPDATE temp_order SET q_exist = a.q_stock
            FROM (
            SELECT
                id_product,
                dt_io,
                q_stock,
                RANK() OVER (PARTITION BY id_product ORDER BY id_io DESC) AS stock_det
            FROM bt_stock
            WHERE id_warehouse <= 11
            """
            end_stringto = ") a WHERE a.stock_det = 1 AND temp_order.id_prod = a.id_product"
            run_tou = (tou + end_stringto + ' AND a.id_product IN (' + (', '.join(map(str, res_only_prods))) + ') ')
            db.execute(run_tou)
        else:
            pass
        db.commit()
        # Controlo que los valores a transferir no sean nulos
        comprob = (dfx['transfer'] != 0).sum()
        if comprob >= 1:
            flash('Los productos fueron transferidos correctamente.')
            return redirect(url_for("auth.redirectlink"))
        flash('Los productos fueron transferidos correctamente, pero hubo intento de transferir por encima de la existencia. Ver listado.')
        return redirect(url_for("auth.redirectlink"))



# Detalle de los almacenes para seleccionar en la baja por eventualidades
@bp.route("/stock/out_product")
@login_required
def out_product():
    db = get_db()
    whexc = ' AND id_warehouse < 13 ORDER BY tx_warehouse'
    whs = db.execute(query_wh + whexc ).fetchall()
    prods = db.execute(query_prods).fetchall()
    return render_template("stock/out_product.html", whs = whs, prods = prods)


# Entrada al stock por salidas no convencionales (vencimiento, rotura, etc.)
@bp.route("/stock/add_out_product", methods=["GET", "POST"])
@login_required
def add_out_product():
    if request.method == "POST":
        dtodayfull = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        tx_mot = request.form["tx_ca"]
        prd = request.form["id_dop"]
        idwh = request.form["id_wh"]
        idwhr = '15'
        # expdate = request.form["expiry_date"]
        qout = request.form["qty_out"]
        txro = request.form["reason_out"]
        reason = tx_mot + ': ' + txro
        db = get_db()
        # Compruebo la posibilidad de dar la baja de acuerdo a los parámetros obtenidos
        db.execute("""DROP TABLE IF EXISTS ptrs""")
        ctt = """CREATE TEMPORARY TABLE ptrs AS
                SELECT
                    id_io,
                    id_product,
                    id_warehouse,
                    dt_expiry,
                    q_batch_balance,
                    ROW_NUMBER() OVER(ORDER BY dt_expiry) AS rn
                FROM bt_stock
                WHERE id_product = (?)
                AND id_warehouse = (?)
                -- AND DATE(dt_expiry) = DATE((?))
                AND q_batch_balance >= (?);
                """
        db.execute(ctt, (prd, idwh, qout)).fetchall()
        comprob = db.execute('SELECT COUNT(*) AS q FROM ptrs;').fetchone()[0]
        if comprob < 1:
            flash('No existen productos a dar de baja con esa combinatoria. Por favor, chequee que productos son los que debe retirar del stock.')
            return redirect(url_for("auth.redirectlink"))
        # Al estar todo OK, agrego registros sumando al almacén de bajas y restando del almacén origen
        db.execute("INSERT INTO bt_stock (dt_io, id_product, id_warehouse, q_inn, q_batch_balance, tx_reason) VALUES (?,?,?,?,?,?)",
                           (dtodayfull, prd, idwhr, qout, qout, reason)
                           )
        upd_out = """UPDATE bt_stock SET q_out = IFNULL(q_out, 0) + (?), q_batch_balance = (IFNULL(q_batch_balance, 0) - (?)) WHERE id_io = (SELECT id_io FROM ptrs WHERE rn = 1)"""
        db.execute(upd_out, (qout, qout,))
        # Actualizo las partidas y el stock general
        db.execute("""UPDATE bt_stock SET q_out = 0 WHERE q_out IS NULL""")
        db.execute('UPDATE bt_stock SET q_stock = a.stock_av FROM (' + query_us + ') a WHERE bt_stock.id_io = a.id_io').fetchall()
        ptu = """
            UPDATE bt_product SET q_stock = a.q_stock, dt_last_update = (?)
            FROM (
            SELECT
                id_product,
                q_stock,
                RANK() OVER (PARTITION BY id_product ORDER BY id_io DESC) AS stock_det
            FROM bt_stock
            WHERE id_warehouse <= 11
            AND id_product = (?)
            ) a
            WHERE a.stock_det = 1
            AND bt_product.id_product = a.id_product;
            """
        db.execute(ptu, (dtodayfull, prd,)).fetchall()
        # Compruebo si el producto está en la PO y de existir, actualizo el stock que se indica en PO
        sppo = db.execute(f"""SELECT COUNT(*) AS quantity FROM temp_order""").fetchone()[0]
        if sppo > 0:
            tou = """
                UPDATE temp_order SET q_exist = a.q_stock
                FROM (
                    SELECT
                        id_product,
                        dt_io,
                        q_stock,
                        RANK() OVER (PARTITION BY id_product ORDER BY id_io DESC) AS stock_det
                    FROM bt_stock
                    WHERE id_warehouse <= 11
                    AND id_product = (?)
                    ) a
                WHERE a.stock_det = 1
                AND temp_order.id_prod = a.id_product;
                """
            db.execute(tou, (prd,)).fetchall()
        else:
            pass
        db.commit()
        flash('Baja ingresada correctamente')
        return redirect(url_for("auth.redirectlink"))
    return render_template("stock/out_products.html")