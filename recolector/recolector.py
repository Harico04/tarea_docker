import os
import re
import requests
import psycopg2
from datetime import date

URL = "https://science.nasa.gov/wp-json/wp/v2/apod-basic"


def obtener_apod():
    hoy = date.today().strftime("%y%m%d")
    r = requests.get(URL, params={"date_from": hoy, "date_to": hoy}, timeout=10)
    r.raise_for_status()
    datos = r.json()
    return datos[0] if datos else None


def limpiar_explicacion(h):
    if not h:
        return None
    h = re.sub(r"^\s*<strong>\s*Explanation:\s*</strong>\s*", "", h, flags=re.I)
    h = re.sub(r"(<br\s*/?>\s*)*<strong>\s*Tomorrow.*$", "", h, flags=re.S | re.I)
    return h.strip() or None


def guardar(dato):
    imagen_url = dato.get("hdurl")
    if not imagen_url:
        print(f"Sin imagen hoy (media_type={dato.get('media_type')}), no se guarda")
        return False

    autor = (dato.get("credit") or "").strip() or None
    descripcion = limpiar_explicacion(dato.get("explanation"))

    conn = psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    try:
        with conn, conn.cursor() as cur:   # `with conn` hace commit al salir
            cur.execute(
                """
                INSERT INTO imagenes (fecha, imagen_url, autor, descripcion)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (fecha) DO NOTHING
                """,
                (dato["date"], imagen_url, autor, descripcion),
            )
            return cur.rowcount == 1       # True si insertó, False si ya existía
    finally:
        conn.close()


if __name__ == "__main__":
    dato = obtener_apod()
    if dato is None:
        print("Todavía no hay entrada para hoy")
    else:
        print("Fecha:", dato["date"])
        print("Imagen:", dato.get("hdurl"))
        if guardar(dato):
            print("Guardada en la base de datos")
        else:
            print("No se guardó (ya existía o no hay imagen)")
