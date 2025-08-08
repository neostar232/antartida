from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for, make_response
from .auth import login_required
from .db import get_db
from datetime import datetime, date
import pytz as tz
from io import BytesIO
from flask_weasyprint import HTML, render_pdf
import pandas as pd

bp = Blueprint("orders", __name__)

# Traigo ultima instancia de orden, a fin de otorgar una numeracion temporal
query_num_ord = """SELECT IFNULL(MAX(id_order), 0) + 1 AS mxm FROM bt_order_header;"""


# Listado de categorias
query_cat = """SELECT * FROM lkp_categories ORDER BY tx_category"""


# Listado de subcategorias - se filtran en el formulario
query_cat_sel = """
                SELECT * FROM lkp_subcategories WHERE id_category IN (
                """


# Listado de productos - se filtran en el formulario
query_pr_sel = """
            SELECT
                b.id_product,
                s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS producto,
                c.id_category,
                -- IFNULL(SUM(p.q_stock),0) AS existencias, -- Modificado 20250103
                IFNULL(SUM(p.q_batch_balance),0) AS existencias,
                0 AS nuq
            FROM bt_product b INNER JOIN lkp_categories c
            ON b.id_category = c.id_category
            INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            INNER JOIN lkp_units u
            ON b.id_unity = u.id_unity
            LEFT JOIN bt_stock p
            ON (
                b.id_product = p.id_product
                AND p.id_warehouse <= 11
                )
            LEFT JOIN lkp_warehouse w
            ON p.id_warehouse = w.id_warehouse
            WHERE b.flag_ctrl = 1
            -- AND (w.id_warehouse <= 12 -- Agregado 20250103 // Se elimina condición 20250510 // back 20250614
            -- OR p.id_warehouse IS NULL)
            AND c.id_category NOT IN (SELECT DISTINCT id_category FROM temp_order)
            AND c.id_category IN (
            """


# Productos en Preorden
query_to = """SELECT
                id_prod AS id_producto,
                tx_prod AS producto,
                id_category,
                q_exist AS existencias,
                nuq
            FROM temp_order
            """

# Actualizo nro. de Pedido en la tabla de detalle
query_upd_on = """
            INSERT INTO bt_in_out_prods (dt_movement, id_order, id_product, q_in, id_user)
            SELECT
                h.dt_order,
                h.id_order,
                t.id_prod,
                t.nuq,
                h.id_user
            FROM
            (
                SELECT
                    MAX(dt_order) AS dt_order,
                    id_user,
                    id_order
                FROM bt_order_header
                WHERE fl_close_order = 0
                GROUP BY id_user, id_order
                ORDER BY dt_order DESC
                LIMIT 1
            ) h
            LEFT OUTER JOIN
            (
                SELECT
                    id_prod,
                    nuq
                FROM temp_order
            ) t;
            """

# Listado de pedidos cerrados
q_ord_sel = """
            SELECT
                dt_order,
                id_order,
                '0000-'||substr('00000000000' || id_order, -8, 8) AS format
            FROM bt_order_header
            WHERE fl_close_order <> 2
            ORDER BY id_order DESC;
            """

# Detalle de los pedidos cerrados
q_order_detail = """
                SELECT
                    b.id_product,
                    s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS producto,
                    /*
                    CASE
                        WHEN o.fl_sok = 1 THEN o.q_in
                        ELSE o.q_real
                    END AS q_prods,
                    */
                    o.q_in AS q_prods,
                    o.id_order
                FROM bt_in_out_prods o INNER JOIN bt_product b
                ON o.id_product = b.id_product
                INNER JOIN lkp_categories c
                ON b.id_category = c.id_category
                INNER JOIN lkp_subcategories s
                ON b.id_subcategory = s.id_subcategory
                INNER JOIN lkp_units u
                ON b.id_unity = u.id_unity
                WHERE b.flag_ctrl = 1
                AND o.cuit_supplier <> 99999999999
                AND o.id_order =
                """

# Insert de productos a la preorden de aquellos que fueron dados de alta en un momento posterior a su creación
query_ins_nadds = """
                INSERT INTO temp_order (id_prod, id_category, tx_prod, nuq, q_exist)
                SELECT DISTINCT p.*
                FROM
                (
                SELECT
                    b.id_product,
                    c.id_category,
                    s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS tx_producto,
                    0 AS q_cantidad,
                    IFNULL(MAX(p.q_batch_balance),0) AS q_existencias
                FROM bt_product b INNER JOIN lkp_categories c
                ON b.id_category = c.id_category
                INNER JOIN lkp_subcategories s
                ON b.id_subcategory = s.id_subcategory
                INNER JOIN lkp_units u
                ON b.id_unity = u.id_unity
                LEFT JOIN bt_stock p
                ON b.id_product = p.id_product
                LEFT JOIN lkp_warehouse w
                ON p.id_warehouse = w.id_warehouse
                WHERE b.flag_ctrl = 1
                GROUP BY 1, 2, 3, 4
                ) p LEFT JOIN temp_order t
                ON (
                    p.id_category = t.id_category
                    AND p.id_product = t.id_prod
                    )
                INNER JOIN temp_order o
                on p.id_category = o.id_category
                WHERE t.id_category IS NULL
                AND o.nuq IS NOT NULL
                ORDER BY 2, 1;
                """

# Productos de la Orden de Compra que se revierte
query_revoc = """
               INSERT INTO temp_order (id_prod, id_category, tx_prod, nuq, q_exist)
               SELECT
                    o.id_product,
                    c.id_category,
                    s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS producto,
                    o.q_in AS nuq,
                    IFNULL(SUM(p.q_batch_balance),0) AS existencias
                FROM bt_in_out_prods o INNER JOIN bt_product b 
                ON o.id_product = b.id_product
                INNER JOIN lkp_categories c
                ON b.id_category = c.id_category
                INNER JOIN lkp_subcategories s
                ON b.id_subcategory = s.id_subcategory
                INNER JOIN lkp_units u
                ON b.id_unity = u.id_unity
                LEFT JOIN bt_stock p
                ON o.id_product = p.id_product
                WHERE b.flag_ctrl = 1
                AND o.id_order =                 
                """

# Queries para clonar la preorden
query_clone1 = """
                SELECT
                    b.id_product,
                    c.id_category,
                    s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS producto,                    
                    IFNULL(i.q_in,0) AS q_solicitada,
                    IFNULL(SUM(p.q_stock),0) AS q_stock
                FROM bt_in_out_prods i INNER JOIN bt_product b
                ON i.id_product = b.id_product
                INNER JOIN lkp_categories c
                ON b.id_category = c.id_category
                INNER JOIN lkp_subcategories s
                ON b.id_subcategory = s.id_subcategory
                INNER JOIN lkp_units u
                ON b.id_unity = u.id_unity
                LEFT JOIN bt_stock p
                ON i.id_product = p.id_product
                WHERE i.cuit_supplier <> 99999999999
                AND i.id_order = (?)
                GROUP BY 1, 2, 3, 4
                """

query_clone2 = """
                SELECT
                    b.id_product,
                    c.id_category,
                    s.tx_subcategory ||': '|| b.tx_product ||' - ' || u.tx_unity AS producto,                    
                    0 AS q_solicitada,
                    0 AS q_stock
                FROM bt_product b INNER JOIN lkp_categories c
                ON b.id_category = c.id_category
                INNER JOIN lkp_subcategories s
                ON b.id_subcategory = s.id_subcategory
                INNER JOIN lkp_units u
                ON b.id_unity = u.id_unity
                WHERE b.id_product NOT IN (SELECT id_product FROM bt_in_out_prods WHERE id_order = (?))
                AND c.id_category IN
                (
                    SELECT DISTINCT
                        c.id_category
                    FROM bt_in_out_prods io INNER JOIN bt_product o
                    ON io.id_product = o.id_product
                    INNER JOIN lkp_categories c
                    ON o.id_category = c.id_category
                    WHERE io.cuit_supplier <> 99999999999
                    AND io.id_order = (?)
                )
                """

# Muestro las categorias a seleccionar para luego, traerme los productos
# Si la preorden está cerrada (vo == 1), no permito avanzar e informo la situacion
@bp.route("/orders/ordering_sc")
@login_required
def ordering_sc():
    db = get_db()
    ur = session.get("role")
    vo = db.execute(f"""SELECT COUNT(DISTINCT fl_close) AS marca FROM temp_order WHERE fl_close = '{ur}' """).fetchone()[0]
    cates = db.execute(query_cat).fetchall()
    if vo == 1:
        flash('Existe una preorden cerrada en curso. No se puede generar una nueva hasta finalizar el proceso de compra.')
        return redirect(url_for("auth.redirectlink"))
    return render_template("orders/ordering_sc.html", cates = cates, vo = vo)


# Muestro los productos a seleccionar, dependiendo de la/s categoria/s seleccionadas
@bp.route("/orders/ordering_sp", methods=["GET", "POST"])
@login_required
def ordering_sp():
    if request.method == "POST":
        idct = request.form.getlist("id_cate")
        error = None
        if error is not None:
            flash(error)
        else:
            db = get_db()
            new_query = query_pr_sel + (", ".join(map(str, idct))) + ') GROUP BY 1, 2, 3, 5 ORDER BY producto'
            prods = db.execute(new_query).fetchall()
            db.commit()
            return render_template("orders/ordering_sp.html", prods = prods) #, suca = suca)


# Agrego productos a la preorden
@bp.route("/orders/add_to_order", methods=("GET", "POST"))
@login_required
def add_to_order():
    if request.method == "POST":
        id = request.form.getlist("id_prod")
        prod = request.form.getlist("tx_prod")
        q = request.form.getlist("qty_in")
        cate = request.form.getlist("id_ctgr")
        s_exist = request.form.getlist("q_exist")
        error = None
        if error is not None:
            flash(error)
        else:
            db = get_db()
            numor = db.execute(query_num_ord).fetchall()
            # Tomo la lista de productos seleccionados desde el formulario
            for ids, cates, prods, qs, s_exists in zip(id, cate, prod, q, s_exist):
                db = get_db()
                # Guardo los datos en tabla temporal (todos, el form baja completo)
                db.execute("INSERT INTO temp_order (id_prod, id_category, tx_prod, nuq, q_exist) VALUES (?,?,?,?,?)",
                               (ids, cates, prods, qs, s_exists),
                               )
                # Borro los productos que no cuentan con cantidad o la cantidad es vacia
                query_cont_order = """SELECT id_prod, tx_prod, SUM(nuq) AS nuq FROM temp_order WHERE nuq > 0 GROUP BY 1, 2 ORDER BY tx_prod"""
                content = db.execute(query_cont_order).fetchall()
                db.execute("UPDATE temp_order SET nuq = 0 WHERE LENGTH(nuq) < 1 OR nuq glob '*[^0-9]*';")
                db.commit()
        return render_template("orders/ordering_ax.html", numor = numor, content = content )
    return redirect(url_for("orders.add_to_order"))


# Visualizo productos existentes en la preorden
@bp.route("/orders/view_order", methods=("GET", "POST"))
@login_required
def view_order():
    db = get_db()
    ctrl = db.execute('SELECT COUNT(*) AS q FROM temp_order;').fetchone()[0]
    if ctrl < 1:
        flash('No existe una preorden para visualizar.')
        return redirect(url_for("auth.redirectlink"))  
    complete = query_to + " WHERE nuq > 0 ORDER BY tx_prod"
    to_view = db.execute(complete).fetchall()
    db.commit()
    if len(to_view) < 1:
        flash('No existen preórdenes para visualizar. Genere una nueva o aguarde una nueva alta.')
        return redirect(url_for("auth.redirectlink"))
    return render_template("orders/order_view.html", to_view = to_view)

# Selecciono productos para una futura eliminacion (no se utiliza, la eliminacion es masiva)
@bp.route("/orders/sel_remove_to_order", methods=("GET", "POST"))
@login_required
def sel_remove_to_order():
    db = get_db()
    to_del = db.execute(query_to).fetchall()
    db.commit()
    return render_template("orders/ordering_spdel.html", to_del = to_del)


# Borrado de productos de la preorden
@bp.route("/orders/ax_remove_to_order", methods=("GET", "POST"))
@login_required
def ax_remove_to_order():
    if request.method == "POST":
        for getid in request.form.getlist("checkout"):
            db = get_db()
            db.execute("DELETE FROM temp_order WHERE id_to = (?)", [getid])
            db.commit()
        flash('Los productos han sido eliminados!')
    return redirect(url_for("auth.redirectlink"))


# Selecciono productos existentes en la preorden para update
@bp.route("/orders/sel_upd_order", methods=("GET", "POST"))
@login_required
def sel_upd_order():
    db = get_db()
    ur = session.get("role")
    vo = db.execute(f"""SELECT COUNT(DISTINCT fl_close) AS marca FROM temp_order WHERE fl_close = '{ur}' """).fetchone()[0]
    db.execute(query_ins_nadds).fetchall()
    complete = query_to + ' ORDER BY 2'
    to_upd = db.execute(complete).fetchall()
    db.commit()
    if vo == 1:
        flash('No existe una preorden en curso en condiciones de modificarse. Aguarde hasta que se cargue una nueva o finalice el proceso de compra.')
        return redirect(url_for("auth.redirectlink"))
    if len(to_upd) < 1:
        flash('No existe una preorden en curso en condiciones de modificarse. Aguarde hasta que se cargue una nueva o finalice el proceso de compra.')
        return redirect(url_for("auth.redirectlink"))
    return render_template("orders/ordering_update.html", to_upd = to_upd)


# Modifico cantidad de productos en la preorden
@bp.route("/orders/update_order", methods=("GET", "POST"))
@login_required
def update_order():
    if request.method == "POST":
        id = request.form.getlist("id_prod")
        q = request.form.getlist("nuqv")
        error = None
        if error is not None:
            flash(error)
        else:
            db = get_db()
            numor = db.execute(query_num_ord).fetchall()
            # Tomo la lista de productos seleccionados desde el formulario
            for ids, qs in zip(id, q):
                db = get_db()
                # Guardo los datos en tabla temporal (todos, el form baja completo)
                db.execute("UPDATE temp_order SET nuq = (?) WHERE id_prod = (?)", (qs, ids),)
                query_cont_order = """SELECT id_prod, tx_prod, nuq FROM temp_order WHERE nuq > 0 ORDER BY tx_prod"""
                content = db.execute(query_cont_order).fetchall()
                db.execute("UPDATE temp_order SET nuq = 0 WHERE LENGTH(nuq) < 1 OR nuq glob '*[^0-9]*';")
                db.commit()
        return render_template("orders/ordering_ax.html", numor = numor, content = content )
    return redirect(url_for("orders.update_order"))


# Creo la Orden de Compra a partir de la preorden
@bp.route("/orders/go_generate_order", methods=("GET", "POST"))
@login_required
def go_generate_order():
    db = get_db()
    ctrl_compf = db.execute('SELECT COUNT(*) AS q FROM temp_order WHERE fl_close IS NOT NULL;').fetchone()[0]
    if ctrl_compf < 1:
        flash('No existe una preorden cerrada en este momento. Debe cerrarse la preorden y controlarse antes de generar la Orden de Compra.')
        return redirect(url_for("auth.redirectlink"))    
    ctrl_comp = db.execute('SELECT COUNT(*) AS q FROM temp_order;').fetchone()[0]
    if ctrl_comp < 1:
        flash('No existe una preorden en curso para transformarse en Orden de Compra.')
        return redirect(url_for("auth.redirectlink"))
    else:
        return render_template('orders/ordering_gen.html')

# Acá se procesa el pedido
# Genera el nro de orden
# Elimina los productos sin unidades
# Ingresa todos los productos a la tabla de ingresos
# Vacia la tabla de preordenes
# Vuelve a 0 el autoincremental de la tabla de preordenes
@bp.route("/orders/generate_order", methods=("GET", "POST"))
@login_required
def generate_order():
    if request.method == "POST":
        dtoday = date.today()
        oper = session.get("user_id")
        db = get_db()
        db.execute("INSERT INTO bt_order_header (dt_order, id_user) VALUES (?,?)",
                   (dtoday, oper),
                   )
        db.execute("DELETE FROM temp_order WHERE nuq = 0 OR nuq IS NULL OR nuq = '';")
        db.execute(query_upd_on) # nro. de Pedido en la tabla de detalle
        db.execute("DELETE FROM temp_order;")
        db.execute("UPDATE sqlite_sequence SET seq = 0 WHERE name = 'temp_order';")
        db.commit()
    flash('Se generó la Orden de Compra correctamente. El próximo paso es la Recepción e Ingreso de los productos.')
    return redirect(url_for("auth.redirectlink"))

# Cabeceras de las ordenes cerradas, para ser seleccionadas para gestionar
@bp.route("/orders/view_closed_orders")
@login_required
def view_closed_orders():
    db = get_db()
    ctrl_close_order = db.execute('SELECT COUNT(*) AS q FROM bt_order_header WHERE fl_close_order <> 2;').fetchone()[0]
    if ctrl_close_order < 1:
        flash('No existen Ordenes de Compra para visualizar.')
        return redirect(url_for("auth.redirectlink"))
    closed_order = db.execute(q_ord_sel)
    db.commit()
    return render_template("orders/order_select.html", closed_order = closed_order)

# Detalle de las ordenes cerradas - Vista en pantalla
@bp.route("/orders/order_detail", methods=("GET", "POST"))
@login_required
def order_detail():
    if request.method == "POST":
        selor = request.form["id_or"]
        error = None
        if error is not None:
            flash(error)
        else:
            db = get_db()
            det_query = (q_order_detail + selor + ' ORDER BY 2')
            det_or = db.execute(det_query).fetchall()
            db.commit()
            return render_template("orders/order_detail.html", det_or = det_or)
        

# Descarga detalle de la orden seleccionada para trabajar en excel
@bp.route("/orders/order_detail_dl", methods=("GET", "POST"))
@login_required
def order_detail_dl():
    io = BytesIO()
    selor = request.form["id_or"]
    with pd.ExcelWriter(io,  engine='openpyxl') as writer:
        db = get_db()
        det_query = (q_order_detail + selor + ' ORDER BY 2')
        list = pd.read_sql_query(det_query, db)
        # result = pd.DataFrame(list)
        pd.DataFrame(list).to_excel(writer, sheet_name='Detalle Orden', index=False)
        writer.close()
        response = make_response(io.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=detalle_orden_cerrada.xlsx'
        response.headers["Content-Type"] = "application/vnd.ms-excel"
        return response

# Descarga en PDF para enviar al proveedor
@bp.route("/orders/order_detail_pdf", methods=("GET", "POST"))
@login_required
def order_detail_pdf():
        if request.method == "POST":
            selor = request.form["id_or"]
            error = None
            if error is not None:
                flash(error)
            else:
                db = get_db()
                det_query = (q_order_detail + selor + ' ORDER BY 2')
                det_or = db.execute(det_query).fetchall()
                qoh = """SELECT
                            dt_order,
                            id_order,
                            '0000-'||substr('00000000000' || id_order, -8, 8) AS formato
                        FROM bt_order_header
                        WHERE id_order = 
                        """
                qohd = db.execute(qoh + selor).fetchall()
                db.commit()
                html = render_template("orders/order_downl.html", det_or = det_or, qohd = qohd)
                return render_pdf(HTML(string=html))

# Accedo al cierre de la preorden
@bp.route("/orders/go_close_preorder", methods=("GET", "POST"))
@login_required
def go_close_preorder():
    db = get_db()
    ctrl_comp = db.execute('SELECT COUNT(*) AS q FROM temp_order WHERE fl_close IS NULL;').fetchone()[0]
    if ctrl_comp < 1:
        flash('No existe una preorden para cerrar.')
        return redirect(url_for("auth.redirectlink"))
    # ur = user role
    ur = session.get("role")
    # Verificación orden
    vo = db.execute(f"""SELECT COUNT(DISTINCT fl_close) AS marca FROM temp_order WHERE fl_close = '{ur}' """).fetchone()[0]
    if vo == 1:
        flash('No existe una preorden para ser cerrada.')
        return redirect(url_for("auth.redirectlink"))
    return render_template('orders/ordering_genpo.html')

# Cierra preorden
@bp.route("/orders/close_preorder", methods=("GET", "POST"))
@login_required
def close_preorder():
    if request.method == "POST":
        ur = session.get("role")
        db = get_db()
        db.execute(f"""UPDATE temp_order SET fl_close = '{ur}' WHERE fl_close IS NULL""").fetchall()
        db.commit()
        flash('Preorden cerrada exitosamente')
    return redirect(url_for("auth.redirectlink"))

# Cancela cierre preorden
@bp.route("/orders/cancel_close_preorder", methods=("GET", "POST"))
@login_required
def cancel_close_preorder():
    if request.method == "POST":
        flash('Se ha cancelado el cierre de la Preorden')
        return redirect(url_for("auth.redirectlink"))


# Revierte el cierre de la preorden para cargar mas productos
@bp.route("/orders/rev_close_preorder", methods=("GET", "POST"))
@login_required
def rev_close_preorder():
    ur = session.get("role")
    db = get_db()
    ctrl_comp = db.execute(f"""SELECT COUNT(*) AS q FROM temp_order WHERE fl_close <> '{ur}' """).fetchone()[0]
    if ctrl_comp < 1:
        flash('No existe una preorden cerrada para revertir.')
        return redirect(url_for("auth.redirectlink"))
    else:
        db.execute(f"""UPDATE temp_order SET fl_close = NULL;""").fetchall
        db.commit()
        flash('Se reabrió la preorden cerrada. Ahora está nuevamente habilitada para la carga de productos.')
        return redirect(url_for("auth.redirectlink"))


# Cierra orden de Compra
@bp.route("/orders/close_order", methods=("GET", "POST"))
@login_required
def close_order():
        if request.method == "POST":
            orselec = request.form["seloc"]
            db = get_db()
            db.execute("UPDATE bt_order_header SET fl_close_order = 1 WHERE fl_close_order = 0 AND id_order = (?)", (orselec,)).fetchall()
            db.commit()
            flash('La Orden de Compra se ha cerrado definitivamente. Ya no podrán gestionarse más productos correspondientes a la carga automática.')
            return redirect(url_for("auth.redirectlink"))
        

# Accedo a la página de reversión de órdenes
@bp.route("/orders/accessing_rev")
@login_required
def accessing_rev():
    db = get_db()
    ctrl_exist_prods = db.execute('SELECT COUNT(*) AS q FROM temp_order;').fetchone()[0]
    if ctrl_exist_prods > 0:
        flash('Existe una preorden abierta. No puede revertir una Orden de compra mientras exista esa situación.')
        return redirect(url_for("auth.redirectlink"))
    return render_template("orders/ordering_revoc.html")


# Reversión Orden de compra
@bp.route("/orders/revert_order", methods=("GET", "POST"))
@login_required
def revert_order():
    db = get_db()
    # Busco la ultima OC generada
    search_order = db.execute('SELECT MAX(id_order) AS mxm FROM bt_in_out_prods;').fetchone()[0]
    search_order = str(search_order)
    # Agrego los productos a la tabla de preorden
    ins_to = query_revoc + search_order + ' GROUP BY 1, 2, 3, 4 ORDER BY 3;'
    db.execute(ins_to).fetchall()
    # Flagueo la marca de cerrado
    db.execute("UPDATE bt_order_header SET fl_close_order = 2 WHERE id_order = (?)", (search_order),)
    # Borro los productos de la tabla de ingreso y salida
    db.execute("DELETE FROM bt_in_out_prods WHERE id_order = (?)", (search_order),)
    db.commit()
    return redirect(url_for("auth.redirectlink"))


# (Listo) Genero preorden seleccionando una OC cerrada anteriormente
@bp.route("/orders/sel_preorder", methods=("GET", "POST"))
@login_required
def sel_preorder():
    db = get_db()
    qto = db.execute(f"""SELECT COUNT(*) AS cantidad FROM temp_order;""").fetchone()[0]
    if qto > 0:
        flash('Ya existe una preorden en curso. Aguarde hasta que se cargue una nueva o finalice el proceso de compra actual.')
        return redirect(url_for("auth.redirectlink"))
    # Busco ordenes de compra generadas anteriormente
    else:
        search_purch_order = db.execute('SELECT dt_order, id_order FROM bt_order_header ORDER BY 2 DESC;').fetchall()
        db.commit()
        return render_template("orders/purch_order_enum.html", search_purch_order = search_purch_order)


# (Detallo) OC's cerradas para cotejar contenido
@bp.route("/orders/detail_preorder", methods=("GET", "POST"))
@login_required
def detail_preorder():
        # Busco ordenes de compra generadas anteriormente
        db = get_db()
        id = request.args.get("id_order")
        spo = db.execute(query_clone1 + ' ORDER BY producto', (id,))
        db.commit()
        return render_template("reports/prod_preorder_enum.html", spo = spo)


# Clono orden
@bp.route("/orders/clone_preorder", methods=("GET", "POST"))
@login_required
def clone_preorder():
    db = get_db()
    qto = db.execute(f"""SELECT COUNT(*) AS cantidad FROM temp_order;""").fetchone()[0]
    if qto > 0:
        flash('Ya existe una preorden en curso. Aguarde hasta que se cargue una nueva o finalice el proceso de compra actual.')
        return redirect(url_for("auth.redirectlink"))
    # Creo las variables para ingestar la tabla de la preorden
    if request.method == "POST":
        numpoc = request.form["id_order_tc"]
        ins = ("INSERT INTO temp_order (id_prod, id_category, tx_prod, nuq, q_exist) ") # 1er. bloque sql
        uni = (ins + query_clone1 + ' UNION ' + query_clone2 + ' ORDER BY id_product') # 2do. bloque sql
        db.execute(uni, (numpoc, numpoc, numpoc))
        db.commit()
        flash('Se clonó la preorden seleccionada. Ya puede modificar la preorden agregando, modificando o eliminando productos.')
        return redirect(url_for("auth.redirectlink"))
    return redirect(url_for("auth.redirectlink"))
