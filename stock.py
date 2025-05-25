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
query_cat = """
            SELECT * FROM lkp_categories ORDER BY tx_category
            """
query_scat = """
            SELECT * FROM lkp_subcategories ORDER BY tx_subcategory
            """
query_units = """
            SELECT * FROM lkp_units ORDER BY tx_unity
            """
query_wh = """
            SELECT * FROM lkp_warehouse WHERE flag_ctrl = 1
            """

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
                t.id_io,
                t.id_product,
                s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS producto,
                t.id_warehouse,
                w.tx_warehouse,
                t.dt_expiry,
                t.q_batch_balance
            FROM bt_stock t INNER JOIN bt_product b
            ON t.id_product = b.id_product
            INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            INNER JOIN lkp_warehouse w
            ON (
                t.id_warehouse = w.id_warehouse
                AND w.id_warehouse NOT IN (12, 13, 14, 15)
                )
            WHERE t.q_batch_balance > 0
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
            CREATE TEMPORARY TABLE nsv AS
            SELECT
                id_io,
                id_product,
                id_warehouse,
                dt_expiry,
                q_batch_balance,
                -- SUM(q_batch_balance) OVER(PARTITION BY id_product ORDER BY dt_expiry ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS stock
                SUM(q_batch_balance) OVER(PARTITION BY id_product ORDER BY id_io, dt_expiry ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS stock
            FROM bt_stock
            WHERE q_batch_balance <> 0
            AND id_warehouse < 12
            ORDER BY 2, 3, 1;
            """

# Creo temporal para agregar las confirmaciones de la OC en el stock
query_insocs = """
            CREATE TEMPORARY TABLE ttis (
                dt_io           TEXT,
                id_product      INTEGER,
                id_warehouse    INTEGER,
                dt_expiry       TEXT,
                q_inn           INTEGER,
                q_inn_real      INTEGER,
                fl_ok            INTEGER
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


# Entrada masiva de productos (recepcion de remito del proveedor)
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
                # Actualizo las partidas y el stock general
                db.execute("""DROP TABLE IF EXISTS nsv""")
                db.execute(query_us).fetchall()
                db.execute("""UPDATE bt_stock SET q_stock = (SELECT stock FROM nsv WHERE nsv.id_io = bt_stock.id_io)""")
                db.commit()
            flash('Productos ingresados correctamente')
            return redirect(url_for("auth.redirectlink"))
    return render_template("stock/in_multi_products.html")


# Exportacion de las existencias a vencer por almacen
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
        whexc = ' AND id_warehouse NOT IN (13, 14, 15) ORDER BY tx_warehouse'
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
            db.execute("""DROP TABLE IF EXISTS nsv""")
            db.execute(query_us).fetchall()
            db.execute("""UPDATE bt_stock SET q_stock = (SELECT stock FROM nsv WHERE nsv.id_io = bt_stock.id_io)""")
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
    whs = db.execute(query_wh + ' AND id_warehouse <> 15 ORDER BY tx_warehouse;').fetchall()
    return render_template("stock/move_stock.html", whs = whs, aptt = aptt)


# Agrego los productos transferidos la tabla de stock
@bp.route("/stock/enter_transf", methods=["GET", "POST"])
@login_required
def enter_transf():
    if request.method == "POST":
        dtodayfull = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
        prod = request.form.getlist('idprodh')
        move = request.form.getlist('idioh')
        qtr = request.form.getlist('q_trf')
        qav = request.form.getlist('avai')
        wdest = request.form.getlist('id_wh')
        # Creo DF's con los datos recibidos desde el formulario de carga - Disponible y a Transferir
        dict_transf = {'id_io': move, 'dt_io': dtodayfull, 'id_product': prod, 'id_warehouse': wdest, 'q_proda': qav, 'q_prodt': qtr}
        transx = pd.DataFrame(dict_transf)
        # Creo dataframe con los valores obtenidos de las listas y tuplas
        transf = pd.DataFrame(transx, columns=['id_io', 'dt_io', 'id_product', 'id_warehouse', 'q_proda', 'q_prodt'])
        transf[['id_io', 'id_product', 'id_warehouse', 'q_proda', 'q_prodt']] = transf[['id_io', 'id_product', 'id_warehouse', 'q_proda', 'q_prodt']].apply(pd.to_numeric)
        # Obtengo los índices de las filas a eliminar, que son las que la q a transferir es 0
        indexNum = transf[transf['q_prodt'] == 0].index
        # Elimino los índices encontrados
        transf.drop(indexNum, inplace = True)
        # Regenero los indices
        transf.reset_index(drop=True, inplace=True)
        # Creo tabla que va a manejar la info de los productos y cantidades
        db = get_db()
        erased = """DELETE FROM temp_transfer;"""
        db.execute(erased).fetchall()
        transf.to_sql('temp_transfer', db, if_exists='append', index=False)

        tupd = pd.read_sql_query("""select q_prodt, id_io from temp_transfer WHERE q_proda >= q_prodt;""",db)
        tupd.columns = ['q_prodt', 'id_io']
        stockx = tupd.values.tolist()
        sql_update_query = """UPDATE bt_stock SET q_out = IFNULL(q_out, 0) + (?) WHERE id_io =(?)"""
        db.executemany(sql_update_query, stockx)

        # db.execute(query_upd_out).fetchall()
        upd_qs0 = """UPDATE bt_stock SET q_stock = 0 WHERE q_batch_balance = 0;"""
        db.execute(upd_qs0).fetchall()
        db.execute(query_add_transf).fetchall()
        upd_qbb = """UPDATE bt_stock SET q_batch_balance = (q_inn - IFNULL(q_out, 0));"""
        db.execute(upd_qbb).fetchall()
        db.execute("""DROP TABLE IF EXISTS nsv""")
        db.execute(query_us).fetchall()
        db.execute("""UPDATE bt_stock SET q_stock = (SELECT stock FROM nsv WHERE nsv.id_io = bt_stock.id_io)""")
        # db.execute("UPDATE sqlite_sequence SET seq = 0 WHERE name = 'temp_stock';")
        db.commit()
        # Codigo anterior - desde acá
        # dispo = [val[0] if val else '0' for val in qav]
        # dispo = list(map(int, dispo))
        # updt = [val[0] if val else '0' for val in qtr]
        # tt = list(map(int, updt))
        # if dispo >= tt:
        # if all(d >= t for d, t in zip(dispo, tt)):
        # comprob = np.greater_equal(dispo,tt).all()
        # if np.all(dispo >= tt):
        # if comprob == True:
        #    for qtrs, prods, wdests, moves in zip (qtr, prod, wdest, move):
        #        db = get_db()
        #        OK - upd_out = """UPDATE bt_stock SET q_out = IFNULL(q_out, 0) + (?) WHERE id_io =(?)"""
        #        OK - db.execute(upd_out, (qtrs, moves),).fetchall()
        #        OK - db.execute("""UPDATE bt_stock SET q_stock = 0 WHERE q_batch_balance = 0""")
        #        ins_prd = """INSERT INTO temp_stock (id_io, dt_io, id_product, id_warehouse, q_inn) VALUES(?,?,?,?,?)"""
        #        db.execute(ins_prd, (moves, dtoday, prods, wdests, qtrs),).fetchall()
        #        -- db.execute("""DELETE FROM temp_stock WHERE length(q_inn) = 0;""")
        #        db.execute(query_add_transf).fetchall()
        #        db.execute("""UPDATE bt_stock SET q_batch_balance = (q_inn - IFNULL(q_out, 0))""")
        #        db.execute("""DELETE FROM temp_stock;""")
        #        db.execute("""DROP TABLE IF EXISTS nsv""")
        #        db.execute(query_us).fetchall()
        #        db.execute("""UPDATE bt_stock SET q_stock = (SELECT stock FROM nsv WHERE nsv.id_io = bt_stock.id_io)""")
        #        db.execute("UPDATE sqlite_sequence SET seq = 0 WHERE name = 'temp_stock';")
        #        db.commit()
        # Hasta acá

        comprob = db.execute('SELECT COUNT(*) AS q FROM temp_transfer WHERE q_prodt > q_proda;').fetchone()[0]
        if comprob < 1:
            flash('Los productos fueron transferidos correctamente.')
            return redirect(url_for("auth.redirectlink"))
        flash('Los productos fueron transferidos correctamente, pero hubo intento de transferir por encima de la existencia. Ver listado.')
        return redirect(url_for("auth.redirectlink"))


# Detalle de los almacenes para seleccionar en el alta masiva
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
        expdate = request.form["expiry_date"]
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
        # db.execute(ctt, (prd, idwh, expdate, qout)).fetchall()
        db.execute(ctt, (prd, idwh, qout)).fetchall()
        comprob = db.execute('SELECT COUNT(*) AS q FROM ptrs;').fetchone()[0]
        if comprob < 1:
            flash('No existen productos a dar de baja con esa combinatoria. Por favor, chequee que productos son los que debe retirar del stock.')
            return redirect(url_for("auth.redirectlink"))
        # Al estar todo OK, agrego registros sumando al almacén de bajas y restando del almacén origen
        # db.execute("INSERT INTO bt_stock (dt_io, id_product, id_warehouse, dt_expiry, q_inn, q_batch_balance, tx_reason) VALUES (?,?,?,?,?,?,?)",
        #                    (dtoday, prd, idwhr, expdate, qout, qout, reason)
        #                    )
        db.execute("INSERT INTO bt_stock (dt_io, id_product, id_warehouse, q_inn, q_batch_balance, tx_reason) VALUES (?,?,?,?,?,?)",
                           (dtodayfull, prd, idwhr, qout, qout, reason)
                           )
        # numrow = db.execute("SELECT id_io FROM ptrs WHERE rn = 1;")
        upd_out = """UPDATE bt_stock SET q_out = IFNULL(q_out, 0) + (?), q_batch_balance = (IFNULL(q_batch_balance, 0) - (?)) WHERE id_io = (SELECT id_io FROM ptrs WHERE rn = 1)"""
        db.execute(upd_out, (qout, qout,))
        # Actualizo las partidas y el stock general
        db.execute("DROP TABLE IF EXISTS nsv")
        db.execute(query_us).fetchall()
        db.execute("""UPDATE bt_stock SET q_stock = (SELECT stock FROM nsv WHERE nsv.id_io = bt_stock.id_io)""")
        db.commit()
        flash('Baja ingresada correctamente')
        return redirect(url_for("auth.redirectlink"))
    return render_template("stock/out_products.html")