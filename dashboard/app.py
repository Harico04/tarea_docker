import os
import re
from contextlib import closing
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import psycopg2
from dash import Dash, Input, Output, State, callback, dcc, html

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
ZONA = ZoneInfo(os.getenv("APP_TZ", "UTC"))


def hoy() -> date:
    return datetime.now(ZONA).date()


def formatear_fecha(f: date) -> str:
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def a_texto_plano(fragmento: str) -> str:
    """Quita las etiquetas HTML (se usa para el atributo alt de la imagen)."""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


VACIAS = {"br", "hr", "img"}
DESCARTAR = {"script", "style", "iframe", "object", "embed", "noscript", "template"}
PERMITIDAS = {
    "a", "abbr", "b", "blockquote", "cite", "code", "div", "em", "h1", "h2", "h3",
    "h4", "h5", "h6", "i", "li", "mark", "ol", "p", "pre", "q", "s", "small",
    "span", "strong", "sub", "sup", "u", "ul",
}
ATRIBUTOS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
}


def _url_segura(url: str) -> bool:
    limpia = re.sub(r"[\x00-\x20]", "", url).lower()
    return urlsplit(limpia).scheme in ("", "http", "https", "mailto", "tel")


def _crear(tag: str, attrs, hijos):
    props = {}
    for nombre, valor in attrs:
        valor = valor or ""
        if nombre not in ATRIBUTOS.get(tag, {"title"}):
            continue
        if nombre in ("href", "src") and not _url_segura(valor):
            continue
        props[nombre] = valor
    if tag == "a" and "href" in props:
        props["target"] = "_blank"
        props["rel"] = "noopener noreferrer"
    componente = getattr(html, tag.capitalize())
    return componente(**props) if tag in VACIAS else componente(hijos, **props)


class _HtmlADash(HTMLParser):
    """Convierte HTML en componentes Dash. Solo deja pasar etiquetas y atributos
    de la lista blanca, así que scripts, estilos y eventos (onclick, etc.) no
    llegan al navegador."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = []
        self.pila = []  # [(etiqueta, atributos, hijos)]
        self.descartando = 0

    def _destino(self):
        return self.pila[-1][2] if self.pila else self.raiz

    def _cerrar_ultima(self):
        tag, attrs, hijos = self.pila.pop()
        self._destino().append(_crear(tag, attrs, hijos))

    def handle_starttag(self, tag, attrs):
        if self.descartando or tag in DESCARTAR:
            if tag in DESCARTAR:
                self.descartando += 1
        elif tag in VACIAS:
            self._destino().append(_crear(tag, attrs, None))
        elif tag in PERMITIDAS:
            self.pila.append((tag, attrs, []))
        # Etiquetas desconocidas: se ignoran, pero se conserva su contenido.

    def handle_endtag(self, tag):
        if tag in DESCARTAR:
            self.descartando = max(0, self.descartando - 1)
        elif not self.descartando and tag in PERMITIDAS:
            if any(t == tag for t, _, _ in self.pila):
                while self.pila[-1][0] != tag:  # cierra etiquetas sin cerrar
                    self._cerrar_ultima()
                self._cerrar_ultima()

    def handle_data(self, data):
        if not self.descartando:
            self._destino().append(data)

    def resultado(self):
        self.close()
        while self.pila:
            self._cerrar_ultima()
        return self.raiz


def bloque_html(texto: str, clase: str):
    """Renderiza el HTML que viene en el texto de la base de datos."""
    parser = _HtmlADash()
    parser.feed(texto)
    return html.Div(parser.resultado(), className=clase)


def obtener_imagenes(desde: date, hasta: date) -> dict:
    """Devuelve {fecha: fila} de los registros entre ambas fechas (inclusive)."""
    with closing(
        psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "db"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=5,
        )
    ) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT fecha, imagen_url, autor, descripcion "
            "FROM imagenes WHERE fecha BETWEEN %s AND %s",
            (desde, hasta),
        )
        return {fila[0]: fila for fila in cur.fetchall()}


def dia_vacio(titulo: str, detalle: str, es_hoy: bool = False):
    ficha = []
    ficha += [
        html.H2(titulo, className="fecha"),
        html.P(detalle, className="autor"),
    ]
    return html.Article(
        className="dia dia--vacio",
        children=html.Div(
            className="bloque bloque--ficha",
            children=html.Section(className="ficha", children=ficha),
        ),
    )


def vista_dia(fila, es_hoy: bool = False):
    fecha, url, autor, descripcion = fila
    ficha = []
    ficha += [
        html.H2(formatear_fecha(fecha), className="fecha"),
        bloque_html(autor or "Autor desconocido", "autor"),
    ]
    if descripcion:
        ficha.append(bloque_html(descripcion, "descripcion"))

    alt = (a_texto_plano(descripcion) if descripcion else "") or "Imagen del día"

    return html.Article(
        className="dia",
        children=[
            html.Div(
                className="bloque bloque--imagen",
                children=html.Figure(className="marco", children=html.Img(src=url, alt=alt)),
            ),
            html.Div(
                className="bloque bloque--ficha",
                children=html.Section(className="ficha", children=ficha),
            ),
        ],
    )


def campo(etiqueta: str, id_: str, ejemplo: str, minimo: int, maximo: int):
    return html.Div(
        className="campo",
        children=[
            html.Label(etiqueta, htmlFor=id_),
            dcc.Input(
                id=id_, type="number", min=minimo, max=maximo, step=1,
                placeholder=ejemplo, autoComplete="off", n_submit=0,
                style={"fontFamily": "inherit"},
            ),
        ],
    )


app = Dash(
    __name__,
    title="Imagen del día",
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap"
    ],
)
server = app.server  # para gunicorn

app.layout = html.Div(
    style={"fontFamily": "'Inter', system-ui, sans-serif"},
    children=[
        html.Div(
            className="seccion seccion--buscador",
            children=html.Header(
                className="buscador",
                children=[
                    html.Div(
                        className="buscador__campos",
                        children=[
                            campo("Día", "dia", "DD", 1, 31),
                            campo("Mes", "mes", "MM", 1, 12),
                            campo("Año", "anio", "AAAA", 1, 9999),
                        ],
                    ),
                ],
            ),
        ),
        html.Div(className="seccion seccion--contenido", children=html.Div(id="contenido")),
        dcc.Store(id="fecha-elegida"),  # None = hoy; "invalida" = fecha incorrecta
        # Vuelve a consultar cada minuto: recoge los datos en cuanto el
        # recolector los inserta y cambia de día al pasar la medianoche.
        dcc.Interval(id="refresco", interval=60_000),
    ],
)


@callback(
    Output("fecha-elegida", "data"),
    Input("dia", "n_submit"),
    Input("mes", "n_submit"),
    Input("anio", "n_submit"),
    State("dia", "value"),
    State("mes", "value"),
    State("anio", "value"),
    prevent_initial_call=True,
)
def elegir_fecha(_d, _m, _a, dia, mes, anio):
    if dia is None and mes is None and anio is None:
        return None  # campos vacíos: volver a hoy
    try:
        return date(int(anio), int(mes), int(dia)).isoformat()
    except (TypeError, ValueError):
        return "invalida"


@callback(
    Output("contenido", "children"),
    Input("refresco", "n_intervals"),
    Input("fecha-elegida", "data"),
)
def actualizar(_, elegida):
    if elegida == "invalida":
        return html.Main(
            className="lista",
            children=dia_vacio("Fecha no válida", "Revisa el día, el mes y el año."),
        )

    fecha_hoy = hoy()
    fecha = date.fromisoformat(elegida) if elegida else fecha_hoy
    try:
        filas = obtener_imagenes(fecha, fecha)
    except psycopg2.Error:
        return html.Main(
            className="lista",
            children=dia_vacio("No se pudo leer la base de datos", "Se reintentará en un minuto."),
        )

    es_hoy = fecha == fecha_hoy
    return html.Main(
        className="lista",
        children=vista_dia(filas[fecha], es_hoy)
        if fecha in filas
        else dia_vacio(formatear_fecha(fecha), "No se tiene registro de este día.", es_hoy),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
