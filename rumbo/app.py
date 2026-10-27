"""
Rumbo - Sistema de gestión y reserva de paquetes turísticos
Universidad Cooperativa de Colombia - Ingeniería de Sistemas

Alcance de esta entrega: los 21 primeros requerimientos funcionales del documento (RF-01 a RF-21).
Módulos construidos hasta ahora:
  - Acceso: RF-01 (registro del cliente; el administrador entra con cuenta de la agencia + token) y RF-02 (autenticación).
  - Cuenta: RF-03 (recuperar contraseña) y RF-04 (editar perfil).
  - Destinos y paquetes: RF-05 (buscar destinos), RF-06 (filtrar paquetes), RF-07 (detalle del
    paquete), RF-08 (comparar paquetes) y RF-09 (disponibilidad de cupos por fecha).
  - Reservas: RF-10 (reservar), RF-11 (servicios adicionales), RF-12 (código de confirmación),
    RF-13 (cancelar), RF-14 (modificar fecha) y RF-15 (aviso de confirmación).
  - Pagos y comprobantes: RF-16 (pago en línea), RF-17 (pago en cuotas), RF-18 (comprobante en
    PDF) y RF-19 (validar cupo antes de confirmar el pago).
  - Después del viaje: RF-20 (calificar y comentar) y RF-21 (chat de soporte con un asesor).

Segunda entrega (en construcción): se agregan 7 requerimientos más (RF-22 a RF-28) mientras se
siguen corrigiendo observaciones sobre los 21 anteriores.
  - RF-22: notificar al cliente cuando cambia el itinerario de un paquete que ya reservó.
  - RF-23: el administrador crea, edita y elimina (desactiva) paquetes turísticos.
  - RF-24: el administrador genera reportes de ventas por período.
  - RF-25: el administrador gestiona el inventario de proveedores (hoteles, restaurantes).
  - RF-26: el cliente consulta los países disponibles como destinos turísticos.
  - RF-27: el cliente filtra los destinos turísticos por región.
  - RF-28: el cliente busca paquetes turísticos escribiendo el nombre de un destino (ya cubierto
    por el buscador de RF-06, que compara también contra el nombre del destino).
"""
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "turismo.db")

app = Flask(__name__)
# En producción define SECRET_KEY como variable de entorno.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "clave-de-desarrollo-cambiar")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

APP_NOMBRE = "Rumbo"

# Textos y datos propios de cada tipo de usuario
ROLES = {
    "cliente": {
        "singular": "cliente",
        "titular": "Elige tu destino, reserva y viaja",
        "bajada": "Explora paquetes, reserva con tu fecha y número de personas, "
                  "paga en línea y sigue el estado de cada viaje.",
        "panel": "panel_cliente",
    },
    "administrador": {
        "singular": "administrador",
        "titular": "Toda la oferta turística, bajo control",
        "bajada": "Gestiona paquetes, cupos, promociones y clientes, y consulta "
                  "reportes para decidir con datos.",
        "panel": "panel_admin",
    },
}

RESET_MINUTOS_VALIDEZ = 30

# ---------------------------------------------------------------------------
# Cuentas de administrador: NO existe registro público.
# La agencia crea la cuenta inicial y entrega al encargado (1) el correo y la
# contraseña ya establecidos y (2) el token de acceso de la agencia, que se pide
# en cada inicio de sesión como administrador. En producción defínelos como
# variables de entorno (ADMIN_TOKEN, ADMIN_CORREO, ADMIN_PASSWORD).
# ---------------------------------------------------------------------------
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "RUMBO-AGENCIA-2026")
ADMIN_CORREO_INICIAL = os.environ.get("ADMIN_CORREO", "admin@rumbo.com")
ADMIN_PASSWORD_INICIAL = os.environ.get("ADMIN_PASSWORD", "Rumbo2026Admin")
ADMIN_NOMBRE_INICIAL = ("Encargado", "de la Agencia")

# ---------------------------------------------------------------------------
# Fotos de los destinos (Wikimedia Commons, licencias Creative Commons).
# Si existe un archivo static/img/destinos/<nombre-del-destino>.jpg (o png/webp)
# se usa ese en lugar de la URL guardada en la base de datos.
# ---------------------------------------------------------------------------
_COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/"
FOTOS_DESTINOS = {
    "Cartagena de Indias": "70 - Carthagène - Décembre 2008.jpg",
    "Eje Cafetero": "Valle de Cocora, Colombia 04.jpg",
    "San Andrés": "Johnny Cay (8304072347).jpg",
    "Tayrona y Sierra Nevada": "Arrecifes.jpg",
    "Cusco y Machu Picchu": "80 - Machu Picchu - Juin 2009 - edit.jpg",
    "Ciudad de México": "Federal District buildings on Zocalo Mexico City.jpg",
}


def url_commons(archivo):
    from urllib.parse import quote
    return _COMMONS + quote(archivo.replace(" ", "_")) + "?width=900"


def _slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def foto_destino(nombre, guardada=""):
    """URL de la foto de un destino: archivo local si existe, si no la guardada."""
    slug = _slug(nombre)
    for ext in ("jpg", "jpeg", "png", "webp"):
        if os.path.exists(os.path.join(BASE_DIR, "static", "img", "destinos", f"{slug}.{ext}")):
            return url_for("static", filename=f"img/destinos/{slug}.{ext}")
    return guardada or ""


# ---------------------------------------------------------------------------
# Catálogo del módulo de destinos, paquetes y reservas (RF-05 a RF-21)
# ---------------------------------------------------------------------------
CATEGORIAS = {
    "playa": "Playa",
    "aventura": "Aventura",
    "cultural": "Cultural",
    "naturaleza": "Naturaleza",
}
TIPOS_SERVICIO = {
    "seguro": "Seguro de viaje",
    "transporte": "Transporte",
    "tour": "Tour guiado",
}
CUOTAS_DISPONIBLES = [1, 3, 6, 12]

# Tipos de documento aceptados para registrar a las personas de una reserva.
TIPOS_DOCUMENTO = ["Cédula de ciudadanía", "Tarjeta de identidad", "Cédula de extranjería", "Pasaporte"]
PUNTUACIONES = [1, 2, 3, 4, 5]

# Fechas de salida "de prueba" que quedan en el pasado a propósito, para que el
# docente pueda probar de inmediato RF-13/RF-14 (plazos ya vencidos) y RF-20
# (calificar un viaje) sin tener que esperar semanas a que ocurra un viaje real.
FECHA_PRUEBA_DIAS = -2

MESES_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def hoy():
    return date.today()


def fecha_es(valor_iso, con_nota=False):
    d = datetime.strptime(valor_iso, "%Y-%m-%d").date()
    texto = f"{d.day} de {MESES_ES[d.month]} de {d.year}"
    if con_nota and d < hoy():
        texto += " (fecha de prueba, ya pasó)"
    return texto


def cop(valor):
    return "$" + f"{int(valor):,}".replace(",", ".")


app.jinja_env.filters["fecha_es"] = fecha_es
app.jinja_env.filters["cop"] = cop
app.jinja_env.globals["foto_destino"] = foto_destino
app.jinja_env.globals["hoy"] = hoy

# ---------------------------------------------------------------------------
# Base de datos (SQLite: viene incluida con Python, no requiere instalar nada)
# ---------------------------------------------------------------------------
def sin_acentos(texto):
    """Quita tildes/diacríticos y pasa a minúsculas, para búsquedas que no
    dependan de que el usuario escriba los acentos exactos (RF-05: buscar
    'mexico' debe encontrar 'México')."""
    if texto is None:
        return None
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c)).lower()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        # RF-05/RF-27/RF-28: función SQL para comparar texto sin distinguir
        # tildes ni mayúsculas/minúsculas en las búsquedas de destinos y paquetes.
        g.db.create_function("sin_acentos", 1, sin_acentos)
    return g.db


@app.teardown_appcontext
def cerrar_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def iniciar_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                nombres       TEXT NOT NULL,
                apellidos     TEXT NOT NULL,
                correo        TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol           TEXT NOT NULL CHECK (rol IN ('cliente', 'administrador')),
                estado        TEXT NOT NULL DEFAULT 'activo',
                creado_en     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS restablecimientos (
                token       TEXT PRIMARY KEY,
                usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
                expira_en   TEXT NOT NULL,
                usado       INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # --- RF-05 a RF-09: destinos y paquetes -----------------------------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS destinos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre      TEXT NOT NULL,
                pais        TEXT NOT NULL,
                region      TEXT NOT NULL,
                descripcion TEXT NOT NULL DEFAULT ''
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS paquetes (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                destino_id              INTEGER NOT NULL REFERENCES destinos(id),
                nombre                  TEXT NOT NULL,
                categoria               TEXT NOT NULL,
                resumen                 TEXT NOT NULL DEFAULT '',
                duracion_dias           INTEGER NOT NULL,
                precio_persona          INTEGER NOT NULL,
                permite_cuotas          INTEGER NOT NULL DEFAULT 0,
                plazo_cancelacion_dias  INTEGER NOT NULL DEFAULT 5,
                activo                  INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS paquete_incluidos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id  INTEGER NOT NULL REFERENCES paquetes(id),
                texto       TEXT NOT NULL,
                orden       INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS paquete_itinerario (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id   INTEGER NOT NULL REFERENCES paquetes(id),
                dia_numero   INTEGER NOT NULL,
                titulo       TEXT NOT NULL,
                descripcion  TEXT NOT NULL DEFAULT ''
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS paquete_servicios (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id      INTEGER NOT NULL REFERENCES paquetes(id),
                tipo            TEXT NOT NULL,
                nombre          TEXT NOT NULL,
                precio_persona  INTEGER NOT NULL,
                activo          INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS paquete_salidas (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id          INTEGER NOT NULL REFERENCES paquetes(id),
                fecha               TEXT NOT NULL,
                cupos_totales       INTEGER NOT NULL,
                cupos_disponibles   INTEGER NOT NULL,
                UNIQUE (paquete_id, fecha)
            )
            """
        )
        # --- RF-10 a RF-15: reservas -----------------------------------------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS reservas (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo               TEXT NOT NULL UNIQUE,
                cliente_id           INTEGER NOT NULL REFERENCES usuarios(id),
                paquete_id           INTEGER NOT NULL REFERENCES paquetes(id),
                salida_id            INTEGER NOT NULL REFERENCES paquete_salidas(id),
                num_personas         INTEGER NOT NULL,
                estado               TEXT NOT NULL DEFAULT 'pendiente',
                subtotal_paquete     INTEGER NOT NULL,
                subtotal_servicios   INTEGER NOT NULL DEFAULT 0,
                total                INTEGER NOT NULL,
                creado_en            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS reserva_servicios (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                reserva_id     INTEGER NOT NULL REFERENCES reservas(id),
                servicio_id    INTEGER NOT NULL REFERENCES paquete_servicios(id),
                precio_total   INTEGER NOT NULL
            )
            """
        )
        # --- Datos básicos de las personas incluidas en una reserva (viajeros) ---
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS reserva_viajeros (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                reserva_id        INTEGER NOT NULL REFERENCES reservas(id),
                nombres           TEXT NOT NULL,
                apellidos         TEXT NOT NULL,
                tipo_documento    TEXT NOT NULL,
                numero_documento  TEXT NOT NULL
            )
            """
        )
        # --- RF-16 a RF-19: pagos ---------------------------------------------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS pagos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                reserva_id      INTEGER NOT NULL REFERENCES reservas(id),
                metodo          TEXT NOT NULL,
                titular         TEXT NOT NULL,
                tarjeta_final   TEXT NOT NULL,
                cuotas          INTEGER NOT NULL DEFAULT 1,
                monto           INTEGER NOT NULL,
                estado          TEXT NOT NULL DEFAULT 'aprobado',
                creado_en       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # --- RF-20: calificaciones ---------------------------------------------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS calificaciones (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                reserva_id    INTEGER NOT NULL UNIQUE REFERENCES reservas(id),
                paquete_id    INTEGER NOT NULL REFERENCES paquetes(id),
                cliente_id    INTEGER NOT NULL REFERENCES usuarios(id),
                puntuacion    INTEGER NOT NULL,
                comentario    TEXT NOT NULL DEFAULT '',
                creado_en     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # --- RF-21: chat de soporte ---------------------------------------------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS mensajes_soporte (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id   INTEGER NOT NULL REFERENCES usuarios(id),
                autor        TEXT NOT NULL,
                texto        TEXT NOT NULL,
                creado_en    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # --- RF-22: notificaciones al cliente sobre cambios de itinerario -------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS notificaciones (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
                paquete_id  INTEGER REFERENCES paquetes(id),
                texto       TEXT NOT NULL,
                leida       INTEGER NOT NULL DEFAULT 0,
                creado_en   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # --- RF-25: inventario de proveedores (hoteles, restaurantes) -----------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS proveedores (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                destino_id  INTEGER NOT NULL REFERENCES destinos(id),
                tipo        TEXT NOT NULL CHECK (tipo IN ('hotel', 'restaurante')),
                nombre      TEXT NOT NULL,
                direccion   TEXT NOT NULL DEFAULT '',
                capacidad   INTEGER NOT NULL DEFAULT 0,
                contacto    TEXT NOT NULL DEFAULT '',
                activo      INTEGER NOT NULL DEFAULT 1,
                creado_en   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # --- RF-44: promociones para los paquetes turísticos --------------------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS promociones (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id      INTEGER NOT NULL REFERENCES paquetes(id),
                nombre          TEXT NOT NULL,
                codigo          TEXT NOT NULL DEFAULT '',
                tipo            TEXT NOT NULL CHECK (tipo IN ('porcentaje', 'monto_fijo')),
                valor           INTEGER NOT NULL,
                fecha_inicio    TEXT NOT NULL,
                fecha_fin       TEXT NOT NULL,
                activa          INTEGER NOT NULL DEFAULT 1,
                creado_en       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # --- RF-46: costos asociados a cada paquete turístico -------------------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS paquete_costos (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id   INTEGER NOT NULL REFERENCES paquetes(id),
                categoria    TEXT NOT NULL CHECK (categoria IN
                             ('alojamiento', 'transporte', 'vuelos', 'actividades', 'otros')),
                descripcion  TEXT NOT NULL,
                monto        INTEGER NOT NULL,
                creado_en    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # --- RF-47: pagos a proveedores (hoteles, transportadores, etc.) --------
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS pagos_proveedores (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id       INTEGER REFERENCES paquetes(id),
                tipo_proveedor   TEXT NOT NULL CHECK (tipo_proveedor IN
                                 ('hotel', 'transportador', 'aerolinea', 'otro')),
                nombre_proveedor TEXT NOT NULL,
                concepto         TEXT NOT NULL,
                monto            INTEGER NOT NULL,
                estado           TEXT NOT NULL DEFAULT 'pendiente'
                                 CHECK (estado IN ('pendiente', 'pagado')),
                fecha_pago       TEXT,
                creado_en        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # ---------------------------------------------------------------------
        # RF-29 a RF-42: gestión operativa de la agencia (hoteles, habitaciones,
        # conductores, vehículos, pilotos, vuelos/aeronaves) y su asignación a
        # los paquetes turísticos, con detección de conflictos de disponibilidad.
        # ---------------------------------------------------------------------
        # RF-29/RF-30: hoteles asociados a la agencia (datos generales y de
        # contacto); el administrador puede modificarlos y activarlos/desactivarlos.
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS hoteles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                destino_id  INTEGER NOT NULL REFERENCES destinos(id),
                nombre      TEXT NOT NULL,
                direccion   TEXT NOT NULL DEFAULT '',
                telefono    TEXT NOT NULL DEFAULT '',
                correo      TEXT NOT NULL DEFAULT '',
                checkin     TEXT NOT NULL DEFAULT '14:00',
                checkout    TEXT NOT NULL DEFAULT '12:00',
                politicas   TEXT NOT NULL DEFAULT '',
                activo      INTEGER NOT NULL DEFAULT 1,
                creado_en   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # RF-31: tipos de habitación de cada hotel (capacidad, tarifa, características).
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS hotel_habitaciones (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                hotel_id        INTEGER NOT NULL REFERENCES hoteles(id),
                tipo            TEXT NOT NULL,
                capacidad       INTEGER NOT NULL,
                tarifa_noche    INTEGER NOT NULL,
                caracteristicas TEXT NOT NULL DEFAULT '',
                cupos_totales   INTEGER NOT NULL,
                activo          INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        # RF-32: habitaciones asignadas a un paquete (fechas de una salida
        # concreta), para poder calcular la disponibilidad restante por fecha.
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS paquete_hoteles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id      INTEGER NOT NULL REFERENCES paquetes(id),
                salida_id       INTEGER NOT NULL REFERENCES paquete_salidas(id),
                habitacion_id   INTEGER NOT NULL REFERENCES hotel_habitaciones(id),
                cantidad        INTEGER NOT NULL
            )
            """
        )
        # RF-33: conductores (datos personales, contacto y documentación).
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS conductores (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombres     TEXT NOT NULL,
                apellidos   TEXT NOT NULL,
                telefono    TEXT NOT NULL DEFAULT '',
                correo      TEXT NOT NULL DEFAULT '',
                documento   TEXT NOT NULL,
                activo      INTEGER NOT NULL DEFAULT 1,
                creado_en   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # RF-34: vehículos disponibles para el transporte turístico.
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS vehiculos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                placa       TEXT NOT NULL UNIQUE,
                tipo        TEXT NOT NULL,
                capacidad   INTEGER NOT NULL,
                estado      TEXT NOT NULL DEFAULT 'disponible'
                            CHECK (estado IN ('disponible', 'mantenimiento')),
                activo      INTEGER NOT NULL DEFAULT 1,
                creado_en   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # RF-35/RF-36: conductor + vehículo asignados al transporte de una
        # salida concreta de un paquete, con fecha y hora para revisar disponibilidad.
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS transporte_asignaciones (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id      INTEGER NOT NULL REFERENCES paquetes(id),
                salida_id       INTEGER NOT NULL REFERENCES paquete_salidas(id),
                conductor_id    INTEGER NOT NULL REFERENCES conductores(id),
                vehiculo_id     INTEGER NOT NULL REFERENCES vehiculos(id),
                fecha           TEXT NOT NULL,
                hora            TEXT NOT NULL,
                notas           TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # RF-37: pilotos (datos profesionales, contacto y documentación).
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS pilotos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombres     TEXT NOT NULL,
                apellidos   TEXT NOT NULL,
                telefono    TEXT NOT NULL DEFAULT '',
                correo      TEXT NOT NULL DEFAULT '',
                documento   TEXT NOT NULL,
                licencia    TEXT NOT NULL,
                activo      INTEGER NOT NULL DEFAULT 1,
                creado_en   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # RF-38: aeronaves de la agencia, usadas por los vuelos de los paquetes.
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS aeronaves (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                matricula   TEXT NOT NULL UNIQUE,
                modelo      TEXT NOT NULL,
                capacidad   INTEGER NOT NULL,
                activo      INTEGER NOT NULL DEFAULT 1,
                creado_en   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # RF-38/RF-39/RF-40: vuelos de un paquete (aeronave, origen, destino,
        # horarios) con el piloto asignado, para revisar su disponibilidad.
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS vuelos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id      INTEGER NOT NULL REFERENCES paquetes(id),
                salida_id       INTEGER NOT NULL REFERENCES paquete_salidas(id),
                aeronave_id     INTEGER NOT NULL REFERENCES aeronaves(id),
                piloto_id       INTEGER REFERENCES pilotos(id),
                origen          TEXT NOT NULL,
                destino         TEXT NOT NULL,
                fecha           TEXT NOT NULL,
                hora_salida     TEXT NOT NULL,
                hora_llegada    TEXT NOT NULL
            )
            """
        )
        # RF-41: versiones de paquetes para comparar combinaciones de servicios,
        # duración y costo antes de publicar una versión definitiva.
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS paquete_versiones (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                paquete_id      INTEGER NOT NULL REFERENCES paquetes(id),
                nombre_version  TEXT NOT NULL,
                duracion_dias   INTEGER NOT NULL,
                costo_total     INTEGER NOT NULL,
                servicios_ids   TEXT NOT NULL DEFAULT '[]',
                estado          TEXT NOT NULL DEFAULT 'borrador'
                                CHECK (estado IN ('borrador', 'publicada')),
                creado_en       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Migración compatible con bases creadas con una versión anterior.
        columnas_hotel = {fila[1] for fila in db.execute("PRAGMA table_info(hoteles)").fetchall()}
        if "checkin" not in columnas_hotel:
            db.execute("ALTER TABLE hoteles ADD COLUMN checkin TEXT NOT NULL DEFAULT '14:00'")
        if "checkout" not in columnas_hotel:
            db.execute("ALTER TABLE hoteles ADD COLUMN checkout TEXT NOT NULL DEFAULT '12:00'")
        if "politicas" not in columnas_hotel:
            db.execute("ALTER TABLE hoteles ADD COLUMN politicas TEXT NOT NULL DEFAULT ''")

        columnas_destino = {fila[1] for fila in db.execute("PRAGMA table_info(destinos)").fetchall()}
        if "imagen" not in columnas_destino:
            db.execute("ALTER TABLE destinos ADD COLUMN imagen TEXT NOT NULL DEFAULT ''")

        db.commit()
    sembrar_catalogo()
    completar_fotos()
    asegurar_admin_inicial()


def completar_fotos():
    """Asigna foto a los destinos que aún no tienen (también en bases ya creadas)."""
    with sqlite3.connect(DB_PATH) as db:
        for nombre, archivo in FOTOS_DESTINOS.items():
            db.execute("UPDATE destinos SET imagen = ? WHERE nombre = ? AND imagen = ''",
                       (url_commons(archivo), nombre))
        db.commit()


def asegurar_admin_inicial():
    """Crea la cuenta de administrador de la agencia si todavía no hay ninguna."""
    with sqlite3.connect(DB_PATH) as db:
        hay = db.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'administrador'").fetchone()[0]
        if hay:
            return
        db.execute(
            "INSERT INTO usuarios (nombres, apellidos, correo, password_hash, rol) VALUES (?,?,?,?,?)",
            (ADMIN_NOMBRE_INICIAL[0], ADMIN_NOMBRE_INICIAL[1], ADMIN_CORREO_INICIAL,
             generate_password_hash(ADMIN_PASSWORD_INICIAL), "administrador"),
        )
        db.commit()


def sembrar_catalogo():
    """Carga destinos y paquetes de ejemplo la primera vez que se ejecuta la app.

    RF-22 en adelante (creación de paquetes por el administrador) es de la
    siguiente entrega, así que por ahora el catálogo se siembra aquí para que
    el cliente tenga algo real que buscar, filtrar y reservar.
    """
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        if db.execute("SELECT COUNT(*) AS n FROM destinos").fetchone()["n"] > 0:
            return

        destinos = [
            ("Cartagena de Indias", "Colombia", "Caribe", "Murallas, balcones y atardeceres sobre el mar."),
            ("Eje Cafetero", "Colombia", "Andina", "Montañas verdes, fincas cafeteras y pueblos de colores."),
            ("San Andrés", "Colombia", "Caribe", "El mar de los siete colores y arrecifes de coral."),
            ("Tayrona y Sierra Nevada", "Colombia", "Caribe", "Selva, playas vírgenes y cultura indígena."),
            ("Cusco y Machu Picchu", "Perú", "Andina", "La ciudad inca y la puerta al Camino del Inca."),
            ("Ciudad de México", "México", "América del Norte", "Historia, gastronomía y arte en cada esquina."),
        ]
        db.executemany(
            "INSERT INTO destinos (nombre, pais, region, descripcion) VALUES (?,?,?,?)",
            destinos,
        )
        ids = {fila["nombre"]: fila["id"]
              for fila in db.execute("SELECT id, nombre FROM destinos")}

        paquetes = [
            # nombre, destino, categoria, resumen, dias, precio, cuotas, plazo
            ("Cartagena Colonial y Playa", "Cartagena de Indias", "playa",
             "Centro histórico, islas del Rosario y una noche de salsa en la Ciudad Amurallada.",
             4, 1850000, 1, 5),
            ("Ruta del Café Premium", "Eje Cafetero", "naturaleza",
             "Recorrido por fincas cafeteras, Valle de Cocora y el Parque del Café.",
             3, 1450000, 1, 4),
            ("San Andrés Todo Incluido", "San Andrés", "playa",
             "Hotel frente al mar, tour a Johnny Cay y snorkel en el mar de los siete colores.",
             5, 2650000, 1, 6),
            ("Tayrona Aventura", "Tayrona y Sierra Nevada", "aventura",
             "Caminatas por la selva, playas de Cabo San Juan y noche en hamaca frente al mar.",
             3, 1150000, 0, 3),
            ("Machu Picchu Clásico", "Cusco y Machu Picchu", "cultural",
             "Valle Sagrado, tren panorámico y entrada a la ciudadela inca con guía certificado.",
             6, 4200000, 1, 10),
            ("CDMX Cultural Express", "Ciudad de México", "cultural",
             "Teotihuacán, centro histórico, Frida Kahlo y la mejor gastronomía callejera.",
             4, 2100000, 0, 5),
        ]
        for nombre, destino, categoria, resumen, dias, precio, cuotas, plazo in paquetes:
            cur = db.execute(
                "INSERT INTO paquetes (destino_id, nombre, categoria, resumen, duracion_dias, "
                "precio_persona, permite_cuotas, plazo_cancelacion_dias) VALUES (?,?,?,?,?,?,?,?)",
                (ids[destino], nombre, categoria, resumen, dias, precio, cuotas, plazo),
            )
            paquete_id = cur.lastrowid

            incluidos = ["Alojamiento", "Desayunos incluidos", "Traslados aeropuerto-hotel",
                        "Guía local en español", "Seguro médico básico"]
            db.executemany(
                "INSERT INTO paquete_incluidos (paquete_id, texto, orden) VALUES (?,?,?)",
                [(paquete_id, texto, i) for i, texto in enumerate(incluidos)],
            )

            db.executemany(
                "INSERT INTO paquete_itinerario (paquete_id, dia_numero, titulo, descripcion) VALUES (?,?,?,?)",
                [
                    (paquete_id, 1, "Llegada y bienvenida",
                     f"Recepción en el destino, traslado al hotel y tarde libre para conocer {destino}."),
                    (paquete_id, 2, "Recorrido principal",
                     "Tour guiado por los atractivos más representativos del paquete."),
                    (paquete_id, dias, "Tiempo libre y salida",
                     "Última mañana libre, check-out y traslado de regreso al aeropuerto."),
                ],
            )

            db.executemany(
                "INSERT INTO paquete_servicios (paquete_id, tipo, nombre, precio_persona) VALUES (?,?,?,?)",
                [
                    (paquete_id, "seguro", "Seguro de viaje ampliado", 85000),
                    (paquete_id, "transporte", "Transporte privado aeropuerto-hotel-aeropuerto", 120000),
                    (paquete_id, "tour", "Tour opcional de día completo", 180000),
                ],
            )

            for offset in (FECHA_PRUEBA_DIAS, 10, 25, 50):
                fecha = (date.today() + timedelta(days=offset)).isoformat()
                totales = 12
                disponibles = 4 if offset == FECHA_PRUEBA_DIAS else totales
                db.execute(
                    "INSERT INTO paquete_salidas (paquete_id, fecha, cupos_totales, cupos_disponibles) "
                    "VALUES (?,?,?,?)",
                    (paquete_id, fecha, totales, disponibles),
                )
        db.commit()

# ---------------------------------------------------------------------------
# Seguridad: token CSRF y control de acceso por rol
# ---------------------------------------------------------------------------
def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = token_csrf
app.jinja_env.globals["app_nombre"] = APP_NOMBRE


@app.context_processor
def inyectar_notificaciones():
    """RF-22: número de notificaciones sin leer, visible en la barra del cliente."""
    if session.get("rol") == "cliente":
        fila = get_db().execute(
            "SELECT COUNT(*) AS n FROM notificaciones WHERE usuario_id = ? AND leida = 0",
            (session["usuario_id"],),
        ).fetchone()
        return {"notificaciones_sin_leer": fila["n"]}
    return {"notificaciones_sin_leer": 0}


@app.before_request
def proteger_formularios():
    if request.method == "POST":
        enviado = request.form.get("csrf_token", "").encode()
        esperado = session.get("csrf", "").encode()
        if not esperado or not hmac.compare_digest(enviado, esperado):
            abort(400)


def solo_rol(rol):
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if session.get("rol") != rol:
                flash("Inicia sesión para continuar.", "error")
                return redirect(url_for("acceso", rol=rol))
            return vista(*args, **kwargs)
        return envoltura
    return decorador


def rol_valido(rol):
    if rol not in ROLES:
        abort(404)
    return ROLES[rol]

# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------
RE_NOMBRE = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$", re.UNICODE)
RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def limpiar(texto):
    return re.sub(r"\s+", " ", (texto or "").strip())


def validar_nombre_apellido(datos, errores):
    for campo, etiqueta in (("nombres", "Escribe tus nombres."),
                            ("apellidos", "Escribe tus apellidos.")):
        valor = datos[campo]
        if not valor:
            errores[campo] = etiqueta
        elif not (2 <= len(valor) <= 60) or not RE_NOMBRE.match(valor):
            errores[campo] = "Usa solo letras (entre 2 y 60 caracteres)."


def validar_correo(correo, errores):
    if not correo:
        errores["correo"] = "Escribe tu correo electrónico."
    elif len(correo) > 120 or not RE_CORREO.match(correo):
        errores["correo"] = "Escribe un correo válido, por ejemplo nombre@dominio.com."


def validar_password_nueva(password, confirmar, errores, campo="password"):
    if not password:
        errores[campo] = "Crea una contraseña."
    elif len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        errores[campo] = "Debe tener al menos 8 caracteres, con letras y números."
    elif len(password) > 128:
        errores[campo] = "Usa como máximo 128 caracteres."

    if not confirmar:
        errores["confirmar"] = "Confirma tu contraseña."
    elif password and confirmar != password:
        errores["confirmar"] = "Las contraseñas no coinciden."


def validar_registro(form):
    datos = {
        "nombres": limpiar(form.get("nombres")),
        "apellidos": limpiar(form.get("apellidos")),
        "correo": (form.get("correo") or "").strip().lower(),
    }
    password = form.get("password", "")
    confirmar = form.get("confirmar", "")
    errores = {}

    validar_nombre_apellido(datos, errores)
    validar_correo(datos["correo"], errores)
    validar_password_nueva(password, confirmar, errores)

    return datos, password, errores


def generar_token_reset(usuario_id):
    token = secrets.token_urlsafe(32)
    expira = (datetime.utcnow() + timedelta(minutes=RESET_MINUTOS_VALIDEZ)).isoformat()
    db = get_db()
    db.execute("DELETE FROM restablecimientos WHERE usuario_id = ?", (usuario_id,))
    db.execute(
        "INSERT INTO restablecimientos (token, usuario_id, expira_en) VALUES (?, ?, ?)",
        (token, usuario_id, expira),
    )
    db.commit()
    return token


def buscar_token_valido(token):
    fila = get_db().execute(
        "SELECT * FROM restablecimientos WHERE token = ?", (token,)
    ).fetchone()
    if not fila or fila["usado"]:
        return None
    if datetime.utcnow() > datetime.fromisoformat(fila["expira_en"]):
        return None
    return fila

# ---------------------------------------------------------------------------
# Rutas públicas
# ---------------------------------------------------------------------------
def destinos_con_precio():
    """Destinos con foto, número de paquetes y precio mínimo (portada y panel)."""
    return get_db().execute(
        "SELECT d.*, COUNT(p.id) AS num_paquetes, MIN(p.precio_persona) AS desde "
        "FROM destinos d LEFT JOIN paquetes p ON p.destino_id = d.id AND p.activo = 1 "
        "GROUP BY d.id ORDER BY d.id"
    ).fetchall()


@app.route("/")
def inicio():
    if session.get("rol") in ROLES:
        return redirect(url_for(ROLES[session["rol"]]["panel"]))
    return render_template("inicio.html", destinos=destinos_con_precio())


@app.route("/acceso/<rol>/registro", methods=["GET", "POST"])
def registro(rol):
    info = rol_valido(rol)
    if rol != "cliente":
        # Las cuentas de administrador no se crean desde la web: las entrega
        # la agencia (ver ADMIN_* en la configuración).
        abort(404)
    datos = {"nombres": "", "apellidos": "", "correo": ""}
    errores = {}

    if request.method == "POST":
        datos, password, errores = validar_registro(request.form)
        if not errores:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO usuarios (nombres, apellidos, correo, password_hash, rol) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (datos["nombres"], datos["apellidos"], datos["correo"],
                     generate_password_hash(password), rol),
                )
                db.commit()
            except sqlite3.IntegrityError:
                errores["correo"] = "Este correo ya tiene una cuenta. Inicia sesión."
            else:
                flash("Cuenta creada. Ya puedes iniciar sesión.", "ok")
                return redirect(url_for("acceso", rol=rol))

    return render_template("acceso.html", rol=rol, r=info, modo="registro",
                           datos=datos, errores=errores)


@app.route("/acceso/<rol>", methods=["GET", "POST"])
def acceso(rol):
    info = rol_valido(rol)
    correo = ""
    errores = {}

    if request.method == "POST":
        correo = (request.form.get("correo") or "").strip().lower()
        password = request.form.get("password", "")
        usuario = get_db().execute(
            "SELECT * FROM usuarios WHERE correo = ?", (correo,)
        ).fetchone()

        token_ok = True
        if rol == "administrador":
            enviado_token = (request.form.get("token_agencia") or "").strip()
            token_ok = hmac.compare_digest(enviado_token.encode(), ADMIN_TOKEN.encode())

        if not usuario or not check_password_hash(usuario["password_hash"], password) or not token_ok:
            errores["general"] = ("Correo, contraseña o token de la agencia incorrectos."
                                  if rol == "administrador" else "Correo o contraseña incorrectos.")
        elif usuario["rol"] != rol:
            errores["general"] = (
                f"Esta cuenta está registrada como {usuario['rol']}. "
                f"Entra por la opción de {usuario['rol']}."
            )
        elif usuario["estado"] != "activo":
            errores["general"] = "Tu cuenta está desactivada. Comunícate con la agencia."
        else:
            session.clear()
            session["usuario_id"] = usuario["id"]
            session["rol"] = usuario["rol"]
            session["nombre"] = usuario["nombres"]
            session["nombre_completo"] = f"{usuario['nombres']} {usuario['apellidos']}"
            return redirect(url_for(info["panel"]))

    return render_template("acceso.html", rol=rol, r=info, modo="ingresar",
                           datos={"correo": correo}, errores=errores)


@app.route("/salir", methods=["POST"])
def salir():
    session.clear()
    flash("Cerraste sesión correctamente.", "ok")
    return redirect(url_for("inicio"))

# ---------------------------------------------------------------------------
# RF-03: recuperar contraseña
# ---------------------------------------------------------------------------
@app.route("/acceso/<rol>/recuperar", methods=["GET", "POST"])
def recuperar(rol):
    info = rol_valido(rol)
    correo = ""
    errores = {}
    enlace = None
    enviado = False

    if request.method == "POST":
        correo = (request.form.get("correo") or "").strip().lower()
        validar_correo(correo, errores)

        if not errores:
            enviado = True
            usuario = get_db().execute(
                "SELECT * FROM usuarios WHERE correo = ? AND rol = ?", (correo, rol)
            ).fetchone()
            # Por seguridad el mensaje es igual exista o no la cuenta; solo se
            # genera un enlace real cuando sí hay una cuenta con ese correo.
            if usuario and rol == "cliente":
                token = generar_token_reset(usuario["id"])
                enlace = url_for("restablecer", token=token, _external=True)

    return render_template("recuperar.html", rol=rol, r=info, correo=correo,
                           errores=errores, enlace=enlace, enviado=enviado)


@app.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer(token):
    fila = buscar_token_valido(token)
    if not fila:
        return render_template("error.html", codigo=410,
                               mensaje="Este enlace ya no es válido. Solicita uno nuevo desde "
                                       "\"¿Olvidaste tu contraseña?\"."), 410

    usuario = get_db().execute(
        "SELECT * FROM usuarios WHERE id = ?", (fila["usuario_id"],)
    ).fetchone()
    errores = {}

    if request.method == "POST":
        password = request.form.get("password", "")
        confirmar = request.form.get("confirmar", "")
        validar_password_nueva(password, confirmar, errores)

        if not errores:
            db = get_db()
            db.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(password), usuario["id"]))
            db.execute("UPDATE restablecimientos SET usado = 1 WHERE token = ?", (token,))
            db.commit()
            flash("Tu contraseña se actualizó. Ya puedes iniciar sesión.", "ok")
            return redirect(url_for("acceso", rol=usuario["rol"]))

    return render_template("restablecer.html", rol=usuario["rol"],
                           r=ROLES[usuario["rol"]], errores=errores)

# ---------------------------------------------------------------------------
# Paneles (punto de partida para los demás módulos)
# ---------------------------------------------------------------------------
@app.route("/cliente/panel")
@solo_rol("cliente")
def panel_cliente():
    db = get_db()
    uid = session["usuario_id"]
    proximo = db.execute(
        "SELECT r.id, r.codigo, r.estado, r.num_personas, p.nombre AS paquete_nombre, "
        "s.fecha AS fecha_salida FROM reservas r "
        "JOIN paquetes p ON p.id = r.paquete_id JOIN paquete_salidas s ON s.id = r.salida_id "
        "WHERE r.cliente_id = ? AND r.estado IN ('pendiente', 'confirmada') AND s.fecha >= ? "
        "ORDER BY s.fecha LIMIT 1",
        (uid, hoy().isoformat()),
    ).fetchone()
    dias_para_viaje = dias_hasta(proximo["fecha_salida"]) if proximo else None
    por_pagar = db.execute(
        "SELECT COUNT(*) AS n FROM reservas r WHERE r.cliente_id = ? AND r.estado = 'pendiente' "
        "AND NOT EXISTS (SELECT 1 FROM pagos pg WHERE pg.reserva_id = r.id)",
        (uid,),
    ).fetchone()["n"]
    total_reservas = db.execute(
        "SELECT COUNT(*) AS n FROM reservas WHERE cliente_id = ?", (uid,)
    ).fetchone()["n"]
    destinos_populares = destinos_con_precio()
    return render_template(
        "panel.html", rol="cliente", proximo=proximo, dias_para_viaje=dias_para_viaje,
        por_pagar=por_pagar, total_reservas=total_reservas,
        destinos_populares=destinos_populares,
    )


@app.route("/administrador/panel")
@solo_rol("administrador")
def panel_admin():
    db = get_db()
    inicio_mes = hoy().replace(day=1).isoformat()

    def uno(sql, params=()):
        return db.execute(sql, params).fetchone()[0] or 0

    metricas = {
        "paquetes_activos": uno("SELECT COUNT(*) FROM paquetes WHERE activo = 1"),
        "reservas_pendientes": uno("SELECT COUNT(*) FROM reservas WHERE estado = 'pendiente'"),
        "ventas_mes": uno(
            "SELECT SUM(monto) FROM pagos WHERE estado = 'aprobado' AND date(creado_en) >= ?",
            (inicio_mes,),
        ),
        "clientes": uno("SELECT COUNT(*) FROM usuarios WHERE rol = 'cliente'"),
        "por_pagar_proveedores": uno(
            "SELECT SUM(monto) FROM pagos_proveedores WHERE estado = 'pendiente'"
        ),
    }
    conflictos = detectar_conflictos(db)
    incompletos = []
    for p in db.execute("SELECT id, nombre FROM paquetes WHERE activo = 1 ORDER BY nombre").fetchall():
        estado = estado_operativo_paquete(db, p["id"])
        if not estado["listo"]:
            incompletos.append({"id": p["id"], "nombre": p["nombre"], "problema": estado["problemas"][0]})
    return render_template(
        "panel.html", rol="administrador", metricas=metricas,
        conflictos=conflictos, incompletos=incompletos,
    )


# ---------------------------------------------------------------------------
# Requerimientos funcionales (página informativa para docentes y usuarios)
# ---------------------------------------------------------------------------
# (id, módulo, actor, texto, dónde se usa, endpoint, rol necesario para el enlace, argumentos)
_C, _A = "cliente", "administrador"
REQUERIMIENTOS = [
    (1, "Cuenta y acceso", "Cliente", "Registrarse con nombre, correo electrónico y contraseña.", "Inicio › Crear cuenta", "registro", None, {"rol": _C}),
    (2, "Cuenta y acceso", "Cliente / Administrador", "Iniciar sesión con credenciales válidas.", "Inicio › Iniciar sesión", "acceso", None, {"rol": _C}),
    (3, "Cuenta y acceso", "Cliente", "Recuperar la contraseña mediante correo electrónico.", "Iniciar sesión › ¿Olvidaste tu contraseña?", "recuperar", None, {"rol": _C}),
    (4, "Cuenta y acceso", "Cliente", "Editar los datos del perfil.", "Menú de usuario › Mi perfil", "perfil", _C, {"rol": _C}),
    (5, "Explorar viajes", "Cliente", "Buscar destinos turísticos por nombre, país o región.", "Destinos", "cliente_destinos", _C, {}),
    (6, "Explorar viajes", "Cliente", "Filtrar paquetes por precio, duración y categoría.", "Paquetes", "cliente_paquetes", _C, {}),
    (7, "Explorar viajes", "Cliente", "Ver el detalle de cada paquete: itinerario, incluidos y precio.", "Paquetes › Ver detalle", "cliente_paquetes", _C, {}),
    (8, "Explorar viajes", "Cliente", "Comparar dos o más paquetes turísticos.", "Paquetes › Comparar", "cliente_paquetes", _C, {}),
    (9, "Explorar viajes", "Cliente", "Ver la disponibilidad de cupos por fecha de cada paquete.", "Paquetes › Ver detalle", "cliente_paquetes", _C, {}),
    (26, "Explorar viajes", "Cliente", "Consultar los países disponibles como destinos turísticos.", "Países", "cliente_paises", _C, {}),
    (27, "Explorar viajes", "Cliente", "Filtrar los destinos turísticos por región.", "Destinos › Filtrar por región", "cliente_destinos", _C, {}),
    (28, "Explorar viajes", "Cliente", "Buscar paquetes escribiendo el nombre de un destino.", "Paquetes › Buscar", "cliente_paquetes", _C, {}),
    (10, "Reservas", "Cliente", "Reservar un paquete eligiendo la fecha y el número de personas.", "Paquetes › Ver detalle › Reservar", "cliente_paquetes", _C, {}),
    (11, "Reservas", "Cliente", "Elegir servicios adicionales: seguro de viaje, transporte y tours.", "Paquetes › Ver detalle › Reservar", "cliente_paquetes", _C, {}),
    (12, "Reservas", "Sistema", "Generar un número de confirmación único por cada reserva.", "Mis reservas", "cliente_reservas", _C, {}),
    (13, "Reservas", "Cliente", "Cancelar una reserva dentro de los plazos establecidos.", "Mis reservas › Ver › Cancelar", "cliente_reservas", _C, {}),
    (14, "Reservas", "Cliente", "Modificar la fecha de una reserva ya realizada.", "Mis reservas › Ver › Cambiar fecha", "cliente_reservas", _C, {}),
    (15, "Reservas", "Sistema", "Enviar una confirmación al completar una reserva.", "Mis reservas › Ver", "cliente_reservas", _C, {}),
    (16, "Pagos", "Cliente", "Pagar en línea con tarjeta de crédito o débito.", "Mis reservas › Ver › Pagar", "cliente_reservas", _C, {}),
    (17, "Pagos", "Cliente", "Pagar en cuotas cuando el paquete lo permite.", "Mis reservas › Ver › Pagar", "cliente_reservas", _C, {}),
    (18, "Pagos", "Sistema", "Generar un comprobante de pago en PDF.", "Mis reservas › Ver › Descargar comprobante", "cliente_reservas", _C, {}),
    (19, "Pagos", "Sistema", "Validar el cupo disponible antes de confirmar el pago.", "Mis reservas › Ver › Pagar", "cliente_reservas", _C, {}),
    (20, "Después del viaje", "Cliente", "Calificar y comentar un paquete después del viaje.", "Mis reservas › Ver › Califica tu viaje", "cliente_reservas", _C, {}),
    (21, "Después del viaje", "Cliente", "Pedir ayuda a un asesor mediante chat.", "Soporte", "cliente_soporte", _C, {}),
    (22, "Después del viaje", "Sistema", "Avisar al usuario sobre cambios de itinerario o de su destino.", "Avisos", "cliente_notificaciones", _C, {}),
    (23, "Paquetes y promociones", "Administrador", "Crear, editar y eliminar paquetes turísticos.", "Paquetes", "admin_paquetes", _A, {}),
    (41, "Paquetes y promociones", "Administrador", "Diseñar y guardar versiones de un paquete para comparar servicios, duración y costo antes de publicar la definitiva.", "Paquetes › Editar › Versiones", "admin_paquetes", _A, {}),
    (43, "Paquetes y promociones", "Administrador", "Consultar el estado operativo de un paquete antes de habilitarlo para reservas.", "Paquetes › Editar › Estado operativo", "admin_paquetes", _A, {}),
    (44, "Paquetes y promociones", "Administrador", "Crear, modificar, activar y desactivar promociones.", "Paquetes › Editar › Promociones", "admin_paquetes", _A, {}),
    (45, "Paquetes y promociones", "Administrador", "Actualizar la disponibilidad de cupos según la fecha del viaje.", "Paquetes › Editar › Fechas y cupos", "admin_paquetes", _A, {}),
    (46, "Paquetes y promociones", "Administrador", "Registrar y actualizar los costos de cada paquete: alojamiento, transporte, vuelos, actividades y otros.", "Paquetes › Editar › Costos", "admin_paquetes", _A, {}),
    (25, "Proveedores y hoteles", "Administrador", "Gestionar el inventario de lugares para proveedores: hoteles y restaurantes.", "Proveedores", "admin_proveedores", _A, {}),
    (29, "Proveedores y hoteles", "Administrador", "Registrar los horarios de check-in y check-out de cada hotel.", "Hoteles, transporte y vuelos › Hoteles", "admin_operacion", _A, {}),
    (30, "Proveedores y hoteles", "Administrador", "Registrar las políticas de cada hotel: cancelaciones, mascotas y restricciones.", "Hoteles, transporte y vuelos › Hoteles", "admin_operacion", _A, {}),
    (31, "Proveedores y hoteles", "Administrador", "Registrar tipos de habitación, capacidad, tarifas y características de cada hotel.", "Hoteles, transporte y vuelos › Hoteles", "admin_operacion", _A, {}),
    (32, "Proveedores y hoteles", "Administrador", "Consultar la disponibilidad de habitaciones según las fechas de un paquete.", "Paquetes › Editar › Recursos operativos", "admin_paquetes", _A, {}),
    (33, "Transporte y vuelos", "Administrador", "Registrar conductores con datos personales, contacto y documentación.", "Hoteles, transporte y vuelos › Conductores", "admin_operacion", _A, {}),
    (34, "Transporte y vuelos", "Administrador", "Registrar vehículos con tipo, capacidad y estado.", "Hoteles, transporte y vuelos › Vehículos", "admin_operacion", _A, {}),
    (35, "Transporte y vuelos", "Administrador", "Asignar conductores y vehículos al transporte de un paquete.", "Paquetes › Editar › Recursos operativos", "admin_paquetes", _A, {}),
    (36, "Transporte y vuelos", "Administrador", "Consultar la disponibilidad de conductores y vehículos por fecha y horario.", "Paquetes › Editar › Recursos operativos", "admin_paquetes", _A, {}),
    (37, "Transporte y vuelos", "Administrador", "Registrar pilotos con datos profesionales, contacto y documentación.", "Hoteles, transporte y vuelos › Pilotos", "admin_operacion", _A, {}),
    (38, "Transporte y vuelos", "Administrador", "Registrar vuelos y aeronaves de los paquetes, con horarios, origen y destino.", "Hoteles, transporte y vuelos › Aeronaves", "admin_operacion", _A, {}),
    (39, "Transporte y vuelos", "Administrador", "Asignar pilotos a los vuelos programados.", "Paquetes › Editar › Recursos operativos", "admin_paquetes", _A, {}),
    (40, "Transporte y vuelos", "Administrador", "Consultar la disponibilidad de pilotos según fecha y horario del vuelo.", "Paquetes › Editar › Recursos operativos", "admin_paquetes", _A, {}),
    (42, "Transporte y vuelos", "Sistema", "Detectar y avisar conflictos de disponibilidad entre hoteles, conductores, vehículos y pilotos.", "Hoteles, transporte y vuelos (alerta arriba)", "admin_operacion", _A, {}),
    (47, "Clientes y finanzas", "Administrador", "Registrar y consultar pagos realizados y valores pendientes con proveedores.", "Pagos a proveedores", "admin_pagos_proveedores", _A, {}),
    (48, "Clientes y finanzas", "Administrador", "Consultar, actualizar y gestionar los datos y el estado de las cuentas de clientes.", "Clientes", "admin_clientes", _A, {}),
    (24, "Reportes", "Administrador", "Generar reportes de ventas por período.", "Reportes › Ventas por período", "admin_reportes", _A, {}),
    (49, "Reportes", "Administrador", "Generar reportes de reservas por fecha, destino, estado y paquete.", "Reportes › Reservas", "admin_reportes", _A, {}),
    (50, "Reportes", "Administrador", "Consultar reportes generales de ventas, costos, ingresos, pagos a proveedores, disponibilidad y operación.", "Reportes › Reporte general", "admin_reportes", _A, {}),
]


@app.route("/requerimientos")
def requerimientos():
    rol_actual = session.get("rol")
    grupos = {}
    for rf, modulo, actor, texto, donde, endpoint, rol_req, args in REQUERIMIENTOS:
        enlace = url_for(endpoint, **args) if (rol_req is None or rol_req == rol_actual) else None
        grupos.setdefault(modulo, []).append(
            {"id": f"RF-{rf:02d}", "n": rf, "actor": actor, "texto": texto, "donde": donde, "enlace": enlace}
        )
    for items in grupos.values():
        items.sort(key=lambda i: i["n"])
    return render_template(
        "requerimientos.html", grupos=grupos, total=len(REQUERIMIENTOS), rol=rol_actual or "",
    )

# ---------------------------------------------------------------------------
# RF-04: editar perfil y cambiar contraseña (cliente y administrador)
# ---------------------------------------------------------------------------
@app.route("/<rol>/perfil", methods=["GET", "POST"])
def perfil(rol):
    info = rol_valido(rol)
    if session.get("rol") != rol:
        flash("Inicia sesión para continuar.", "error")
        return redirect(url_for("acceso", rol=rol))

    db = get_db()
    usuario = db.execute("SELECT * FROM usuarios WHERE id = ?", (session["usuario_id"],)).fetchone()
    datos = {"nombres": usuario["nombres"], "apellidos": usuario["apellidos"], "correo": usuario["correo"]}
    errores = {}

    if request.method == "POST" and request.form.get("accion") == "datos":
        datos = {
            "nombres": limpiar(request.form.get("nombres")),
            "apellidos": limpiar(request.form.get("apellidos")),
            "correo": (request.form.get("correo") or "").strip().lower(),
        }
        validar_nombre_apellido(datos, errores)
        validar_correo(datos["correo"], errores)

        if not errores:
            try:
                db.execute(
                    "UPDATE usuarios SET nombres = ?, apellidos = ?, correo = ? WHERE id = ?",
                    (datos["nombres"], datos["apellidos"], datos["correo"], usuario["id"]),
                )
                db.commit()
            except sqlite3.IntegrityError:
                errores["correo"] = "Ese correo ya lo usa otra cuenta."
            else:
                session["nombre"] = datos["nombres"]
                session["nombre_completo"] = f"{datos['nombres']} {datos['apellidos']}"
                flash("Tus datos se actualizaron correctamente.", "ok")
                return redirect(url_for("perfil", rol=rol))

    return render_template("perfil.html", rol=rol, r=info, datos=datos, errores=errores,
                           errores_pw={})


@app.route("/<rol>/perfil/contrasena", methods=["POST"])
def cambiar_contrasena(rol):
    rol_valido(rol)
    if session.get("rol") != rol:
        flash("Inicia sesión para continuar.", "error")
        return redirect(url_for("acceso", rol=rol))

    db = get_db()
    usuario = db.execute("SELECT * FROM usuarios WHERE id = ?", (session["usuario_id"],)).fetchone()
    actual = request.form.get("actual", "")
    nueva = request.form.get("password", "")
    confirmar = request.form.get("confirmar", "")
    errores_pw = {}

    if not check_password_hash(usuario["password_hash"], actual):
        errores_pw["actual"] = "Tu contraseña actual no es correcta."
    validar_password_nueva(nueva, confirmar, errores_pw)
    if not errores_pw and actual and nueva == actual:
        errores_pw["password"] = "La nueva contraseña debe ser distinta a la actual."

    if not errores_pw:
        db.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?",
                   (generate_password_hash(nueva), usuario["id"]))
        db.commit()
        flash("Tu contraseña se cambió correctamente.", "ok")
        return redirect(url_for("perfil", rol=rol))

    datos = {"nombres": usuario["nombres"], "apellidos": usuario["apellidos"], "correo": usuario["correo"]}
    return render_template("perfil.html", rol=rol, r=ROLES[rol], datos=datos,
                           errores={}, errores_pw=errores_pw)


# ---------------------------------------------------------------------------
# Utilidades del módulo de destinos, paquetes y reservas
# ---------------------------------------------------------------------------
def paquete_o_404(paquete_id):
    fila = get_db().execute(
        "SELECT p.*, d.nombre AS destino_nombre, d.pais, d.region, d.imagen AS destino_imagen "
        "FROM paquetes p JOIN destinos d ON d.id = p.destino_id "
        "WHERE p.id = ? AND p.activo = 1",
        (paquete_id,),
    ).fetchone()
    if not fila:
        abort(404)
    return fila


def cargar_extras_paquete(paquete_id):
    db = get_db()
    incluidos = db.execute(
        "SELECT texto FROM paquete_incluidos WHERE paquete_id = ? ORDER BY orden", (paquete_id,)
    ).fetchall()
    itinerario = db.execute(
        "SELECT * FROM paquete_itinerario WHERE paquete_id = ? ORDER BY dia_numero", (paquete_id,)
    ).fetchall()
    servicios = db.execute(
        "SELECT * FROM paquete_servicios WHERE paquete_id = ? AND activo = 1", (paquete_id,)
    ).fetchall()
    salidas = db.execute(
        "SELECT * FROM paquete_salidas WHERE paquete_id = ? ORDER BY fecha", (paquete_id,)
    ).fetchall()
    resumen = db.execute(
        "SELECT COUNT(*) AS n, AVG(puntuacion) AS promedio FROM calificaciones WHERE paquete_id = ?",
        (paquete_id,),
    ).fetchone()
    comentarios = db.execute(
        "SELECT c.puntuacion, c.comentario, c.creado_en, u.nombres "
        "FROM calificaciones c JOIN usuarios u ON u.id = c.cliente_id "
        "WHERE c.paquete_id = ? ORDER BY c.creado_en DESC LIMIT 10",
        (paquete_id,),
    ).fetchall()
    return incluidos, itinerario, servicios, salidas, resumen, comentarios


def notificar_clientes_paquete(paquete_id, texto):
    """RF-22: avisa a todo cliente con una reserva activa (pendiente o confirmada)
    sobre un cambio de itinerario o de información del destino de ese paquete."""
    db = get_db()
    clientes = db.execute(
        "SELECT DISTINCT cliente_id FROM reservas WHERE paquete_id = ? "
        "AND estado IN ('pendiente', 'confirmada')",
        (paquete_id,),
    ).fetchall()
    for fila in clientes:
        db.execute(
            "INSERT INTO notificaciones (usuario_id, paquete_id, texto) VALUES (?, ?, ?)",
            (fila["cliente_id"], paquete_id, texto),
        )
    db.commit()
    return len(clientes)


def generar_codigo_confirmacion():
    """RF-12: número de confirmación único por reserva."""
    db = get_db()
    while True:
        codigo = "RB-" + secrets.token_hex(4).upper()
        existe = db.execute("SELECT 1 FROM reservas WHERE codigo = ?", (codigo,)).fetchone()
        if not existe:
            return codigo


def reserva_de_cliente_o_404(reserva_id):
    fila = get_db().execute(
        "SELECT r.*, p.nombre AS paquete_nombre, p.plazo_cancelacion_dias, p.permite_cuotas, "
        "       p.destino_id, p.duracion_dias, s.fecha AS fecha_salida, s.id AS salida_id "
        "FROM reservas r "
        "JOIN paquetes p ON p.id = r.paquete_id "
        "JOIN paquete_salidas s ON s.id = r.salida_id "
        "WHERE r.id = ? AND r.cliente_id = ?",
        (reserva_id, session.get("usuario_id")),
    ).fetchone()
    if not fila:
        abort(404)
    return fila


def dias_hasta(fecha_iso):
    return (datetime.strptime(fecha_iso, "%Y-%m-%d").date() - hoy()).days

# ---------------------------------------------------------------------------
# RF-05 y RF-27: buscar destinos por nombre, país o región, y además filtrar
# específicamente por región con un menú desplegable.
# ---------------------------------------------------------------------------
@app.route("/cliente/destinos")
@solo_rol("cliente")
def cliente_destinos():
    q = limpiar(request.args.get("q"))
    region = request.args.get("region") or ""
    db = get_db()

    condiciones = []
    parametros = []
    if q:
        # RF-05: comparar sin tildes ni mayúsculas para que "mexico" encuentre
        # "México", "bogota" encuentre "Bogotá", etc.
        condiciones.append(
            "(sin_acentos(d.nombre) LIKE sin_acentos(?) OR "
            "sin_acentos(d.pais) LIKE sin_acentos(?) OR "
            "sin_acentos(d.region) LIKE sin_acentos(?))"
        )
        patron = f"%{q}%"
        parametros += [patron, patron, patron]
    if region:
        # RF-27: filtro exacto por región, independiente del texto libre de RF-05.
        condiciones.append("d.region = ?")
        parametros.append(region)

    sql = (
        "SELECT d.*, COUNT(p.id) AS num_paquetes FROM destinos d "
        "LEFT JOIN paquetes p ON p.destino_id = d.id AND p.activo = 1 "
        + ("WHERE " + " AND ".join(condiciones) + " " if condiciones else "")
        + "GROUP BY d.id ORDER BY d.nombre"
    )
    destinos = db.execute(sql, parametros).fetchall()
    regiones = [f["region"] for f in db.execute("SELECT DISTINCT region FROM destinos ORDER BY region")]

    return render_template("cliente_destinos.html", destinos=destinos, q=q,
                           region=region, regiones=regiones)

# ---------------------------------------------------------------------------
# RF-26: consultar los países disponibles como destinos turísticos
# ---------------------------------------------------------------------------
@app.route("/cliente/paises")
@solo_rol("cliente")
def cliente_paises():
    paises = get_db().execute(
        "SELECT d.pais, COUNT(DISTINCT d.id) AS num_destinos, "
        "       COUNT(DISTINCT CASE WHEN p.activo = 1 THEN p.id END) AS num_paquetes "
        "FROM destinos d LEFT JOIN paquetes p ON p.destino_id = d.id "
        "GROUP BY d.pais ORDER BY d.pais"
    ).fetchall()
    return render_template("cliente_paises.html", paises=paises)

# ---------------------------------------------------------------------------
# RF-22: notificaciones sobre cambios de itinerario o del destino del viaje
# ---------------------------------------------------------------------------
@app.route("/cliente/notificaciones")
@solo_rol("cliente")
def cliente_notificaciones():
    db = get_db()
    notificaciones = db.execute(
        "SELECT n.*, p.nombre AS paquete_nombre FROM notificaciones n "
        "LEFT JOIN paquetes p ON p.id = n.paquete_id "
        "WHERE n.usuario_id = ? ORDER BY n.creado_en DESC",
        (session["usuario_id"],),
    ).fetchall()
    db.execute("UPDATE notificaciones SET leida = 1 WHERE usuario_id = ? AND leida = 0",
              (session["usuario_id"],))
    db.commit()
    return render_template("cliente_notificaciones.html", notificaciones=notificaciones)

# ---------------------------------------------------------------------------
# RF-06: filtrar paquetes por precio, duración y categoría (incluye la
# búsqueda de RF-05 cuando llega un destino o un texto desde esa pantalla)
# ---------------------------------------------------------------------------
@app.route("/cliente/paquetes")
@solo_rol("cliente")
def cliente_paquetes():
    q = limpiar(request.args.get("q"))
    destino_id = request.args.get("destino_id", type=int)
    categoria = request.args.get("categoria") or ""
    precio_max = request.args.get("precio_max", type=int)
    duracion_max = request.args.get("duracion_max", type=int)

    condiciones = ["p.activo = 1"]
    parametros = []
    if q:
        # RF-06/RF-28: misma normalización de tildes/mayúsculas que RF-05,
        # para que buscar "mexico" también encuentre paquetes de "México".
        condiciones.append(
            "(sin_acentos(p.nombre) LIKE sin_acentos(?) OR "
            "sin_acentos(d.nombre) LIKE sin_acentos(?) OR "
            "sin_acentos(d.pais) LIKE sin_acentos(?) OR "
            "sin_acentos(d.region) LIKE sin_acentos(?))"
        )
        patron = f"%{q}%"
        parametros += [patron, patron, patron, patron]
    if destino_id:
        condiciones.append("p.destino_id = ?")
        parametros.append(destino_id)
    if categoria in CATEGORIAS:
        condiciones.append("p.categoria = ?")
        parametros.append(categoria)
    if precio_max:
        condiciones.append("p.precio_persona <= ?")
        parametros.append(precio_max)
    if duracion_max:
        condiciones.append("p.duracion_dias <= ?")
        parametros.append(duracion_max)

    sql = (
        "SELECT p.*, d.nombre AS destino_nombre, d.pais, d.region, d.imagen AS destino_imagen, "
        "       (SELECT ROUND(AVG(puntuacion), 1) FROM calificaciones WHERE paquete_id = p.id) AS promedio "
        "FROM paquetes p JOIN destinos d ON d.id = p.destino_id "
        "WHERE " + " AND ".join(condiciones) + " ORDER BY p.nombre"
    )
    paquetes = get_db().execute(sql, parametros).fetchall()

    return render_template(
        "cliente_paquetes.html", paquetes=paquetes, categorias=CATEGORIAS,
        filtros={"q": q, "destino_id": destino_id, "categoria": categoria,
                "precio_max": precio_max, "duracion_max": duracion_max},
    )

# ---------------------------------------------------------------------------
# RF-07 y RF-09: detalle del paquete (itinerario, incluidos, precio) y
# disponibilidad de cupos por fecha. También arma el formulario de reserva
# (RF-10, RF-11) y muestra las calificaciones ya publicadas (RF-20).
# ---------------------------------------------------------------------------
@app.route("/cliente/paquetes/<int:paquete_id>")
@solo_rol("cliente")
def cliente_paquete_detalle(paquete_id):
    paquete = paquete_o_404(paquete_id)
    incluidos, itinerario, servicios, salidas, resumen, comentarios = cargar_extras_paquete(paquete_id)
    return render_template(
        "cliente_paquete_detalle.html", p=paquete, incluidos=incluidos, itinerario=itinerario,
        servicios=servicios, salidas=salidas, resumen=resumen, comentarios=comentarios,
    )

# ---------------------------------------------------------------------------
# RF-08: comparar dos o más paquetes turísticos
# ---------------------------------------------------------------------------
@app.route("/cliente/comparar")
@solo_rol("cliente")
def cliente_comparar():
    ids = [i for i in (request.args.get("ids") or "").split(",") if i.isdigit()][:4]
    paquetes = []
    for pid in ids:
        fila = get_db().execute(
            "SELECT p.*, d.nombre AS destino_nombre, d.pais, d.region, d.imagen AS destino_imagen "
            "FROM paquetes p JOIN destinos d ON d.id = p.destino_id "
            "WHERE p.id = ? AND p.activo = 1", (pid,),
        ).fetchone()
        if fila:
            incluidos, _, _, salidas, resumen, _ = cargar_extras_paquete(fila["id"])
            paquetes.append({"p": fila, "incluidos": incluidos, "salidas": salidas, "resumen": resumen})
    if len(paquetes) < 2:
        flash("Selecciona al menos dos paquetes para compararlos.", "error")
        return redirect(url_for("cliente_paquetes"))
    return render_template("cliente_comparar.html", paquetes=paquetes)

# ---------------------------------------------------------------------------
# RF-10, RF-11, RF-12, RF-15: crear una reserva
# ---------------------------------------------------------------------------
@app.route("/cliente/paquetes/<int:paquete_id>/reservar", methods=["POST"])
@solo_rol("cliente")
def cliente_reservar(paquete_id):
    paquete = paquete_o_404(paquete_id)
    db = get_db()

    salida_id = request.form.get("salida_id", type=int)
    num_personas = request.form.get("num_personas", type=int) or 0
    servicio_ids = [int(v) for v in request.form.getlist("servicios") if v.isdigit()]

    salida = db.execute(
        "SELECT * FROM paquete_salidas WHERE id = ? AND paquete_id = ?", (salida_id, paquete_id)
    ).fetchone()

    if not salida:
        flash("Elige una fecha de salida válida.", "error")
    elif num_personas < 1 or num_personas > 20:
        flash("El número de personas debe estar entre 1 y 20.", "error")
    elif num_personas > salida["cupos_disponibles"]:
        # RF-19 (impedir sobreventa): se valida aquí y otra vez al confirmar el pago.
        flash(f"Solo quedan {salida['cupos_disponibles']} cupos disponibles para esa fecha.", "error")
    else:
        servicios = db.execute(
            f"SELECT * FROM paquete_servicios WHERE paquete_id = ? AND activo = 1 "
            f"AND id IN ({','.join('?' * len(servicio_ids)) or 'NULL'})",
            [paquete_id] + servicio_ids,
        ).fetchall() if servicio_ids else []

        subtotal_paquete = paquete["precio_persona"] * num_personas
        subtotal_servicios = sum(s["precio_persona"] * num_personas for s in servicios)
        total = subtotal_paquete + subtotal_servicios
        codigo = generar_codigo_confirmacion()

        cur = db.execute(
            "INSERT INTO reservas (codigo, cliente_id, paquete_id, salida_id, num_personas, "
            "subtotal_paquete, subtotal_servicios, total) VALUES (?,?,?,?,?,?,?,?)",
            (codigo, session["usuario_id"], paquete_id, salida_id, num_personas,
             subtotal_paquete, subtotal_servicios, total),
        )
        reserva_id = cur.lastrowid
        for s in servicios:
            db.execute(
                "INSERT INTO reserva_servicios (reserva_id, servicio_id, precio_total) VALUES (?,?,?)",
                (reserva_id, s["id"], s["precio_persona"] * num_personas),
            )
        db.execute(
            "UPDATE paquete_salidas SET cupos_disponibles = cupos_disponibles - ? WHERE id = ?",
            (num_personas, salida_id),
        )
        db.commit()

        # RF-15: aviso de confirmación. No hay servidor de correo configurado
        # (misma situación que RF-03), así que el "correo" queda disponible
        # en la pantalla de la reserva con una nota que lo explica.
        flash(
            f"Reserva creada con el código {codigo}. Te mostramos el aviso de confirmación "
            "abajo porque el proyecto no tiene un servidor de correo conectado.", "ok"
        )
        return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id, nueva=1))

    return redirect(url_for("cliente_paquete_detalle", paquete_id=paquete_id))

# ---------------------------------------------------------------------------
# Listado y detalle de "Mis reservas"
# ---------------------------------------------------------------------------
@app.route("/cliente/reservas")
@solo_rol("cliente")
def cliente_reservas():
    reservas = get_db().execute(
        "SELECT r.*, p.nombre AS paquete_nombre, s.fecha AS fecha_salida "
        "FROM reservas r JOIN paquetes p ON p.id = r.paquete_id "
        "JOIN paquete_salidas s ON s.id = r.salida_id "
        "WHERE r.cliente_id = ? ORDER BY r.creado_en DESC",
        (session["usuario_id"],),
    ).fetchall()
    return render_template("cliente_reservas.html", reservas=reservas)


@app.route("/cliente/reservas/<int:reserva_id>")
@solo_rol("cliente")
def cliente_reserva_detalle(reserva_id):
    reserva = reserva_de_cliente_o_404(reserva_id)
    db = get_db()
    servicios = db.execute(
        "SELECT rs.*, ps.nombre, ps.tipo FROM reserva_servicios rs "
        "JOIN paquete_servicios ps ON ps.id = rs.servicio_id WHERE rs.reserva_id = ?",
        (reserva_id,),
    ).fetchall()
    # El cliente puede consultar el itinerario también al reservar/pagar,
    # no solo en el detalle del paquete antes de reservar.
    itinerario = db.execute(
        "SELECT * FROM paquete_itinerario WHERE paquete_id = ? ORDER BY dia_numero",
        (reserva["paquete_id"],),
    ).fetchall()
    salidas_disponibles = db.execute(
        "SELECT * FROM paquete_salidas WHERE paquete_id = ? AND id != ? "
        "AND cupos_disponibles >= ? ORDER BY fecha",
        (reserva["paquete_id"], reserva["salida_id"], reserva["num_personas"]),
    ).fetchall()
    pago = db.execute("SELECT * FROM pagos WHERE reserva_id = ? ORDER BY id DESC LIMIT 1",
                      (reserva_id,)).fetchone()
    calificacion = db.execute("SELECT * FROM calificaciones WHERE reserva_id = ?",
                              (reserva_id,)).fetchone()

    dias_restantes = dias_hasta(reserva["fecha_salida"])
    puede_cancelar = reserva["estado"] in ("pendiente", "confirmada") and dias_restantes >= reserva["plazo_cancelacion_dias"]
    puede_modificar = reserva["estado"] in ("pendiente", "confirmada") and dias_restantes >= reserva["plazo_cancelacion_dias"]
    puede_pagar = reserva["estado"] == "pendiente"
    puede_calificar = (reserva["estado"] in ("confirmada", "finalizada") and dias_restantes < 0
                      and not calificacion)

    viajeros = db.execute(
        "SELECT * FROM reserva_viajeros WHERE reserva_id = ? ORDER BY id", (reserva_id,)
    ).fetchall()

    return render_template(
        "cliente_reserva_detalle.html", r=reserva, servicios=servicios, pago=pago,
        calificacion=calificacion, salidas_disponibles=salidas_disponibles,
        dias_restantes=dias_restantes, puede_cancelar=puede_cancelar,
        puede_modificar=puede_modificar, puede_pagar=puede_pagar, puede_calificar=puede_calificar,
        cuotas_disponibles=CUOTAS_DISPONIBLES, es_nueva=request.args.get("nueva") == "1",
        viajeros=viajeros, tipos_documento=TIPOS_DOCUMENTO, itinerario=itinerario,
    )

# ---------------------------------------------------------------------------
# Registrar los datos básicos de las personas incluidas en una reserva (viajeros)
# ---------------------------------------------------------------------------
@app.route("/cliente/reservas/<int:reserva_id>/viajeros", methods=["POST"])
@solo_rol("cliente")
def cliente_reserva_viajero_agregar(reserva_id):
    reserva = reserva_de_cliente_o_404(reserva_id)
    db = get_db()

    ya_registrados = db.execute(
        "SELECT COUNT(*) AS n FROM reserva_viajeros WHERE reserva_id = ?", (reserva_id,)
    ).fetchone()["n"]
    if ya_registrados >= reserva["num_personas"]:
        flash("Ya registraste los datos de todas las personas de esta reserva.", "error")
        return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id))

    nombres = limpiar(request.form.get("nombres"))
    apellidos = limpiar(request.form.get("apellidos"))
    tipo_documento = request.form.get("tipo_documento") or ""
    numero_documento = limpiar(request.form.get("numero_documento"))

    if not nombres or len(nombres) < 2:
        flash("Escribe el nombre de la persona.", "error")
    elif not apellidos or len(apellidos) < 2:
        flash("Escribe el apellido de la persona.", "error")
    elif tipo_documento not in TIPOS_DOCUMENTO:
        flash("Elige un tipo de documento válido.", "error")
    elif not numero_documento or not re.fullmatch(r"[A-Za-z0-9-]{5,20}", numero_documento):
        flash("El número de documento debe tener entre 5 y 20 caracteres (letras, números o guion).", "error")
    else:
        db.execute(
            "INSERT INTO reserva_viajeros (reserva_id, nombres, apellidos, tipo_documento, numero_documento) "
            "VALUES (?,?,?,?,?)",
            (reserva_id, nombres, apellidos, tipo_documento, numero_documento),
        )
        db.commit()
        flash("Datos del viajero registrados.", "ok")
    return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id))


@app.route("/cliente/reservas/<int:reserva_id>/viajeros/<int:viajero_id>/eliminar", methods=["POST"])
@solo_rol("cliente")
def cliente_reserva_viajero_eliminar(reserva_id, viajero_id):
    reserva_de_cliente_o_404(reserva_id)
    db = get_db()
    db.execute(
        "DELETE FROM reserva_viajeros WHERE id = ? AND reserva_id = ?", (viajero_id, reserva_id)
    )
    db.commit()
    flash("Viajero eliminado.", "ok")
    return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id))

# ---------------------------------------------------------------------------
# RF-13: cancelar una reserva dentro de los plazos establecidos
# ---------------------------------------------------------------------------
@app.route("/cliente/reservas/<int:reserva_id>/cancelar", methods=["POST"])
@solo_rol("cliente")
def cliente_cancelar_reserva(reserva_id):
    reserva = reserva_de_cliente_o_404(reserva_id)
    dias_restantes = dias_hasta(reserva["fecha_salida"])

    if reserva["estado"] not in ("pendiente", "confirmada"):
        flash("Esta reserva ya no se puede cancelar.", "error")
    elif dias_restantes < reserva["plazo_cancelacion_dias"]:
        flash(
            f"El plazo para cancelar este paquete es de {reserva['plazo_cancelacion_dias']} días "
            "antes del viaje, y ese plazo ya se cumplió.", "error"
        )
    else:
        db = get_db()
        db.execute("UPDATE reservas SET estado = 'cancelada' WHERE id = ?", (reserva_id,))
        db.execute(
            "UPDATE paquete_salidas SET cupos_disponibles = cupos_disponibles + ? WHERE id = ?",
            (reserva["num_personas"], reserva["salida_id"]),
        )
        db.commit()
        flash("Tu reserva se canceló correctamente.", "ok")
    return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id))

# ---------------------------------------------------------------------------
# RF-14: modificar la fecha de una reserva ya realizada
# ---------------------------------------------------------------------------
@app.route("/cliente/reservas/<int:reserva_id>/modificar-fecha", methods=["POST"])
@solo_rol("cliente")
def cliente_modificar_fecha(reserva_id):
    reserva = reserva_de_cliente_o_404(reserva_id)
    dias_restantes = dias_hasta(reserva["fecha_salida"])
    nueva_salida_id = request.form.get("salida_id", type=int)
    db = get_db()

    nueva_salida = db.execute(
        "SELECT * FROM paquete_salidas WHERE id = ? AND paquete_id = ?",
        (nueva_salida_id, reserva["paquete_id"]),
    ).fetchone()

    if reserva["estado"] not in ("pendiente", "confirmada"):
        flash("Esta reserva ya no se puede modificar.", "error")
    elif dias_restantes < reserva["plazo_cancelacion_dias"]:
        flash(f"Solo puedes cambiar la fecha hasta {reserva['plazo_cancelacion_dias']} días antes del viaje.", "error")
    elif not nueva_salida or nueva_salida["id"] == reserva["salida_id"]:
        flash("Elige una fecha distinta a la actual.", "error")
    elif nueva_salida["cupos_disponibles"] < reserva["num_personas"]:
        flash("Esa fecha no tiene cupos suficientes para tu número de personas.", "error")
    else:
        db.execute(
            "UPDATE paquete_salidas SET cupos_disponibles = cupos_disponibles + ? WHERE id = ?",
            (reserva["num_personas"], reserva["salida_id"]),
        )
        db.execute(
            "UPDATE paquete_salidas SET cupos_disponibles = cupos_disponibles - ? WHERE id = ?",
            (reserva["num_personas"], nueva_salida_id),
        )
        db.execute("UPDATE reservas SET salida_id = ? WHERE id = ?", (nueva_salida_id, reserva_id))
        db.commit()
        flash("La fecha de tu reserva se actualizó correctamente.", "ok")
    return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id))

# ---------------------------------------------------------------------------
# Validación de datos de pago
# ---------------------------------------------------------------------------
RE_TARJETA = re.compile(r"^\d{16}$")
RE_VENCIMIENTO = re.compile(r"^(0[1-9]|1[0-2])/(\d{2})$")
RE_CVV = re.compile(r"^\d{3,4}$")


def validar_pago(form, permite_cuotas):
    errores = {}
    metodo = form.get("metodo")
    titular = limpiar(form.get("titular"))
    numero = re.sub(r"\s+", "", form.get("numero_tarjeta", ""))
    vencimiento = (form.get("vencimiento") or "").strip()
    cvv = (form.get("cvv") or "").strip()
    cuotas = form.get("cuotas", type=int) or 1

    if metodo not in ("credito", "debito"):
        errores["metodo"] = "Elige el tipo de tarjeta."
    if not titular or len(titular) < 3:
        errores["titular"] = "Escribe el nombre tal como aparece en la tarjeta."
    if not RE_TARJETA.match(numero):
        errores["numero_tarjeta"] = "El número de tarjeta debe tener 16 dígitos."

    match_venc = RE_VENCIMIENTO.match(vencimiento)
    if not match_venc:
        errores["vencimiento"] = "Usa el formato MM/AA."
    else:
        mes, anio = int(match_venc.group(1)), 2000 + int(match_venc.group(2))
        if (anio, mes) < (hoy().year, hoy().month):
            errores["vencimiento"] = "Esa tarjeta ya está vencida."

    if not RE_CVV.match(cvv):
        errores["cvv"] = "El código de seguridad debe tener 3 o 4 dígitos."

    if not permite_cuotas:
        cuotas = 1
    elif cuotas not in CUOTAS_DISPONIBLES:
        errores["cuotas"] = "Elige un número de cuotas válido."

    return {"metodo": metodo, "titular": titular, "final": numero[-4:] if numero else "",
            "cuotas": cuotas}, errores

# ---------------------------------------------------------------------------
# RF-16, RF-17, RF-19: pagar una reserva en línea, con o sin cuotas, validando
# el cupo una última vez antes de confirmar el pago
# ---------------------------------------------------------------------------
@app.route("/cliente/reservas/<int:reserva_id>/pagar", methods=["POST"])
@solo_rol("cliente")
def cliente_pagar_reserva(reserva_id):
    reserva = reserva_de_cliente_o_404(reserva_id)
    db = get_db()

    if reserva["estado"] != "pendiente":
        flash("Esta reserva no está pendiente de pago.", "error")
        return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id))

    datos_pago, errores = validar_pago(request.form, reserva["permite_cuotas"])

    # RF-19: se vuelve a validar el cupo justo antes de confirmar el pago,
    # por si algo cambió entre que se creó la reserva y el momento de pagar.
    salida_actual = db.execute(
        "SELECT cupos_disponibles, cupos_totales FROM paquete_salidas WHERE id = ?",
        (reserva["salida_id"],),
    ).fetchone()
    cupo_ok = salida_actual["cupos_disponibles"] >= 0

    if not cupo_ok:
        errores["general"] = "Ya no hay cupo disponible para la fecha de esta reserva."

    if errores:
        for texto in errores.values():
            flash(texto, "error")
        return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id))

    db.execute(
        "INSERT INTO pagos (reserva_id, metodo, titular, tarjeta_final, cuotas, monto) "
        "VALUES (?,?,?,?,?,?)",
        (reserva_id, datos_pago["metodo"], datos_pago["titular"], datos_pago["final"],
         datos_pago["cuotas"], reserva["total"]),
    )
    db.execute("UPDATE reservas SET estado = 'confirmada' WHERE id = ?", (reserva_id,))
    db.commit()
    flash("Pago aprobado. Ya puedes descargar tu comprobante en PDF.", "ok")
    return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id))

# ---------------------------------------------------------------------------
# RF-18: comprobante de pago en PDF
# ---------------------------------------------------------------------------
def construir_pdf_comprobante(reserva, servicios, pago):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=2 * cm, bottomMargin=2 * cm)
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("titulo", parent=estilos["Title"], textColor=colors.HexColor("#0b6e7f"))
    normal = estilos["Normal"]

    elementos = [
        Paragraph("Rumbo — Comprobante de pago", titulo),
        Spacer(1, 6),
        Paragraph(f"Código de reserva: <b>{reserva['codigo']}</b>", normal),
        Paragraph(f"Paquete: {reserva['paquete_nombre']}", normal),
        Paragraph(f"Fecha de salida: {fecha_es(reserva['fecha_salida'])}", normal),
        Paragraph(f"Número de personas: {reserva['num_personas']}", normal),
        Spacer(1, 14),
    ]

    filas = [["Concepto", "Valor"],
             ["Paquete turístico", cop(reserva["subtotal_paquete"])]]
    for s in servicios:
        filas.append([s["nombre"], cop(s["precio_total"])])
    filas.append(["Total pagado", cop(pago["monto"])])
    filas.append(["Medio de pago", f"Tarjeta {pago['metodo']} terminada en {pago['tarjeta_final']}"])
    filas.append(["Cuotas", str(pago["cuotas"])])
    filas.append(["Fecha de pago", pago["creado_en"]])

    tabla = Table(filas, colWidths=[9 * cm, 7 * cm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b6e7f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -3), (0, -3), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cddde0")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 16))
    elementos.append(Paragraph(
        "Documento generado automáticamente por Rumbo — Universidad Cooperativa de Colombia.",
        estilos["Italic"],
    ))

    doc.build(elementos)
    buffer.seek(0)
    return buffer


@app.route("/cliente/reservas/<int:reserva_id>/comprobante.pdf")
@solo_rol("cliente")
def cliente_comprobante_pdf(reserva_id):
    reserva = reserva_de_cliente_o_404(reserva_id)
    db = get_db()
    pago = db.execute("SELECT * FROM pagos WHERE reserva_id = ? ORDER BY id DESC LIMIT 1",
                      (reserva_id,)).fetchone()
    if not pago:
        abort(404)
    servicios = db.execute(
        "SELECT rs.*, ps.nombre FROM reserva_servicios rs "
        "JOIN paquete_servicios ps ON ps.id = rs.servicio_id WHERE rs.reserva_id = ?",
        (reserva_id,),
    ).fetchall()
    buffer = construir_pdf_comprobante(reserva, servicios, pago)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True,
                     download_name=f"comprobante-{reserva['codigo']}.pdf")

# ---------------------------------------------------------------------------
# RF-20: calificar y comentar un paquete después del viaje
# ---------------------------------------------------------------------------
@app.route("/cliente/reservas/<int:reserva_id>/calificar", methods=["POST"])
@solo_rol("cliente")
def cliente_calificar(reserva_id):
    reserva = reserva_de_cliente_o_404(reserva_id)
    dias_restantes = dias_hasta(reserva["fecha_salida"])
    puntuacion = request.form.get("puntuacion", type=int)
    comentario = limpiar(request.form.get("comentario"))
    db = get_db()

    ya_existe = db.execute("SELECT 1 FROM calificaciones WHERE reserva_id = ?", (reserva_id,)).fetchone()

    if reserva["estado"] not in ("confirmada", "finalizada"):
        flash("Solo puedes calificar un viaje que ya pagaste.", "error")
    elif dias_restantes >= 0:
        flash("Podrás calificar este paquete después de la fecha del viaje.", "error")
    elif ya_existe:
        flash("Ya calificaste esta reserva.", "error")
    elif puntuacion not in PUNTUACIONES:
        flash("Elige una calificación entre 1 y 5 estrellas.", "error")
    else:
        db.execute(
            "INSERT INTO calificaciones (reserva_id, paquete_id, cliente_id, puntuacion, comentario) "
            "VALUES (?,?,?,?,?)",
            (reserva_id, reserva["paquete_id"], session["usuario_id"], puntuacion, comentario),
        )
        db.execute("UPDATE reservas SET estado = 'finalizada' WHERE id = ?", (reserva_id,))
        db.commit()
        flash("¡Gracias por calificar tu viaje!", "ok")
    return redirect(url_for("cliente_reserva_detalle", reserva_id=reserva_id))

# ---------------------------------------------------------------------------
# RF-21: solicitar a un asesor mediante chat si se requiere soporte
# ---------------------------------------------------------------------------
RESPUESTA_AUTOMATICA = (
    "Gracias por escribirnos. Un asesor de Rumbo revisará tu mensaje y te responderá "
    "aquí mismo lo antes posible."
)


@app.route("/cliente/soporte", methods=["GET", "POST"])
@solo_rol("cliente")
def cliente_soporte():
    db = get_db()
    if request.method == "POST":
        texto = limpiar(request.form.get("mensaje"))
        if not texto:
            flash("Escribe un mensaje antes de enviarlo.", "error")
        else:
            db.execute(
                "INSERT INTO mensajes_soporte (cliente_id, autor, texto) VALUES (?, 'cliente', ?)",
                (session["usuario_id"], texto),
            )
            # No hay un panel de asesores conectado todavía (es un módulo de
            # administrador, RF-22 en adelante), así que el sistema confirma
            # la recepción del mensaje con una respuesta automática.
            db.execute(
                "INSERT INTO mensajes_soporte (cliente_id, autor, texto) VALUES (?, 'asesor', ?)",
                (session["usuario_id"], RESPUESTA_AUTOMATICA),
            )
            db.commit()
            return redirect(url_for("cliente_soporte"))

    mensajes = db.execute(
        "SELECT * FROM mensajes_soporte WHERE cliente_id = ? ORDER BY id", (session["usuario_id"],)
    ).fetchall()
    return render_template("cliente_soporte.html", mensajes=mensajes)


# ---------------------------------------------------------------------------
# Utilidades del módulo de administrador (RF-22 a RF-25)
# ---------------------------------------------------------------------------
def paquete_admin_o_404(paquete_id):
    """Como paquete_o_404, pero el administrador también puede ver y editar
    paquetes desactivados (activo = 0)."""
    fila = get_db().execute(
        "SELECT p.*, d.nombre AS destino_nombre, d.pais, d.region "
        "FROM paquetes p JOIN destinos d ON d.id = p.destino_id WHERE p.id = ?",
        (paquete_id,),
    ).fetchone()
    if not fila:
        abort(404)
    return fila


def validar_paquete(form, destinos_validos):
    datos = {
        "destino_id": form.get("destino_id", type=int),
        "nombre": limpiar(form.get("nombre")),
        "categoria": form.get("categoria") or "",
        "resumen": limpiar(form.get("resumen")),
        "duracion_dias": form.get("duracion_dias", type=int),
        "precio_persona": form.get("precio_persona", type=int),
        "permite_cuotas": 1 if form.get("permite_cuotas") == "on" else 0,
        "plazo_cancelacion_dias": form.get("plazo_cancelacion_dias", type=int),
    }
    errores = {}

    if datos["destino_id"] not in destinos_validos:
        errores["destino_id"] = "Elige un destino válido."
    if not datos["nombre"] or len(datos["nombre"]) < 3:
        errores["nombre"] = "Escribe el nombre del paquete (mínimo 3 caracteres)."
    if datos["categoria"] not in CATEGORIAS:
        errores["categoria"] = "Elige una categoría válida."
    if not datos["resumen"] or len(datos["resumen"]) < 10:
        errores["resumen"] = "Escribe una descripción breve (mínimo 10 caracteres)."
    if not datos["duracion_dias"] or not (1 <= datos["duracion_dias"] <= 60):
        errores["duracion_dias"] = "La duración debe ser entre 1 y 60 días."
    if not datos["precio_persona"] or datos["precio_persona"] <= 0:
        errores["precio_persona"] = "Escribe un precio por persona mayor a cero."
    if datos["plazo_cancelacion_dias"] is None or not (0 <= datos["plazo_cancelacion_dias"] <= 60):
        errores["plazo_cancelacion_dias"] = "El plazo de cancelación debe estar entre 0 y 60 días."

    return datos, errores


def validar_proveedor(form, destinos_validos):
    datos = {
        "destino_id": form.get("destino_id", type=int),
        "tipo": form.get("tipo") or "",
        "nombre": limpiar(form.get("nombre")),
        "direccion": limpiar(form.get("direccion")),
        "capacidad": form.get("capacidad", type=int),
        "contacto": limpiar(form.get("contacto")),
    }
    errores = {}

    if datos["destino_id"] not in destinos_validos:
        errores["destino_id"] = "Elige un destino válido."
    if datos["tipo"] not in ("hotel", "restaurante"):
        errores["tipo"] = "Elige el tipo de proveedor."
    if not datos["nombre"] or len(datos["nombre"]) < 2:
        errores["nombre"] = "Escribe el nombre del proveedor."
    if datos["capacidad"] is None or datos["capacidad"] < 0:
        errores["capacidad"] = "Escribe una capacidad válida (0 o más)."

    return datos, errores

# ---------------------------------------------------------------------------
# RF-23: el administrador crea, edita y elimina paquetes turísticos
# ---------------------------------------------------------------------------
@app.route("/administrador/paquetes")
@solo_rol("administrador")
def admin_paquetes():
    db = get_db()
    paquetes = db.execute(
        "SELECT p.*, d.nombre AS destino_nombre FROM paquetes p "
        "JOIN destinos d ON d.id = p.destino_id ORDER BY p.activo DESC, p.nombre"
    ).fetchall()
    # RF-43: estado operativo de cada paquete, visible también en el listado.
    operativos = {p["id"]: estado_operativo_paquete(db, p["id"])["listo"] for p in paquetes}
    return render_template("admin_paquetes.html", paquetes=paquetes, operativos=operativos)


@app.route("/administrador/paquetes/nuevo", methods=["GET", "POST"])
@solo_rol("administrador")
def admin_paquete_nuevo():
    db = get_db()
    destinos = db.execute("SELECT * FROM destinos ORDER BY nombre").fetchall()
    destinos_validos = {d["id"] for d in destinos}
    datos = {"destino_id": "", "nombre": "", "categoria": "", "resumen": "",
             "duracion_dias": "", "precio_persona": "", "permite_cuotas": 0,
             "plazo_cancelacion_dias": 5}
    errores = {}

    if request.method == "POST":
        datos, errores = validar_paquete(request.form, destinos_validos)
        if not errores:
            cur = db.execute(
                "INSERT INTO paquetes (destino_id, nombre, categoria, resumen, duracion_dias, "
                "precio_persona, permite_cuotas, plazo_cancelacion_dias) VALUES (?,?,?,?,?,?,?,?)",
                (datos["destino_id"], datos["nombre"], datos["categoria"], datos["resumen"],
                 datos["duracion_dias"], datos["precio_persona"], datos["permite_cuotas"],
                 datos["plazo_cancelacion_dias"]),
            )
            db.commit()
            flash("Paquete creado. Ahora agrega el itinerario, los incluidos, los servicios "
                  "adicionales y al menos una fecha de salida para que quede visible al cliente.", "ok")
            return redirect(url_for("admin_paquete_editar", paquete_id=cur.lastrowid))

    return render_template("admin_paquete_formulario.html", modo="nuevo", destinos=destinos,
                           categorias=CATEGORIAS, datos=datos, errores=errores)


@app.route("/administrador/paquetes/<int:paquete_id>/editar", methods=["GET", "POST"])
@solo_rol("administrador")
def admin_paquete_editar(paquete_id):
    paquete = paquete_admin_o_404(paquete_id)
    db = get_db()
    destinos = db.execute("SELECT * FROM destinos ORDER BY nombre").fetchall()
    destinos_validos = {d["id"] for d in destinos}
    datos = dict(paquete)
    errores = {}

    if request.method == "POST" and request.form.get("accion") == "datos":
        anterior = dict(paquete)
        datos, errores = validar_paquete(request.form, destinos_validos)
        if not errores:
            db.execute(
                "UPDATE paquetes SET destino_id=?, nombre=?, categoria=?, resumen=?, "
                "duracion_dias=?, precio_persona=?, permite_cuotas=?, plazo_cancelacion_dias=? "
                "WHERE id=?",
                (datos["destino_id"], datos["nombre"], datos["categoria"], datos["resumen"],
                 datos["duracion_dias"], datos["precio_persona"], datos["permite_cuotas"],
                 datos["plazo_cancelacion_dias"], paquete_id),
            )
            db.commit()
            # RF-22: la pantalla de notificaciones promete avisar sobre "cambios de
            # itinerario o de información del destino" en los paquetes ya reservados.
            # Cualquier cambio en los datos generales (destino, precio, duración,
            # nombre, categoría, cuotas o plazo de cancelación) afecta el viaje del
            # cliente, así que se notifica por cada campo que realmente cambió.
            cambios = []
            if datos["destino_id"] != anterior["destino_id"]:
                nuevo_destino = db.execute(
                    "SELECT nombre FROM destinos WHERE id = ?", (datos["destino_id"],)
                ).fetchone()
                cambios.append(f"el destino ahora es {nuevo_destino['nombre']}")
            if datos["nombre"] != anterior["nombre"]:
                cambios.append(f"el paquete pasó a llamarse \"{datos['nombre']}\"")
            if datos["precio_persona"] != anterior["precio_persona"]:
                cambios.append(
                    f"el precio por persona cambió de {cop(anterior['precio_persona'])} "
                    f"a {cop(datos['precio_persona'])}"
                )
            if datos["duracion_dias"] != anterior["duracion_dias"]:
                cambios.append(f"la duración ahora es de {datos['duracion_dias']} días")
            if datos["categoria"] != anterior["categoria"]:
                cambios.append(f"la categoría cambió a {datos['categoria']}")
            if datos["plazo_cancelacion_dias"] != anterior["plazo_cancelacion_dias"]:
                cambios.append(
                    f"el plazo de cancelación ahora es de {datos['plazo_cancelacion_dias']} días"
                )
            if datos["permite_cuotas"] != anterior["permite_cuotas"]:
                cambios.append(
                    "ahora permite pago en cuotas" if datos["permite_cuotas"]
                    else "ya no permite pago en cuotas"
                )

            if cambios:
                texto_cambios = "; ".join(cambios)
                avisados = notificar_clientes_paquete(
                    paquete_id,
                    f"Se actualizó la información de tu paquete \"{anterior['nombre']}\": "
                    f"{texto_cambios}.",
                )
                flash(f"Los datos generales del paquete se actualizaron correctamente. "
                      f"Se notificó a {avisados} cliente(s) con reservas activas por los "
                      "cambios.", "ok")
            else:
                flash("Los datos generales del paquete se actualizaron correctamente.", "ok")
            return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))
        datos["id"] = paquete_id

    incluidos, itinerario, servicios, salidas, resumen_calif, _ = cargar_extras_paquete(paquete_id)
    versiones = []
    for v in db.execute(
        "SELECT * FROM paquete_versiones WHERE paquete_id=? ORDER BY id DESC", (paquete_id,)
    ).fetchall():
        fila = dict(v)
        try:
            ids = json.loads(fila["servicios_ids"] or "[]")
        except (TypeError, ValueError):
            ids = []
        fila["servicios"] = [
            next((dict(serv) for serv in servicios if serv["id"] == sid), None)
            for sid in ids
        ]
        fila["servicios"] = [x for x in fila["servicios"] if x]
        versiones.append(fila)

    # RF-43/RF-44/RF-46: estado operativo, promociones y costos del paquete.
    promociones = db.execute(
        "SELECT * FROM promociones WHERE paquete_id = ? ORDER BY activa DESC, fecha_inicio DESC",
        (paquete_id,),
    ).fetchall()
    costos = db.execute(
        "SELECT * FROM paquete_costos WHERE paquete_id = ? ORDER BY categoria, creado_en DESC",
        (paquete_id,),
    ).fetchall()
    total_costos = sum(c["monto"] for c in costos)
    estado_operativo = estado_operativo_paquete(db, paquete_id)

    return render_template(
        "admin_paquete_editar.html", p=paquete, datos=datos, errores=errores, destinos=destinos,
        categorias=CATEGORIAS, tipos_servicio=TIPOS_SERVICIO, incluidos=incluidos,
        itinerario=itinerario, servicios=servicios, salidas=salidas, resumen_calif=resumen_calif,
        versiones=versiones, promociones=promociones, costos=costos, total_costos=total_costos,
        categorias_costo=CATEGORIAS_COSTO, estado_operativo=estado_operativo,
    )


@app.route("/administrador/paquetes/<int:paquete_id>/versiones", methods=["POST"])
@solo_rol("administrador")
def admin_paquete_version_crear(paquete_id):
    paquete = paquete_admin_o_404(paquete_id)
    db = get_db()
    nombre_version = limpiar(request.form.get("nombre_version"))
    duracion = request.form.get("duracion_dias", type=int)
    costo = request.form.get("costo_total", type=int)
    servicios_ids = request.form.getlist("servicios_ids", type=int)

    if not nombre_version:
        flash("Escribe un nombre para la versión.", "error")
        return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))
    if not duracion or duracion < 1:
        flash("La duración de la versión debe ser de al menos 1 día.", "error")
        return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))
    if costo is None or costo < 0:
        flash("El costo de la versión no puede ser negativo.", "error")
        return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))

    servicios_validos = {
        row["id"] for row in db.execute(
            "SELECT id FROM paquete_servicios WHERE paquete_id = ? AND activo = 1",
            (paquete_id,),
        ).fetchall()
    }
    if any(sid not in servicios_validos for sid in servicios_ids):
        flash("La versión contiene un servicio que no pertenece a este paquete.", "error")
        return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))

    db.execute(
        "INSERT INTO paquete_versiones "
        "(paquete_id, nombre_version, duracion_dias, costo_total, servicios_ids) "
        "VALUES (?,?,?,?,?)",
        (paquete_id, nombre_version, duracion, costo, json.dumps(servicios_ids)),
    )
    db.commit()
    flash(f"Versión \"{nombre_version}\" guardada como borrador.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/versiones/<int:version_id>/publicar", methods=["POST"])
@solo_rol("administrador")
def admin_paquete_version_publicar(paquete_id, version_id):
    paquete = paquete_admin_o_404(paquete_id)
    db = get_db()
    version = db.execute(
        "SELECT * FROM paquete_versiones WHERE id = ? AND paquete_id = ?",
        (version_id, paquete_id),
    ).fetchone()
    if not version:
        abort(404)

    try:
        servicios_ids = json.loads(version["servicios_ids"] or "[]")
    except (TypeError, ValueError):
        servicios_ids = []

    servicios_validos = {
        row["id"] for row in db.execute(
            "SELECT id FROM paquete_servicios WHERE paquete_id = ?",
            (paquete_id,),
        ).fetchall()
    }
    if any(sid not in servicios_validos for sid in servicios_ids):
        flash("No se pudo publicar: la versión contiene servicios que ya no existen.", "error")
        return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))

    # La versión publicada se convierte en los datos definitivos de duración,
    # costo y combinación de servicios del paquete.
    db.execute(
        "UPDATE paquetes SET duracion_dias=?, precio_persona=? WHERE id=?",
        (version["duracion_dias"], version["costo_total"], paquete_id),
    )
    db.execute(
        "UPDATE paquete_servicios SET activo = CASE WHEN id IN ({}) THEN 1 ELSE 0 END "
        "WHERE paquete_id = ?".format(",".join("?" for _ in servicios_validos) or "NULL"),
        (*sorted(servicios_validos), paquete_id),
    )
    if servicios_validos:
        # La consulta anterior funciona con la lista completa de servicios; esta
        # segunda actualización evita depender de una lista vacía para el IN.
        db.execute(
            "UPDATE paquete_servicios SET activo=0 WHERE paquete_id=?",
            (paquete_id,),
        )
        if servicios_ids:
            db.execute(
                "UPDATE paquete_servicios SET activo=1 WHERE paquete_id=? AND id IN ({})".format(
                    ",".join("?" for _ in servicios_ids)
                ),
                (paquete_id, *servicios_ids),
            )

    db.execute(
        "UPDATE paquete_versiones SET estado='borrador' WHERE paquete_id=?",
        (paquete_id,),
    )
    db.execute(
        "UPDATE paquete_versiones SET estado='publicada' WHERE id=?",
        (version_id,),
    )
    db.commit()
    flash(
        f"La versión \"{version['nombre_version']}\" quedó publicada como versión definitiva "
        "del paquete.",
        "ok",
    )
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/versiones/<int:version_id>/eliminar", methods=["POST"])
@solo_rol("administrador")
def admin_paquete_version_eliminar(paquete_id, version_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    db.execute(
        "DELETE FROM paquete_versiones WHERE id=? AND paquete_id=? AND estado='borrador'",
        (version_id, paquete_id),
    )
    db.commit()
    flash("Borrador eliminado.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/eliminar", methods=["POST"])
@solo_rol("administrador")
def admin_paquete_eliminar(paquete_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    db.execute("UPDATE paquetes SET activo = 0 WHERE id = ?", (paquete_id,))
    db.commit()
    flash("El paquete se eliminó: ya no aparece en el catálogo de los clientes.", "ok")
    return redirect(url_for("admin_paquetes"))


@app.route("/administrador/paquetes/<int:paquete_id>/reactivar", methods=["POST"])
@solo_rol("administrador")
def admin_paquete_reactivar(paquete_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    db.execute("UPDATE paquetes SET activo = 1 WHERE id = ?", (paquete_id,))
    db.commit()
    flash("El paquete se reactivó y volvió a aparecer en el catálogo.", "ok")
    return redirect(url_for("admin_paquetes"))


# --- Itinerario del paquete (parte de RF-23; dispara la notificación de RF-22) ---
@app.route("/administrador/paquetes/<int:paquete_id>/itinerario/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_itinerario_agregar(paquete_id):
    paquete = paquete_admin_o_404(paquete_id)
    db = get_db()
    dia = request.form.get("dia_numero", type=int)
    titulo = limpiar(request.form.get("titulo"))
    descripcion = limpiar(request.form.get("descripcion"))

    if not dia or dia < 1 or not titulo:
        flash("Escribe el número de día y el título de la actividad.", "error")
    else:
        db.execute(
            "INSERT INTO paquete_itinerario (paquete_id, dia_numero, titulo, descripcion) "
            "VALUES (?,?,?,?)",
            (paquete_id, dia, titulo, descripcion),
        )
        db.commit()
        avisados = notificar_clientes_paquete(
            paquete_id,
            f"Se actualizó el itinerario de tu paquete \"{paquete['nombre']}\": "
            f"nueva actividad en el día {dia} ({titulo}).",
        )
        flash(f"Actividad agregada al itinerario. Se notificó a {avisados} cliente(s) "
              "con reservas activas.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/itinerario/<int:item_id>/eliminar", methods=["POST"])
@solo_rol("administrador")
def admin_itinerario_eliminar(paquete_id, item_id):
    paquete = paquete_admin_o_404(paquete_id)
    db = get_db()
    db.execute("DELETE FROM paquete_itinerario WHERE id = ? AND paquete_id = ?", (item_id, paquete_id))
    db.commit()
    notificar_clientes_paquete(
        paquete_id, f"Se actualizó el itinerario de tu paquete \"{paquete['nombre']}\"."
    )
    flash("Actividad eliminada del itinerario. Se notificó a los clientes con reservas activas.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


# --- Incluidos del paquete (parte de RF-23) ---
@app.route("/administrador/paquetes/<int:paquete_id>/incluidos/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_incluido_agregar(paquete_id):
    paquete_admin_o_404(paquete_id)
    texto = limpiar(request.form.get("texto"))
    if not texto:
        flash("Escribe qué incluye el paquete.", "error")
    else:
        db = get_db()
        orden = db.execute(
            "SELECT COALESCE(MAX(orden), -1) + 1 AS n FROM paquete_incluidos WHERE paquete_id = ?",
            (paquete_id,),
        ).fetchone()["n"]
        db.execute("INSERT INTO paquete_incluidos (paquete_id, texto, orden) VALUES (?,?,?)",
                  (paquete_id, texto, orden))
        db.commit()
        flash("Se agregó un elemento incluido en el paquete.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/incluidos/<int:item_id>/eliminar", methods=["POST"])
@solo_rol("administrador")
def admin_incluido_eliminar(paquete_id, item_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    db.execute("DELETE FROM paquete_incluidos WHERE id = ? AND paquete_id = ?", (item_id, paquete_id))
    db.commit()
    flash("Elemento incluido eliminado.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


# --- Servicios adicionales del paquete (parte de RF-23) ---
@app.route("/administrador/paquetes/<int:paquete_id>/servicios/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_servicio_agregar(paquete_id):
    paquete_admin_o_404(paquete_id)
    tipo = request.form.get("tipo") or ""
    nombre = limpiar(request.form.get("nombre"))
    precio = request.form.get("precio_persona", type=int)

    if tipo not in TIPOS_SERVICIO:
        flash("Elige un tipo de servicio válido.", "error")
    elif not nombre:
        flash("Escribe el nombre del servicio adicional.", "error")
    elif not precio or precio <= 0:
        flash("Escribe un precio por persona mayor a cero.", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO paquete_servicios (paquete_id, tipo, nombre, precio_persona) VALUES (?,?,?,?)",
            (paquete_id, tipo, nombre, precio),
        )
        db.commit()
        flash("Servicio adicional agregado.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/servicios/<int:item_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_servicio_estado(paquete_id, item_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    servicio = db.execute(
        "SELECT * FROM paquete_servicios WHERE id = ? AND paquete_id = ?", (item_id, paquete_id)
    ).fetchone()
    if servicio:
        db.execute("UPDATE paquete_servicios SET activo = ? WHERE id = ?",
                  (0 if servicio["activo"] else 1, item_id))
        db.commit()
        flash("Se actualizó el estado del servicio adicional.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


# --- Fechas de salida y cupos del paquete (parte de RF-23) ---
@app.route("/administrador/paquetes/<int:paquete_id>/salidas/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_salida_agregar(paquete_id):
    paquete_admin_o_404(paquete_id)
    fecha = (request.form.get("fecha") or "").strip()
    cupos = request.form.get("cupos_totales", type=int)
    db = get_db()

    try:
        datetime.strptime(fecha, "%Y-%m-%d")
        fecha_valida = True
    except ValueError:
        fecha_valida = False

    if not fecha_valida:
        flash("Escribe una fecha de salida válida.", "error")
    elif not cupos or cupos < 1:
        flash("Escribe una cantidad de cupos mayor a cero.", "error")
    else:
        try:
            db.execute(
                "INSERT INTO paquete_salidas (paquete_id, fecha, cupos_totales, cupos_disponibles) "
                "VALUES (?,?,?,?)",
                (paquete_id, fecha, cupos, cupos),
            )
            db.commit()
            flash("Fecha de salida agregada.", "ok")
        except sqlite3.IntegrityError:
            flash("Ese paquete ya tiene una fecha de salida igual a esa.", "error")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/salidas/<int:salida_id>/actualizar", methods=["POST"])
@solo_rol("administrador")
def admin_salida_actualizar(paquete_id, salida_id):
    """RF-45: el administrador actualiza la disponibilidad de cupos de una
    fecha de salida ya existente (no solo puede agregar fechas nuevas)."""
    paquete_admin_o_404(paquete_id)
    db = get_db()
    salida = db.execute(
        "SELECT * FROM paquete_salidas WHERE id = ? AND paquete_id = ?", (salida_id, paquete_id)
    ).fetchone()
    if not salida:
        abort(404)

    nuevo_total = request.form.get("cupos_totales", type=int)
    ocupadas = salida["cupos_totales"] - salida["cupos_disponibles"]

    if not nuevo_total or nuevo_total < 1:
        flash("Escribe una cantidad de cupos totales mayor a cero.", "error")
    elif nuevo_total < ocupadas:
        flash(
            f"No puedes bajar los cupos totales a {nuevo_total}: ya hay {ocupadas} cupos "
            "ocupados por reservas pagadas para esa fecha.", "error",
        )
    else:
        db.execute(
            "UPDATE paquete_salidas SET cupos_totales = ?, cupos_disponibles = ? WHERE id = ?",
            (nuevo_total, nuevo_total - ocupadas, salida_id),
        )
        db.commit()
        flash(f"Cupos actualizados: ahora hay {nuevo_total - ocupadas} disponibles para el "
              f"{salida['fecha']}.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))

# ---------------------------------------------------------------------------
# RF-44: el administrador crea, modifica, activa y desactiva promociones
# ---------------------------------------------------------------------------
def validar_promocion(form):
    datos = {
        "nombre": limpiar(form.get("nombre")),
        "codigo": limpiar(form.get("codigo")).upper(),
        "tipo": form.get("tipo") or "",
        "valor": form.get("valor", type=int),
        "fecha_inicio": (form.get("fecha_inicio") or "").strip(),
        "fecha_fin": (form.get("fecha_fin") or "").strip(),
    }
    errores = {}
    if not datos["nombre"] or len(datos["nombre"]) < 3:
        errores["nombre"] = "Escribe un nombre para la promoción."
    if datos["tipo"] not in ("porcentaje", "monto_fijo"):
        errores["tipo"] = "Elige el tipo de promoción."
    if datos["valor"] is None or datos["valor"] <= 0:
        errores["valor"] = "Escribe un valor mayor a cero."
    elif datos["tipo"] == "porcentaje" and datos["valor"] > 100:
        errores["valor"] = "Un descuento porcentual no puede ser mayor a 100."
    try:
        fi = datetime.strptime(datos["fecha_inicio"], "%Y-%m-%d").date()
        ff = datetime.strptime(datos["fecha_fin"], "%Y-%m-%d").date()
        if ff < fi:
            errores["fecha_fin"] = "La fecha de fin debe ser igual o posterior a la de inicio."
    except ValueError:
        errores["fecha_inicio"] = "Escribe fechas de inicio y fin válidas."
    return datos, errores


@app.route("/administrador/paquetes/<int:paquete_id>/promociones/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_promocion_agregar(paquete_id):
    paquete_admin_o_404(paquete_id)
    datos, errores = validar_promocion(request.form)
    if errores:
        flash(next(iter(errores.values())), "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO promociones (paquete_id, nombre, codigo, tipo, valor, fecha_inicio, fecha_fin) "
            "VALUES (?,?,?,?,?,?,?)",
            (paquete_id, datos["nombre"], datos["codigo"], datos["tipo"], datos["valor"],
             datos["fecha_inicio"], datos["fecha_fin"]),
        )
        db.commit()
        flash("Promoción creada correctamente.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


@app.route("/administrador/promociones/<int:promocion_id>/editar", methods=["POST"])
@solo_rol("administrador")
def admin_promocion_editar(promocion_id):
    db = get_db()
    promo = db.execute("SELECT * FROM promociones WHERE id = ?", (promocion_id,)).fetchone()
    if not promo:
        abort(404)
    datos, errores = validar_promocion(request.form)
    if errores:
        flash(next(iter(errores.values())), "error")
    else:
        db.execute(
            "UPDATE promociones SET nombre=?, codigo=?, tipo=?, valor=?, fecha_inicio=?, fecha_fin=? "
            "WHERE id=?",
            (datos["nombre"], datos["codigo"], datos["tipo"], datos["valor"],
             datos["fecha_inicio"], datos["fecha_fin"], promocion_id),
        )
        db.commit()
        flash("Promoción modificada correctamente.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=promo["paquete_id"]))


@app.route("/administrador/promociones/<int:promocion_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_promocion_estado(promocion_id):
    db = get_db()
    promo = db.execute("SELECT * FROM promociones WHERE id = ?", (promocion_id,)).fetchone()
    if not promo:
        abort(404)
    db.execute("UPDATE promociones SET activa = ? WHERE id = ?", (0 if promo["activa"] else 1, promocion_id))
    db.commit()
    flash("Promoción activada." if not promo["activa"] else "Promoción desactivada.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=promo["paquete_id"]))

# ---------------------------------------------------------------------------
# RF-46: el administrador registra y actualiza los costos de cada paquete
# ---------------------------------------------------------------------------
CATEGORIAS_COSTO = {
    "alojamiento": "Alojamiento", "transporte": "Transporte", "vuelos": "Vuelos",
    "actividades": "Actividades", "otros": "Otros",
}


@app.route("/administrador/paquetes/<int:paquete_id>/costos/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_costo_agregar(paquete_id):
    paquete_admin_o_404(paquete_id)
    categoria = request.form.get("categoria") or ""
    descripcion = limpiar(request.form.get("descripcion"))
    monto = request.form.get("monto", type=int)

    if categoria not in CATEGORIAS_COSTO:
        flash("Elige una categoría de costo válida.", "error")
    elif not descripcion:
        flash("Describe a qué corresponde este costo.", "error")
    elif monto is None or monto < 0:
        flash("Escribe un monto válido (0 o más).", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO paquete_costos (paquete_id, categoria, descripcion, monto) VALUES (?,?,?,?)",
            (paquete_id, categoria, descripcion, monto),
        )
        db.commit()
        flash("Costo registrado correctamente.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/costos/<int:costo_id>/eliminar", methods=["POST"])
@solo_rol("administrador")
def admin_costo_eliminar(paquete_id, costo_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    db.execute("DELETE FROM paquete_costos WHERE id = ? AND paquete_id = ?", (costo_id, paquete_id))
    db.commit()
    flash("Costo eliminado.", "ok")
    return redirect(url_for("admin_paquete_editar", paquete_id=paquete_id))

# ---------------------------------------------------------------------------
# RF-43: estado operativo de un paquete, antes de habilitarlo para reservas
# ---------------------------------------------------------------------------
def estado_operativo_paquete(db, paquete_id):
    problemas = []
    salidas = db.execute(
        "SELECT * FROM paquete_salidas WHERE paquete_id = ? AND fecha >= date('now')", (paquete_id,)
    ).fetchall()
    if not salidas:
        problemas.append("No tiene fechas de salida futuras.")
    elif not any(s["cupos_disponibles"] > 0 for s in salidas):
        problemas.append("Todas sus fechas de salida futuras ya están sin cupos.")

    n_itinerario = db.execute(
        "SELECT COUNT(*) AS n FROM paquete_itinerario WHERE paquete_id = ?", (paquete_id,)
    ).fetchone()["n"]
    if not n_itinerario:
        problemas.append("No tiene actividades registradas en el itinerario.")

    n_incluidos = db.execute(
        "SELECT COUNT(*) AS n FROM paquete_incluidos WHERE paquete_id = ?", (paquete_id,)
    ).fetchone()["n"]
    if not n_incluidos:
        problemas.append("No tiene elementos marcados como incluidos.")

    return {"listo": not problemas, "problemas": problemas}

# ---------------------------------------------------------------------------
# RF-47: pagos a proveedores (hoteles, transportadores y demás proveedores)
# ---------------------------------------------------------------------------
TIPOS_PAGO_PROVEEDOR = {
    "hotel": "Hotel", "transportador": "Transportador", "aerolinea": "Aerolínea", "otro": "Otro",
}


def validar_pago_proveedor(form):
    datos = {
        "paquete_id": form.get("paquete_id", type=int) or None,
        "tipo_proveedor": form.get("tipo_proveedor") or "",
        "nombre_proveedor": limpiar(form.get("nombre_proveedor")),
        "concepto": limpiar(form.get("concepto")),
        "monto": form.get("monto", type=int),
    }
    errores = {}
    if datos["tipo_proveedor"] not in TIPOS_PAGO_PROVEEDOR:
        errores["tipo_proveedor"] = "Elige el tipo de proveedor."
    if not datos["nombre_proveedor"]:
        errores["nombre_proveedor"] = "Escribe el nombre del proveedor."
    if not datos["concepto"]:
        errores["concepto"] = "Describe el concepto del pago."
    if datos["monto"] is None or datos["monto"] <= 0:
        errores["monto"] = "Escribe un monto mayor a cero."
    return datos, errores


@app.route("/administrador/pagos-proveedores")
@solo_rol("administrador")
def admin_pagos_proveedores():
    db = get_db()
    filtro_estado = request.args.get("estado") or ""
    sql = (
        "SELECT pp.*, p.nombre AS paquete_nombre FROM pagos_proveedores pp "
        "LEFT JOIN paquetes p ON p.id = pp.paquete_id "
    )
    params = []
    if filtro_estado in ("pendiente", "pagado"):
        sql += "WHERE pp.estado = ? "
        params.append(filtro_estado)
    sql += "ORDER BY pp.estado, pp.creado_en DESC"
    pagos = db.execute(sql, params).fetchall()

    totales = db.execute(
        "SELECT estado, COALESCE(SUM(monto), 0) AS total FROM pagos_proveedores GROUP BY estado"
    ).fetchall()
    total_pendiente = next((t["total"] for t in totales if t["estado"] == "pendiente"), 0)
    total_pagado = next((t["total"] for t in totales if t["estado"] == "pagado"), 0)

    paquetes = db.execute("SELECT id, nombre FROM paquetes WHERE activo = 1 ORDER BY nombre").fetchall()
    return render_template(
        "admin_pagos_proveedores.html", pagos=pagos, tipos=TIPOS_PAGO_PROVEEDOR,
        paquetes=paquetes, filtro_estado=filtro_estado,
        total_pendiente=total_pendiente, total_pagado=total_pagado,
    )


@app.route("/administrador/pagos-proveedores/nuevo", methods=["POST"])
@solo_rol("administrador")
def admin_pago_proveedor_nuevo():
    datos, errores = validar_pago_proveedor(request.form)
    if errores:
        flash(next(iter(errores.values())), "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO pagos_proveedores (paquete_id, tipo_proveedor, nombre_proveedor, "
            "concepto, monto) VALUES (?,?,?,?,?)",
            (datos["paquete_id"], datos["tipo_proveedor"], datos["nombre_proveedor"],
             datos["concepto"], datos["monto"]),
        )
        db.commit()
        flash("Pago a proveedor registrado como pendiente.", "ok")
    return redirect(url_for("admin_pagos_proveedores"))


@app.route("/administrador/pagos-proveedores/<int:pago_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_pago_proveedor_estado(pago_id):
    db = get_db()
    pago = db.execute("SELECT * FROM pagos_proveedores WHERE id = ?", (pago_id,)).fetchone()
    if not pago:
        abort(404)
    if pago["estado"] == "pendiente":
        db.execute(
            "UPDATE pagos_proveedores SET estado='pagado', fecha_pago=? WHERE id=?",
            (hoy().isoformat(), pago_id),
        )
        flash("Pago marcado como pagado.", "ok")
    else:
        db.execute("UPDATE pagos_proveedores SET estado='pendiente', fecha_pago=NULL WHERE id=?", (pago_id,))
        flash("Pago marcado nuevamente como pendiente.", "ok")
    db.commit()
    return redirect(url_for("admin_pagos_proveedores"))

# ---------------------------------------------------------------------------
# RF-48: el administrador consulta, actualiza y gestiona las cuentas de los
# clientes registrados
# ---------------------------------------------------------------------------
@app.route("/administrador/clientes")
@solo_rol("administrador")
def admin_clientes():
    db = get_db()
    q = limpiar(request.args.get("q"))
    sql = (
        "SELECT u.*, "
        "(SELECT COUNT(*) FROM reservas r WHERE r.cliente_id = u.id) AS num_reservas "
        "FROM usuarios u WHERE u.rol = 'cliente' "
    )
    params = []
    if q:
        sql += "AND (u.nombres LIKE ? OR u.apellidos LIKE ? OR u.correo LIKE ?) "
        patron = f"%{q}%"
        params += [patron, patron, patron]
    sql += "ORDER BY u.creado_en DESC"
    clientes = db.execute(sql, params).fetchall()
    return render_template("admin_clientes.html", clientes=clientes, q=q)


@app.route("/administrador/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@solo_rol("administrador")
def admin_cliente_editar(cliente_id):
    db = get_db()
    cliente = db.execute(
        "SELECT * FROM usuarios WHERE id = ? AND rol = 'cliente'", (cliente_id,)
    ).fetchone()
    if not cliente:
        abort(404)
    datos = dict(cliente)
    errores = {}

    if request.method == "POST":
        datos["nombres"] = limpiar(request.form.get("nombres"))
        datos["apellidos"] = limpiar(request.form.get("apellidos"))
        datos["correo"] = (request.form.get("correo") or "").strip().lower()
        if not datos["nombres"] or len(datos["nombres"]) < 2:
            errores["nombres"] = "Escribe los nombres del cliente."
        if not datos["apellidos"] or len(datos["apellidos"]) < 2:
            errores["apellidos"] = "Escribe los apellidos del cliente."
        if not datos["correo"] or not RE_CORREO.match(datos["correo"]):
            errores["correo"] = "Escribe un correo válido."
        if not errores:
            try:
                db.execute(
                    "UPDATE usuarios SET nombres=?, apellidos=?, correo=? WHERE id=?",
                    (datos["nombres"], datos["apellidos"], datos["correo"], cliente_id),
                )
                db.commit()
                flash("Los datos del cliente se actualizaron correctamente.", "ok")
                return redirect(url_for("admin_clientes"))
            except sqlite3.IntegrityError:
                errores["correo"] = "Ese correo ya lo usa otra cuenta."
        datos["id"] = cliente_id

    reservas = db.execute(
        "SELECT r.*, p.nombre AS paquete_nombre FROM reservas r "
        "JOIN paquetes p ON p.id = r.paquete_id WHERE r.cliente_id = ? ORDER BY r.creado_en DESC",
        (cliente_id,),
    ).fetchall()
    return render_template("admin_cliente_editar.html", datos=datos, errores=errores,
                           cliente=cliente, reservas=reservas)


@app.route("/administrador/clientes/<int:cliente_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_cliente_estado(cliente_id):
    db = get_db()
    cliente = db.execute(
        "SELECT * FROM usuarios WHERE id = ? AND rol = 'cliente'", (cliente_id,)
    ).fetchone()
    if not cliente:
        abort(404)
    nuevo_estado = "inactivo" if cliente["estado"] == "activo" else "activo"
    db.execute("UPDATE usuarios SET estado = ? WHERE id = ?", (nuevo_estado, cliente_id))
    db.commit()
    flash(
        f"La cuenta de {cliente['nombres']} quedó {nuevo_estado}.",
        "ok" if nuevo_estado == "activo" else "error",
    )
    return redirect(request.referrer or url_for("admin_clientes"))

# ---------------------------------------------------------------------------
# RF-24: el administrador genera reportes de ventas por período
# ---------------------------------------------------------------------------
@app.route("/administrador/reportes")
@solo_rol("administrador")
def admin_reportes():
    hasta = request.args.get("hasta") or hoy().isoformat()
    desde = request.args.get("desde") or (hoy() - timedelta(days=30)).isoformat()
    db = get_db()

    pagos = db.execute(
        "SELECT pg.*, r.codigo, r.num_personas, p.nombre AS paquete_nombre "
        "FROM pagos pg JOIN reservas r ON r.id = pg.reserva_id "
        "JOIN paquetes p ON p.id = r.paquete_id "
        "WHERE date(pg.creado_en) BETWEEN ? AND ? ORDER BY pg.creado_en DESC",
        (desde, hasta),
    ).fetchall()
    por_paquete = db.execute(
        "SELECT p.nombre, COUNT(*) AS num_ventas, SUM(pg.monto) AS total "
        "FROM pagos pg JOIN reservas r ON r.id = pg.reserva_id "
        "JOIN paquetes p ON p.id = r.paquete_id "
        "WHERE date(pg.creado_en) BETWEEN ? AND ? "
        "GROUP BY p.id ORDER BY total DESC",
        (desde, hasta),
    ).fetchall()
    total_periodo = sum(p["monto"] for p in pagos)

    # --- RF-49: reporte de reservas filtrable por fecha, destino, estado y paquete ---
    f_destino = request.args.get("destino_id", type=int)
    f_estado = request.args.get("estado_reserva") or ""
    f_paquete = request.args.get("paquete_id", type=int)

    sql_reservas = (
        "SELECT r.*, p.nombre AS paquete_nombre, d.nombre AS destino_nombre, "
        "ps.fecha AS fecha_viaje, u.nombres || ' ' || u.apellidos AS cliente_nombre "
        "FROM reservas r "
        "JOIN paquetes p ON p.id = r.paquete_id "
        "JOIN destinos d ON d.id = p.destino_id "
        "JOIN paquete_salidas ps ON ps.id = r.salida_id "
        "JOIN usuarios u ON u.id = r.cliente_id "
        "WHERE date(r.creado_en) BETWEEN ? AND ? "
    )
    params_reservas = [desde, hasta]
    if f_destino:
        sql_reservas += "AND d.id = ? "
        params_reservas.append(f_destino)
    if f_estado in ("pendiente", "confirmada", "cancelada", "finalizada"):
        sql_reservas += "AND r.estado = ? "
        params_reservas.append(f_estado)
    if f_paquete:
        sql_reservas += "AND p.id = ? "
        params_reservas.append(f_paquete)
    sql_reservas += "ORDER BY r.creado_en DESC"
    reservas_filtradas = db.execute(sql_reservas, params_reservas).fetchall()

    destinos = db.execute("SELECT * FROM destinos ORDER BY nombre").fetchall()
    paquetes_todos = db.execute("SELECT id, nombre FROM paquetes ORDER BY nombre").fetchall()

    # --- RF-50: reporte general (ventas, costos, ingresos, pagos a proveedores,
    # disponibilidad y estado operativo de los paquetes) ---
    total_costos = db.execute(
        "SELECT COALESCE(SUM(monto), 0) AS n FROM paquete_costos"
    ).fetchone()["n"]
    total_ventas_historico = db.execute(
        "SELECT COALESCE(SUM(monto), 0) AS n FROM pagos"
    ).fetchone()["n"]
    pagos_prov_totales = db.execute(
        "SELECT estado, COALESCE(SUM(monto), 0) AS total FROM pagos_proveedores GROUP BY estado"
    ).fetchall()
    total_prov_pagado = next((t["total"] for t in pagos_prov_totales if t["estado"] == "pagado"), 0)
    total_prov_pendiente = next((t["total"] for t in pagos_prov_totales if t["estado"] == "pendiente"), 0)

    disponibilidad = db.execute(
        "SELECT COALESCE(SUM(cupos_totales), 0) AS totales, "
        "COALESCE(SUM(cupos_disponibles), 0) AS libres "
        "FROM paquete_salidas WHERE fecha >= date('now')"
    ).fetchone()

    todos_los_paquetes = db.execute("SELECT id, nombre FROM paquetes WHERE activo = 1").fetchall()
    paquetes_operativos = 0
    paquetes_incompletos = 0
    for pq in todos_los_paquetes:
        if estado_operativo_paquete(db, pq["id"])["listo"]:
            paquetes_operativos += 1
        else:
            paquetes_incompletos += 1

    resumen_general = {
        "ventas": total_ventas_historico,
        "costos": total_costos,
        "ingreso_neto": total_ventas_historico - total_costos,
        "pagos_proveedores_pagado": total_prov_pagado,
        "pagos_proveedores_pendiente": total_prov_pendiente,
        "cupos_totales": disponibilidad["totales"],
        "cupos_libres": disponibilidad["libres"],
        "cupos_ocupados": disponibilidad["totales"] - disponibilidad["libres"],
        "paquetes_operativos": paquetes_operativos,
        "paquetes_incompletos": paquetes_incompletos,
    }

    return render_template(
        "admin_reportes.html", pagos=pagos, por_paquete=por_paquete,
        total_periodo=total_periodo, desde=desde, hasta=hasta,
        reservas_filtradas=reservas_filtradas, destinos=destinos, paquetes_todos=paquetes_todos,
        f_destino=f_destino, f_estado=f_estado, f_paquete=f_paquete,
        resumen_general=resumen_general,
    )

# ---------------------------------------------------------------------------
# RF-25: el administrador gestiona el inventario de proveedores (hoteles,
# restaurantes) que se usan en los paquetes turísticos.
# ---------------------------------------------------------------------------
@app.route("/administrador/proveedores")
@solo_rol("administrador")
def admin_proveedores():
    proveedores = get_db().execute(
        "SELECT pr.*, d.nombre AS destino_nombre FROM proveedores pr "
        "JOIN destinos d ON d.id = pr.destino_id ORDER BY pr.activo DESC, pr.nombre"
    ).fetchall()
    return render_template("admin_proveedores.html", proveedores=proveedores)


@app.route("/administrador/proveedores/nuevo", methods=["GET", "POST"])
@solo_rol("administrador")
def admin_proveedor_nuevo():
    db = get_db()
    destinos = db.execute("SELECT * FROM destinos ORDER BY nombre").fetchall()
    destinos_validos = {d["id"] for d in destinos}
    datos = {"destino_id": "", "tipo": "hotel", "nombre": "", "direccion": "",
             "capacidad": "", "contacto": ""}
    errores = {}

    if request.method == "POST":
        datos, errores = validar_proveedor(request.form, destinos_validos)
        if not errores:
            db.execute(
                "INSERT INTO proveedores (destino_id, tipo, nombre, direccion, capacidad, contacto) "
                "VALUES (?,?,?,?,?,?)",
                (datos["destino_id"], datos["tipo"], datos["nombre"], datos["direccion"],
                 datos["capacidad"], datos["contacto"]),
            )
            db.commit()
            flash("Proveedor agregado al inventario.", "ok")
            return redirect(url_for("admin_proveedores"))

    return render_template("admin_proveedor_formulario.html", modo="nuevo", destinos=destinos,
                           datos=datos, errores=errores)


@app.route("/administrador/proveedores/<int:proveedor_id>/editar", methods=["GET", "POST"])
@solo_rol("administrador")
def admin_proveedor_editar(proveedor_id):
    db = get_db()
    proveedor = db.execute("SELECT * FROM proveedores WHERE id = ?", (proveedor_id,)).fetchone()
    if not proveedor:
        abort(404)
    destinos = db.execute("SELECT * FROM destinos ORDER BY nombre").fetchall()
    destinos_validos = {d["id"] for d in destinos}
    datos = dict(proveedor)
    errores = {}

    if request.method == "POST":
        datos, errores = validar_proveedor(request.form, destinos_validos)
        if not errores:
            db.execute(
                "UPDATE proveedores SET destino_id=?, tipo=?, nombre=?, direccion=?, "
                "capacidad=?, contacto=? WHERE id=?",
                (datos["destino_id"], datos["tipo"], datos["nombre"], datos["direccion"],
                 datos["capacidad"], datos["contacto"], proveedor_id),
            )
            db.commit()
            flash("Proveedor actualizado correctamente.", "ok")
            return redirect(url_for("admin_proveedores"))

    return render_template("admin_proveedor_formulario.html", modo="editar", destinos=destinos,
                           datos=datos, errores=errores, proveedor_id=proveedor_id)


@app.route("/administrador/proveedores/<int:proveedor_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_proveedor_estado(proveedor_id):
    db = get_db()
    proveedor = db.execute("SELECT * FROM proveedores WHERE id = ?", (proveedor_id,)).fetchone()
    if not proveedor:
        abort(404)
    db.execute("UPDATE proveedores SET activo = ? WHERE id = ?",
              (0 if proveedor["activo"] else 1, proveedor_id))
    db.commit()
    flash("Se actualizó el estado del proveedor.", "ok")
    return redirect(url_for("admin_proveedores"))


@app.route("/administrador/proveedores/<int:proveedor_id>/eliminar", methods=["POST"])
@solo_rol("administrador")
def admin_proveedor_eliminar(proveedor_id):
    db = get_db()
    proveedor = db.execute("SELECT * FROM proveedores WHERE id = ?", (proveedor_id,)).fetchone()
    if not proveedor:
        abort(404)
    db.execute("DELETE FROM proveedores WHERE id = ?", (proveedor_id,))
    db.commit()
    flash("Proveedor eliminado del inventario.", "ok")
    return redirect(url_for("admin_proveedores"))


# ===========================================================================
# RF-29 a RF-42: gestión operativa (hoteles, conductores, vehículos, pilotos,
# vuelos/aeronaves) y su asignación a los paquetes, con conflictos de
# disponibilidad.
# ===========================================================================
def limpiar_opcional(texto):
    return limpiar(texto)


def validar_hotel(form, destinos_validos):
    datos = {
        "destino_id": form.get("destino_id", type=int),
        "nombre": limpiar(form.get("nombre")),
        "direccion": limpiar(form.get("direccion")),
        "telefono": limpiar(form.get("telefono")),
        "correo": limpiar(form.get("correo")),
        "checkin": limpiar(form.get("checkin")) or "14:00",
        "checkout": limpiar(form.get("checkout")) or "12:00",
        "politicas": limpiar(form.get("politicas")),
    }
    errores = {}
    if datos["destino_id"] not in destinos_validos:
        errores["destino_id"] = "Elige un destino válido."
    if not datos["nombre"] or len(datos["nombre"]) < 2:
        errores["nombre"] = "Escribe el nombre del hotel."
    if datos["correo"] and not RE_CORREO.match(datos["correo"]):
        errores["correo"] = "Escribe un correo válido o deja el campo vacío."
    for campo, etiqueta in (("checkin", "check-in"), ("checkout", "check-out")):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", datos[campo]):
            errores[campo] = f"Escribe una hora de {etiqueta} válida."
    return datos, errores


def validar_habitacion(form):
    datos = {
        "tipo": limpiar(form.get("tipo")),
        "capacidad": form.get("capacidad", type=int),
        "tarifa_noche": form.get("tarifa_noche", type=int),
        "caracteristicas": limpiar(form.get("caracteristicas")),
        "cupos_totales": form.get("cupos_totales", type=int),
    }
    errores = {}
    if not datos["tipo"]:
        errores["tipo"] = "Escribe el tipo de habitación (sencilla, doble, suite...)."
    if not datos["capacidad"] or datos["capacidad"] < 1:
        errores["capacidad"] = "La capacidad debe ser al menos 1 persona."
    if datos["tarifa_noche"] is None or datos["tarifa_noche"] < 0:
        errores["tarifa_noche"] = "Escribe una tarifa por noche válida."
    if not datos["cupos_totales"] or datos["cupos_totales"] < 1:
        errores["cupos_totales"] = "El número de habitaciones de este tipo debe ser al menos 1."
    return datos, errores


def validar_persona_operativa(form, con_licencia=False):
    datos = {
        "nombres": limpiar(form.get("nombres")),
        "apellidos": limpiar(form.get("apellidos")),
        "telefono": limpiar(form.get("telefono")),
        "correo": limpiar(form.get("correo")),
        "documento": limpiar(form.get("documento")),
    }
    errores = {}
    validar_nombre_apellido(datos, errores)
    if datos["correo"] and not RE_CORREO.match(datos["correo"]):
        errores["correo"] = "Escribe un correo válido o deja el campo vacío."
    if not datos["documento"] or not re.fullmatch(r"[A-Za-z0-9-]{5,20}", datos["documento"]):
        errores["documento"] = "El documento debe tener entre 5 y 20 caracteres (letras, números o guion)."
    if con_licencia:
        datos["licencia"] = limpiar(form.get("licencia"))
        if not datos["licencia"]:
            errores["licencia"] = "Escribe el número de licencia de piloto."
    return datos, errores


def validar_vehiculo(form):
    datos = {
        "placa": limpiar(form.get("placa")).upper(),
        "tipo": limpiar(form.get("tipo")),
        "capacidad": form.get("capacidad", type=int),
        "estado": form.get("estado") or "disponible",
    }
    errores = {}
    if not datos["placa"] or not re.fullmatch(r"[A-Z0-9-]{4,10}", datos["placa"]):
        errores["placa"] = "Escribe una placa válida (letras, números o guion)."
    if not datos["tipo"]:
        errores["tipo"] = "Escribe el tipo de vehículo (bus, van, automóvil...)."
    if not datos["capacidad"] or datos["capacidad"] < 1:
        errores["capacidad"] = "La capacidad debe ser al menos 1 pasajero."
    if datos["estado"] not in ("disponible", "mantenimiento"):
        errores["estado"] = "Elige un estado válido."
    return datos, errores


def validar_aeronave(form):
    datos = {
        "matricula": limpiar(form.get("matricula")).upper(),
        "modelo": limpiar(form.get("modelo")),
        "capacidad": form.get("capacidad", type=int),
    }
    errores = {}
    if not datos["matricula"] or not re.fullmatch(r"[A-Z0-9-]{3,10}", datos["matricula"]):
        errores["matricula"] = "Escribe una matrícula válida."
    if not datos["modelo"]:
        errores["modelo"] = "Escribe el modelo de la aeronave."
    if not datos["capacidad"] or datos["capacidad"] < 1:
        errores["capacidad"] = "La capacidad debe ser al menos 1 pasajero."
    return datos, errores


def cargar_catalogos_operativos(db):
    return {
        "hoteles": db.execute(
            "SELECT h.*, d.nombre AS destino_nombre FROM hoteles h "
            "JOIN destinos d ON d.id = h.destino_id ORDER BY h.activo DESC, h.nombre"
        ).fetchall(),
        "conductores": db.execute(
            "SELECT * FROM conductores ORDER BY activo DESC, nombres"
        ).fetchall(),
        "vehiculos": db.execute(
            "SELECT * FROM vehiculos ORDER BY activo DESC, placa"
        ).fetchall(),
        "pilotos": db.execute(
            "SELECT * FROM pilotos ORDER BY activo DESC, nombres"
        ).fetchall(),
        "aeronaves": db.execute(
            "SELECT * FROM aeronaves ORDER BY activo DESC, matricula"
        ).fetchall(),
    }


def horarios_se_cruzan(fecha_a, hora_ini_a, hora_fin_a, fecha_b, hora_ini_b, hora_fin_b):
    """True si dos franjas (fecha + horario) se traslapan el mismo día."""
    return fecha_a == fecha_b and hora_ini_a < hora_fin_b and hora_ini_b < hora_fin_a


def vuelos_de_pilotos(db):
    """Para cada piloto activo, todos los vuelos que ya tiene asignados en
    cualquier paquete (fecha y horario), para poder consultar su disponibilidad."""
    filas = db.execute(
        "SELECT v.id, v.piloto_id, v.fecha, v.hora_salida, v.hora_llegada, v.origen, v.destino, "
        "       p.nombre AS paquete_nombre "
        "FROM vuelos v JOIN paquetes p ON p.id = v.paquete_id "
        "WHERE v.piloto_id IS NOT NULL ORDER BY v.fecha, v.hora_salida"
    ).fetchall()
    por_piloto = {}
    for f in filas:
        por_piloto.setdefault(f["piloto_id"], []).append(f)
    return por_piloto


def detectar_conflictos(db):
    """RF-42: detecta choques de disponibilidad entre hoteles, conductores,
    vehículos y pilotos, comparando lo asignado el mismo día."""
    conflictos = []

    for fila in db.execute(
        "SELECT c.nombres || ' ' || c.apellidos AS nombre, ta.fecha, COUNT(*) AS n "
        "FROM transporte_asignaciones ta JOIN conductores c ON c.id = ta.conductor_id "
        "GROUP BY ta.conductor_id, ta.fecha HAVING COUNT(*) > 1"
    ).fetchall():
        conflictos.append(
            f"El conductor {fila['nombre']} tiene {fila['n']} servicios de transporte "
            f"asignados el {fila['fecha']}."
        )

    for fila in db.execute(
        "SELECT v.placa AS placa, ta.fecha, COUNT(*) AS n "
        "FROM transporte_asignaciones ta JOIN vehiculos v ON v.id = ta.vehiculo_id "
        "GROUP BY ta.vehiculo_id, ta.fecha HAVING COUNT(*) > 1"
    ).fetchall():
        conflictos.append(
            f"El vehículo {fila['placa']} tiene {fila['n']} servicios de transporte "
            f"asignados el {fila['fecha']}."
        )

    vuelos_asignados = db.execute(
        "SELECT v.*, p.nombres || ' ' || p.apellidos AS piloto_nombre "
        "FROM vuelos v JOIN pilotos p ON p.id = v.piloto_id WHERE v.piloto_id IS NOT NULL "
        "ORDER BY v.fecha, v.hora_salida"
    ).fetchall()
    ya_reportados = set()
    for i, v1 in enumerate(vuelos_asignados):
        for v2 in vuelos_asignados[i + 1:]:
            if v1["piloto_id"] != v2["piloto_id"]:
                continue
            if horarios_se_cruzan(v1["fecha"], v1["hora_salida"], v1["hora_llegada"],
                                   v2["fecha"], v2["hora_salida"], v2["hora_llegada"]):
                clave = (v1["piloto_id"], v1["fecha"])
                if clave not in ya_reportados:
                    conflictos.append(
                        f"El piloto {v1['piloto_nombre']} tiene vuelos con horario cruzado "
                        f"el {v1['fecha']} ({v1['hora_salida']}-{v1['hora_llegada']} y "
                        f"{v2['hora_salida']}-{v2['hora_llegada']})."
                    )
                    ya_reportados.add(clave)

    for fila in db.execute(
        "SELECT hh.tipo AS tipo, h.nombre AS hotel, ps.fecha AS fecha, "
        "       hh.cupos_totales AS cupos, SUM(ph.cantidad) AS asignadas "
        "FROM paquete_hoteles ph "
        "JOIN hotel_habitaciones hh ON hh.id = ph.habitacion_id "
        "JOIN hoteles h ON h.id = hh.hotel_id "
        "JOIN paquete_salidas ps ON ps.id = ph.salida_id "
        "GROUP BY ph.habitacion_id, ps.fecha "
        "HAVING SUM(ph.cantidad) > hh.cupos_totales"
    ).fetchall():
        conflictos.append(
            f"El hotel {fila['hotel']} tiene más habitaciones \"{fila['tipo']}\" asignadas "
            f"({fila['asignadas']}) que las {fila['cupos']} disponibles para el {fila['fecha']}."
        )

    return conflictos


@app.route("/administrador/operacion")
@solo_rol("administrador")
def admin_operacion():
    db = get_db()
    destinos = db.execute("SELECT * FROM destinos ORDER BY nombre").fetchall()
    catalogos = cargar_catalogos_operativos(db)
    habitaciones_por_hotel = {}
    for h in catalogos["hoteles"]:
        habitaciones_por_hotel[h["id"]] = db.execute(
            "SELECT * FROM hotel_habitaciones WHERE hotel_id = ? ORDER BY activo DESC, tipo",
            (h["id"],),
        ).fetchall()
    return render_template(
        "admin_operacion.html", destinos=destinos,
        habitaciones_por_hotel=habitaciones_por_hotel,
        conflictos=detectar_conflictos(db), **catalogos,
    )


# --- RF-29/RF-30: hoteles --------------------------------------------------
@app.route("/administrador/operacion/hoteles/nuevo", methods=["POST"])
@solo_rol("administrador")
def admin_hotel_nuevo():
    db = get_db()
    destinos_validos = {d["id"] for d in db.execute("SELECT id FROM destinos")}
    datos, errores = validar_hotel(request.form, destinos_validos)
    if errores:
        flash(next(iter(errores.values())), "error")
    else:
        db.execute(
            "INSERT INTO hoteles (destino_id, nombre, direccion, telefono, correo, checkin, checkout, politicas) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (datos["destino_id"], datos["nombre"], datos["direccion"], datos["telefono"], datos["correo"],
             datos["checkin"], datos["checkout"], datos["politicas"]),
        )
        db.commit()
        flash("Hotel registrado correctamente.", "ok")
    return redirect(url_for("admin_operacion"))


@app.route("/administrador/operacion/hoteles/<int:hotel_id>/editar", methods=["GET", "POST"])
@solo_rol("administrador")
def admin_hotel_editar(hotel_id):
    db = get_db()
    hotel = db.execute("SELECT * FROM hoteles WHERE id = ?", (hotel_id,)).fetchone()
    if not hotel:
        abort(404)
    destinos = db.execute("SELECT * FROM destinos ORDER BY nombre").fetchall()
    destinos_validos = {d["id"] for d in destinos}
    datos = dict(hotel)
    errores = {}
    if request.method == "POST":
        datos, errores = validar_hotel(request.form, destinos_validos)
        if not errores:
            db.execute(
                "UPDATE hoteles SET destino_id=?, nombre=?, direccion=?, telefono=?, correo=?, "
                "checkin=?, checkout=?, politicas=? WHERE id=?",
                (datos["destino_id"], datos["nombre"], datos["direccion"], datos["telefono"],
                 datos["correo"], datos["checkin"], datos["checkout"], datos["politicas"], hotel_id),
            )
            db.commit()
            flash("Los datos del hotel se actualizaron correctamente.", "ok")
            return redirect(url_for("admin_operacion"))
        datos["id"] = hotel_id
    return render_template("admin_hotel_formulario.html", datos=datos, errores=errores,
                           destinos=destinos, modo="editar")


@app.route("/administrador/operacion/hoteles/<int:hotel_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_hotel_estado(hotel_id):
    db = get_db()
    hotel = db.execute("SELECT * FROM hoteles WHERE id = ?", (hotel_id,)).fetchone()
    if not hotel:
        abort(404)
    db.execute("UPDATE hoteles SET activo = ? WHERE id = ?", (0 if hotel["activo"] else 1, hotel_id))
    db.commit()
    flash("Se actualizó el estado del hotel.", "ok")
    return redirect(url_for("admin_operacion"))


# --- RF-31: tipos de habitación por hotel ----------------------------------
@app.route("/administrador/operacion/hoteles/<int:hotel_id>/habitaciones/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_habitacion_agregar(hotel_id):
    db = get_db()
    hotel = db.execute("SELECT * FROM hoteles WHERE id = ?", (hotel_id,)).fetchone()
    if not hotel:
        abort(404)
    datos, errores = validar_habitacion(request.form)
    if errores:
        flash(next(iter(errores.values())), "error")
    else:
        db.execute(
            "INSERT INTO hotel_habitaciones (hotel_id, tipo, capacidad, tarifa_noche, "
            "caracteristicas, cupos_totales) VALUES (?,?,?,?,?,?)",
            (hotel_id, datos["tipo"], datos["capacidad"], datos["tarifa_noche"],
             datos["caracteristicas"], datos["cupos_totales"]),
        )
        db.commit()
        flash("Tipo de habitación registrado.", "ok")
    return redirect(url_for("admin_operacion"))


@app.route("/administrador/operacion/habitaciones/<int:habitacion_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_habitacion_estado(habitacion_id):
    db = get_db()
    habitacion = db.execute("SELECT * FROM hotel_habitaciones WHERE id = ?", (habitacion_id,)).fetchone()
    if not habitacion:
        abort(404)
    db.execute("UPDATE hotel_habitaciones SET activo = ? WHERE id = ?",
              (0 if habitacion["activo"] else 1, habitacion_id))
    db.commit()
    flash("Se actualizó el estado del tipo de habitación.", "ok")
    return redirect(url_for("admin_operacion"))


# --- RF-33: conductores -----------------------------------------------------
@app.route("/administrador/operacion/conductores/nuevo", methods=["POST"])
@solo_rol("administrador")
def admin_conductor_nuevo():
    db = get_db()
    datos, errores = validar_persona_operativa(request.form)
    if errores:
        flash(next(iter(errores.values())), "error")
    else:
        db.execute(
            "INSERT INTO conductores (nombres, apellidos, telefono, correo, documento) VALUES (?,?,?,?,?)",
            (datos["nombres"], datos["apellidos"], datos["telefono"], datos["correo"], datos["documento"]),
        )
        db.commit()
        flash("Conductor registrado correctamente.", "ok")
    return redirect(url_for("admin_operacion"))


@app.route("/administrador/operacion/conductores/<int:conductor_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_conductor_estado(conductor_id):
    db = get_db()
    c = db.execute("SELECT * FROM conductores WHERE id = ?", (conductor_id,)).fetchone()
    if not c:
        abort(404)
    db.execute("UPDATE conductores SET activo = ? WHERE id = ?", (0 if c["activo"] else 1, conductor_id))
    db.commit()
    flash("Se actualizó el estado del conductor.", "ok")
    return redirect(url_for("admin_operacion"))


# --- RF-34: vehículos -------------------------------------------------------
@app.route("/administrador/operacion/vehiculos/nuevo", methods=["POST"])
@solo_rol("administrador")
def admin_vehiculo_nuevo():
    db = get_db()
    datos, errores = validar_vehiculo(request.form)
    if errores:
        flash(next(iter(errores.values())), "error")
    else:
        try:
            db.execute(
                "INSERT INTO vehiculos (placa, tipo, capacidad, estado) VALUES (?,?,?,?)",
                (datos["placa"], datos["tipo"], datos["capacidad"], datos["estado"]),
            )
            db.commit()
            flash("Vehículo registrado correctamente.", "ok")
        except sqlite3.IntegrityError:
            flash("Ya existe un vehículo registrado con esa placa.", "error")
    return redirect(url_for("admin_operacion"))


@app.route("/administrador/operacion/vehiculos/<int:vehiculo_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_vehiculo_estado(vehiculo_id):
    db = get_db()
    v = db.execute("SELECT * FROM vehiculos WHERE id = ?", (vehiculo_id,)).fetchone()
    if not v:
        abort(404)
    db.execute("UPDATE vehiculos SET activo = ? WHERE id = ?", (0 if v["activo"] else 1, vehiculo_id))
    db.commit()
    flash("Se actualizó el estado del vehículo.", "ok")
    return redirect(url_for("admin_operacion"))


# --- RF-37: pilotos ----------------------------------------------------------
@app.route("/administrador/operacion/pilotos/nuevo", methods=["POST"])
@solo_rol("administrador")
def admin_piloto_nuevo():
    db = get_db()
    datos, errores = validar_persona_operativa(request.form, con_licencia=True)
    if errores:
        flash(next(iter(errores.values())), "error")
    else:
        db.execute(
            "INSERT INTO pilotos (nombres, apellidos, telefono, correo, documento, licencia) "
            "VALUES (?,?,?,?,?,?)",
            (datos["nombres"], datos["apellidos"], datos["telefono"], datos["correo"],
             datos["documento"], datos["licencia"]),
        )
        db.commit()
        flash("Piloto registrado correctamente.", "ok")
    return redirect(url_for("admin_operacion"))


@app.route("/administrador/operacion/pilotos/<int:piloto_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_piloto_estado(piloto_id):
    db = get_db()
    p = db.execute("SELECT * FROM pilotos WHERE id = ?", (piloto_id,)).fetchone()
    if not p:
        abort(404)
    db.execute("UPDATE pilotos SET activo = ? WHERE id = ?", (0 if p["activo"] else 1, piloto_id))
    db.commit()
    flash("Se actualizó el estado del piloto.", "ok")
    return redirect(url_for("admin_operacion"))


# --- RF-38 (aeronaves): vuelos y aeronaves ----------------------------------
@app.route("/administrador/operacion/aeronaves/nuevo", methods=["POST"])
@solo_rol("administrador")
def admin_aeronave_nueva():
    db = get_db()
    datos, errores = validar_aeronave(request.form)
    if errores:
        flash(next(iter(errores.values())), "error")
    else:
        try:
            db.execute(
                "INSERT INTO aeronaves (matricula, modelo, capacidad) VALUES (?,?,?)",
                (datos["matricula"], datos["modelo"], datos["capacidad"]),
            )
            db.commit()
            flash("Aeronave registrada correctamente.", "ok")
        except sqlite3.IntegrityError:
            flash("Ya existe una aeronave registrada con esa matrícula.", "error")
    return redirect(url_for("admin_operacion"))


@app.route("/administrador/operacion/aeronaves/<int:aeronave_id>/estado", methods=["POST"])
@solo_rol("administrador")
def admin_aeronave_estado(aeronave_id):
    db = get_db()
    a = db.execute("SELECT * FROM aeronaves WHERE id = ?", (aeronave_id,)).fetchone()
    if not a:
        abort(404)
    db.execute("UPDATE aeronaves SET activo = ? WHERE id = ?", (0 if a["activo"] else 1, aeronave_id))
    db.commit()
    flash("Se actualizó el estado de la aeronave.", "ok")
    return redirect(url_for("admin_operacion"))


# --- Recursos asignados a un paquete concreto (RF-32, RF-35, RF-38) ------
@app.route("/administrador/paquetes/<int:paquete_id>/recursos")
@solo_rol("administrador")
def admin_paquete_recursos(paquete_id):
    paquete = paquete_admin_o_404(paquete_id)
    db = get_db()
    salidas = db.execute(
        "SELECT * FROM paquete_salidas WHERE paquete_id = ? ORDER BY fecha", (paquete_id,)
    ).fetchall()
    habitaciones = db.execute(
        "SELECT hh.*, h.nombre AS hotel_nombre FROM hotel_habitaciones hh "
        "JOIN hoteles h ON h.id = hh.hotel_id WHERE hh.activo = 1 AND h.activo = 1 "
        "ORDER BY h.nombre, hh.tipo"
    ).fetchall()

    # RF-32: consultar la disponibilidad de habitaciones para las fechas de ESTE
    # paquete, cruzando cada tipo de habitación con cada fecha de salida, antes
    # de asignar nada (no solo después, como ya mostraba la tabla de abajo).
    disponibilidad_habitaciones = []
    for s in salidas:
        for hab in habitaciones:
            ocupadas = db.execute(
                "SELECT COALESCE(SUM(ph.cantidad), 0) AS n FROM paquete_hoteles ph "
                "JOIN paquete_salidas ps ON ps.id = ph.salida_id "
                "WHERE ph.habitacion_id = ? AND ps.fecha = ?",
                (hab["id"], s["fecha"]),
            ).fetchone()["n"]
            disponibilidad_habitaciones.append({
                "fecha": s["fecha"], "hotel_nombre": hab["hotel_nombre"], "tipo": hab["tipo"],
                "cupos_totales": hab["cupos_totales"], "ocupadas": ocupadas,
                "libres": hab["cupos_totales"] - ocupadas,
            })

    hoteles_asignados = db.execute(
        "SELECT ph.*, hh.tipo, hh.capacidad, hh.cupos_totales, h.nombre AS hotel_nombre, "
        "       ps.fecha AS fecha, "
        "       (SELECT COALESCE(SUM(ph2.cantidad), 0) FROM paquete_hoteles ph2 "
        "        JOIN paquete_salidas ps2 ON ps2.id = ph2.salida_id "
        "        WHERE ph2.habitacion_id = ph.habitacion_id AND ps2.fecha = ps.fecha) AS asignadas_fecha "
        "FROM paquete_hoteles ph "
        "JOIN hotel_habitaciones hh ON hh.id = ph.habitacion_id "
        "JOIN hoteles h ON h.id = hh.hotel_id "
        "JOIN paquete_salidas ps ON ps.id = ph.salida_id "
        "WHERE ph.paquete_id = ? ORDER BY ps.fecha",
        (paquete_id,),
    ).fetchall()
    conductores = db.execute("SELECT * FROM conductores WHERE activo = 1 ORDER BY nombres").fetchall()
    vehiculos = db.execute("SELECT * FROM vehiculos WHERE activo = 1 ORDER BY placa").fetchall()
    transportes = db.execute(
        "SELECT ta.*, c.nombres || ' ' || c.apellidos AS conductor_nombre, v.placa "
        "FROM transporte_asignaciones ta "
        "JOIN conductores c ON c.id = ta.conductor_id "
        "JOIN vehiculos v ON v.id = ta.vehiculo_id "
        "WHERE ta.paquete_id = ? ORDER BY ta.fecha, ta.hora",
        (paquete_id,),
    ).fetchall()
    aeronaves = db.execute("SELECT * FROM aeronaves WHERE activo = 1 ORDER BY matricula").fetchall()
    pilotos = db.execute("SELECT * FROM pilotos WHERE activo = 1 ORDER BY nombres").fetchall()
    vuelos = db.execute(
        "SELECT v.*, a.matricula, p.nombres || ' ' || p.apellidos AS piloto_nombre "
        "FROM vuelos v JOIN aeronaves a ON a.id = v.aeronave_id "
        "LEFT JOIN pilotos p ON p.id = v.piloto_id "
        "WHERE v.paquete_id = ? ORDER BY v.fecha, v.hora_salida",
        (paquete_id,),
    ).fetchall()

    # RF-40: consultar la disponibilidad de cada piloto según la fecha y el
    # horario exactos de cada vuelo de este paquete, antes de asignarlo.
    vuelos_por_piloto = vuelos_de_pilotos(db)
    opciones_piloto_por_vuelo = {}
    for v in vuelos:
        opciones = []
        for pil in pilotos:
            conflicto = None
            for otro in vuelos_por_piloto.get(pil["id"], []):
                if otro["id"] == v["id"]:
                    continue  # no contar el propio vuelo que ya tiene asignado este piloto
                if horarios_se_cruzan(
                    v["fecha"], v["hora_salida"], v["hora_llegada"],
                    otro["fecha"], otro["hora_salida"], otro["hora_llegada"],
                ):
                    conflicto = otro
                    break
            opciones.append({
                "id": pil["id"], "nombre": f"{pil['nombres']} {pil['apellidos']}",
                "disponible": conflicto is None, "conflicto": conflicto,
            })
        opciones_piloto_por_vuelo[v["id"]] = opciones

    return render_template(
        "admin_paquete_recursos.html", p=paquete, salidas=salidas, habitaciones=habitaciones,
        disponibilidad_habitaciones=disponibilidad_habitaciones,
        hoteles_asignados=hoteles_asignados, conductores=conductores, vehiculos=vehiculos,
        transportes=transportes, aeronaves=aeronaves, pilotos=pilotos, vuelos=vuelos,
        opciones_piloto_por_vuelo=opciones_piloto_por_vuelo,
        conflictos=detectar_conflictos(db),
    )


@app.route("/administrador/paquetes/<int:paquete_id>/recursos/hoteles/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_recurso_hotel_agregar(paquete_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    salida_id = request.form.get("salida_id", type=int)
    habitacion_id = request.form.get("habitacion_id", type=int)
    cantidad = request.form.get("cantidad", type=int)
    salida = db.execute("SELECT * FROM paquete_salidas WHERE id = ? AND paquete_id = ?",
                        (salida_id, paquete_id)).fetchone()
    habitacion = db.execute("SELECT * FROM hotel_habitaciones WHERE id = ?", (habitacion_id,)).fetchone()
    if not salida or not habitacion or not cantidad or cantidad < 1:
        flash("Elige una fecha de salida, un tipo de habitación y una cantidad válida.", "error")
        return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))

    # RF-32: disponibilidad de habitaciones para la fecha de esta salida.
    ya_asignadas = db.execute(
        "SELECT COALESCE(SUM(ph.cantidad), 0) AS n FROM paquete_hoteles ph "
        "JOIN paquete_salidas ps ON ps.id = ph.salida_id "
        "WHERE ph.habitacion_id = ? AND ps.fecha = ?",
        (habitacion_id, salida["fecha"]),
    ).fetchone()["n"]
    disponibles = habitacion["cupos_totales"] - ya_asignadas

    db.execute(
        "INSERT INTO paquete_hoteles (paquete_id, salida_id, habitacion_id, cantidad) VALUES (?,?,?,?)",
        (paquete_id, salida_id, habitacion_id, cantidad),
    )
    db.commit()
    if cantidad > disponibles:
        # RF-42: notificar el conflicto apenas se genera, además de quedar
        # visible en el panel de conflictos.
        flash(
            f"Habitación asignada, pero hay un conflicto: solo había {disponibles} habitación(es) "
            f"\"{habitacion['tipo']}\" disponibles para el {salida['fecha']} y se asignaron {cantidad}.",
            "error",
        )
    else:
        flash("Habitación asignada al paquete.", "ok")
    return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/recursos/hoteles/<int:item_id>/eliminar", methods=["POST"])
@solo_rol("administrador")
def admin_recurso_hotel_eliminar(paquete_id, item_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    db.execute("DELETE FROM paquete_hoteles WHERE id = ? AND paquete_id = ?", (item_id, paquete_id))
    db.commit()
    flash("Se quitó la habitación asignada.", "ok")
    return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/recursos/transporte/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_recurso_transporte_agregar(paquete_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    salida_id = request.form.get("salida_id", type=int)
    conductor_id = request.form.get("conductor_id", type=int)
    vehiculo_id = request.form.get("vehiculo_id", type=int)
    hora = limpiar(request.form.get("hora")) or "08:00"
    salida = db.execute("SELECT * FROM paquete_salidas WHERE id = ? AND paquete_id = ?",
                        (salida_id, paquete_id)).fetchone()
    conductor = db.execute("SELECT * FROM conductores WHERE id = ?", (conductor_id,)).fetchone()
    vehiculo = db.execute("SELECT * FROM vehiculos WHERE id = ?", (vehiculo_id,)).fetchone()
    if not salida or not conductor or not vehiculo:
        flash("Elige una fecha de salida, un conductor y un vehículo válidos.", "error")
        return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))

    # RF-36: disponibilidad del conductor y del vehículo en esa fecha.
    conductor_ocupado = db.execute(
        "SELECT COUNT(*) AS n FROM transporte_asignaciones WHERE conductor_id = ? AND fecha = ?",
        (conductor_id, salida["fecha"]),
    ).fetchone()["n"]
    vehiculo_ocupado = db.execute(
        "SELECT COUNT(*) AS n FROM transporte_asignaciones WHERE vehiculo_id = ? AND fecha = ?",
        (vehiculo_id, salida["fecha"]),
    ).fetchone()["n"]

    db.execute(
        "INSERT INTO transporte_asignaciones (paquete_id, salida_id, conductor_id, vehiculo_id, fecha, hora) "
        "VALUES (?,?,?,?,?,?)",
        (paquete_id, salida_id, conductor_id, vehiculo_id, salida["fecha"], hora),
    )
    db.commit()
    if conductor_ocupado or vehiculo_ocupado:
        flash(
            "Transporte asignado, pero hay un conflicto: el conductor o el vehículo ya tenían "
            f"otro servicio asignado el {salida['fecha']}.", "error",
        )
    else:
        flash("Conductor y vehículo asignados a esta salida.", "ok")
    return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/recursos/transporte/<int:item_id>/eliminar", methods=["POST"])
@solo_rol("administrador")
def admin_recurso_transporte_eliminar(paquete_id, item_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    db.execute("DELETE FROM transporte_asignaciones WHERE id = ? AND paquete_id = ?", (item_id, paquete_id))
    db.commit()
    flash("Se quitó la asignación de transporte.", "ok")
    return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/recursos/vuelos/agregar", methods=["POST"])
@solo_rol("administrador")
def admin_recurso_vuelo_agregar(paquete_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    salida_id = request.form.get("salida_id", type=int)
    aeronave_id = request.form.get("aeronave_id", type=int)
    origen = limpiar(request.form.get("origen"))
    destino = limpiar(request.form.get("destino"))
    hora_salida = limpiar(request.form.get("hora_salida")) or "08:00"
    hora_llegada = limpiar(request.form.get("hora_llegada")) or "10:00"
    salida = db.execute("SELECT * FROM paquete_salidas WHERE id = ? AND paquete_id = ?",
                        (salida_id, paquete_id)).fetchone()
    aeronave = db.execute("SELECT * FROM aeronaves WHERE id = ?", (aeronave_id,)).fetchone()
    if not salida or not aeronave or not origen or not destino:
        flash("Elige una fecha de salida, una aeronave y escribe origen y destino.", "error")
        return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))
    db.execute(
        "INSERT INTO vuelos (paquete_id, salida_id, aeronave_id, origen, destino, fecha, "
        "hora_salida, hora_llegada) VALUES (?,?,?,?,?,?,?,?)",
        (paquete_id, salida_id, aeronave_id, origen, destino, salida["fecha"], hora_salida, hora_llegada),
    )
    db.commit()
    flash("Vuelo registrado para esta salida.", "ok")
    return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/recursos/vuelos/<int:vuelo_id>/piloto", methods=["POST"])
@solo_rol("administrador")
def admin_recurso_vuelo_piloto(paquete_id, vuelo_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    vuelo = db.execute("SELECT * FROM vuelos WHERE id = ? AND paquete_id = ?",
                       (vuelo_id, paquete_id)).fetchone()
    if not vuelo:
        abort(404)
    piloto_id = request.form.get("piloto_id", type=int)
    piloto = db.execute("SELECT * FROM pilotos WHERE id = ?", (piloto_id,)).fetchone()
    if not piloto:
        flash("Elige un piloto válido.", "error")
        return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))

    # RF-40: disponibilidad del piloto según la fecha Y el horario del vuelo
    # (no solo la fecha: dos vuelos el mismo día a horas distintas no chocan).
    otros_vuelos = db.execute(
        "SELECT * FROM vuelos WHERE piloto_id = ? AND fecha = ? AND id != ?",
        (piloto_id, vuelo["fecha"], vuelo_id),
    ).fetchall()
    conflicto = next(
        (o for o in otros_vuelos if horarios_se_cruzan(
            vuelo["fecha"], vuelo["hora_salida"], vuelo["hora_llegada"],
            o["fecha"], o["hora_salida"], o["hora_llegada"],
        )),
        None,
    )

    db.execute("UPDATE vuelos SET piloto_id = ? WHERE id = ?", (piloto_id, vuelo_id))
    db.commit()
    if conflicto:
        flash(
            f"Piloto asignado, pero hay un conflicto: ya tiene otro vuelo el {vuelo['fecha']} "
            f"de {conflicto['hora_salida']} a {conflicto['hora_llegada']}.",
            "error",
        )
    else:
        flash("Piloto asignado al vuelo.", "ok")
    return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))


@app.route("/administrador/paquetes/<int:paquete_id>/recursos/vuelos/<int:vuelo_id>/eliminar", methods=["POST"])
@solo_rol("administrador")
def admin_recurso_vuelo_eliminar(paquete_id, vuelo_id):
    paquete_admin_o_404(paquete_id)
    db = get_db()
    db.execute("DELETE FROM vuelos WHERE id = ? AND paquete_id = ?", (vuelo_id, paquete_id))
    db.commit()
    flash("Se eliminó el vuelo.", "ok")
    return redirect(url_for("admin_paquete_recursos", paquete_id=paquete_id))


@app.errorhandler(404)
def no_encontrado(_e):
    return render_template("error.html", codigo=404,
                           mensaje="No encontramos la página que buscas."), 404


@app.errorhandler(400)
def solicitud_invalida(_e):
    return render_template("error.html", codigo=400,
                           mensaje="La sesión del formulario expiró. Vuelve a intentarlo."), 400


iniciar_db()

if __name__ == "__main__":
    app.run(debug=True)
