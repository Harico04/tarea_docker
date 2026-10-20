"""Ejecuta un comando al arrancar y después todos los días a las 8:00 AM
(hora de APP_TZ; se cambia con HORA_EJECUCION=HH:MM).

Uso: python programador.py <comando> [argumentos...]
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZONA = ZoneInfo(os.getenv("APP_TZ", "UTC"))
HORA_EJECUCION = os.getenv("HORA_EJECUCION", "08:00")  # HH:MM en la zona APP_TZ
EJECUTAR_AL_ARRANCAR = os.getenv("EJECUTAR_AL_ARRANCAR", "1") == "1"
INTENTOS = int(os.getenv("REINTENTOS", "5"))
ESPERA_REINTENTO = int(os.getenv("ESPERA_REINTENTO", "60"))  # segundos


def proxima_ejecucion(ahora: datetime) -> datetime:
    hora, minuto = map(int, HORA_EJECUCION.split(":"))
    hoy_a_la_hora = ahora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    return hoy_a_la_hora if ahora < hoy_a_la_hora else hoy_a_la_hora + timedelta(days=1)


def ejecutar(comando: list[str]) -> int:
    print(f"[{datetime.now(ZONA):%Y-%m-%d %H:%M:%S}] Ejecutando: {' '.join(comando)}", flush=True)
    resultado = subprocess.run(comando)
    print(f"[{datetime.now(ZONA):%Y-%m-%d %H:%M:%S}] Terminó con código {resultado.returncode}", flush=True)
    return resultado.returncode


def ejecutar_con_reintentos(comando: list[str]) -> None:
    """Reintenta si el comando falla (código distinto de 0): al reiniciar el equipo
    la base de datos puede tardar unos segundos en estar lista, y la API puede fallar."""
    for intento in range(1, INTENTOS + 1):
        if ejecutar(comando) == 0:
            return
        if intento < INTENTOS:
            print(f"Falló (intento {intento}/{INTENTOS}). Reintentando en {ESPERA_REINTENTO} s.", flush=True)
            time.sleep(ESPERA_REINTENTO)
    print("Se agotaron los intentos; se reintentará en la próxima ejecución programada.", flush=True)


def main() -> None:
    comando = sys.argv[1:]
    if not comando:
        sys.exit("Uso: python programador.py <comando> [argumentos...]")

    if EJECUTAR_AL_ARRANCAR:
        ejecutar_con_reintentos(comando)

    while True:
        objetivo = proxima_ejecucion(datetime.now(ZONA))
        print(f"Próxima ejecución: {objetivo:%Y-%m-%d %H:%M:%S %Z}", flush=True)
        # Duerme en tramos cortos para no desviarse si el reloj cambia o el equipo se suspende.
        while (restante := (objetivo.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()) > 0:
            time.sleep(min(restante, 30))
        ejecutar_con_reintentos(comando)


if __name__ == "__main__":
    main()
