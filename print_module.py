import functools
from flask import Blueprint, render_template, url_for, Response, jsonify, request, current_app, session, g
from flask_weasyprint import HTML, render_pdf
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db

bp = Blueprint('print_module', __name__, url_prefix='/print_module')

# --- Función auxiliar para obtener los datos del ticket (OK) ---
def _get_ticket_data(ticket_id):
    db = get_db()
    ticket_details = db.execute(
        """SELECT
            h.id_ticket,
            STRFTIME('%Y-%m-%d %H:%M',h.dt_ticket) AS dt_ticket,
            h.id_passenger,
            pa.tx_name||' '||pa.tx_surname AS passenger_name,
            c.id_consumption,
            s.tx_subcategory||' -' || p.tx_product AS product,
            c.nu_quantity,
            c.pc_unity
        FROM bt_ticket_header h
        INNER JOIN bt_passenger pa ON pa.id_passenger = h.id_passenger
        LEFT JOIN bt_consumption c ON h.id_ticket = c.id_ticket
        LEFT JOIN bt_product p ON p.id_product = c.id_product
        LEFT JOIN lkp_subcategories s ON s.id_subcategory = p.id_subcategory
        WHERE h.id_ticket = ?
        ORDER BY c.id_consumption;""",
        (ticket_id,)
    ).fetchall()
    
    if not ticket_details:
        return None
    
    header = {
        'id_ticket': ticket_details[0]['id_ticket'],
        'dt_ticket': ticket_details[0]['dt_ticket'],
        'id_passenger': ticket_details[0]['id_passenger'],
        'passenger_name': ticket_details[0]['passenger_name'],
    }
    items = []
    total_amount = 0
    
    for row in ticket_details:
        if row['id_consumption'] is not None:
            item_total = row['nu_quantity'] * row['pc_unity']
            items.append({
                'product': row['product'],
                'quantity': row['nu_quantity'],
                'unit_price': row['pc_unity'],
                'total_price': item_total,
            })
            total_amount += item_total
            
    header['total_amount'] = total_amount
    
    return {'header': header, 'items': items}

# --- NUEVA FUNCIÓN: Obtiene la lista de tickets de un cliente ---
def _get_tickets_for_client(passenger_id):
    """Obtiene una lista de tickets con sus totales para un pasajero."""
    db = get_db()
    tickets = db.execute(
        """SELECT
            h.id_ticket,
            STRFTIME('%Y-%m-%d %H:%M', h.dt_ticket) AS dt_ticket,
            pa.tx_name||' '||pa.tx_surname AS passenger_name,
            SUM(c.nu_quantity * c.pc_unity) AS total_amount
        FROM bt_ticket_header h
        INNER JOIN bt_passenger pa ON pa.id_passenger = h.id_passenger
        LEFT JOIN bt_consumption c ON h.id_ticket = c.id_ticket
        WHERE h.id_passenger = ?
        GROUP BY h.id_ticket
        ORDER BY h.dt_ticket DESC;""",
        (passenger_id,)
    ).fetchall()
    return tickets


# --- RUTAS DE BÚSQUEDA Y ESTADO DE CUENTA ---

# (Esta ruta ya la tenías)
@bp.route('/search_passenger', methods=['GET', 'POST'])
@login_required
def search_passenger():
    """
    Ruta para buscar un pasajero y ver su estado de cuenta.
    """
    if request.method == 'POST':
        query = request.form['query']
        db = get_db()
        passengers = db.execute(
            """SELECT id_passenger, tx_name, tx_surname
            FROM bt_passenger
            WHERE tx_name LIKE ? OR tx_surname LIKE ? OR id_passenger = ?
            ORDER BY tx_name""",
            ('%' + query + '%', '%' + query + '%', query)
        ).fetchall()
        return render_template('print_module/search_passenger.html', passengers=passengers, query=query)
    
    return render_template('print_module/search_passenger.html', passengers=None)

# --- NUEVA RUTA: Muestra la página completa del estado de cuenta ---
@bp.route('/estado_de_cuenta/<int:passenger_id>')
@login_required
def client_account_statement(passenger_id):
    """
    Ruta principal para ver el estado de cuenta de un cliente.
    Muestra la lista de tickets y permite ver el detalle.
    """
    tickets = _get_tickets_for_client(passenger_id)
    return render_template('print_module/account_statement.html', tickets=tickets, passenger_id=passenger_id)

# --- NUEVA RUTA: Retorna el fragmento HTML para HTMX ---
@bp.route('/htmx/get_ticket_details/<int:ticket_id>')
@login_required
def get_ticket_details_htmx(ticket_id):
    """
    Ruta para obtener los detalles de un ticket como un fragmento HTML para htmx.
    """
    ticket_data = _get_ticket_data(ticket_id)
    if not ticket_data:
        return "Ticket no encontrado o sin detalles.", 404

    return render_template('print_module/ticket_details_htmx.html', ticket_data=ticket_data)


# --- RUTAS DE IMPRESIÓN (OK) ---

@bp.route('/get_ticket_details_for_print', methods=["GET"])
@login_required
def get_ticket_details_for_print():
    ticket_id = request.args.get('ticket_id', type=int)
    if not ticket_id:
        return jsonify({"message": "Falta el ID del ticket"}), 400
    ticket_data = _get_ticket_data(ticket_id)
    if not ticket_data:
        return jsonify({"message": "Ticket no encontrado o sin detalles."}), 404
    return jsonify(ticket_data)

@bp.route("/generate_ticket_txt/<int:ticket_id>")
@login_required
def generate_ticket_txt(ticket_id):
    ticket_data = _get_ticket_data(ticket_id)
    if not ticket_data:
        return jsonify({"message": "Ticket no encontrado o sin detalles."}), 404
    header = ticket_data['header']
    items = ticket_data['items']
    content = ""
    content += "--------------------------------------\n"
    content += "           TICKET DE COMPRA           \n"
    content += "--------------------------------------\n"
    content += f"Ticket ID: {header['id_ticket']}\n"
    content += f"Fecha: {header['dt_ticket']}\n"
    content += f"Pasajero: {header['passenger_name']}\n"
    content += "--------------------------------------\n"
    content += "CANT.  DESCRIPCION            PRECIO\n"
    content += "--------------------------------------\n"
    for item in items:
        product_str = item['product'][:20].ljust(20)
        quantity_str = str(item['quantity']).ljust(6)
        price_str = f"{item['total_price']:.2f}".rjust(8)
        content += f"{quantity_str} {product_str} {price_str}\n"
    content += "--------------------------------------\n"
    content += f"TOTAL: {header['total_amount']:.2f}\n"
    content += "--------------------------------------\n"
    content += "\n  ¡Gracias por su preferencia!\n"
    response = Response(content, mimetype="text/plain")
    response.headers["Content-Disposition"] = f"attachment; filename=ticket_{ticket_id}.txt"
    return response

@bp.route("/generate_ticket_pdf/<int:ticket_id>")
@login_required
def generate_ticket_pdf(ticket_id):
    ticket_data = _get_ticket_data(ticket_id)
    if not ticket_data:
        return jsonify({"message": "Ticket no encontrado o sin detalles."}), 404
    rendered_html = render_template(
        'print_module/ticket_pdf_template.html',
        ticket=ticket_data['header'],
        items=ticket_data['items'],
        passenger_name=ticket_data['header']['passenger_name']
    )
    return render_pdf(HTML(string=rendered_html))

@bp.route('/print_ticket_page/<int:ticket_id>')
@login_required
def print_ticket_page(ticket_id):
    return render_template('print_module/print_ticket.html', ticket_id=ticket_id)