from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from .db import get_db
from .auth import login_required
from datetime import datetime
import pytz as tz

bp = Blueprint("upgrade_cabin", __name__)
current_campaign = 0
categorias_ordenadas = [
        "Standard Twin",
        "Standard Plus Twin",
        "Standard Plus Triple",
        "Superior Twin",
        "Premier Single",
        "Premier Twin",
        "Suite Twin"
    ]

@bp.route("/upgrade_cabin", methods=["GET", "POST"])
@login_required
def upgrade_cabin():
    db = get_db()
    # Obtener lista de pasajeros y cabinas para los selects
    passengers = db.execute("SELECT id_passenger, tx_name || ' ' || tx_surname AS name FROM bt_passenger").fetchall()
    cabins = db.execute("SELECT id_cabin, nu_cabin || ' - ' || tx_cabin_type AS cabin FROM lkp_cabins").fetchall()

    if request.method == "POST":
        id_passenger = request.form["id_passenger"]
        cabina_actual = request.form["cabina_actual"]
        cabina_upgrade = request.form["cabina_upgrade"]
        tipo_upgrade = request.form.get("tipo_upgrade", "normal")
        precio = 0 if tipo_upgrade == "critico" else request.form["precio"]
        fecha_upgrade = request.form["fecha_upgrade"]

        print(id_passenger, cabina_actual, cabina_upgrade, tipo_upgrade, precio, fecha_upgrade)

        # Insertar en la tabla de movimientos
        db.execute(
            "INSERT INTO mov_cabin_upgrades (passenger_id, from_cabin_id, to_cabin_id, upgrade_type, price, date) VALUES (?, ?, ?, ?, ?, ?)",
            (id_passenger, cabina_actual, cabina_upgrade, tipo_upgrade, precio, fecha_upgrade)
        )
        print("Insertado en mov_cabin_upgrades")
        # Actualizar la cabina ocupada en tabla de ocupaciones
        current_campaign = db.execute("SELECT MAX(id_campaign) as id FROM bt_cabin_occupation").fetchone()["id"]
        db.execute(
            "UPDATE bt_cabin_occupation SET id_cabin = ? WHERE id_passenger = ? AND id_campaign = ?",
            (cabina_upgrade, id_passenger, current_campaign)
        )
        db.commit()
        print("Actualizado en bt_cabin_occupation")
        #Añado el consumo en la bt_consumption e imprimo ticket
        add_consumption(id_passenger, precio)
        flash("Upgrade de cabina registrado correctamente.")
        return redirect(url_for("auth.redirectlink"))

    return render_template("passengers/upgrade_cabin.html", passengers=passengers, cabins=cabins)

def add_consumption(id_passenger, price):
    dtoday = datetime.now(tz.timezone('America/Argentina/Buenos_Aires')).replace(tzinfo=None)
    quantity = 1
    id_product = 1260 # Este es el id del producto de upgrade de cabina
    oper = session.get("user_id")
    db = get_db()
    db.execute("INSERT INTO bt_ticket_header (dt_ticket, id_passenger, id_user) VALUES (?,?,?)",
                (dtoday, id_passenger, oper),
                )
    db.commit()
    print("Insertado en bt_ticket_header")
    req_tkt = db.execute('SELECT MAX(id_ticket) AS mxm FROM bt_ticket_header;').fetchone()[0]
    db.execute("INSERT INTO bt_consumption (id_ticket, id_product, id_passenger, dt_consumption, nu_quantity, pc_unity) VALUES (?,?,?,?,?,?)",
                (req_tkt, id_product, id_passenger, dtoday, quantity, price),
                )
    db.commit()
    print("Añadido en bt_consumption")


def update_passenger_info(id_passenger, id_cabin):
    db = get_db()
    # 1. Obtener el valor actual de tx_password
    cur = db.execute("SELECT tx_password FROM bt_passenger WHERE id_passenger = ?", (id_passenger,))
    row = cur.fetchone()
    if row and row[0]:
        old_password = row[0]
        # 2. Extraer la parte después del arroba
        if '@' in old_password:
            password_suffix = old_password.split('@', 1)[1]
        else:
            password_suffix = old_password  # Por si no tiene arroba, se usa todo
        # 3. Construir el nuevo tx_password
        new_password = f"{id_cabin}@{password_suffix}"
        # 4. Hacer el UPDATE de ambos campos
        db.execute(
            "UPDATE bt_passenger SET id_cabin = ?, tx_password = ? WHERE id_passenger = ?",
            (id_cabin, new_password, id_passenger)
        )
    else:
        # Si no hay tx_password, solo actualiza id_cabin
        db.execute(
            "UPDATE bt_passenger SET id_cabin = ? WHERE id_passenger = ?",
            (id_cabin, id_passenger)
        )
    db.commit()
    print("Actualizado en bt_passenger")
    
    
@bp.route("/get_cabina_info", methods=["POST"])
@login_required
def get_cabina_info():
    db = get_db()
    id_passenger = request.form["id_passenger"]
    tipo_upgrade = request.form.get("tipo_upgrade", "normal")
    print("tipo_upgrade: ", tipo_upgrade)


    # 1) Cabina actual del pasajero (en campaña vigente) + tipo + nombre formateado
    row_actual = db.execute("""
        WITH cc AS (
          SELECT MAX(id_campaign) AS id FROM bt_cabin_occupation
        )
        SELECT
          o.id_cabin AS cabina_actual_id,
          c.tx_cabin_type AS cabina_actual_type,
          '(' || c.nu_cabin || ') ' || c.tx_cabin_type AS cabina_actual_name,
          cc.id AS current_campaign
        FROM cc
        LEFT JOIN bt_cabin_occupation o 
          ON o.id_campaign = cc.id AND o.id_passenger = ?
        LEFT JOIN lkp_cabins c 
          ON c.id_cabin = o.id_cabin
        LIMIT 1;
    """, (id_passenger,)).fetchone()

    current_campaign = row_actual["current_campaign"] if row_actual else None
    cabina_actual_id = row_actual["cabina_actual_id"] if row_actual and row_actual["cabina_actual_id"] is not None else None
    cabina_actual_type = row_actual["cabina_actual_type"] if row_actual and row_actual["cabina_actual_type"] is not None else None
    cabina_actual_name = row_actual["cabina_actual_name"] if row_actual and row_actual["cabina_actual_name"] is not None else None

    # 2) Cabinas con lugar disponible (capacidad_restante > 0) en campaña vigente
    #    Calculamos ocupados por cabina en una CTE y luego un LEFT JOIN con el catálogo.
    libres = db.execute("""
        WITH cc AS (
          SELECT MAX(id_campaign) AS id FROM bt_cabin_occupation
        ),
        occ AS (
          SELECT o.id_cabin, COUNT(*) AS ocupados
          FROM bt_cabin_occupation o, cc
          WHERE o.id_campaign = cc.id
          GROUP BY o.id_cabin
        )
        SELECT 
          c.id_cabin AS id,
          '(' || c.nu_cabin || ') ' || c.tx_cabin_type AS cabin,
          c.tx_cabin_type AS tipo,
          c.nu_capacity AS capacidad_total,
          COALESCE(occ.ocupados, 0) AS ocupados,
          (c.nu_capacity - COALESCE(occ.ocupados, 0)) AS capacidad_restante
        FROM lkp_cabins c
        LEFT JOIN occ ON occ.id_cabin = c.id_cabin
        WHERE (c.nu_capacity - COALESCE(occ.ocupados, 0)) > 0
        ORDER BY c.nu_cabin;
    """).fetchall()

    
    idx_actual = categorias_ordenadas.index(cabina_actual_type) if cabina_actual_type in categorias_ordenadas else 0

    libres_list = []
    for r in libres:
        print("r: ", r)
        print("cabina_actual_type: ", cabina_actual_type)
        tipo_cabina = r["tipo"]
        print("tipo_cabina: ", tipo_cabina)
        idx_cabina = categorias_ordenadas.index(tipo_cabina) if tipo_cabina in categorias_ordenadas else 0
        print("idx_cabina: ", idx_cabina)
        print("idx_actual: ", idx_actual)
        if tipo_upgrade == "critico" or idx_cabina >= idx_actual:
            libres_list.append({
                "id": r["id"],
                "cabin": r["cabin"],
                "capacidad_restante": r["capacidad_restante"],
                "capacidad_total": r["capacidad_total"]
            })

    print(libres_list)

    return jsonify({
        "cabina_actual_id": cabina_actual_id,
        "cabina_actual_type": cabina_actual_type,
        "cabina_actual_name": cabina_actual_name,
        "cabinas_libres": libres_list
    })

    '''
    # Serializar resultado
    libres_list = [{
        "id": r["id"],
        "cabin": r["cabin"],
        "capacidad_restante": r["capacidad_restante"],
        "capacidad_total": r["capacidad_total"]
    } for r in libres]

    return jsonify({
        "cabina_actual_id": cabina_actual_id,
        "cabina_actual_type": cabina_actual_type,
        "cabina_actual_name": cabina_actual_name,
        "cabinas_libres": libres_list
    })
    '''



@bp.route("/get_cabin_price_diff", methods=["POST"])
@login_required
def get_cabin_price_diff():
    precios_cabinas = {
        "Standard Twin": 0,
        "Standard Plus Twin": 1000,
        "Standard Plus Triple": 1000,
        "Superior Twin": 2000,
        "Premier Single": 3000,
        "Premier Twin": 3000,
        "Suite Twin": 4000
    }
    tipo_cabina_actual = request.form["tipo_cabina_actual"]
    tipo_cabina_upgrade = request.form["tipo_cabina_upgrade"]

    precio_actual = precios_cabinas.get(tipo_cabina_actual, 0)
    precio_upgrade = precios_cabinas.get(tipo_cabina_upgrade, 0)
    diferencia = max(0, precio_upgrade - precio_actual)

    return jsonify({"precio": diferencia})