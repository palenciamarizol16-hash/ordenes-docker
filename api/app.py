"""API REST de órdenes de venta (Flask + SQL Server)."""
import logging
import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pymssql
from flask import Flask, jsonify, request

app = Flask(__name__)
app.json.sort_keys = False
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ordenes-api")

ESTADOS = ("Pendiente", "Pagada", "Anulada")
CENTAVOS = Decimal("0.01")


# ---------------- Conexión a la base de datos ----------------
def get_conn():
    return pymssql.connect(
        server=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "1433"),
        user=os.environ.get("DB_USER", "sa"),
        password=os.environ["DB_PASSWORD"],
        database=os.environ.get("DB_NAME", "OrdenesDB"),
        as_dict=True,
        login_timeout=5,
    )


@contextmanager
def db():
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------- Errores y utilidades ----------------
class ApiError(Exception):
    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


@app.errorhandler(ApiError)
def manejar_api_error(e):
    return jsonify(error=e.mensaje), e.codigo


@app.errorhandler(404)
def manejar_404(_):
    return jsonify(error="Recurso no encontrado"), 404


@app.errorhandler(405)
def manejar_405(_):
    return jsonify(error="Método no permitido"), 405


@app.errorhandler(pymssql.Error)
def manejar_error_bd(e):
    log.exception("Error de base de datos: %s", e)
    return jsonify(error="Error en la base de datos"), 500


def limpiar(fila):
    if fila is None:
        return None
    salida = {}
    for clave, valor in fila.items():
        if isinstance(valor, Decimal):
            valor = float(valor)
        elif isinstance(valor, (date, datetime)):
            valor = valor.isoformat()
        salida[clave] = valor
    return salida


def cuerpo_json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Se esperaba un cuerpo JSON válido (objeto)")
    return data


# ---------------- Validaciones ----------------
def validar_texto(valor, campo, maximo=100):
    if not isinstance(valor, str) or not valor.strip():
        raise ApiError(f"El campo '{campo}' es obligatorio")
    valor = valor.strip()
    if len(valor) > maximo:
        raise ApiError(f"El campo '{campo}' no puede superar {maximo} caracteres")
    return valor


def validar_fecha(valor):
    if valor is None or valor == "":
        return date.today()
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        raise ApiError("El campo 'fecha' debe tener formato YYYY-MM-DD")


def validar_estado(valor):
    if valor not in ESTADOS:
        raise ApiError(f"El campo 'estado' debe ser uno de: {', '.join(ESTADOS)}")
    return valor


def validar_cantidad(valor):
    if isinstance(valor, bool):
        raise ApiError("El campo 'cantidad' debe ser un entero mayor que 0")
    try:
        n = int(str(valor).strip())
    except ValueError:
        raise ApiError("El campo 'cantidad' debe ser un entero mayor que 0")
    if n <= 0 or n > 1_000_000:
        raise ApiError("El campo 'cantidad' debe estar entre 1 y 1000000")
    return n


def validar_precio(valor):
    if isinstance(valor, bool):
        raise ApiError("El campo 'precio_unitario' debe ser un número mayor o igual a 0")
    try:
        p = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError):
        raise ApiError("El campo 'precio_unitario' debe ser un número mayor o igual a 0")
    if not p.is_finite() or p < 0 or p > Decimal("9999999.99"):
        raise ApiError("El campo 'precio_unitario' debe estar entre 0 y 9999999.99")
    return p.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


# ---------------- Acceso a datos ----------------
def obtener_orden(cur, orden_id):
    cur.execute(
        "SELECT id, cliente, fecha, estado, total FROM ordenes WHERE id = %s",
        (orden_id,),
    )
    fila = cur.fetchone()
    if fila is None:
        raise ApiError("La orden no existe", 404)
    return fila


def obtener_detalle(cur, detalle_id):
    cur.execute(
        "SELECT id, orden_id, producto, cantidad, precio_unitario, subtotal "
        "FROM orden_detalle WHERE id = %s",
        (detalle_id,),
    )
    fila = cur.fetchone()
    if fila is None:
        raise ApiError("El detalle no existe", 404)
    return fila


def listar_detalles(cur, orden_id):
    cur.execute(
        "SELECT id, orden_id, producto, cantidad, precio_unitario, subtotal "
        "FROM orden_detalle WHERE orden_id = %s ORDER BY id",
        (orden_id,),
    )
    return cur.fetchall()


def recalcular_total(cur, orden_id):
    """El total de la orden = suma de los subtotales de sus detalles."""
    cur.execute(
        "UPDATE ordenes SET total = "
        "(SELECT ISNULL(SUM(subtotal), 0) FROM orden_detalle WHERE orden_id = %s) "
        "WHERE id = %s",
        (orden_id, orden_id),
    )


# ---------------- Endpoints ----------------
@app.get("/health")
def health():
    try:
        with db() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
        return jsonify(status="ok", db="up"), 200
    except Exception as e:  # noqa: BLE001
        log.warning("Health check falló: %s", e)
        return jsonify(status="error", db="down"), 503


# ---------- Órdenes ----------
@app.get("/api/ordenes")
def listar_ordenes():
    with db() as cur:
        cur.execute("SELECT id, cliente, fecha, estado, total FROM ordenes ORDER BY id DESC")
        return jsonify([limpiar(f) for f in cur.fetchall()]), 200


@app.get("/api/ordenes/<int:orden_id>")
def ver_orden(orden_id):
    with db() as cur:
        orden = limpiar(obtener_orden(cur, orden_id))
        orden["detalles"] = [limpiar(d) for d in listar_detalles(cur, orden_id)]
        return jsonify(orden), 200


@app.post("/api/ordenes")
def crear_orden():
    data = cuerpo_json()
    cliente = validar_texto(data.get("cliente"), "cliente")
    fecha = validar_fecha(data.get("fecha"))
    estado = validar_estado(data.get("estado", "Pendiente"))
    with db() as cur:
        cur.execute(
            "INSERT INTO ordenes (cliente, fecha, estado, total) "
            "OUTPUT INSERTED.id VALUES (%s, %s, %s, 0)",
            (cliente, fecha, estado),
        )
        nuevo_id = cur.fetchone()["id"]
        orden = limpiar(obtener_orden(cur, nuevo_id))
        orden["detalles"] = []
    return jsonify(orden), 201


@app.put("/api/ordenes/<int:orden_id>")
def actualizar_orden(orden_id):
    data = cuerpo_json()
    with db() as cur:
        actual = obtener_orden(cur, orden_id)
        cliente = validar_texto(data.get("cliente", actual["cliente"]), "cliente")
        fecha = validar_fecha(data.get("fecha", actual["fecha"]))
        estado = validar_estado(data.get("estado", actual["estado"]))
        cur.execute(
            "UPDATE ordenes SET cliente = %s, fecha = %s, estado = %s WHERE id = %s",
            (cliente, fecha, estado, orden_id),
        )
        orden = limpiar(obtener_orden(cur, orden_id))
        orden["detalles"] = [limpiar(d) for d in listar_detalles(cur, orden_id)]
    return jsonify(orden), 200


@app.delete("/api/ordenes/<int:orden_id>")
def eliminar_orden(orden_id):
    with db() as cur:
        obtener_orden(cur, orden_id)
        cur.execute("DELETE FROM ordenes WHERE id = %s", (orden_id,))
    return jsonify(mensaje="Orden eliminada junto con sus detalles"), 200


# ---------- Detalles ----------
@app.get("/api/ordenes/<int:orden_id>/detalles")
def listar_detalles_orden(orden_id):
    with db() as cur:
        obtener_orden(cur, orden_id)
        return jsonify([limpiar(d) for d in listar_detalles(cur, orden_id)]), 200


@app.post("/api/ordenes/<int:orden_id>/detalles")
def agregar_detalle(orden_id):
    data = cuerpo_json()
    producto = validar_texto(data.get("producto"), "producto")
    cantidad = validar_cantidad(data.get("cantidad"))
    precio = validar_precio(data.get("precio_unitario"))
    subtotal = (precio * cantidad).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    with db() as cur:
        obtener_orden(cur, orden_id)
        cur.execute(
            "INSERT INTO orden_detalle (orden_id, producto, cantidad, precio_unitario, subtotal) "
            "OUTPUT INSERTED.id VALUES (%s, %s, %s, %s, %s)",
            (orden_id, producto, cantidad, precio, subtotal),
        )
        nuevo_id = cur.fetchone()["id"]
        recalcular_total(cur, orden_id)
        detalle = limpiar(obtener_detalle(cur, nuevo_id))
    return jsonify(detalle), 201


@app.put("/api/detalles/<int:detalle_id>")
def actualizar_detalle(detalle_id):
    data = cuerpo_json()
    with db() as cur:
        actual = obtener_detalle(cur, detalle_id)
        producto = validar_texto(data.get("producto", actual["producto"]), "producto")
        cantidad = validar_cantidad(data.get("cantidad", actual["cantidad"]))
        precio = validar_precio(data.get("precio_unitario", actual["precio_unitario"]))
        subtotal = (precio * cantidad).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        cur.execute(
            "UPDATE orden_detalle SET producto = %s, cantidad = %s, "
            "precio_unitario = %s, subtotal = %s WHERE id = %s",
            (producto, cantidad, precio, subtotal, detalle_id),
        )
        recalcular_total(cur, actual["orden_id"])
        detalle = limpiar(obtener_detalle(cur, detalle_id))
    return jsonify(detalle), 200


@app.delete("/api/detalles/<int:detalle_id>")
def eliminar_detalle(detalle_id):
    with db() as cur:
        actual = obtener_detalle(cur, detalle_id)
        cur.execute("DELETE FROM orden_detalle WHERE id = %s", (detalle_id,))
        recalcular_total(cur, actual["orden_id"])
    return jsonify(mensaje="Detalle eliminado"), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)