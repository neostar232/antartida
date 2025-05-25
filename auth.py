import functools
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import datetime as dt
from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")

def login_required(view):
    """View decorator that redirects anonymous users to the login page."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(**kwargs)
    return wrapped_view


@bp.before_app_request
def load_logged_in_user():
    # Si el user_id es almacenado en la sesion, carga al usuario en g.user desde la base de datos
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = (
            get_db().execute("SELECT * FROM bt_users WHERE fl_active = 1 AND id_user = ?", (user_id,)).fetchone()
        )


# Registro de usuario nuevo (a definir acciones)
@bp.route("/register", methods=("GET", "POST"))
def register():
    # Registra un nuevo usuario.
    # Valida que el nombre de usuario no haya sido tomado con anterioridad.
    # Enmascara la psw por seguridad y la guarda en la bd
    if request.method == "POST":
        tx_mail = request.form["tx_mail"]
        tx_name = request.form["nyap"]
        password = request.form["password"]
        id_role = request.form["rol_user"]
        db = get_db()
        error = None
        if not tx_mail:
            error = "El usuario es requerido."
        elif not tx_name:
            error = "El nombre y apellido es obligatorio."
        elif not password:
            error = "La contraseña es obligatoria."
        elif not id_role:
            error = "El rol es indispensable."
        if error is None:
            try:
                db.execute(
                    "INSERT INTO bt_users (tx_mail, tx_name, tx_psw, id_role) VALUES (?, ?, ?, ?)",
                    (tx_mail, tx_name, generate_password_hash(password), id_role),
                )
                db.commit()
            except db.IntegrityError:
                # Si el usuario existe, muestra el error
                error = f"El usuario {tx_mail} ya se encuentra registrado."
            else:
                # Si no existe, crea y redirecciona al panel principal
                flash('El usuario fue creado exitosamente')
                return redirect(url_for("auth.redirectlink"))
        flash(error)
    return render_template("auth/register.html")


# Acceso de usuario segun rol definido en el alta
@bp.route("/login", methods=("GET", "POST"))
def login():
    """Log in de usuario y agregado de user + rol al objeto session."""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()
        error = None
        user = db.execute(
            "SELECT * FROM bt_users WHERE tx_mail = ?", (username,)
        ).fetchone()
        if user is None:
            error = "Usuario Incorrecto."
        elif not check_password_hash(user['tx_psw'], password):
            error = "PSW Incorrecta."
        # Chequeo el rol del usuario y accedo en consecuencia
        if error is None and (user['id_role'] ==1):
            # Almacena el usuario en una nueva sesion y regresa al index
            session.clear()
            session['user_id'] = user['id_user']
            session['role'] = user['id_role']
            # Agrego el ingreso a la tabla de sesiones
            db.execute("INSERT INTO bt_sessions(id_user, dt_session_in) VALUES (?,?)", (session['user_id'], dt.datetime.now()))
            db.commit()
            return redirect(url_for("reports.panel"))
        if error is None and (user['id_role'] == 2):
            # Almacena el usuario en una nueva sesion y regresa al index
            session.clear()
            session['user_id'] = user['id_user']
            session['role'] = user['id_role']
            # Agrego el ingreso a la tabla de sesiones
            db.execute("INSERT INTO bt_sessions(id_user, dt_session_in) VALUES (?,?)", (session['user_id'], dt.datetime.now()))
            db.commit()
            return redirect(url_for("reports.panelb")) # --> micropanel
        if error is None and (user['id_role'] == 5):
            # Almacena el usuario en una nueva sesion y regresa al index
            session.clear()
            session['user_id'] = user['id_user']
            session['role'] = user['id_role']
            # Agrego el ingreso a la tabla de sesiones
            db.execute("INSERT INTO bt_sessions(id_user, dt_session_in) VALUES (?,?)", (session['user_id'], dt.datetime.now()))
            db.commit()
            return redirect(url_for("reports.panelpv")) # --> micropanel
        flash(error)
    return render_template("auth/login.html")

# De acuerdo al rol definido para el usuario, lo envio al panel al que debe acceder
@bp.route("/redirectlink")
def redirectlink():
        rolx = session.get("role")
        error = None
        if error is None and rolx == 1:
            return redirect(url_for("reports.panel"))
        if error is None and rolx == 2:
            return redirect(url_for("reports.panelb"))
        if error is None and rolx == 5:
            return redirect(url_for("reports.panelpv"))


@bp.route("/logout")
def logout():
    # Actualizo registro de sesiones
    db = get_db()
    db.execute("UPDATE bt_sessions SET dt_session_out = ? WHERE id_user = ? AND dt_session_out IS NULL",
               (dt.datetime.now(), session["user_id"])
               )
    db.commit()
    # Limpia la session corriente, incluyendo el user_id
    session.clear()
    # return render_template("auth/login.html")
    return redirect(url_for("auth.login"))


# Dirijo el enlace hacia el alta de un nuevo usuario
@bp.route("/go_create_user", methods=("GET", "POST"))
@login_required
def go_create_user():
     db = get_db()
     roles = db.execute("SELECT * FROM lkp_roles ORDER BY tx_desc_role").fetchall()
     return render_template('auth/register.html', roles = roles)


# Dirijo el enlace hacia la baja logica de usuario
@bp.route("/go_del_user", methods=("GET", "POST"))
@login_required
def go_del_user():
     db = get_db()
     uact = session.get("user_id") # Evito que el usuario actual se elimine
     duser = db.execute("SELECT * FROM bt_users WHERE fl_active = 1 AND id_user <> (?) ORDER BY tx_name", (uact,))
     db.commit()
     return render_template('auth/del_user.html', duser = duser)


# Eliminacion logica de usuario
@bp.route("/del_user", methods=("GET", "POST"))
@login_required
def del_user():
    if request.method == "POST":
        utd = request.form["sel_user"]
        db = get_db()
        db.execute("UPDATE bt_users SET fl_active = 0 WHERE id_user = (?)", (utd,))
        db.commit()
        flash('El usuario fue dado de baja exitosamente!')
        return redirect(url_for("auth.redirectlink"))


# Dirijo el enlace hacia modificacion del usuario
@bp.route("/go_mod_user", methods=("GET", "POST"))
@login_required
def go_mod_user():
    db = get_db()
    uact = session.get("user_id") 
    duser = db.execute("SELECT * FROM bt_users WHERE id_user <> (?) ORDER BY tx_name", (uact,))
    db.commit()
    return render_template('auth/go_mod_user.html', duser = duser)


# Selecciono el usuario a modificar
@bp.route("/sel_mod_user", methods=("GET", "POST"))
@login_required
def sel_mod_user():
    if request.method == "POST":
        utd = request.form["sel_user"]
        db = get_db()
        selus = db.execute("SELECT * FROM bt_users WHERE id_user = (?)", (utd,))
        roles = db.execute("SELECT * FROM lkp_roles")
        db.commit()
        return render_template('auth/mod_user.html', selus = selus, roles = roles)


# Modifico al usuario
@bp.route("/mod_user", methods=("GET", "POST"))
@login_required
def mod_user():
    if request.method == "POST":
        tx_mail = request.form["tx_nnu"]
        tx_name = request.form["tx_nnn"]
        password = request.form["tx_npsw"]
        id_role = request.form["sel_rol"]
        id_user = request.form["ids"]
        db = get_db()
        error = None
        if not tx_mail:
            error = "El usuario es requerido."
        elif not tx_name:
            error = "El nombre y apellido es obligatorio."
        elif not password:
            error = "La contraseña es obligatoria."
        elif not id_role:
            error = "El rol es indispensable."
        if error is None:
            try:
                db.execute("UPDATE bt_users SET tx_mail = ?, tx_name = ?, tx_psw = ?, id_role = ?, fl_active = 1 WHERE id_user = ?",
                    (tx_mail, tx_name, generate_password_hash(password), id_role, id_user),
                    )
                db.commit()
            except db.IntegrityError:
                # Si el usuario existe, muestra el error
                error = f"El nombre de usuario {tx_mail} ya se encuentra utilizado."
            else:
                # Si no existe, crea y redirecciona al panel principal
                flash('Usuario modificado')
                return redirect(url_for("auth.redirectlink"))
        flash(error)
    return render_template("auth/register.html")


