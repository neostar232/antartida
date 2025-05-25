import functools
import datetime as dt
from os.path import basename
import zipfile as zp
from flask import Blueprint, flash, g, redirect, url_for, session
# from werkzeug.exceptions import abort
from .auth import login_required
# from .db import get_db
# from celery import Celery
from datetime import datetime
# from apscheduler.schedulers.background import BackgroundScheduler

bp = Blueprint("cron", __name__)


# Desconecto a los usuarios conectados y compacto base, con nombre del momento en que realizo la accion
@bp.route("/bkp/cronx")
@login_required
def cronx():
    session.clear()
    flash('Por necesidad de resguardo de información, su usuario ha sido desconectado. Aguarde 5 minutos y vuelva a conectarse.')
    # dirpath = '//media/marcelo/webs/antartica_v2/static/bkp/'
    dirpath = '//media/marcelo/500Mec/webs/ushuaia/static/bkp/'
    filename = 'dbushuaia'+'_'+datetime.today().strftime("%Y%m%d")+'_'+datetime.today().strftime("%H%M%S")+'.zip'
    dirfile = dirpath+filename
    # source = '//media/marcelo/webs/antartica_v2/db3/ushuaia.db'
    source = '//media/marcelo/500Mec/webs/ushuaia/db3/ushuaia.db'
    with zp.ZipFile(dirfile, 'w') as zipObj:
        zipObj.write(source, basename(source))
    return redirect(url_for("auth.redirectlink"))


# sched = BackgroundScheduler()
# sched.add_job(func=cronx, trigger='interval', minutes = 2)
# sched.start()
