import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, session, Response
from datetime import datetime
import pytz as tz
from .auth import login_required
from .db import get_db

# from escpos import BluetoothConnection
# from escpos.exceptions import NoDeviceError, USBNotFoundError, DeviceNotFoundError

# IMPORTANTE: Reemplaza esta dirección MAC con la de tu impresora
# Puedes encontrarla en la configuración del Bluetooth de tu dispositivo
PRINTER_BLUETOOTH_MAC = "00:01:90:AA:7E:79"

bp = Blueprint('print_module', __name__, url_prefix='/print_module')

# Función para verificar si el usuario ha iniciado sesión
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

def imprimir_ticket_por_mac(datos_ticket):
    """
    Función para imprimir un ticket en una impresora Bluetooth
    usando directamente su dirección MAC.
    """
    try:
        # Crea una instancia de la impresora Bluetooth, conectándose por MAC
        # Nota: La clase se llama directamente desde el módulo 'printer'
        p = BluetoothConnection(PRINTER_BLUETOOTH_MAC)

        # Imprime el ticket
        p.set(align="center", bold=True)
        p.text("Restaurante de Ejemplo\n")
        p.set(align="left", bold=False)
        p.text("--------------------------------\n")
        p.text(f"Pedido No: {datos_ticket['numero_pedido']}\n")
        p.text(f"Fecha: {datos_ticket['fecha']}\n")
        p.text("--------------------------------\n")
        
        for item in datos_ticket['items']:
            p.text(f"{item['cantidad']} x {item['nombre']}...{item['precio']:.2f}€\n")
        
        p.text("--------------------------------\n")
        p.set(align="right", bold=True)
        p.text(f"Total: {datos_ticket['total']:.2f}€\n")
        p.text("\n")
        p.set(align="center", bold=False)
        p.text("¡Gracias por tu visita!\n")
        p.text("\n\n")

        p.cut()
        
        # Es muy importante cerrar la conexión
        p.close()

        return "Ticket impreso correctamente", 200
    except NoDeviceError:
        return "Error: No se encontró la impresora Bluetooth. Verifica que esté encendida y enlazada.", 500
    except Exception as e:
        return f"Error al imprimir: {e}", 500

@bp.route('/show_ticket/<int:id_ticket>', methods=['GET'])
@login_required
def show_ticket_in_browser(id_ticket):
    """
    Esta ruta muestra el ticket en el navegador en formato de recibo.
    """
    print(f"DEBUG: Attempting to show ticket ID: {id_ticket} in browser.")
    try:
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
            (id_ticket,)
        ).fetchall()
        
        if not ticket_details:
            print(f"DEBUG: Ticket ID {id_ticket} not found.")
            return "Ticket not found.", 404
        
        header = {
            'id_ticket': ticket_details[0]['id_ticket'],
            'dt_ticket': ticket_details[0]['dt_ticket'],
            'passenger_name': ticket_details[0]['passenger_name'],
        }
        items_list = [
            {'product': row['product'], 'quantity': row['nu_quantity'], 'price': row['pc_unity']}
            for row in ticket_details if row['id_consumption'] is not None
        ]
        
        return render_template('print_module/recibo.html', header=header, items_list=items_list)
        
    except Exception as e:
        print(f"ERROR: Failed to get ticket data: {e}")
        return f"Server error: {e}", 500

@bp.route('/print_ticket_by_mac/<int:id_ticket>', methods=['GET'])
@login_required
def print_ticket_by_mac(id_ticket):
    """
    Esta ruta llama a la función de impresión Bluetooth por MAC.
    """
    print(f"DEBUG: Intentando imprimir ticket ID: {id_ticket} por MAC.")
    try:
        db = get_db()
        ticket_details = db.execute(
            """SELECT
                h.id_ticket AS numero_pedido,
                STRFTIME('%Y-%m-%d %H:%M',h.dt_ticket) AS fecha,
                p.tx_product AS nombre,
                c.nu_quantity AS cantidad,
                c.pc_unity AS precio
            FROM bt_ticket_header h
            LEFT JOIN bt_consumption c ON h.id_ticket = c.id_ticket
            LEFT JOIN bt_product p ON p.id_product = c.id_product
            WHERE h.id_ticket = ?
            ORDER BY c.id_consumption;""",
            (id_ticket,)
        ).fetchall()
        
        if not ticket_details:
            print(f"DEBUG: Ticket ID {id_ticket} no encontrado.")
            return {"message": "Ticket no encontrado"}, 404
        
        datos_ticket = {
            "numero_pedido": ticket_details[0]['numero_pedido'],
            "fecha": ticket_details[0]['fecha'],
            "items": [],
            "total": 0.0
        }
        
        for row in ticket_details:
            if row['nombre'] is not None:
                item_total = row['cantidad'] * row['precio']
                datos_ticket['items'].append({
                    "cantidad": row['cantidad'],
                    "nombre": row['nombre'],
                    "precio": row['precio']
                })
                datos_ticket['total'] += item_total
                
        # Llamar a la función de impresión por MAC
        mensaje, estado = imprimir_ticket_por_mac(datos_ticket)
        
        return {"message": mensaje}, estado

    except Exception as e:
        print(f"ERROR: Fallo al procesar la solicitud: {e}")
        return {"message": f"Error del servidor: {e}"}, 500