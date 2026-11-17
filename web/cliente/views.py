from datetime import date

import requests
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

ESTADOS = ["Pendiente", "Pagada", "Anulada"]


class ApiError(Exception):
    """Error devuelto por la API o por no poder conectarse a ella."""


def api(metodo, ruta, **kwargs):
    url = f"{settings.API_URL}{ruta}"
    try:
        r = requests.request(metodo, url, timeout=10, **kwargs)
    except requests.RequestException:
        raise ApiError("No se pudo conectar con la API. Intente de nuevo en unos segundos.")
    if r.status_code >= 400:
        try:
            mensaje = r.json().get("error", r.text)
        except ValueError:
            mensaje = r.text or "Error desconocido"
        raise ApiError(f"{mensaje} (código {r.status_code})")
    return r.json() if r.content else None


def datos_orden(post):
    return {
        "cliente": post.get("cliente", "").strip(),
        "fecha": post.get("fecha", ""),
        "estado": post.get("estado", "Pendiente"),
    }


def datos_detalle(post):
    return {
        "producto": post.get("producto", "").strip(),
        "cantidad": post.get("cantidad", ""),
        "precio_unitario": post.get("precio_unitario", ""),
    }


# ---------------- Órdenes ----------------
def lista_ordenes(request):
    ordenes = []
    try:
        ordenes = api("GET", "/api/ordenes")
    except ApiError as e:
        messages.error(request, str(e))
    return render(request, "cliente/lista_ordenes.html", {"ordenes": ordenes})


@require_http_methods(["GET", "POST"])
def crear_orden(request):
    contexto = {"titulo": "Nueva orden", "estados": ESTADOS}
    if request.method == "POST":
        datos = datos_orden(request.POST)
        try:
            nueva = api("POST", "/api/ordenes", json=datos)
        except ApiError as e:
            messages.error(request, str(e))
            return render(request, "cliente/form_orden.html", {**contexto, "orden": datos})
        messages.success(request, f"Orden #{nueva['id']} creada. Ahora agrega sus productos.")
        return redirect("detalle_orden", orden_id=nueva["id"])
    orden = {"fecha": date.today().isoformat(), "estado": "Pendiente"}
    return render(request, "cliente/form_orden.html", {**contexto, "orden": orden})


@require_http_methods(["GET", "POST"])
def editar_orden(request, orden_id):
    contexto = {"titulo": f"Editar orden #{orden_id}", "estados": ESTADOS}
    if request.method == "POST":
        datos = datos_orden(request.POST)
        try:
            api("PUT", f"/api/ordenes/{orden_id}", json=datos)
        except ApiError as e:
            messages.error(request, str(e))
            return render(request, "cliente/form_orden.html", {**contexto, "orden": datos})
        messages.success(request, f"Orden #{orden_id} actualizada.")
        return redirect("detalle_orden", orden_id=orden_id)
    try:
        orden = api("GET", f"/api/ordenes/{orden_id}")
    except ApiError as e:
        messages.error(request, str(e))
        return redirect("lista_ordenes")
    return render(request, "cliente/form_orden.html", {**contexto, "orden": orden})


@require_POST
def eliminar_orden(request, orden_id):
    try:
        api("DELETE", f"/api/ordenes/{orden_id}")
        messages.success(request, f"Orden #{orden_id} eliminada.")
    except ApiError as e:
        messages.error(request, str(e))
    return redirect("lista_ordenes")


# ---------------- Detalles ----------------
def detalle_orden(request, orden_id):
    try:
        orden = api("GET", f"/api/ordenes/{orden_id}")
    except ApiError as e:
        messages.error(request, str(e))
        return redirect("lista_ordenes")
    editar = request.GET.get("editar", "")
    editar_id = int(editar) if editar.isdigit() else None
    return render(
        request,
        "cliente/detalle_orden.html",
        {"orden": orden, "detalles": orden["detalles"], "editar_id": editar_id},
    )


@require_POST
def agregar_detalle(request, orden_id):
    try:
        api("POST", f"/api/ordenes/{orden_id}/detalles", json=datos_detalle(request.POST))
        messages.success(request, "Producto agregado. El total se recalculó.")
    except ApiError as e:
        messages.error(request, str(e))
    return redirect("detalle_orden", orden_id=orden_id)


@require_POST
def editar_detalle(request, orden_id, detalle_id):
    try:
        api("PUT", f"/api/detalles/{detalle_id}", json=datos_detalle(request.POST))
        messages.success(request, "Producto actualizado. El total se recalculó.")
        return redirect("detalle_orden", orden_id=orden_id)
    except ApiError as e:
        messages.error(request, str(e))
        return redirect(f"/ordenes/{orden_id}/?editar={detalle_id}")


@require_POST
def eliminar_detalle(request, orden_id, detalle_id):
    try:
        api("DELETE", f"/api/detalles/{detalle_id}")
        messages.success(request, "Producto eliminado. El total se recalculó.")
    except ApiError as e:
        messages.error(request, str(e))
    return redirect("detalle_orden", orden_id=orden_id)