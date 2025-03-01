import os
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from . import stock_controller

#db = SQLAlchemy()
#migrate = Migrate()

def create_app(test_config=None):
    # Crea y configura una instancia de la aplicacion Flask
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_mapping(
        SECRET_KEY='ysemarchoyasubarcolellamolibertad',  
        DATABASE = os.path.join(app.root_path, 'db3', 'ushuaia.db'),
        #SQLALCHEMY_TRACK_MODIFICATIONS=False,  # Evita warnings innecesarios
    )
    #app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(app.root_path, 'db3', 'ushuaia.db')}"
    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)
    # asegurarse que la carpeta de la instancia existe
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    @app.route("/")
    def index():
        return redirect(url_for('auth.login'))

    from . import db
    db.init_app(app)

    #migrate.init_app(app, db)  # Inicializar Flask-Migrate

    # Aplicando los Blueprints a la app
    from . import auth, reports, suppliers, stock, config_vs, orders, cron
    
    app.register_blueprint(auth.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(suppliers.bp)
    app.register_blueprint(stock.bp)
    app.register_blueprint(config_vs.bp)
    app.register_blueprint(orders.bp)
    app.register_blueprint(cron.bp)
    app.register_blueprint(stock_controller.bp)
    app.add_url_rule("/", endpoint="index")
    return app
