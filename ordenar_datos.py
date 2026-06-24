#!/usr/bin/env python3
"""
ordenar_datos.py — Auto-detección y ordenado de archivos CSV climáticos.

Uso:
  python3 ordenar_datos.py                  # escanea datos_crudos/ por defecto
  python3 ordenar_datos.py /ruta/a/carpeta  # carpeta a escanear

El script identifica cada CSV por su contenido (no por el nombre),
lo mueve al subdirectorio correcto y normaliza el nombre si es necesario.

Tipos soportados:
  • WeatherLink (7GT-EEP / 7GT-UES) → datos_crudos/weatherlink/
  • SMA inversor solar              → datos_crudos/sma_solar/
"""

import os
import re
import sys
import shutil
from datetime import datetime

# ── Rutas del proyecto ────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_WL_DEST    = os.path.join(_SCRIPT_DIR, "datos_crudos", "weatherlink")
_SMA_DEST   = os.path.join(_SCRIPT_DIR, "datos_crudos", "sma_solar")
_DEFAULT_IN = os.path.join(_SCRIPT_DIR, "datos_crudos")

# ── Patrones de fecha para archivos SMA ──────────────────────────────
_PAT_ISO   = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:\(\d+\))?\.csv$", re.I)
_PAT_LEGAC = re.compile(r"^(\d{2})-(\d{2})-(\d{4})(?:\(\d+\))?\.csv$", re.I)


# ─────────────────────────────────────────────────────────────────────
# Identificar tipo de archivo leyendo solo las primeras 2 líneas
# ─────────────────────────────────────────────────────────────────────

def _identificar(ruta: str) -> str:
    """
    Retorna: 'WL-EEP', 'WL-UES', 'SMA', o 'DESCONOCIDO'.
    Lee solo las 2 primeras líneas para no cargar el archivo completo.
    """
    try:
        for enc in ("utf-8", "latin-1"):
            try:
                with open(ruta, encoding=enc, errors="replace") as f:
                    linea0 = f.readline().strip().strip('"')
                    linea1 = f.readline().strip().strip('"')
                break
            except UnicodeDecodeError:
                continue
        else:
            return "DESCONOCIDO"

        # WeatherLink: primera línea es el nombre de la estación
        if "7GT-EEP" in linea0.upper():
            return "WL-EEP"
        if "7GT-UES" in linea0.upper():
            return "WL-UES"

        # SMA: primera línea tiene la firma del exportador
        if linea0.upper().startswith("CSV-EXPORT"):
            return "SMA"

        # Intento secundario: si la segunda línea tiene la firma SMA
        if linea1.upper().startswith("CSV-EXPORT"):
            return "SMA"

    except Exception:
        pass
    return "DESCONOCIDO"


# ─────────────────────────────────────────────────────────────────────
# Normalizar nombre de archivo SMA a YYYY-MM-DD.csv
# ─────────────────────────────────────────────────────────────────────

def _fecha_desde_nombre(fname: str):
    """
    Devuelve (año, mes, día) si el nombre tiene fecha, o None.
    Soporta: YYYY-MM-DD.csv, MM-DD-YYYY.csv (y variantes con (N)).
    """
    base = os.path.basename(fname)
    m = _PAT_ISO.match(base)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = _PAT_LEGAC.match(base)
    if m:
        return int(m.group(3)), int(m.group(1)), int(m.group(2))
    return None


def _nombre_sma_destino(ruta_src: str, destino_dir: str) -> str:
    """
    Calcula el path de destino para un archivo SMA.
    Normaliza a YYYY-MM-DD.csv; añade (N) si ya existe.
    """
    fecha = _fecha_desde_nombre(ruta_src)
    if fecha:
        año, mes, dia = fecha
        base_nombre = f"{año:04d}-{mes:02d}-{dia:02d}.csv"
    else:
        # Último recurso: conservar nombre original
        base_nombre = os.path.basename(ruta_src)

    dest = os.path.join(destino_dir, base_nombre)
    # Manejar duplicados: añadir (1), (2), …
    if os.path.exists(dest) and os.path.abspath(dest) != os.path.abspath(ruta_src):
        stem = base_nombre[:-4]  # quitar .csv
        n = 1
        while True:
            dest = os.path.join(destino_dir, f"{stem}({n}).csv")
            if not os.path.exists(dest):
                break
            n += 1
    return dest


# ─────────────────────────────────────────────────────────────────────
# Mover / copiar archivo al destino correcto
# ─────────────────────────────────────────────────────────────────────

def _mover(src: str, dest: str) -> bool:
    """Mueve src → dest. Crea directorio si no existe. Retorna True si OK."""
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.abspath(src) == os.path.abspath(dest):
            return False  # ya está en su lugar
        shutil.move(src, dest)
        return True
    except Exception as e:
        print(f"    ERROR al mover {src}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
# Escanear y ordenar
# ─────────────────────────────────────────────────────────────────────

def ordenar(directorio: str):
    directorio = os.path.abspath(directorio)
    if not os.path.isdir(directorio):
        print(f"Error: '{directorio}' no es un directorio válido.")
        sys.exit(1)

    os.makedirs(_WL_DEST, exist_ok=True)
    os.makedirs(_SMA_DEST, exist_ok=True)

    print(f"\nEscaneando: {directorio}")
    print("=" * 60)

    n_wl, n_sma, n_unk, n_lugar = 0, 0, 0, 0

    # Recolectar todos los CSV recursivamente
    todos = []
    for dirpath, _, filenames in os.walk(directorio):
        for fname in sorted(filenames):
            if fname.lower().endswith(".csv") and not fname.endswith("_clean.csv"):
                todos.append(os.path.join(dirpath, fname))

    if not todos:
        print("  No se encontraron archivos CSV.")
        return

    for ruta in todos:
        tipo = _identificar(ruta)
        fname = os.path.basename(ruta)

        if tipo in ("WL-EEP", "WL-UES"):
            dest = os.path.join(_WL_DEST, fname)
            if os.path.abspath(ruta) == os.path.abspath(dest):
                print(f"  ✓ (ya en lugar)  {fname}  [WeatherLink {tipo[3:]}]")
                n_lugar += 1
            elif _mover(ruta, dest):
                print(f"  ✓  {fname}  →  weatherlink/  [WeatherLink {tipo[3:]}]")
                n_wl += 1
        elif tipo == "SMA":
            dest = _nombre_sma_destino(ruta, _SMA_DEST)
            dest_base = os.path.basename(dest)
            if os.path.abspath(ruta) == os.path.abspath(dest):
                print(f"  ✓ (ya en lugar)  {fname}  [SMA]")
                n_lugar += 1
            elif _mover(ruta, dest):
                if dest_base != fname:
                    print(f"  ✓  {fname}  →  sma_solar/{dest_base}  [SMA, renombrado]")
                else:
                    print(f"  ✓  {fname}  →  sma_solar/  [SMA]")
                n_sma += 1
        else:
            print(f"  ?  {fname}  [formato desconocido — no movido]")
            n_unk += 1

    print("=" * 60)
    print(f"  WeatherLink: {n_wl} movido(s)  |  SMA: {n_sma} movido(s)  "
          f"|  Ya en lugar: {n_lugar}  |  Desconocidos: {n_unk}")
    if n_wl + n_sma + n_lugar > 0:
        print("\n  Siguiente paso:")
        print("    python3 ejecutar_proyecto.py")
    print()


# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    entrada = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_IN
    ordenar(entrada)
