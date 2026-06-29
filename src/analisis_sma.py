#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=======================================================================
FASE VI — ANÁLISIS DEL SISTEMA SOLAR SMA + PIRANÓMETRO PYRA0102
Módulo complementario a analisis_climatico.py

Sensores procesados:
  · PYRA0102  (S/N 158511170)  — Piranómetro + sensor ambiental
  · WR725UAE  (S/N 2000801893) — Inversor SMA #1
  · WR725UAE  (S/N 2000801894) — Inversor SMA #2
  · WR725UAE  (S/N 2000801917) — Inversor SMA #3

Fuentes de datos:
  · 2023-2024/2023/    → datos históricos 2023
  · 2023-2024/2024/    → datos históricos 2024
  · SMA-EIE-2025-2026/ → datos recientes 2025–2026

Restricciones cumplidas:
  Sin .mean()/.std()/.median()/.min()/.max()/.quantile()
  Motor estadístico 100 % manual (bucles Python + Newton-Raphson)
=======================================================================
"""

import os
import sys
import re
import io
import math
import json
import base64
import datetime

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ═══════════════════════════════════════════════════════════════════════
# RUTAS BASE DEL PROYECTO
# ═══════════════════════════════════════════════════════════════════════

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT   = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
_DATA_SMA    = os.path.join(_PROJ_ROOT, "datos_crudos", "sma_solar")
_DASH_DIR    = os.path.join(_PROJ_ROOT, "dashboard")
_EXPORT_DIR  = os.path.join(_DASH_DIR, "exportaciones")

# Añadir core_math al path para importar wrappers C++
sys.path.insert(0, os.path.join(_PROJ_ROOT, "core_math"))

# ═══════════════════════════════════════════════════════════════════════
# CONSTANTES Y CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════

def _descubrir_carpetas_sma(raiz: str) -> list:
    """Devuelve todos los subdirectorios de raiz que contengan CSVs SMA."""
    carpetas = set()
    for dirpath, _, filenames in os.walk(raiz):
        if any(f.lower().endswith(".csv") for f in filenames):
            carpetas.add(dirpath)
    return sorted(carpetas)

_CARPETAS_SMA = _descubrir_carpetas_sma(_DATA_SMA)

# Índices de columna en el CSV SMA (58 columnas totales)
_IDX = {
    "ts":    0,    # TimeStamp hh:mm
    "hum":   1,    # envhmdt       %
    "press": 2,    # envpress      hPa
    "irr":   4,    # IntSolIrr     W/m²
    "tamb":  7,    # TmpAmb C      °C
    "tmod":  10,   # TmpMdul C     °C (temperatura módulo solar)
    # Inversor 1
    "etot1": 15, "fac1": 16, "iac1": 19, "ipv1": 20,
    "pac1":  22, "tinv1": 25, "vac1": 26, "vpv1": 27,
    # Inversor 2
    "etot2": 30, "fac2": 31, "iac2": 34, "ipv2": 35,
    "pac2":  37, "tinv2": 40, "vac2": 41, "vpv2": 42,
    # Inversor 3
    "etot3": 45, "fac3": 46, "iac3": 49, "ipv3": 50,
    "pac3":  52, "tinv3": 55, "vac3": 56, "vpv3": 57,
}

_C = dict(
    fondo="#050f2e", ax=(0.04, 0.12, 0.25, 1.0),
    grid=(1, 1, 1, 0.05), texto="#7b93c4", primario="#e8f0ff",
    naranja="#f59e0b", azul="#3b82f6", cyan="#06b6d4",
    verde="#10b981", amarillo="#fbbf24", rojo="#ef4444",
    rosa="#fca5a5", morado="#a78bfa", lima="#84cc16",
)

plt.rcParams.update({
    "text.color": _C["texto"],
    "axes.labelcolor": _C["texto"],
    "xtick.color": _C["texto"],
    "ytick.color": _C["texto"],
})

# ═══════════════════════════════════════════════════════════════════════
# MOTOR MATEMÁTICO MANUAL (sin cajas negras)
# ═══════════════════════════════════════════════════════════════════════

def _es_nan(v) -> bool:
    try:
        return v != v
    except TypeError:
        return False


def _media(s: list) -> float:
    n = len(s)
    if n == 0:
        return float("nan")
    total = 0.0
    for v in s:
        total += v
    return total / n


def _varianza(s: list) -> float:
    n = len(s)
    if n < 2:
        return float("nan")
    mu = _media(s)
    acc = 0.0
    for v in s:
        d = v - mu
        acc += d * d
    return acc / (n - 1)


def _sqrt_nr(S: float) -> float:
    """√S por Newton-Raphson (Método Babilónico)."""
    if S < 0:
        return float("nan")
    if S == 0.0:
        return 0.0
    x = max(S, 1.0)
    for _ in range(200):
        xn = 0.5 * (x + S / x)
        if abs(xn - x) < 1e-13 * max(abs(x), 1e-300):
            break
        x = xn
    return x


def _maximo(s: list) -> float:
    if not s:
        return float("nan")
    p = s[0]
    for v in s[1:]:
        if v > p:
            p = v
    return p


def _minimo(s: list) -> float:
    if not s:
        return float("nan")
    p = s[0]
    for v in s[1:]:
        if v < p:
            p = v
    return p


def _quicksort(arr: list) -> list:
    n = len(arr)
    if n <= 1:
        return arr[:]
    a, b, c = arr[0], arr[n // 2], arr[-1]
    pivot = sorted([a, b, c])[1]
    return (_quicksort([x for x in arr if x < pivot])
            + [x for x in arr if x == pivot]
            + _quicksort([x for x in arr if x > pivot]))


def _percentil(s: list, p: float) -> float:
    if not s:
        return float("nan")
    o = _quicksort(s)
    n = len(o)
    L = (p / 100.0) * (n - 1)
    idx = int(L)
    frac = L - idx
    if idx + 1 >= n:
        return float(o[-1])
    return float(o[idx]) + frac * (float(o[idx + 1]) - float(o[idx]))


def _log2(n: float) -> float:
    return math.log(n) / math.log(2)


def _pearson(sx: list, sy: list) -> float:
    n = len(sx)
    if n < 2 or n != len(sy):
        return float("nan")
    mx, my = _media(sx), _media(sy)
    num = sq_x = sq_y = 0.0
    for xi, yi in zip(sx, sy):
        dx, dy = xi - mx, yi - my
        num  += dx * dy
        sq_x += dx * dx
        sq_y += dy * dy
    den = _sqrt_nr(sq_x * sq_y)
    return num / den if den != 0 else float("nan")


def _estadisticos(s: list, col: str = "") -> dict:
    """Estadísticos descriptivos completos — sin cajas negras."""
    n = len(s)
    if n == 0:
        return {"col": col, "n": 0}
    mu   = _media(s)
    var  = _varianza(s)
    sig  = _sqrt_nr(var)
    vmax = _maximo(s)
    vmin = _minimo(s)
    p25  = _percentil(s, 25)
    p50  = _percentil(s, 50)
    p75  = _percentil(s, 75)
    p10  = _percentil(s, 10)
    p90  = _percentil(s, 90)
    iqr  = p75 - p25
    ic   = 1.645 * sig / _sqrt_nr(n)
    return {
        "col": col, "n": n,
        "media": mu, "varianza": var, "desv_estandar": sig,
        "maximo": vmax, "minimo": vmin, "rango": vmax - vmin,
        "p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90,
        "iqr": iqr, "ic_inf": mu - ic, "ic_sup": mu + ic,
    }


# ═══════════════════════════════════════════════════════════════════════
# CARGA Y PARSEO DE CSV SMA
# ═══════════════════════════════════════════════════════════════════════

def _parse_fecha_nombre(nombre: str):
    """
    Extrae fecha de nombre de archivo.
    Formatos aceptados:
      YYYY-MM-DD[.csv]          → estándar
      YYYY-MM-DD(N)[.csv]       → duplicado (se ignora el sufijo)
      MM-DD-YYYY[.csv]          → formato antiguo
      MM-DD-YYYY(N)[.csv]       → duplicado antiguo
    Retorna datetime.date o None.
    """
    base = os.path.splitext(os.path.basename(nombre))[0]
    base = re.sub(r'\(\d+\)', '', base).strip()

    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', base)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    m = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', base)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None

    return None


def _float_safe(s: str):
    """Convierte cadena a float; retorna None si falla."""
    v = s.strip()
    if not v or v in ('--', '-', 'nan', 'None', 'N/A'):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _cargar_csv_dia(ruta: str, fecha: datetime.date) -> list:
    """
    Parsea un CSV SMA de un día y retorna lista de dicts.
    Maneja separadores ; y , automáticamente.
    Columnas derivadas: pac_total, energia_wh (estimada por intervalo).
    """
    try:
        with open(ruta, encoding='latin-1') as f:
            lineas = f.readlines()
    except Exception as e:
        print(f"  [WARN SMA] No se pudo leer {os.path.basename(ruta)}: {e}")
        return []

    if not lineas:
        return []

    # Detectar separador
    sep = ';' if lineas[0].count(';') > lineas[0].count(',') else ','

    # Encontrar primera fila de datos (comienza con HH:MM)
    data_start = None
    for i, linea in enumerate(lineas):
        partes = linea.strip().split(sep)
        ts_raw = partes[0].strip().strip('"') if partes else ""
        # Acepta hh:mm o fechas tipo DD.MM.YYYY hh:mm o YYYY-MM-DD hh:mm
        if re.match(r'^\d{1,2}:\d{2}$', ts_raw):
            data_start = i
            break
        if re.search(r'\d{1,2}:\d{2}$', ts_raw) and re.search(r'\d{2}[\.\-]\d{2}[\.\-]\d{2,4}', ts_raw):
            data_start = i
            break

    if data_start is None:
        return []

    # Calcular intervalo (en minutos) para energía
    # Se lee de las primeras 2 filas de datos
    intervalo_min = 15.0
    filas_ts = []
    for linea in lineas[data_start:data_start + 5]:
        partes = linea.strip().split(sep)
        ts_raw = partes[0].strip().strip('"') if partes else ""
        t_m = re.search(r'(\d{1,2}):(\d{2})$', ts_raw)
        if t_m:
            filas_ts.append(int(t_m.group(1)) * 60 + int(t_m.group(2)))
    if len(filas_ts) >= 2 and filas_ts[1] != filas_ts[0]:
        delta = abs(filas_ts[1] - filas_ts[0])
        if 1 <= delta <= 60:
            intervalo_min = float(delta)

    registros = []
    timestamps_vistos = set()

    for linea in lineas[data_start:]:
        partes = linea.strip().split(sep)
        if len(partes) < 8:
            continue

        ts_raw = partes[0].strip().strip('"')
        t_m = re.search(r'(\d{1,2}):(\d{2})$', ts_raw)
        if not t_m:
            t_m = re.search(r'(\d{1,2}):(\d{2})', ts_raw)
        if not t_m:
            continue

        hora   = int(t_m.group(1))
        minuto = int(t_m.group(2))
        if hora > 23 or minuto > 59:
            continue

        try:
            dt = datetime.datetime(fecha.year, fecha.month, fecha.day, hora, minuto)
        except ValueError:
            continue

        # Evitar duplicados en el mismo archivo
        if dt in timestamps_vistos:
            continue
        timestamps_vistos.add(dt)

        fila = {"datetime": dt}

        for alias, idx in _IDX.items():
            if alias == "ts" or idx >= len(partes):
                continue
            v = _float_safe(partes[idx])
            if v is not None:
                fila[alias] = v

        # Pac total de los 3 inversores
        p1 = fila.get("pac1", 0.0) or 0.0
        p2 = fila.get("pac2", 0.0) or 0.0
        p3 = fila.get("pac3", 0.0) or 0.0
        fila["pac_total"] = p1 + p2 + p3

        # Energía estimada en este intervalo (W → Wh)
        fila["energia_wh"] = fila["pac_total"] * intervalo_min / 60.0
        # Irradiancia integrada en este intervalo (W/m² → Wh/m²)
        fila["irr_wh"] = (fila.get("irr") or 0.0) * intervalo_min / 60.0

        registros.append(fila)

    return registros


def cargar_todos_sma(carpetas: list = None, verbose: bool = True) -> pd.DataFrame:
    """
    Carga todos los CSV SMA desde las carpetas indicadas.
    Retorna un DataFrame con datetime como índice, ordenado cronológicamente.
    Los archivos con duplicados (nombre(1).csv) se fusionan con el principal.
    """
    if carpetas is None:
        carpetas = _CARPETAS_SMA

    # Agrupar archivos por fecha para fusionar duplicados
    archivos_por_fecha: dict = {}

    for carpeta in carpetas:
        if not os.path.isdir(carpeta):
            if verbose:
                print(f"  [WARN SMA] Carpeta no encontrada: {carpeta}")
            continue
        for fname in sorted(os.listdir(carpeta)):
            if not fname.lower().endswith('.csv'):
                continue
            fecha = _parse_fecha_nombre(fname)
            if fecha is None:
                if verbose:
                    print(f"  [WARN SMA] Nombre no reconocido: {fname}")
                continue
            ruta = os.path.join(carpeta, fname)
            archivos_por_fecha.setdefault(fecha, []).append(ruta)

    todas_las_fechas = sorted(archivos_por_fecha.keys())
    if verbose:
        print(f"  [SMA] {len(todas_las_fechas)} fechas únicas "
              f"({todas_las_fechas[0]} → {todas_las_fechas[-1]})")

    todos_registros: list = []
    timestamps_globales: set = set()

    for i, fecha in enumerate(todas_las_fechas):
        if verbose and i % 100 == 0:
            pct = int(i / len(todas_las_fechas) * 100)
            print(f"  [SMA] cargando {i}/{len(todas_las_fechas)} ({pct}%)...",
                  end="\r", flush=True)

        for ruta in archivos_por_fecha[fecha]:
            registros = _cargar_csv_dia(ruta, fecha)
            for r in registros:
                if r["datetime"] not in timestamps_globales:
                    timestamps_globales.add(r["datetime"])
                    todos_registros.append(r)

    if verbose:
        print(f"\n  [SMA] {len(todos_registros):,} registros cargados totales.")

    if not todos_registros:
        return pd.DataFrame()

    df = pd.DataFrame(todos_registros)
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


# ═══════════════════════════════════════════════════════════════════════
# ANÁLISIS ESTADÍSTICO
# ═══════════════════════════════════════════════════════════════════════

_VARIABLES_SMA = [
    ("irr",       "Irradiancia Solar (W/m²)",         "IntSolIrr — PYRA0102"),
    ("tamb",      "Temperatura Ambiente (°C)",          "TmpAmb — PYRA0102"),
    ("tmod",      "Temperatura Módulo (°C)",            "TmpMdul — PYRA0102"),
    ("hum",       "Humedad Ambiente (%)",               "envhmdt — PYRA0102"),
    ("press",     "Presión Ambiente (hPa)",             "envpress — PYRA0102"),
    ("pac_total", "Potencia AC Total (W)",              "Pac Inv1+Inv2+Inv3"),
    ("pac1",      "Potencia AC Inversor 1 (W)",         "Pac — WR725UAE #1"),
    ("pac2",      "Potencia AC Inversor 2 (W)",         "Pac — WR725UAE #2"),
    ("pac3",      "Potencia AC Inversor 3 (W)",         "Pac — WR725UAE #3"),
    ("vac1",      "Tensión AC Inversor 1 (V)",         "Vac — WR725UAE #1"),
    ("vpv1",      "Tensión PV Inversor 1 (V)",         "Vpv — WR725UAE #1"),
    ("fac1",      "Frecuencia Red Inv1 (Hz)",           "Fac — WR725UAE #1"),
    ("tinv1",     "Temperatura Inversor 1 (°C)",        "Temp — WR725UAE #1"),
    ("tinv2",     "Temperatura Inversor 2 (°C)",        "Temp — WR725UAE #2"),
    ("tinv3",     "Temperatura Inversor 3 (°C)",        "Temp — WR725UAE #3"),
    ("energia_wh","Energía por Intervalo (Wh)",         "Pac_total × Δt"),
]


def calcular_estadisticos_sma(df: pd.DataFrame) -> dict:
    """
    Calcula estadísticos descriptivos para todas las variables SMA.
    Motor 100 % manual — sin .mean()/.std()/.median()/.min()/.max().
    """
    resultado = {}
    for alias, nombre, fuente in _VARIABLES_SMA:
        if alias not in df.columns:
            continue
        vals = [float(v) for v in df[alias].tolist()
                if not _es_nan(v) and v is not None]
        if not vals:
            continue
        st = _estadisticos(vals, alias)
        st["nombre"] = nombre
        st["fuente"] = fuente
        resultado[alias] = st
    return resultado


def calcular_stats_mensuales_sma(df: pd.DataFrame) -> dict:
    """
    Estadísticos mes a mes para variables clave del sistema solar.
    Retorna: { alias: { 'YYYY-MM': {...stats...} } }
    """
    df2 = df.copy()
    df2["_mes"] = df2["datetime"].dt.to_period("M")
    periodos = sorted(df2["_mes"].dropna().unique(), key=str)

    resultado = {}
    for alias in ["irr", "pac_total", "tamb", "tmod", "energia_wh"]:
        if alias not in df2.columns:
            continue
        por_mes = {}
        for p in periodos:
            mask = (df2["_mes"] == p).tolist()
            s = []
            for inc, v in zip(mask, df2[alias].tolist()):
                if inc and not _es_nan(v) and v is not None:
                    try:
                        s.append(float(v))
                    except (TypeError, ValueError):
                        pass
            if s:
                por_mes[str(p)] = _estadisticos(s)
        resultado[alias] = por_mes
    return resultado


def calcular_energia_diaria(df: pd.DataFrame) -> dict:
    """
    Suma la energía producida por día (kWh).
    Retorna { 'YYYY-MM-DD': energia_kwh }
    """
    df2 = df[["datetime", "energia_wh"]].copy()
    df2["_fecha"] = df2["datetime"].dt.strftime("%Y-%m-%d")
    fechas = sorted(df2["_fecha"].unique())
    resultado = {}
    for f in fechas:
        mask = (df2["_fecha"] == f).tolist()
        total_wh = 0.0
        for inc, v in zip(mask, df2["energia_wh"].tolist()):
            if inc and not _es_nan(v) and v is not None:
                try:
                    total_wh += float(v)
                except (TypeError, ValueError):
                    pass
        resultado[f] = round(total_wh / 1000.0, 4)   # → kWh
    return resultado


def calcular_energia_mensual(energia_diaria: dict) -> dict:
    """Agrupa energía diaria por mes (kWh/mes)."""
    por_mes: dict = {}
    for fecha_str, kwh in energia_diaria.items():
        mes = fecha_str[:7]   # 'YYYY-MM'
        por_mes[mes] = por_mes.get(mes, 0.0) + kwh
    return {k: round(v, 3) for k, v in sorted(por_mes.items())}


def calcular_eficiencia(df: pd.DataFrame) -> dict:
    """
    Correlación de Pearson: irradiancia vs potencia total.
    Solo con registros donde irr > 10 W/m² (luz solar real).
    """
    irr_vals, pac_vals = [], []
    for irr, pac in zip(df.get("irr", []), df.get("pac_total", [])):
        if (not _es_nan(irr) and not _es_nan(pac)
                and irr is not None and pac is not None):
            fi, fp = float(irr), float(pac)
            if fi > 10.0:
                irr_vals.append(fi)
                pac_vals.append(fp)

    r = _pearson(irr_vals, pac_vals)
    return {
        "r": r, "r2": r * r if not _es_nan(r) else float("nan"),
        "n": len(irr_vals),
        "interpretacion": (
            "Muy fuerte" if abs(r) >= 0.9 else
            "Fuerte"     if abs(r) >= 0.7 else
            "Moderada"   if abs(r) >= 0.5 else
            "Débil"
        ) if not _es_nan(r) else "N/D",
    }


# ═══════════════════════════════════════════════════════════════════════
# VISUALIZACIONES
# ═══════════════════════════════════════════════════════════════════════

def _ax_dark(ax, titulo="", xlabel="", ylabel=""):
    ax.set_facecolor(_C["ax"])
    ax.grid(True, color=_C["grid"], linestyle="-", linewidth=0.6)
    ax.tick_params(colors=_C["texto"], labelsize=8)
    for sp in ax.spines.values():
        sp.set_edgecolor("#1e3a5f")
    if titulo:
        ax.set_title(titulo, color=_C["primario"], fontsize=10,
                     fontweight="bold", pad=10)
    if xlabel:
        ax.set_xlabel(xlabel, color=_C["texto"], fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=_C["texto"], fontsize=9)


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                dpi=140, facecolor=fig.get_facecolor())
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return b64


def _media_movil(valores: list, ventana: int) -> list:
    """Media móvil manual sin .rolling()."""
    n = len(valores)
    resultado = []
    for i in range(n):
        inicio = max(0, i - ventana // 2)
        fin    = min(n, i + ventana // 2)
        bloque = [v for v in valores[inicio:fin] if not _es_nan(v)]
        resultado.append(_media(bloque) if bloque else float("nan"))
    return resultado


def graf_serie_sma(df: pd.DataFrame, col: str,
                   titulo: str, ylabel: str, color: str,
                   ventana: int = 288) -> str:
    """Serie temporal con media móvil."""
    if col not in df.columns:
        return ""
    valores = df[col].tolist()
    n = len(valores)
    if n == 0:
        return ""

    mm = _media_movil(valores, ventana)

    fig, ax = plt.subplots(figsize=(13, 3.6))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, titulo, "Tiempo", ylabel)

    x = list(range(n))
    limpio = [v if not _es_nan(v) else 0 for v in valores]
    ax.fill_between(x, limpio, alpha=0.10, color=color)
    ax.plot(x, valores, color=color, linewidth=0.5, alpha=0.65, label="Medición")
    ax.plot(x, mm, color=_C["amarillo"], linewidth=1.8, alpha=0.95,
            label=f"Media móvil ({ventana} muestras)")

    paso = max(1, n // 8)
    ticks = list(range(0, n, paso))
    fechas = df["datetime"].tolist()
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(fechas[i])[:10] for i in ticks if i < n],
                       color=_C["texto"], fontsize=7, rotation=15)
    ax.legend(facecolor=_C["fondo"], labelcolor=_C["texto"],
              fontsize=8, edgecolor="#1e3a5f", loc="upper right")
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def graf_histograma_sma(s: list, titulo: str, xlabel: str,
                        color: str = "#f59e0b") -> str:
    """Histograma con regla de Sturges — 100 % manual."""
    n = len(s)
    if n < 5:
        return ""
    k = max(5, math.ceil(_log2(n) + 1))
    vmin, vmax = _minimo(s), _maximo(s)
    ancho = (vmax - vmin) / k if (vmax - vmin) > 0 else 1.0

    freq = [0] * k
    for v in s:
        idx = int((v - vmin) / ancho)
        idx = max(0, min(k - 1, idx))
        freq[idx] += 1

    centros = [vmin + (i + 0.5) * ancho for i in range(k)]
    mu  = _media(s)
    sig = _sqrt_nr(_varianza(s))

    fig, ax = plt.subplots(figsize=(11, 4.2))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, titulo, xlabel, "Frecuencia Absoluta")
    ax.bar(centros, freq, width=ancho * 0.88, color=color,
           edgecolor="#0a1220", linewidth=0.9, alpha=0.85, align="center")
    ax.axvline(mu, color=_C["rojo"], linestyle="--", linewidth=2.0,
               label=f"x̄ = {mu:.2f}")
    ax.axvline(mu - sig, color=_C["amarillo"], linestyle=":", linewidth=1.4,
               label=f"−σ = {mu - sig:.2f}")
    ax.axvline(mu + sig, color=_C["amarillo"], linestyle=":", linewidth=1.4,
               label=f"+σ = {mu + sig:.2f}")
    ax.legend(facecolor=_C["fondo"], labelcolor=_C["texto"],
              fontsize=8.5, edgecolor="#1e3a5f")
    ax.text(0.98, 0.95, f"k Sturges = {k}", transform=ax.transAxes,
            color=_C["texto"], fontsize=8, ha="right", va="top",
            family="monospace")
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def graf_boxplot_mensual_sma(stats_men: dict, col: str, titulo: str) -> str:
    """Boxplot mensual dibujado a mano (sin ax.boxplot)."""
    datos_mes = stats_men.get(col, {})
    if not datos_mes:
        return ""

    meses = sorted(datos_mes.keys())
    if not meses:
        return ""

    fig, ax = plt.subplots(figsize=(max(12, len(meses) * 1.1), 5.5))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, titulo, "Mes", col)

    posiciones = list(range(1, len(meses) + 1))

    for pos, mes in zip(posiciones, meses):
        sm = datos_mes[mes]
        q1, q2, q3 = sm.get("p25", 0), sm.get("p50", 0), sm.get("p75", 0)
        iqr = q3 - q1
        lim_inf = q1 - 1.5 * iqr
        lim_sup = q3 + 1.5 * iqr
        vmin_mes = sm.get("minimo", q1)
        vmax_mes = sm.get("maximo", q3)
        bw_inf = max(lim_inf, vmin_mes)
        bw_sup = min(lim_sup, vmax_mes)

        rect = mpatches.FancyBboxPatch(
            (pos - 0.36, q1), 0.72, max(q3 - q1, 0.01),
            boxstyle="round,pad=0.02",
            facecolor="#0d2e6e", edgecolor=_C["azul"], linewidth=1.6
        )
        ax.add_patch(rect)
        ax.plot([pos - 0.36, pos + 0.36], [q2, q2],
                color=_C["amarillo"], linewidth=2.5)
        for bv in [bw_inf, bw_sup]:
            ax.plot([pos - 0.2, pos + 0.2], [bv, bv],
                    color=_C["cyan"], linewidth=1.4)
        ax.plot([pos, pos], [bw_inf, q1], color=_C["cyan"], linewidth=1.1)
        ax.plot([pos, pos], [q3, bw_sup], color=_C["cyan"], linewidth=1.1)

    ax.set_xticks(posiciones)
    ax.set_xticklabels(
        [m[5:] for m in meses], rotation=45,
        color=_C["texto"], fontsize=7.5, ha="right"
    )
    ax.set_xlim(0.3, len(posiciones) + 0.7)
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def graf_energia_mensual(energia_mensual: dict) -> str:
    """Barras de energía producida por mes (kWh)."""
    if not energia_mensual:
        return ""

    meses = sorted(energia_mensual.keys())
    valores = [energia_mensual[m] for m in meses]
    if not valores:
        return ""

    mu = _media(valores)
    etiquetas = [m[5:] + "\n" + m[:4] for m in meses]

    colores = [_C["verde"] if v >= mu else _C["azul"] for v in valores]

    fig, ax = plt.subplots(figsize=(max(14, len(meses) * 0.9), 5))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, "Energía Producida por Mes (kWh) — Sistema Solar SMA",
             "Mes", "Energía (kWh)")

    bars = ax.bar(list(range(len(meses))), valores, color=colores,
                  edgecolor="#0a1220", linewidth=0.9, alpha=0.9, width=0.7)
    ax.axhline(mu, color=_C["amarillo"], linestyle="--", linewidth=1.8,
               label=f"Promedio: {mu:.1f} kWh/mes")

    for bar, v in zip(bars, valores):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + _maximo(valores) * 0.01,
                f"{v:.1f}", ha="center", va="bottom",
                color=_C["texto"], fontsize=6.5, family="monospace")

    ax.set_xticks(list(range(len(meses))))
    ax.set_xticklabels(etiquetas, color=_C["texto"], fontsize=6.5)
    ax.legend(facecolor=_C["fondo"], labelcolor=_C["texto"],
              fontsize=9, edgecolor="#1e3a5f")
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def graf_scatter_irr_pac(df: pd.DataFrame, eficiencia: dict) -> str:
    """Dispersión: irradiancia vs potencia total (solo horas solares)."""
    irr_vals, pac_vals = [], []
    for irr, pac in zip(df.get("irr", pd.Series()),
                        df.get("pac_total", pd.Series())):
        if (not _es_nan(irr) and not _es_nan(pac)
                and irr is not None and pac is not None):
            fi, fp = float(irr), float(pac)
            if fi > 10.0:
                irr_vals.append(fi)
                pac_vals.append(fp)

    if len(irr_vals) < 10:
        return ""

    # Muestrear para no saturar el gráfico (máx 3000 puntos)
    paso = max(1, len(irr_vals) // 3000)
    ix = irr_vals[::paso]
    py = pac_vals[::paso]

    fig, ax = plt.subplots(figsize=(9, 6))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax,
             f"Irradiancia vs Potencia AC — r = {eficiencia.get('r', float('nan')):.4f}",
             "Irradiancia Solar (W/m²)", "Potencia AC Total (W)")

    scatter_colors = [_C["naranja"] if p > 500 else _C["azul"] for p in py]
    ax.scatter(ix, py, c=scatter_colors, s=3, alpha=0.35)

    # Línea de tendencia lineal (ajuste manual)
    if len(ix) >= 2:
        mx_i = _media(ix)
        mx_p = _media(py)
        num = den = 0.0
        for xi, yi in zip(ix, py):
            d = xi - mx_i
            num += d * (yi - mx_p)
            den += d * d
        if den != 0:
            m_slope = num / den
            b_int   = mx_p - m_slope * mx_i
            x0 = _minimo(ix)
            x1 = _maximo(ix)
            ax.plot([x0, x1], [m_slope * x0 + b_int, m_slope * x1 + b_int],
                    color=_C["rojo"], linewidth=2.0, linestyle="--",
                    label=f"Regresión: y = {m_slope:.2f}x + {b_int:.0f}")

    r_val = eficiencia.get("r", float("nan"))
    ax.text(0.02, 0.96,
            f"r de Pearson = {r_val:+.4f}\n"
            f"R² = {eficiencia.get('r2', float('nan')):.4f}\n"
            f"N = {eficiencia.get('n', 0):,}",
            transform=ax.transAxes, color=_C["primario"],
            fontsize=9, va="top", family="monospace",
            bbox=dict(facecolor="#0a1a3a", alpha=0.7, edgecolor="#1e3a5f",
                      boxstyle="round,pad=0.4"))
    ax.legend(facecolor=_C["fondo"], labelcolor=_C["texto"],
              fontsize=8.5, edgecolor="#1e3a5f")
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def graf_potencia_inversores(df: pd.DataFrame) -> str:
    """Comparativa de potencia entre los 3 inversores (muestra reciente)."""
    cols = [c for c in ["pac1", "pac2", "pac3"] if c in df.columns]
    if not cols:
        return ""

    # Usar último mes de datos con producción
    df_sol = df[df["pac_total"] > 0].copy() if "pac_total" in df.columns else df.copy()
    if df_sol.empty:
        return ""

    # Tomar hasta 3000 filas del período más reciente con sol
    n = min(3000, len(df_sol))
    df_plot = df_sol.tail(n)

    fig, ax = plt.subplots(figsize=(13, 4))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, "Potencia por Inversor — Período Reciente (W)",
             "Tiempo", "Potencia (W)")

    colores_inv = [_C["naranja"], _C["cyan"], _C["verde"]]
    nombres_inv = ["Inversor 1 (S/N 893)", "Inversor 2 (S/N 894)", "Inversor 3 (S/N 917)"]

    x = list(range(n))
    for col, color, nombre in zip(cols, colores_inv, nombres_inv):
        vals = df_plot[col].tolist()
        ax.plot(x, vals, color=color, linewidth=0.7, alpha=0.8, label=nombre)

    paso = max(1, n // 6)
    ticks = list(range(0, n, paso))
    fechas = df_plot["datetime"].tolist()
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(fechas[i])[:16] for i in ticks if i < len(fechas)],
                       color=_C["texto"], fontsize=7, rotation=15)
    ax.legend(facecolor=_C["fondo"], labelcolor=_C["texto"],
              fontsize=8.5, edgecolor="#1e3a5f")
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def graf_temperatura_vs_pac(df: pd.DataFrame) -> str:
    """Temperatura módulo vs potencia — efecto térmico en rendimiento."""
    if "tmod" not in df.columns or "pac_total" not in df.columns:
        return ""

    tmod_v, pac_v = [], []
    for t, p in zip(df["tmod"].tolist(), df["pac_total"].tolist()):
        if (not _es_nan(t) and not _es_nan(p)
                and t is not None and p is not None):
            ft, fp = float(t), float(p)
            if fp > 100.0 and 10.0 < ft < 90.0:
                tmod_v.append(ft)
                pac_v.append(fp)

    if len(tmod_v) < 10:
        return ""

    paso = max(1, len(tmod_v) // 2000)
    tx = tmod_v[::paso]
    py = pac_v[::paso]

    r = _pearson(tmod_v, pac_v)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax,
             f"Temperatura Módulo vs Potencia AC (r = {r:.4f})",
             "Temperatura Módulo (°C)", "Potencia AC Total (W)")

    ax.scatter(tx, py, c=_C["rosa"], s=3, alpha=0.3)
    ax.text(0.02, 0.96, f"r = {r:+.4f}\nN = {len(tmod_v):,}",
            transform=ax.transAxes, color=_C["primario"],
            fontsize=9, va="top", family="monospace",
            bbox=dict(facecolor="#0a1a3a", alpha=0.7, edgecolor="#1e3a5f",
                      boxstyle="round,pad=0.4"))
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


# ═══════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════

def analizar_sistema_solar(verbose: bool = True) -> dict:
    """
    Pipeline completo del análisis SMA.
    Retorna dict con: df, stats, stats_mensuales, energia_diaria,
                       energia_mensual, eficiencia, figs.
    """
    print("\n" + "═" * 60)
    print("  FASE VI — SISTEMA SOLAR SMA + PIRANÓMETRO PYRA0102")
    print("═" * 60)

    # ── Carga ──────────────────────────────────────────────────────────
    print("\n[SMA] Cargando archivos CSV…")
    df = cargar_todos_sma(verbose=verbose)

    if df.empty:
        print("  [ERROR SMA] No se pudieron cargar datos.")
        return {}

    print(f"  Total: {len(df):,} registros "
          f"({df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]})")

    # ── Estadísticos ────────────────────────────────────────────────────
    print("\n[SMA] Calculando estadísticos…")
    stats = calcular_estadisticos_sma(df)
    for alias, st in stats.items():
        if alias in ("irr", "pac_total", "tamb", "energia_wh"):
            n = st.get("n", 0)
            mu = st.get("media", float("nan"))
            vmax = st.get("maximo", float("nan"))
            print(f"  {st['nombre']:<35} n={n:>8,}  "
                  f"x̄={mu:>8.2f}  máx={vmax:>8.2f}")

    # ── Estadísticos mensuales ──────────────────────────────────────────
    print("\n[SMA] Calculando estadísticos mensuales…")
    stats_men = calcular_stats_mensuales_sma(df)

    # ── Energía ────────────────────────────────────────────────────────
    print("\n[SMA] Calculando energía diaria y mensual…")
    energia_diaria   = calcular_energia_diaria(df)
    energia_mensual  = calcular_energia_mensual(energia_diaria)
    etotal_kwh       = sum(energia_mensual.values())
    print(f"  Energía total acumulada: {etotal_kwh:,.1f} kWh")

    # ── Eficiencia / Correlación ────────────────────────────────────────
    print("\n[SMA] Correlación irradiancia-potencia…")
    eficiencia = calcular_eficiencia(df)
    print(f"  r(irr, pac_total) = {eficiencia.get('r', float('nan')):.6f} "
          f"— {eficiencia.get('interpretacion','')}")

    # ── Gráficos ────────────────────────────────────────────────────────
    print("\n[SMA] Generando gráficos…")
    figs = {}

    figs["sma_serie_pac"] = graf_serie_sma(
        df, "pac_total",
        "Potencia AC Total — Sistema Solar SMA (W)",
        "Potencia (W)", _C["verde"], ventana=96)
    print("  → Serie temporal Pac total")

    figs["sma_serie_irr"] = graf_serie_sma(
        df, "irr",
        "Irradiancia Solar — PYRA0102 (W/m²)",
        "Irradiancia (W/m²)", _C["amarillo"], ventana=96)
    print("  → Serie temporal irradiancia")

    figs["sma_serie_tamb"] = graf_serie_sma(
        df, "tamb",
        "Temperatura Ambiente — PYRA0102 (°C)",
        "Temperatura (°C)", _C["naranja"], ventana=96)
    print("  → Serie temporal temperatura ambiente")

    # Histogramas
    for alias, color, lbl in [
        ("irr",       _C["amarillo"], "Irradiancia (W/m²)"),
        ("pac_total", _C["verde"],    "Potencia AC Total (W)"),
        ("tamb",      _C["naranja"],  "Temperatura Ambiente (°C)"),
        ("tmod",      _C["rosa"],     "Temperatura Módulo (°C)"),
    ]:
        if alias in df.columns:
            s = [float(v) for v in df[alias].tolist()
                 if not _es_nan(v) and v is not None]
            if s:
                figs[f"sma_hist_{alias}"] = graf_histograma_sma(
                    s, f"Histograma — {lbl}", lbl, color)
                print(f"  → Histograma {alias}")

    # Boxplot mensual
    for alias, titulo in [
        ("pac_total", "Boxplot Mensual — Potencia AC Total (W)"),
        ("irr",       "Boxplot Mensual — Irradiancia Solar (W/m²)"),
    ]:
        figs[f"sma_box_{alias}"] = graf_boxplot_mensual_sma(
            stats_men, alias, titulo)
        print(f"  → Boxplot mensual {alias}")

    # Energía mensual
    figs["sma_energia_mensual"] = graf_energia_mensual(energia_mensual)
    print("  → Barras energía mensual")

    # Scatter irr vs pac
    figs["sma_scatter_irr_pac"] = graf_scatter_irr_pac(df, eficiencia)
    print("  → Dispersión irradiancia-potencia")

    # Potencia por inversor
    figs["sma_inversores"] = graf_potencia_inversores(df)
    print("  → Comparativa inversores")

    # Temperatura módulo vs potencia
    figs["sma_tmod_pac"] = graf_temperatura_vs_pac(df)
    print("  → Temperatura módulo vs potencia")

    print("\n[SMA] ✓ Análisis completo.")

    return {
        "df":               df,
        "stats":            stats,
        "stats_mensuales":  stats_men,
        "energia_diaria":   energia_diaria,
        "energia_mensual":  energia_mensual,
        "eficiencia":       eficiencia,
        "etotal_kwh":       etotal_kwh,
        "figs":             figs,
    }


# ═══════════════════════════════════════════════════════════════════════
# GENERADOR DE SECCIÓN HTML PARA EL DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

def _fmt(st: dict, k: str, dec: int = 2) -> str:
    v = st.get(k)
    if v is None:
        return "—"
    try:
        fv = float(v)
        return "—" if fv != fv else f"{fv:.{dec}f}"
    except (TypeError, ValueError):
        return "—"


def generar_seccion_html_sma(resultado: dict) -> str:
    """
    Genera el bloque HTML de FASE VI para insertar en el dashboard principal.
    """
    if not resultado:
        return "<p style='color:#64748b'>Datos SMA no disponibles.</p>"

    stats        = resultado.get("stats", {})
    energia_men  = resultado.get("energia_mensual", {})
    eficiencia   = resultado.get("eficiencia", {})
    etotal_kwh   = resultado.get("etotal_kwh", 0.0)
    figs         = resultado.get("figs", {})

    def img(k, style="width:100%;border-radius:8px"):
        b = figs.get(k, "")
        if not b:
            return '<div style="color:#475569;padding:16px;text-align:center">Sin datos</div>'
        return f'<img src="data:image/png;base64,{b}" style="{style}" loading="lazy"/>'

    # Tabla de estadísticos clave
    STATS_MOSTRAR = [
        ("irr",       "☀️ Irradiancia (W/m²)"),
        ("tamb",      "🌡️ Temp. Ambiente (°C)"),
        ("tmod",      "🔋 Temp. Módulo (°C)"),
        ("hum",       "💧 Humedad (%)"),
        ("press",     "🧭 Presión (hPa)"),
        ("pac_total", "⚡ Potencia AC Total (W)"),
        ("pac1",      "⚡ Potencia Inv. 1 (W)"),
        ("pac2",      "⚡ Potencia Inv. 2 (W)"),
        ("pac3",      "⚡ Potencia Inv. 3 (W)"),
        ("vac1",      "🔌 Tensión AC (V)"),
        ("vpv1",      "🔌 Tensión PV (V)"),
        ("fac1",      "〰️ Frecuencia Red (Hz)"),
        ("tinv1",     "🌡️ Temp. Inv. 1 (°C)"),
        ("energia_wh","🏭 Energía/Intervalo (Wh)"),
    ]

    filas_stats = ""
    for alias, nombre in STATS_MOSTRAR:
        st = stats.get(alias, {})
        if not st:
            continue
        filas_stats += (
            f"<tr>"
            f"<td style='color:#94a3b8;font-size:.75rem'>{nombre}</td>"
            f"<td style='font-family:monospace;color:#e2e8f0'>{_fmt(st,'n',0)}</td>"
            f"<td style='font-family:monospace;color:#38bdf8'>{_fmt(st,'media')}</td>"
            f"<td style='font-family:monospace;color:#94a3b8'>{_fmt(st,'desv_estandar')}</td>"
            f"<td style='font-family:monospace;color:#f87171'>{_fmt(st,'maximo')}</td>"
            f"<td style='font-family:monospace;color:#4ade80'>{_fmt(st,'minimo')}</td>"
            f"<td style='font-family:monospace;color:#fbbf24'>{_fmt(st,'p50')}</td>"
            f"<td style='font-family:monospace;color:#a78bfa'>{_fmt(st,'iqr')}</td>"
            f"</tr>"
        )

    # Tabla energía mensual (compacta)
    meses_sorted = sorted(energia_men.keys())
    filas_energia = ""
    for mes in meses_sorted:
        kwh = energia_men[mes]
        bar_w = int(min(kwh / max(energia_men.values()) * 100, 100)) if energia_men else 0
        filas_energia += (
            f"<tr>"
            f"<td style='color:#94a3b8;font-size:.75rem'>{mes}</td>"
            f"<td style='font-family:monospace;color:#4ade80'>{kwh:.2f}</td>"
            f"<td style='width:120px'>"
            f"<div style='background:rgba(255,255,255,.06);border-radius:3px;height:7px'>"
            f"<div style='width:{bar_w}%;height:100%;background:#4ade80;border-radius:3px'></div>"
            f"</div></td>"
            f"</tr>"
        )

    r_val    = eficiencia.get("r", float("nan"))
    r_fmt    = f"{r_val:+.4f}" if not _es_nan(r_val) else "—"
    r_interp = eficiencia.get("interpretacion", "—")
    n_pairs  = eficiencia.get("n", 0)

    html = f"""
<!-- ══ FASE VI — SISTEMA SOLAR SMA ══════════════════════════════════ -->
<section style="margin-top:60px" id="sma">

<div style="display:flex;align-items:center;gap:12px;
            font-size:11px;font-weight:700;letter-spacing:2px;
            text-transform:uppercase;color:#64748b;margin:0 0 28px">
  <span style="height:1px;flex:1;background:linear-gradient(90deg,rgba(255,255,255,.10),transparent)"></span>
  ⚡ FASE VI — SISTEMA SOLAR SMA EIE · PIRANÓMETRO PYRA0102
  <span style="height:1px;flex:3;background:linear-gradient(90deg,rgba(255,255,255,.10),transparent)"></span>
</div>

<!-- KPIs SMA -->
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px">

  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:22px 20px;backdrop-filter:blur(18px)">
    <div style="font-size:9px;letter-spacing:2px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">⚡ Energía Total Acumulada</div>
    <div style="font-size:clamp(22px,2.5vw,32px);font-weight:700;
                color:#4ade80;text-shadow:0 0 20px rgba(74,222,128,.35)">
      {etotal_kwh:,.1f}<span style="font-size:14px;font-weight:400;color:#94a3b8;margin-left:4px">kWh</span>
    </div>
    <div style="font-size:12px;color:#64748b;margin-top:8px">
      {len(meses_sorted)} meses registrados
    </div>
  </div>

  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:22px 20px;backdrop-filter:blur(18px)">
    <div style="font-size:9px;letter-spacing:2px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">☀️ Irradiancia Media</div>
    <div style="font-size:clamp(22px,2.5vw,32px);font-weight:700;
                color:#fbbf24;text-shadow:0 0 20px rgba(251,191,36,.35)">
      {_fmt(stats.get('irr',{}),'media',0)}<span style="font-size:14px;font-weight:400;color:#94a3b8;margin-left:4px">W/m²</span>
    </div>
    <div style="font-size:12px;color:#64748b;margin-top:8px">
      Máx: {_fmt(stats.get('irr',{}),'maximo',0)} W/m²
    </div>
  </div>

  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:22px 20px;backdrop-filter:blur(18px)">
    <div style="font-size:9px;letter-spacing:2px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">⚡ Potencia AC Media</div>
    <div style="font-size:clamp(22px,2.5vw,32px);font-weight:700;
                color:#38bdf8;text-shadow:0 0 20px rgba(56,189,248,.35)">
      {_fmt(stats.get('pac_total',{}),'media',0)}<span style="font-size:14px;font-weight:400;color:#94a3b8;margin-left:4px">W</span>
    </div>
    <div style="font-size:12px;color:#64748b;margin-top:8px">
      Pico: {_fmt(stats.get('pac_total',{}),'maximo',0)} W
    </div>
  </div>

  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:22px 20px;backdrop-filter:blur(18px)">
    <div style="font-size:9px;letter-spacing:2px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">🔗 Corr. Irr-Pac</div>
    <div style="font-size:clamp(22px,2.5vw,32px);font-weight:700;
                color:#a78bfa;text-shadow:0 0 20px rgba(167,139,250,.35)">
      {r_fmt}
    </div>
    <div style="font-size:12px;color:#64748b;margin-top:8px">
      {r_interp} · N={n_pairs:,}
    </div>
  </div>

</div>

<!-- Series temporales -->
<div style="display:grid;grid-template-columns:1fr;gap:14px;margin-bottom:20px">
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    <div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">⚡ Potencia AC Total — Historia Completa</div>
    {img("sma_serie_pac")}
  </div>
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    <div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">☀️ Irradiancia Solar — Historia Completa</div>
    {img("sma_serie_irr")}
  </div>
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    <div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">🌡️ Temperatura Ambiente — Historia Completa</div>
    {img("sma_serie_tamb")}
  </div>
</div>

<!-- Energía mensual + scatter -->
<div style="display:grid;grid-template-columns:3fr 2fr;gap:14px;margin-bottom:20px">
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    <div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">🏭 Energía Producida por Mes (kWh)</div>
    {img("sma_energia_mensual")}
  </div>
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    <div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">🔗 Irradiancia vs Potencia (Pearson)</div>
    {img("sma_scatter_irr_pac")}
  </div>
</div>

<!-- Histogramas + Boxplots -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px">
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    {img("sma_hist_irr")}
  </div>
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    {img("sma_hist_pac_total")}
  </div>
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    {img("sma_hist_tamb")}
  </div>
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    {img("sma_hist_tmod")}
  </div>
</div>

<!-- Boxplots mensuales -->
<div style="display:grid;grid-template-columns:1fr;gap:14px;margin-bottom:20px">
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    {img("sma_box_pac_total")}
  </div>
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    {img("sma_box_irr")}
  </div>
</div>

<!-- Inversores + Efecto temperatura -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px">
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    <div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">⚡ Potencia por Inversor</div>
    {img("sma_inversores")}
  </div>
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:18px;backdrop-filter:blur(16px)">
    <div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:10px">🌡️ Efecto Térmico sobre Rendimiento</div>
    {img("sma_tmod_pac")}
  </div>
</div>

<!-- Tabla estadísticos -->
<div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
            border-radius:16px;padding:22px;backdrop-filter:blur(16px);margin-bottom:20px;
            overflow-x:auto">
  <div style="font-size:9px;letter-spacing:2px;text-transform:uppercase;
              color:#94a3b8;margin-bottom:16px">📐 Estadísticos Descriptivos — Todas las Variables SMA</div>
  <table style="width:100%;border-collapse:collapse;font-size:.76rem">
    <thead>
      <tr style="border-bottom:1px solid rgba(255,255,255,.10)">
        <th style="text-align:left;padding:7px 10px;color:#64748b;font-size:9px;letter-spacing:1px">Variable</th>
        <th style="padding:7px 10px;color:#64748b;font-size:9px">N</th>
        <th style="padding:7px 10px;color:#38bdf8;font-size:9px">x̄ Media</th>
        <th style="padding:7px 10px;color:#94a3b8;font-size:9px">σ</th>
        <th style="padding:7px 10px;color:#f87171;font-size:9px">Máx</th>
        <th style="padding:7px 10px;color:#4ade80;font-size:9px">Mín</th>
        <th style="padding:7px 10px;color:#fbbf24;font-size:9px">P50</th>
        <th style="padding:7px 10px;color:#a78bfa;font-size:9px">IQR</th>
      </tr>
    </thead>
    <tbody>{filas_stats}</tbody>
  </table>
</div>

<!-- Tabla energía mensual -->
<div style="display:grid;grid-template-columns:1fr 2fr;gap:14px;margin-bottom:20px">
  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:22px;backdrop-filter:blur(16px);overflow-y:auto;max-height:480px">
    <div style="font-size:9px;letter-spacing:2px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:16px">🏭 Energía Mensual (kWh)</div>
    <table style="width:100%;border-collapse:collapse;font-size:.76rem">
      <thead>
        <tr style="border-bottom:1px solid rgba(255,255,255,.08)">
          <th style="text-align:left;padding:5px 8px;color:#64748b;font-size:9px">Mes</th>
          <th style="padding:5px 8px;color:#4ade80;font-size:9px">kWh</th>
          <th style="padding:5px 8px;color:#64748b;font-size:9px">Bar</th>
        </tr>
      </thead>
      <tbody>{filas_energia}</tbody>
      <tfoot>
        <tr style="border-top:1px solid rgba(255,255,255,.10)">
          <td style="padding:6px 8px;color:#94a3b8;font-size:.72rem">TOTAL</td>
          <td style="padding:6px 8px;font-family:monospace;color:#4ade80;font-weight:700">
            {etotal_kwh:,.1f}
          </td>
          <td></td>
        </tr>
      </tfoot>
    </table>
  </div>

  <div style="background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10);
              border-radius:16px;padding:22px;backdrop-filter:blur(16px)">
    <div style="font-size:9px;letter-spacing:2px;text-transform:uppercase;
                color:#94a3b8;margin-bottom:16px">ℹ️ Descripción del Sistema</div>
    <div style="font-size:.82rem;color:#94a3b8;line-height:1.9">
      <b style="color:#e2e8f0">Piranómetro PYRA0102</b><br>
      S/N 158511170 · Mide irradiancia solar, presión y temperatura ambiente.<br><br>
      <b style="color:#e2e8f0">Inversor SMA WR725UAE #1</b> · S/N 2000801893<br>
      <b style="color:#e2e8f0">Inversor SMA WR725UAE #2</b> · S/N 2000801894<br>
      <b style="color:#e2e8f0">Inversor SMA WR725UAE #3</b> · S/N 2000801917<br><br>
      <span style="color:#fbbf24">Correlación Irr-Pac:</span>
      r = {r_fmt} ({r_interp}) — Indica el grado de acoplamiento entre
      la radiación recibida y la energía convertida por los inversores.<br><br>
      <span style="color:#4ade80">Energía acumulada total:</span>
      {etotal_kwh:,.1f} kWh desde el inicio del registro.
    </div>
  </div>
</div>

</section>
<!-- FIN FASE VI ══════════════════════════════════════════════════════ -->
"""
    return html


# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD CANVAS INTERACTIVO — PLANTA SOLAR SMA
# ═══════════════════════════════════════════════════════════════════════

def _construir_json_solar(df) -> dict:
    """Construye el JSON de datos diarios + sub-horarios para el dashboard Canvas."""
    dias_json: dict = {}
    energia_diaria_kwh: dict = {}

    if df is None or df.empty:
        return {"dias": {}, "energia_mensual": {}}

    df2 = df.copy()
    df2["_fecha"] = df2["datetime"].dt.strftime("%Y-%m-%d")

    def _sv(v):
        try:
            return None if (v is None or v != v) else round(float(v), 2)
        except (TypeError, ValueError):
            return None

    def _col_or_none(grp, col):
        return grp[col].tolist() if col in grp.columns else [None] * len(grp)

    for fecha, grp in df2.groupby("_fecha", sort=True):
        grp = grp.sort_values("datetime")
        ts_list   = [dt.strftime("%H:%M") for dt in grp["datetime"]]
        pac_list  = [_sv(v) for v in _col_or_none(grp, "pac_total")]
        irr_list  = [_sv(v) for v in _col_or_none(grp, "irr")]
        tamb_list = [_sv(v) for v in _col_or_none(grp, "tamb")]
        tmod_list = [_sv(v) for v in _col_or_none(grp, "tmod")]

        # Daily aggregates
        pac_vals  = [v for v in pac_list  if v is not None and v >= 0]
        irr_vals  = [v for v in irr_list  if v is not None and v >= 0]
        tamb_vals = [v for v in tamb_list if v is not None]
        tmod_vals = [v for v in tmod_list if v is not None]

        kwh = 0.0
        if "energia_wh" in grp.columns:
            for v in grp["energia_wh"].tolist():
                if v is not None and not (v != v):
                    try:
                        kwh += float(v)
                    except (TypeError, ValueError):
                        pass
        kwh_day = round(kwh / 1000.0, 3)
        energia_diaria_kwh[fecha] = kwh_day

        irr_wh_sum = 0.0
        if "irr_wh" in grp.columns:
            for v in grp["irr_wh"].tolist():
                if v is not None and not (v != v):
                    try:
                        irr_wh_sum += float(v)
                    except (TypeError, ValueError):
                        pass
        irr_kwh_day = round(irr_wh_sum / 1000.0, 3)

        dias_json[fecha] = {
            "kwh":      kwh_day,
            "pac_max":  round(_maximo(pac_vals),  2) if pac_vals  else 0,
            "irr_max":  round(_maximo(irr_vals),  2) if irr_vals  else 0,
            "irr_kwh":  irr_kwh_day,
            "tamb_avg": round(_media(tamb_vals),   2) if tamb_vals else None,
            "tmod_avg": round(_media(tmod_vals),   2) if tmod_vals else None,
            "horas": {
                "t":    ts_list,
                "pac":  pac_list,
                "irr":  irr_list,
                "tamb": tamb_list,
                "tmod": tmod_list,
            },
        }

    # Energia mensual
    energia_mensual: dict = {}
    for fecha, kwh in energia_diaria_kwh.items():
        mes = fecha[:7]
        energia_mensual[mes] = round(energia_mensual.get(mes, 0.0) + kwh, 3)

    return {
        "dias":             dias_json,
        "energia_mensual":  energia_mensual,
    }


def generar_dashboard_solar_canvas(resultado: dict,
                                   nombre: str = "dashboard_solar.html") -> str:
    """
    Genera un dashboard HTML interactivo basado en Canvas/uPlot para la planta solar.
    Incluye calendario de días, gráficas dinámicas, estadísticos y comparativa.
    """
    if not resultado:
        return nombre

    df           = resultado.get("df")
    stats        = resultado.get("stats", {})
    stats_men    = resultado.get("stats_mensuales", {})
    eficiencia   = resultado.get("eficiencia", {})
    etotal_kwh   = resultado.get("etotal_kwh", 0.0)
    energia_men  = resultado.get("energia_mensual", {})

    solar_data   = _construir_json_solar(df)
    solar_json   = json.dumps(solar_data, ensure_ascii=False, separators=(",", ":"))

    # Stats globales clave para la cabecera
    st_pac = stats.get("pac_total", {})
    st_irr = stats.get("irr",       {})
    r_val  = eficiencia.get("r", float("nan"))
    r_fmt  = f"{r_val:.4f}" if r_val == r_val else "N/D"

    # Pre-serialize stats for JS embedding (NaN → 0)
    def _jv(v):
        try:
            fv = float(v)
            return 0.0 if fv != fv else round(fv, 2)
        except (TypeError, ValueError):
            return 0.0

    _stats_js = {}
    for k, st in stats.items():
        med = st.get("media", 0)
        if isinstance(med, float) and med != med:
            continue
        _stats_js[k] = {
            "media":  _jv(st.get("media", 0)),
            "desv":   _jv(st.get("desv_estandar", 0)),
            "maximo": _jv(st.get("maximo", 0)),
            "minimo": _jv(st.get("minimo", 0)),
            "p50":    _jv(st.get("p50", 0)),
            "n":      int(st.get("n", 0)),
        }
    stats_json = json.dumps(_stats_js, ensure_ascii=False, separators=(",", ":"))

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard Solar SMA — Planta Fotovoltaica EIE · Universidad de El Salvador</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="uPlot.min.css">
<script src="chart.umd.min.js"></script>
<script src="uPlot.iife.min.js"></script>
<style>
:root{{
  --bg:#050f2e;--card:rgba(255,255,255,.055);--brd:rgba(255,255,255,.09);
  --brd2:rgba(255,255,255,.05);--tx:#e2e8f0;--tx2:#94a3b8;--tx3:#64748b;
  --blue:#38bdf8;--warm:#f59e0b;--green:#10b981;--red:#ef4444;
  --yellow:#fbbf24;--purple:#a78bfa;
  --r:'Inter',system-ui,sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx);font-family:var(--r);min-height:100vh;overflow-x:hidden}}

/* ── Fondo animado ── */
body::before{{
  content:'';position:fixed;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(ellipse 900px 600px at 10% 20%, rgba(251,191,36,.07) 0%, transparent 70%),
    radial-gradient(ellipse 700px 500px at 90% 80%, rgba(16,185,129,.06) 0%, transparent 65%),
    radial-gradient(ellipse 500px 400px at 50% 50%, rgba(56,189,248,.04) 0%, transparent 70%);
  animation: bgPulse 12s ease-in-out infinite alternate;
}}
@keyframes bgPulse{{
  0%  {{opacity:.6}}
  100%{{opacity:1}}
}}

/* ── Layout ── */
.navbar{{position:sticky;top:0;z-index:100;background:rgba(5,15,46,.93);
  backdrop-filter:blur(20px);border-bottom:1px solid var(--brd);
  padding:10px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.nav-title{{font-size:.8rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  color:var(--yellow);white-space:nowrap}}
.nav-sep{{width:1px;height:22px;background:var(--brd);margin:0 4px;align-self:center}}
.period-bar{{display:flex;gap:6px;align-items:center}}
.btn-period{{padding:5px 12px;border-radius:8px;border:1px solid var(--brd);
  background:transparent;color:var(--tx2);font-family:var(--r);font-size:.75rem;cursor:pointer;transition:.2s}}
.btn-period:hover{{background:rgba(255,255,255,.06)}}
.btn-period.active{{background:rgba(251,191,36,.15);border-color:var(--yellow);color:var(--yellow)}}
.btn-comparar-active{{border-color:rgba(248,113,113,.6)!important;
  background:rgba(248,113,113,.15)!important;color:#f87171!important}}
.nav-period-label{{font-size:.66rem;color:var(--tx3);white-space:nowrap;
  padding:4px 10px;border-radius:6px;background:rgba(255,255,255,.04);border:1px solid var(--brd2)}}
.nav-links{{display:flex;gap:6px;margin-left:auto}}
.nav-link{{padding:4px 11px;border-radius:7px;border:1px solid var(--brd);
  background:rgba(255,255,255,.03);color:var(--tx2);font-size:.7rem;text-decoration:none;
  transition:.2s;white-space:nowrap}}
.nav-link:hover{{background:rgba(255,255,255,.08);color:var(--tx);border-color:rgba(255,255,255,.2)}}
.nav-link.home{{color:var(--blue);border-color:rgba(56,189,248,.3)}}
.nav-cal-input{{background:rgba(255,255,255,.05);border:1px solid var(--brd);border-radius:7px;
  color:var(--tx);font-family:var(--r);font-size:.72rem;padding:4px 8px;cursor:pointer;
  color-scheme:dark;white-space:nowrap}}
.nav-cal-input:hover{{border-color:var(--yellow)}}
.nav-link.home:hover{{background:rgba(56,189,248,.1)}}

/* ── Hero header ── */
.hero-solar{{
  position:relative;z-index:1;
  background:linear-gradient(135deg,rgba(251,191,36,.10) 0%,rgba(16,185,129,.07) 50%,rgba(5,15,46,0) 100%);
  border-bottom:1px solid rgba(251,191,36,.12);
  padding:40px 32px 36px;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:24px;
}}
.hero-solar::after{{
  content:'';position:absolute;bottom:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(251,191,36,.3),rgba(16,185,129,.2),transparent);
}}
.hero-left{{display:flex;flex-direction:column;gap:6px}}
.hero-badge{{display:inline-flex;align-items:center;gap:6px;
  background:rgba(251,191,36,.12);border:1px solid rgba(251,191,36,.25);
  border-radius:20px;padding:4px 12px;font-size:.68rem;color:var(--yellow);
  font-weight:600;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px}}
.hero-badge::before{{content:'';width:7px;height:7px;border-radius:50%;
  background:var(--yellow);box-shadow:0 0 8px var(--yellow);animation:blink 2s ease-in-out infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.hero-title{{font-size:clamp(1.4rem,3vw,2.2rem);font-weight:800;
  background:linear-gradient(135deg,#fbbf24,#10b981 60%,#38bdf8);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  line-height:1.15}}
.hero-sub{{font-size:.85rem;color:var(--tx2);margin-top:2px}}
.hero-loc{{font-size:.75rem;color:var(--tx3);display:flex;align-items:center;gap:5px;margin-top:4px}}
.hero-right{{display:flex;flex-direction:column;gap:10px;align-items:flex-end}}
.hero-stat{{text-align:right}}
.hero-stat-val{{font-size:2.2rem;font-weight:800;color:var(--yellow);
  font-variant-numeric:tabular-nums;line-height:1;text-shadow:0 0 24px rgba(251,191,36,.4)}}
.hero-stat-lbl{{font-size:.65rem;color:var(--tx3);letter-spacing:1.5px;text-transform:uppercase;margin-top:2px}}
.hero-badges{{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}}
.sys-badge{{padding:4px 10px;border-radius:6px;font-size:.68rem;font-weight:600;
  border:1px solid;white-space:nowrap}}

/* ── Main container ── */
.main{{max-width:1380px;margin:0 auto;padding:24px 20px 80px;position:relative;z-index:1}}

/* ── Section headers ── */
.sec-divider{{display:flex;align-items:center;gap:14px;margin:32px 0 18px;
  font-size:.68rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--tx3)}}
.sec-divider::before,.sec-divider::after{{content:'';flex:1;height:1px;
  background:linear-gradient(90deg,rgba(255,255,255,.08),transparent)}}
.sec-divider::before{{background:linear-gradient(90deg,transparent,rgba(255,255,255,.08))}}

/* ── KPI cards ── */
.kpi-row{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:24px}}
.kpi{{background:var(--card);border:1px solid var(--brd);border-radius:16px;
  padding:20px 24px;flex:1;min-width:150px;position:relative;overflow:hidden;transition:.2s}}
.kpi::after{{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:16px 16px 0 0}}
.kpi.yellow::after{{background:linear-gradient(90deg,var(--yellow),transparent)}}
.kpi.blue::after  {{background:linear-gradient(90deg,var(--blue),transparent)}}
.kpi.green::after {{background:linear-gradient(90deg,var(--green),transparent)}}
.kpi.purple::after{{background:linear-gradient(90deg,var(--purple),transparent)}}
.kpi:hover{{transform:translateY(-2px);border-color:rgba(255,255,255,.15)}}
.kpi-val{{font-size:1.7rem;font-weight:800;font-variant-numeric:tabular-nums;line-height:1.1}}
.kpi-sub{{font-size:.75rem;color:var(--tx2);margin-top:4px}}
.kpi-lbl{{font-size:.62rem;letter-spacing:1.5px;text-transform:uppercase;color:var(--tx3);margin-top:6px}}

/* ── Calendar ── */
.cal-section{{margin-bottom:20px}}
.cal-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px}}
.cal-label{{font-size:.68rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--tx2)}}
.cal-nav button{{background:none;border:1px solid var(--brd);color:var(--tx2);
  border-radius:6px;padding:3px 10px;cursor:pointer;font-size:.85rem;transition:.2s}}
.cal-nav button:hover{{background:rgba(255,255,255,.06);color:var(--tx)}}
#cal-month-label{{font-size:.9rem;color:var(--tx);font-weight:600;min-width:140px;text-align:center}}
.cal-scroll{{display:flex;gap:6px;overflow-x:auto;padding-bottom:8px;
  scrollbar-width:thin;scrollbar-color:var(--brd) transparent}}
.cal-day{{display:flex;flex-direction:column;align-items:center;min-width:76px;
  padding:10px 6px;border-radius:12px;border:1px solid transparent;
  background:rgba(255,255,255,.04);cursor:pointer;transition:.2s}}
.cal-day:hover{{background:rgba(251,191,36,.08);border-color:rgba(251,191,36,.2)}}
.cal-day.active{{background:rgba(251,191,36,.15);border-color:rgba(251,191,36,.5);
  box-shadow:0 0 16px rgba(251,191,36,.15)}}
.cal-day.no-data{{opacity:.3;cursor:not-allowed;pointer-events:none}}
.cal-dname{{font-size:.6rem;color:var(--tx3);margin-bottom:2px;font-weight:500;pointer-events:none}}
.cal-dnum{{font-size:1rem;font-weight:700;pointer-events:none}}
.cal-kwh{{font-size:.72rem;font-weight:700;color:var(--yellow);margin-top:4px;pointer-events:none}}
.cal-bar{{width:44px;height:4px;border-radius:2px;background:rgba(251,191,36,.15);
  margin-top:5px;overflow:hidden;pointer-events:none}}
.cal-bar-fill{{height:100%;border-radius:2px;background:linear-gradient(90deg,#f59e0b,#10b981);transition:.4s;pointer-events:none}}

/* ── uPlot cards ── */
.uplot-card{{overflow:hidden}}
.uplot-card{{background:var(--card);border:1px solid var(--brd);border-radius:18px;
  padding:20px 22px;margin-bottom:16px;transition:.2s}}
.uplot-card:hover{{border-color:rgba(255,255,255,.14)}}
.uplot-title{{font-size:.7rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
  color:var(--tx2);margin-bottom:16px;display:flex;align-items:center;justify-content:space-between}}
.zoom-controls{{display:flex;gap:6px}}
.zoom-btn{{background:none;border:1px solid var(--brd);color:var(--tx2);
  border-radius:6px;padding:2px 9px;cursor:pointer;font-size:.85rem;transition:.2s}}
.zoom-btn:hover{{background:rgba(255,255,255,.07);color:var(--tx)}}

/* ── System info banner ── */
.sys-info{{background:linear-gradient(135deg,rgba(251,191,36,.07),rgba(16,185,129,.05));
  border:1px solid rgba(251,191,36,.18);border-radius:16px;padding:22px 26px;margin-bottom:24px;
  display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:18px}}
.si-item{{display:flex;flex-direction:column;gap:4px}}
.si-label{{font-size:.62rem;color:var(--tx3);letter-spacing:1.5px;text-transform:uppercase;font-weight:700}}
.si-val{{font-size:.88rem;color:var(--tx);font-weight:500}}
.si-sub{{font-size:.72rem;color:var(--tx3)}}

/* ── Comparison panel ── */
.comp-panel{{display:none;margin-bottom:20px;background:rgba(255,255,255,.03);
  border:1px solid var(--brd);border-radius:14px;padding:18px 20px}}
.comp-panel.visible{{display:block}}
.comp-row{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:14px;align-items:flex-end}}
.comp-group{{display:flex;flex-direction:column;gap:6px;flex:1;min-width:180px}}
.comp-group label{{font-size:.65rem;font-weight:600;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--tx3)}}
.date-inp{{background:rgba(255,255,255,.06);border:1px solid var(--brd);border-radius:8px;
  color:var(--tx);font-family:var(--r);font-size:.78rem;padding:6px 10px;
  outline:none;cursor:pointer;transition:.2s;width:100%}}
.date-inp:focus{{border-color:var(--yellow);background:rgba(251,191,36,.07)}}
.comp-badge-a{{color:#f87171}}.comp-badge-b{{color:#34d399}}
.btn-run-comp{{padding:7px 18px;border-radius:8px;
  background:linear-gradient(135deg,rgba(248,113,113,.25),rgba(52,211,153,.25));
  color:var(--tx);font-family:var(--r);font-size:.78rem;cursor:pointer;
  border:1px solid rgba(248,113,113,.3);transition:.2s;white-space:nowrap}}
.btn-run-comp:hover{{background:linear-gradient(135deg,rgba(248,113,113,.4),rgba(52,211,153,.4))}}
.comp-result{{margin-top:16px}}
.comp-result-title{{font-size:.7rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  color:var(--tx2);margin-bottom:12px}}
.comp-table-wrap{{overflow-x:auto}}
.comp-table{{width:100%;border-collapse:collapse;font-size:.75rem}}
.comp-table th,.comp-table td{{padding:7px 12px;text-align:center;border-bottom:1px solid var(--brd2)}}
.comp-table th{{color:var(--tx3);font-weight:600;font-size:.65rem;letter-spacing:1px;text-transform:uppercase}}
.comp-table td.var-name{{text-align:left;font-weight:600;color:var(--tx2)}}
.comp-diff-pos{{color:#34d399}}.comp-diff-neg{{color:#f87171}}
.comp-mini-charts{{display:flex;flex-wrap:wrap;gap:14px;margin-top:16px}}
.comp-mini-card{{background:rgba(255,255,255,.04);border:1px solid var(--brd);
  border-radius:10px;padding:12px;flex:1;min-width:200px}}
.comp-mini-label{{font-size:.65rem;color:var(--tx3);margin-bottom:6px;font-weight:600}}
.comp-interp{{margin-top:16px;background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.15);
  border-radius:10px;padding:14px 16px;font-size:.78rem;color:var(--tx2);line-height:1.6}}
.comp-interp strong{{color:var(--tx)}}

/* ── Stats grid ── */
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-bottom:24px}}
.stat-card{{background:var(--card);border:1px solid var(--brd);border-radius:12px;padding:14px 18px;transition:.2s}}
.stat-card:hover{{border-color:rgba(251,191,36,.2)}}
.stat-name{{font-size:.65rem;color:var(--tx3);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}}
.stat-row{{display:flex;justify-content:space-between;font-size:.75rem;margin-bottom:3px}}
.stat-key{{color:var(--tx3)}}.stat-val{{font-weight:600;font-variant-numeric:tabular-nums}}

/* ── Footer ── */
.site-footer{{
  position:relative;z-index:1;margin-top:60px;
  border-top:1px solid var(--brd);
  padding:28px 32px;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;
  background:rgba(0,0,0,.2);
}}
.footer-links{{display:flex;gap:14px;flex-wrap:wrap}}
.footer-link{{color:var(--tx3);font-size:.75rem;text-decoration:none;transition:.2s}}
.footer-link:hover{{color:var(--tx)}}
.footer-copy{{font-size:.72rem;color:var(--tx3);text-align:right}}
</style>
</head>
<body>

<!-- ── NAVBAR ── -->
<div class="navbar">
  <span class="nav-title">☀️ SMA Solar EIE</span>
  <div class="nav-sep"></div>
  <div class="period-bar">
    <button class="btn-period active" id="p-dia"  onclick="setPeriodo('dia')">Día</button>
    <button class="btn-period"        id="p-mes"  onclick="setPeriodo('mes')">Mes</button>
    <button class="btn-period"        id="p-anio" onclick="setPeriodo('anio')">Año</button>
    <button class="btn-period"        id="p-todo" onclick="setPeriodo('todo')">Todo</button>
  </div>
  <button class="btn-period" id="btn-comparar" onclick="toggleComparacion()" title="Comparar dos rangos">📊 Comparar</button>
  <div class="nav-sep"></div>
  <input type="date" class="nav-cal-input" id="nav-cal-input"
         onchange="irAFecha(this.value)" title="Ir a una fecha específica">
  <div class="nav-links">
    <a class="nav-link home" href="index.html">🏠 Inicio</a>
    <a class="nav-link" href="dashboard_msn_interactivo.html">🌤 Clima</a>
    <a class="nav-link" href="dashboard_fusion.html">🔗 Fusión</a>
  </div>
  <span class="nav-period-label" id="nav-label">—</span>
</div>

<!-- ── HERO HEADER ── -->
<div class="hero-solar">
  <div class="hero-left">
    <div class="hero-badge">Sistema activo · EIE</div>
    <div class="hero-title">Sistema Solar Fotovoltaico SMA</div>
    <div class="hero-sub">Análisis de producción energética 2023 – 2026</div>
    <div class="hero-loc">📍 Escuela de Ingeniería Eléctrica (EIE) · Universidad de El Salvador, San Salvador</div>
    <div class="hero-badges" style="margin-top:14px">
      <span class="sys-badge" style="background:rgba(251,191,36,.1);border-color:rgba(251,191,36,.25);color:var(--yellow)">
        ☀️ Piranómetro PYRA0102
      </span>
      <span class="sys-badge" style="background:rgba(16,185,129,.1);border-color:rgba(16,185,129,.25);color:var(--green)">
        ⚡ 3 × SMA WR725UAE
      </span>
      <span class="sys-badge" style="background:rgba(56,189,248,.1);border-color:rgba(56,189,248,.25);color:var(--blue)">
        📐 Métodos Numéricos · C++
      </span>
    </div>
  </div>
  <div class="hero-right">
    <div class="hero-stat">
      <div class="hero-stat-val">{etotal_kwh:,.0f}</div>
      <div class="hero-stat-lbl" style="color:var(--yellow)">kWh acumulados</div>
    </div>
    <div class="hero-stat" style="margin-top:10px">
      <div style="font-size:1.3rem;font-weight:700;color:var(--green)">{r_fmt}</div>
      <div style="font-size:.6rem;color:var(--tx3);letter-spacing:1px;text-transform:uppercase;margin-top:2px">correlación irr–pac</div>
    </div>
  </div>
</div>

<!-- ── SISTEMA INFO ── -->
<div class="sys-info">
  <div class="si-item">
    <div class="si-label">Piranómetro</div>
    <div class="si-val">PYRA0102 · S/N 158511170</div>
    <div class="si-sub">Irradiancia · Temperatura · Presión</div>
  </div>
  <div class="si-item">
    <div class="si-label">Inversor 1</div>
    <div class="si-val">SMA WR725UAE</div>
    <div class="si-sub">S/N 2000801893</div>
  </div>
  <div class="si-item">
    <div class="si-label">Inversor 2</div>
    <div class="si-val">SMA WR725UAE</div>
    <div class="si-sub">S/N 2000801894</div>
  </div>
  <div class="si-item">
    <div class="si-label">Inversor 3</div>
    <div class="si-val">SMA WR725UAE</div>
    <div class="si-sub">S/N 2000801917</div>
  </div>
  <div class="si-item">
    <div class="si-label">Período registrado</div>
    <div class="si-val">2023 – 2026</div>
    <div class="si-sub">{len(energia_men)} meses de datos</div>
  </div>
</div>

<!-- ── CONTENIDO PRINCIPAL ── -->
<div class="main">

<!-- KPIs -->
<div class="sec-divider">⚡ Indicadores Clave</div>
<div class="kpi-row">
  <div class="kpi yellow">
    <div class="kpi-val" style="color:var(--yellow)">{etotal_kwh:,.1f}</div>
    <div class="kpi-sub" style="color:var(--tx3)">kWh</div>
    <div class="kpi-lbl">Energía total acumulada</div>
  </div>
  <div class="kpi blue">
    <div class="kpi-val" style="color:var(--blue)">{_fmt(st_pac,'media',0)}</div>
    <div class="kpi-sub" style="color:var(--tx3)">W</div>
    <div class="kpi-lbl">Potencia AC media</div>
  </div>
  <div class="kpi" style="--accent:var(--warm)">
    <div class="kpi-val" style="color:var(--warm)">{_fmt(st_irr,'media',1)}</div>
    <div class="kpi-sub" style="color:var(--tx3)">W/m²</div>
    <div class="kpi-lbl">Irradiancia media</div>
  </div>
  <div class="kpi green">
    <div class="kpi-val" style="color:var(--green)">{r_fmt}</div>
    <div class="kpi-sub" style="color:var(--tx3)">r Pearson</div>
    <div class="kpi-lbl">Correlación Irr–Pac</div>
  </div>
</div>

<!-- ══ CALENDARIO ══ -->
<div class="cal-section" id="cal-section">
  <div class="cal-header">
    <span class="cal-label">📅 Selecciona un día</span>
    <div class="cal-nav" style="display:flex;align-items:center;gap:8px">
      <button onclick="calNav(-1)">‹</button>
      <span id="cal-month-label">—</span>
      <button onclick="calNav(1)">›</button>
    </div>
  </div>
  <div class="cal-scroll" id="cal-scroll"></div>
</div>

<!-- ══ PANEL COMPARATIVA ══ -->
<div class="comp-panel" id="comp-panel">
  <div class="comp-row">
    <div class="comp-group">
      <label><span class="comp-badge-a">▶ Rango A</span></label>
      <input type="date" class="date-inp" id="comp-a-desde">
      <input type="date" class="date-inp" id="comp-a-hasta">
    </div>
    <div class="comp-group">
      <label><span class="comp-badge-b">▶ Rango B</span></label>
      <input type="date" class="date-inp" id="comp-b-desde">
      <input type="date" class="date-inp" id="comp-b-hasta">
    </div>
    <button class="btn-run-comp" onclick="renderComparacion()">Comparar rangos</button>
  </div>
  <div id="comp-result"></div>
</div>

<!-- ══ GRÁFICO PAC + IRRADIANCIA ══ -->
<div class="uplot-card">
  <div class="uplot-title">
    <span id="chart-pac-title">Potencia AC Total + Irradiancia</span>
    <div class="zoom-controls">
      <button class="zoom-btn" onclick="uZoom('pac',-1)">＋</button>
      <button class="zoom-btn" onclick="uZoom('pac',1)">－</button>
      <button class="zoom-btn" onclick="uZoomReset('pac')">⟳</button>
    </div>
  </div>
  <div id="uplot-pac"></div>
</div>

<!-- ══ GRÁFICO TEMPERATURAS ══ -->
<div class="uplot-card">
  <div class="uplot-title">
    <span id="chart-temp-title">Temperatura Ambiente y Módulo</span>
    <div class="zoom-controls">
      <button class="zoom-btn" onclick="uZoom('temp',-1)">＋</button>
      <button class="zoom-btn" onclick="uZoom('temp',1)">－</button>
      <button class="zoom-btn" onclick="uZoomReset('temp')">⟳</button>
    </div>
  </div>
  <div id="uplot-temp"></div>
</div>

<!-- ══ ESTADÍSTICOS GLOBALES ══ -->
<div class="sec-divider">📊 Estadísticos globales del sistema</div>
<div class="stats-grid" id="stats-grid"></div>

</div><!-- /main -->

<!-- ── FOOTER ── -->
<footer class="site-footer">
  <div class="footer-links">
    <a class="footer-link" href="index.html">🏠 Inicio</a>
    <a class="footer-link" href="dashboard_msn_interactivo.html">🌤 Dashboard Climático</a>
    <a class="footer-link" href="dashboard_fusion.html">🔗 Fusión RadSolar–Potencia</a>
  </div>
  <div class="footer-copy">
    Sistema Solar SMA EIE · Universidad de El Salvador<br>
    Análisis generado con Python · C++ (Newton-Raphson · QuickSort · Pearson)<br>
    Datos 2023–2026 · {len(energia_men)} meses registrados
  </div>
  <div style="margin-top:10px;font-size:.66rem;line-height:1.9;color:#6b7280">
    ANÁLISIS CLIMÁTICO Y FOTOVOLTAICO — CICLO I-2026 · AEL115 · UES-FIA<br>
    MAURICIO A. MUÑOZ CONTRERAS <code>MC24021</code> &nbsp;·&nbsp;
    MARCELO X. MOLINA GOMEZ <code>MG24048</code> &nbsp;·&nbsp;
    DIEGO J. MENDOZA PRUDENCIO <code>MP24048</code> &nbsp;·&nbsp;
    FERNANDO J. PADILLA CRUZ <code>PC24039</code> &nbsp;·&nbsp;
    OSCAR M. VELASQUEZ VILLANUEVA <code>VV24002</code>
  </div>
  <div style="margin-top:4px;font-size:.62rem;color:#4b5563">
    © 2026 · Universidad de El Salvador, Facultad de Ingeniería y Arquitectura
  </div>
</footer>

<script>
// ── Datos embebidos ──────────────────────────────────────────────────
const SOLAR = {solar_json};

// ── Estado ──
let periodo   = 'dia';
let diaActivo = null;
let calMes    = null;
let uPac      = null;
let uTemp     = null;
let modoComp  = false;

// ── Helpers ──────────────────────────────────────────────────────────
function fechasDias(){{ return Object.keys(SOLAR.dias).sort(); }}

function diasDelMes(anio, mes){{
  return fechasDias().filter(d => d.startsWith(String(anio).padStart(4,'0')+'-'+String(mes).padStart(2,'0')));
}}

function kwhMaxDia(){{
  let mx = 0;
  fechasDias().forEach(d => {{ if(SOLAR.dias[d].kwh > mx) mx = SOLAR.dias[d].kwh; }});
  return mx || 1;
}}

function fmtFecha(d){{
  const [y,m,dd] = d.split('-');
  const ms = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
  return `${{dd}} ${{ms[+m-1]}} ${{y}}`;
}}

function semNombre(ts){{
  const dias = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
  return dias[new Date(ts+'T12:00:00').getDay()];
}}

// ── Calendario ───────────────────────────────────────────────────────
function renderCalendario(){{
  const scroll = document.getElementById('cal-scroll');
  if(!scroll) return;
  scroll.innerHTML = '';
  const dias = fechasDias();
  if(!dias.length) return;

  let anio, mes;
  if(calMes){{ [anio, mes] = calMes.split('-').map(Number); }}
  else {{
    const ultimo = dias[dias.length-1];
    anio = +ultimo.split('-')[0]; mes = +ultimo.split('-')[1];
    calMes = `${{anio}}-${{String(mes).padStart(2,'0')}}`;
  }}

  document.getElementById('cal-month-label').textContent =
    ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto',
     'Septiembre','Octubre','Noviembre','Diciembre'][mes-1] + ' ' + anio;

  const diasMes = diasDelMes(anio, mes);
  const maxKwh  = kwhMaxDia();

  diasMes.forEach(fecha => {{
    const obj = SOLAR.dias[fecha];
    const kwh = obj ? obj.kwh : 0;
    const pct = Math.round((kwh/maxKwh)*100);
    const num = fecha.split('-')[2];
    const nom = semNombre(fecha);
    const div = document.createElement('div');
    div.className = 'cal-day' + (fecha===diaActivo?' active':'') + (!obj?' no-data':'');
    if(obj) div.dataset.fecha = fecha;
    div.innerHTML = `
      <div class="cal-dname">${{nom}}</div>
      <div class="cal-dnum">${{+num}}</div>
      <div class="cal-kwh">${{obj ? kwh.toFixed(1)+' kWh' : '—'}}</div>
      <div class="cal-bar"><div class="cal-bar-fill" style="width:${{pct}}%"></div></div>`;
    scroll.appendChild(div);
  }});
}}

function calNav(dir){{
  if(!calMes) return;
  let [y,m] = calMes.split('-').map(Number);
  m += dir;
  if(m > 12){{ m=1; y++; }} else if(m < 1){{ m=12; y--; }}
  calMes = `${{y}}-${{String(m).padStart(2,'0')}}`;
  renderCalendario();
  // Al cambiar de mes → vista de mes completo
  periodo = 'mes';
  document.querySelectorAll('.btn-period').forEach(b=>b.classList.remove('active'));
  const pm = document.getElementById('p-mes');
  if(pm) pm.classList.add('active');
  actualizarGraficos();
  actualizarNavLabel();
}}

function seleccionarDia(fecha){{
  diaActivo = fecha;
  // Al seleccionar un día concreto → vista de día
  periodo = 'dia';
  document.querySelectorAll('.btn-period').forEach(b=>b.classList.remove('active'));
  const pd = document.getElementById('p-dia');
  if(pd) pd.classList.add('active');
  renderCalendario();
  actualizarGraficos();
  actualizarNavLabel();
}}

// ── Navegación directa por fecha (navbar input) ───────────────────────
function irAFecha(fechaStr){{
  if(!fechaStr) return;
  const parts = fechaStr.split('-').map(Number);
  if(parts.length !== 3) return;
  const [y, m] = parts;
  calMes = `${{y}}-${{String(m).padStart(2,'0')}}`;
  if(SOLAR.dias[fechaStr]){{
    diaActivo = fechaStr;
    periodo = 'dia';
    document.querySelectorAll('.btn-period').forEach(b=>b.classList.remove('active'));
    const pd = document.getElementById('p-dia');
    if(pd) pd.classList.add('active');
  }} else {{
    periodo = 'mes';
    document.querySelectorAll('.btn-period').forEach(b=>b.classList.remove('active'));
    const pm = document.getElementById('p-mes');
    if(pm) pm.classList.add('active');
  }}
  renderCalendario();
  actualizarGraficos();
  actualizarNavLabel();
}}

// ── Período ───────────────────────────────────────────────────────────
function setPeriodo(p){{
  periodo = p;
  document.querySelectorAll('.btn-period').forEach(b=>b.classList.remove('active'));
  document.getElementById('p-'+p).classList.add('active');
  if(p==='dia' && !diaActivo){{
    const dias = fechasDias();
    if(dias.length) diaActivo = dias[dias.length-1];
  }}
  actualizarGraficos();
  actualizarNavLabel();
}}

function actualizarNavLabel(){{
  const lbl = document.getElementById('nav-label');
  if(!lbl) return;
  if(periodo==='dia')      lbl.textContent = diaActivo ? fmtFecha(diaActivo) : '—';
  else if(periodo==='mes') lbl.textContent = calMes || '—';
  else if(periodo==='anio'){{
    const dias = fechasDias();
    lbl.textContent = dias.length ? dias[0].slice(0,4)+' – '+dias[dias.length-1].slice(0,4) : '—';
  }} else lbl.textContent = 'Todo el registro';
}}

// ── Datos para el período activo ─────────────────────────────────────
function getDatosPeriodo(){{
  const dias = fechasDias();
  if(!dias.length) return {{ts:[],pac:[],irr:[],tamb:[],tmod:[]}};

  if(periodo==='dia' && diaActivo){{
    const h = SOLAR.dias[diaActivo]?.horas || {{}};
    return {{ ts: h.t||[], pac: h.pac||[], irr: h.irr||[], tamb: h.tamb||[], tmod: h.tmod||[] }};
  }}

  // Para mes/año/todo: agregar por día (un punto = media diaria)
  let filtro;
  if(periodo==='mes')      filtro = d => calMes && d.startsWith(calMes);
  else if(periodo==='anio'){{
    const anio = diaActivo ? diaActivo.slice(0,4) : (dias[dias.length-1]||'').slice(0,4);
    filtro = d => d.startsWith(anio);
  }} else filtro = () => true;

  const sel = dias.filter(filtro);
  const ts=[],pac=[],irr=[],tamb=[],tmod=[];
  sel.forEach(d => {{
    const obj = SOLAR.dias[d];
    if(!obj) return;
    ts.push(d);
    pac.push(obj.kwh*1000);   // kWh → Wh-equiv para comparar, mostramos kWh en tooltip
    irr.push(obj.irr_max != null ? obj.irr_max : 0);
    tamb.push(obj.tamb_avg);
    tmod.push(obj.tmod_avg);
  }});
  return {{ts, pac, irr, tamb, tmod, _diario:true}};
}}

// ── uPlot ─────────────────────────────────────────────────────────────
function tsToSec(tStr, fecha){{
  // Los timestamps de SMA están en hora local — usar Date() sin UTC
  // para que el navegador interprete como hora local y no desplace 6 h.
  return new Date(fecha + 'T' + tStr + ':00').getTime() / 1000;
}}

function construirSeriesUplot(datos){{
  if(!datos.ts.length) return null;
  const isDiario = datos._diario;
  let xs;
  if(isDiario){{
    // Usar mediodía local para que la etiqueta de fecha no caiga en día anterior
    xs = datos.ts.map(d => new Date(d + 'T12:00:00').getTime() / 1000);
  }} else {{
    xs = datos.ts.map(t => tsToSec(t, diaActivo));
  }}
  return {{ xs, pac:datos.pac, irr:datos.irr, tamb:datos.tamb, tmod:datos.tmod, isDiario }};
}}

const _uOpts = (title, w) => ({{
  width: w||800, height:220,
  cursor:{{sync:{{key:'solar'}}}},
  scales:{{x:{{time:true}}}},
  legend:{{show:true}},
  axes:[
    {{stroke:'#475569',grid:{{stroke:'rgba(255,255,255,.04)'}},ticks:{{stroke:'#475569'}}}},
    {{stroke:'#38bdf8',grid:{{stroke:'rgba(255,255,255,.04)'}},ticks:{{stroke:'#38bdf8'}}}},
    {{side:1,stroke:'#f59e0b',grid:{{show:false}},ticks:{{stroke:'#f59e0b'}}}},
  ],
}});

function buildUPac(data, w){{
  if(uPac){{ uPac.destroy(); uPac=null; }}
  if(!data) return;
  const isDiario = data.isDiario;
  const pac  = data.pac.map(v=>v==null?null:(isDiario?v/1000:v));
  const irr  = data.irr.map(v=>v==null?null:v);
  const labelPac = isDiario ? 'Energía (kWh)' : 'Potencia AC (W)';
  const labelIrr = isDiario ? 'Irradiancia pico (W/m²)' : 'Irradiancia (W/m²)';
  const opts = {{
    width: w||800, height:220,
    cursor:{{sync:{{key:'solar'}}}},
    scales:{{ x:{{time:true}}, pac:{{auto:true}}, irr:{{auto:true}} }},
    legend:{{show:true}},
    axes:[
      {{stroke:'#475569',grid:{{stroke:'rgba(255,255,255,.04)'}},ticks:{{stroke:'#475569'}}}},
      {{scale:'irr',side:3,size:60,stroke:'#f59e0b',label:labelIrr,
        grid:{{stroke:'rgba(255,255,255,.04)'}},ticks:{{stroke:'#f59e0b'}}}},
      {{scale:'pac',side:1,size:60,stroke:'#fbbf24',label:labelPac,
        grid:{{show:false}},ticks:{{stroke:'#fbbf24'}}}},
    ],
    series:[
      {{}},
      {{label:labelIrr,stroke:'#f59e0b',width:1.5,scale:'irr',dash:[4,3],
        value:(u,v)=>v!=null?v.toFixed(1)+' W/m²':'—'}},
      {{label:labelPac,     stroke:'#fbbf24',width:1.5,scale:'pac',
        value:(u,v)=>v!=null?v.toFixed(isDiario?2:0)+(isDiario?' kWh':' W'):'—'}},
    ],
  }};
  const cont = document.getElementById('uplot-pac');
  if(!cont) return;
  uPac = new uPlot(opts, [data.xs, irr, pac], cont);
}}

function buildUTemp(data, w){{
  if(uTemp){{ uTemp.destroy(); uTemp=null; }}
  if(!data) return;
  const opts = {{
    width: w||800, height:180,
    cursor:{{sync:{{key:'solar'}}}},
    scales:{{ x:{{time:true}}, t:{{auto:true}} }},
    legend:{{show:true}},
    axes:[
      {{stroke:'#475569',grid:{{stroke:'rgba(255,255,255,.04)'}},ticks:{{stroke:'#475569'}}}},
      {{scale:'t',stroke:'#38bdf8',label:'Temperatura (°C)',
        grid:{{stroke:'rgba(255,255,255,.04)'}},ticks:{{stroke:'#38bdf8'}}}},
    ],
    series:[
      {{}},
      {{label:'T. Ambiente',stroke:'#38bdf8',width:1.5,scale:'t',
        value:(u,v)=>v!=null?v.toFixed(1)+' °C':'—'}},
      {{label:'T. Módulo',  stroke:'#f87171',width:1.5,scale:'t',
        value:(u,v)=>v!=null?v.toFixed(1)+' °C':'—'}},
    ],
  }};
  const cont = document.getElementById('uplot-temp');
  if(!cont) return;
  uTemp = new uPlot(opts, [data.xs, data.tamb, data.tmod], cont);
}}

function chartWidth(){{ return Math.min(document.querySelector('.main').offsetWidth - 80, 1300); }}

function actualizarGraficos(){{
  const datos  = getDatosPeriodo();
  const series = construirSeriesUplot(datos);
  const w      = chartWidth();
  buildUPac(series,  w);
  buildUTemp(series, w);
  // Ajustar al ancho real tras cualquier reflow del DOM
  requestAnimationFrame(() => {{
    const w2 = chartWidth();
    if(uPac)  uPac.setSize({{width:w2, height:220}});
    if(uTemp) uTemp.setSize({{width:w2, height:180}});
  }});
}}

// ── Zoom ──────────────────────────────────────────────────────────────
const _zoomState = {{}};
function uZoom(key, dir){{
  const u = key==='pac'?uPac:uTemp;
  if(!u) return;
  const sc = u.scales.x;
  const rng = sc.max - sc.min;
  const factor = dir<0 ? 0.7 : 1.4;
  const mid = (sc.min+sc.max)/2;
  u.setScale('x',{{min:mid-rng*factor/2, max:mid+rng*factor/2}});
}}
function uZoomReset(key){{
  const u = key==='pac'?uPac:uTemp;
  if(u) u.setData(u.data);
}}

// ── Stats grid ────────────────────────────────────────────────────────
const STATS_VARS = [
  ['pac_total','Potencia AC Total (W)'],
  ['irr','Irradiancia (W/m²)'],
  ['tamb','Temperatura Ambiente (°C)'],
  ['tmod','Temperatura Módulo (°C)'],
  ['energia_wh','Energía por Intervalo (Wh)'],
];
function renderStatsGrid(){{
  const grid = document.getElementById('stats-grid');
  if(!grid) return;
  // Stats are embedded from Python
  const GLOBAL_STATS = {stats_json};
  grid.innerHTML = '';
  STATS_VARS.forEach(([k,nombre]) => {{
    const st = GLOBAL_STATS[k];
    if(!st) return;
    const card = document.createElement('div');
    card.className = 'stat-card';
    card.innerHTML = `
      <div class="stat-name">${{nombre}}</div>
      <div class="stat-row"><span class="stat-key">Media</span><span class="stat-val">${{st.media.toFixed(2)}}</span></div>
      <div class="stat-row"><span class="stat-key">σ</span><span class="stat-val">${{st.desv.toFixed(2)}}</span></div>
      <div class="stat-row"><span class="stat-key">Máx</span><span class="stat-val">${{st.maximo.toFixed(2)}}</span></div>
      <div class="stat-row"><span class="stat-key">Mín</span><span class="stat-val">${{st.minimo.toFixed(2)}}</span></div>
      <div class="stat-row"><span class="stat-key">Mediana</span><span class="stat-val">${{st.p50.toFixed(2)}}</span></div>
      <div class="stat-row"><span class="stat-key">N</span><span class="stat-val">${{st.n.toLocaleString()}}</span></div>`;
    grid.appendChild(card);
  }});
}}

// ── Comparativa ───────────────────────────────────────────────────────
function toggleComparacion(){{
  modoComp = !modoComp;
  const panel  = document.getElementById('comp-panel');
  const calSec = document.getElementById('cal-section');
  const btn    = document.getElementById('btn-comparar');
  if(modoComp){{
    panel.classList.add('visible');
    if(calSec) calSec.style.display='none';
    if(btn) btn.classList.add('btn-comparar-active');
    _prefillDates();
  }} else {{
    panel.classList.remove('visible');
    document.getElementById('comp-result').innerHTML='';
    if(calSec) calSec.style.display='';
    if(btn) btn.classList.remove('btn-comparar-active');
  }}
}}

function _prefillDates(){{
  const dias = fechasDias();
  if(!dias.length) return;
  const mid  = dias[Math.floor(dias.length/2)];
  const last = dias[dias.length-1];
  const get  = id => document.getElementById(id);
  if(!get('comp-a-desde').value) get('comp-a-desde').value = dias[0];
  if(!get('comp-a-hasta').value) get('comp-a-hasta').value = mid;
  if(!get('comp-b-desde').value) get('comp-b-desde').value = mid;
  if(!get('comp-b-hasta').value) get('comp-b-hasta').value = last;
}}

function _calcStats(vals){{
  if(!vals.length) return {{n:0,media:0,sd:0,min:0,max:0}};
  const n   = vals.length;
  const sum = vals.reduce((a,b)=>a+b,0);
  const mu  = sum/n;
  const var_ = vals.reduce((a,b)=>a+(b-mu)*(b-mu),0)/n;
  const sd  = Math.sqrt(var_);
  let mn=vals[0],mx=vals[0];
  vals.forEach(v=>{{if(v<mn)mn=v;if(v>mx)mx=v;}});
  return {{n,media:mu,sd,min:mn,max:mx}};
}}

function _getDiasRango(desde, hasta){{
  return fechasDias().filter(d => d>=desde && d<=hasta);
}}

function _interpretarSolar(sA, sB, varNombre){{
  const dif = sB.media - sA.media;
  const pct = Math.abs(sA.media)>0.01 ? Math.abs(dif/sA.media*100).toFixed(1) : '—';
  let txt = '';
  if(Math.abs(dif)<0.5)
    txt = `En <strong>${{varNombre}}</strong>, ambos períodos son muy similares en promedio.`;
  else{{
    const cual = dif>0 ? 'el Rango B fue mayor' : 'el Rango A fue mayor';
    txt = `En <strong>${{varNombre}}</strong>, ${{cual}} (${{(dif>=0?'+':'')+dif.toFixed(1)}}, variación ~${{pct}}%). `;
    if(varNombre.includes('Energía')||varNombre.includes('Potencia'))
      txt += dif>0 ? 'El segundo período generó más energía, posiblemente por mejor irradiancia o más días soleados.'
                   : 'El primer período fue más productivo.';
    else if(varNombre.includes('Irradiancia'))
      txt += dif>0 ? 'Mayor irradiación en el período B sugiere condiciones más soleadas.'
                   : 'Mayor irradiación en el período A — cielos más despejados.';
    else if(varNombre.includes('Temperatura'))
      txt += 'Las diferencias de temperatura pueden afectar el rendimiento de los módulos.';
  }}
  return txt;
}}

function renderComparacion(){{
  const aD = document.getElementById('comp-a-desde').value;
  const aH = document.getElementById('comp-a-hasta').value;
  const bD = document.getElementById('comp-b-desde').value;
  const bH = document.getElementById('comp-b-hasta').value;
  if(!aD||!aH||!bD||!bH){{ alert('Completa ambos rangos de fecha.'); return; }}

  const diasA = _getDiasRango(aD,aH);
  const diasB = _getDiasRango(bD,bH);

  const vars = [
    ['kwh',     'Energía diaria (kWh)'],
    ['pac_max', 'Potencia pico (W)'],
    ['irr_max', 'Irradiancia pico (W/m²)'],
    ['tamb_avg','T. Ambiente (°C)'],
    ['tmod_avg','T. Módulo (°C)'],
  ];

  let rowsHtml = '';
  const miniData = [];
  vars.forEach(([k,nombre]) => {{
    const vA = diasA.map(d=>SOLAR.dias[d]?.[k]).filter(v=>v!=null&&!isNaN(v));
    const vB = diasB.map(d=>SOLAR.dias[d]?.[k]).filter(v=>v!=null&&!isNaN(v));
    if(!vA.length&&!vB.length) return;
    const sA = _calcStats(vA), sB = _calcStats(vB);
    const dMed = sB.media-sA.media;
    const dCls = dMed>=0?'comp-diff-pos':'comp-diff-neg';
    rowsHtml += `<tr>
      <td class="var-name">${{nombre}}</td>
      <td>${{sA.n}}</td><td>${{sA.media.toFixed(2)}}</td><td>${{sA.sd.toFixed(2)}}</td>
      <td>${{sA.min.toFixed(2)}}</td><td>${{sA.max.toFixed(2)}}</td>
      <td>${{sB.n}}</td><td>${{sB.media.toFixed(2)}}</td><td>${{sB.sd.toFixed(2)}}</td>
      <td>${{sB.min.toFixed(2)}}</td><td>${{sB.max.toFixed(2)}}</td>
      <td class="${{dCls}}">${{(dMed>=0?'+':'')+dMed.toFixed(2)}}</td>
    </tr>`;
    miniData.push({{k,nombre,vA,vB,sA,sB}});
  }});

  // Mini charts HTML
  let miniHtml = '<div class="comp-mini-charts">';
  miniData.forEach(item => {{
    miniHtml += `<div class="comp-mini-card">
      <div class="comp-mini-label">${{item.nombre}}</div>
      <canvas id="comp-cv-${{item.k}}" width="220" height="70"></canvas>
    </div>`;
  }});
  miniHtml += '</div>';

  // Interpretación texto (primera var no-temp)
  const mainItem = miniData.find(d=>d.k==='kwh')||miniData[0];
  const interp = mainItem ? _interpretarSolar(mainItem.sA, mainItem.sB, mainItem.nombre) : '';

  document.getElementById('comp-result').innerHTML = `
    <div class="comp-result-title">
      <span class="comp-badge-a">Rango A</span> (${{aD}} → ${{aH}})
      vs <span class="comp-badge-b">Rango B</span> (${{bD}} → ${{bH}})
    </div>
    <div class="comp-table-wrap"><table class="comp-table">
      <thead><tr>
        <th>Variable</th>
        <th colspan="5" style="color:#f87171">Rango A</th>
        <th colspan="5" style="color:#34d399">Rango B</th>
        <th>Δ</th>
      </tr><tr>
        <th></th>
        <th>N</th><th>Media</th><th>σ</th><th>Mín</th><th>Máx</th>
        <th>N</th><th>Media</th><th>σ</th><th>Mín</th><th>Máx</th>
        <th></th>
      </tr></thead>
      <tbody>${{rowsHtml}}</tbody>
    </table></div>
    ${{miniHtml}}
    <div class="comp-interp">${{interp}}</div>`;

  requestAnimationFrame(() => {{
    miniData.forEach(item => {{
      const cv = document.getElementById('comp-cv-'+item.k);
      if(!cv) return;
      _drawCompChart(cv, item.vA, item.vB);
    }});
  }});
}}

function _drawCompChart(canvas, datA, datB){{
  const ctx=canvas.getContext('2d');
  const W=canvas.width,H=canvas.height;
  ctx.clearRect(0,0,W,H);
  if(!datA.length&&!datB.length) return;
  const ds = arr => {{
    if(arr.length<=60) return arr;
    const out=[]; const step=arr.length/60;
    for(let i=0;i<60;i++) out.push(arr[Math.round(i*step)]);
    return out;
  }};
  const sA=ds(datA),sB=ds(datB);
  const all=sA.concat(sB);
  const mn=Math.min(...all),mx=Math.max(...all),rng=mx-mn||1;
  const drawLine=(pts,color)=>{{
    if(!pts.length) return;
    ctx.beginPath(); ctx.strokeStyle=color; ctx.lineWidth=1.5;
    pts.forEach((v,i)=>{{
      const x=(i/(pts.length-1||1))*W, y=H-((v-mn)/rng)*(H-8)-4;
      i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
    }}); ctx.stroke();
  }};
  if(sA.length>1){{
    ctx.beginPath();
    sA.forEach((v,i)=>{{
      const x=(i/(sA.length-1||1))*W,y=H-((v-mn)/rng)*(H-8)-4;
      i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
    }});
    ctx.lineTo(W,H);ctx.lineTo(0,H);ctx.closePath();
    ctx.fillStyle='rgba(248,113,113,.12)';ctx.fill();
  }}
  drawLine(sA,'#f87171'); drawLine(sB,'#34d399');
  ctx.beginPath();ctx.arc(8,8,4,0,Math.PI*2);ctx.fillStyle='#f87171';ctx.fill();
  ctx.beginPath();ctx.arc(8,20,4,0,Math.PI*2);ctx.fillStyle='#34d399';ctx.fill();
  ctx.fillStyle='rgba(255,255,255,.5)';ctx.font='9px sans-serif';
  ctx.fillText('A',16,12);ctx.fillText('B',16,24);
}}

// ── Arranque ──────────────────────────────────────────────────────────
function _initCalListener(){{
  const scroll = document.getElementById('cal-scroll');
  if(!scroll || scroll._calInit) return;
  scroll._calInit = true;
  scroll.addEventListener('click', function(e){{
    const dayEl = e.target.closest('.cal-day:not(.no-data)');
    if(!dayEl || !dayEl.dataset.fecha) return;
    seleccionarDia(dayEl.dataset.fecha);
  }});
}}

function init(){{
  const dias = fechasDias();
  if(dias.length){{
    diaActivo = dias[dias.length-1];
    calMes = diaActivo.slice(0,7);
  }}
  renderCalendario();
  _initCalListener();
  actualizarGraficos();
  renderStatsGrid();
  actualizarNavLabel();
  // Redimensionar al ancho real después de layout
  requestAnimationFrame(() => {{
    const w = chartWidth();
    if(uPac)  uPac.setSize({{width:w, height:220}});
    if(uTemp) uTemp.setSize({{width:w, height:180}});
  }});
  const _resizeSolar = () => requestAnimationFrame(() => {{
    const w = chartWidth();
    if(uPac)  uPac.setSize({{width:w, height:220}});
    if(uTemp) uTemp.setSize({{width:w, height:180}});
  }});
  window.addEventListener('resize', _resizeSolar);
  new ResizeObserver(_resizeSolar).observe(document.querySelector('.main') || document.body);
}}

init();
</script>
</body></html>"""

    with open(nombre, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  [OK] Dashboard solar Canvas → {nombre}")
    return nombre


if __name__ == "__main__":
    resultado = analizar_sistema_solar()
    if resultado:
        os.makedirs(_DASH_DIR, exist_ok=True)
        os.makedirs(_EXPORT_DIR, exist_ok=True)
        salida = os.path.join(_DASH_DIR, "dashboard_solar.html")
        generar_dashboard_solar_canvas(resultado, salida)
        print(f"  → {salida} generado")
