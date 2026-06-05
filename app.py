import os, sys, uuid, shutil
from pathlib import Path
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session, send_file, flash)

# Asegurar que parser.py y generator.py están en el path
sys.path.insert(0, str(Path(__file__).parent))
from parser import parse_and_merge
from generator import make_html, render as gen_render

# ─── CONFIG ──────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambiar-en-produccion-12345")

UPLOAD_FOLDER = Path("uploads")
OUTPUT_FOLDER = Path("outputs")
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

# Usuarios: variable de entorno USERS = "francisco:pass1,empleado1:pass2,empleado2:pass3"
def get_users():
    raw = os.environ.get("USERS", "francisco:quick2024,empleado1:seguro2024,empleado2:cotiza2024")
    users = {}
    for pair in raw.split(","):
        if ":" in pair:
            u, p = pair.strip().split(":", 1)
            users[u.strip()] = p.strip()
    return users

# ─── AUTH ────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "").strip()
        users = get_users()
        if users.get(usuario) == password:
            session["user"] = usuario
            return redirect(url_for("index"))
        error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ─── MAIN ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    return render_template("index.html", user=session["user"])

@app.route("/generar", methods=["POST"])
@login_required
def generar():
    files = request.files.getlist("pdfs")
    files = [f for f in files if f and f.filename]

    if not files:
        flash("Por favor subí al menos un PDF.", "error")
        return redirect(url_for("index"))
    if len(files) > 6:
        flash("Máximo 6 PDFs por cotización.", "error")
        return redirect(url_for("index"))

    # Guardar PDFs temporalmente
    session_id = str(uuid.uuid4())[:8]
    tmp_dir = UPLOAD_FOLDER / session_id
    tmp_dir.mkdir()

    pdf_paths = []
    for f in files:
        dest = tmp_dir / f.filename
        f.save(dest)
        pdf_paths.append(str(dest))

    try:
        # Parsear y mergear
        client_name, vehicle_banner, rows, has_tr = parse_and_merge(pdf_paths)

        # Override manual si el usuario lo editó
        manual_name    = request.form.get("nombre_cliente", "").strip()
        manual_vehicle = request.form.get("vehiculo", "").strip()
        if manual_name:
            client_name = manual_name
        if manual_vehicle:
            vehicle_banner = manual_vehicle.upper()

        # Generar imagen
        out_filename = f"cotizacion_{session_id}.png"
        out_path = str(OUTPUT_FOLDER / out_filename)
        html = make_html(client_name, vehicle_banner, rows, has_tr=has_tr)
        gen_render(html, out_path)

        # Guardar en sesión para descarga
        session["last_output"]   = out_filename
        session["last_client"]   = client_name
        session["last_vehicle"]  = vehicle_banner

        return render_template("resultado.html",
                               user=session["user"],
                               client_name=client_name,
                               vehicle=vehicle_banner,
                               out_filename=out_filename)

    except Exception as e:
        flash(f"Error al procesar los PDFs: {e}", "error")
        return redirect(url_for("index"))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.route("/preview/<filename>")
@login_required
def preview(filename):
    path = OUTPUT_FOLDER / filename
    if not path.exists():
        return "Not found", 404
    return send_file(str(path), mimetype="image/png")

@app.route("/descargar/<filename>")
@login_required
def descargar(filename):
    path = OUTPUT_FOLDER / filename
    if not path.exists():
        flash("El archivo ya no está disponible.", "error")
        return redirect(url_for("index"))
    client = session.get("last_client", "cotizacion")
    download_name = f"QuickSeguro_{client.split(',')[0].strip()}.png"
    return send_file(str(path), as_attachment=True, download_name=download_name)

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
