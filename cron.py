import os
import zipfile as zp
from datetime import datetime
from os.path import basename

from flask import Blueprint, flash, redirect, url_for, session, current_app
from .auth import login_required

bp = Blueprint("cron", __name__)

@bp.route("/bkp/cronx")
@login_required
def cronx():
    session.clear()
    flash('Por necesidad de resguardo de información, su usuario ha sido desconectado. Aguarde 5 minutos y vuelva a conectarse.')
    app_root = current_app.root_path
    backup_dir_name = 'static/bkp'
    dirpath = os.path.join(app_root, backup_dir_name)
    os.makedirs(dirpath, exist_ok=True)
    filename = 'dbushuaia'+'_'+datetime.today().strftime("%Y%m%d")+'_'+datetime.today().strftime("%H%M%S")+'.zip'
    dirfile = os.path.join(dirpath, filename)
    db_filename = 'ushuaia.db'
    db_folder = 'db3'
    source = os.path.join(app_root, db_folder, db_filename)
    # Verifico que el archivo de origen existe antes de intentar hacer nada
    if not os.path.exists(source):
        flash(f'Error: El archivo de base de datos no se encontró en "{source}". No se pudo realizar la copia de seguridad.')
        current_app.logger.error(f'Intento de backup fallido: DB no encontrada en {source}')
        return redirect(url_for("auth.login"))
    try:
        with zp.ZipFile(dirfile, 'w') as zipObj:
            zipObj.write(source, arcname=db_filename) # arcname asegura que el nombre dentro del zip sea solo 'ushuaia.db'
        flash(f'Copia de seguridad "{filename}" creada con éxito.')
        current_app.logger.info(f'Backup exitoso: {dirfile}')
    except Exception as e:
        flash(f'Error al crear la copia de seguridad: {e}')
        current_app.logger.error(f'Error durante el backup a {dirfile}: {e}')
    return redirect(url_for("auth.login"))