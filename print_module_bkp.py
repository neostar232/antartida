import functools
from flask import Blueprint, render_template, url_for, Response, jsonify, request, current_app, session, g
from flask_weasyprint import HTML, render_pdf
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db

bp = Blueprint('print_module', __name__, url_prefix='/print_module')

# --- Función auxiliar para obtener los datos del ticket ---
# Esta función NO es una vista, por lo que puede ser llamada desde cualquier otra función.
# Se encarga de toda la lógica de la base de datos y el procesamiento de los datos.
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

# ---
# Rutas
# ---

@bp.route('/get_ticket_details_for_print', methods=["GET"])
@login_required
def get_ticket_details_for_print():
    """
    Ruta para obtener los detalles de un ticket como JSON. 
    Ideal para usar con JavaScript (por ejemplo, con fetch API).
    """
    # Se espera que el ID del ticket se pase como un parámetro de consulta
    ticket_id = request.args.get('ticket_id', type=int)
    if not ticket_id:
        return jsonify({"message": "Falta el ID del ticket"}), 400
    
    ticket_data = _get_ticket_data(ticket_id)
    
    if not ticket_data:
        return jsonify({"message": "Ticket no encontrado o sin detalles."}), 404
        
    return jsonify(ticket_data)


@bp.route("/generate_ticket_pdf/<int:ticket_id>")
@login_required
def generate_ticket_pdf(ticket_id):
    """
    Ruta para generar el PDF de un ticket.
    """
    # Llama a la función auxiliar para obtener los datos
    ticket_data = _get_ticket_data(ticket_id)
    
    if not ticket_data:
        return jsonify({"message": "Ticket no encontrado o sin detalles."}), 404
    
    # Renderizo la plantilla HTML específica para el PDF
    rendered_html = render_template(
        'print_module/ticket_pdf_template.html',
        ticket=ticket_data['header'], # Datos del encabezado del ticket
        items=ticket_data['items'], # Detalles de los items del ticket
        passenger_name=ticket_data['header']['passenger_name']
    )
    
    # Convertir el HTML renderizado a PDF usando flask_weasyprint.
    return render_pdf(HTML(string=rendered_html))


@bp.route('/print_ticket_page/<int:ticket_id>')
@login_required
def print_ticket_page(ticket_id):
    """
    Ruta para renderizar la página HTML que contiene un botón para imprimir el ticket.
    """
    return render_template('print_module/print_ticket.html', ticket_id=ticket_id)