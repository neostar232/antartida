from flask import Blueprint, request, jsonify
from .stock_service import add_stock, remove_stock

bp = Blueprint('stock_actual', __name__, url_prefix='/stock_actual')

@bp.route('/add', methods=['POST'])
def add_to_stock():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity')

    if not product_id or not quantity:
        return jsonify({'error': 'Faltan parámetros'}), 400

    stock = add_stock(product_id, quantity)
    return jsonify({'message': 'Stock actualizado', 'product_id': stock["product_id"], 'quantity': stock["quantity"]})


@bp.route('/remove', methods=['POST'])
def remove_from_stock():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity')

    if not product_id or not quantity:
        return jsonify({'error': 'Faltan parámetros'}), 400

    try:
        stock = remove_stock(product_id, quantity)
        return jsonify({'message': 'Stock actualizado', 'product_id': stock["product_id"], 'quantity': stock["quantity"]})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
