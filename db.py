import sqlite3
import click
from flask import current_app, g

def get_db():
    # Conecta a la base de datos configurada en la aplicacion. La conexion es unica
    # para cada solicitud y será reutilizada si es llamada nuevamente.
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    # Si esta solicitud se conecta a la base de datos, cierra la conexion.
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    # Borra datos existentes y crea nuevas tablas
    db = get_db()
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8'))

@click.command('init-db')
def init_db_command():
    # Borra datos existentes y crea nuevos tablas
    init_db()
    click.echo('Base de datos inicializada.')

def init_app(app):
    # Registra funciones de base de datos con la app Flask. Es llamada por la application factory.
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

