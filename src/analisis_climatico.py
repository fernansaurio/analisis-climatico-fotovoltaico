#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=======================================================================
PROYECTO DE PROGRAMACIÓN NUMÉRICA Y ANÁLISIS CLIMÁTICO AVANZADO
Asignatura: Métodos Numéricos
Estaciones: 7GT-EEP (San Luis Talpa, La Paz) y 7GT-UES (Universidad de El Salvador, San Salvador)
=======================================================================
ÁRBOL DE MÓDULOS
─────────────────────────────────────────────────────────────────────
  analisis_climatico.py   ← PUNTO DE ENTRADA PRINCIPAL (este archivo)
  ajuste_curvas.py        ← Wrapper Python → C++ (AjusteCurvas)
  metodos_raices.py       ← Wrapper Python → C++ (MetodosRaices)
  algebra_lineal_lib.py   ← Wrapper Python → C++ (AlgebraLineal)

LIBRERÍAS UTILIZADAS
─────────────────────────────────────────────────────────────────────
 ✅ PERMITIDAS:
   pandas     → pd.read_csv, pd.to_datetime, pd.concat, drop_duplicates
   numpy      → np.asarray, np.zeros, np.float64, np.nan  (solo arrays)
   matplotlib → renderizado final de gráficos (Agg backend, sin GUI)

 ✅ ESTÁNDAR Python (sin restricciones):
   os, math, io, base64, webbrowser, ctypes, json

 ✅ WRAPPERS C++ PROPIOS (motor de alto rendimiento):
   AjusteCurvas  → media, σ, percentiles, QuickSort, Pearson, histogramas
   MetodosRaices → Newton-Raphson para raíz cuadrada de varianza
   AlgebraLineal → operaciones matriciales en Fase IV (opcional)

 ❌ PROHIBIDO (caja negra estadística):
   .mean(), .std(), .var(), .median(), .quantile(), .mode(),
   .describe(), .min(), .max(), .interpolate(), .fillna()
   y equivalentes de NumPy / SciPy.
=======================================================================
"""

# ──────────────────────────────────────────────────────────────────────
# BLOQUE 0 · IMPORTACIONES
# ──────────────────────────────────────────────────────────────────────
import os
import sys
import math
import io
import base64
import json
import webbrowser

import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")           # Sin GUI — compatible con servidores
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection

# ── Rutas base del proyecto ───────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT  = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
_WL_DIR     = os.path.join(_PROJ_ROOT, "datos_crudos", "weatherlink")
_DASH_DIR   = os.path.join(_PROJ_ROOT, "dashboard")
_EXPORT_DIR = os.path.join(_DASH_DIR, "exportaciones")

# Añadir core_math al path para importar wrappers C++
sys.path.insert(0, os.path.join(_PROJ_ROOT, "core_math"))

# ── Wrappers C++ ──────────────────────────────────────────────────────
_LIBS = {}

try:
    from ajuste_curvas import AjusteCurvas
    _LIBS["ac"] = True
    print("[C++] AjusteCurvas   ✓")
except (ImportError, OSError, FileNotFoundError) as e:
    _LIBS["ac"] = False
    print(f"[WARN] AjusteCurvas no disponible ({e})\n       → Fallback Python puro")

try:
    from metodos_raices import MetodosRaices
    _MR = MetodosRaices()
    _LIBS["mr"] = True
    print("[C++] MetodosRaices  ✓  (Newton-Raphson para √)")
except (ImportError, OSError, FileNotFoundError) as e:
    _MR = None
    _LIBS["mr"] = False
    print(f"[WARN] MetodosRaices no disponible ({e})\n       → Método Babilónico Python")

try:
    from algebra_lineal_lib import AlgebraLineal
    _LIBS["al"] = True
    print("[C++] AlgebraLineal  ✓")
except (ImportError, OSError, FileNotFoundError) as e:
    _LIBS["al"] = False
    print(f"[WARN] AlgebraLineal no disponible ({e})")


# ══════════════════════════════════════════════════════════════════════
# FASE I — CARGA, SEGMENTACIÓN TEMPORAL Y CURACIÓN NUMÉRICA
# ══════════════════════════════════════════════════════════════════════

FECHA_INICIO = pd.Timestamp("2025-02-01 00:00:00")

_COLS_TEXTO = {
    "Date & Time", "Prevailing Wind Dir",
    "Avg Wind Dir", "High Wind Direction",
}


def _es_nan(v) -> bool:
    """Detecta NaN sin math.isnan — cumple restricción de caja negra."""
    try:
        return v != v       # NaN ≠ NaN por IEEE 754
    except TypeError:
        return False


def _ruta_clean(ruta: str) -> str:
    """Devuelve la ruta del CSV limpio correspondiente al CSV original."""
    base, ext = os.path.splitext(ruta)
    return base + "_clean" + ext


def cargar_csv(ruta: str) -> pd.DataFrame:
    """
    ── FASE I ──────────────────────────────────────────────────────────
    Lee y cura un archivo CSV de WeatherLink.

    Caché de CSV limpio:
      Si existe <nombre>_clean.csv más reciente que el original,
      se carga directamente (sin re-procesar). Si no existe o está
      desactualizado, se ejecuta el pipeline completo y se guarda.

    Pipeline completo:
      1. Saltar 5 filas de metadatos (skiprows=5)
      2. Sustituir '--' y vacíos por NaN
      3. Parsear "Date & Time" con pd.to_datetime
      4. Filtrar: conservar solo desde FECHA_INICIO
      5. Interpolación lineal MANUAL (sin .interpolate())
      6. Guardar CSV limpio en <nombre>_clean.csv
    ────────────────────────────────────────────────────────────────────
    """
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"Archivo no encontrado: {ruta}")

    nombre_base = os.path.basename(ruta)
    ruta_clean  = _ruta_clean(ruta)

    # ── Comprobar caché ──────────────────────────────────────────────
    if os.path.exists(ruta_clean):
        t_orig  = os.path.getmtime(ruta)
        t_clean = os.path.getmtime(ruta_clean)
        if t_clean >= t_orig:
            print(f"  [CACHE] Cargando CSV limpio → {os.path.basename(ruta_clean)}")
            df = pd.read_csv(ruta_clean, low_memory=False, encoding="utf-8")
            dt_col = df.columns[0]
            df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
            print(f"          {len(df):,} registros (sin re-procesar)")
            return df
        else:
            print(f"  [CACHE] CSV original más nuevo — re-procesando...")

    # ── Pipeline de carga y curación ─────────────────────────────────
    print(f"  Leyendo → {nombre_base}")

    try:
        df = pd.read_csv(
            ruta,
            skiprows=5,
            header=0,
            na_values=["--", "---", "", " ", "N/A"],
            low_memory=False,
            encoding="utf-8",
            on_bad_lines="skip",
            quotechar='"',
        )
    except UnicodeDecodeError:
        print(f"  [WARN] Codificación UTF-8 falló para {nombre_base}; intentando latin-1")
        df = pd.read_csv(
            ruta,
            skiprows=5,
            header=0,
            na_values=["--", "---", "", " ", "N/A"],
            low_memory=False,
            encoding="latin-1",
            on_bad_lines="skip",
            quotechar='"',
        )

    # Limpiar comillas residuales en nombres de columna
    df.columns = [str(c).strip().replace('"', '') for c in df.columns]

    # Parsear timestamps
    dt_col = df.columns[0]
    df[dt_col] = (df[dt_col].astype(str)
                  .str.replace('"', '').str.strip())
    df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce", dayfirst=False)

    # Convertir columnas numéricas
    for col in df.columns:
        if col not in _COLS_TEXTO:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Filtro temporal — solo desde 01/02/2025
    df = df[df[dt_col] >= FECHA_INICIO].copy()
    df = df.reset_index(drop=True)
    n_registros = len(df)

    # Contar NaN antes de interpolar
    total_nan_antes = sum(
        df[c].isna().sum() for c in df.columns if c not in _COLS_TEXTO
    )

    # ── Interpolación lineal MANUAL ──────────────────────────────────
    df = _interpolar_manual(df, nombre_csv=nombre_base)

    total_nan_despues = sum(
        df[c].isna().sum() for c in df.columns if c not in _COLS_TEXTO
    )
    rellenados = total_nan_antes - total_nan_despues

    print(f"       {n_registros:,} registros válidos desde {FECHA_INICIO.date()}")
    print(f"       NaN antes: {total_nan_antes:,}  →  rellenados: {rellenados:,}"
          f"  →  NaN restantes: {total_nan_despues:,}")

    # ── Guardar CSV limpio ───────────────────────────────────────────
    df.to_csv(ruta_clean, index=False, encoding="utf-8")
    print(f"       [GUARDADO] CSV limpio → {os.path.basename(ruta_clean)}")

    return df


# Acumulador global de estadísticas de interpolación
# { nombre_csv: { col: {nan_antes, interpolados_lineal, extrapolados, nan_despues} } }
_INTERP_LOG: dict = {}


def _interpolar_manual(df: pd.DataFrame,
                        nombre_csv: str = "") -> pd.DataFrame:
    """
    Interpolación lineal MANUAL sobre NaN — sin .interpolate() ni .fillna().

    Método aplicado (Interpolación Lineal por Tramos):
    ─────────────────────────────────────────────────────────────────────
    Sea a = índice del último valor conocido antes del hueco,
        b = índice del primer valor conocido después del hueco.
    Para cada índice k en [a+1, b-1]:

        f(k) = f(a) + (k - a) × [f(b) − f(a)] / (b − a)

    Casos límite (extrapolación constante):
      · Solo borde izquierdo conocido (b no existe) → f(k) = f(a)
      · Solo borde derecho conocido (a no existe)   → f(k) = f(b)
      · Columna completamente vacía                 → sin cambio

    Justificación de elección:
      La interpolación lineal es el método más apropiado para series
      temporales climáticas de intervalos regulares (5 min) porque:
        1. Asume variación suave y continua entre mediciones consecutivas.
        2. Preserva la tendencia local sin distorsionar máximos/mínimos.
        3. Computacionalmente O(n) — sin sistemas de ecuaciones.
        4. Alternativas como splines cúbicos (requieren álgebra lineal
           global) o Lagrange (oscilaciones de Runge en huecos largos)
           son innecesariamente complejas para huecos de 5–30 min.
    ─────────────────────────────────────────────────────────────────────
    """
    log_csv: dict = {}

    for col in df.columns:
        if col in _COLS_TEXTO:
            continue
        vals = df[col].tolist()
        n    = len(vals)

        nan_antes = sum(1 for v in vals if _es_nan(v))
        if nan_antes == 0:
            continue   # columna sin NaN — saltamos

        cnt_lineal    = 0
        cnt_extrapol  = 0

        i = 0
        while i < n:
            if _es_nan(vals[i]):
                # Buscar vecino izquierdo (a)
                a = i - 1
                while a >= 0 and _es_nan(vals[a]):
                    a -= 1
                # Buscar vecino derecho (b)
                b = i + 1
                while b < n and _es_nan(vals[b]):
                    b += 1

                fin = b if b < n else n
                for k in range(i, fin):
                    if a >= 0 and b < n:
                        # Interpolación lineal
                        fa, fb = vals[a], vals[b]
                        vals[k]      = fa + (k - a) * (fb - fa) / (b - a)
                        cnt_lineal  += 1
                    elif a >= 0:
                        # Extrapolación por el extremo izquierdo
                        vals[k]       = vals[a]
                        cnt_extrapol += 1
                    elif b < n:
                        # Extrapolación por el extremo derecho
                        vals[k]       = vals[b]
                        cnt_extrapol += 1
                i = b
            else:
                i += 1

        df[col] = vals
        nan_despues = sum(1 for v in vals if _es_nan(v))

        if nan_antes > 0:
            log_csv[col] = {
                "nan_antes":        nan_antes,
                "interpolados":     cnt_lineal,
                "extrapolados":     cnt_extrapol,
                "nan_despues":      nan_despues,
            }

    if nombre_csv:
        _INTERP_LOG[nombre_csv] = log_csv

    return df


def concatenar_estacion(rutas: list) -> pd.DataFrame:
    """Une múltiples CSVs de la misma estación, elimina duplicados."""
    frames = []
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for ruta in rutas:
        if os.path.exists(ruta):
            frames.append(cargar_csv(ruta))
        else:
            alt = os.path.join(script_dir, ruta)
            if os.path.exists(alt):
                frames.append(cargar_csv(alt))
            else:
                print(f"  [WARN] No encontrado: {os.path.basename(ruta)}")
    if not frames:
        raise RuntimeError(f"No se encontró ningún CSV en: {rutas}")
    dt_col = frames[0].columns[0]
    df = pd.concat(frames, ignore_index=True)
    df = (df.drop_duplicates(subset=[dt_col])
            .sort_values(dt_col)
            .reset_index(drop=True))
    return df


# ══════════════════════════════════════════════════════════════════════
# FASE II — MOTOR ESTADÍSTICO MANUAL
# ══════════════════════════════════════════════════════════════════════

# ── II.A: Raíz cuadrada con Newton-Raphson ────────────────────────────

def sqrt_nr(S: float) -> float:
    """
    √S mediante Newton-Raphson / Método Babilónico.
    Delega al wrapper C++ si está disponible.
    """
    if S < 0:
        return float("nan")
    if S == 0.0:
        return 0.0
    if _MR is not None:
        try:
            f  = lambda x: x * x - S
            df = lambda x: 2.0 * x
            raiz, _ = _MR.newton_raphson(f, df, S / 2.0, tol=1e-12, max_iter=200)
            return raiz
        except Exception:
            pass
    # Fallback Babilónico Python puro
    x = max(S, 1.0)
    for _ in range(200):
        xn = 0.5 * (x + S / x)
        if abs(xn - x) < 1e-13 * x:
            break
        x = xn
    return x


def log2_manual(n: float) -> float:
    """log₂(n) = ln(n)/ln(2) — para Regla de Sturges."""
    return math.log(n) / math.log(2)


# ── II.B: Utilidades puras Python (fallback cuando no hay C++) ─────────

def _serie(df: pd.DataFrame, col: str) -> list:
    """Extrae columna como lista de float, descartando NaN."""
    if col not in df.columns:
        return []
    out = []
    for v in df[col].tolist():
        if not _es_nan(v) and v is not None:
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                pass
    return out


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


def _moda(s: list, dec: int = 1) -> float:
    if not s:
        return float("nan")
    tabla = {}
    for v in s:
        k = round(v, dec)
        tabla[k] = tabla.get(k, 0) + 1
    mejor, max_f = None, -1
    for k, f in tabla.items():
        if f > max_f:
            max_f = f
            mejor = k
    return float(mejor) if mejor is not None else float("nan")


def _quicksort(arr: list) -> list:
    """QuickSort recursivo con pivot mediana-de-tres. O(n log n) promedio."""
    n = len(arr)
    if n <= 1:
        return arr[:]
    a, b, c = arr[0], arr[n // 2], arr[-1]
    pivot = sorted([a, b, c])[1]
    izq = [x for x in arr if x < pivot]
    cen = [x for x in arr if x == pivot]
    der = [x for x in arr if x > pivot]
    return _quicksort(izq) + cen + _quicksort(der)


def _percentil(s: list, p: float) -> float:
    """
    Percentil p (0–100) via QuickSort + interpolación lineal.
    L = (p/100)×(n-1); interpolación entre floor(L) y ceil(L).
    """
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


# ── II.C: Wrapper inteligente → usa C++ si disponible ─────────────────

def _ac_from_serie(s: list):
    """Crea AjusteCurvas con serie como matriz Nx1."""
    ac = AjusteCurvas()
    datos = np.asarray([[v] for v in s], dtype=np.float64)
    ac.establecer_datos(datos)
    return ac


def calcular_estadisticos(df: pd.DataFrame, col: str) -> dict:
    """
    ── FASE II ──────────────────────────────────────────────────────────
    Estadísticos completos de una columna:
      N, Media, Varianza, σ (Newton-Raphson), Moda, Máx, Mín, Rango,
      P10, P25, P50, P75, P90, IQR, IC90% inferior/superior.
    Motor: C++ (AjusteCurvas) con fallback Python puro.
    ─────────────────────────────────────────────────────────────────────
    """
    s = _serie(df, col)
    n = len(s)
    if n == 0:
        return {"col": col, "n": 0, "error": "Sin datos"}

    if _LIBS["ac"]:
        ac = _ac_from_serie(s)
        ac.ordenar_por_columna(0, ascendente=True)
        mu   = ac.media(0)
        var  = ac.varianza_metodo3(0)
        sig  = ac.desviacion_estandar_metodo3(0)
        vmax = ac.maximo(0)
        vmin = ac.minimo(0)
        mod  = ac.moda(0)
        p10  = ac.percentil(0, 10.0)
        p25  = ac.percentil(0, 25.0)
        p50  = ac.mediana(0)
        p75  = ac.percentil(0, 75.0)
        p90  = ac.percentil(0, 90.0)
    else:
        mu   = _media(s)
        var  = _varianza(s)
        sig  = sqrt_nr(var)
        vmax = _maximo(s)
        vmin = _minimo(s)
        mod  = _moda(s)
        p10  = _percentil(s, 10)
        p25  = _percentil(s, 25)
        p50  = _percentil(s, 50)
        p75  = _percentil(s, 75)
        p90  = _percentil(s, 90)

    # IC 90%: x̄ ± 1.645 · σ/√n
    error_ic = 1.645 * sig / sqrt_nr(n)

    return {
        "col": col, "n": n,
        "media": mu, "varianza": var, "desv_estandar": sig,
        "maximo": vmax, "minimo": vmin, "rango": vmax - vmin,
        "moda": mod,
        "p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90,
        "riq": p75 - p25,
        "ic_inf": mu - error_ic, "ic_sup": mu + error_ic,
    }


def calcular_estadisticos_mensuales(df: pd.DataFrame, col: str) -> dict:
    """Estadísticos mes a mes sin .mean()/.std()/.median()."""
    dt_col = df.columns[0]
    df2 = df[[dt_col, col]].copy()
    df2["_mes"] = df2[dt_col].dt.to_period("M")
    periodos = sorted(df2["_mes"].dropna().unique(), key=str)
    res = {}
    for p in periodos:
        mask = (df2["_mes"] == p).tolist()
        s = []
        for inc, v in zip(mask, df2[col].tolist()):
            if inc and not _es_nan(v):
                try:
                    s.append(float(v))
                except (TypeError, ValueError):
                    pass
        if not s:
            continue
        if _LIBS["ac"]:
            ac = _ac_from_serie(s)
            ac.ordenar_por_columna(0, True)
            res[str(p)] = {
                "n": len(s), "media": ac.media(0),
                "desv": ac.desviacion_estandar_metodo3(0),
                "maximo": ac.maximo(0), "minimo": ac.minimo(0),
                "p25": ac.percentil(0, 25), "p50": ac.mediana(0),
                "p75": ac.percentil(0, 75),
            }
        else:
            res[str(p)] = {
                "n": len(s), "media": _media(s),
                "desv": sqrt_nr(_varianza(s)),
                "maximo": _maximo(s), "minimo": _minimo(s),
                "p25": _percentil(s, 25), "p50": _percentil(s, 50),
                "p75": _percentil(s, 75),
            }
    return res


def imprimir_stats(st: dict, estacion: str):
    print(f"\n{'═'*60}")
    print(f"  {st.get('col','?'):<30} │ {estacion}")
    print(f"{'═'*60}")
    for etiq, k in [
        ("N muestral", "n"), ("Media (x̄)", "media"),
        ("Varianza (s²)", "varianza"), ("Desv. Est. (σ)", "desv_estandar"),
        ("Moda", "moda"), ("Máximo", "maximo"), ("Mínimo", "minimo"),
        ("Rango", "rango"), ("P10", "p10"), ("P25 (Q1)", "p25"),
        ("P50 – Mediana", "p50"), ("P75 (Q3)", "p75"), ("P90", "p90"),
        ("IQR", "riq"), ("IC 90% inf", "ic_inf"), ("IC 90% sup", "ic_sup"),
    ]:
        v = st.get(k, float("nan"))
        s = str(v) if k == "n" else f"{v:.5f}"
        print(f"  {etiq:<22}: {s}")


# ══════════════════════════════════════════════════════════════════════
# FASE III — VISUALIZACIONES
# ══════════════════════════════════════════════════════════════════════

# Paleta unificada inspirada en el dashboard de referencia
_C = dict(
    fondo="#050f2e",
    ax=(0.04, 0.12, 0.25, 1.0),
    grid=(1, 1, 1, 0.05),
    texto="#7b93c4",
    primario="#e8f0ff",
    naranja="#f59e0b",
    azul="#3b82f6",
    cyan="#06b6d4",
    verde="#10b981",
    amarillo="#fbbf24",
    rojo="#ef4444",
    rosa="#fca5a5",
    azul_claro="#93c5fd",
)
plt.rcParams.update({
    "text.color": _C["texto"],
    "axes.labelcolor": _C["texto"],
    "xtick.color": _C["texto"],
    "ytick.color": _C["texto"],
})


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
                dpi=150, facecolor=fig.get_facecolor())
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return b64


# ── III.A: Serie temporal ─────────────────────────────────────────────

def grafico_serie(df: pd.DataFrame, col: str,
                  titulo: str, ylabel: str, color: str) -> str:
    """Línea temporal de la variable sobre el histórico completo."""
    dt_col = df.columns[0]
    tiempos = df[dt_col].tolist()
    valores = df[col].tolist()
    n = len(valores)
    if n == 0:
        return ""

    # Calcular medias móviles manualmente (ventana 288 = 1 día de muestras a 5 min)
    ventana = 288
    media_movil = []
    for i in range(n):
        inicio = max(0, i - ventana // 2)
        fin    = min(n, i + ventana // 2)
        bloque = [valores[j] for j in range(inicio, fin) if not _es_nan(valores[j])]
        media_movil.append(_media(bloque) if bloque else float("nan"))

    fig, ax = plt.subplots(figsize=(13, 3.8))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, titulo, "Fecha", ylabel)

    x = list(range(n))
    ax.fill_between(x, [v if not _es_nan(v) else 0 for v in valores],
                    alpha=0.12, color=color)
    ax.plot(x, valores, color=color, linewidth=0.55, alpha=0.7, label="Datos brutos")
    ax.plot(x, media_movil, color=_C["amarillo"], linewidth=1.8,
            alpha=0.95, label="Media móvil (1 día)")

    paso = max(1, n // 8)
    ticks = list(range(0, n, paso))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(tiempos[i])[:10] for i in ticks if i < n],
                       color=_C["texto"], fontsize=7.5, rotation=15)
    ax.legend(facecolor=_C["fondo"], labelcolor=_C["texto"],
              fontsize=8, edgecolor="#1e3a5f", loc="upper right")
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


# ── III.B: Histograma (Regla de Sturges) ─────────────────────────────

def histograma(serie: list, titulo: str, xlabel: str,
               color: str = "#f59e0b") -> str:
    """
    Histograma de frecuencias absolutas.
    Bins = ⌈log₂(n) + 1⌉  (Sturges).
    Líneas: x̄ (rojo) y ±σ (amarillo).
    """
    n = len(serie)
    if n == 0:
        return ""

    k = max(5, math.ceil(log2_manual(n) + 1))
    vmin = _minimo(serie)
    vmax = _maximo(serie)
    ancho = (vmax - vmin) / k if (vmax - vmin) > 0 else 1.0

    freq = [0] * k
    for v in serie:
        idx = int((v - vmin) / ancho)
        idx = max(0, min(k - 1, idx))
        freq[idx] += 1

    centros = [vmin + (i + 0.5) * ancho for i in range(k)]
    mu  = _media(serie)
    sig = sqrt_nr(_varianza(serie))

    fig, ax = plt.subplots(figsize=(11, 4.5))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, titulo, xlabel, "Frecuencia Absoluta")

    ax.bar(centros, freq, width=ancho * 0.88, color=color,
           edgecolor="#0a1220", linewidth=0.9, alpha=0.85, align="center")

    ax.axvline(mu, color=_C["rojo"], linestyle="--",
               linewidth=2.0, label=f"x̄ = {mu:.2f}")
    ax.axvline(mu - sig, color=_C["amarillo"], linestyle=":",
               linewidth=1.4, label=f"−σ = {mu - sig:.2f}")
    ax.axvline(mu + sig, color=_C["amarillo"], linestyle=":",
               linewidth=1.4, label=f"+σ = {mu + sig:.2f}")

    ax.legend(facecolor=_C["fondo"], labelcolor=_C["texto"],
              fontsize=8.5, edgecolor="#1e3a5f")
    ax.text(0.98, 0.95, f"k Sturges = {k}",
            transform=ax.transAxes, color=_C["texto"],
            fontsize=8, ha="right", va="top", family="monospace")
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


# ── III.C: Boxplot mensual (dibujado a mano) ──────────────────────────

def boxplot_mensual(df: pd.DataFrame, col: str, titulo: str) -> str:
    """
    Caja y Bigotes mensual MANUAL.
    Caja: P25–P75; Línea: P50; Bigotes: ±1.5·IQR; Outliers: puntos.
    NO usa ax.boxplot().
    """
    dt_col = df.columns[0]
    df2 = df[[dt_col, col]].copy()
    df2["_mes"] = df2[dt_col].dt.to_period("M")
    periodos = sorted(df2["_mes"].dropna().unique(), key=str)

    meses, series = [], {}
    for p in periodos:
        mask = (df2["_mes"] == p).tolist()
        s = []
        for inc, v in zip(mask, df2[col].tolist()):
            if inc and not _es_nan(v):
                try:
                    s.append(float(v))
                except (TypeError, ValueError):
                    pass
        if s:
            tag = str(p)
            meses.append(tag)
            series[tag] = s

    if not meses:
        return ""

    fig, ax = plt.subplots(figsize=(max(12, len(meses) * 1.1), 5.5))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, titulo, "Mes", col)

    posiciones = list(range(1, len(meses) + 1))

    for pos, tag in zip(posiciones, meses):
        s = series[tag]

        if _LIBS["ac"]:
            ac = _ac_from_serie(s)
            ac.ordenar_por_columna(0, True)
            q1  = ac.percentil(0, 25)
            q2  = ac.mediana(0)
            q3  = ac.percentil(0, 75)
        else:
            q1  = _percentil(s, 25)
            q2  = _percentil(s, 50)
            q3  = _percentil(s, 75)

        iqr     = q3 - q1
        lim_inf = q1 - 1.5 * iqr
        lim_sup = q3 + 1.5 * iqr

        cand_inf = [v for v in s if v >= lim_inf]
        cand_sup = [v for v in s if v <= lim_sup]
        bw_inf = _minimo(cand_inf) if cand_inf else q1
        bw_sup = _maximo(cand_sup) if cand_sup else q3

        # Caja
        rect = mpatches.FancyBboxPatch(
            (pos - 0.36, q1), 0.72, q3 - q1,
            boxstyle="round,pad=0.02",
            facecolor="#0d2e6e", edgecolor=_C["azul"], linewidth=1.6
        )
        ax.add_patch(rect)

        # Mediana
        ax.plot([pos - 0.36, pos + 0.36], [q2, q2],
                color=_C["amarillo"], linewidth=2.5)

        # Bigotes
        for bv in [bw_inf, bw_sup]:
            ax.plot([pos - 0.2, pos + 0.2], [bv, bv],
                    color=_C["cyan"], linewidth=1.4)
        ax.plot([pos, pos], [bw_inf, q1], color=_C["cyan"], linewidth=1.1)
        ax.plot([pos, pos], [q3, bw_sup], color=_C["cyan"], linewidth=1.1)

        # Outliers
        for v in s:
            if v < bw_inf or v > bw_sup:
                ax.scatter(pos, v, color=_C["rojo"], s=9, alpha=0.45, zorder=5)

    ax.set_xticks(posiciones)
    ax.set_xticklabels(meses, rotation=45, color=_C["texto"],
                       fontsize=7.5, ha="right")
    ax.set_xlim(0.3, len(posiciones) + 0.7)
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


# ── III.D: Rosa de los Vientos ────────────────────────────────────────

_RUMBOS_16 = {
    "N":  0.0,   "NNE": 22.5,  "NE": 45.0,   "ENE": 67.5,
    "E": 90.0,   "ESE": 112.5, "SE": 135.0,  "SSE": 157.5,
    "S": 180.0,  "SSW": 202.5, "SW": 225.0,  "WSW": 247.5,
    "W": 270.0,  "WNW": 292.5, "NW": 315.0,  "NNW": 337.5,
}


def rosa_de_vientos(df: pd.DataFrame, titulo: str) -> str:
    """
    Rosa de los Vientos Polar — 16 rumbos de 22.5° c/u.
    Norte en cénit, sentido horario.
    Color según velocidad media del viento en cada rumbo.
    """
    col_dir = "Prevailing Wind Dir"
    col_vel = "Avg Wind Speed - km/h"
    if col_dir not in df.columns:
        return ""

    freq = {r: 0  for r in _RUMBOS_16}
    vel  = {r: [] for r in _RUMBOS_16}

    vels = (df[col_vel].tolist() if col_vel in df.columns
            else [0.0] * len(df))

    for dv, vv in zip(df[col_dir].tolist(), vels):
        if isinstance(dv, str):
            r = dv.strip().upper().replace('"', '')
            if r in freq:
                freq[r] += 1
                if not _es_nan(vv):
                    vel[r].append(float(vv))

    total = sum(freq.values())
    if total == 0:
        return ""

    pct     = {r: freq[r] / total * 100 for r in _RUMBOS_16}
    vel_med = {r: _media(vel[r]) if vel[r] else 0.0 for r in _RUMBOS_16}

    fig = plt.figure(figsize=(7.5, 7.5))
    fig.patch.set_facecolor(_C["fondo"])
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor((0.04, 0.12, 0.25, 0.7))
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.tick_params(colors=_C["texto"], labelsize=7.5)
    ax.grid(color="#ffffff18", linestyle="--", linewidth=0.5)

    ancho = math.radians(22.5) * 0.82
    for rumbo, ang_deg in _RUMBOS_16.items():
        ang = math.radians(ang_deg)
        vm  = vel_med[rumbo]
        color = (_C["azul"]    if vm < 5   else
                 _C["verde"]   if vm < 10  else
                 _C["amarillo"]if vm < 20  else
                 _C["rojo"])
        ax.bar(ang, pct[rumbo], width=ancho, color=color,
               alpha=0.85, edgecolor="#ffffff25", linewidth=0.5)

    leyenda = [
        mpatches.Patch(color=_C["azul"],     label="< 5 km/h"),
        mpatches.Patch(color=_C["verde"],    label="5–10 km/h"),
        mpatches.Patch(color=_C["amarillo"], label="10–20 km/h"),
        mpatches.Patch(color=_C["rojo"],     label="> 20 km/h"),
    ]
    ax.legend(handles=leyenda, loc="lower left", fontsize=7.5,
              facecolor=_C["fondo"], labelcolor=_C["texto"],
              edgecolor="#1e3a5f", bbox_to_anchor=(-0.15, -0.12))
    ax.set_title(titulo, color=_C["primario"], fontsize=10,
                 fontweight="bold", pad=22)
    plt.tight_layout()
    return _fig_to_b64(fig)


# ── III.E: Barras de Pearson ──────────────────────────────────────────

def grafico_pearson(correlaciones: dict) -> str:
    if not correlaciones:
        return ""
    nombres = [d["nombre"]  for d in correlaciones.values()]
    rs      = [d["r"]       for d in correlaciones.values()]
    colores = [_C["verde"] if r >= 0 else _C["rojo"] for r in rs]

    fig, ax = plt.subplots(figsize=(10, max(4, len(nombres) * 0.65)))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, "Correlación de Pearson — 7GT-EEP vs 7GT-UES",
             "r de Pearson", "")

    bars = ax.barh(nombres, rs, color=colores,
                   edgecolor="#1e3a5f", linewidth=0.9,
                   alpha=0.85, height=0.55)
    ax.axvline(0, color="#ffffff35", linewidth=1.2)
    ax.set_xlim(-1.1, 1.1)

    for bar, r in zip(bars, rs):
        xp = bar.get_width() + 0.025 if r >= 0 else bar.get_width() - 0.025
        ax.text(xp, bar.get_y() + bar.get_height() / 2,
                f"{r:+.4f}", va="center",
                ha="left" if r >= 0 else "right",
                color=_C["primario"], fontsize=8.5, family="monospace")

    ax.set_yticklabels(nombres, color=_C["texto"], fontsize=8.5)
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


# ── III.F: Comparativa Temperatura y Humedad (doble estación) ─────────

def grafico_comparativo(df_eep: pd.DataFrame, df_ues: pd.DataFrame,
                         col: str, titulo: str, ylabel: str) -> str:
    """Superpone las dos estaciones en un mismo eje para comparar."""
    dt_eep, dt_ues = df_eep.columns[0], df_ues.columns[0]
    if col not in df_eep.columns or col not in df_ues.columns:
        return ""

    fig, ax = plt.subplots(figsize=(13, 3.8))
    fig.patch.set_facecolor(_C["fondo"])
    _ax_dark(ax, titulo, "Índice temporal", ylabel)

    s_eep = df_eep[col].tolist()
    s_ues = df_ues[col].tolist()
    n = max(len(s_eep), len(s_ues))

    ax.plot(list(range(len(s_eep))), s_eep, color=_C["naranja"],
            linewidth=0.65, alpha=0.8, label="7GT-EEP (San Luis Talpa)")
    ax.plot(list(range(len(s_ues))), s_ues, color=_C["cyan"],
            linewidth=0.65, alpha=0.8, label="7GT-UES (Univ. El Salvador)")

    ax.legend(facecolor=_C["fondo"], labelcolor=_C["texto"],
              fontsize=8.5, edgecolor="#1e3a5f")
    plt.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


# ══════════════════════════════════════════════════════════════════════
# FASE IV — CORRELACIÓN DE PEARSON INTER-ESTACIONAL
# ══════════════════════════════════════════════════════════════════════

def alinear_temporalmente(df_a: pd.DataFrame, df_b: pd.DataFrame):
    """
    Alinea por marca de tiempo exacta usando diccionario O(n).
    Retorna listas de índices paralelos.
    """
    dt_a = df_a.columns[0]
    dt_b = df_b.columns[0]
    idx_a = {ts: i for i, ts in enumerate(df_a[dt_a].tolist())}
    idx_b = {ts: i for i, ts in enumerate(df_b[dt_b].tolist())}
    comunes = []
    for ts, ia in idx_a.items():
        if ts in idx_b:
            comunes.append((ts, ia, idx_b[ts]))
    comunes.sort(key=lambda x: x[0])
    print(f"  {len(comunes):,} timestamps alineados.")
    return [x[1] for x in comunes], [x[2] for x in comunes]


def pearson_manual(sx: list, sy: list) -> float:
    """
    r = Σ[(xi−x̄)(yi−ȳ)] / √[Σ(xi−x̄)² · Σ(yi−ȳ)²]
    Implementación completamente manual — sin scipy ni numpy.corrcoef.
    """
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
    den = sqrt_nr(sq_x * sq_y)
    return num / den if den != 0 else float("nan")


def _interp_pearson(r: float) -> str:
    ar = abs(r) if r == r else 0
    if ar >= 0.9: return "Muy fuerte"
    if ar >= 0.7: return "Fuerte"
    if ar >= 0.5: return "Moderada"
    if ar >= 0.3: return "Débil"
    return "Muy débil / Nula"


def calcular_correlaciones(df_eep: pd.DataFrame,
                            df_ues: pd.DataFrame) -> dict:
    """
    ── FASE IV ──────────────────────────────────────────────────────────
    Pearson para variables clave entre las dos estaciones.
    Motor: C++ pearson_correlation(0,1) si disponible; Python manual si no.
    ─────────────────────────────────────────────────────────────────────
    """
    ia, ib = alinear_temporalmente(df_eep, df_ues)

    VARS = [
        # Bloque A — Interior
        ("Inside Temp - °C",        "Temperatura Interior (°C)"),
        ("Inside Hum - %",          "Humedad Interior (%)"),
        ("Inside Dew Point - °C",   "Punto de Rocío Interior (°C)"),
        ("Inside Wet Bulb - °C",    "Bulbo Húmedo Interior (°C)"),
        ("Inside Heat Index - °C",  "Índice de Calor Interior (°C)"),
        # Bloque B — Barómetro
        ("Barometer - mb",          "Presión Barométrica (mb)"),
        ("Absolute Pressure - mb",  "Presión Absoluta (mb)"),
        # Bloque C — Exterior
        ("Temp - °C",               "Temperatura Exterior (°C)"),
        ("Hum - %",                 "Humedad Exterior (%)"),
        ("Dew Point - °C",          "Punto de Rocío (°C)"),
        ("Wet Bulb - °C",           "Bulbo Húmedo (°C)"),
        ("Avg Wind Speed - km/h",   "Velocidad del Viento (km/h)"),
        ("High Wind Speed - km/h",  "Ráfaga Máxima de Viento (km/h)"),
        ("Wind Run - km",           "Recorrido del Viento (km)"),
        ("Wind Chill - °C",         "Índice de Enfriamiento Eólico (°C)"),
        ("Heat Index - °C",         "Índice de Calor (°C)"),
        ("Thw Index - °C",          "Índice THW (°C)"),
        ("Thsw Index - °C",         "Índice THSW (°C)"),
        ("Solar Rad - W/m^2",       "Radiación Solar (W/m²)"),
        ("High Solar Rad - W/m^2",  "Radiación Solar Pico (W/m²)"),
        ("Solar Energy - Ly",       "Energía Solar (Ly)"),
        ("UV Index",                "Índice UV"),
        ("ET - mm",                 "Evapotranspiración (mm)"),
        ("Rain - mm",               "Precipitación (mm)"),
        ("High Rain Rate - mm",     "Tasa de Lluvia Máxima (mm)"),
        ("Heating Degree Days",     "Grados-Día Calefacción"),
        ("Cooling Degree Days",     "Grados-Día Refrigeración"),
    ]

    vals_eep = {c: df_eep[c].tolist() for c in df_eep.columns}
    vals_ues = {c: df_ues[c].tolist() for c in df_ues.columns}
    res = {}

    for col, nombre in VARS:
        if col not in vals_eep or col not in vals_ues:
            continue
        sx, sy = [], []
        for i_e, i_u in zip(ia, ib):
            xe, yu = vals_eep[col][i_e], vals_ues[col][i_u]
            if not _es_nan(xe) and not _es_nan(yu):
                try:
                    sx.append(float(xe))
                    sy.append(float(yu))
                except (TypeError, ValueError):
                    pass
        if len(sx) < 2:
            continue

        if _LIBS["ac"]:
            datos = np.asarray([[a, b] for a, b in zip(sx, sy)], dtype=np.float64)
            ac = AjusteCurvas()
            ac.establecer_datos(datos)
            r = ac.pearson_correlation(0, 1)
        else:
            r = pearson_manual(sx, sy)

        res[col] = {
            "nombre": nombre, "r": r,
            "r2": r * r if r == r else float("nan"),
            "n": len(sx), "media_eep": _media(sx), "media_ues": _media(sy),
            "interpretacion": _interp_pearson(r),
        }

    return res


# ══════════════════════════════════════════════════════════════════════
# GENERACIÓN DEL DASHBOARD HTML — VERSIÓN PÚBLICO GENERAL (MSN Weather)
# ══════════════════════════════════════════════════════════════════════

# ─── helpers de formato amigable ──────────────────────────────────────

def _v(st: dict, k: str, dec: int = 1, suf: str = "") -> str:
    """Formatea un valor estadístico para consumo general."""
    val = st.get(k)
    if val is None:
        return "—"
    try:
        fv = float(val)
        if fv != fv:          # NaN
            return "—"
        return f"{fv:.{dec}f}{suf}"
    except (TypeError, ValueError):
        return "—"


def _confort_humedad(h: float) -> str:
    if h < 30:  return "Muy seco"
    if h < 50:  return "Agradable"
    if h < 65:  return "Confortable"
    if h < 80:  return "Algo húmedo"
    return "Muy húmedo"


def _nivel_uv(uv: float) -> tuple:
    """Devuelve (etiqueta, color_hex)."""
    if uv < 3:   return ("Bajo",      "#4ade80")
    if uv < 6:   return ("Moderado",  "#fbbf24")
    if uv < 8:   return ("Alto",      "#f97316")
    if uv < 11:  return ("Muy alto",  "#ef4444")
    return ("Extremo", "#a855f7")


def _icono_temp(t: float) -> str:
    if t < 18: return "🧥"
    if t < 24: return "☀️"
    if t < 30: return "🌤️"
    return "🔥"


def _icono_hum(h: float) -> str:
    if h < 40: return "🏜️"
    if h < 65: return "🌿"
    return "💧"


def _mes_label(periodo_str: str) -> str:
    """'2025-02' → 'Feb'"""
    meses = ["Ene","Feb","Mar","Abr","May","Jun",
              "Jul","Ago","Sep","Oct","Nov","Dic"]
    try:
        parts = periodo_str.split("-")
        return meses[int(parts[1]) - 1]
    except Exception:
        return periodo_str


# ─── generación de filas mensuales para el mini-gráfico de barras ────

def _barras_mensuales_html(mensual: dict, col_key: str = "media",
                            color: str = "#38bdf8") -> str:
    """
    Genera un mini gráfico de barras horizontales en HTML puro
    a partir del dict de estadísticos mensuales.
    """
    if not mensual:
        return "<p style='color:#64748b;font-size:.8rem'>Sin datos mensuales</p>"

    items = [(k, v) for k, v in mensual.items() if col_key in v]
    if not items:
        return ""

    vals  = [v[col_key] for _, v in items]
    vmin  = _minimo(vals)
    vmax  = _maximo(vals)
    rng   = (vmax - vmin) if (vmax - vmin) > 0 else 1.0

    rows = ""
    for periodo, datos in items:
        val  = datos.get(col_key, 0)
        pct  = max(4, int((val - vmin) / rng * 100))
        lbl  = _mes_label(periodo)
        rows += f"""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
          <span style="width:28px;font-size:.72rem;color:#94a3b8;text-align:right">{lbl}</span>
          <div style="flex:1;background:rgba(255,255,255,.06);border-radius:4px;height:8px;overflow:hidden">
            <div style="width:{pct}%;height:100%;background:{color};border-radius:4px;
                        transition:width .6s ease"></div>
          </div>
          <span style="width:40px;font-size:.72rem;color:#e2e8f0;text-align:right">{val:.1f}</span>
        </div>"""
    return rows


# ─── main dashboard builder ───────────────────────────────────────────

def _tabla_comparativa(st_e: dict, st_u: dict,
                        col: str, nombre: str) -> str:
    def f(d, k):
        v = d.get(k)
        if v is None:
            return "N/D"
        if k == "n":
            return str(int(v))
        try:
            return f"{float(v):.4f}" if float(v) == float(v) else "N/D"
        except (TypeError, ValueError):
            return "N/D"

    filas = [
        ("N muestral", "n"), ("Media (x̄)", "media"),
        ("Desv. Est. (σ)", "desv_estandar"), ("Varianza (s²)", "varianza"),
        ("Moda", "moda"), ("Máximo", "maximo"), ("Mínimo", "minimo"),
        ("P10", "p10"), ("P25 (Q1)", "p25"), ("Mediana (P50)", "p50"),
        ("P75 (Q3)", "p75"), ("P90", "p90"),
        ("IQR", "riq"), ("IC 90% inf", "ic_inf"), ("IC 90% sup", "ic_sup"),
    ]
    rows = "".join(
        f"<tr><td class='lbl'>{lbl}</td>"
        f"<td class='eep'>{f(st_e, k)}</td>"
        f"<td class='ues'>{f(st_u, k)}</td></tr>"
        for lbl, k in filas
    )
    return f"""
    <div class="tbl-card">
      <h3 class="tbl-h">{nombre}</h3>
      <table class="st"><thead><tr>
        <th>Métrica</th><th class="th-eep">7GT-EEP</th>
        <th class="th-ues">7GT-UES</th>
      </tr></thead><tbody>{rows}</tbody></table>
    </div>"""


def _filas_comparativa(st_eep: dict, st_ues: dict) -> str:
    """Genera filas HTML de comparativa entre estaciones sin f-strings anidados."""
    PARES = [
        ("Temp - °C",             "🌡️ Temperatura media (°C)"),
        ("Hum - %",               "💧 Humedad media (%)"),
        ("Barometer - mb",        "🧭 Presión (mb)"),
        ("Avg Wind Speed - km/h", "💨 Viento medio (km/h)"),
        ("Solar Rad - W/m^2",     "☀️ Radiación solar (W/m²)"),
        ("Rain - mm",             "🌧️ Lluvia media (mm)"),
    ]
    rows = []
    for col, nom in PARES:
        ve = _v(st_eep.get(col) or {}, "media", 1)
        vu = _v(st_ues.get(col) or {}, "media", 1)
        rows.append(
            f'<div class="compare-row">'
            f'<span class="compare-lbl">{nom}</span>'
            f'<span class="compare-val v-eep">{ve}</span>'
            f'<span class="compare-val v-ues">{vu}</span>'
            f'<span></span></div>'
        )
    return "\n".join(rows)


def generar_dashboard_publico(st_eep: dict, st_ues: dict, figs: dict,
                               correlaciones: dict,
                               st_mensual_ues: dict = None,
                               nombre: str = "dashboard_proyecto_climatico.html") -> str:
    """
    Dashboard estilo MSN Weather — público general.
    Muestra los datos estadísticos de forma amigable y visual.
    """
    if st_mensual_ues is None:
        st_mensual_ues = {}

    # ── Extraer estadísticos clave ────────────────────────────────────
    T   = st_ues.get("Temp - °C",             {})
    H   = st_ues.get("Hum - %",               {})
    B   = st_ues.get("Barometer - mb",         {})
    UV  = st_ues.get("UV Index",               {})
    SOL = st_ues.get("Solar Rad - W/m^2",      {})
    VTO = st_ues.get("Avg Wind Speed - km/h",  {})
    LL  = st_ues.get("Rain - mm",              {})
    HI  = st_ues.get("Heat Index - °C",        {})
    DP  = st_ues.get("Dew Point - °C",         {})
    ET  = st_ues.get("ET - mm",                {})
    THW = st_ues.get("Thw Index - °C",         {})

    # Valores numéricos para lógica de íconos / etiquetas
    try:
        temp_media   = float(T.get("media",   25.0) or 25.0)
        hum_media    = float(H.get("media",   70.0) or 70.0)
        uv_media     = float(UV.get("media",   4.0) or 4.0)
        lluvia_total = float(LL.get("p90",     0.0) or 0.0)
    except (TypeError, ValueError):
        temp_media, hum_media, uv_media, lluvia_total = 25.0, 70.0, 4.0, 0.0

    uv_lbl, uv_color = _nivel_uv(uv_media)
    hum_confort      = _confort_humedad(hum_media)

    # ── Gráficos como <img> ───────────────────────────────────────────
    def img_tag(k, style=""):
        b = figs.get(k, "")
        if not b:
            return '<div class="no-img">Datos no disponibles</div>'
        return f'<img src="data:image/png;base64,{b}" class="chart-img" style="{style}" />'

    # ── Barras mensuales (temperatura) ────────────────────────────────
    barras_temp = _barras_mensuales_html(
        st_mensual_ues, "media", "#f87171")
    barras_hum  = _barras_mensuales_html(
        st_mensual_ues if st_mensual_ues else {},
        "media", "#38bdf8")

    # Estadísticos mensuales de humedad (si disponible)
    # Se reutilizan los mismos keys pero se espera que main() los pase
    # como st_mensual_ues; para humedad se usaría otro dict si se pasa.

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>El Tiempo en El Salvador · Estaciones 7GT-EEP &amp; 7GT-UES</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ════════════════════════════════════════
   VARIABLES & RESET
════════════════════════════════════════ */
:root {{
  --bg:        #06101f;
  --bg2:       #0c1a31;
  --card:      rgba(255,255,255,.055);
  --card-hover:rgba(255,255,255,.09);
  --brd:       rgba(255,255,255,.10);
  --brd2:      rgba(255,255,255,.06);
  --tx:        #f1f5f9;
  --tx2:       #94a3b8;
  --tx3:       #64748b;
  --blue:      #38bdf8;
  --blue2:     #0ea5e9;
  --warm:      #f87171;
  --amber:     #fbbf24;
  --green:     #4ade80;
  --purple:    #a78bfa;
  --r:         'Outfit', sans-serif;
  --mono:      'DM Mono', monospace;
}}
*, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0 }}
html {{ scroll-behavior:smooth }}
body {{
  font-family: var(--r);
  background: var(--bg);
  color: var(--tx);
  min-height: 100vh;
  overflow-x: hidden;
}}

/* ════════════════════════════════════════
   FONDO ANIMADO
════════════════════════════════════════ */
.sky {{
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(ellipse 90% 55% at 15% 8%,  rgba(56,189,248,.12) 0%, transparent 65%),
    radial-gradient(ellipse 70% 50% at 85% 90%,  rgba(99,102,241,.09) 0%, transparent 60%),
    linear-gradient(175deg, #06101f 0%, #0c1a31 50%, #060f1e 100%);
}}
.sky-glow {{
  position: fixed; top: -200px; left: 50%;
  transform: translateX(-50%);
  width: 900px; height: 500px; z-index: 0; pointer-events: none;
  background: radial-gradient(ellipse, rgba(14,165,233,.08) 0%, transparent 70%);
  animation: glow-pulse 8s ease-in-out infinite alternate;
}}
@keyframes glow-pulse {{
  0%   {{ opacity:.5; transform:translateX(-50%) scale(.95) }}
  100% {{ opacity:1;  transform:translateX(-50%) scale(1.05) }}
}}

/* Stars */
.stars-layer {{
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image:
    radial-gradient(circle, rgba(255,255,255,.55) 1px, transparent 1px),
    radial-gradient(circle, rgba(255,255,255,.25) 1px, transparent 1px);
  background-size: 320px 320px, 160px 160px;
  background-position: 0 0, 90px 70px;
  animation: twinkle 11s ease-in-out infinite alternate;
}}
@keyframes twinkle {{
  0%   {{ opacity:.35 }}
  100% {{ opacity:.85 }}
}}

/* ════════════════════════════════════════
   LAYOUT
════════════════════════════════════════ */
.page {{
  position: relative; z-index: 1;
  max-width: 1200px; margin: 0 auto;
  padding: 0 24px 100px;
}}

/* ════════════════════════════════════════
   HEADER
════════════════════════════════════════ */
header {{
  display: flex; justify-content: space-between; align-items: flex-end;
  padding: 48px 0 32px;
  border-bottom: 1px solid var(--brd2);
  animation: slide-down .8s ease both;
}}
@keyframes slide-down {{
  from {{ opacity:0; transform:translateY(-20px) }}
  to   {{ opacity:1; transform:none }}
}}
.hdr-loc {{
  display: flex; flex-direction: column; gap: 6px;
}}
.loc-line {{
  display: flex; align-items: center; gap: 8px;
  font-size: .78rem; color: var(--tx2);
  letter-spacing: .5px;
}}
.loc-pin {{
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--blue);
  box-shadow: 0 0 10px var(--blue);
  animation: pin-pulse 2.5s ease-in-out infinite;
}}
@keyframes pin-pulse {{
  0%,100% {{ transform:scale(1); opacity:1 }}
  50%      {{ transform:scale(1.6); opacity:.6 }}
}}
.city-name {{
  font-size: clamp(22px,4vw,42px);
  font-weight: 700; line-height: 1.1;
  background: linear-gradient(120deg, #f1f5f9 0%, var(--blue) 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.period-tag {{
  display: inline-flex; align-items: center; gap: 6px;
  background: rgba(56,189,248,.12); border: 1px solid rgba(56,189,248,.25);
  border-radius: 100px; padding: 3px 12px;
  font-size: .72rem; color: var(--blue); letter-spacing: .5px;
}}
.hdr-clock {{
  text-align: right;
}}
.clock-time {{
  font-family: var(--mono); font-size: clamp(26px,3.5vw,38px);
  font-weight: 500; color: var(--tx);
  text-shadow: 0 0 30px rgba(56,189,248,.3);
}}
.clock-date {{
  font-size: .76rem; color: var(--tx2); margin-top: 4px;
}}

/* ════════════════════════════════════════
   SECCIÓN HERO — TEMPERATURA
════════════════════════════════════════ */
.hero {{
  display: grid; grid-template-columns: 1fr auto;
  gap: 32px; align-items: end;
  padding: 52px 0 40px;
  animation: slide-down .9s ease .1s both;
}}
.hero-temp {{
  display: flex; align-items: flex-start; gap: 20px;
}}
.temp-big {{
  font-size: clamp(72px, 12vw, 110px);
  font-weight: 300; line-height: 1;
  color: var(--tx);
  text-shadow: 0 0 60px rgba(248,113,113,.25);
}}
.temp-meta {{
  display: flex; flex-direction: column; gap: 4px;
  padding-top: 18px;
}}
.temp-icon {{ font-size: 1.8rem; }}
.temp-feel {{ font-size: 1rem; color: var(--tx2); }}
.temp-range {{
  font-size: .9rem; font-weight: 600; color: var(--tx);
  margin-top: 4px;
}}
.temp-range .hi {{ color: var(--warm); }}
.temp-range .lo {{ color: var(--blue); }}
.hero-station {{
  text-align: right; padding-bottom: 12px;
}}
.station-id {{
  font-family: var(--mono); font-size: .7rem;
  color: var(--tx3); letter-spacing: 1.5px;
}}
.station-desc {{
  font-size: .8rem; color: var(--tx2); margin-top: 4px;
}}

/* ════════════════════════════════════════
   SCROLL 24h (temperatura histórica típica)
════════════════════════════════════════ */
.scroll-panel {{
  background: var(--card); border: 1px solid var(--brd);
  border-radius: 20px; padding: 22px 24px;
  backdrop-filter: blur(16px);
  animation: fade-up .8s ease .2s both;
}}
@keyframes fade-up {{
  from {{ opacity:0; transform:translateY(24px) }}
  to   {{ opacity:1; transform:none }}
}}
.panel-label {{
  font-size: .68rem; font-weight: 600; letter-spacing: 2px;
  text-transform: uppercase; color: var(--tx2); margin-bottom: 18px;
}}
.h-scroll {{
  display: flex; gap: 6px; overflow-x: auto;
  padding-bottom: 6px; scrollbar-width: thin;
  scrollbar-color: var(--brd) transparent;
}}
.h-item {{
  display: flex; flex-direction: column; align-items: center;
  min-width: 64px; gap: 8px;
  padding: 12px 8px; border-radius: 12px;
  background: rgba(255,255,255,.04);
  border: 1px solid transparent;
  transition: background .2s, border-color .2s;
  cursor: default;
}}
.h-item:hover {{
  background: rgba(56,189,248,.08);
  border-color: rgba(56,189,248,.2);
}}
.h-item.active {{
  background: rgba(56,189,248,.14);
  border-color: rgba(56,189,248,.35);
}}
.h-time  {{ font-size: .7rem; color: var(--tx2); }}
.h-icon  {{ font-size: 1.3rem; }}
.h-val   {{ font-size: 1rem; font-weight: 600; color: var(--tx); }}
.h-sub   {{ font-size: .65rem; color: var(--tx3); }}

/* ════════════════════════════════════════
   GRID DE MÉTRICAS
════════════════════════════════════════ */
.metrics-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 14px;
  animation: fade-up .8s ease .3s both;
}}
.metric-card {{
  background: var(--card); border: 1px solid var(--brd);
  border-radius: 18px; padding: 20px 22px;
  backdrop-filter: blur(16px);
  transition: background .25s, transform .25s, border-color .25s;
  position: relative; overflow: hidden;
}}
.metric-card::after {{
  content: ''; position: absolute;
  top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.15), transparent);
}}
.metric-card:hover {{
  background: var(--card-hover);
  transform: translateY(-3px);
  border-color: rgba(255,255,255,.18);
}}
.m-icon-row {{
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}}
.m-icon   {{ font-size: 1.4rem; }}
.m-badge  {{
  font-size: .62rem; padding: 2px 8px; border-radius: 100px;
  font-weight: 600; letter-spacing: .5px;
}}
.m-label  {{ font-size: .68rem; color: var(--tx2); margin-bottom: 4px; letter-spacing: .3px; }}
.m-value  {{ font-size: 1.9rem; font-weight: 600; line-height: 1.1; color: var(--tx); }}
.m-unit   {{ font-size: .85rem; font-weight: 400; color: var(--tx2); margin-left: 2px; }}
.m-sub    {{ font-size: .72rem; color: var(--tx2); margin-top: 6px; }}

/* ════════════════════════════════════════
   TENDENCIA MENSUAL
════════════════════════════════════════ */
.tendency-grid {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  animation: fade-up .8s ease .4s both;
}}
.tend-card {{
  background: var(--card); border: 1px solid var(--brd);
  border-radius: 18px; padding: 22px 24px;
  backdrop-filter: blur(16px);
}}
.tend-title {{
  font-size: .68rem; font-weight: 600; letter-spacing: 1.8px;
  text-transform: uppercase; color: var(--tx2); margin-bottom: 18px;
}}

/* ════════════════════════════════════════
   GRÁFICOS
════════════════════════════════════════ */
.chart-section {{
  animation: fade-up .8s ease .45s both;
}}
.chart-card {{
  background: var(--card); border: 1px solid var(--brd);
  border-radius: 18px; padding: 20px;
  backdrop-filter: blur(16px); overflow: hidden;
}}
.chart-title {{
  font-size: .76rem; font-weight: 600; color: var(--tx2);
  letter-spacing: 1.5px; text-transform: uppercase;
  margin-bottom: 14px;
}}
.chart-img  {{ width:100%; border-radius:8px; display:block; }}
.no-img     {{ color:var(--tx3); font-size:.8rem; text-align:center; padding:32px; }}

/* ════════════════════════════════════════
   WIND ROSE
════════════════════════════════════════ */
.wind-section {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  animation: fade-up .8s ease .5s both;
}}

/* ════════════════════════════════════════
   COMPARATIVA ESTACIONES
════════════════════════════════════════ */
.compare-card {{
  background: var(--card); border: 1px solid var(--brd);
  border-radius: 18px; padding: 22px 24px;
  backdrop-filter: blur(16px);
  animation: fade-up .8s ease .55s both;
}}
.compare-row {{
  display: flex; align-items: center;
  padding: 10px 0; border-bottom: 1px solid var(--brd2);
  gap: 16px;
}}
.compare-row:last-child {{ border-bottom: none; }}
.compare-lbl  {{ flex: 1; font-size: .82rem; color: var(--tx2); }}
.compare-val  {{ font-family: var(--mono); font-size: .88rem; font-weight: 500; }}
.v-eep        {{ color: #f59e0b; }}
.v-ues        {{ color: var(--blue); }}

/* ════════════════════════════════════════
   SECTION SPACERS
════════════════════════════════════════ */
.section {{ margin-bottom: 20px; }}
.sec-head {{
  display: flex; align-items: center; gap: 12px;
  font-size: .68rem; font-weight: 700; letter-spacing: 2.5px;
  text-transform: uppercase; color: var(--tx3);
  margin: 44px 0 16px;
}}
.sec-head::after {{
  content: ''; height: 1px; flex: 1;
  background: linear-gradient(90deg, var(--brd), transparent);
}}

/* ════════════════════════════════════════
   PILL / UV BAR
════════════════════════════════════════ */
.uv-bar {{
  height: 6px; border-radius: 3px; margin-top: 8px;
  background: linear-gradient(90deg,
    #4ade80 0%, #fbbf24 33%, #f97316 55%, #ef4444 77%, #a855f7 100%);
  position: relative; overflow: visible;
}}
.uv-cursor {{
  position: absolute; top: -3px; width: 12px; height: 12px;
  border-radius: 50%; background: #fff;
  box-shadow: 0 0 8px rgba(0,0,0,.6);
  transform: translateX(-50%);
  transition: left .5s ease;
}}

/* ════════════════════════════════════════
   FOOTER
════════════════════════════════════════ */
footer {{
  border-top: 1px solid var(--brd2);
  padding: 20px 0; text-align: center;
  font-size: .72rem; color: var(--tx3);
  line-height: 1.8; margin-top: 60px;
}}
footer b {{ color: var(--tx2); font-weight: 500; }}

/* ════════════════════════════════════════
   RESPONSIVE
════════════════════════════════════════ */
@media (max-width:720px) {{
  .hero             {{ grid-template-columns: 1fr; }}
  .hero-station     {{ text-align:left; padding-top:0; }}
  .tendency-grid    {{ grid-template-columns: 1fr; }}
  .wind-section     {{ grid-template-columns: 1fr; }}
  .metrics-grid     {{ grid-template-columns: repeat(2,1fr); }}
  header            {{ flex-direction:column; align-items:flex-start; gap:16px; }}
  .hdr-clock        {{ text-align:left; }}
}}
@media (max-width:480px) {{
  .metrics-grid     {{ grid-template-columns: 1fr 1fr; }}
  .page             {{ padding:0 16px 80px; }}
}}
</style>
</head>
<body>

<div class="sky"></div>
<div class="sky-glow"></div>
<div class="stars-layer"></div>

<div class="page">

<!-- ══ HEADER ══════════════════════════════════════════════════════ -->
<header>
  <div class="hdr-loc">
    <div class="loc-line">
      <span class="loc-pin"></span>
      <span>El Salvador &nbsp;·&nbsp; 7GT-UES: Univ. El Salvador · 7GT-EEP: San Luis Talpa</span>
    </div>
    <h1 class="city-name">El Tiempo en El Salvador</h1>
    <span class="period-tag">📅 Registro Feb 2025 – 2026</span>
  </div>
  <div class="hdr-clock">
    <div class="clock-time" id="clk">--:--</div>
    <div class="clock-date" id="clkd">—</div>
  </div>
</header>

<!-- ══ HERO TEMPERATURA ═════════════════════════════════════════════ -->
<div class="hero section">
  <div class="hero-temp">
    <div class="temp-big">{_v(T, 'media', 0)}°</div>
    <div class="temp-meta">
      <span class="temp-icon">{_icono_temp(temp_media)}</span>
      <span style="font-size:.95rem;color:var(--tx2)">Temperatura típica</span>
      <span class="temp-feel">Sensación {_v(HI, 'media', 0)}°C</span>
      <span class="temp-range">
        <span class="hi">▲ {_v(T, 'maximo', 0)}°</span> &nbsp;
        <span class="lo">▼ {_v(T, 'minimo', 0)}°</span>
      </span>
    </div>
  </div>
  <div class="hero-station">
    <div class="station-id">7GT-UES / 7GT-EEP</div>
    <div class="station-desc">WeatherLink Pro · UES San Salvador · San Luis Talpa</div>
  </div>
</div>

<!-- ══ SCROLL 24h — distribución horaria típica ══════════════════════ -->
<div class="scroll-panel section">
  <div class="panel-label">🌡️ Distribución de temperatura — rango habitual</div>
  <div class="h-scroll">
    <div class="h-item active">
      <span class="h-time">Madrugada</span>
      <span class="h-icon">🌙</span>
      <span class="h-val">{_v(T,'p10',0)}°</span>
      <span class="h-sub">Mín típica</span>
    </div>
    <div class="h-item">
      <span class="h-time">Mañana</span>
      <span class="h-icon">🌅</span>
      <span class="h-val">{_v(T,'p25',0)}°</span>
      <span class="h-sub">Fresco</span>
    </div>
    <div class="h-item">
      <span class="h-time">Mediodía</span>
      <span class="h-icon">☀️</span>
      <span class="h-val">{_v(T,'p75',0)}°</span>
      <span class="h-sub">Cálido</span>
    </div>
    <div class="h-item">
      <span class="h-time">Tarde</span>
      <span class="h-icon">🌤️</span>
      <span class="h-val">{_v(T,'p90',0)}°</span>
      <span class="h-sub">Máx típica</span>
    </div>
    <div class="h-item">
      <span class="h-time">Promedio</span>
      <span class="h-icon">🌡️</span>
      <span class="h-val">{_v(T,'media',0)}°</span>
      <span class="h-sub">Del día</span>
    </div>
    <div class="h-item">
      <span class="h-time">Sensación</span>
      <span class="h-icon">🤒</span>
      <span class="h-val">{_v(HI,'media',0)}°</span>
      <span class="h-sub">Índice calor</span>
    </div>
    <div class="h-item">
      <span class="h-time">Rocío</span>
      <span class="h-icon">💧</span>
      <span class="h-val">{_v(DP,'media',0)}°</span>
      <span class="h-sub">Punto rocío</span>
    </div>
    <div class="h-item">
      <span class="h-time">Registro</span>
      <span class="h-icon">📈</span>
      <span class="h-val">{_v(T,'maximo',0)}°</span>
      <span class="h-sub">Absoluto</span>
    </div>
  </div>
</div>

<!-- ══ MÉTRICAS ══════════════════════════════════════════════════════ -->
<div class="sec-head">Condiciones habituales</div>

<div class="metrics-grid section">

  <!-- Viento -->
  <div class="metric-card">
    <div class="m-icon-row">
      <span class="m-icon">💨</span>
      <span class="m-badge" style="background:rgba(56,189,248,.15);color:var(--blue)">km/h</span>
    </div>
    <div class="m-label">Viento</div>
    <div class="m-value">{_v(VTO,'media',0)}<span class="m-unit">km/h</span></div>
    <div class="m-sub">Ráfagas hasta {_v(VTO,'p90',0)} km/h</div>
  </div>

  <!-- Humedad -->
  <div class="metric-card">
    <div class="m-icon-row">
      <span class="m-icon">{_icono_hum(hum_media)}</span>
      <span class="m-badge" style="background:rgba(99,102,241,.15);color:#a5b4fc">{hum_confort}</span>
    </div>
    <div class="m-label">Humedad</div>
    <div class="m-value">{_v(H,'media',0)}<span class="m-unit">%</span></div>
    <div class="m-sub">Punto de rocío {_v(DP,'media',1)}°C</div>
  </div>

  <!-- Presión -->
  <div class="metric-card">
    <div class="m-icon-row">
      <span class="m-icon">🧭</span>
      <span class="m-badge" style="background:rgba(74,222,128,.12);color:var(--green)">mb</span>
    </div>
    <div class="m-label">Presión atmosférica</div>
    <div class="m-value">{_v(B,'media',0)}<span class="m-unit">mb</span></div>
    <div class="m-sub">Varía entre {_v(B,'minimo',0)} – {_v(B,'maximo',0)} mb</div>
  </div>

  <!-- UV -->
  <div class="metric-card">
    <div class="m-icon-row">
      <span class="m-icon">🔆</span>
      <span class="m-badge" style="background:rgba(251,191,36,.15);color:{uv_color}">{uv_lbl}</span>
    </div>
    <div class="m-label">Índice UV</div>
    <div class="m-value">{_v(UV,'media',1)}</div>
    <div class="uv-bar">
      <div class="uv-cursor" style="left:{min(int(uv_media/11*100),100)}%"></div>
    </div>
    <div class="m-sub" style="margin-top:10px">Radiación solar {_v(SOL,'media',0)} W/m²</div>
  </div>

  <!-- Lluvia -->
  <div class="metric-card">
    <div class="m-icon-row">
      <span class="m-icon">🌧️</span>
      <span class="m-badge" style="background:rgba(56,189,248,.12);color:var(--blue)">mm</span>
    </div>
    <div class="m-label">Precipitación</div>
    <div class="m-value">{_v(LL,'media',1)}<span class="m-unit">mm</span></div>
    <div class="m-sub">Días con más lluvia: hasta {_v(LL,'p90',0)} mm</div>
  </div>

  <!-- Evapotranspiración -->
  <div class="metric-card">
    <div class="m-icon-row">
      <span class="m-icon">🌿</span>
      <span class="m-badge" style="background:rgba(74,222,128,.10);color:var(--green)">mm</span>
    </div>
    <div class="m-label">Evapotranspiración</div>
    <div class="m-value">{_v(ET,'media',2)}<span class="m-unit">mm</span></div>
    <div class="m-sub">Indica qué tanta agua pierde la vegetación</div>
  </div>

</div>

<!-- ══ TENDENCIA MENSUAL ════════════════════════════════════════════ -->
<div class="sec-head">Comportamiento mensual</div>

<div class="tendency-grid section">
  <div class="tend-card">
    <div class="tend-title">🌡️ Temperatura promedio por mes (°C)</div>
    {barras_temp if barras_temp else '<p style="color:var(--tx3);font-size:.8rem">Sin datos mensuales</p>'}
  </div>
  <div class="tend-card">
    <div class="tend-title">📊 Evolución histórica de temperatura</div>
    {f'<img src="data:image/png;base64,{figs.get("serie_temp_ues","")}" class="chart-img" />' if figs.get("serie_temp_ues") else '<div class="no-img">Sin gráfico</div>'}
  </div>
</div>

<!-- ══ GRÁFICOS DE VIENTO ═══════════════════════════════════════════ -->
<div class="sec-head">Rosa de los vientos</div>

<div class="wind-section section">
  <div class="chart-card">
    <div class="chart-title">🌬️ De dónde sopla el viento — Estación EEP</div>
    {img_tag('wind_eep')}
  </div>
  <div class="chart-card">
    <div class="chart-title">🌬️ De dónde sopla el viento — Estación UES</div>
    {img_tag('wind_ues')}
  </div>
</div>

<!-- ══ EVOLUCIÓN TEMPERATURA ════════════════════════════════════════ -->
<div class="sec-head">Comparativa entre estaciones</div>

<div class="section">
  <div class="chart-card">
    <div class="chart-title">🌡️ Temperatura — Estación EEP (amarillo) vs UES (celeste)</div>
    {img_tag('comp_temp')}
  </div>
</div>

<!-- ══ COMPARATIVA EEP vs UES ═══════════════════════════════════════ -->
<div class="compare-card section">
  <div class="panel-label" style="margin-bottom:14px">
    📍 Diferencias entre las dos estaciones — UES (San Salvador) vs EEP (San Luis Talpa)
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,auto) 1fr;
              font-size:.7rem;color:var(--tx3);gap:0 16px;
              margin-bottom:10px;padding-bottom:6px;
              border-bottom:1px solid var(--brd2)">
    <span>Dato</span>
    <span style="color:#f59e0b">EEP</span>
    <span style="color:var(--blue)">UES</span>
    <span></span>
  </div>
  {_filas_comparativa(st_eep, st_ues)}
</div>

<!-- ══ HUMEDAD — serie temporal ═════════════════════════════════════ -->
<div class="sec-head">Humedad y presión</div>
<div class="section" style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
  <div class="chart-card">
    <div class="chart-title">💧 Humedad a lo largo del tiempo</div>
    {img_tag('serie_hum_ues')}
  </div>
  <div class="chart-card">
    <div class="chart-title">🧭 Presión atmosférica</div>
    {img_tag('serie_bar_ues')}
  </div>
</div>

</div><!-- /page -->

<!-- ══ FOOTER ════════════════════════════════════════════════════════ -->
<footer>
  <b>Estación 7GT-UES · Universidad de El Salvador, San Salvador</b><br>
  <b>Estación 7GT-EEP · San Luis Talpa, La Paz, El Salvador</b><br>
  Datos recopilados con WeatherLink Pro · Feb 2025 – 2026<br>
  Análisis estadístico elaborado por el equipo de Métodos Numéricos
</footer>

<script>
(function() {{
  var dias = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
  var meses = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
  function pad(n){{ return n < 10 ? '0'+n : n; }}
  function tick() {{
    var d = new Date();
    document.getElementById('clk').textContent =
      pad(d.getHours()) + ':' + pad(d.getMinutes());
    document.getElementById('clkd').textContent =
      dias[d.getDay()] + ', ' + d.getDate() + ' ' + meses[d.getMonth()] + ' ' + d.getFullYear();
  }}
  tick();
  setInterval(tick, 30000);
}})();
</script>
</body>
</html>"""

    with open(nombre, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  [OK] Dashboard público → {nombre}")
    return nombre


def generar_dashboard(st_eep: dict, st_ues: dict, figs: dict,
                       correlaciones: dict,
                       nombre: str = "dashboard_proyecto_climatico.html") -> str:

    VARS_DISPLAY = [
        # Bloque A — Interior
        ("Inside Temp - °C",        "🏠 Temperatura Interior (°C)"),
        ("High Inside Temp - °C",   "🏠 Temp. Interior Máx (°C)"),
        ("Low Inside Temp - °C",    "🏠 Temp. Interior Mín (°C)"),
        ("Inside Hum - %",          "🏠 Humedad Interior (%)"),
        ("Inside Dew Point - °C",   "🏠 Rocío Interior (°C)"),
        ("Inside Wet Bulb - °C",    "🏠 Bulbo Húmedo Interior (°C)"),
        ("Inside Heat Index - °C",  "🏠 Índice Calor Interior (°C)"),
        # Bloque B — Barómetro
        ("Barometer - mb",          "🧭 Presión Barométrica (mb)"),
        ("High Bar - mb",           "🧭 Presión Máx (mb)"),
        ("Low Bar - mb",            "🧭 Presión Mín (mb)"),
        ("Absolute Pressure - mb",  "🧭 Presión Absoluta (mb)"),
        # Bloque C — Exterior
        ("Temp - °C",               "🌡️ Temperatura Exterior (°C)"),
        ("High Temp - °C",          "🌡️ Temp. Exterior Máx (°C)"),
        ("Low Temp - °C",           "🌡️ Temp. Exterior Mín (°C)"),
        ("Hum - %",                 "💧 Humedad Exterior (%)"),
        ("High Hum - %",            "💧 Humedad Máx (%)"),
        ("Low Hum - %",             "💧 Humedad Mín (%)"),
        ("Dew Point - °C",          "🌫️ Punto de Rocío (°C)"),
        ("High Dew Point - °C",     "🌫️ Rocío Máx (°C)"),
        ("Low Dew Point - °C",      "🌫️ Rocío Mín (°C)"),
        ("Wet Bulb - °C",           "💧 Bulbo Húmedo (°C)"),
        ("High Wet Bulb - °C",      "💧 Bulbo Húmedo Máx (°C)"),
        ("Low Wet Bulb - °C",       "💧 Bulbo Húmedo Mín (°C)"),
        ("Avg Wind Speed - km/h",   "💨 Velocidad Viento (km/h)"),
        ("High Wind Speed - km/h",  "💨 Ráfaga Máxima (km/h)"),
        ("Wind Run - km",           "💨 Recorrido Viento (km)"),
        ("Wind Chill - °C",         "🥶 Sensación Eólica (°C)"),
        ("Low Wind Chill - °C",     "🥶 Sensación Eólica Mín (°C)"),
        ("Heat Index - °C",         "🔥 Índice de Calor (°C)"),
        ("High Heat Index - °C",    "🔥 Índice Calor Máx (°C)"),
        ("Thw Index - °C",          "🌡️ Índice THW (°C)"),
        ("High Thw Index - °C",     "🌡️ Índice THW Máx (°C)"),
        ("Low Thw Index - °C",      "🌡️ Índice THW Mín (°C)"),
        ("Thsw Index - °C",         "🌡️ Índice THSW (°C)"),
        ("High Thsw Index - °C",    "🌡️ Índice THSW Máx (°C)"),
        ("Low Thsw Index - °C",     "🌡️ Índice THSW Mín (°C)"),
        ("ET - mm",                 "🌿 Evapotranspiración (mm)"),
        ("Rain - mm",               "🌧️ Precipitación (mm)"),
        ("High Rain Rate - mm",     "🌧️ Tasa Lluvia Máx (mm)"),
        ("Solar Rad - W/m^2",       "☀️ Radiación Solar (W/m²)"),
        ("High Solar Rad - W/m^2",  "☀️ Radiación Solar Máx (W/m²)"),
        ("Solar Energy - Ly",       "☀️ Energía Solar (Ly)"),
        ("UV Index",                "🔆 Índice UV"),
        ("High UV Index",           "🔆 Índice UV Máx"),
        ("UV Dose - MEDs",          "🔆 Dosis UV (MEDs)"),
        ("Heating Degree Days",     "🏭 Grados-Día Calefacción"),
        ("Cooling Degree Days",     "❄️ Grados-Día Refrigeración"),
    ]

    tablas = "".join(
        _tabla_comparativa(st_eep.get(col, {}), st_ues.get(col, {}), col, nom)
        for col, nom in VARS_DISPLAY
    )

    filas_corr = ""
    for d in correlaciones.values():
        r = d["r"]
        if abs(r) >= 0.7:
            cls = "cf"
        elif abs(r) >= 0.4:
            cls = "cm"
        else:
            cls = "cd"
        filas_corr += (
            f"<tr><td>{d['nombre']}</td>"
            f"<td class='{cls}'>{r:+.6f}</td>"
            f"<td>{d.get('r2', float('nan')):.4f}</td>"
            f"<td>{d['interpretacion']}</td>"
            f"<td>{d['n']:,}</td></tr>"
        )

    def img(k, caption=""):
        b = figs.get(k, "")
        inner = (f'<img src="data:image/png;base64,{b}" class="plt" />'
                 if b else '<p class="nd">Gráfico no disponible</p>')
        if caption:
            inner += f'<p class="cap">{caption}</p>'
        return inner

    # Lee el JSON de estadísticos clave para las tarjetas KPI
    def kpi(st, k, dec=2):
        v = st.get(k)
        if v is None or _es_nan(float(v) if v else float("nan")):
            return "—"
        return f"{float(v):.{dec}f}"

    st_temp_ues = st_ues.get("Temp - °C", {})
    st_hum_ues  = st_ues.get("Hum - %", {})
    st_bar_ues  = st_ues.get("Barometer - mb", {})
    st_sol_ues  = st_ues.get("Solar Rad - W/m^2", {})
    st_temp_eep = st_eep.get("Temp - °C", {})
    st_hum_eep  = st_eep.get("Hum - %", {})

    html = f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Dashboard Climático — 7GT-EEP San Luis Talpa &amp; 7GT-UES Univ. El Salvador</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:opsz,wght@9..40,300;400;500;700&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#050f2e; --bg2:#0a1628; --card:rgba(255,255,255,0.04);
  --brd:rgba(255,255,255,0.10); --brd2:rgba(255,255,255,0.06);
  --tx:#e8f0ff; --tx2:#7b93c4;
  --blue:#3b82f6; --cyan:#06b6d4; --amber:#f59e0b;
  --green:#10b981; --red:#ef4444; --rose:#fca5a5;
  --eep-c:#f59e0b; --ues-c:#06b6d4;
  --fm:'Space Mono',monospace; --fb:'DM Sans',sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{font-family:var(--fb);background:var(--bg);color:var(--tx);min-height:100vh;overflow-x:hidden}}

/* ── Background FX ── */
.bg-layer{{position:fixed;inset:0;z-index:0;pointer-events:none;
  background:radial-gradient(ellipse 80% 60% at 20% 10%,rgba(59,130,246,.16) 0%,transparent 60%),
             radial-gradient(ellipse 60% 50% at 80% 80%,rgba(6,182,212,.10) 0%,transparent 60%),
             linear-gradient(180deg,#050f2e 0%,#0a1a4e 50%,#071538 100%)}}
.stars{{position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:radial-gradient(circle,rgba(255,255,255,.6) 1px,transparent 1px),
                   radial-gradient(circle,rgba(255,255,255,.3) 1px,transparent 1px);
  background-size:250px 250px,130px 130px;background-position:0 0,80px 60px;
  animation:twinkle 9s ease-in-out infinite alternate}}
@keyframes twinkle{{0%{{opacity:.4}}100%{{opacity:.9}}}}
.aurora{{position:fixed;top:-180px;left:-100px;right:-100px;height:480px;z-index:0;
  background:linear-gradient(135deg,rgba(59,130,246,.07),rgba(6,182,212,.05),transparent);
  filter:blur(60px);animation:aurora-drift 18s ease-in-out infinite alternate}}
@keyframes aurora-drift{{0%{{transform:translateX(-60px) skewX(-4deg);opacity:.5}}
  100%{{transform:translateX(60px) skewX(4deg);opacity:.9}}}}

/* ── Layout ── */
.page{{position:relative;z-index:1;max-width:1380px;margin:0 auto;padding:0 32px 100px}}

/* ── Header ── */
header{{display:flex;justify-content:space-between;align-items:flex-end;
  padding:52px 0 40px;border-bottom:1px solid var(--brd);
  animation:fadeDown .9s ease both}}
@keyframes fadeDown{{0%{{opacity:0;transform:translateY(-18px)}}100%{{opacity:1;transform:none}}}}
.hdr-left{{display:flex;flex-direction:column;gap:8px}}
.badge-live{{display:inline-flex;align-items:center;gap:8px;
  background:rgba(59,130,246,.14);border:1px solid rgba(59,130,246,.3);
  border-radius:100px;padding:4px 14px;font-family:var(--fm);font-size:11px;
  color:var(--blue);letter-spacing:1.5px;text-transform:uppercase}}
.badge-live::before{{content:'';width:7px;height:7px;border-radius:50%;
  background:var(--blue);box-shadow:0 0 8px var(--blue);
  animation:pdot 2s ease-in-out infinite}}
@keyframes pdot{{0%,100%{{transform:scale(1);opacity:1}}50%{{transform:scale(1.5);opacity:.5}}}}
header h1{{font-family:var(--fb);font-size:clamp(24px,4vw,44px);font-weight:700;line-height:1.1;
  background:linear-gradient(135deg,#e8f0ff 0%,var(--cyan) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
header p{{font-size:13px;color:var(--tx2)}}
.hdr-right{{text-align:right}}
.clock{{font-family:var(--fm);font-size:30px;font-weight:700;color:var(--cyan);
  text-shadow:0 0 22px rgba(6,182,212,.45)}}
.clock-date{{font-size:12px;color:var(--tx2);margin-top:5px}}

/* ── Nav ── */
nav{{position:sticky;top:0;z-index:100;background:rgba(5,15,46,.92);
  backdrop-filter:blur(20px);border-bottom:1px solid var(--brd2);
  padding:10px 32px;display:flex;gap:8px;flex-wrap:wrap;margin:0 -32px;
  animation:fadeDown 1s ease .2s both}}
nav a{{color:var(--tx2);text-decoration:none;padding:5px 14px;
  border:1px solid var(--brd2);border-radius:6px;font-size:.75rem;
  font-family:var(--fm);letter-spacing:.5px;transition:.2s}}
nav a:hover{{background:var(--blue);color:#fff;border-color:var(--blue)}}

/* ── Section heading ── */
.sec{{margin-bottom:48px}}
.sec-h{{display:flex;align-items:center;gap:12px;
  font-family:var(--fm);font-size:11px;font-weight:700;
  letter-spacing:2px;text-transform:uppercase;color:var(--tx2);margin:52px 0 24px}}
.sec-h::before{{content:'';height:1px;flex:1;
  background:linear-gradient(90deg,var(--brd),transparent)}}
.sec-h::after{{content:'';height:1px;flex:3;
  background:linear-gradient(90deg,var(--brd),transparent)}}

/* ── Cards ── */
.card{{background:var(--card);border:1px solid var(--brd);border-radius:16px;
  backdrop-filter:blur(18px);padding:24px;position:relative;overflow:hidden;
  transition:transform .3s,box-shadow .3s,border-color .3s}}
.card:hover{{transform:translateY(-4px);box-shadow:0 20px 60px rgba(0,0,0,.45)}}
.card::before{{content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.18),transparent)}}

/* ── KPI grid ── */
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.kpi{{padding:22px 24px}}
.kpi-lbl{{font-family:var(--fm);font-size:9.5px;letter-spacing:2px;
  text-transform:uppercase;color:var(--tx2);margin-bottom:12px}}
.kpi-icon{{font-size:24px;margin-bottom:8px;display:block}}
.kpi-val{{font-family:var(--fm);font-size:clamp(20px,2.8vw,34px);font-weight:700;line-height:1}}
.kpi-val.temp{{color:#fca5a5;text-shadow:0 0 22px rgba(239,68,68,.4)}}
.kpi-val.hum {{color:#93c5fd;text-shadow:0 0 22px rgba(59,130,246,.4)}}
.kpi-val.bar {{color:#6ee7b7;text-shadow:0 0 22px rgba(16,185,129,.4)}}
.kpi-val.sol {{color:#fde68a;text-shadow:0 0 22px rgba(245,158,11,.4)}}
.kpi-unit{{font-size:12px;color:var(--tx2);margin-left:4px;font-weight:400}}
.kpi-sub{{margin-top:10px;font-size:12px;color:var(--tx2);font-family:var(--fm)}}
.kpi-sub span{{color:var(--tx);font-weight:700}}

/* ── Station badges ── */
.st-badges{{display:flex;gap:10px;margin-bottom:22px}}
.st-b{{padding:5px 16px;border-radius:100px;font-family:var(--fm);font-size:11px;
  letter-spacing:1px;font-weight:700}}
.st-b.eep{{background:rgba(245,158,11,.15);color:var(--eep-c);border:1px solid rgba(245,158,11,.35)}}
.st-b.ues{{background:rgba(6,182,212,.15);color:var(--ues-c);border:1px solid rgba(6,182,212,.35)}}

/* ── Grid layouts ── */
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.g1{{display:grid;grid-template-columns:1fr;gap:16px}}
.g3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}}

/* ── Plots ── */
.plt{{width:100%;border-radius:6px;display:block}}
.nd{{color:var(--tx2);font-size:.8rem;text-align:center;padding:28px}}
.cap{{font-family:var(--fm);font-size:9px;color:var(--tx2);text-align:center;
  margin-top:8px;letter-spacing:.5px}}

/* ── Stats tables ── */
.tbl-card{{background:var(--card);border:1px solid var(--brd);
  border-radius:12px;padding:16px;margin-bottom:16px}}
.tbl-h{{font-size:.9rem;color:var(--cyan);margin-bottom:12px;font-family:var(--fm)}}
.st{{width:100%;border-collapse:collapse;font-size:.78rem}}
.st th{{background:rgba(255,255,255,.04);color:var(--tx2);padding:7px 10px;
  border:1px solid var(--brd2);text-align:left;
  font-family:var(--fm);font-size:9px;letter-spacing:1px}}
.th-eep{{color:var(--eep-c)!important}}.th-ues{{color:var(--ues-c)!important}}
.st td{{padding:5px 10px;border:1px solid var(--brd2);color:var(--tx);font-family:var(--fm)}}
.st td.lbl{{color:var(--tx2);font-size:.73rem}}
.st td.eep{{color:var(--eep-c)}}.st td.ues{{color:var(--ues-c)}}
.st tr:nth-child(even) td{{background:rgba(255,255,255,.025)}}

/* ── Pearson table ── */
.ct{{width:100%;border-collapse:collapse;font-size:.82rem}}
.ct th{{background:rgba(255,255,255,.04);color:var(--tx2);padding:9px 12px;
  border:1px solid var(--brd2);font-family:var(--fm);font-size:9px;letter-spacing:1px}}
.ct td{{padding:7px 12px;border:1px solid var(--brd2);color:var(--tx);font-family:var(--fm)}}
.ct tr:nth-child(even) td{{background:rgba(255,255,255,.025)}}
.cf{{color:var(--green)!important;font-weight:700}}
.cm{{color:var(--amber)!important}}
.cd{{color:var(--red)!important}}

/* ── Note ── */
.note{{color:var(--tx2);font-size:.78rem;margin-bottom:14px;
  line-height:1.8;padding:10px 14px;background:rgba(59,130,246,.06);
  border-left:3px solid rgba(59,130,246,.4);border-radius:0 6px 6px 0}}
.note code{{color:var(--cyan);font-family:var(--fm);font-size:.75rem}}

/* ── Footer ── */
footer{{background:rgba(5,15,46,.6);border-top:1px solid var(--brd2);
  padding:18px 32px;text-align:center;font-size:.72rem;color:var(--tx2)}}

@media(max-width:920px){{
  .kpi-grid,.g2,.g3{{grid-template-columns:1fr 1fr}}
  .page{{padding:0 16px 60px}}
  nav{{margin:0 -16px;padding:8px 16px}}
}}
@media(max-width:580px){{
  .kpi-grid,.g2,.g3{{grid-template-columns:1fr}}
}}
</style></head><body>

<div class="bg-layer"></div>
<div class="stars"></div>
<div class="aurora"></div>

<div class="page">

<header>
  <div class="hdr-left">
    <span class="badge-live">WeatherLink Pro Analytics</span>
    <h1>Dashboard Climático Avanzado</h1>
    <p>Análisis histórico Feb 2025 – 2026 &nbsp;·&nbsp; Métodos Numéricos C++ + Python</p>
  </div>
  <div class="hdr-right">
    <div class="clock" id="clk">--:--:--</div>
    <div class="clock-date" id="clkd">— —</div>
  </div>
</header>

<nav>
  <a href="#kpi">KPIs</a>
  <a href="#series">Series Temporales</a>
  <a href="#stats">Estadísticos</a>
  <a href="#hist">Histogramas</a>
  <a href="#box">Boxplots</a>
  <a href="#wind">Rosa de Vientos</a>
  <a href="#pearson">Correlación</a>
  <span style="flex:1"></span>
  <a href="index.html" style="color:#38bdf8;border-color:rgba(56,189,248,.3);background:rgba(56,189,248,.07)">🏠 Inicio</a>
  <a href="dashboard_msn_interactivo.html" style="color:#38bdf8;border-color:rgba(56,189,248,.3);background:rgba(56,189,248,.07)">🌤 Clima</a>
  <a href="dashboard_solar.html" style="color:#fbbf24;border-color:rgba(251,191,36,.3);background:rgba(251,191,36,.07)">☀️ Solar</a>
  <a href="dashboard_fusion.html" style="color:#a78bfa;border-color:rgba(167,139,250,.3);background:rgba(167,139,250,.07)">🔗 Fusión</a>
</nav>

<main>

<!-- KPI CARDS -->
<section class="sec" id="kpi">
  <h2 class="sec-h">⚡ Indicadores Clave — 7GT-UES (Univ. El Salvador) · 7GT-EEP (San Luis Talpa)</h2>
  <div class="kpi-grid">

    <div class="card kpi">
      <div class="kpi-lbl">🌡️ Temperatura Exterior</div>
      <div class="kpi-val temp">{kpi(st_temp_ues,'media')}<span class="kpi-unit">°C</span></div>
      <div class="kpi-sub">
        x̄ &nbsp;·&nbsp; σ = <span>{kpi(st_temp_ues,'desv_estandar')}</span><br>
        Rango: <span>{kpi(st_temp_ues,'minimo')} – {kpi(st_temp_ues,'maximo')} °C</span>
      </div>
    </div>

    <div class="card kpi">
      <div class="kpi-lbl">💧 Humedad Exterior</div>
      <div class="kpi-val hum">{kpi(st_hum_ues,'media')}<span class="kpi-unit">%</span></div>
      <div class="kpi-sub">
        x̄ &nbsp;·&nbsp; σ = <span>{kpi(st_hum_ues,'desv_estandar')}</span><br>
        Mediana: <span>{kpi(st_hum_ues,'p50')} %</span>
      </div>
    </div>

    <div class="card kpi">
      <div class="kpi-lbl">🧭 Presión Barométrica</div>
      <div class="kpi-val bar">{kpi(st_bar_ues,'media')}<span class="kpi-unit">mb</span></div>
      <div class="kpi-sub">
        x̄ &nbsp;·&nbsp; σ = <span>{kpi(st_bar_ues,'desv_estandar')}</span><br>
        IQR: <span>{kpi(st_bar_ues,'riq')} mb</span>
      </div>
    </div>

    <div class="card kpi">
      <div class="kpi-lbl">☀️ Radiación Solar</div>
      <div class="kpi-val sol">{kpi(st_sol_ues,'media')}<span class="kpi-unit">W/m²</span></div>
      <div class="kpi-sub">
        x̄ &nbsp;·&nbsp; σ = <span>{kpi(st_sol_ues,'desv_estandar')}</span><br>
        Máximo: <span>{kpi(st_sol_ues,'maximo')} W/m²</span>
      </div>
    </div>

  </div>

  <div class="st-badges" style="margin-top:20px">
    <span class="st-b eep">7GT-EEP — San Luis Talpa</span>
    <span class="st-b ues">7GT-UES — Univ. El Salvador</span>
  </div>

  <!-- Mini comparativa EEP vs UES -->
  <div class="g2">
    <div class="card">
      <div class="kpi-lbl" style="margin-bottom:14px">🌡️ Temperatura — EEP vs UES</div>
      <table class="st"><thead><tr>
        <th>Métrica</th><th class="th-eep">EEP</th><th class="th-ues">UES</th>
      </tr></thead><tbody>
        <tr><td class="lbl">Media</td>
            <td class="eep">{kpi(st_temp_eep,'media')} °C</td>
            <td class="ues">{kpi(st_temp_ues,'media')} °C</td></tr>
        <tr><td class="lbl">σ</td>
            <td class="eep">{kpi(st_temp_eep,'desv_estandar')}</td>
            <td class="ues">{kpi(st_temp_ues,'desv_estandar')}</td></tr>
        <tr><td class="lbl">Mediana</td>
            <td class="eep">{kpi(st_temp_eep,'p50')} °C</td>
            <td class="ues">{kpi(st_temp_ues,'p50')} °C</td></tr>
        <tr><td class="lbl">Máximo</td>
            <td class="eep">{kpi(st_temp_eep,'maximo')} °C</td>
            <td class="ues">{kpi(st_temp_ues,'maximo')} °C</td></tr>
        <tr><td class="lbl">Mínimo</td>
            <td class="eep">{kpi(st_temp_eep,'minimo')} °C</td>
            <td class="ues">{kpi(st_temp_ues,'minimo')} °C</td></tr>
      </tbody></table>
    </div>
    <div class="card">
      <div class="kpi-lbl" style="margin-bottom:14px">💧 Humedad — EEP vs UES</div>
      <table class="st"><thead><tr>
        <th>Métrica</th><th class="th-eep">EEP</th><th class="th-ues">UES</th>
      </tr></thead><tbody>
        <tr><td class="lbl">Media</td>
            <td class="eep">{kpi(st_hum_eep,'media')} %</td>
            <td class="ues">{kpi(st_hum_ues,'media')} %</td></tr>
        <tr><td class="lbl">σ</td>
            <td class="eep">{kpi(st_hum_eep,'desv_estandar')}</td>
            <td class="ues">{kpi(st_hum_ues,'desv_estandar')}</td></tr>
        <tr><td class="lbl">Mediana</td>
            <td class="eep">{kpi(st_hum_eep,'p50')} %</td>
            <td class="ues">{kpi(st_hum_ues,'p50')} %</td></tr>
        <tr><td class="lbl">Máximo</td>
            <td class="eep">{kpi(st_hum_eep,'maximo')} %</td>
            <td class="ues">{kpi(st_hum_ues,'maximo')} %</td></tr>
        <tr><td class="lbl">IQR</td>
            <td class="eep">{kpi(st_hum_eep,'riq')}</td>
            <td class="ues">{kpi(st_hum_ues,'riq')}</td></tr>
      </tbody></table>
    </div>
  </div>
</section>

<!-- SERIES TEMPORALES -->
<section class="sec" id="series">
  <h2 class="sec-h">📈 Fase I — Series Temporales (Interpolación Lineal Manual)</h2>
  <p class="note">
    Pipeline: <code>skiprows=5</code> → sustitución <code>--/NaN</code> →
    <code>pd.to_datetime</code> → filtro ≥ 01/02/2025 →
    interpolación f(k) = f(a) + (k−a)·[f(b)−f(a)]/(b−a).
    La línea <span style="color:#fbbf24;font-weight:700">amarilla</span>
    muestra la media móvil de 24 h (ventana 288 muestras).
  </p>
  <div class="g1">
    <div class="card">{img("comp_temp","🌡️ Temperatura Exterior — Comparativa EEP (naranja) vs UES (cyan)")}</div>
    <div class="card">{img("serie_temp_ues","🌡️ Temperatura Exterior 7GT-UES")}</div>
    <div class="card">{img("serie_hum_ues","💧 Humedad Exterior 7GT-UES")}</div>
    <div class="card">{img("serie_bar_ues","🧭 Presión Barométrica 7GT-UES")}</div>
    <div class="card">{img("serie_solar_ues","☀️ Radiación Solar 7GT-UES")}</div>
  </div>
</section>

<!-- ESTADÍSTICOS -->
<section class="sec" id="stats">
  <h2 class="sec-h">📐 Fase II — Estadísticos Descriptivos Comparativos</h2>
  <p class="note">
    Motor: C++ <code>AjusteCurvas</code> (QuickSort interno, percentiles, Pearson) con fallback Python puro.
    σ calculada via Newton-Raphson sobre f(x) = x²−S  |  IC 90%: x̄ ± 1.645 · σ/√n.
    Sin <code>.mean() .std() .median() .quantile()</code>.
  </p>
  {tablas}
</section>

<!-- HISTOGRAMAS -->
<section class="sec" id="hist">
  <h2 class="sec-h">📊 Fase III — Histogramas (k = ⌈log₂n + 1⌉, Regla de Sturges)</h2>
  <div class="g2">
    <div class="card">{img("hist_temp_eep","🌡️ Temperatura — 7GT-EEP")}</div>
    <div class="card">{img("hist_temp_ues","🌡️ Temperatura — 7GT-UES")}</div>
    <div class="card">{img("hist_hum_eep","💧 Humedad — 7GT-EEP")}</div>
    <div class="card">{img("hist_hum_ues","💧 Humedad — 7GT-UES")}</div>
    <div class="card">{img("hist_bar_eep","🧭 Presión — 7GT-EEP")}</div>
    <div class="card">{img("hist_bar_ues","🧭 Presión — 7GT-UES")}</div>
    <div class="card">{img("hist_solar_ues","☀️ Radiación Solar — 7GT-UES")}</div>
    <div class="card">{img("hist_wind_ues","💨 Velocidad Viento — 7GT-UES")}</div>
  </div>
</section>

<!-- BOXPLOTS -->
<section class="sec" id="box">
  <h2 class="sec-h">📦 Fase III — Boxplots Mensuales (dibujado sin ax.boxplot)</h2>
  <p class="note">
    Caja: P25–P75 · Línea: P50 (mediana) · Bigotes: ±1.5·IQR ·
    Outliers: puntos individuales rojos.
  </p>
  <div class="g1">
    <div class="card">{img("box_temp_eep")}</div>
    <div class="card">{img("box_temp_ues")}</div>
    <div class="card">{img("box_hum_ues")}</div>
    <div class="card">{img("box_bar_ues")}</div>
  </div>
</section>

<!-- ROSA DE VIENTOS -->
<section class="sec" id="wind">
  <h2 class="sec-h">🌬️ Fase III — Rosa de los Vientos (16 rumbos · 22.5° c/u)</h2>
  <p class="note">
    Dirección parseada a ángulos polares en radianes ·
    Norte en cénit · Sentido horario · Color por velocidad media.
  </p>
  <div class="g2">
    <div class="card" style="text-align:center">
      <span class="st-b eep" style="display:inline-block;margin-bottom:12px">7GT-EEP — San Salvador</span>
      {img("wind_eep")}
    </div>
    <div class="card" style="text-align:center">
      <span class="st-b ues" style="display:inline-block;margin-bottom:12px">7GT-UES — San Salvador</span>
      {img("wind_ues")}
    </div>
  </div>
</section>

<!-- CORRELACIÓN DE PEARSON -->
<section class="sec" id="pearson">
  <h2 class="sec-h">🔗 Fase IV — Correlación de Pearson Inter-Estacional</h2>
  <p class="note">
    r = Σ[(xᵢ−x̄)(yᵢ−ȳ)] / √[Σ(xᵢ−x̄)² · Σ(yᵢ−ȳ)²] ·
    Motor: <code>AjusteCurvas::pearson_correlation(0,1)</code> sobre matriz alineada
    (timestamps exactos).
  </p>
  <div class="g2">
    <div class="card">{img("pearson")}</div>
    <div class="card">
      <table class="ct">
        <thead><tr>
          <th>Variable</th><th>r de Pearson</th><th>R²</th>
          <th>Interpretación</th><th>N pares</th>
        </tr></thead>
        <tbody>{filas_corr}</tbody>
      </table>
    </div>
  </div>
</section>

</main>
</div><!-- /acad-section -->
</div><!-- /page -->

<footer>
  Dashboard generado por el Motor de Análisis Climático &nbsp;·&nbsp;
  Métodos Numéricos &nbsp;·&nbsp;
  C++: AjusteCurvas · MetodosRaices · AlgebraLineal &nbsp;·&nbsp;
  Algoritmos: QuickSort · Newton-Raphson · Interpolación Lineal Manual
</footer>

<script>
function actualizarReloj(){{
  const ahora = new Date();
  document.getElementById('clk').textContent =
    ahora.toLocaleTimeString('es-SV');
  document.getElementById('clkd').textContent =
    ahora.toLocaleDateString('es-SV',{{weekday:'long',year:'numeric',month:'long',day:'numeric'}});
}}
actualizarReloj();
setInterval(actualizarReloj, 1000);
</script>
</body></html>"""

    with open(nombre, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  [OK] Dashboard → {nombre}")
    return nombre


# ══════════════════════════════════════════════════════════════════════
# FASE V — DASHBOARD MSN INTERACTIVO (con JSON embebido)
# ══════════════════════════════════════════════════════════════════════

# ── V.A: Algoritmos astronómicos (Python puro, sin librerías) ─────────

def _fase_lunar_conway(fecha) -> dict:
    """
    Fase lunar mediante la ecuación de Conway adaptada.
    Solo necesita la fecha. No requiere librerías externas.
    Retorna: fase (0.0–1.0), nombre, emoji.
    """
    anio = fecha.year
    mes  = fecha.month
    dia  = fecha.day

    if mes < 3:
        anio -= 1
        mes  += 12

    A = int(anio / 100)
    B = int(A / 4)
    C = 2 - A + B
    E = int(365.25 * (anio + 4716))
    F = int(30.6001 * (mes + 1))
    JD = C + dia + E + F - 1524.5

    # Ciclo sinódico (días)
    CICLO = 29.53058867
    fase_raw = (JD - 2451550.1) / CICLO
    fase = fase_raw - int(fase_raw)
    if fase < 0:
        fase += 1.0

    # Tabla de nombres y emojis
    if fase < 0.025 or fase >= 0.975:
        nombre, emoji = "Luna nueva",         "🌑"
    elif fase < 0.25:
        nombre, emoji = "Creciente",           "🌒"
    elif fase < 0.275:
        nombre, emoji = "Cuarto creciente",    "🌓"
    elif fase < 0.50:
        nombre, emoji = "Gibosa creciente",    "🌔"
    elif fase < 0.525:
        nombre, emoji = "Luna llena",          "🌕"
    elif fase < 0.75:
        nombre, emoji = "Gibosa menguante",    "🌖"
    elif fase < 0.775:
        nombre, emoji = "Cuarto menguante",    "🌗"
    else:
        nombre, emoji = "Menguante",           "🌘"

    return {"fase": round(fase, 4), "nombre": nombre, "emoji": emoji}


def _sol_noaa(fecha, lat: float = 13.6929, lon: float = -89.2182) -> dict:
    """
    Cálculo amanecer/ocaso basado en algoritmos NOAA (Jean Meeus).
    Lat/Lon default: San Salvador, El Salvador.
    Retorna: amanecer, ocaso (HH:MM local), duracion_h.
    """
    anio = fecha.year
    mes  = fecha.month
    dia  = fecha.day

    # Número de día Juliano
    A = int((14 - mes) / 12)
    Y = anio + 4800 - A
    M = mes + 12 * A - 3
    JD = (dia
          + int((153 * M + 2) / 5)
          + 365 * Y
          + int(Y / 4)
          - int(Y / 100)
          + int(Y / 400)
          - 32045)

    n  = JD - 2451545.0 + 0.0008
    Js = n - lon / 360.0

    M_sol = (357.5291 + 0.98560028 * Js) % 360.0
    C = (1.9148 * math.sin(math.radians(M_sol))
         + 0.0200 * math.sin(math.radians(2 * M_sol))
         + 0.0003 * math.sin(math.radians(3 * M_sol)))
    lam = (M_sol + C + 180.0 + 102.9372) % 360.0

    Jtr = (2451545.0 + Js
           + 0.0053 * math.sin(math.radians(M_sol))
           - 0.0069 * math.sin(math.radians(2 * lam)))

    dec_sin = math.sin(math.radians(lam)) * math.sin(math.radians(23.4397))
    dec_cos = math.sqrt(1.0 - dec_sin * dec_sin)

    lat_r   = math.radians(lat)
    elev_r  = math.radians(-0.833)
    cos_w0_num = (math.sin(elev_r) - math.sin(lat_r) * dec_sin)
    cos_w0_den = math.cos(lat_r) * dec_cos
    if abs(cos_w0_den) < 1e-9:
        return {"amanecer": "N/A", "ocaso": "N/A", "duracion_h": 0.0}

    cos_w0 = cos_w0_num / cos_w0_den
    cos_w0 = max(-1.0, min(1.0, cos_w0))
    w0 = math.degrees(math.acos(cos_w0)) / 360.0

    Jrise = Jtr - w0
    Jset  = Jtr + w0

    def jd_a_hhmm(jd_val):
        frac = (jd_val + 0.5) % 1.0
        # Ajuste UTC-6 (El Salvador)
        frac_local = (frac - 6.0 / 24.0) % 1.0
        h = int(frac_local * 24)
        m = int((frac_local * 24 - h) * 60)
        return f"{h:02d}:{m:02d}"

    am_str = jd_a_hhmm(Jrise)
    oc_str = jd_a_hhmm(Jset)
    dur_h  = w0 * 48.0  # 2 * w0 * 24

    return {
        "amanecer":   am_str,
        "ocaso":      oc_str,
        "duracion_h": round(dur_h, 2)
    }


def _icono_clima_dia(solar_max: float, lluvia_total: float) -> str:
    """Ícono de clima diario basado en irradiancia y lluvia."""
    if lluvia_total > 5.0:
        return "⛈️" if solar_max > 300 else "🌧️"
    if lluvia_total > 0.5:
        return "🌦️"
    if solar_max > 600:
        return "☀️"
    if solar_max > 200:
        return "⛅"
    return "☁️"


def _analisis_texto(variable: str, valor: float, sensor: str) -> str:
    """Mini-análisis descriptivo automático por variable."""
    if variable == "temp":
        if valor < 18:   return "Temperatura fresca, ideal para actividades al aire libre."
        if valor < 24:   return "Temperatura agradable y confortable."
        if valor < 29:   return "Temperatura cálida, mantenerse hidratado."
        if valor < 33:   return "Temperatura alta, precaución con la exposición solar."
        return "Temperatura muy alta, riesgo de golpe de calor."
    if variable == "hum":
        if valor < 30:   return "Ambiente muy seco, se recomienda hidratación frecuente."
        if valor < 50:   return "Humedad agradable, condiciones ideales."
        if valor < 65:   return "Humedad confortable para la mayoría de personas."
        if valor < 80:   return "Ambiente algo húmedo, puede sensación de bochorno."
        return "Alta humedad, bochornoso. Precaución en ejercicio físico."
    if variable == "lluvia":
        if valor == 0:   return "Sin precipitaciones registradas."
        if valor < 2:    return "Lluvia ligera o llovizna."
        if valor < 10:   return "Lluvia moderada."
        if valor < 30:   return "Lluvia intensa. Se recomienda precaución vial."
        return "Precipitación muy intensa. Riesgo de inundaciones."
    if variable == "viento":
        if valor < 5:    return "Viento calmo o brisa muy leve."
        if valor < 15:   return "Brisa suave, condiciones agradables."
        if valor < 30:   return "Viento moderado, considerar en actividades al aire libre."
        if valor < 50:   return "Viento fuerte. Precaución con objetos ligeros."
        return "Viento muy fuerte. Evitar exposición directa."
    if variable == "uv":
        if valor < 3:    return "UV bajo. Sin precauciones especiales."
        if valor < 6:    return "UV moderado. Se recomienda protector solar."
        if valor < 8:    return "UV alto. Protector solar factor 30+ obligatorio."
        if valor < 11:   return "UV muy alto. Minimizar exposición entre 10am-4pm."
        return "UV extremo. Riesgo de quemadura en minutos. Quedarse bajo techo."
    if variable == "presion":
        if valor < 1000: return "Presión baja. Posible tiempo inestable o lluvioso."
        if valor < 1013: return "Presión ligeramente bajo la media."
        if valor < 1020: return "Presión normal. Tiempo estable."
        return "Presión alta. Tiempo seco y despejado esperado."
    return ""


# ── V.A1: Tendencia lineal C++ (regresion_lineal) ────────────────────

def _calcular_tendencia_cpp(df_eep: "pd.DataFrame",
                             df_ues: "pd.DataFrame",
                             todas_fechas: list) -> dict:
    """
    Ajusta regresion_lineal C++ sobre (índice_día → variable) para detectar
    si la temperatura/solar/etc. tienen tendencia creciente o decreciente.
    Retorna pendiente (°C/mes), R², y etiqueta de interpretación.
    """
    VARS = [
        ("Temp - °C",          "temp"),
        ("Hum - %",            "hum"),
        ("Solar Rad - W/m^2",  "solar"),
        ("Rain - mm",          "lluvia"),
        ("Avg Wind Speed - km/h", "viento"),
        ("Barometer - mb",     "presion"),
    ]
    resultado = {}

    for df, sensor_name in [(df_eep, "EEP"), (df_ues, "UES")]:
        dt_col = df.columns[0]
        df2 = df[[dt_col] + [c for c, _ in VARS if c in df.columns]].copy()
        df2["_fecha"] = df2[dt_col].dt.strftime("%Y-%m-%d")
        for col, _ in VARS:
            if col in df2.columns:
                df2[col] = pd.to_numeric(df2[col], errors="coerce")
        grp = df2.groupby("_fecha")

        fecha_medias = {}
        for fecha, grupo in grp:
            fila = {}
            for col, alias in VARS:
                if col not in grupo.columns:
                    continue
                vals = [v for v in grupo[col].tolist() if v == v]
                if vals:
                    fila[alias] = sum(vals) / len(vals)
            fecha_medias[fecha] = fila

        fechas_ord = sorted(f for f in todas_fechas if f in fecha_medias)
        n = len(fechas_ord)
        if n < 14:
            continue

        res_sensor = {}
        for _, alias in VARS:
            xs = []
            ys = []
            for i, f in enumerate(fechas_ord):
                v = fecha_medias[f].get(alias)
                if v is not None:
                    xs.append(float(i))
                    ys.append(float(v))
            if len(xs) < 10:
                continue
            try:
                datos = np.ascontiguousarray([[x, y] for x, y in zip(xs, ys)], dtype=np.float64)
                ac = AjusteCurvas()
                ac.establecer_datos(datos)
                coef = ac.regresion_lineal(0, 1)  # [b0, b1]: y = b0 + b1*x
                b0, b1 = float(coef[0]), float(coef[1])
                # R² manual (sin numpy estadístico)
                ym = sum(ys) / len(ys)
                ss_tot = sum((y - ym)**2 for y in ys)
                ss_res = sum((y - (b0 + b1*x))**2 for x, y in zip(xs, ys))
                r2 = 1 - ss_res / ss_tot if ss_tot > 1e-10 else 0.0
                # Pendiente por mes (30 días)
                por_mes = b1 * 30.0
                if abs(por_mes) < 0.05:
                    etiq = "Estable"
                elif por_mes > 0:
                    etiq = f"↑ +{abs(por_mes):.3f}/mes"
                else:
                    etiq = f"↓ −{abs(por_mes):.3f}/mes"
                res_sensor[alias] = {
                    "b0": round(b0, 4), "b1": round(b1, 6),
                    "r2": round(r2, 4), "por_mes": round(por_mes, 4),
                    "etiqueta": etiq, "n": len(xs),
                }
            except Exception as e:
                pass
        resultado[sensor_name] = res_sensor

    return resultado


# ── V.A2: Modelo predictivo con regresión polinomial C++ ─────────────

def _calcular_prediccion_cpp(df_eep: "pd.DataFrame", todas_fechas: list) -> dict:
    """
    Ajusta un polinomio de grado 3 (C++ regresion_polinomial) sobre
    (día_del_año → temp_media_diaria) y (día_del_año → solar_media_diaria)
    y predice los siguientes 30 días desde la última fecha disponible.
    """
    import datetime as _dt

    dt_col = df_eep.columns[0]
    TEMP_COL  = "Temp - °C"
    SOLAR_COL = "Solar Rad - W/m^2"
    LLUVIA_COL= "Rain - mm"

    # Calcular promedios diarios desde horas agrupadas
    df_w = df_eep[[dt_col, TEMP_COL, SOLAR_COL, LLUVIA_COL]].copy()
    df_w["_fecha"] = df_w[dt_col].dt.strftime("%Y-%m-%d")
    df_w["_doy"]   = df_w[dt_col].dt.dayofyear.astype(float)

    for col in [TEMP_COL, SOLAR_COL, LLUVIA_COL]:
        df_w[col] = pd.to_numeric(df_w[col], errors="coerce")

    # Media y suma diaria usando groupby (pandas, permitido para agrupación)
    grp = df_w.groupby("_fecha")
    doys   = {}
    temps  = {}
    solars = {}
    lluvias= {}
    for fecha, grupo in grp:
        doys[fecha]    = float(grupo["_doy"].iloc[0])
        t_list = [v for v in grupo[TEMP_COL].tolist() if v == v]
        s_list = [v for v in grupo[SOLAR_COL].tolist() if v == v]
        l_list = [v for v in grupo[LLUVIA_COL].tolist() if v == v]
        if t_list:  temps[fecha]   = sum(t_list) / len(t_list)
        if s_list:  solars[fecha]  = sum(s_list) / len(s_list)
        if l_list:  lluvias[fecha] = sum(l_list)

    fechas_ord = sorted(f for f in todas_fechas if f in temps)
    if len(fechas_ord) < 10:
        return {"error": "Pocos datos para regresión"}

    xs_t  = np.ascontiguousarray([[doys[f], temps[f]] for f in fechas_ord], dtype=np.float64)
    xs_s  = np.ascontiguousarray([[doys[f], solars[f]] for f in fechas_ord
                                   if f in solars], dtype=np.float64)

    coef_t, coef_s = None, None
    try:
        ac_t = AjusteCurvas()
        ac_t.establecer_datos(xs_t)
        coef_t = ac_t.regresion_polinomial(0, 1, 3).tolist()  # [a0,a1,a2,a3]
    except Exception as e:
        print(f"    [WARN prediccion temp] {e}")

    try:
        ac_s = AjusteCurvas()
        ac_s.establecer_datos(xs_s)
        coef_s = ac_s.regresion_polinomial(0, 1, 3).tolist()
    except Exception as e:
        print(f"    [WARN prediccion solar] {e}")

    # Predecir próximos 30 días
    ultima = _dt.date.fromisoformat(fechas_ord[-1])
    predicciones = []
    for i in range(1, 31):
        fd = ultima + _dt.timedelta(days=i)
        doy = float(fd.timetuple().tm_yday)
        pred = {"fecha": str(fd), "doy": doy}
        if coef_t:
            t = sum(coef_t[j] * (doy ** j) for j in range(4))
            pred["temp"] = round(max(10.0, min(50.0, t)), 1)
        if coef_s:
            s = sum(coef_s[j] * (doy ** j) for j in range(4))
            pred["solar"] = round(max(0.0, s), 1)
        predicciones.append(pred)

    # Stats del ajuste: error cuadrático medio C++
    rmse_t, rmse_s = None, None
    try:
        if coef_t:
            errores = []
            for f in fechas_ord:
                doy = doys[f]
                pred_t = sum(coef_t[j] * (doy ** j) for j in range(4))
                errores.append((pred_t - temps[f]) ** 2)
            rmse_t = round(sqrt_nr(sum(errores) / len(errores)), 4)
    except Exception:
        pass
    try:
        if coef_s:
            errores_s = []
            for f in fechas_ord:
                if f not in solars: continue
                doy = doys[f]
                pred_s = sum(coef_s[j] * (doy ** j) for j in range(4))
                errores_s.append((pred_s - solars[f]) ** 2)
            rmse_s = round(sqrt_nr(sum(errores_s) / len(errores_s)), 4) if errores_s else None
    except Exception:
        pass

    return {
        "tipo":          "polinomial_grado3",
        "coef_temp":     [round(c, 6) for c in coef_t]  if coef_t  else None,
        "coef_solar":    [round(c, 6) for c in coef_s]  if coef_s  else None,
        "rmse_temp":     rmse_t,
        "rmse_solar":    rmse_s,
        "n_datos":       len(fechas_ord),
        "ultima_fecha":  str(ultima),
        "predicciones":  predicciones,
    }


# ── V.B: Construcción del JSON de datos por día ───────────────────────

def _construir_json_clima(df_eep, df_ues) -> dict:
    """
    Construye window.CLIMA desde los DataFrames.
    Estructura:
      {
        sensores: ["EEP","UES"],
        dias: { "YYYY-MM-DD": { EEP: {...}, UES: {...} } },
        fases_lunares: { "YYYY-MM-DD": {fase, nombre, emoji} },
        sol:           { "YYYY-MM-DD": {amanecer, ocaso, duracion_h} },
        stats:         { EEP: {...}, UES: {...} }
      }
    """
    print("  [MSN] Construyendo JSON de datos por día…")

    dt_col_eep = df_eep.columns[0]
    dt_col_ues = df_ues.columns[0]

    # Columnas de interés (con sus alias para el JSON)
    COLS_EEP = [
        ("Temp - °C",              "temp"),
        ("High Temp - °C",         "temp_max"),
        ("Low Temp - °C",          "temp_min"),
        ("Hum - %",                "hum"),
        ("Solar Rad - W/m^2",      "solar"),
        ("High Solar Rad - W/m^2", "solar_max"),
        ("Rain - mm",              "lluvia"),
        ("Avg Wind Speed - km/h",  "viento"),
        ("High Wind Speed - km/h", "viento_max"),
        ("Prevailing Wind Dir",    "dir_viento"),
        ("Barometer - mb",         "presion"),
        ("Heat Index - °C",        "heat_index"),
        ("Dew Point - °C",         "rocio"),
        ("UV Index",               "uv"),
        ("High UV Index",          "uv_max"),
        ("ET - mm",                "et"),
    ]
    COLS_UES = [c for c in COLS_EEP if c[0] not in ("UV Index", "High UV Index", "ET - mm")]

    def extraer_dia(df, dt_col, cols_mapa):
        """
        Agrupa por fecha con pandas groupby (O(n)).
        Stats diarios con numpy vectorizado: max/min/sum/mean sobre arrays,
        sin bucles Python sobre filas individuales.
        """
        _ALIAS_TEXTO = {"dir_viento"}
        _ALIAS_MAX   = {"solar_max", "temp_max", "uv_max", "viento_max"}
        _ALIAS_MIN   = {"temp_min"}
        _ALIAS_SUM   = {"lluvia", "et"}

        # Columnas numéricas -> float64 de una vez (pandas, permitido)
        cols_presentes = [(c, a) for c, a in cols_mapa if c in df.columns]
        df2 = df[[dt_col] + [c for c, a in cols_presentes]].copy()
        df2["_f"] = df2[dt_col].dt.strftime("%Y-%m-%d")
        df2["_t"] = df2[dt_col].dt.strftime("%H:%M")

        for col_csv, alias in cols_presentes:
            if alias not in _ALIAS_TEXTO:
                df2[col_csv] = pd.to_numeric(df2[col_csv], errors="coerce")

        num_cols  = [(c, a) for c, a in cols_presentes if a not in _ALIAS_TEXTO]
        text_cols = [(c, a) for c, a in cols_presentes if a in _ALIAS_TEXTO]

        # Pre-extraer arrays numpy por columna (una sola vez, O(n))
        arr_map = {c: df2[c].to_numpy(dtype=float, na_value=float("nan"))
                   for c, a in num_cols}
        t_arr   = df2["_t"].to_numpy()
        f_arr   = df2["_f"].to_numpy()

        # Índices de cada fecha (O(n) total con numpy argsort)
        order     = f_arr.argsort(kind="stable")
        f_sorted  = f_arr[order]
        fechas_u, first_idx, counts = np.unique(
            f_sorted, return_index=True, return_counts=True
        )
        fechas = fechas_u.tolist()
        total  = len(fechas)

        # Texto: índices originales
        text_raw = {c: df2[c].to_numpy(dtype=object) for c, a in text_cols}

        dias = {}
        for ni, (fecha, fi, cnt) in enumerate(zip(fechas, first_idx, counts)):
            if ni % 50 == 0:
                pct = int(ni / total * 100) if total else 0
                print("      " + str(ni) + "/" + str(total)
                      + " (" + str(pct) + "%)...", end="\r", flush=True)

            # Índices originales de este grupo
            orig_idx = order[fi: fi + cnt]
            reg = {}

            # Columnas numéricas — estadísticos vía C++ o Python manual
            for col_csv, alias in num_cols:
                arr = arr_map[col_csv][orig_idx]
                # Convertir a lista Python para _maximo/_minimo/_media (sin .max/.min/.mean)
                vals_list = [float(v) for v in arr if not (v != v)]
                if not vals_list:
                    continue
                if alias in _ALIAS_MAX:
                    reg[alias] = round(_maximo(vals_list), 2)
                elif alias in _ALIAS_MIN:
                    reg[alias] = round(_minimo(vals_list), 2)
                elif alias in _ALIAS_SUM:
                    reg[alias] = round(float(np.nansum(arr)), 2)
                else:
                    reg[alias] = round(_media(vals_list), 2)

            # Columnas de texto: moda
            for col_csv, alias in text_cols:
                raw = text_raw[col_csv][orig_idx]
                tabla = {}
                for v in raw:
                    sv = str(v).strip()
                    if sv and sv not in ("", "--", "nan", "None"):
                        tabla[sv] = tabla.get(sv, 0) + 1
                reg[alias] = max(tabla, key=tabla.get) if tabla else "N/D"

            # Icono del día
            solar_max  = reg.get("solar_max", reg.get("solar", 0) or 0)
            lluvia_tot = reg.get("lluvia", 0) or 0
            reg["icono"] = _icono_clima_dia(solar_max, lluvia_tot)

            # Mini-análisis
            reg["analisis"] = {
                "temp":    _analisis_texto("temp",    reg.get("temp",    25.0), ""),
                "hum":     _analisis_texto("hum",     reg.get("hum",     70.0), ""),
                "lluvia":  _analisis_texto("lluvia",  reg.get("lluvia",   0.0), ""),
                "viento":  _analisis_texto("viento",  reg.get("viento",   5.0), ""),
                "uv":      _analisis_texto("uv",      reg.get("uv",       3.0), ""),
                "presion": _analisis_texto("presion", reg.get("presion", 1013.), ""),
            }

            # Datos horarios: formato columnar comprimido
            # {t:[...], temp:[...], hum:[...], ...}
            # 1 decimal en lugar de 2 → ~40% menos caracteres numéricos
            t_group = t_arr[orig_idx]
            horas_col = {"t": [str(v) for v in t_group]}
            for col_csv, alias in num_cols:
                col_arr = arr_map[col_csv][orig_idx]
                # Solo incluir columnas que tengan al menos un valor no-NaN
                vals_h = []
                tiene_datos = False
                for v in col_arr:
                    if np.isnan(v):
                        vals_h.append(None)
                    else:
                        vals_h.append(round(float(v), 1))
                        tiene_datos = True
                if tiene_datos:
                    horas_col[alias] = vals_h

            reg["horas"] = horas_col
            dias[fecha]  = reg

        print()
        return dias

    print("    EEP…")
    dias_eep = extraer_dia(df_eep, dt_col_eep, COLS_EEP)
    print("    UES…")
    dias_ues = extraer_dia(df_ues, dt_col_ues, COLS_UES)

    # Unir días de ambos sensores
    todas_fechas = sorted(set(list(dias_eep.keys()) + list(dias_ues.keys())))
    dias_union = {}
    for f in todas_fechas:
        dias_union[f] = {
            "EEP": dias_eep.get(f, {}),
            "UES": dias_ues.get(f, {}),
        }

    # Fases lunares y sol
    print("    Fases lunares y datos del sol…")
    fases = {}
    sol   = {}
    import datetime as _dt
    for fecha_str in todas_fechas:
        try:
            d = _dt.date.fromisoformat(fecha_str)
        except ValueError:
            continue
        fases[fecha_str] = _fase_lunar_conway(d)
        sol[fecha_str]   = _sol_noaa(d)

    # Stats globales por sensor (usando funciones ya existentes)
    print("    Stats globales…")
    COLS_STATS = [
        "Temp - °C", "Hum - %", "Barometer - mb",
        "Solar Rad - W/m^2", "Avg Wind Speed - km/h",
        "Rain - mm", "Heat Index - °C", "Dew Point - °C",
        "UV Index", "ET - mm",
    ]
    stats_eep, stats_ues = {}, {}
    for col in COLS_STATS:
        if col in df_eep.columns:
            st = calcular_estadisticos(df_eep, col)
            stats_eep[col] = {k: (round(v, 4) if isinstance(v, float) else v)
                              for k, v in st.items() if k != "col"}
        if col in df_ues.columns:
            st = calcular_estadisticos(df_ues, col)
            stats_ues[col] = {k: (round(v, 4) if isinstance(v, float) else v)
                              for k, v in st.items() if k != "col"}

    # Stats mensuales por sensor
    stats_men_eep, stats_men_ues = {}, {}
    for col in ["Temp - °C", "Hum - %", "Solar Rad - W/m^2", "Rain - mm"]:
        if col in df_eep.columns:
            stats_men_eep[col] = calcular_estadisticos_mensuales(df_eep, col)
        if col in df_ues.columns:
            stats_men_ues[col] = calcular_estadisticos_mensuales(df_ues, col)

    # Stats por alias JS (clave → CSV col) para acceso directo desde el frontend
    _ALIAS_MAP = {
        "temp":    "Temp - °C",
        "hum":     "Hum - %",
        "solar":   "Solar Rad - W/m^2",
        "lluvia":  "Rain - mm",
        "viento":  "Avg Wind Speed - km/h",
        "presion": "Barometer - mb",
    }
    def _rnd(v):
        return round(float(v), 4) if isinstance(v, (float, int)) else v

    stats_alias_eep, stats_alias_ues = {}, {}
    for alias, col in _ALIAS_MAP.items():
        if col in stats_eep:
            stats_alias_eep[alias] = {k: _rnd(v) for k, v in stats_eep[col].items()}
        if col in stats_ues:
            stats_alias_ues[alias] = {k: _rnd(v) for k, v in stats_ues[col].items()}

    stats_men_alias_eep, stats_men_alias_ues = {}, {}
    for alias, col in _ALIAS_MAP.items():
        if col in stats_men_eep:
            stats_men_alias_eep[alias] = {
                mes: {k: _rnd(v) for k, v in mst.items()}
                for mes, mst in stats_men_eep[col].items()
            }
        if col in stats_men_ues:
            stats_men_alias_ues[alias] = {
                mes: {k: _rnd(v) for k, v in mst.items()}
                for mes, mst in stats_men_ues[col].items()
            }

    # Tendencia lineal C++ (regresion_lineal) por variable y sensor
    print("    Tendencia lineal C++ por variable…")
    tendencia = _calcular_tendencia_cpp(df_eep, df_ues, todas_fechas)

    # Modelo predictivo con regresión polinomial C++ grado 3
    print("    Modelo predictivo (regresión polinomial C++ grado 3)…")
    prediccion = _calcular_prediccion_cpp(df_eep, todas_fechas)

    clima = {
        "sensores":          ["EEP", "UES"],
        "dias":              dias_union,
        "fases_lunares":     fases,
        "sol":               sol,
        "stats":             {"EEP": stats_eep,         "UES": stats_ues},
        "stats_mensual":     {"EEP": stats_men_eep,      "UES": stats_men_ues},
        "stats_alias":       {"EEP": stats_alias_eep,    "UES": stats_alias_ues},
        "stats_men_alias":   {"EEP": stats_men_alias_eep,"UES": stats_men_alias_ues},
        "tendencia":         tendencia,
        "prediccion":        prediccion,
    }
    print(f"    JSON listo: {len(todas_fechas)} días, "
          f"{len(dias_eep)} EEP, {len(dias_ues)} UES.")
    return clima


# ── V.C: Generador del HTML interactivo ──────────────────────────────

def generar_dashboard_msn_interactivo(
        df_eep, df_ues,
        figs: dict,
        correlaciones: dict,
        nombre: str = "dashboard_msn_interactivo.html") -> str:
    """
    Dashboard MSN-style completamente interactivo.
    Embebe window.CLIMA como JSON dentro del HTML.
    Sin dependencias de red para los datos (Chart.js desde CDN).
    """
    import datetime as _dt

    clima_data = _construir_json_clima(df_eep, df_ues)
    clima_json = json.dumps(clima_data, ensure_ascii=False, separators=(",", ":"))

    # Gráficos base64 del análisis académico (Pearson, series, etc.)
    def img(k, style="width:100%;border-radius:8px"):
        b = figs.get(k, "")
        if not b:
            return '<div style="color:#475569;padding:20px;text-align:center">Sin datos</div>'
        return f'<img src="data:image/png;base64,{b}" style="{style}" loading="lazy"/>'

    filas_corr = ""
    for d in correlaciones.values():
        r  = d.get("r", float("nan"))
        r2 = d.get("r2", float("nan"))
        nm = d.get("nombre", "")
        interp = d.get("interpretacion", "")
        n  = d.get("n", 0)
        color = "#4ade80" if r >= 0.7 else "#fbbf24" if r >= 0.3 else "#f87171"
        filas_corr += (
            f"<tr><td>{nm}</td>"
            f"<td style='color:{color};font-family:monospace'>{r:+.6f}</td>"
            f"<td style='font-family:monospace'>{r2:.4f}</td>"
            f"<td>{interp}</td><td>{n:,}</td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Clima San Salvador · EEP &amp; UES · Dashboard Interactivo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<!-- Chart.js para gráficos académicos secundarios (histograma, boxplot, dispersión) -->
<!-- Chart.js y uPlot: archivos locales en dashboard/ (funciona con file://) -->
<script src="chart.umd.min.js"></script>
<link  rel="stylesheet" href="uPlot.min.css">
<script src="uPlot.iife.min.js"></script>
<style>
:root{{
  --bg:#06101f;--bg2:#0c1a31;--bg3:#0f2040;
  --card:rgba(255,255,255,.055);--card-h:rgba(255,255,255,.09);
  --brd:rgba(255,255,255,.10);--brd2:rgba(255,255,255,.06);
  --tx:#f1f5f9;--tx2:#94a3b8;--tx3:#64748b;
  --blue:#38bdf8;--warm:#f87171;--amber:#fbbf24;--green:#4ade80;--purple:#a78bfa;
  --r:'Outfit',sans-serif;--mono:'DM Mono',monospace;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{font-family:var(--r);background:var(--bg);color:var(--tx);min-height:100vh;overflow-x:hidden}}

/* ── Fondos animados ── */
.sky{{position:fixed;inset:0;z-index:0;pointer-events:none;
  background:radial-gradient(ellipse 90% 55% at 15% 8%,rgba(56,189,248,.12) 0%,transparent 65%),
             radial-gradient(ellipse 70% 50% at 85% 90%,rgba(99,102,241,.09) 0%,transparent 60%),
             linear-gradient(175deg,#06101f 0%,#0c1a31 50%,#060f1e 100%)}}
.sky-glow{{position:fixed;top:-200px;left:50%;transform:translateX(-50%);
  width:900px;height:500px;z-index:0;pointer-events:none;
  background:radial-gradient(ellipse,rgba(14,165,233,.08) 0%,transparent 70%);
  animation:glow-pulse 8s ease-in-out infinite alternate}}
@keyframes glow-pulse{{0%{{opacity:.5;transform:translateX(-50%) scale(.95)}}100%{{opacity:1;transform:translateX(-50%) scale(1.05)}}}}
.stars{{position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:radial-gradient(circle,rgba(255,255,255,.55) 1px,transparent 1px),
                   radial-gradient(circle,rgba(255,255,255,.25) 1px,transparent 1px);
  background-size:320px 320px,160px 160px;background-position:0 0,90px 70px;
  animation:twinkle 11s ease-in-out infinite alternate}}
@keyframes twinkle{{0%{{opacity:.35}}100%{{opacity:.85}}}}

/* ── Layout ── */
.page{{position:relative;z-index:1;max-width:1240px;margin:0 auto;padding:0 24px 100px}}

/* ── Header ── */
header{{display:flex;justify-content:space-between;align-items:flex-end;padding:40px 0 28px;border-bottom:1px solid var(--brd2)}}
.city-name{{font-size:clamp(20px,3.5vw,38px);font-weight:700;
  background:linear-gradient(120deg,#f1f5f9 0%,var(--blue) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.loc-pin{{width:7px;height:7px;border-radius:50%;background:var(--blue);
  box-shadow:0 0 10px var(--blue);display:inline-block;animation:pin-pulse 2.5s infinite}}
@keyframes pin-pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.6);opacity:.6}}}}
.period-tag{{display:inline-flex;align-items:center;gap:6px;
  background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.25);
  border-radius:100px;padding:3px 12px;font-size:.72rem;color:var(--blue)}}
.clock-time{{font-family:var(--mono);font-size:clamp(22px,3vw,34px);font-weight:500}}
.clock-date{{font-size:.76rem;color:var(--tx2);margin-top:2px;text-align:right}}

/* ── Navbar sticky ── */
.navbar{{
  display:flex;flex-wrap:wrap;gap:8px;align-items:center;
  padding:10px 24px;
  /* sticky */
  position:sticky;top:0;z-index:200;
  /* glassmorphism al hacer scroll */
  background:rgba(6,16,31,.82);
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid var(--brd2);
  /* compensar el padding del .page */
  margin:0 -24px;
  transition:box-shadow .3s;
}}
.navbar.scrolled{{box-shadow:0 4px 32px rgba(0,0,0,.45)}}
/* Cuando NO hace scroll, integrado con el fondo */
.navbar-inner{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;width:100%;max-width:1240px;margin:0 auto}}
.sensor-btns{{display:flex;gap:6px}}
.btn-sensor,.btn-tab{{
  padding:6px 14px;border-radius:100px;border:1px solid var(--brd);
  background:transparent;color:var(--tx2);font-family:var(--r);
  font-size:.78rem;cursor:pointer;transition:.2s;white-space:nowrap}}
.btn-sensor:hover,.btn-tab:hover{{background:rgba(56,189,248,.1);color:var(--blue)}}
.btn-sensor.active{{background:rgba(56,189,248,.18);border-color:rgba(56,189,248,.5);color:var(--blue)}}
.btn-tab.active{{background:rgba(56,189,248,.18);border-color:rgba(56,189,248,.5);color:var(--blue)}}
.tabs{{display:flex;gap:5px;flex-wrap:wrap}}
/* Divider vertical entre sensor y tabs */
.nav-sep{{width:1px;height:22px;background:var(--brd);margin:0 4px;align-self:center}}

/* ── Selector de período (también sticky, dentro del navbar) ── */
.period-bar{{display:flex;gap:6px;align-items:center}}
.btn-period{{padding:5px 12px;border-radius:8px;border:1px solid var(--brd);
  background:transparent;color:var(--tx2);font-family:var(--r);font-size:.75rem;cursor:pointer;transition:.2s}}
.btn-period:hover{{background:rgba(255,255,255,.06)}}
.btn-period.active{{background:rgba(56,189,248,.15);border-color:var(--blue);color:var(--blue)}}
/* Etiqueta período seleccionado en navbar */
.nav-period-label{{font-size:.66rem;color:var(--tx3);white-space:nowrap;
  padding:4px 10px;border-radius:6px;background:rgba(255,255,255,.04);
  border:1px solid var(--brd2)}}
/* ── Date picker en navbar ── */
.nav-datepicker-wrap{{display:flex;align-items:center;gap:4px}}
.nav-date-input{{
  background:rgba(255,255,255,.06);border:1px solid var(--brd);
  color:var(--tx);border-radius:8px;padding:4px 8px;
  font-size:.78rem;font-family:var(--mono);cursor:pointer;
  color-scheme:dark;
}}
.nav-date-input::-webkit-calendar-picker-indicator{{
  filter:invert(1) opacity(.6);cursor:pointer;
}}
.nav-date-input:hover{{border-color:var(--blue);background:rgba(56,189,248,.08)}}

/* ── Calendario barra MSN-style ── */
.cal-section{{margin-top:20px}}
.cal-label{{font-size:.68rem;font-weight:600;letter-spacing:2px;text-transform:uppercase;
  color:var(--tx2);margin-bottom:14px;display:flex;align-items:center;gap:10px}}
.cal-nav{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.cal-nav button{{background:none;border:1px solid var(--brd);color:var(--tx2);
  border-radius:6px;padding:3px 10px;cursor:pointer;font-size:.85rem}}
.cal-nav button:hover{{background:rgba(255,255,255,.06)}}
#cal-month-label{{font-size:.9rem;color:var(--tx);font-weight:500;min-width:130px;text-align:center}}
.cal-scroll{{display:flex;gap:6px;overflow-x:auto;padding-bottom:8px;
  scrollbar-width:thin;scrollbar-color:var(--brd) transparent}}
.cal-day{{display:flex;flex-direction:column;align-items:center;min-width:68px;
  padding:10px 6px;border-radius:12px;border:1px solid transparent;
  background:rgba(255,255,255,.04);cursor:pointer;transition:.2s}}
.cal-day:hover{{background:rgba(56,189,248,.08);border-color:rgba(56,189,248,.2)}}
.cal-day.active{{background:rgba(56,189,248,.16);border-color:rgba(56,189,248,.45)}}
.cal-day.no-data{{opacity:.35;cursor:not-allowed;pointer-events:none}}
.cal-dname{{font-size:.62rem;color:var(--tx3);margin-bottom:2px;pointer-events:none}}
.cal-dnum{{font-size:.95rem;font-weight:600;pointer-events:none}}
.cal-ico{{font-size:1.3rem;margin:3px 0;pointer-events:none}}
.cal-tmax{{font-size:.75rem;font-weight:600;color:var(--warm);pointer-events:none}}
.cal-tmin{{font-size:.65rem;color:var(--blue);pointer-events:none}}

/* ── Panel de comparativa ── */
.comp-panel{{display:none;margin-top:16px;background:rgba(255,255,255,.03);
  border:1px solid var(--brd);border-radius:14px;padding:18px 20px}}
.comp-panel.visible{{display:block}}
.comp-row{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:14px;align-items:flex-end}}
.comp-group{{display:flex;flex-direction:column;gap:6px;flex:1;min-width:180px}}
.comp-group label{{font-size:.65rem;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--tx3)}}
.date-inp{{background:rgba(255,255,255,.06);border:1px solid var(--brd);border-radius:8px;
  color:var(--tx);font-family:var(--r);font-size:.78rem;padding:6px 10px;outline:none;
  cursor:pointer;transition:.2s;width:100%}}
.date-inp:focus{{border-color:var(--blue);background:rgba(56,189,248,.07)}}
.comp-badge-a{{color:#f87171}}.comp-badge-b{{color:#34d399}}
.btn-run-comp{{padding:7px 18px;border-radius:8px;border:none;
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
.comp-interp{{margin-top:16px;background:rgba(56,189,248,.06);border:1px solid rgba(56,189,248,.15);
  border-radius:10px;padding:14px 16px;font-size:.78rem;color:var(--tx2);line-height:1.6}}
.comp-interp strong{{color:var(--tx)}}
.btn-comparar-active{{border-color:rgba(248,113,113,.6)!important;background:rgba(248,113,113,.15)!important;color:#f87171!important}}

/* ── Gráfico principal ── */
.chart-main-card{{background:var(--card);border:1px solid var(--brd);
  border-radius:18px;padding:20px 22px;margin-top:20px;min-height:260px;
  backdrop-filter:blur(16px)}}
.chart-main-title{{font-size:.72rem;font-weight:600;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--tx2);margin-bottom:14px}}
#chart-main-canvas{{width:100%!important;max-height:220px}}

/* ── Grid de widgets ── */
.widgets-grid{{display:grid;
  grid-template-columns:repeat(auto-fit,minmax(195px,1fr));
  gap:14px;margin-top:20px}}
.widget{{background:var(--card);border:1px solid var(--brd);
  border-radius:18px;padding:18px 20px;backdrop-filter:blur(16px);
  transition:.25s;position:relative;overflow:hidden}}
.widget::after{{content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.15),transparent)}}
.widget:hover{{background:var(--card-h);transform:translateY(-3px)}}
.w-ico-row{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.w-ico{{font-size:1.4rem}}
.w-badge{{font-size:.6rem;padding:2px 8px;border-radius:100px;font-weight:600}}
.w-label{{font-size:.66rem;color:var(--tx2);margin-bottom:3px;letter-spacing:.3px}}
.w-value{{font-size:1.85rem;font-weight:600;line-height:1.1}}
.w-unit{{font-size:.82rem;font-weight:400;color:var(--tx2);margin-left:2px}}
.w-sub{{font-size:.7rem;color:var(--tx2);margin-top:5px;line-height:1.4}}
.w-analysis{{font-size:.68rem;color:var(--tx3);margin-top:6px;font-style:italic;line-height:1.4}}

/* ── Trayectoria solar SVG ── */
.sun-widget{{grid-column:span 2}}
#sol-svg{{width:100%;height:80px}}
.sun-times{{display:flex;justify-content:space-between;font-size:.75rem;color:var(--tx2);margin-top:6px}}

/* ── Fase lunar ── */
.moon-face{{font-size:3rem;text-align:center;line-height:1;margin:6px 0}}

/* ── UV Bar ── */
.uv-bar{{height:6px;border-radius:3px;margin-top:8px;
  background:linear-gradient(90deg,#4ade80 0%,#fbbf24 33%,#f97316 55%,#ef4444 77%,#a855f7 100%);
  position:relative}}
.uv-cursor{{position:absolute;top:-3px;width:12px;height:12px;border-radius:50%;
  background:#fff;box-shadow:0 0 8px rgba(0,0,0,.6);transform:translateX(-50%);transition:left .5s}}

/* ── Mapa viento ── */
.map-card{{background:var(--card);border:1px solid var(--brd);border-radius:18px;
  overflow:hidden;margin-top:20px}}
.map-card iframe{{width:100%;height:380px;border:none;display:block}}
.map-label{{padding:14px 20px;font-size:.72rem;color:var(--tx2)}}

/* ── Sección académica ── */
.sec-head{{display:flex;align-items:center;gap:12px;font-size:.68rem;
  font-weight:700;letter-spacing:2.5px;text-transform:uppercase;color:var(--tx3);margin:44px 0 16px}}
.sec-head::after{{content:'';height:1px;flex:1;background:linear-gradient(90deg,var(--brd),transparent)}}
.acad-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.acad-card{{background:var(--card);border:1px solid var(--brd);border-radius:18px;padding:20px;backdrop-filter:blur(16px)}}
.acad-title{{font-size:.72rem;color:var(--tx2);letter-spacing:1px;text-transform:uppercase;margin-bottom:12px}}
/* ── Modelo predictivo ── */
.pred-badge{{background:rgba(255,255,255,.04);border:1px solid var(--brd2);border-radius:10px;padding:8px 14px;min-width:120px}}
.pred-badge-label{{font-size:.62rem;color:var(--tx3);text-transform:uppercase;letter-spacing:.8px;margin-bottom:4px}}
.pred-badge-val{{font-size:.95rem;font-family:var(--mono);color:var(--green);font-weight:500}}
.ct{{width:100%;border-collapse:collapse;font-size:.8rem}}
.ct th{{background:rgba(255,255,255,.06);color:var(--tx2);padding:8px 10px;
  text-align:left;border-bottom:1px solid var(--brd2);font-weight:500}}
.ct td{{padding:7px 10px;border-bottom:1px solid var(--brd2);color:var(--tx)}}
.ct tr:last-child td{{border-bottom:none}}

/* ── uPlot overrides ── */
.uplot{{width:100%!important}}
.uplot .u-wrap{{width:100%!important}}
.u-title{{color:var(--tx2)!important;font-family:var(--r)!important;font-size:.72rem!important}}
.u-legend{{font-size:.72rem!important;color:var(--tx2)!important}}
.u-legend .u-value{{color:var(--tx)!important}}

/* ── Contenedor de gráfico uPlot con controles ── */
.uplot-card{{background:var(--card);border:1px solid var(--brd);border-radius:18px;
  padding:16px 18px 12px;margin-top:14px;backdrop-filter:blur(16px);position:relative;
  transition:border-color .2s}}
/* Estado bloqueado (por defecto): cursor normal, sin interacción de zoom/pan */
.uplot-card .u-over{{cursor:default!important;pointer-events:none}}
/* Estado activo: cursor crosshair, interacción habilitada */
.uplot-card.chart-active .u-over{{cursor:crosshair!important;pointer-events:all}}
.uplot-card.chart-active{{border-color:rgba(56,189,248,.45);
  box-shadow:0 0 0 1px rgba(56,189,248,.2)}}
.uplot-title{{font-size:.72rem;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;
  color:var(--tx2);margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}}
.zoom-controls{{display:flex;gap:6px;align-items:center}}
/* Botón toggle de activación — el más importante */
.btn-activate{{
  display:inline-flex;align-items:center;gap:5px;
  background:rgba(255,255,255,.06);border:1px solid var(--brd);color:var(--tx2);
  border-radius:6px;padding:4px 11px;font-size:.72rem;cursor:pointer;
  transition:.15s;user-select:none;font-family:var(--r)}}
.btn-activate:hover{{background:rgba(56,189,248,.12);color:var(--blue);border-color:rgba(56,189,248,.3)}}
.btn-activate.on{{background:rgba(56,189,248,.2);border-color:var(--blue);color:var(--blue)}}
.btn-activate .dot{{width:6px;height:6px;border-radius:50%;background:currentColor;
  box-shadow:0 0 6px currentColor}}
.zoom-btn{{background:rgba(255,255,255,.06);border:1px solid var(--brd);color:var(--tx2);
  border-radius:6px;padding:3px 9px;font-size:.75rem;cursor:pointer;transition:.15s;user-select:none}}
.zoom-btn:hover{{background:rgba(56,189,248,.12);color:var(--blue);border-color:rgba(56,189,248,.3)}}
/* Hint dinámico */
.zoom-hint{{font-size:.62rem;color:var(--tx3);margin-top:6px;text-align:right;
  transition:color .2s}}
.uplot-card.chart-active .zoom-hint{{color:var(--blue)}}

/* ── Sparkline dentro de widget ── */
.spark-wrap{{margin-top:8px;position:relative;height:40px}}
.spark-wrap canvas{{position:absolute;inset:0;width:100%!important;height:100%!important}}

/* ── Cursor personalizado sobre uPlot ── */
.uplot-card .u-cursor-pt{{border-radius:50%}}

/* ── Lazy loading skeleton ── */
.lazy-section{{opacity:0;transform:translateY(20px);transition:opacity .5s ease,transform .5s ease}}
.lazy-section.visible{{opacity:1;transform:translateY(0)}}
.lazy-section.lazy-pending{{position:relative;min-height:120px}}
.lazy-section.lazy-pending::after{{
  content:'Cargando análisis…';
  position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
  font-size:.75rem;color:var(--tx3);letter-spacing:1px;
  animation:lazy-pulse 1.4s ease-in-out infinite}}
@keyframes lazy-pulse{{0%,100%{{opacity:.3}}50%{{opacity:1}}}}
/* Skeleton shimmer para canvas vacíos */
.acad-card canvas:empty,
.acad-card canvas[data-lazy]{{
  background:linear-gradient(90deg,
    rgba(255,255,255,.03) 25%,
    rgba(255,255,255,.07) 50%,
    rgba(255,255,255,.03) 75%);
  background-size:200% 100%;
  animation:shimmer 1.6s infinite}}
@keyframes shimmer{{0%{{background-position:200% 0}}100%{{background-position:-200% 0}}}}

/* ── Responsive ── */
@media(max-width:760px){{
  .acad-grid{{grid-template-columns:1fr}}
  header{{flex-direction:column;gap:12px}}
  .sun-widget{{grid-column:span 1}}
  .clock-date{{text-align:left}}
}}
@media(max-width:480px){{
  .page{{padding:0 14px 80px}}
  .widgets-grid{{grid-template-columns:1fr 1fr}}
}}
</style>
</head>
<body>
<div class="sky"></div>
<div class="sky-glow"></div>
<div class="stars"></div>

<div class="page">

<!-- ══ HEADER ══ -->
<header>
  <div>
    <div style="display:flex;align-items:center;gap:8px;font-size:.78rem;color:var(--tx2);margin-bottom:6px">
      <span class="loc-pin"></span>
      <span>San Salvador, El Salvador &nbsp;·&nbsp; Estaciones 7GT-EEP &amp; 7GT-UES</span>
    </div>
    <h1 class="city-name">Clima San Salvador</h1>
    <span class="period-tag">📅 Registro histórico Feb 2025–2026</span>
  </div>
  <div>
    <div class="clock-time" id="clk">--:--</div>
    <div class="clock-date" id="clkd">—</div>
  </div>
</header>

<!-- ══ NAVBAR STICKY: Sensor + Tabs + Período + Calendario ══ -->
<div class="navbar" id="main-navbar">
  <div class="navbar-inner">
    <!-- Sensor -->
    <div class="sensor-btns">
      <button class="btn-sensor active" id="btn-eep" onclick="setSensor('EEP')">📡 EEP</button>
      <button class="btn-sensor" id="btn-ues" onclick="setSensor('UES')">📡 UES</button>
    </div>
    <div class="nav-sep"></div>
    <!-- Tabs de variable -->
    <div class="tabs">
      <button class="btn-tab active" id="tab-general"  onclick="setTab('general')">🌤 General</button>
      <button class="btn-tab" id="tab-lluvia"   onclick="setTab('lluvia')">🌧 Lluvia</button>
      <button class="btn-tab" id="tab-viento"  onclick="setTab('viento')">💨 Viento</button>
      <button class="btn-tab" id="tab-hum"     onclick="setTab('hum')">💧 Hum</button>
      <button class="btn-tab" id="tab-presion" onclick="setTab('presion')">🧭 Presión</button>
    </div>
    <div class="nav-sep"></div>
    <!-- Período -->
    <div class="period-bar">
      <button class="btn-period active" id="p-dia"  onclick="setPeriodo('dia')">Día</button>
      <button class="btn-period" id="p-mes"   onclick="setPeriodo('mes')">Mes</button>
      <button class="btn-period" id="p-anio"  onclick="setPeriodo('anio')">Año</button>
      <button class="btn-period" id="p-todo"  onclick="setPeriodo('todo')">Todo</button>
    </div>
    <div class="nav-sep"></div>
    <!-- Selector de fecha rápido en navbar -->
    <div class="nav-datepicker-wrap" title="Ir a una fecha específica">
      <label for="nav-cal-input" style="font-size:.75rem;color:var(--tx3);margin-right:4px">📅</label>
      <input type="date" id="nav-cal-input" class="nav-date-input"
             onchange="irAFecha(this.value)" title="Selecciona una fecha">
    </div>
    <button class="btn-period" id="btn-comparar" onclick="toggleComparacion()" title="Comparar dos rangos de tiempo">📊 Comparar</button>
    <!-- Indicador de fecha/período activo -->
    <span class="nav-period-label" id="nav-periodo-label">—</span>
    <!-- Links a otras páginas -->
    <div style="display:flex;gap:6px;margin-left:auto">
      <a href="index.html" style="padding:4px 11px;border-radius:7px;border:1px solid rgba(56,189,248,.3);
        background:rgba(56,189,248,.07);color:var(--blue);font-size:.7rem;text-decoration:none;
        white-space:nowrap;transition:.2s" onmouseover="this.style.background='rgba(56,189,248,.15)'"
        onmouseout="this.style.background='rgba(56,189,248,.07)'">🏠 Inicio</a>
      <a href="dashboard_solar.html" style="padding:4px 11px;border-radius:7px;border:1px solid rgba(251,191,36,.3);
        background:rgba(251,191,36,.07);color:#fbbf24;font-size:.7rem;text-decoration:none;
        white-space:nowrap;transition:.2s" onmouseover="this.style.background='rgba(251,191,36,.15)'"
        onmouseout="this.style.background='rgba(251,191,36,.07)'">☀️ Solar</a>
      <a href="dashboard_fusion.html" style="padding:4px 11px;border-radius:7px;border:1px solid rgba(167,139,250,.3);
        background:rgba(167,139,250,.07);color:#a78bfa;font-size:.7rem;text-decoration:none;
        white-space:nowrap;transition:.2s" onmouseover="this.style.background='rgba(167,139,250,.15)'"
        onmouseout="this.style.background='rgba(167,139,250,.07)'">🔗 Fusión</a>
    </div>
  </div>
</div>

<!-- ══ CALENDARIO MSN-STYLE ══ -->
<div class="cal-section">
  <div class="cal-label">
    📅 Selecciona un día
    <div class="cal-nav">
      <button onclick="calNav(-1)">‹</button>
      <span id="cal-month-label">—</span>
      <button onclick="calNav(1)">›</button>
    </div>
  </div>
  <div class="cal-scroll" id="cal-scroll"></div>
</div>

<!-- ══ PANEL COMPARATIVA DE RANGOS ══ -->
<div class="comp-panel" id="comp-panel">
  <div class="comp-row">
    <div class="comp-group">
      <label><span class="comp-badge-a">▶ Rango A</span></label>
      <input type="date" class="date-inp" id="comp-a-desde" onchange="actualizarEtiquetasComp()">
      <input type="date" class="date-inp" id="comp-a-hasta" onchange="actualizarEtiquetasComp()">
    </div>
    <div class="comp-group">
      <label><span class="comp-badge-b">▶ Rango B</span></label>
      <input type="date" class="date-inp" id="comp-b-desde" onchange="actualizarEtiquetasComp()">
      <input type="date" class="date-inp" id="comp-b-hasta" onchange="actualizarEtiquetasComp()">
    </div>
    <button class="btn-run-comp" onclick="renderComparacion()">Comparar rangos</button>
  </div>
  <div class="comp-result" id="comp-result"></div>
</div>

<!-- ══ GRÁFICO PRINCIPAL uPlot: Temperatura + Humedad ══ -->
<div class="uplot-card" id="card-main">
  <div class="uplot-title">
    <span id="chart-title">Temperatura y Humedad — Día seleccionado</span>
    <div class="zoom-controls">
      <button class="zoom-btn" onclick="uZoomIn('main')"    title="Zoom in">＋</button>
      <button class="zoom-btn" onclick="uZoomOut('main')"   title="Zoom out">－</button>
      <button class="zoom-btn" onclick="uZoomReset('main')" title="Reset">⟳</button>
    </div>
  </div>
  <div id="uplot-main" style="width:100%"></div>
  <div class="zoom-hint" id="hint-main">Clic para activar · Rueda para zoom · Arrastra para pan</div>
</div>

<!-- ══ GRÁFICO SOLAR uPlot: Irradiancia ══ -->
<div class="uplot-card" id="card-solar">
  <div class="uplot-title">
    <span id="chart-solar-title">Irradiancia Solar — Día seleccionado</span>
    <div class="zoom-controls">
      <button class="zoom-btn" onclick="uZoomIn('solar')"    title="Zoom in">＋</button>
      <button class="zoom-btn" onclick="uZoomOut('solar')"   title="Zoom out">－</button>
      <button class="zoom-btn" onclick="uZoomReset('solar')" title="Reset">⟳</button>
    </div>
  </div>
  <div id="uplot-solar" style="width:100%"></div>
  <div class="zoom-hint" id="hint-solar">Clic para activar · Rueda para zoom · Arrastra para pan</div>
</div>

<!-- ══ GRID DE WIDGETS ══ -->
<div class="widgets-grid" id="widgets-grid">
  <!-- Generados por JS -->
</div>

<!-- ══ MAPA VIENTO DECORATIVO ══ -->
<div class="map-card">
  <div class="map-label">🌍 Vientos atmosféricos en tiempo real — San Salvador (decorativo)</div>
  <iframe
    src="https://earth.nullschool.net/#current/wind/surface/level/orthographic=-89.2,13.7,3000/loc=-89.193,13.692"
    loading="lazy" title="Mapa de vientos earth.nullschool.net"
    sandbox="allow-scripts allow-same-origin"></iframe>
</div>

<!-- ══ SECCIÓN ACADÉMICA DINÁMICA ══ -->
<div id="acad-section" class="lazy-section lazy-pending">
<div class="sec-head" id="acad-head">Análisis estadístico — período seleccionado</div>

<!-- Selector de variable para los gráficos académicos -->
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;align-items:center">
  <span style="font-size:.72rem;color:var(--tx2);letter-spacing:1px">VARIABLE:</span>
  <button class="btn-tab active" id="av-temp"    onclick="setAcadVar('temp')">🌡 Temperatura</button>
  <button class="btn-tab" id="av-hum"     onclick="setAcadVar('hum')">💧 Humedad</button>
  <button class="btn-tab" id="av-solar"   onclick="setAcadVar('solar')">☀ Solar</button>
  <button class="btn-tab" id="av-lluvia"  onclick="setAcadVar('lluvia')">🌧 Lluvia</button>
  <button class="btn-tab" id="av-viento"  onclick="setAcadVar('viento')">💨 Viento</button>
  <button class="btn-tab" id="av-presion" onclick="setAcadVar('presion')">🧭 Presión</button>
</div>

<!-- Fila superior: Serie temporal + Histograma -->
<div class="acad-grid" style="margin-bottom:16px">
  <div class="acad-card">
    <div class="acad-title" id="at-serie">📈 Serie temporal</div>
    <canvas id="acad-serie" style="width:100%;max-height:200px"></canvas>
  </div>
  <div class="acad-card">
    <div class="acad-title" id="at-hist">📊 Histograma (Regla de Sturges)</div>
    <canvas id="acad-hist"  style="width:100%;max-height:200px"></canvas>
  </div>
</div>

<!-- Fila inferior: Boxplot mensual + Dispersión EEP vs UES -->
<div class="acad-grid" style="margin-bottom:16px">
  <div class="acad-card">
    <div class="acad-title" id="at-box">📦 Boxplot mensual</div>
    <canvas id="acad-box"   style="width:100%;max-height:200px"></canvas>
  </div>
  <div class="acad-card">
    <div class="acad-title" id="at-disp">🔀 Dispersión EEP vs UES</div>
    <canvas id="acad-disp"  style="width:100%;max-height:200px"></canvas>
  </div>
</div>

<!-- Tabla de estadísticos del período -->
<div class="acad-card" style="margin-bottom:16px">
  <div class="acad-title">📋 Estadísticos del período — <span id="st-periodo-label">—</span></div>
  <div style="overflow-x:auto">
    <table class="ct" id="acad-stats-table">
      <thead><tr>
        <th>Métrica</th><th>Valor (período)</th><th>Unidad</th>
      </tr></thead>
      <tbody id="acad-stats-body"></tbody>
    </table>
  </div>
</div>

<!-- Rosa de vientos estática (matplotlib) -->
<div class="sec-head">Rosa de los Vientos (matplotlib — histórico completo)</div>
<div class="acad-grid">
  <div class="acad-card"><div class="acad-title">7GT-EEP</div>{img("wind_eep")}</div>
  <div class="acad-card"><div class="acad-title">7GT-UES</div>{img("wind_ues")}</div>
</div>

<!-- Comparativa estaciones interactiva (uPlot) -->
<div class="sec-head">Comparativa estaciones — Temperatura · EEP vs UES</div>
<div class="uplot-card" id="card-comp" style="margin-bottom:16px">
  <div class="uplot-title">
    <span id="comp-title">Temperatura EEP (naranja) vs UES (cian) — período seleccionado</span>
    <div class="zoom-controls">
      <button class="zoom-btn" onclick="uZoomComp(0.75)">＋</button>
      <button class="zoom-btn" onclick="uZoomComp(1.35)">－</button>
      <button class="zoom-btn" onclick="uZoomCompReset()">⟳</button>
    </div>
  </div>
  <div id="uplot-comp" style="width:100%"></div>
  <div class="zoom-hint" id="hint-comp">Clic para activar · Rueda para zoom · Arrastra para pan</div>
</div>

<!-- ══ MAPA DE CALOR POR HORA DEL DÍA ══ -->
<div class="sec-head">Mapa de Calor — Distribución Horaria (Canvas 2D)</div>
<div class="acad-card" style="margin-bottom:16px">
  <div class="acad-title" id="heatmap-title">🌡 Temperatura media por hora del día · período seleccionado</div>
  <canvas id="acad-heatmap" style="width:100%;height:120px;image-rendering:pixelated"></canvas>
  <div style="display:flex;justify-content:space-between;font-size:.65rem;color:var(--tx3);margin-top:4px;padding:0 4px">
    <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:59</span>
  </div>
</div>

<!-- ══ TENDENCIA LINEAL C++ ══ -->
<div class="sec-head">Análisis de Tendencia — Regresión Lineal C++ (AjusteCurvas)</div>
<div class="acad-card" style="margin-bottom:16px">
  <canvas id="acad-tendencia" style="width:100%;max-height:200px"></canvas>
  <div style="overflow-x:auto;margin-top:12px">
    <table class="ct" id="tendencia-table">
      <thead><tr>
        <th>Variable</th><th>Pendiente/mes</th><th>R²</th><th>Tendencia</th><th>N días</th>
      </tr></thead>
      <tbody id="tendencia-tbody"></tbody>
    </table>
  </div>
</div>

<!-- ══ TABLA RESUMEN MENSUAL COMPLETA ══ -->
<div class="sec-head">Resumen Mensual Completo — C++ AjusteCurvas</div>
<div class="acad-card" style="margin-bottom:16px;overflow-x:auto">
  <div id="tabla-mensual-wrap" style="overflow-x:auto">
    <table class="ct" id="tabla-mensual">
      <thead id="tabla-mensual-head"></thead>
      <tbody id="tabla-mensual-body"></tbody>
    </table>
  </div>
</div>

<!-- ══ EVENTOS EXTREMOS ══ -->
<div class="sec-head">Análisis de Eventos Extremos — Umbrales Climáticos</div>
<div class="acad-card" style="margin-bottom:16px">
  <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px" id="extremos-badges"></div>
  <table class="ct" id="extremos-table">
    <thead><tr>
      <th>Umbral</th><th>Descripción</th><th>N días</th><th>% del período</th><th>Último evento</th>
    </tr></thead>
    <tbody id="extremos-tbody"></tbody>
  </table>
</div>

<!-- Correlación de Pearson -->
<div class="sec-head">Correlación de Pearson Inter-Estacional (Fase IV)</div>
<div class="acad-card">
  <table class="ct" style="margin-top:4px">
    <thead><tr>
      <th>Variable</th><th>r de Pearson</th><th>R²</th><th>Interpretación</th><th>N pares</th>
    </tr></thead>
    <tbody>{filas_corr}</tbody>
  </table>
</div>

<!-- ══ MODELO PREDICTIVO C++ ══ -->
<div class="sec-head" style="margin-top:40px">
  Modelo Predictivo — Regresión Polinomial Grado 3 (C++ AjusteCurvas)
</div>
<div class="acad-card">
  <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:14px">
    <div class="pred-badge">
      <div class="pred-badge-label">Tipo de modelo</div>
      <div class="pred-badge-val" id="pred-tipo">—</div>
    </div>
    <div class="pred-badge">
      <div class="pred-badge-label">N datos entrenamiento</div>
      <div class="pred-badge-val" id="pred-n">—</div>
    </div>
    <div class="pred-badge">
      <div class="pred-badge-label">RMSE Temperatura</div>
      <div class="pred-badge-val" id="pred-rmse-t">—</div>
    </div>
    <div class="pred-badge">
      <div class="pred-badge-label">RMSE Solar</div>
      <div class="pred-badge-val" id="pred-rmse-s">—</div>
    </div>
    <div class="pred-badge">
      <div class="pred-badge-label">Última fecha real</div>
      <div class="pred-badge-val" id="pred-ultima">—</div>
    </div>
  </div>
  <div class="acad-title">🌡 Predicción temperatura próximos 30 días</div>
  <canvas id="pred-temp-canvas" style="width:100%;max-height:200px"></canvas>
  <div class="acad-title" style="margin-top:16px">☀ Predicción radiación solar próximos 30 días</div>
  <canvas id="pred-solar-canvas" style="width:100%;max-height:200px"></canvas>
  <div style="margin-top:12px">
    <table class="ct" id="pred-table">
      <thead><tr>
        <th>Fecha</th><th>Día del año</th><th>Temp. predicha (°C)</th><th>Solar predicha (W/m²)</th>
      </tr></thead>
      <tbody id="pred-tbody"></tbody>
    </table>
  </div>
  <div style="font-size:.68rem;color:var(--tx3);margin-top:8px">
    Coeficientes polinomio temperatura:
    <span id="pred-coef-t" style="font-family:var(--mono);color:var(--tx2)">—</span>
  </div>
</div>

</div><!-- /page -->

<footer style="border-top:1px solid var(--brd2);padding:18px 24px;text-align:center;
  font-size:.72rem;color:var(--tx3);margin-top:60px">
  Dashboard generado por el Motor de Análisis Climático &nbsp;·&nbsp;
  Métodos Numéricos &nbsp;·&nbsp;
  C++: AjusteCurvas · MetodosRaices · AlgebraLineal &nbsp;·&nbsp;
  Algoritmos: QuickSort · Newton-Raphson · Interpolación Lineal Manual · Conway (Luna) · NOAA (Sol)
</footer>

<!-- ══ DATOS EMBEBIDOS ══ -->
<script>
const CLIMA = {clima_json};
</script>

<!-- ══ LÓGICA INTERACTIVA ══ -->
<script>
// ── Estado global ──
let sensor   = 'EEP';
let tabActiva= 'general';
let periodo  = 'dia';
let diaSelec = null;
let calMes   = null;   // {{ year, month }}
let chartMain= null;

const DIAS_ES = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
const MESES_ES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                  'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

// ── Reloj ──
function actualizarReloj(){{
  const d = new Date();
  const pad = n => String(n).padStart(2,'0');
  document.getElementById('clk').textContent =
    pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds());
  document.getElementById('clkd').textContent =
    DIAS_ES[d.getDay()]+', '+d.getDate()+' '+MESES_ES[d.getMonth()]+' '+d.getFullYear();
}}
actualizarReloj();
setInterval(actualizarReloj,1000);

// ── Navbar: sombra al hacer scroll ──────────────────────────────────
window.addEventListener('scroll', ()=>{{
  const nb = document.getElementById('main-navbar');
  if(nb) nb.classList.toggle('scrolled', window.scrollY > 60);
}}, {{passive:true}});

// ── Actualizar etiqueta de período en navbar ─────────────────────────
function actualizarNavLabel(){{
  const el = document.getElementById('nav-periodo-label');
  if(!el) return;
  const fechas = fechasConSensor(sensor);
  if(!fechas.length){{ el.textContent='—'; return; }}
  if(periodo==='dia'){{
    el.textContent = diaSelec || '—';
  }} else if(periodo==='mes'){{
    const pref = diaSelec ? diaSelec.slice(0,7) : fechas[fechas.length-1].slice(0,7);
    el.textContent = pref;
  }} else if(periodo==='anio'){{
    const anio = diaSelec ? diaSelec.slice(0,4) : fechas[fechas.length-1].slice(0,4);
    el.textContent = anio;
  }} else {{
    const f0 = fechas[0].slice(0,7), fN = fechas[fechas.length-1].slice(0,7);
    el.textContent = f0 + ' → ' + fN;
  }}
}}

// ── Fechas disponibles ──
const todasFechas = Object.keys(CLIMA.dias).sort();
function fechasConSensor(s){{
  return todasFechas.filter(f => CLIMA.dias[f] && CLIMA.dias[f][s] && Object.keys(CLIMA.dias[f][s]).length > 3);
}}

// ── Inicialización ──
function init(){{
  const fechas = fechasConSensor(sensor);
  if(!fechas.length) return;
  // Abrir en el último mes con datos
  const uf = fechas[fechas.length-1];
  const [y,m] = uf.split('-').map(Number);
  calMes = {{year:y, month:m}};
  diaSelec = uf;
  renderizarCalendario();
  _initCalListener();
  actualizarTodo();
}}

// ── Navegación de mes ──
function calNav(dir){{
  let m = calMes.month + dir;
  let y = calMes.year;
  if(m < 1){{m=12; y--;}}
  if(m > 12){{m=1;  y++;}}
  calMes = {{year:y, month:m}};
  renderizarCalendario();
  // Al cambiar de mes → vista de mes completo
  periodo = 'mes';
  document.querySelectorAll('.btn-period').forEach(b=>b.classList.remove('active'));
  const pm = document.getElementById('p-mes');
  if(pm) pm.classList.add('active');
  actualizarTodo();
}}

// ── Calendario ──
function renderizarCalendario(){{
  const label = document.getElementById('cal-month-label');
  label.textContent = MESES_ES[calMes.month-1]+' '+calMes.year;

  const scroll = document.getElementById('cal-scroll');
  scroll.innerHTML = '';

  const pad = n => String(n).padStart(2,'0');
  const diasEnMes = new Date(calMes.year, calMes.month, 0).getDate();

  for(let d=1; d<=diasEnMes; d++){{
    const f   = `${{calMes.year}}-${{pad(calMes.month)}}-${{pad(d)}}`;
    const obj = CLIMA.dias[f];
    const dat = obj && obj[sensor] && Object.keys(obj[sensor]).length > 0 ? obj[sensor] : null;

    const diaObj = new Date(calMes.year, calMes.month-1, d);
    const dnom   = DIAS_ES[diaObj.getDay()];

    const div = document.createElement('div');
    div.className = 'cal-day' + (!dat ? ' no-data' : '') + (f===diaSelec ? ' active' : '');
    if(dat) div.dataset.fecha = f;
    div.innerHTML = `
      <span class="cal-dname">${{dnom}}</span>
      <span class="cal-dnum">${{d}}</span>
      <span class="cal-ico">${{dat ? dat.icono||'—' : '·'}}</span>
      <span class="cal-tmax">${{dat && dat.temp_max!=null ? dat.temp_max.toFixed(0)+'°':'—'}}</span>
      <span class="cal-tmin">${{dat && dat.temp_min!=null ? dat.temp_min.toFixed(0)+'°':'—'}}</span>`;
    scroll.appendChild(div);
  }}

  // Auto-scroll al día seleccionado
  if(diaSelec){{
    const d = parseInt(diaSelec.split('-')[2]);
    if(scroll.children[d-1]) scroll.children[d-1].scrollIntoView({{inline:'center',behavior:'smooth'}});
  }}
}}

// Delegación de eventos: un solo listener en el contenedor
function _initCalListener(){{
  const scroll = document.getElementById('cal-scroll');
  if(!scroll || scroll._calInit) return;
  scroll._calInit = true;
  scroll.addEventListener('click', function(e){{
    const dayEl = e.target.closest('.cal-day:not(.no-data)');
    if(!dayEl || !dayEl.dataset.fecha) return;
    seleccionarDia(dayEl.dataset.fecha, dayEl);
  }});
}}

function seleccionarDia(f, el){{
  diaSelec = f;
  document.querySelectorAll('.cal-day').forEach(e=>e.classList.remove('active'));
  if(el) el.classList.add('active');
  // Al seleccionar un día concreto → vista de día
  periodo = 'dia';
  document.querySelectorAll('.btn-period').forEach(b=>b.classList.remove('active'));
  const pd = document.getElementById('p-dia');
  if(pd) pd.classList.add('active');
  // Sincronizar input de fecha en navbar
  const inp = document.getElementById('nav-cal-input');
  if(inp) inp.value = f;
  actualizarTodoSinScroll();
}}

// ── Recolectar datos según período ──
function obtenerDatos(){{
  const fechas = fechasConSensor(sensor);
  if(!fechas.length) return [];

  if(periodo==='dia'){{
    if(!diaSelec || !CLIMA.dias[diaSelec]?.[sensor]) return [];
    return [{{fecha:diaSelec, d:CLIMA.dias[diaSelec][sensor]}}];
  }}
  if(periodo==='mes'){{
    const pref = diaSelec ? diaSelec.slice(0,7) : fechas[fechas.length-1].slice(0,7);
    return fechas.filter(f=>f.startsWith(pref))
                 .map(f=>({{fecha:f, d:CLIMA.dias[f][sensor]}}));
  }}
  if(periodo==='anio'){{
    const anio = diaSelec ? diaSelec.slice(0,4) : fechas[fechas.length-1].slice(0,4);
    return fechas.filter(f=>f.startsWith(anio))
                 .map(f=>({{fecha:f, d:CLIMA.dias[f][sensor]}}));
  }}
  // todo
  return fechas.map(f=>({{fecha:f, d:CLIMA.dias[f][sensor]}}));
}}

function _avg(arr){{
  const v = arr.filter(x=>x!=null && !isNaN(x));
  if(!v.length) return null;
  return v.reduce((a,b)=>a+b,0)/v.length;
}}
function _sum(arr){{
  const v = arr.filter(x=>x!=null && !isNaN(x));
  return v.reduce((a,b)=>a+b,0);
}}

// ══════════════════════════════════════════════════════════════════════
// GRÁFICOS PRINCIPALES — uPlot (Canvas 2D, ultra-rápido, pan+zoom)
// ══════════════════════════════════════════════════════════════════════

let uMain  = null;   // instancia uPlot principal
let uSolar = null;   // instancia uPlot solar
let _uMainData  = null;  // datos crudos para zoom
let _uSolarData = null;

// ── Paleta ──────────────────────────────────────────────────────────
const C = {{
  temp   : '#f87171',
  hum    : '#38bdf8',
  solar  : '#fbbf24',
  lluvia : '#60a5fa',
  viento : '#a78bfa',
  presion: '#6ee7b7',
  grid   : 'rgba(255,255,255,.05)',
  axis   : '#475569',
  bg     : 'transparent',
}};

// ── Convertir etiquetas de tiempo a timestamps Unix (uPlot los requiere) ──
function etiquetasATimestamps(labels, esDia, fechaBase){{
  // esDia: labels son "HH:MM"   → baseDate + offset minutos
  // !esDia: labels son "MM-DD"  → año del período seleccionado
  return labels.map((l, i) => {{
    if(esDia){{
      const [h, m] = l.split(':').map(Number);
      const d = new Date(fechaBase + 'T00:00:00');
      d.setHours(h, m, 0, 0);
      return d.getTime() / 1000;
    }} else {{
      // l = "MM-DD", necesitamos el año
      const anio = diaSelec ? diaSelec.slice(0,4) : '2025';
      return new Date(anio + '-' + l + 'T12:00:00').getTime() / 1000;
    }}
  }});
}}

// ── Opciones comunes uPlot ───────────────────────────────────────────
function mkUOpts(containerId, titulo, series, height){{
  const W = document.getElementById(containerId)?.offsetWidth || 800;
  return {{
    width:  W,
    height: height || 220,
    title:  '',
    cursor: {{
      sync: {{ key: 'clima-sync' }},
      drag: {{ x:true, y:false, uni:10 }},
    }},
    select: {{ show:true }},
    legend: {{ show:true, live:true, markers:{{ width:2 }} }},
    scales: {{
      x: {{ time:true }},
    }},
    axes: [
      {{
        stroke:    C.axis,
        grid:      {{ stroke:C.grid, width:1 }},
        ticks:     {{ stroke:C.axis }},
        font:      '10px Outfit, sans-serif',
        values:    (u, vals) => vals.map(v => {{
          if(v == null) return '';
          const d = new Date(v * 1000);
          const h = d.getHours(), mi = d.getMinutes();
          const mo = d.getMonth()+1, dy = d.getDate();
          // Si hay horas, mostrar HH:MM, si no MM/DD
          return (h>0||mi>0) ? String(h).padStart(2,'0')+':'+String(mi).padStart(2,'0')
                              : String(mo)+'/'+String(dy).padStart(2,'0');
        }}),
      }},
      {{
        stroke:    series[0]?.stroke || C.temp,
        grid:      {{ stroke:C.grid, width:1 }},
        ticks:     {{ stroke:C.axis }},
        font:      '10px Outfit, sans-serif',
      }},
    ],
    series,
    hooks: {{
      ready: [u => {{
        // Pan con click+drag (el mousedown se define después del wheel)
        const over = u.over;
        let dragging = false, startX = 0, startMin, startMax;
        window.addEventListener('mousemove', e => {{
          if(!dragging) return;
          const dx     = e.clientX - startX;
          const range  = startMax - startMin;
          const pxRange = over.offsetWidth;
          const shift  = -(dx / pxRange) * range;
          u.setScale('x', {{ min: startMin+shift, max: startMax+shift }});
        }});
        window.addEventListener('mouseup', () => {{ dragging = false; }});

        // ── Wheel: clic sobre la gráfica la activa; si ya está activa hace zoom ──
        // passive:false en el card padre para poder llamar preventDefault siempre
        const card = over.closest('.uplot-card');
        card.addEventListener('wheel', e => {{
          if(!card.classList.contains('chart-active')){{
            // Primer contacto con la rueda → activar la gráfica
            e.preventDefault();
            const idCard = card.id.replace('card-','');
            toggleChartActive(idCard);
            return;
          }}
          // Ya activa → hacer zoom
          e.preventDefault();
          const sc    = u.scales.x;
          const range = sc.max - sc.min;
          const factor = e.deltaY > 0 ? 1.25 : 0.8;
          const rect  = over.getBoundingClientRect();
          const ratio = (e.clientX - rect.left) / rect.width;
          const pivot = sc.min + ratio * range;
          const newRange = range * factor;
          u.setScale('x', {{
            min: pivot - ratio * newRange,
            max: pivot + (1-ratio) * newRange
          }});
        }}, {{ passive:false }});

        // Drag pan — SOLO si activo
        over.addEventListener('mousedown', e => {{
          if(!card.classList.contains('chart-active')) return;
          if(e.button !== 0) return;
          dragging = true;
          startX   = e.clientX;
          const sc = u.scales.x;
          startMin = sc.min; startMax = sc.max;
        }});

        // Clic simple fuera del drag → activar/desactivar
        over.addEventListener('click', e => {{
          if(!card.classList.contains('chart-active')){{
            const idCard = card.id.replace('card-','');
            toggleChartActive(idCard);
          }}
        }});

        // Doble clic → reset de zoom (la gráfica ya está activa por el clic previo)
        over.addEventListener('dblclick', () => {{
          u.setScale('x', {{ min: u.data[0][0], max: u.data[0][u.data[0].length-1] }});
        }});
      }}]
    }}
  }};
}}

// ── Toggle activación de gráfica (zoom/pan) ─────────────────────────
function toggleChartActive(id){{
  const card = document.getElementById('card-'+id);
  const btn  = document.getElementById('btn-act-'+id);
  const hint = document.getElementById('hint-'+id);
  if(!card) return;

  const wasActive = card.classList.contains('chart-active');

  // Desactivar TODOS los cards primero
  document.querySelectorAll('.uplot-card').forEach(c => {{
    c.classList.remove('chart-active');
  }});
  document.querySelectorAll('.btn-activate').forEach(b => {{
    b.classList.remove('on');
    b.innerHTML = '<span class="dot"></span> Activar';
  }});
  document.querySelectorAll('.zoom-hint').forEach(h => {{
    h.textContent = 'Clic para activar · Rueda para zoom · Arrastra para pan';
  }});

  // Si no estaba activo, activar este
  if(!wasActive){{
    card.classList.add('chart-active');
    if(btn){{
      btn.classList.add('on');
      btn.innerHTML = '<span class="dot"></span> Activa';
    }}
    if(hint) hint.textContent = '🔓 Activa — Rueda: zoom · Arrastrar: pan · Doble clic: reset · Clic fuera: desactivar';
  }}
}}

// ── Botones de zoom (±20%) ───────────────────────────────────────────
function uZoom(id, factor){{
  const u = id==='main' ? uMain : uSolar;
  if(!u) return;
  const sc = u.scales.x;
  const mid = (sc.min + sc.max) / 2;
  const half = (sc.max - sc.min) / 2 * factor;
  u.setScale('x', {{ min: mid-half, max: mid+half }});
}}
function uZoomIn(id)  {{ uZoom(id, 0.75); }}
function uZoomOut(id) {{ uZoom(id, 1.35); }}
function uZoomReset(id){{
  const u = id==='main' ? uMain : uSolar;
  if(!u) return;
  u.setScale('x', {{ min: u.data[0][0], max: u.data[0][u.data[0].length-1] }});
}}

// ── Destruir instancia uPlot y limpiar contenedor ────────────────────
function destroyU(id){{
  if(id==='main')  {{ if(uMain)  {{ uMain.destroy();  uMain=null;  }} }}
  if(id==='solar') {{ if(uSolar) {{ uSolar.destroy(); uSolar=null; }} }}
  const el = document.getElementById('uplot-'+id);
  if(el) el.innerHTML = '';
}}

// ── Construir datos uPlot [[ts...],[s1...],[s2...]] ──────────────────
function buildUData(labels, seriesArrays, esDia, fechaBase){{
  const ts = etiquetasATimestamps(labels, esDia, fechaBase);
  return [ts, ...seriesArrays.map(arr =>
    arr.map(v => (v == null || isNaN(v)) ? null : v)
  )];
}}

// ── GRÁFICO PRINCIPAL uPlot ──────────────────────────────────────────
function actualizarGrafico(datos){{
  destroyU('main');
  destroyU('solar');
  if(!datos.length) return;

  const esDia    = periodo==='dia' && datos.length===1
                   && datos[0].d.horas && datos[0].d.horas.t?.length > 0;
  const fechaBase= esDia ? datos[0].fecha : (diaSelec||datos[0].fecha);
  const pref     = esDia ? datos[0].fecha
                         : periodo.charAt(0).toUpperCase()+periodo.slice(1)
                           +' ('+sensor+')';

  // ── Etiquetas eje X ──
  let labels = esDia
    ? (datos[0].d.horas?.t || [])
    : datos.map(e=>e.fecha.slice(5));

  // ── Extractores ──
  // horas en formato columnar: {{t:[...], temp:[...], hum:[...], ...}}
  const serieHora = c => (datos[0].d.horas?.[c] || datos[0].d.horas?.t?.map(()=>null) || []);
  const seriaDia  = c => datos.map(e=>{{ const v=e.d[c]; return (v!=null&&!isNaN(v))?v:null; }});
  const get       = c => esDia ? serieHora(c) : seriaDia(c);

  // ──────────────────────────────────────────────────────────────────
  // GRÁFICO PRINCIPAL: Temperatura + Humedad (o variable de tab)
  // ──────────────────────────────────────────────────────────────────
  let s1=[], s2=[], tituloMain='', uSeriesMain=[];
  const isGeneral = tabActiva==='general' || tabActiva==='hum';

  if(isGeneral){{
    s1 = get('temp'); s2 = get('hum');
    tituloMain = 'Temperatura y Humedad — '+pref;
    uSeriesMain = [
      {{ label:'Temp (°C)',  stroke:C.temp,    fill:'rgba(248,113,113,.10)', width:2 }},
      {{ label:'Hum (%)',    stroke:C.hum,     fill:'rgba(56,189,248,.06)',  width:1.5,
         scale:'hum', value:(u,v)=>v!=null?v.toFixed(1)+'%':'—' }},
    ];
  }} else if(tabActiva==='lluvia'){{
    s1 = get('lluvia');
    tituloMain = 'Precipitación (mm) — '+pref;
    uSeriesMain = [{{ label:'Lluvia (mm)', stroke:C.lluvia, fill:'rgba(96,165,250,.15)', width:2 }}];
  }} else if(tabActiva==='viento'){{
    s1 = get('viento');
    tituloMain = 'Viento (km/h) — '+pref;
    uSeriesMain = [{{ label:'Viento (km/h)', stroke:C.viento, fill:'rgba(167,139,250,.12)', width:2 }}];
  }} else if(tabActiva==='presion'){{
    s1 = get('presion');
    tituloMain = 'Presión (mb) — '+pref;
    uSeriesMain = [{{ label:'Presión (mb)', stroke:C.presion, fill:'rgba(110,231,183,.08)', width:2 }}];
  }}

  document.getElementById('chart-title').textContent = tituloMain;

  if(s1.length && uSeriesMain.length){{
    const dataArrays = isGeneral ? [s1, s2] : [s1];
    const uData = buildUData(labels, dataArrays, esDia, fechaBase);
    _uMainData  = uData;

    const opts = mkUOpts('uplot-main', tituloMain, [
      {{ label:'Tiempo' }},
      ...uSeriesMain
    ], 230);

    // Segundo eje Y para humedad
    if(isGeneral){{
      opts.scales['hum'] = {{ range: (u,min,max) => [0, 105] }};
      opts.axes.push({{
        scale:  'hum',
        side:   1,
        stroke: C.hum,
        grid:   {{ show:false }},
        ticks:  {{ stroke:C.axis }},
        font:   '10px Outfit, sans-serif',
        values: (u, vals) => vals.map(v => v!=null ? v.toFixed(0)+'%' : ''),
      }});
    }}

    uMain = new uPlot(opts, uData, document.getElementById('uplot-main'));
  }}

  // ──────────────────────────────────────────────────────────────────
  // GRÁFICO SOLAR: Irradiancia (siempre visible)
  // ──────────────────────────────────────────────────────────────────
  const dsSolar   = get('solar');
  const tituloSol = 'Irradiancia Solar (W/m²) — '+pref;
  document.getElementById('chart-solar-title').textContent = tituloSol;

  const uDataSolar = buildUData(labels, [dsSolar], esDia, fechaBase);
  _uSolarData = uDataSolar;

  const optsSolar = mkUOpts('uplot-solar', tituloSol, [
    {{ label:'Tiempo' }},
    {{ label:'Solar (W/m²)', stroke:C.solar, fill:'rgba(251,191,36,.15)', width:2 }},
  ], 180);

  uSolar = new uPlot(optsSolar, uDataSolar, document.getElementById('uplot-solar'));

  // Redimensionar al ancho real del contenedor
  requestAnimationFrame(()=>{{
    const wMain  = document.getElementById('uplot-main')?.offsetWidth  || 800;
    const wSolar = document.getElementById('uplot-solar')?.offsetWidth || 800;
    if(uMain)  uMain.setSize({{width:wMain,  height:230}});
    if(uSolar) uSolar.setSize({{width:wSolar, height:180}});
  }});
}}

// Redimensionar uPlot al cambiar tamaño de ventana
window.addEventListener('resize', ()=>{{
  requestAnimationFrame(()=>{{
    const wMain  = document.getElementById('uplot-main')?.offsetWidth  || 800;
    const wSolar = document.getElementById('uplot-solar')?.offsetWidth || 800;
    if(uMain)  uMain.setSize({{width:wMain,  height:230}});
    if(uSolar) uSolar.setSize({{width:wSolar, height:180}});
  }});
}});

// ── Widgets ──
function actualizarWidgets(datos){{
  const grid = document.getElementById('widgets-grid');
  grid.innerHTML = '';

  // Calcular valores promedio del período
  const vals = (k) => datos.map(e=>e.d[k]).filter(v=>v!=null&&!isNaN(v));

  const temp    = _avg(vals('temp'));
  const temp_mx = Math.max(...vals('temp_max').filter(v=>v!=null), ...[NaN]);
  const temp_mn = Math.min(...vals('temp_min').filter(v=>v!=null), ...[NaN]);
  const hum     = _avg(vals('hum'));
  const lluvia  = _sum(vals('lluvia'));
  const viento  = _avg(vals('viento'));
  const vMax    = Math.max(...vals('viento_max').filter(v=>v!=null),...[NaN]);
  const presion = _avg(vals('presion'));
  const hi      = _avg(vals('heat_index'));
  const rocio   = _avg(vals('rocio'));
  const solar   = _avg(vals('solar'));

  // Datos del día seleccionado para luna y sol
  const dFecha = diaSelec || (datos.length ? datos[datos.length-1].fecha : null);
  const luna   = dFecha ? CLIMA.fases_lunares[dFecha] : null;
  const sol    = dFecha ? CLIMA.sol[dFecha] : null;

  const icono_dir = (d)=>{{
    if(!d||d==='N/D') return '';
    const m={{'N':'↑','NNE':'↗','NE':'↗','ENE':'→','E':'→','ESE':'→',
              'SE':'↘','SSE':'↘','S':'↓','SSW':'↙','SW':'↙','WSW':'←',
              'W':'←','WNW':'←','NW':'↖','NNW':'↖'}};
    return (m[d.toUpperCase()]||'')+'&nbsp;'+d;
  }};

  const dir_v = datos.length===1 ? datos[0].d.dir_viento : '—';

  function widget(ico, badge, badgeColor, label, val, unit, sub, analysis, extra=''){{
    const div = document.createElement('div');
    div.className = 'widget';
    div.innerHTML = `
      <div class="w-ico-row">
        <span class="w-ico">${{ico}}</span>
        ${{badge ? `<span class="w-badge" style="background:${{badgeColor}}22;color:${{badgeColor}}">${{badge}}</span>` : ''}}
      </div>
      <div class="w-label">${{label}}</div>
      <div class="w-value">${{val!=null&&!isNaN(val)?Number(val).toFixed(1):'—'}}<span class="w-unit">${{unit}}</span></div>
      ${{sub ? `<div class="w-sub">${{sub}}</div>` : ''}}
      ${{analysis ? `<div class="w-analysis">${{analysis}}</div>` : ''}}
      ${{extra}}`;
    grid.appendChild(div);
    return div;
  }}

  // 1) Temperatura
  const tSub = (temp_mx&&!isNaN(temp_mx)?'▲ '+temp_mx.toFixed(0)+'° ':'')
             + (temp_mn&&!isNaN(temp_mn)?'▼ '+temp_mn.toFixed(0)+'°':'');
  widget('🌡️', temp!=null?temp.toFixed(0)+'°':'', '#f87171', 'Temperatura exterior',
    temp, '°C', tSub + (hi!=null&&!isNaN(hi) ? ' · Sensación '+hi.toFixed(0)+'°' : ''),
    temp!=null?CLIMA.dias[dFecha||'']?.[sensor]?.analisis?.temp:'',
    '<div class="spark-wrap"><canvas id="spark-temp"></canvas></div>');

  // 2) Humedad
  const humLabel = hum!=null ?
    (hum<30?'Muy seco':hum<50?'Agradable':hum<65?'Confortable':hum<80?'Algo húmedo':'Muy húmedo') : '';
  const divHum = widget('💧', humLabel, '#38bdf8', 'Humedad exterior', hum, '%',
    rocio!=null&&!isNaN(rocio) ? 'Punto de rocío: '+rocio.toFixed(1)+'°C' : '',
    hum!=null?CLIMA.dias[dFecha||'']?.[sensor]?.analisis?.hum:'',
    '<div class="spark-wrap"><canvas id="spark-hum"></canvas></div>');
  // Mini barra humedad
  if(hum!=null&&!isNaN(hum)){{
    const barra = document.createElement('div');
    barra.style.cssText='height:4px;border-radius:2px;margin-top:8px;overflow:hidden;background:rgba(255,255,255,.08)';
    const fill = document.createElement('div');
    fill.style.cssText=`width:${{hum.toFixed(0)}}%;height:100%;background:linear-gradient(90deg,#38bdf8,#4ade80);border-radius:2px`;
    barra.appendChild(fill);
    divHum.appendChild(barra);
  }}

  // 3) Precipitación
  widget('🌧️', lluvia>5?'Lluvia':'Sin lluvia', '#60a5fa', 'Precipitación',
    lluvia, 'mm', periodo==='dia'?'Total del día':'Total del período',
    datos.length===1&&datos[0].d.analisis?datos[0].d.analisis.lluvia:'',
    '<div class="spark-wrap"><canvas id="spark-lluvia"></canvas></div>');

  // 4) Viento
  const divViento = widget('💨', dir_v&&dir_v!=='N/D'?icono_dir(dir_v):'', '#a78bfa',
    'Viento promedio', viento, 'km/h',
    vMax&&!isNaN(vMax)?'Ráfaga máx: '+vMax.toFixed(0)+' km/h':'',
    datos.length===1&&datos[0].d.analisis?datos[0].d.analisis.viento:'',
    '<div class="spark-wrap"><canvas id="spark-viento"></canvas></div>');



  // 6) Presión
  const presLbl = presion==null?'':presion<1000?'Baja':presion<1013?'Normal-baja':presion<1020?'Normal':'Alta';
  widget('🧭', presLbl, '#6ee7b7', 'Presión barométrica', presion, 'mb', '',
    datos.length===1&&datos[0].d.analisis?datos[0].d.analisis.presion:'',
    '<div class="spark-wrap"><canvas id="spark-presion"></canvas></div>');

  // 7) Sol (trayectoria SVG)
  const solDiv = document.createElement('div');
  solDiv.className = 'widget sun-widget';
  const am = sol?.amanecer||'--:--', oc = sol?.ocaso||'--:--', dur = sol?.duracion_h||0;
  // Calcular posición del sol (fracción del día)
  function hmToFrac(s){{
    if(!s||s==='N/A') return 0.5;
    const [h,m] = s.split(':').map(Number);
    return (h + (m||0)/60) / 24;
  }}
  const fAm = hmToFrac(am), fOc = hmToFrac(oc);
  // Generar arco SVG del sol
  const arc = (() => {{
    const W=260, H=70, pad=20;
    const xAm = pad + fAm*(W-2*pad), xOc = pad + fOc*(W-2*pad);
    const cx=(xAm+xOc)/2, cy=H-10, rx=(xOc-xAm)/2, ry=H-20;
    return `M${{xAm}},${{cy}} A${{rx}},${{ry}} 0 0,1 ${{xOc}},${{cy}}`;
  }})();

  solDiv.innerHTML = `
    <div class="w-ico-row"><span class="w-ico">🌅</span></div>
    <div class="w-label">Trayectoria Solar · San Salvador</div>
    <svg id="sol-svg" viewBox="0 0 260 70">
      <defs><linearGradient id="sg" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" style="stop-color:#f97316"/>
        <stop offset="50%" style="stop-color:#fbbf24"/>
        <stop offset="100%" style="stop-color:#f97316"/>
      </linearGradient></defs>
      <line x1="20" y1="60" x2="240" y2="60" stroke="rgba(255,255,255,.1)" stroke-width="1"/>
      <path d="${{arc}}" fill="none" stroke="url(#sg)" stroke-width="2" stroke-dasharray="4 2"/>
      <text x="20" y="68" font-size="8" fill="#f97316">↑</text>
      <text x="235" y="68" font-size="8" fill="#f97316">↓</text>
    </svg>
    <div class="sun-times">
      <span>🌅 ${{am}}</span>
      <span>⏱ ${{dur.toFixed(1)}} h luz</span>
      <span>🌇 ${{oc}}</span>
    </div>`;
  grid.appendChild(solDiv);

  // 8) Fase lunar
  const moonDiv = document.createElement('div');
  moonDiv.className='widget';
  moonDiv.innerHTML=`
    <div class="w-ico-row"><span class="w-ico">🌙</span></div>
    <div class="w-label">Fase Lunar · Ecuación Conway</div>
    <div class="moon-face">${{luna?.emoji||'🌑'}}</div>
    <div class="w-value" style="font-size:1rem">${{luna?.nombre||'—'}}</div>
    <div class="w-sub">Fase: ${{luna? (luna.fase*100).toFixed(0)+'%' : '—'}}</div>
    <div class="w-analysis">Calculado por algoritmo de Conway sin librerías externas.</div>`;
  grid.appendChild(moonDiv);

  // ── Sparklines animados en widgets ────────────────────────────────
  // Se dibujan tras un pequeño delay para que el DOM esté listo
  requestAnimationFrame(()=>{{
    const sparkDefs = [
      {{ id:'spark-temp',    vals: datos.map(e=>e.d.temp),    color:'#f87171' }},
      {{ id:'spark-hum',     vals: datos.map(e=>e.d.hum),     color:'#38bdf8' }},
      {{ id:'spark-lluvia',  vals: datos.map(e=>e.d.lluvia),  color:'#60a5fa' }},
      {{ id:'spark-viento',  vals: datos.map(e=>e.d.viento),  color:'#a78bfa' }},
      {{ id:'spark-presion', vals: datos.map(e=>e.d.presion), color:'#6ee7b7' }},
    ];

    sparkDefs.forEach(def => dibujarSparkline(def.id, def.vals, def.color));
  }});
}}

// ── Motor de sparkline (Canvas 2D, animado) ──────────────────────────
function dibujarSparkline(canvasId, rawVals, color){{
  const canvas = document.getElementById(canvasId);
  if(!canvas) return;
  const vals = rawVals.filter(v=>v!=null&&!isNaN(v));
  if(vals.length < 2) return;

  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.offsetWidth  || canvas.parentElement?.offsetWidth  || 160;
  const H   = canvas.offsetHeight || 40;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  let vmin = vals[0], vmax = vals[0];
  for(const v of vals){{ if(v<vmin) vmin=v; if(v>vmax) vmax=v; }}
  const range = vmax - vmin || 1;

  const n  = vals.length;
  const xS = W / (n - 1);
  const pad = 4;

  function getX(i){{ return i * xS; }}
  function getY(v){{ return H - pad - ((v - vmin) / range) * (H - 2*pad); }}

  // Animación de entrada: dibuja de izquierda a derecha en ~500ms
  let progress = 0;
  const duration = 500;
  let startTime = null;

  function frame(ts){{
    if(!startTime) startTime = ts;
    progress = Math.min(1, (ts - startTime) / duration);
    // ease-out
    const p = 1 - Math.pow(1 - progress, 3);
    const maxI = Math.max(1, Math.floor(p * (n-1)));

    ctx.clearRect(0, 0, W, H);

    // Área rellena (gradiente vertical)
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0,   color + '55');
    grad.addColorStop(1,   color + '00');
    ctx.beginPath();
    ctx.moveTo(getX(0), H);
    ctx.lineTo(getX(0), getY(vals[0]));
    for(let i=1; i<=maxI; i++){{
      const xc = (getX(i-1)+getX(i))/2;
      ctx.quadraticCurveTo(getX(i-1), getY(vals[i-1]), xc, (getY(vals[i-1])+getY(vals[i]))/2);
    }}
    ctx.lineTo(getX(maxI), H);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Línea
    ctx.beginPath();
    ctx.moveTo(getX(0), getY(vals[0]));
    for(let i=1; i<=maxI; i++){{
      const xc = (getX(i-1)+getX(i))/2;
      ctx.quadraticCurveTo(getX(i-1), getY(vals[i-1]), xc, (getY(vals[i-1])+getY(vals[i]))/2);
    }}
    ctx.strokeStyle = color;
    ctx.lineWidth   = 1.5;
    ctx.stroke();

    // Punto final (valor actual)
    const xi = getX(maxI), yi = getY(vals[maxI]);
    ctx.beginPath();
    ctx.arc(xi, yi, 3, 0, Math.PI*2);
    ctx.fillStyle = color;
    ctx.fill();

    if(progress < 1) requestAnimationFrame(frame);
  }}
  requestAnimationFrame(frame);
}}

// ── actualizarTodo se define en el bloque lazy más abajo ──

// ── Setter sensor (tab/período definidos en el bloque lazy más abajo) ──
function setSensor(s){{
  sensor = s;
  ['eep','ues'].forEach(x=>document.getElementById('btn-'+x).classList.remove('active'));
  document.getElementById('btn-'+s.toLowerCase()).classList.add('active');
  _acadCargado = false;   // forzar re-render académico al cambiar sensor
  init();
}}

// ══════════════════════════════════════════════════════════════════════
// GRÁFICOS ACADÉMICOS DINÁMICOS
// ══════════════════════════════════════════════════════════════════════

let acadVar = 'temp';
let chartSerie = null, chartHist = null, chartBox = null, chartDisp = null;

const ACAD_META = {{
  temp:    {{ clave:'temp',    label:'Temperatura',      unit:'°C',    color:'#f87171' }},
  hum:     {{ clave:'hum',     label:'Humedad',           unit:'%',     color:'#38bdf8' }},
  solar:   {{ clave:'solar',   label:'Radiación Solar',   unit:'W/m²',  color:'#fbbf24' }},
  lluvia:  {{ clave:'lluvia',  label:'Precipitación',     unit:'mm',    color:'#60a5fa' }},
  viento:  {{ clave:'viento',  label:'Viento',            unit:'km/h',  color:'#a78bfa' }},
  presion: {{ clave:'presion', label:'Presión',           unit:'mb',    color:'#6ee7b7' }},
}};

function setAcadVar(v){{
  acadVar = v;
  document.querySelectorAll('[id^="av-"]').forEach(b=>b.classList.remove('active'));
  const btn = document.getElementById('av-'+v);
  if(btn) btn.classList.add('active');
  const datos = obtenerDatos();
  actualizarGraficosAcad(datos);
}}

// ── Helpers Chart.js ─────────────────────────────────────────────────
const CHART_OPTS = {{
  responsive:true, animation:false,
  plugins:{{legend:{{display:false}},tooltip:{{mode:'index',intersect:false}}}},
  scales:{{
    x:{{ticks:{{color:'#64748b',maxTicksLimit:18,font:{{size:9}}}},
       grid:{{color:'rgba(255,255,255,.04)'}}}},
    y:{{ticks:{{color:'#64748b',font:{{size:9}}}},
       grid:{{color:'rgba(255,255,255,.04)'}}}},
  }}
}};

function mkChart(id, type, labels, datasets, extraOpts){{
  try {{
    const canvas = document.getElementById(id);
    if(!canvas) return null;
    if(typeof Chart === 'undefined') {{
      _mostrarErrorCanvas(canvas, 'Chart.js no disponible');
      return null;
    }}
    const ctx = canvas.getContext('2d');
    const existing = Chart.getChart(canvas);
    if(existing) existing.destroy();
    return new Chart(ctx, {{
      type,
      data: {{labels, datasets}},
      options: Object.assign({{}}, CHART_OPTS, extraOpts||{{}})
    }});
  }} catch(e) {{
    console.error('mkChart [' + id + ']:', e);
    const cv = document.getElementById(id);
    if(cv) _mostrarErrorCanvas(cv, 'Error: ' + e.message);
    return null;
  }}
}}

function _mostrarErrorCanvas(canvas, msg){{
  try {{
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle='rgba(248,113,113,.3)';
    ctx.font='12px Outfit,sans-serif';
    ctx.textAlign='center';
    ctx.fillText(msg, canvas.width/2, canvas.height/2);
  }} catch(e) {{}}
}}

// ── Histograma manual (Regla de Sturges) ────────────────────────────
function calcHistograma(vals){{
  if(!vals.length) return {{labels:[], freqs:[]}};
  const n   = vals.length;
  const k   = Math.max(5, Math.ceil(Math.log2(n) + 1));
  let vmin  = vals[0], vmax = vals[0];
  for(const v of vals){{ if(v<vmin) vmin=v; if(v>vmax) vmax=v; }}
  const ancho = (vmax - vmin) / k || 1;
  const freq  = new Array(k).fill(0);
  for(const v of vals){{
    let i = Math.floor((v - vmin) / ancho);
    if(i >= k) i = k - 1;
    freq[i]++;
  }}
  const labels = Array.from({{length:k}}, (_,i) =>
    (vmin + i*ancho).toFixed(1) + '–' + (vmin + (i+1)*ancho).toFixed(1));
  return {{labels, freqs: freq, vmin, vmax, ancho, k}};
}}

// ── Boxplot mensual (datos → per-month P25/P50/P75/whiskers) ────────
function calcBoxplot(datos, clave){{
  // Agrupar por mes YYYY-MM
  const grupos = {{}};
  for(const {{fecha, d}} of datos){{
    if(!d) continue;
    const mes = fecha.slice(0,7);
    if(!grupos[mes]) grupos[mes]=[];
    const v = d[clave];
    if(v!=null && !isNaN(v)) grupos[mes].push(v);
  }}
  // Si modo día: agrupar horas del día
  if(periodo==='dia' && datos.length===1 && datos[0].d.horas?.t?.length){{
    const horas = datos[0].d.horas;
    grupos['horas'] = (horas[clave] || []).filter(v=>v!=null&&!isNaN(v));
  }}

  const meses = Object.keys(grupos).sort();
  return meses.map(mes=>{{
    const vals = grupos[mes].slice().sort((a,b)=>a-b);
    const n = vals.length;
    if(!n) return null;
    const pct = (p) => {{
      const L = p/100*(n-1), i=Math.floor(L), f=L-i;
      return i+1<n ? vals[i]+f*(vals[i+1]-vals[i]) : vals[i];
    }};
    const q1=pct(25), q2=pct(50), q3=pct(75);
    const iqr=q3-q1;
    const wLo = vals.find(v=>v>=q1-1.5*iqr) ?? q1;
    const wHi = [...vals].reverse().find(v=>v<=q3+1.5*iqr) ?? q3;
    return {{mes, q1, q2, q3, wLo, wHi, n}};
  }}).filter(Boolean);
}}

// ── Estadísticos del período (manual) ───────────────────────────────
function calcStats(vals){{
  if(!vals.length) return null;
  const n = vals.length;
  let sum=0, vmin=vals[0], vmax=vals[0];
  for(const v of vals){{ sum+=v; if(v<vmin) vmin=v; if(v>vmax) vmax=v; }}
  const media = sum/n;
  let var2=0;
  for(const v of vals) var2 += (v-media)*(v-media);
  var2 /= (n-1);
  const sigma = Math.sqrt(var2);
  const sorted = vals.slice().sort((a,b)=>a-b);
  const pct = (p) => {{
    const L=p/100*(n-1), i=Math.floor(L), f=L-i;
    return i+1<n ? sorted[i]+f*(sorted[i+1]-sorted[i]) : sorted[i];
  }};
  return {{n, media, sigma, varianza:var2, vmin, vmax,
           p25:pct(25), p50:pct(50), p75:pct(75),
           ic_inf: media-1.645*sigma/Math.sqrt(n),
           ic_sup: media+1.645*sigma/Math.sqrt(n)}};
}}

// ── Renderizar todos los gráficos académicos ────────────────────────
function actualizarGraficosAcad(datos){{
  if(!datos || !datos.length) return;

  const meta  = ACAD_META[acadVar] || ACAD_META.temp;
  const clave = meta.clave;
  const color = meta.color;
  const unit  = meta.unit;
  const label = meta.label + (unit ? ' ('+unit+')' : '');
  const c1    = color;
  const c1bg  = color + '26';



  // ── Etiqueta del período en el encabezado ──
  const periodoLabel = periodo==='dia' ? (diaSelec||'—')
    : periodo==='mes' ? (diaSelec ? diaSelec.slice(0,7) : '—')
    : periodo==='anio' ? (diaSelec ? diaSelec.slice(0,4) : '—')
    : 'Histórico completo';
  document.getElementById('acad-head').textContent =
    'Análisis estadístico — ' + periodoLabel + ' · ' + sensor;
  document.getElementById('st-periodo-label').textContent =
    periodoLabel + ' · ' + sensor;

  // ── 1) SERIE TEMPORAL ──
  let serieLabels = [], serieVals = [];
  if(periodo==='dia' && datos.length===1 && datos[0].d.horas?.t?.length){{
    const horas = datos[0].d.horas;
    serieLabels = horas.t;
    serieVals   = (horas[clave] || horas.t.map(()=>null));
  }} else {{
    // Usar datos horarios de todos los días (resample a medias diarias)
    serieLabels = datos.map(e=>e.fecha.slice(5));
    serieVals   = datos.map(e=>{{
      const v = e.d[clave];
      return (v!=null&&!isNaN(v)) ? v : null;
    }});
  }}

  const serieNoVacios = serieVals.filter(v=>v!=null).length;
  document.getElementById('at-serie').textContent =
    serieNoVacios
      ? '📈 Serie temporal — '+label+' · '+periodoLabel+' ('+serieNoVacios+' pts)'
      : '📈 Serie temporal — sin datos para este período';

  if(serieNoVacios > 0){{
    mkChart('acad-serie','line', serieLabels, [{{
      label, data: serieVals,
      borderColor: c1, backgroundColor: c1bg,
      fill:true, tension:.3,
      pointRadius: serieLabels.length > 200 ? 0 : 2,
      borderWidth: serieLabels.length > 200 ? 1 : 1.5
    }}]);
  }} else {{
    const cv = document.getElementById('acad-serie');
    if(cv){{ const ex=Chart.getChart(cv); if(ex) ex.destroy();
      const ctx2=cv.getContext('2d');
      ctx2.clearRect(0,0,cv.width,cv.height);
      ctx2.fillStyle='rgba(100,116,139,.5)';
      ctx2.font='13px Outfit,sans-serif';
      ctx2.textAlign='center';
      ctx2.fillText('Sin datos para este período/variable',cv.width/2,cv.height/2);
    }}
  }}

  // ── 2) HISTOGRAMA (Sturges) ──
  // Recolectar todos los valores numéricos del período
  let allVals = [];
  if(periodo==='dia' && datos.length===1 && datos[0].d.horas?.t?.length){{
    allVals = (datos[0].d.horas[clave] || []).filter(v=>v!=null&&!isNaN(v));
  }} else {{
    for(const {{d}} of datos){{
      const v = d[clave];
      if(v!=null && !isNaN(v)) allVals.push(v);
    }}
  }}

  const hist = calcHistograma(allVals);
  document.getElementById('at-hist').textContent =
    allVals.length
      ? '📊 Histograma k='+hist.k+' (Sturges) — '+label+' (n='+allVals.length+')'
      : '📊 Histograma — sin datos para este período';

  if(allVals.length > 0){{
    mkChart('acad-hist','bar', hist.labels, [{{
      label:'Frecuencia', data: hist.freqs,
      backgroundColor: c1bg, borderColor: c1,
      borderWidth:1.5
    }}], {{
      plugins:{{
        annotation: undefined,
        legend:{{display:false}},
        tooltip:{{callbacks:{{title:l=>l[0].label, label:l=>'Frec: '+l.raw}}}}
      }}
    }});
  }} else {{
    const cv = document.getElementById('acad-hist');
    if(cv){{ const ex=Chart.getChart(cv); if(ex) ex.destroy();
      const ctx2=cv.getContext('2d');
      ctx2.clearRect(0,0,cv.width,cv.height);
      ctx2.fillStyle='rgba(100,116,139,.5)';
      ctx2.font='13px Outfit,sans-serif';
      ctx2.textAlign='center';
      ctx2.fillText('Sin datos para este período/variable',cv.width/2,cv.height/2);
    }}
  }}

  // ── 3) BOXPLOT MENSUAL ──
  const boxData = calcBoxplot(datos, clave);
  const boxLabels = boxData.map(b=>b.mes);

  // Chart.js no tiene boxplot nativo; lo simulamos con
  // barras flotantes (q1→q3) + puntos para mediana y bigotes
  const boxMin  = boxData.map(b=>b.wLo);
  const boxQ1   = boxData.map(b=>b.q1);
  const boxMed  = boxData.map(b=>b.q2);
  const boxQ3   = boxData.map(b=>b.q3);
  const boxMax  = boxData.map(b=>b.wHi);
  // Caja: dataset de barra flotante (base=q1, valor=q3-q1)
  const cajaBase  = boxQ1;
  const cajaAlto  = boxData.map((b,i)=>b.q3-b.q1);

  document.getElementById('at-box').textContent =
    '📦 Boxplot — ' + label + ' · ' + periodoLabel;

  mkChart('acad-box','bar', boxLabels, [
    // Rango total (bigotes): transparente, solo para escala
    {{label:'Mín', data:boxMin, backgroundColor:'transparent',
      borderColor:'transparent', borderWidth:0, stack:'box'}},
    // Espacio q1-min
    {{label:'Bigote inf', data:boxData.map((b,i)=>b.q1-b.wLo),
      backgroundColor:'rgba(100,116,139,.3)', borderColor:'transparent',
      borderWidth:0, stack:'box'}},
    // Caja q1-q3
    {{label:'Caja (Q1-Q3)', data:cajaAlto,
      backgroundColor:c1bg, borderColor:c1,
      borderWidth:1.5, stack:'box'}},
    // Bigote sup
    {{label:'Bigote sup', data:boxData.map(b=>b.wHi-b.q3),
      backgroundColor:'rgba(100,116,139,.3)', borderColor:'transparent',
      borderWidth:0, stack:'box'}},
    // Mediana como línea de puntos
    {{label:'Mediana', data:boxMed,
      type:'line', borderColor:'#fbbf24',
      borderWidth:2, pointRadius:4,
      pointBackgroundColor:'#fbbf24', fill:false, tension:0,
      order:-1}},
  ], {{
    plugins:{{legend:{{display:false}},
      tooltip:{{callbacks:{{
        label: function(ctx){{
          const i=ctx.dataIndex;
          if(!boxData[i]) return '';
          const b=boxData[i];
          return [
            'Mediana: '+b.q2.toFixed(1)+' '+unit,
            'Q1-Q3: '+b.q1.toFixed(1)+' — '+b.q3.toFixed(1),
            'Bigotes: '+b.wLo.toFixed(1)+' — '+b.wHi.toFixed(1),
            'N: '+b.n
          ];
        }}
      }}}}
    }},
    scales:{{
      x:{{stacked:true,ticks:{{color:'#64748b',font:{{size:9}}}},
         grid:{{color:'rgba(255,255,255,.04)'}}}},
      y:{{stacked:false,ticks:{{color:'#64748b',font:{{size:9}}}},
         grid:{{color:'rgba(255,255,255,.04)'}}}},
    }}
  }});

  // ── 4) DISPERSIÓN EEP vs UES ──
  const claveDisp = clave;
  const dispPts = [];
  for(const {{fecha, d}} of datos){{
    const objEEP = CLIMA.dias[fecha]?.EEP;
    const objUES = CLIMA.dias[fecha]?.UES;
    if(!objEEP || !objUES) continue;
    const x = objEEP[claveDisp], y = objUES[claveDisp];
    if(x!=null && y!=null && !isNaN(x) && !isNaN(y))
      dispPts.push({{x, y}});
  }}

  document.getElementById('at-disp').textContent =
    '🔀 EEP vs UES — ' + label + ' · ' + periodoLabel
    + ' (n=' + dispPts.length + ')';

  mkChart('acad-disp','scatter', [], [{{
    label: 'EEP vs UES',
    data: dispPts,
    backgroundColor: c1 + '55',
    borderColor: c1,
    borderWidth: 1,
    pointRadius: Math.max(2, Math.min(5, 200/Math.max(dispPts.length,1))),
  }}], {{
    plugins:{{legend:{{display:false}},
      tooltip:{{callbacks:{{label:ctx=>'EEP:'+ctx.raw.x.toFixed(1)+' UES:'+ctx.raw.y.toFixed(1)}}}}}},
    scales:{{
      x:{{title:{{display:true,text:'EEP — '+label,color:'#64748b',font:{{size:9}}}},
         ticks:{{color:'#64748b',font:{{size:9}}}},
         grid:{{color:'rgba(255,255,255,.04)'}}}},
      y:{{title:{{display:true,text:'UES — '+label,color:'#64748b',font:{{size:9}}}},
         ticks:{{color:'#64748b',font:{{size:9}}}},
         grid:{{color:'rgba(255,255,255,.04)'}}}},
    }}
  }});

  // ── 5) TABLA DE ESTADÍSTICOS (pre-computados con C++ AjusteCurvas) ──
  // Para "todo": CLIMA.stats_alias[sensor][acadVar]  (sobre todas las lecturas horarias)
  // Para "mes":  CLIMA.stats_men_alias[sensor][acadVar][mesActivo]
  // Para "anio": agrega todos los meses del año desde stats_men_alias
  // Para "dia":  calcStats(allVals) sobre los valores horarios del día
  const tbody = document.getElementById('acad-stats-body');
  let st = null;
  if(periodo === 'dia'){{
    // Día: stats de lecturas horarias (calcStats manual, pocos puntos)
    st = calcStats(allVals);
  }} else if(periodo === 'todo'){{
    // Histórico completo: usar stats globales pre-computados C++
    const sg = CLIMA.stats_alias?.[sensor]?.[acadVar];
    if(sg){{
      st = {{
        n:        sg.n        || 0,
        media:    sg.media    || 0,
        sigma:    sg.desv_estandar || 0,
        varianza: sg.varianza || 0,
        vmin:     sg.minimo   || 0,
        vmax:     sg.maximo   || 0,
        p25:      sg.p25      || 0,
        p50:      sg.p50      || 0,
        p75:      sg.p75      || 0,
        ic_inf:   sg.ic_inf   || 0,
        ic_sup:   sg.ic_sup   || 0,
      }};
    }}
  }} else if(periodo === 'mes'){{
    const mesActivo = (diaSelec||fechasConSensor(sensor).at(-1)||'').slice(0,7);
    const sm_dict = CLIMA.stats_men_alias?.[sensor]?.[acadVar];
    const sm = sm_dict?.[mesActivo];
    if(sm){{
      st = {{
        n: sm.n||0, media: sm.media||0, sigma: sm.desv||0,
        varianza: (sm.desv||0)*(sm.desv||0),
        vmin: sm.minimo||0, vmax: sm.maximo||0,
        p25: sm.p25||0, p50: sm.p50||0, p75: sm.p75||0,
        ic_inf: (sm.media||0)-1.645*(sm.desv||0)/Math.sqrt(Math.max(sm.n||1,1)),
        ic_sup: (sm.media||0)+1.645*(sm.desv||0)/Math.sqrt(Math.max(sm.n||1,1)),
      }};
    }} else {{
      // Fallback: calcStats de medias diarias del mes
      st = calcStats(allVals);
    }}
  }} else if(periodo === 'anio'){{
    const anioActivo = (diaSelec||fechasConSensor(sensor).at(-1)||'').slice(0,4);
    const sm_dict = CLIMA.stats_men_alias?.[sensor]?.[acadVar];
    if(sm_dict){{
      // Combinar meses del año usando stats globales por mes → media ponderada
      let sumN=0, sumMu=0, sumVar=0, vmin=Infinity, vmax=-Infinity, sumP25=0, sumP50=0, sumP75=0, nM=0;
      for(const [mes, sm] of Object.entries(sm_dict)){{
        if(!mes.startsWith(anioActivo)) continue;
        sumN  += sm.n||0;  sumMu += (sm.media||0)*(sm.n||0);
        sumVar+= (sm.desv||0)*(sm.desv||0)*(Math.max((sm.n||1)-1,1));
        if((sm.minimo||0) < vmin) vmin = sm.minimo||0;
        if((sm.maximo||0) > vmax) vmax = sm.maximo||0;
        sumP25 += sm.p25||0; sumP50 += sm.p50||0; sumP75 += sm.p75||0; nM++;
      }}
      if(sumN > 0){{
        const mu   = sumMu / sumN;
        const sig2 = sumN > 1 ? sumVar / (sumN-1) : 0;
        const sig  = Math.sqrt(sig2);
        st = {{
          n: sumN, media: mu, sigma: sig, varianza: sig2,
          vmin: vmin===Infinity?0:vmin, vmax: vmax===-Infinity?0:vmax,
          p25: sumP25/nM, p50: sumP50/nM, p75: sumP75/nM,
          ic_inf: mu-1.645*sig/Math.sqrt(sumN),
          ic_sup: mu+1.645*sig/Math.sqrt(sumN),
        }};
      }} else {{
        st = calcStats(allVals);
      }}
    }} else {{
      st = calcStats(allVals);
    }}
  }}
  if(tbody){{
    if(!st){{
      tbody.innerHTML = '<tr><td colspan="3" style="color:var(--tx3);text-align:center">Sin datos para este período</td></tr>';
    }} else {{
      const f4 = v => (v!=null&&!isNaN(v)) ? Number(v).toFixed(4) : '—';
      const fi = v => (v!=null&&!isNaN(v)) ? Number(v).toFixed(0) : '—';
      const rows = [
        ['N muestral',                     fi(st.n),                              'lecturas (C++)'],
        ['Media (x̄)',                      f4(st.media),                          unit],
        ['Desv. Est. (σ)',                  f4(st.sigma),                          unit],
        ['Varianza (s²)',                   f4(st.varianza),                       unit+'²'],
        ['Mínimo',                         f4(st.vmin),                           unit],
        ['Máximo',                         f4(st.vmax),                           unit],
        ['Rango (Máx−Mín)',                f4(st.vmax-st.vmin),                   unit],
        ['P25 (Q1)',                       f4(st.p25),                            unit],
        ['Mediana (P50)',                  f4(st.p50),                            unit],
        ['P75 (Q3)',                       f4(st.p75),                            unit],
        ['IQR (Q3−Q1)',                    f4(st.p75-st.p25),                     unit],
        ['IC 90% inferior',               f4(st.ic_inf),                         unit],
        ['IC 90% superior',               f4(st.ic_sup),                         unit],
      ];
      tbody.innerHTML = rows.map(([m,v,u])=>
        `<tr><td>${{m}}</td><td style="font-family:var(--mono);color:var(--blue)">${{v}}</td><td style="color:var(--tx3)">${{u}}</td></tr>`
      ).join('');
    }}
  }}

  // ── 6) MAPA DE CALOR POR HORA ──────────────────────────────────────
  try {{ dibujarHeatmap(datos, clave, unit, c1); }} catch(e) {{}}

  // ── 7) TENDENCIA LINEAL C++ ─────────────────────────────────────────
  try {{ renderTendencia(datos, clave, color, unit); }} catch(e) {{}}

  // ── 8) TABLA MENSUAL COMPLETA ───────────────────────────────────────
  try {{ renderTablaMensual(); }} catch(e) {{}}

  // ── 9) EVENTOS EXTREMOS ────────────────────────────────────────────
  try {{ renderEventosExtremos(datos); }} catch(e) {{}}

  // ── 10) COMPARATIVA EEP vs UES (uPlot interactivo) ─────────────────
  actualizarCompUPlot(datos);
}}

// ══ MAPA DE CALOR POR HORA DEL DÍA (Canvas 2D) ══════════════════════

function dibujarHeatmap(datos, clave, unit, colorStr){{
  const cv = document.getElementById('acad-heatmap');
  if(!cv) return;
  const W = cv.offsetWidth || 800, H = 120;
  cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d');
  ctx.clearRect(0,0,W,H);

  // Acumular valores por hora (0-23) desde datos horarios
  const porHora = Array.from({{length:24}}, ()=>{{return {{sum:0,n:0}}}});
  for(const {{d}} of datos){{
    const horas = d.horas;
    if(!horas || !horas.t) continue;
    horas.t.forEach((t,i)=>{{
      const h = parseInt(t.split(':')[0]);
      const v = horas[clave]?.[i];
      if(v!=null && !isNaN(v) && h>=0 && h<24){{
        porHora[h].sum += v; porHora[h].n++;
      }}
    }});
  }}
  const medias = porHora.map(b=> b.n>0 ? b.sum/b.n : null);
  const vals   = medias.filter(v=>v!=null);
  if(!vals.length){{ ctx.fillStyle='rgba(100,116,139,.3)'; ctx.fillRect(0,0,W,H); return; }}

  let vmin=vals[0], vmax=vals[0];
  vals.forEach(v=>{{ if(v<vmin) vmin=v; if(v>vmax) vmax=v; }});
  const rng = vmax - vmin || 1;

  // Color gradient: frío (azul) → templado (amarillo) → caliente (rojo)
  function colorPct(pct){{
    if(pct < 0.5){{
      const t = pct*2;
      return `rgba(${{Math.round(56+119*t)}},${{Math.round(189-89*t)}},${{Math.round(248-228*t)}},0.9)`;
    }} else {{
      const t = (pct-0.5)*2;
      return `rgba(${{Math.round(175+80*t)}},${{Math.round(100-67*t)}},${{Math.round(20-20*t)}},0.9)`;
    }}
  }}

  const cw = W/24;
  medias.forEach((v,h)=>{{
    if(v==null){{ ctx.fillStyle='rgba(30,41,59,.6)'; ctx.fillRect(h*cw,0,cw,H); return; }}
    const pct = (v-vmin)/rng;
    ctx.fillStyle = colorPct(pct);
    ctx.fillRect(h*cw, 0, cw, H);
    // Valor encima
    ctx.fillStyle='rgba(255,255,255,.9)'; ctx.font=`bold ${{Math.max(9,Math.min(12,cw-2))}}px DM Mono,monospace`;
    ctx.textAlign='center';
    ctx.fillText(v.toFixed(0), h*cw+cw/2, H/2+4);
  }});

  // Barra de color de referencia
  const grad = ctx.createLinearGradient(0,H-14,W,H-14);
  grad.addColorStop(0,'rgba(56,189,248,.8)');
  grad.addColorStop(0.5,'rgba(251,191,36,.8)');
  grad.addColorStop(1,'rgba(248,113,113,.8)');
  ctx.fillStyle=grad; ctx.fillRect(0,H-6,W,6);

  // Etiqueta título del canvas
  const lbl = document.getElementById('heatmap-title');
  if(lbl) lbl.textContent = `🎨 Temperatura media por hora — ${{unit}} · rango ${{vmin.toFixed(1)}}→${{vmax.toFixed(1)}}`;
}}

// ══ TENDENCIA LINEAL C++ ═════════════════════════════════════════════

function renderTendencia(datos, clave, color, unit){{
  // Gráfico de puntos + línea de tendencia pre-computada
  const tend = CLIMA.tendencia?.[sensor]?.[acadVar];
  const labels = datos.map(e=>e.fecha.slice(5));
  const vals   = datos.map(e=>{{const v=e.d[clave];return (v!=null&&!isNaN(v))?v:null;}});
  const noVacios = vals.filter(v=>v!=null);

  const datasets = [{{
    label:'Datos reales', data:vals,
    borderColor:color+'99', backgroundColor:'transparent',
    pointRadius:2, borderWidth:1.5, tension:0, type:'line'
  }}];

  if(tend && datos.length > 1){{
    const b0=tend.b0, b1=tend.b1;
    const trendLine = vals.map((_,i)=>b0+b1*i);
    datasets.push({{
      label:`Tendencia (b₁=${{(b1*30).toFixed(4)}}/mes)`,
      data:trendLine,
      borderColor:'#f87171', backgroundColor:'transparent',
      borderWidth:2, borderDash:[8,4], pointRadius:0, tension:0
    }});
  }}

  mkChart('acad-tendencia','line',labels,datasets,{{
    plugins:{{
      legend:{{display:true,labels:{{color:'#94a3b8',font:{{size:9}}}}}},
      tooltip:{{mode:'index',intersect:false,
        callbacks:{{label:c=>`${{c.dataset.label}}: ${{c.raw!=null?Number(c.raw).toFixed(2):''}} ${{unit}}`}}
      }}
    }},
    scales:{{
      x:{{ticks:{{color:'#64748b',maxTicksLimit:14,font:{{size:9}}}},grid:{{color:'rgba(255,255,255,.04)'}}}},
      y:{{ticks:{{color:'#64748b',font:{{size:9}}}},grid:{{color:'rgba(255,255,255,.04)'}},
         title:{{display:true,text:unit,color:'#64748b',font:{{size:9}}}}}},
    }}
  }});

  // Tabla de tendencias
  const tbody = document.getElementById('tendencia-tbody');
  if(!tbody) return;
  const UNIDADES = {{temp:'°C',hum:'%',solar:'W/m²',lluvia:'mm',viento:'km/h',presion:'mb'}};
  const LABELS   = {{temp:'Temperatura',hum:'Humedad',solar:'Rad. Solar',lluvia:'Precipitación',viento:'Viento',presion:'Presión Barométrica'}};
  const tendAll  = CLIMA.tendencia?.[sensor] || {{}};
  const rows = Object.entries(tendAll).map(([var_, td])=>{{
    const color_ = td.por_mes > 0.05 ? '#f87171' : td.por_mes < -0.05 ? '#60a5fa' : '#6ee7b7';
    return `<tr>
      <td>${{LABELS[var_]||var_}}</td>
      <td style="font-family:var(--mono);color:${{color_}}">${{td.por_mes>0?'+':''}}${{td.por_mes.toFixed(4)}} ${{UNIDADES[var_]||''}}/mes</td>
      <td style="font-family:var(--mono)">${{td.r2.toFixed(4)}}</td>
      <td style="color:${{color_}}">${{td.etiqueta}}</td>
      <td>${{td.n}}</td>
    </tr>`;
  }}).join('');
  tbody.innerHTML = rows || '<tr><td colspan="5" style="color:var(--tx3);text-align:center">Sin datos de tendencia</td></tr>';
}}

// ══ TABLA RESUMEN MENSUAL COMPLETA ═══════════════════════════════════

function renderTablaMensual(){{
  const smAlias = CLIMA.stats_men_alias?.[sensor];
  if(!smAlias) return;
  const thead = document.getElementById('tabla-mensual-head');
  const tbody = document.getElementById('tabla-mensual-body');
  if(!thead || !tbody) return;

  const VARS_ORD = ['temp','hum','solar','lluvia','viento','presion'];
  const LABS = {{temp:'Temp (°C)',hum:'Hum (%)',solar:'Solar (W/m²)',lluvia:'Lluvia (mm)',viento:'Viento (km/h)',presion:'Presión (mb)'}};

  // Encabezado: Mes | Temp_media Temp_max Temp_min | ...
  thead.innerHTML = `<tr>
    <th>Mes</th>
    ${{VARS_ORD.map(v=>`<th colspan="3" style="text-align:center">${{LABS[v]||v}}</th>`).join('')}}
  </tr>
  <tr>
    <th></th>
    ${{VARS_ORD.map(()=>'<th>Media</th><th>Máx</th><th>Mín</th>').join('')}}
  </tr>`;

  // Ordenar meses disponibles
  const meses = new Set();
  VARS_ORD.forEach(v=>{{ if(smAlias[v]) Object.keys(smAlias[v]).forEach(m=>meses.add(m)); }});
  const mesOrden = [...meses].sort();

  const f1 = v => (v!=null&&!isNaN(v)) ? Number(v).toFixed(1) : '—';

  tbody.innerHTML = mesOrden.map(mes=>{{
    const cells = VARS_ORD.map(v=>{{
      const sm = smAlias[v]?.[mes];
      if(!sm) return '<td>—</td><td>—</td><td>—</td>';
      return `<td style="font-family:var(--mono)">${{f1(sm.media)}}</td>
              <td style="font-family:var(--mono);color:#f87171">${{f1(sm.maximo)}}</td>
              <td style="font-family:var(--mono);color:#60a5fa">${{f1(sm.minimo)}}</td>`;
    }}).join('');
    return `<tr><td style="font-family:var(--mono);white-space:nowrap">${{mes}}</td>${{cells}}</tr>`;
  }}).join('');
}}

// ══ EVENTOS EXTREMOS ═════════════════════════════════════════════════

function renderEventosExtremos(datos){{
  const UMBRALES = [
    {{alias:'temp',  label:'Ola de calor',   cond:v=>v>=33,  desc:'Temperatura ≥ 33°C', icon:'🌡🔴', color:'#f87171'}},
    {{alias:'temp',  label:'Frío inusual',   cond:v=>v<=18,  desc:'Temperatura ≤ 18°C', icon:'❄️',   color:'#60a5fa'}},
    {{alias:'lluvia',label:'Lluvia intensa', cond:v=>v>=5,   desc:'Precipitación ≥ 5 mm',icon:'🌧🔵',color:'#60a5fa'}},
    {{alias:'solar', label:'Solar máxima',   cond:v=>v>=800, desc:'Radiación ≥ 800 W/m²',icon:'☀🟡',color:'#fbbf24'}},
    {{alias:'viento',label:'Viento fuerte',  cond:v=>v>=25,  desc:'Viento ≥ 25 km/h',  icon:'💨⚪', color:'#a78bfa'}},
    {{alias:'presion',label:'Presión baja',  cond:v=>v<=1008,desc:'Presión ≤ 1008 mb',  icon:'🧭⬇', color:'#fbbf24'}},
  ];
  const total = datos.length || 1;
  const badgesEl = document.getElementById('extremos-badges');
  const tbody = document.getElementById('extremos-tbody');
  if(!tbody) return;

  const resultados = UMBRALES.map(u=>{{
    const dias_ev = datos.filter(e=>{{
      const v=e.d[u.alias]; return v!=null && !isNaN(v) && u.cond(v);
    }});
    const ultimo = dias_ev.length ? dias_ev[dias_ev.length-1].fecha : null;
    return {{...u, n:dias_ev.length, ultimo}};
  }});

  if(badgesEl){{
    badgesEl.innerHTML = resultados.map(r=>
      `<div class="pred-badge" style="border-color:${{r.color}}22">
        <div class="pred-badge-label">${{r.icon}} ${{r.label}}</div>
        <div class="pred-badge-val" style="color:${{r.color}}">${{r.n}} días (${{(r.n/total*100).toFixed(1)}}%)</div>
      </div>`
    ).join('');
  }}

  tbody.innerHTML = resultados.map(r=>
    `<tr>
      <td style="color:${{r.color}}">${{r.icon}} ${{r.label}}</td>
      <td>${{r.desc}}</td>
      <td style="font-family:var(--mono)">${{r.n}}</td>
      <td style="font-family:var(--mono)">${{(r.n/total*100).toFixed(2)}}%</td>
      <td style="font-family:var(--mono);color:var(--tx2)">${{r.ultimo||'—'}}</td>
    </tr>`
  ).join('');
}}

// ── Comparativa EEP vs UES sobre uPlot ──────────────────────────────
let uComp = null;

function actualizarCompUPlot(datos){{
  // Destruir instancia anterior
  if(uComp){{ uComp.destroy(); uComp = null; }}
  const el = document.getElementById('uplot-comp');
  if(!el) return;
  el.innerHTML = '';

  const esDia = periodo==='dia' && datos.length===1
                && datos[0].d.horas?.t?.length > 0;

  // Construir serie EEP y UES para la variable académica activa
  let labelsC = [], sEEP = [], sUES = [];

  if(esDia){{
    labelsC = datos[0].d.horas.t || [];
    sEEP    = datos[0].d.horas[acadVar] || labelsC.map(()=>null);
    // Para UES en modo día necesitamos los datos del mismo día en UES
    const dUES = CLIMA.dias[datos[0].fecha]?.UES?.horas;
    sUES = dUES ? (dUES[acadVar] || labelsC.map(()=>null)) : labelsC.map(()=>null);
  }} else {{
    labelsC = datos.map(e=>e.fecha.slice(5));
    sEEP = datos.map(e=>{{
      const obj = CLIMA.dias[e.fecha]?.EEP;
      const v = obj?.[acadVar]; return (v!=null&&!isNaN(v))?v:null;
    }});
    sUES = datos.map(e=>{{
      const obj = CLIMA.dias[e.fecha]?.UES;
      const v = obj?.[acadVar]; return (v!=null&&!isNaN(v))?v:null;
    }});
  }}

  const meta   = ACAD_META[acadVar] || ACAD_META.temp;
  const fechaBase = esDia ? datos[0].fecha : (diaSelec||datos[0].fecha);
  const ts     = etiquetasATimestamps(labelsC, esDia, fechaBase);

  document.getElementById('comp-title').textContent =
    meta.label+' — EEP (naranja) vs UES (cian) · '+periodoLabel;

  const W = el.offsetWidth || 800;
  uComp = new uPlot({{
    width: W, height: 200,
    cursor: {{ sync:{{ key:'clima-sync' }} }},
    legend: {{ show:true, live:true }},
    scales: {{ x:{{ time:true }} }},
    axes: [
      {{ stroke:C.axis, grid:{{stroke:C.grid,width:1}}, font:'10px Outfit,sans-serif',
         values:(u,vals)=>vals.map(v=>{{
           if(v==null) return '';
           const d=new Date(v*1000);
           const h=d.getHours(),mi=d.getMinutes(),mo=d.getMonth()+1,dy=d.getDate();
           return (h>0||mi>0)?String(h).padStart(2,'0')+':'+String(mi).padStart(2,'0')
                             :String(mo)+'/'+String(dy).padStart(2,'0');
         }})
      }},
      {{ stroke:'#fb923c', grid:{{stroke:C.grid,width:1}}, font:'10px Outfit,sans-serif' }},
    ],
    series: [
      {{ label:'Tiempo' }},
      {{ label:'EEP '+meta.label, stroke:'#fb923c', fill:'rgba(251,146,60,.10)', width:1.8 }},
      {{ label:'UES '+meta.label, stroke:'#38bdf8', fill:'rgba(56,189,248,.08)',  width:1.8 }},
    ],
    hooks:{{
      ready:[u=>{{
        const ov = u.over;
        let dr=false,sx=0,sm,sM;
        ov.addEventListener('mousedown',e=>{{
          if(!ov.closest('.chart-active')||e.button!==0) return;
          dr=true; sx=e.clientX; sm=u.scales.x.min; sM=u.scales.x.max;
        }});
        window.addEventListener('mousemove',e=>{{
          if(!dr) return;
          const dx=e.clientX-sx, rng=sM-sm, sh=-(dx/ov.offsetWidth)*rng;
          u.setScale('x',{{min:sm+sh,max:sM+sh}});
        }});
        window.addEventListener('mouseup',()=>{{dr=false;}});
        const cardC = ov.closest('.uplot-card');
        cardC.addEventListener('wheel',e=>{{
          if(!cardC.classList.contains('chart-active')){{
            e.preventDefault();
            toggleChartActive('comp');
            return;
          }}
          e.preventDefault();
          const sc=u.scales.x,rng=sc.max-sc.min,f=e.deltaY>0?1.25:0.8;
          const rc=ov.getBoundingClientRect(),rt=(e.clientX-rc.left)/rc.width;
          const pv=sc.min+rt*rng,nr=rng*f;
          u.setScale('x',{{min:pv-rt*nr,max:pv+(1-rt)*nr}});
        }},{{passive:false}});
        ov.addEventListener('click',()=>{{
          if(!cardC.classList.contains('chart-active')) toggleChartActive('comp');
        }});
        ov.addEventListener('dblclick',()=>{{
          u.setScale('x',{{min:u.data[0][0],max:u.data[0][u.data[0].length-1]}});
        }});
      }}]
    }}
  }}, [ts, sEEP, sUES], el);

  requestAnimationFrame(()=>{{
    const w2 = el.offsetWidth||800;
    if(uComp) uComp.setSize({{width:w2,height:200}});
  }});
}}

function uZoomComp(f){{
  if(!uComp) return;
  const sc=uComp.scales.x,mid=(sc.min+sc.max)/2,h=(sc.max-sc.min)/2*f;
  uComp.setScale('x',{{min:mid-h,max:mid+h}});
}}
function uZoomCompReset(){{
  if(!uComp) return;
  uComp.setScale('x',{{min:uComp.data[0][0],max:uComp.data[0][uComp.data[0].length-1]}});
}}

// ══════════════════════════════════════════════════════════════════════
// LAZY LOADING — IntersectionObserver
// ══════════════════════════════════════════════════════════════════════

let _acadCargado  = false;  // ¿Ya se renderizaron los gráficos académicos?
let _acadPendiente = false; // ¿Hay un render pendiente para cuando sea visible?
let _acadVisible   = false; // ¿La sección está en el viewport?

// Observar la sección académica
const _acadObserver = new IntersectionObserver((entries) => {{
  for(const entry of entries){{
    _acadVisible = entry.isIntersecting;
    const sec = document.getElementById('acad-section');
    if(_acadVisible){{
      // Primera vez que entra en viewport: quitar skeleton, animar entrada
      if(sec){{
        sec.classList.remove('lazy-pending');
        sec.classList.add('visible');
      }}
      // Si hay un render pendiente (período cambió mientras no era visible)
      if(_acadPendiente){{
        _acadPendiente = false;
        const datos = obtenerDatos();
        actualizarGraficosAcad(datos);
      }} else if(!_acadCargado){{
        // Primera carga
        _acadCargado = true;
        const datos = obtenerDatos();
        actualizarGraficosAcad(datos);
      }}
    }}
  }}
}}, {{
  root: null,
  rootMargin: '200px 0px',  // pre-cargar 200px antes de llegar
  threshold: 0
}});

// Iniciar observación cuando el DOM esté listo
function iniciarObserverAcad(){{
  const sec = document.getElementById('acad-section');
  if(sec) _acadObserver.observe(sec);
}}

// ── Debounce ─────────────────────────────────────────────────────────
let _debounceTid = null;
const _DEBOUNCE_MS = 80;

// ── Calendario rápido: ir a una fecha específica desde el input del navbar ──
function irAFecha(fechaStr){{
  if(!fechaStr) return;
  // Aceptar la fecha aunque no tenga datos — ir al mes correcto
  const parts = fechaStr.split('-').map(Number);
  if(parts.length !== 3) return;
  const [y, m] = parts;
  calMes = {{year: y, month: m}};
  // Si hay datos para ese día, seleccionarlo; si no, mostrar el mes
  if(CLIMA.dias[fechaStr] && CLIMA.dias[fechaStr][sensor]) {{
    diaSelec = fechaStr;
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
  renderizarCalendario();
  actualizarTodoSinScroll();
}}

// Parchear setPeriodo, setTab, setSensor para NO subir al tope
function setPeriodo(p){{
  const sy = window.scrollY;
  periodo = p;
  document.querySelectorAll('.btn-period').forEach(b=>b.classList.remove('active'));
  document.getElementById('p-'+p).classList.add('active');
  actualizarTodoDebounced(sy);
}}
function setTab(t){{
  const sy = window.scrollY;
  tabActiva = t;
  document.querySelectorAll('.btn-tab').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+t).classList.add('active');
  actualizarTodoDebounced(sy);
}}

// ── Actualizar todo preservando scroll ────────────────────────────────
let _debounceSy = 0;
function actualizarTodoDebounced(sy){{
  if(sy !== undefined) _debounceSy = sy;
  clearTimeout(_debounceTid);
  _debounceTid = setTimeout(actualizarTodo, _DEBOUNCE_MS);
}}

function actualizarTodoSinScroll(){{
  const sy = window.scrollY;
  actualizarTodo();
  requestAnimationFrame(()=>window.scrollTo({{top: sy, behavior:'instant'}}));
}}

// ── Actualizar todo: sección académica solo si es visible ─────────────
function actualizarTodo(){{
  const sy = _debounceSy || window.scrollY;
  const datos = obtenerDatos();
  actualizarGrafico(datos);
  actualizarWidgets(datos);
  actualizarNavLabel();
  // Sección académica: diferir si no es visible
  if(_acadVisible){{
    _acadCargado = true;
    _acadPendiente = false;
    actualizarGraficosAcad(datos);
  }} else {{
    // Marcar pendiente — se dibujará cuando entre en viewport
    _acadPendiente = true;
  }}
  // Restaurar scroll después de re-render de uPlot
  requestAnimationFrame(()=>window.scrollTo({{top: sy, behavior:'instant'}}));
}}

// ── Comparativa de rangos ──────────────────────────────────────────────
let modoComparacion = false;

function toggleComparacion(){{
  modoComparacion = !modoComparacion;
  const panel   = document.getElementById('comp-panel');
  const calScr  = document.getElementById('cal-scroll');
  const calSec  = calScr && calScr.closest('.cal-section');
  const btnComp = document.getElementById('btn-comparar');
  if(modoComparacion){{
    panel.classList.add('visible');
    if(calSec) calSec.style.display = 'none';
    if(btnComp) btnComp.classList.add('btn-comparar-active');
    _prefillCompDates();
  }} else {{
    panel.classList.remove('visible');
    document.getElementById('comp-result').innerHTML = '';
    if(calSec) calSec.style.display = '';
    if(btnComp) btnComp.classList.remove('btn-comparar-active');
  }}
}}

function _prefillCompDates(){{
  const sens = sensor || 'EEP';
  const dias = fechasConSensor(sens).sort();
  if(!dias.length) return;
  const mid = dias[Math.floor(dias.length/2)];
  const last = dias[dias.length-1];
  const ainp = d => document.getElementById(d);
  if(!ainp('comp-a-desde').value) ainp('comp-a-desde').value = dias[0];
  if(!ainp('comp-a-hasta').value) ainp('comp-a-hasta').value = mid;
  if(!ainp('comp-b-desde').value) ainp('comp-b-desde').value = mid;
  if(!ainp('comp-b-hasta').value) ainp('comp-b-hasta').value = last;
}}

function actualizarEtiquetasComp(){{ /* hook for future live update */ }}

function getDatosRango(desde, hasta){{
  if(!desde || !hasta) return [];
  const sens = sensor || 'EEP';
  const dias = fechasConSensor(sens).filter(d => d >= desde && d <= hasta).sort();
  return dias.map(d => ({{fecha:d, dia:CLIMA.dias[d]}}));
}}

function _extraerValores(entradas, clave){{
  const vals = [];
  const sens = sensor || 'EEP';
  entradas.forEach(e => {{
    const diaObj = e.dia && e.dia[sens];
    if(!diaObj) return;
    const horas = diaObj.horas;
    if(!horas) return;
    const arr = horas[clave];
    if(Array.isArray(arr)) arr.forEach(v => {{ if(v!=null && !isNaN(v)) vals.push(v); }});
  }});
  return vals;
}}

function _etiquetaVariable(k){{
  return {{temp:'Temperatura (°C)',hum:'Humedad (%)',presion:'Presión (hPa)',
    lluvia:'Lluvia (mm)',viento:'Viento (m/s)' }}[k] || k;
}}

function _interpretarComparacion(statsA, statsB, claveActiva){{
  const lineas = [];
  const etiq = _etiquetaVariable(claveActiva);
  const dif = statsB.media - statsA.media;
  const difSign = dif >= 0 ? `+${{dif.toFixed(2)}}` : dif.toFixed(2);
  if(Math.abs(dif) < 0.01){{
    lineas.push(`Los promedios de <strong>${{etiq}}</strong> son prácticamente idénticos entre ambos rangos.`);
  }} else {{
    const cual = dif > 0 ? 'el Rango B fue mayor' : 'el Rango A fue mayor';
    lineas.push(`En <strong>${{etiq}}</strong>, ${{cual}} (${{difSign}} en promedio). Esto equivale a una variación del ${{Math.abs(dif/Math.max(Math.abs(statsA.media),0.01)*100).toFixed(1)}}%.`);
  }}
  const sdA = statsA.sigma||0, sdB = statsB.sigma||0;
  if(sdB > sdA*1.15)
    lineas.push(`El Rango B muestra mayor variabilidad (σ=${{sdB.toFixed(2)}} vs σ=${{sdA.toFixed(2)}}), lo que indica condiciones más cambiantes.`);
  else if(sdA > sdB*1.15)
    lineas.push(`El Rango A presenta mayor variabilidad (σ=${{sdA.toFixed(2)}} vs σ=${{sdB.toFixed(2)}}), con condiciones más inestables.`);
  else
    lineas.push(`Ambos rangos tienen variabilidad similar (σ≈${{sdA.toFixed(2)}}), lo que sugiere condiciones estables en ambos períodos.`);

  if(statsA.n < 10 || statsB.n < 10)
    lineas.push(`⚠️ Algún rango tiene pocos datos (A: ${{statsA.n}}, B: ${{statsB.n}}) — interpreta con cautela.`);
  return lineas.join(' ');
}}

function renderComparacion(){{
  const aD = document.getElementById('comp-a-desde').value;
  const aH = document.getElementById('comp-a-hasta').value;
  const bD = document.getElementById('comp-b-desde').value;
  const bH = document.getElementById('comp-b-hasta').value;
  if(!aD||!aH||!bD||!bH){{ alert('Selecciona ambos rangos completos.'); return; }}

  const entA = getDatosRango(aD, aH);
  const entB = getDatosRango(bD, bH);
  const variables = ['temp','hum','presion','viento','lluvia'];
  const claveTab = (tabActiva&&tabActiva!=='general') ? tabActiva : 'temp';

  // Tabla stats
  let rowsHtml = '';
  variables.forEach(k => {{
    const vA = _extraerValores(entA, k);
    const vB = _extraerValores(entB, k);
    if(!vA.length && !vB.length) return;
    const sA = calcStats(vA);
    const sB = calcStats(vB);
    if(!sA||!sB) return;
    const dMed = sB.media - sA.media;
    const dCls = dMed >= 0 ? 'comp-diff-pos' : 'comp-diff-neg';
    const dStr = (dMed>=0?'+':'')+dMed.toFixed(2);
    rowsHtml += `
      <tr>
        <td class="var-name">${{_etiquetaVariable(k)}}</td>
        <td>${{sA.n}}</td><td>${{sA.media.toFixed(2)}}</td><td>${{(sA.sigma||0).toFixed(2)}}</td>
        <td>${{(sA.vmin||0).toFixed(2)}}</td><td>${{(sA.vmax||0).toFixed(2)}}</td>
        <td>${{sB.n}}</td><td>${{sB.media.toFixed(2)}}</td><td>${{(sB.sigma||0).toFixed(2)}}</td>
        <td>${{(sB.vmin||0).toFixed(2)}}</td><td>${{(sB.vmax||0).toFixed(2)}}</td>
        <td class="${{dCls}}">${{dStr}}</td>
      </tr>`;
  }});

  // Mini charts (one per variable)
  let miniHtml = '<div class="comp-mini-charts">';
  variables.forEach(k => {{
    const vA = _extraerValores(entA, k);
    const vB = _extraerValores(entB, k);
    if(!vA.length && !vB.length) return;
    miniHtml += `<div class="comp-mini-card">
      <div class="comp-mini-label">${{_etiquetaVariable(k)}}</div>
      <canvas id="comp-canvas-${{k}}" width="220" height="70"></canvas>
    </div>`;
  }});
  miniHtml += '</div>';

  // Interpretación (para la variable activa en el tab)
  const vAact = _extraerValores(entA, claveTab);
  const vBact = _extraerValores(entB, claveTab);
  const sAact = calcStats(vAact);
  const sBact = calcStats(vBact);
  const interp = _interpretarComparacion(sAact, sBact, claveTab);

  document.getElementById('comp-result').innerHTML = `
    <div class="comp-result-title">Resultados de comparativa — <span class="comp-badge-a">Rango A</span> (${{aD}} → ${{aH}}) vs <span class="comp-badge-b">Rango B</span> (${{bD}} → ${{bH}})</div>
    <div class="comp-table-wrap">
      <table class="comp-table">
        <thead><tr>
          <th>Variable</th>
          <th colspan="5" style="color:#f87171">Rango A</th>
          <th colspan="5" style="color:#34d399">Rango B</th>
          <th>Δ Media</th>
        </tr><tr>
          <th></th>
          <th>N</th><th>Media</th><th>σ</th><th>Mín</th><th>Máx</th>
          <th>N</th><th>Media</th><th>σ</th><th>Mín</th><th>Máx</th>
          <th></th>
        </tr></thead>
        <tbody>${{rowsHtml}}</tbody>
      </table>
    </div>
    ${{miniHtml}}
    <div class="comp-interp">${{interp}}</div>`;

  // Draw mini charts after DOM update
  requestAnimationFrame(() => {{
    variables.forEach(k => {{
      const cv = document.getElementById('comp-canvas-'+k);
      if(!cv) return;
      const vA = _extraerValores(entA, k);
      const vB = _extraerValores(entB, k);
      dibujarCompChart(cv, vA, vB);
    }});
  }});
}}

function dibujarCompChart(canvas, datA, datB){{
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0,0,W,H);
  if(!datA.length && !datB.length) return;

  function downsample(arr, n){{
    if(arr.length <= n) return arr;
    const out = [];
    const step = arr.length/n;
    for(let i=0;i<n;i++) out.push(arr[Math.round(i*step)]);
    return out;
  }}

  const N = 60;
  const sA = downsample(datA, N);
  const sB = downsample(datB, N);
  const all = sA.concat(sB);
  const mn = Math.min(...all);
  const mx = Math.max(...all);
  const rng = mx - mn || 1;

  function drawLine(pts, color){{
    if(!pts.length) return;
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    pts.forEach((v,i) => {{
      const x = (i/(pts.length-1||1))*W;
      const y = H - ((v-mn)/rng)*(H-8) - 4;
      i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
    }});
    ctx.stroke();
  }}

  // fill under A
  if(sA.length>1){{
    ctx.beginPath();
    sA.forEach((v,i) => {{
      const x=(i/(sA.length-1||1))*W, y=H-((v-mn)/rng)*(H-8)-4;
      i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
    }});
    ctx.lineTo(W,H); ctx.lineTo(0,H); ctx.closePath();
    ctx.fillStyle='rgba(248,113,113,.12)'; ctx.fill();
  }}
  drawLine(sA, '#f87171');
  drawLine(sB, '#34d399');

  // legend dots
  ctx.beginPath(); ctx.arc(8,8,4,0,Math.PI*2); ctx.fillStyle='#f87171'; ctx.fill();
  ctx.beginPath(); ctx.arc(8,20,4,0,Math.PI*2); ctx.fillStyle='#34d399'; ctx.fill();
  ctx.fillStyle='rgba(255,255,255,.5)'; ctx.font='9px sans-serif';
  ctx.fillText('A',16,12); ctx.fillText('B',16,24);
}}

// ── Modelo Predictivo: renderizar al cargar ───────────────────────────
function renderPrediccion(){{
  const P = CLIMA.prediccion;
  if(!P || P.error) return;

  // Badges de información
  const set = (id, v) => {{ const el=document.getElementById(id); if(el) el.textContent=v; }};
  set('pred-tipo',    'Polinomial grado 3 (C++ AjusteCurvas)');
  set('pred-n',       P.n_datos + ' días');
  set('pred-rmse-t',  P.rmse_temp!=null ? P.rmse_temp.toFixed(4)+' °C' : '—');
  set('pred-rmse-s',  P.rmse_solar!=null ? P.rmse_solar.toFixed(4)+' W/m²' : '—');
  set('pred-ultima',  P.ultima_fecha || '—');
  if(P.coef_temp){{
    const cf = P.coef_temp;
    set('pred-coef-t', `a₀=${{cf[0].toFixed(4)}}  a₁=${{cf[1].toFixed(6)}}  a₂=${{cf[2].toFixed(8)}}  a₃=${{cf[3].toFixed(10)}}`);
  }}

  const preds = P.predicciones || [];
  const labels = preds.map(p=>p.fecha.slice(5));

  // Gráfica temperatura
  if(preds.some(p=>p.temp!=null)){{
    const tVals = preds.map(p=>p.temp??null);
    const cvT = document.getElementById('pred-temp-canvas');
    if(cvT){{
      new Chart(cvT, {{
        type:'line',
        data:{{ labels, datasets:[{{
          label:'Temp predicha (°C)', data:tVals,
          borderColor:'#f87171', backgroundColor:'#f8717122',
          fill:true, tension:.4, pointRadius:3,
          borderDash:[6,3], borderWidth:2
        }}] }},
        options:{{
          responsive:true, animation:false,
          plugins:{{legend:{{display:false}},
            tooltip:{{callbacks:{{label:c=>c.raw.toFixed(1)+' °C'}}}}}},
          scales:{{
            x:{{ticks:{{color:'#64748b',font:{{size:9}}}},grid:{{color:'rgba(255,255,255,.04)'}}}},
            y:{{ticks:{{color:'#64748b',font:{{size:9}}}},grid:{{color:'rgba(255,255,255,.04)'}},
               title:{{display:true,text:'°C',color:'#64748b',font:{{size:9}}}}}},
          }}
        }}
      }});
    }}
  }}

  // Gráfica solar
  if(preds.some(p=>p.solar!=null)){{
    const sVals = preds.map(p=>p.solar??null);
    const cvS = document.getElementById('pred-solar-canvas');
    if(cvS){{
      new Chart(cvS, {{
        type:'line',
        data:{{ labels, datasets:[{{
          label:'Solar predicha (W/m²)', data:sVals,
          borderColor:'#fbbf24', backgroundColor:'#fbbf2422',
          fill:true, tension:.4, pointRadius:3,
          borderDash:[6,3], borderWidth:2
        }}] }},
        options:{{
          responsive:true, animation:false,
          plugins:{{legend:{{display:false}},
            tooltip:{{callbacks:{{label:c=>c.raw.toFixed(1)+' W/m²'}}}}}},
          scales:{{
            x:{{ticks:{{color:'#64748b',font:{{size:9}}}},grid:{{color:'rgba(255,255,255,.04)'}}}},
            y:{{ticks:{{color:'#64748b',font:{{size:9}}}},grid:{{color:'rgba(255,255,255,.04)'}},
               title:{{display:true,text:'W/m²',color:'#64748b',font:{{size:9}}}}}},
          }}
        }}
      }});
    }}
  }}

  // Tabla de predicciones
  const tbody = document.getElementById('pred-tbody');
  if(tbody){{
    tbody.innerHTML = preds.map(p=>
      `<tr>
        <td style="font-family:var(--mono)">${{p.fecha}}</td>
        <td style="color:var(--tx3)">${{p.doy}}</td>
        <td style="color:#f87171;font-family:var(--mono)">${{p.temp!=null?p.temp.toFixed(1)+'°C':'—'}}</td>
        <td style="color:#fbbf24;font-family:var(--mono)">${{p.solar!=null?p.solar.toFixed(1)+' W/m²':'—'}}</td>
      </tr>`
    ).join('');
  }}
}}

// ── Actualizar date input del navbar con el día seleccionado ──────────
function syncNavDateInput(){{
  const inp = document.getElementById('nav-cal-input');
  if(inp && diaSelec) inp.value = diaSelec;
}}

// ── Arranque ──
init();
iniciarObserverAcad();
// Sincronizar input de fecha con diaSelec inicial
setTimeout(syncNavDateInput, 200);
// Renderizar modelo predictivo
setTimeout(renderPrediccion, 300);
</script>
</body></html>"""

    with open(nombre, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  [OK] Dashboard MSN interactivo → {nombre}")
    return nombre




# ══════════════════════════════════════════════════════════════════════
# REPORTE DE INTERPOLACIÓN
# ══════════════════════════════════════════════════════════════════════

def _imprimir_reporte_interpolacion():
    """
    Imprime en consola el reporte completo de la interpolacion lineal
    aplicada a cada CSV durante la Fase I.
    """
    SEP  = "=" * 70
    SEP2 = "-" * 70

    print()
    print(SEP)
    print("  REPORTE DE INTERPOLACION — FASE I")
    print(SEP)
    print()
    print("  METODO ELEGIDO: Interpolacion Lineal por Tramos")
    print()
    print("  Justificacion:")
    print("  " + SEP2)
    print("  Los datos provienen de estaciones Davis Vantage Pro2 con")
    print("  intervalos fijos de 5 minutos. Los huecos tipicos son de")
    print("  1 a 6 registros consecutivos (5 a 30 min), causados por")
    print("  micro-cortes de transmision o errores de sensor.")
    print()
    print("  Para este tipo de hueco la interpolacion lineal es optima:")
    print("    1. Asume variacion continua entre mediciones proximas.")
    print("    2. Preserva la tendencia local sin amplificar ruido.")
    print("    3. Complejidad O(n): un solo pase por columna.")
    print("    4. No requiere sistemas de ecuaciones ni ventanas globales.")
    print()
    print("  Alternativas descartadas:")
    print("    - Splines cubicos: O(n^3), innecesario para huecos cortos.")
    print("    - Lagrange: oscilaciones de Runge en huecos largos.")
    print("    - Relleno con media global: distorsiona la tendencia diaria.")
    print()
    print("  Formula aplicada:")
    print("    f(k) = f(a) + (k - a) * [f(b) - f(a)] / (b - a)")
    print("    a = ultimo indice conocido antes del hueco")
    print("    b = primer indice conocido despues del hueco")
    print("    Caso limite: extrapolacion constante si falta un extremo.")
    print()

    if not _INTERP_LOG:
        print("  (No se ejecuto interpolacion — se usaron archivos en cache)")
        print(SEP)
        return

    for nombre_csv, cols_log in _INTERP_LOG.items():
        if not cols_log:
            print("  " + nombre_csv + ": sin NaN — no se interpolo nada.")
            continue

        total_nan   = sum(v["nan_antes"]    for v in cols_log.values())
        total_inter = sum(v["interpolados"] for v in cols_log.values())
        total_extra = sum(v["extrapolados"] for v in cols_log.values())
        total_rest  = sum(v["nan_despues"]  for v in cols_log.values())
        pct = (total_inter + total_extra) / total_nan * 100 if total_nan else 0.0

        print("  Archivo: " + nombre_csv)
        print("  " + SEP2)
        print("  " + "Columna".ljust(38) + "NaN".rjust(8)
              + "Lineal".rjust(9) + "Extrap".rjust(9) + "Restantes".rjust(11))
        print("  " + "." * 68)

        orden = sorted(cols_log.items(),
                       key=lambda x: x[1]["nan_antes"], reverse=True)
        for col, m in orden:
            print("  " + col[:38].ljust(38)
                  + str(m["nan_antes"]).rjust(8)
                  + str(m["interpolados"]).rjust(9)
                  + str(m["extrapolados"]).rjust(9)
                  + str(m["nan_despues"]).rjust(11))

        print("  " + "." * 68)
        print("  " + "TOTAL".ljust(38)
              + str(total_nan).rjust(8)
              + str(total_inter).rjust(9)
              + str(total_extra).rjust(9)
              + str(total_rest).rjust(11))
        print("  Porcentaje resuelto: " + str(round(pct, 1)) + "%")
        print()

    print("  LEYENDA:")
    print("    NaN       = valores faltantes antes de interpolar")
    print("    Lineal    = rellenados con formula f(k) = f(a) + pendiente*(k-a)")
    print("    Extrap    = extremos sin vecino, rellenados por constante")
    print("    Restantes = NaN que no pudieron rellenarse (columna vacia)")
    print(SEP)

# ══════════════════════════════════════════════════════════════════════
# SISTEMA DE CACHÉ DE CÁLCULOS
# ══════════════════════════════════════════════════════════════════════

import pickle
import hashlib

CACHE_CALC_PATH = os.path.join(_PROJ_ROOT, "analisis_cache.pkl")

def _hash_archivos(archivos: list) -> str:
    """Hash MD5 de nombre+tamaño+mtime de los CSVs. Cambia si cambia cualquier archivo."""
    h = hashlib.md5()
    for ruta in sorted(archivos):
        if os.path.exists(ruta):
            st = os.stat(ruta)
            h.update(f"{ruta}|{st.st_size}|{st.st_mtime}".encode())
        else:
            h.update(f"{ruta}|missing".encode())
    return h.hexdigest()


def _guardar_cache(datos: dict, hash_csv: str):
    """Serializa el resultado completo del análisis (Fases I-IV) en disco."""
    payload = {"hash": hash_csv, "datos": datos}
    with open(CACHE_CALC_PATH, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    size_mb = os.path.getsize(CACHE_CALC_PATH) / 1024 / 1024
    print(f"  [CACHE] Guardado → {CACHE_CALC_PATH} ({size_mb:.1f} MB)")


def _cargar_cache(hash_csv: str):
    """Carga la caché si existe y el hash coincide. Retorna dict o None."""
    if not os.path.exists(CACHE_CALC_PATH):
        return None
    try:
        with open(CACHE_CALC_PATH, "rb") as f:
            payload = pickle.load(f)
        if payload.get("hash") == hash_csv:
            size_mb = os.path.getsize(CACHE_CALC_PATH) / 1024 / 1024
            mtime   = os.path.getmtime(CACHE_CALC_PATH)
            import datetime as _dt2
            fecha_cache = _dt2.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  [CACHE] Caché válida del {fecha_cache} ({size_mb:.1f} MB)")
            return payload["datos"]
        else:
            print("  [CACHE] CSV modificados — caché invalidada.")
            return None
    except Exception as e:
        print(f"  [CACHE] Error al leer caché: {e}")
        return None


def _preguntar_recalcular(cache_existe: bool) -> bool:
    """Pregunta interactivamente. Retorna True si debe recalcular."""
    if not cache_existe:
        return True
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │   Se encontró una caché válida de cálculos previos.     │")
    print("  │                                                         │")
    print("  │   [1] Usar caché   → ejecución rápida (~segundos)       │")
    print("  │   [2] Recalcular   → re-procesar todos los datos        │")
    print("  └─────────────────────────────────────────────────────────┘")
    while True:
        try:
            resp = input("  Elige [1/2] (Enter = 1): ").strip()
        except EOFError:
            resp = "1"
        if resp in ("1", ""):
            print("  → Usando caché.")
            return False
        if resp == "2":
            print("  → Recalculando todo.")
            return True
        print("  Por favor escribe 1 o 2.")

    print()

# ══════════════════════════════════════════════════════════════════════
# FASE VI — DASHBOARD SOLAR SMA (wrapper HTML completo)
# ══════════════════════════════════════════════════════════════════════

def _generar_dashboard_sma(seccion_html: str,
                            nombre: str = "dashboard_solar_sma.html") -> str:
    """Envuelve la sección SMA en un HTML completo independiente."""
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sistema Solar SMA · EIE · Análisis Completo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#06101f;--bg2:#0c1a31;
  --card:rgba(255,255,255,.055);--brd:rgba(255,255,255,.10);
  --tx:#f1f5f9;--tx2:#94a3b8;--tx3:#64748b;
  --r:'Outfit',sans-serif;--mono:'DM Mono',monospace;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{font-family:var(--r);background:var(--bg);color:var(--tx);
     min-height:100vh;overflow-x:hidden}}
.sky{{position:fixed;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(ellipse 90% 55% at 15% 8%,rgba(74,222,128,.10) 0%,transparent 65%),
    radial-gradient(ellipse 70% 50% at 85% 90%,rgba(251,191,36,.07) 0%,transparent 60%),
    linear-gradient(175deg,#06101f 0%,#0c1a31 50%,#060f1e 100%)}}
.stars{{position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:
    radial-gradient(circle,rgba(255,255,255,.55) 1px,transparent 1px),
    radial-gradient(circle,rgba(255,255,255,.25) 1px,transparent 1px);
  background-size:320px 320px,160px 160px;background-position:0 0,90px 70px;
  animation:twinkle 11s ease-in-out infinite alternate}}
@keyframes twinkle{{0%{{opacity:.35}}100%{{opacity:.85}}}}
.page{{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:0 28px 100px}}
header{{padding:52px 0 28px;border-bottom:1px solid rgba(255,255,255,.06)}}
.badge{{display:inline-flex;align-items:center;gap:8px;
  background:rgba(74,222,128,.12);border:1px solid rgba(74,222,128,.25);
  border-radius:100px;padding:4px 14px;font-size:11px;
  color:#4ade80;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:14px}}
.badge::before{{content:'';width:7px;height:7px;border-radius:50%;
  background:#4ade80;box-shadow:0 0 8px #4ade80;
  animation:pdot 2s ease-in-out infinite}}
@keyframes pdot{{0%,100%{{transform:scale(1);opacity:1}}50%{{transform:scale(1.5);opacity:.5}}}}
h1{{font-size:clamp(22px,4vw,40px);font-weight:700;line-height:1.1;
  background:linear-gradient(120deg,#f1f5f9 0%,#4ade80 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;margin-bottom:8px}}
nav{{position:sticky;top:0;z-index:100;background:rgba(6,16,31,.92);
  backdrop-filter:blur(20px);border-bottom:1px solid rgba(255,255,255,.06);
  padding:10px 28px;display:flex;gap:8px;flex-wrap:wrap;margin:0 -28px}}
nav a{{color:#94a3b8;text-decoration:none;padding:5px 14px;
  border:1px solid rgba(255,255,255,.08);border-radius:6px;font-size:.73rem;
  font-family:var(--mono);letter-spacing:.5px;transition:.2s}}
nav a:hover{{background:#4ade80;color:#fff;border-color:#4ade80}}
footer{{border-top:1px solid rgba(255,255,255,.06);padding:20px 0;
  text-align:center;font-size:.72rem;color:#64748b;margin-top:60px}}
</style>
</head>
<body>
<div class="sky"></div>
<div class="stars"></div>
<div class="page">
<header>
  <div class="badge">Sistema Solar SMA · EIE</div>
  <h1>Análisis Sistema Fotovoltaico</h1>
  <p style="color:#94a3b8;font-size:.85rem">
    PYRA0102 · 3× WR725UAE · Datos 2023–2026 · Métodos Numéricos
  </p>
</header>
<nav>
  <a href="#sma">Resumen</a>
  <a href="#sma">Series Temporales</a>
  <a href="#sma">Energía Mensual</a>
  <a href="#sma">Histogramas</a>
  <a href="#sma">Boxplots</a>
  <a href="#sma">Correlación</a>
  <a href="#sma">Estadísticos</a>
</nav>
{seccion_html}
<footer>
  Sistema Solar SMA EIE &nbsp;·&nbsp; Métodos Numéricos &nbsp;·&nbsp;
  PYRA0102 + 3× WR725UAE &nbsp;·&nbsp; Motor estadístico manual Python
</footer>
</div>
</body>
</html>"""
    with open(nombre, "w", encoding="utf-8") as fh:
        fh.write(html)
    return nombre


# ══════════════════════════════════════════════════════════════════════
# MAIN — PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  PROYECTO ANÁLISIS CLIMÁTICO AVANZADO — MÉTODOS NUMÉRICOS")
    print("=" * 70)

    # ── Archivos CSV ──────────────────────────────────────────────────
    ARCHIVOS_EEP = [
        os.path.join(_WL_DIR, "7GT-EEP_1-1-25_12-00_AM_1_Year_1779324867_v2.csv"),
        os.path.join(_WL_DIR, "7GT-EEP_1-1-26_12-00_AM_1_Year_1779324876_v2.csv"),
    ]
    ARCHIVOS_UES = [
        os.path.join(_WL_DIR, "7GT-UES_1-1-25_12-00_AM_1_Year_1779324630_v2.csv"),
        os.path.join(_WL_DIR, "7GT-UES_1-1-26_12-00_AM_1_Year_1779324751_v2.csv"),
    ]

    TODOS_CSV = ARCHIVOS_EEP + ARCHIVOS_UES

    # ── SISTEMA DE CACHÉ ─────────────────────────────────────────────
    print("\n[CACHÉ] Verificando estado…")
    hash_actual  = _hash_archivos(TODOS_CSV)
    datos_cache  = _cargar_cache(hash_actual)
    cache_valida = datos_cache is not None
    recalcular   = _preguntar_recalcular(cache_valida)

    if not recalcular and cache_valida:
        # ── Cargar desde caché ────────────────────────────────────────
        print("\n[CACHÉ] Restaurando Fases I–IV desde disco…")
        df_eep         = datos_cache["df_eep"]
        df_ues         = datos_cache["df_ues"]
        st_eep         = datos_cache["st_eep"]
        st_ues         = datos_cache["st_ues"]
        st_mensual_ues = datos_cache["st_mensual_ues"]
        figs           = datos_cache["figs"]
        correlaciones  = datos_cache["correlaciones"]
        print(f"  7GT-EEP: {len(df_eep):,} registros  |  "
              f"7GT-UES: {len(df_ues):,} registros")
        print("  [OK] Fases I–IV restauradas.")

    else:
        # ── FASE I ────────────────────────────────────────────────────
        print("\n[FASE I] Carga, Segmentación y Curación de Datos")
        print("─" * 50)
        df_eep = concatenar_estacion(ARCHIVOS_EEP)
        df_ues = concatenar_estacion(ARCHIVOS_UES)
        print(f"\n  7GT-EEP: {len(df_eep):,} registros totales")
        print(f"  7GT-UES: {len(df_ues):,} registros totales")

        # ── FASE II ───────────────────────────────────────────────────
        print("\n[FASE II] Motor Estadístico Manual")
        print("─" * 50)

        # Catálogo completo de 53 variables del PDF (Sección 3)
        # Bloque A — Condiciones Internas
        _BLOQUE_A = [
            "Inside Temp - °C", "High Inside Temp - °C", "Low Inside Temp - °C",
            "Inside Hum - %", "High Inside Hum - %", "Low Inside Hum - %",
            "Inside Dew Point - °C", "Inside Wet Bulb - °C",
            "Inside Heat Index - °C", "Inside High Heat Index - °C",
        ]
        # Bloque B — Sensor Barométrico
        _BLOQUE_B = [
            "Barometer - mb", "High Bar - mb", "Low Bar - mb",
            "Absolute Pressure - mb",
        ]
        # Bloque C — Sensores Exteriores (Vantage Pro2)
        _BLOQUE_C = [
            "Temp - °C", "High Temp - °C", "Low Temp - °C",
            "Hum - %", "High Hum - %", "Low Hum - %",
            "Dew Point - °C", "High Dew Point - °C", "Low Dew Point - °C",
            "Wet Bulb - °C", "High Wet Bulb - °C", "Low Wet Bulb - °C",
            "Avg Wind Speed - km/h", "Avg Wind Dir",
            "Wind Run - km", "High Wind Speed - km/h",
            "Wind Chill - °C", "Low Wind Chill - °C",
            "Heat Index - °C", "High Heat Index - °C",
            "Thw Index - °C", "High Thw Index - °C", "Low Thw Index - °C",
            "Thsw Index - °C", "High Thsw Index - °C", "Low Thsw Index - °C",
            "ET - mm", "Rain - mm", "High Rain Rate - mm",
            "Solar Rad - W/m^2", "High Solar Rad - W/m^2", "Solar Energy - Ly",
            "UV Index", "High UV Index", "UV Dose - MEDs",
            "Heating Degree Days", "Cooling Degree Days",
        ]
        COLS_ANALIZAR = _BLOQUE_A + _BLOQUE_B + _BLOQUE_C
        # Eliminar duplicados conservando orden
        seen = set()
        COLS_ANALIZAR = [c for c in COLS_ANALIZAR
                         if not (c in seen or seen.add(c))]

        st_eep, st_ues = {}, {}
        for col in COLS_ANALIZAR:
            print(f"  {col:<38}", end="  ")
            if col in df_eep.columns:
                st_eep[col] = calcular_estadisticos(df_eep, col)
                print("EEP ✓", end="  ")
            if col in df_ues.columns:
                st_ues[col] = calcular_estadisticos(df_ues, col)
                print("UES ✓", end="")
            print()

        for col in ["Temp - °C", "Hum - %", "Barometer - mb"]:
            if col in st_ues:
                imprimir_stats(st_ues[col], "7GT-UES")

        print("\n  [MENSUAL] Temp - °C | 7GT-UES:")
        st_mensual_ues = calcular_estadisticos_mensuales(df_ues, "Temp - °C")
        for mes, sm in st_mensual_ues.items():
            print(f"    {mes}: x̄={sm['media']:.2f}°C  σ={sm['desv']:.2f}  "
                  f"[{sm['minimo']:.1f}–{sm['maximo']:.1f}]  P50={sm['p50']:.2f}")

        # ── FASE III ──────────────────────────────────────────────────
        print("\n[FASE III] Visualizaciones")
        print("─" * 50)
        plt.style.use("dark_background")

        figs = {}

    for col, clave, tit, ylabel in [
        ("Temp - °C", "comp_temp",
         "Temperatura Exterior — 7GT-EEP vs 7GT-UES", "Temp (°C)"),
    ]:
        print(f"  → Comparativa: {col}")
        figs[clave] = grafico_comparativo(df_eep, df_ues, col, tit, ylabel)

    for col, clave, color, lbl in [
        ("Temp - °C",         "serie_temp_ues", "#fca5a5", "Temp (°C)"),
        ("Hum - %",           "serie_hum_ues",  "#93c5fd", "Hum (%)"),
        ("Barometer - mb",    "serie_bar_ues",  "#6ee7b7", "Bar (mb)"),
        ("Solar Rad - W/m^2", "serie_solar_ues","#fde68a", "Solar (W/m²)"),
    ]:
        if col in df_ues.columns:
            print(f"  → Serie UES: {col}")
            figs[clave] = grafico_serie(
                df_ues, col,
                f"Evolución Temporal: {lbl} (7GT-UES)", lbl, color
            )

    for df_r, prefijo in [(df_eep, "eep"), (df_ues, "ues")]:
        for col, key, color in [
            ("Temp - °C",             f"hist_temp_{prefijo}",  "#f59e0b"),
            ("Hum - %",               f"hist_hum_{prefijo}",   "#3b82f6"),
            ("Barometer - mb",        f"hist_bar_{prefijo}",   "#10b981"),
            ("Solar Rad - W/m^2",     f"hist_solar_{prefijo}", "#fbbf24"),
            ("Avg Wind Speed - km/h", f"hist_wind_{prefijo}",  "#a78bfa"),
        ]:
            if col in df_r.columns:
                s = _serie(df_r, col)
                if s:
                    k = math.ceil(log2_manual(len(s)) + 1)
                    print(f"  → Hist [{prefijo.upper()}]: {col} | k={k}")
                    figs[key] = histograma(
                        s, f"{col} ({prefijo.upper()}) — k Sturges={k}", col, color
                    )

    for col, clave, tit in [
        ("Temp - °C",      "box_temp_eep",
         "Boxplot Mensual — Temperatura Exterior (7GT-EEP)"),
        ("Temp - °C",      "box_temp_ues",
         "Boxplot Mensual — Temperatura Exterior (7GT-UES)"),
        ("Hum - %",        "box_hum_ues",
         "Boxplot Mensual — Humedad Exterior (7GT-UES)"),
        ("Barometer - mb", "box_bar_ues",
         "Boxplot Mensual — Presión Barométrica (7GT-UES)"),
    ]:
        df_r = df_eep if "eep" in clave else df_ues
        if col in df_r.columns:
            print(f"  → Boxplot: {tit}")
            figs[clave] = boxplot_mensual(df_r, col, tit)

    for df_r, clave, tit in [
        (df_eep, "wind_eep", "Rosa de los Vientos (7GT-EEP)"),
        (df_ues, "wind_ues", "Rosa de los Vientos (7GT-UES)"),
    ]:
        print(f"  → {tit}")
        figs[clave] = rosa_de_vientos(df_r, tit)

    # ── FASE IV ───────────────────────────────────────────────────────
    print("\n[FASE IV] Correlación de Pearson Inter-Estacional")
    print("─" * 50)
    correlaciones = calcular_correlaciones(df_eep, df_ues)

    print(f"\n  {'Variable':<38} {'r':>10} {'R²':>7}  Interpretación")
    print("  " + "─" * 68)
    for d in correlaciones.values():
        print(f"  {d['nombre']:<38} {d['r']:>+10.6f} "
              f"{d.get('r2', float('nan')):>7.4f}  {d['interpretacion']}")

    figs["pearson"] = grafico_pearson(correlaciones)

    # ── Guardar caché de Fases I–IV ──────────────────────────────
    print("\n[CACHÉ] Guardando resultados de Fases I–IV…")
    _guardar_cache({
        "df_eep":         df_eep,
        "df_ues":         df_ues,
        "st_eep":         st_eep,
        "st_ues":         st_ues,
        "st_mensual_ues": st_mensual_ues,
        "figs":           figs,
        "correlaciones":  correlaciones,
    }, hash_actual)

    # ── Crear carpetas de salida si no existen ────────────────────────
    os.makedirs(_DASH_DIR, exist_ok=True)
    os.makedirs(_EXPORT_DIR, exist_ok=True)

    # ── Dashboard clásico (estadístico, sin interactividad) ──────────
    print("\n[DASHBOARD CLÁSICO] Generando HTML estático (Fases I–IV)...")
    salida_clasico = generar_dashboard_publico(
        st_eep, st_ues, figs, correlaciones,
        st_mensual_ues=st_mensual_ues,
        nombre=os.path.join(_DASH_DIR, "dashboard_proyecto_climatico.html")
    )

    # ── FASE V: Dashboard MSN Interactivo ────────────────────────────
    print("\n[FASE V] Dashboard MSN Interactivo con JSON embebido…")
    salida_msn = generar_dashboard_msn_interactivo(
        df_eep, df_ues, figs, correlaciones,
        nombre=os.path.join(_DASH_DIR, "dashboard_msn_interactivo.html")
    )

    # ── FASE VI: Análisis Sistema Solar SMA ──────────────────────────
    salida_sma = os.path.join(_DASH_DIR, "dashboard_solar_sma.html")
    try:
        sys.path.insert(0, _SCRIPT_DIR)
        from analisis_sma import analizar_sistema_solar, generar_seccion_html_sma
        sma_resultado = analizar_sistema_solar(verbose=True)
        if sma_resultado:
            seccion_sma = generar_seccion_html_sma(sma_resultado)
            _generar_dashboard_sma(seccion_sma, salida_sma)
            print(f"  [OK] Dashboard SMA → {salida_sma}")
        else:
            salida_sma = None
    except Exception as e:
        print(f"  [WARN FASE VI] Error al procesar datos SMA: {e}")
        salida_sma = None

    # ── Reporte de interpolación ──────────────────────────────────────
    _imprimir_reporte_interpolacion()

    webbrowser.open(f"file://{os.path.abspath(salida_msn)}")
    if salida_sma:
        webbrowser.open(f"file://{os.path.abspath(salida_sma)}")

    print(f"\n{'='*70}")
    print("  ✅ ¡Completado!")
    print(f"  📊 Dashboard clásico:   {salida_clasico}")
    print(f"  🌤  Dashboard MSN:       {salida_msn}")
    if salida_sma:
        print(f"  ⚡ Dashboard Solar SMA: {salida_sma}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()