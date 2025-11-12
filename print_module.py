import functools
import pandas as pd
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, session
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db

bp = Blueprint('print_module', __name__, url_prefix='/print_module')


query_ticket = """
            SELECT
                c.id_ticket,
                STRFTIME('%Y-%m-%d %H:%M', c.dt_consumption) AS dt_consumption,
                p.tx_name||' '||p.tx_surname AS pasajero,
                SUM(c.nu_quantity*c.pc_unity) AS full_consumption
            FROM bt_consumption c INNER JOIN bt_passenger p
            ON c.id_passenger = p.id_passenger
            INNER JOIN lkp_campaign n
            ON p.id_campaign = n.id_campaign
            WHERE c.flag_anullment = 0
            AND n.flag_vigency = 1
            GROUP BY 1, 2, 3
            ORDER BY 3, 2, 1;
            """

@bp.route('/show_ticket/<int:id_ticket>', methods=['GET'])
@login_required
def print_ticket(id_ticket):
    """
    Tomo el 'id_ticket' de la URL, consulto a la base de datos para obtener
    los datos completos del ticket y los paso a la plantilla.
    """
    origin = request.args.get('origin')
    db = get_db()
    # 1. Obtengo los datos del encabezado del ticket
    get_head = f"""
            SELECT
                id_ticket,
                STRFTIME('%Y-%m-%d %H:%M', dt_ticket) AS dt_ticket,
                id_passenger
            FROM bt_ticket_header WHERE id_ticket = ?;
            """
    ticket_header = db.execute(get_head, (id_ticket,)).fetchone()
    if not ticket_header:
        flash("Ticket no encontrado.")
        return redirect(url_for('auth.redirectlink'))
    # 2. Obtengo los detalles de los consumos del ticket
    get_cmpt = f"""
            SELECT
                c.id_product,
                d.producto,
                c.nu_quantity,
                c.pc_unity,
                c.nu_quantity * c.pc_unity AS total_price
            FROM bt_consumption c INNER JOIN 
            (
            SELECT
                b.id_product,
                s.tx_subcategory ||' '|| b.tx_product AS producto
            FROM bt_product b INNER JOIN lkp_subcategories s
            ON b.id_subcategory = s.id_subcategory
            WHERE b.flag_ctrl = 1

            UNION

            SELECT
                id_drink AS id_product,
                'Trago - '|| tx_drink AS producto
            FROM lkp_drinks
            WHERE flag_available = 1) d
            ON c.id_product = d.id_product
            WHERE id_ticket = ?;
            """
    consumptions = db.execute(get_cmpt,(id_ticket,)).fetchall()
    
    # Obtengo nombre del pasajero y cabina
    get_psg = f"""
            SELECT
                p.tx_name||' ' ||p.tx_surname AS pasajero
            FROM bt_passenger p INNER JOIN lkp_cabins c
            ON p.id_cabin = c.id_cabin
            WHERE p.id_passenger = ?;
            """
    passenger = db.execute(get_psg, (ticket_header['id_passenger'],)).fetchone()
    total_amount = sum(row['nu_quantity'] * row['pc_unity'] for row in consumptions)
    # Formateo los datos para la plantilla
    ticket_data = {
        "numero_ticket": ticket_header['id_ticket'],
        "fecha": ticket_header['dt_ticket'],
        "pasajero": passenger['pasajero'],
        "consumos": [
            {"item": f" {item['producto']}", "cantidad": item['nu_quantity'], "precio": item['total_price']}
            for item in consumptions
        ],
        "total": total_amount
    }
    if origin == 'reprint':
        return render_template('print_module/reprint_ticket.html', ticket=ticket_data)
    else:
        return render_template('print_module/print_ticket.html', ticket=ticket_data)
    # return render_template('print_module/print_ticket.html', ticket=ticket_data)


# Muestra la lista de tickets para seleccionar uno para su reimpresión
@bp.route('/print_module/reprint', methods=['GET'])
@login_required
def sel_ticket_reprint():
    db = get_db()
    tickets = db.execute(query_ticket).fetchall()
    if len(tickets) < 1:
        flash('No se han emitido tickets aún para este viaje.')
        return redirect(url_for("auth.redirectlink"))
    return render_template('print_module/sel_ticket_reprint.html', tickets=tickets)
