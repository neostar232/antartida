from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

"""
product_id se enlaza con la tabla Product para saber a qué producto pertenece el stock, 
quantity almacena el stock actual, y 
last_updated guarda la última actualización.
"""

class StockActual(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('bt_product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    last_updated = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    #product = db.relationship('Product', backref='stock_actual', lazy=True)