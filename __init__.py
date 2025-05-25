import os
from flask import Flask, redirect, url_for, request, session
import datetime as dt
import fnmatch

def create_app(test_config=None):
    # Crea y configura una instancia de la aplicacion Flask
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_mapping(
        SECRET_KEY='ysemarchoyasubarcolellamolibertad',  
        # DATABASE = os.path.join(app.root_path, 'db3', 'ushuaia.db'),
        DATABASE = os.path.join(app.root_path, 'db3', 'ushuaia_desa.db'),
    )
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


    from .db import get_db


    # Quito la posibilidad de hacer seguimiento por logueo
    # @app.after_request
    # def log_visit(response):
    #    db = get_db()
    #    url = request.url
    #    link_to_del = ['edirectlink', 'static'] # Con static en la lista, no se accede al ccs
    #    res = any(elem in url for elem in link_to_del)
    #    if res == False:
    #        db.execute("INSERT INTO logs(dt_log, id_object, id_user) VALUES (?,?,?)", (dt.datetime.now(), url, session.get("user_id")))
    #        db.commit()
    #        return response
    #    else:
    #        None


    @app.before_request
    def log_visit():
        db = get_db()
        url = request.url
        if request.endpoint and 'static' not in request.endpoint and not request.path.endswith('redirectlink') and not request.path.endswith('htmx') and not request.path.split('/')[-1].startswith('pane'):
        # if request.endpoint and 'static' not in request.endpoint and not request.path.endswith('redirectlink') and not (request.path.endswith('panel') or request.path.split('/')[-1].startswith('pane')):
            db.execute("INSERT INTO logs(dt_log, id_object, id_user) VALUES (?,?,?)", (dt.datetime.now(), url, session.get("user_id")))
            db.commit()
        else:
            None



    # Aplicando los Blueprints a la app
    from . import auth, reports, suppliers, stock, config_vs, orders, cron, bar_sp, consumption
    
    app.register_blueprint(auth.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(suppliers.bp)
    app.register_blueprint(stock.bp)
    app.register_blueprint(config_vs.bp)
    app.register_blueprint(orders.bp)
    app.register_blueprint(cron.bp)
    app.register_blueprint(bar_sp.bp)
    app.register_blueprint(consumption.bp)
    app.add_url_rule("/", endpoint="index")
    return app
