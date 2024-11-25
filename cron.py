import functools
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
# from werkzeug.exceptions import abort
from .auth import login_required
from .db import get_db
# from flask_login import logout_user
# from apscheduler.schedulers.background import BackgroundScheduler

# app = Flask(__name__)

bp = Blueprint("cron", __name__)


# Desconecto a los usuarios conectados
@bp.route("/cronx")
def cronx():
    # logout_user()
    flash('Por necesidad de resguardo de información, su usuario ha sido desconectado. Aguarde 5 minutos y vuelva a intentarlo.')
    return redirect(url_for("auth.redirectlink"))

# if __name__ == '__main__':
#     sched = BackgroundScheduler()
#     sched.add_job(func=cronx, trigger='interval', minutes = 2)
#     sched.start()
