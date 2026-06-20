#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de ingesta de datos — Análisis Climático/Fotovoltaico
============================================================
Funciones:
  · cargar_weatherlink(ruta)  — limpia CSV WeatherLink, detecta frecuencia
  · cargar_sma(carpetas)      — carga todos los CSVs SMA diarios
  · interpolar_linear(serie)  — interpolación manual sin .interpolate()
  · fusionar_datos(df_wl, df_sma) — merge por timestamp con tolerancia
  · exportar_json_rangos(df)  — escribe JSON mensual en dashboard/exportaciones/
  · reporte_curacion(...)     — imprime resumen de limpieza
"""

import os
import sys
import json
import datetime
from pathlib import Path

import pandas as pd
import numpy as np

# ─── Rutas base ───────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent
_PROJ_ROOT  = _SCRIPT_DIR.parent
_WL_DIR     = _PROJ_ROOT / "datos_crudos" / "weatherlink"
_SMA_DIR    = _PROJ_ROOT / "datos_crudos" / "sma_solar"
_EXPORT_DIR = _PROJ_ROOT / "dashboard" / "exportaciones"

# ─── Constantes ───────────────────────────────────────────────────────
FECHA_INICIO = pd.Timestamp("2025-02-01")
# Valores que representan dato ausente en WeatherLink
_ANOMALOS_WL = {"--", "---", "N/A", "n/a", "NA", "", " ", "****"}
# Columnas de texto en WeatherLink (no convertir a numérico)
_COLS_TEXTO_WL = {"Date & Time", "Prevailing Wind Dir",
                  "Avg Wind Dir", "High Wind Direction"}
# Columnas SMA por índice (CSV de 58 columnas)
_IDX = {
    "ts":    0,   "hum":   1,   "press": 2,   "irr":   4,
    "tamb":  7,   "tmod":  10,
    "etot1": 15,  "fac1":  16,  "iac1":  19,  "ipv1":  20,
    "pac1":  22,  "vac1":  26,  "vpv1":  27,
    "etot2": 30,  "fac2":  31,  "iac2":  34,  "ipv2":  35,
    "pac2":  37,  "vac2":  41,  "vpv2":  42,
    "etot3": 45,  "fac3":  46,  "iac3":  49,  "ipv3":  50,
    "pac3":  52,  "vac3":  56,  "vpv3":  57,
}


# ══════════════════════════════════════════════════════════════════════
# DETECCIÓN DINÁMICA DE FRECUENCIA
# ══════════════════════════════════════════════════════════════════════

def detectar_frecuencia(df: pd.DataFrame, col_dt: str = "Date & Time") -> int:
    """
    Calcula el intervalo de muestreo más frecuente (en minutos)
    entre filas consecutivas. No asume ningún valor previo.

    Retorna: int (minutos). Típico: 5, 15 o 30 min.
    """
    if col_dt not in df.columns or len(df) < 2:
        return 5

    tiempos = pd.to_datetime(df[col_dt], errors="coerce").dropna().reset_index(drop=True)
    deltas = []
    for i in range(1, min(300, len(tiempos))):
        d = (tiempos.iloc[i] - tiempos.iloc[i - 1]).total_seconds() / 60.0
        if 1.0 <= d <= 120.0:
            deltas.append(round(d))

    if not deltas:
        return 5

    # Moda sin statistics.mode (no permitida)
    conteo: dict[int, int] = {}
    for d in deltas:
        conteo[d] = conteo.get(d, 0) + 1

    return max(conteo, key=lambda k: conteo[k])


# ══════════════════════════════════════════════════════════════════════
# CARGA Y LIMPIEZA — WEATHERLINK
# ══════════════════════════════════════════════════════════════════════

def cargar_weatherlink(ruta: str,
                       fecha_inicio: pd.Timestamp = FECHA_INICIO,
                       max_gap: int = 3) -> tuple[pd.DataFrame, int]:
    """
    Carga y cura un CSV de WeatherLink (estaciones 7GT-EEP / 7GT-UES).

    Limpieza estricta:
      · Salta 5 filas de metadatos del formato WeatherLink
      · Reemplaza '--', vacíos, '****' y variantes con np.nan
      · Convierte todas las columnas numéricas con pd.to_numeric(errors='coerce')
      · Parsea 'Date & Time' → datetime
      · Filtra registros desde fecha_inicio
      · Aplica interpolación lineal manual en gaps ≤ max_gap muestras

    Retorna: (df_limpio, frecuencia_minutos)
    """
    ruta = str(ruta)
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"CSV WeatherLink no encontrado: {ruta}")

    nombre = os.path.basename(ruta)
    na_vals = list(_ANOMALOS_WL)

    for enc in ("utf-8", "latin-1"):
        try:
            df_raw = pd.read_csv(
                ruta, skiprows=5, header=0,
                encoding=enc, low_memory=False,
                na_values=na_vals, keep_default_na=True
            )
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"No se pudo leer {nombre} con utf-8 ni latin-1")

    # Limpiar nombres de columnas (quitar comillas sobrantes del CSV)
    df_raw.columns = [str(c).strip().strip('"') for c in df_raw.columns]

    # Sustituir anomalías adicionales en columnas numéricas
    for col in df_raw.columns:
        if col in _COLS_TEXTO_WL:
            continue
        if df_raw[col].dtype == object:
            df_raw[col] = df_raw[col].astype(str).str.strip()
            df_raw[col] = df_raw[col].replace(list(_ANOMALOS_WL), np.nan)
            df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce")

    # Parsear timestamp
    dt_col = "Date & Time"
    if dt_col not in df_raw.columns:
        # Buscar columna de fecha
        for c in df_raw.columns:
            if "date" in c.lower() or "time" in c.lower():
                dt_col = c
                break

    # format='mixed' maneja el formato M/D/YY H:MM AM/PM de WeatherLink
    df_raw[dt_col] = pd.to_datetime(df_raw[dt_col], errors="coerce", format="mixed")
    df_raw = df_raw.dropna(subset=[dt_col])
    df_raw = df_raw.sort_values(dt_col).drop_duplicates(subset=[dt_col]).reset_index(drop=True)
    df_raw = df_raw[df_raw[dt_col] >= fecha_inicio].copy()

    # Detectar frecuencia dinámica
    freq_min = detectar_frecuencia(df_raw, dt_col)

    # Interpolación lineal manual
    cols_num = [c for c in df_raw.columns if c not in _COLS_TEXTO_WL
                and pd.api.types.is_numeric_dtype(df_raw[c])]
    for col in cols_num:
        if df_raw[col].isna().any():
            df_raw[col] = interpolar_linear(df_raw[col], max_gap=max_gap)

    return df_raw, freq_min


# ══════════════════════════════════════════════════════════════════════
# CARGA — SMA SOLAR
# ══════════════════════════════════════════════════════════════════════

def _parsear_val_sma(v) -> float:
    """Convierte valor de columna SMA a float. Retorna np.nan si inválido."""
    s = str(v).strip()
    if not s or s in _ANOMALOS_WL or ":" in s:
        return np.nan
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return np.nan


def _parsear_fecha_nombre(nombre: str):
    """Extrae date de nombre de archivo SMA. Soporta YYYY-MM-DD y MM-DD-YYYY."""
    import re
    base = Path(nombre).stem.split("(")[0].strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", base)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", base)
    if m:
        return datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return None


def _fila_sma(cols: list) -> dict | None:
    """Parsea lista de columnas de una fila SMA → dict de valores."""
    if len(cols) < 56:
        return None
    ts = str(cols[_IDX["ts"]]).strip()
    if not ts or ":" not in ts or len(ts) < 4:
        return None

    pac1 = _parsear_val_sma(cols[_IDX["pac1"]])
    pac2 = _parsear_val_sma(cols[_IDX["pac2"]])
    pac3 = _parsear_val_sma(cols[_IDX["pac3"]])

    # pac_total = suma de inversores con datos válidos
    vals_pac = [v for v in (pac1, pac2, pac3) if v == v]  # filtrar NaN
    pac_total = sum(vals_pac) if vals_pac else np.nan

    return {
        "ts_hora": ts,
        "irr":       _parsear_val_sma(cols[_IDX["irr"]]),
        "tamb":      _parsear_val_sma(cols[_IDX["tamb"]]),
        "tmod":      _parsear_val_sma(cols[_IDX["tmod"]]),
        "hum":       _parsear_val_sma(cols[_IDX["hum"]]),
        "press":     _parsear_val_sma(cols[_IDX["press"]]),
        "pac_total": pac_total,
        "pac1": pac1, "pac2": pac2, "pac3": pac3,
        "etot1": _parsear_val_sma(cols[_IDX["etot1"]]),
        "etot2": _parsear_val_sma(cols[_IDX["etot2"]]),
        "etot3": _parsear_val_sma(cols[_IDX["etot3"]]),
    }


def cargar_sma(carpetas=None,
               fecha_inicio: pd.Timestamp = FECHA_INICIO) -> pd.DataFrame:
    """
    Carga todos los CSVs SMA desde las carpetas indicadas.

    Detecta automáticamente:
      · Separador del CSV (';' o ',')
      · Frecuencia de muestreo entre filas (atributo df.attrs['freq_min'])

    Retorna: DataFrame con columna 'ts' (datetime) + variables del inversor.
    """
    if carpetas is None:
        carpetas = [
            _SMA_DIR / "2023-2024" / "2023",
            _SMA_DIR / "2023-2024" / "2024",
            _SMA_DIR / "SMA-EIE-2025-2026",
        ]

    registros = []
    n_archivos = 0

    for carpeta in carpetas:
        carpeta = Path(carpeta)
        if not carpeta.is_dir():
            print(f"  [WARN SMA] Carpeta no encontrada: {carpeta}")
            continue

        archivos = sorted([f for f in carpeta.iterdir()
                           if f.suffix.lower() == ".csv"])
        por_fecha: dict[datetime.date, list] = {}
        for f in archivos:
            fecha = _parsear_fecha_nombre(f.name)
            if fecha:
                por_fecha.setdefault(fecha, []).append(f)

        for fecha in sorted(por_fecha):
            for ruta in por_fecha[fecha]:
                try:
                    with open(ruta, encoding="latin-1") as fh:
                        lineas = fh.readlines()
                    # Detectar separador desde la línea de columnas (índice 4)
                    # que tiene muchos campos: "TimeStamp;envhmdt;..." → mucho más fiable
                    hdr = lineas[4] if len(lineas) > 4 else (lineas[0] if lineas else "")
                    sep = ";" if hdr.count(";") > hdr.count(",") else ","
                    # Líneas 4=columnas, 5=unidades → datos comienzan en línea 6
                    for linea in lineas[6:]:
                        cols = linea.rstrip("\n").split(sep)
                        f_data = _fila_sma(cols)
                        if f_data:
                            ts_str = f"{fecha.strftime('%Y-%m-%d')} {f_data.pop('ts_hora')}"
                            try:
                                ts = pd.Timestamp(ts_str)
                                registros.append({"ts": ts, **f_data})
                            except Exception:
                                pass
                    n_archivos += 1
                except Exception as e:
                    print(f"  [WARN SMA] {ruta.name}: {e}")

    print(f"  [SMA] {n_archivos} archivos leídos → {len(registros):,} registros brutos")

    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)
    df = df.sort_values("ts").drop_duplicates(subset=["ts"]).reset_index(drop=True)
    df = df[df["ts"] >= fecha_inicio].copy()

    # Detectar frecuencia
    freq_min = 15
    if len(df) > 3:
        deltas = []
        for i in range(1, min(100, len(df))):
            d = (df["ts"].iloc[i] - df["ts"].iloc[i - 1]).total_seconds() / 60.0
            if 1.0 <= d <= 60.0:
                deltas.append(round(d))
        if deltas:
            conteo: dict[int, int] = {}
            for d in deltas:
                conteo[d] = conteo.get(d, 0) + 1
            freq_min = max(conteo, key=lambda k: conteo[k])

    df.attrs["freq_min"] = freq_min
    return df


# ══════════════════════════════════════════════════════════════════════
# INTERPOLACIÓN MANUAL (sin .interpolate())
# ══════════════════════════════════════════════════════════════════════

def interpolar_linear(serie: pd.Series, max_gap: int = 3) -> pd.Series:
    """
    Interpolación lineal manual entre muestras faltantes.

    Solo rellena gaps de hasta max_gap muestras consecutivas.
    Gaps mayores se dejan como NaN (no inventar datos).
    No usa .interpolate(), .fillna() ni funciones estadísticas.
    """
    arr = serie.to_list()
    n = len(arr)
    i = 0
    while i < n:
        # Detectar NaN por propiedad IEEE 754 (NaN ≠ NaN)
        if arr[i] != arr[i] and i > 0:
            inicio = i - 1
            j = i
            while j < n and arr[j] != arr[j]:
                j += 1
            gap = j - inicio - 1
            if gap <= max_gap and j < n and arr[inicio] == arr[inicio]:
                v0, v1 = arr[inicio], arr[j]
                for k in range(1, gap + 1):
                    arr[inicio + k] = v0 + (v1 - v0) * k / (gap + 1)
            i = j
        else:
            i += 1
    return pd.Series(arr, index=serie.index, dtype=float)


# ══════════════════════════════════════════════════════════════════════
# FUSIÓN WeatherLink + SMA
# ══════════════════════════════════════════════════════════════════════

def fusionar_datos(df_wl: pd.DataFrame, df_sma: pd.DataFrame,
                   freq_min: int = None) -> pd.DataFrame:
    """
    Alinea cronológicamente WeatherLink y SMA usando merge_asof.

    La tolerancia es max(freq_wl, freq_sma)/2 + 1 minuto para absorber
    el desajuste entre los intervalos de 5 min (WL) y 15 min (SMA).

    Retorna: DataFrame fusionado con columnas wl_* y sma_*.
    """
    if df_wl.empty or df_sma.empty:
        return pd.DataFrame()

    df_wl = df_wl.copy()
    df_sma = df_sma.copy()

    dt_col_wl = "Date & Time"
    df_wl = df_wl.rename(columns={dt_col_wl: "ts"})

    cols_wl = {
        "ts":                     "ts",
        "Temp - °C":              "wl_temp",
        "Hum - %":                "wl_hum",
        "Solar Rad - W/m^2":      "wl_solar_rad",
        "Barometer - mb":         "wl_presion",
        "Avg Wind Speed - km/h":  "wl_viento",
        "Rain - mm":              "wl_lluvia",
    }
    cols_wl_pres = {k: v for k, v in cols_wl.items() if k in df_wl.columns}
    df_wl_sub = df_wl[list(cols_wl_pres.keys())].rename(columns=cols_wl_pres)

    cols_sma = {
        "ts":        "ts",
        "pac_total": "sma_pac",
        "irr":       "sma_irr",
        "tamb":      "sma_tamb",
        "tmod":      "sma_tmod",
        "hum":       "sma_hum",
        "press":     "sma_press",
        "etot1":     "sma_etot1",
        "etot2":     "sma_etot2",
        "etot3":     "sma_etot3",
    }
    cols_sma_pres = {k: v for k, v in cols_sma.items() if k in df_sma.columns}
    df_sma_sub = df_sma[list(cols_sma_pres.keys())].rename(columns=cols_sma_pres)

    df_wl_sub = df_wl_sub.sort_values("ts")
    df_sma_sub = df_sma_sub.sort_values("ts")

    tol_min = (freq_min or 15) // 2 + 2
    tol = pd.Timedelta(minutes=tol_min)

    df_fusion = pd.merge_asof(
        df_wl_sub, df_sma_sub,
        on="ts",
        tolerance=tol,
        direction="nearest"
    )

    return df_fusion


# ══════════════════════════════════════════════════════════════════════
# EXPORTACIÓN JSON MENSUAL
# ══════════════════════════════════════════════════════════════════════

def _jv(v):
    """Convierte valor a tipo JSON-serializable. NaN → None."""
    if v is None:
        return None
    try:
        if v != v:  # NaN por IEEE 754
            return None
    except TypeError:
        pass
    if hasattr(v, "item"):
        return v.item()
    return v


def exportar_json_rangos(df: pd.DataFrame,
                          output_dir: Path = None) -> list[str]:
    """
    Exporta el DataFrame a archivos JSON mensuales en dashboard/exportaciones/.

    Genera:
      · YYYY-MM.json  por cada mes presente en los datos
      · indice.json   con lista de meses y conteo de registros

    Retorna: lista de rutas de archivos generados.
    """
    if output_dir is None:
        output_dir = _EXPORT_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if df.empty or "ts" not in df.columns:
        print("  [WARN] DataFrame vacío, sin JSON que exportar")
        return []

    df = df.copy()
    df["_mes"] = df["ts"].dt.to_period("M")
    meses = sorted(df["_mes"].dropna().unique(), key=str)

    indice = []
    archivos = []
    cols_data = [c for c in df.columns if c not in ("ts", "_mes")]

    for mes in meses:
        sub = df[df["_mes"] == mes]
        mes_str = str(mes)
        registros = []

        for _, row in sub.iterrows():
            r = {"ts": row["ts"].strftime("%Y-%m-%d %H:%M")}
            for col in cols_data:
                r[col] = _jv(row[col])
            registros.append(r)

        payload = {
            "mes":    mes_str,
            "n":      len(registros),
            "cols":   cols_data,
            "datos":  registros
        }

        out_path = output_dir / f"{mes_str}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

        print(f"  [JSON] {out_path.name}  →  {len(registros):,} registros")
        indice.append({"mes": mes_str, "n": len(registros),
                       "archivo": f"{mes_str}.json"})
        archivos.append(str(out_path))

    # Índice global
    idx_payload = {
        "generado": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_registros": sum(m["n"] for m in indice),
        "meses": indice
    }
    idx_path = output_dir / "indice.json"
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx_payload, f, ensure_ascii=False, indent=2)
    print(f"  [JSON] indice.json  →  {len(indice)} meses")

    return archivos


# ══════════════════════════════════════════════════════════════════════
# REPORTE DE CURACIÓN
# ══════════════════════════════════════════════════════════════════════

def reporte_curacion(df_original: pd.DataFrame, df_limpio: pd.DataFrame,
                     fuente: str = "", freq_min: int = None):
    """Imprime resumen de la curación de datos."""
    n_orig = len(df_original)
    n_limp = len(df_limpio)
    print(f"\n  [{fuente}] Curación:")
    print(f"    Registros brutos    : {n_orig:,}")
    print(f"    Registros limpios   : {n_limp:,}  "
          f"({n_orig - n_limp:,} eliminados, {100*(1-n_limp/n_orig if n_orig else 1):.1f}%)")
    if freq_min:
        print(f"    Frecuencia detectada: {freq_min} min")

    nan_cols = [(c, int(df_limpio[c].isna().sum()))
                for c in df_limpio.columns
                if pd.api.types.is_numeric_dtype(df_limpio[c])
                and df_limpio[c].isna().any()]
    nan_cols.sort(key=lambda x: -x[1])
    if nan_cols:
        print(f"    Columnas con NaN ({len(nan_cols)}):")
        for col, cnt in nan_cols[:8]:
            pct = 100 * cnt / len(df_limpio) if len(df_limpio) else 0
            print(f"      {col:<42} {cnt:>6} ({pct:.1f}%)")
        if len(nan_cols) > 8:
            print(f"      ... y {len(nan_cols)-8} columnas más")


# ══════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA — prueba completa del pipeline
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 62)
    print("  INGESTA — ANÁLISIS CLIMÁTICO / FOTOVOLTAICO")
    print("=" * 62)

    # ── WeatherLink ───────────────────────────────────────────────────
    print("\n[1/4] Cargando WeatherLink EEP + UES...")
    archivos_wl = (
        list(_WL_DIR.glob("7GT-EEP*v2.csv")) +
        list(_WL_DIR.glob("7GT-UES*v2.csv"))
    )
    archivos_wl = sorted(f for f in archivos_wl if "_clean" not in f.name)

    dfs_wl = []
    for ruta in archivos_wl:
        print(f"  Procesando: {ruta.name}")
        df_raw_wl = pd.read_csv(
            str(ruta), skiprows=5, header=0,
            encoding="utf-8", low_memory=False,
            na_values=list(_ANOMALOS_WL)
        )
        n_raw = len(df_raw_wl)
        df_clean, freq = cargar_weatherlink(str(ruta))
        reporte_curacion(df_raw_wl, df_clean, ruta.stem[:20], freq)
        dfs_wl.append(df_clean)

    if dfs_wl:
        df_wl_total = (pd.concat(dfs_wl)
                       .sort_values("Date & Time")
                       .drop_duplicates("Date & Time")
                       .reset_index(drop=True))
        freq_wl = detectar_frecuencia(df_wl_total)
        print(f"\n  WL total: {len(df_wl_total):,} registros  |  "
              f"Frecuencia: {freq_wl} min  |  "
              f"Rango: {df_wl_total['Date & Time'].iloc[0].date()} → "
              f"{df_wl_total['Date & Time'].iloc[-1].date()}")
    else:
        df_wl_total = pd.DataFrame()
        freq_wl = 5

    # ── SMA Solar ────────────────────────────────────────────────────
    print("\n[2/4] Cargando SMA Solar...")
    df_sma = cargar_sma()
    freq_sma = df_sma.attrs.get("freq_min", 15) if not df_sma.empty else 15
    if not df_sma.empty:
        print(f"  SMA total: {len(df_sma):,} registros  |  "
              f"Frecuencia: {freq_sma} min  |  "
              f"Rango: {df_sma['ts'].iloc[0].date()} → "
              f"{df_sma['ts'].iloc[-1].date()}")

    # ── Fusión ───────────────────────────────────────────────────────
    print("\n[3/4] Fusionando WeatherLink + SMA...")
    df_fusion = fusionar_datos(df_wl_total, df_sma, freq_min=max(freq_wl, freq_sma))
    print(f"  Fusion: {len(df_fusion):,} registros alineados")
    if not df_fusion.empty:
        n_wl_ok  = df_fusion["wl_solar_rad"].notna().sum() if "wl_solar_rad" in df_fusion.columns else 0
        n_sma_ok = df_fusion["sma_pac"].notna().sum() if "sma_pac" in df_fusion.columns else 0
        print(f"  WL solar_rad válidos: {n_wl_ok:,}  |  SMA pac válidos: {n_sma_ok:,}")

    # ── Export JSON ──────────────────────────────────────────────────
    print("\n[4/4] Exportando JSON mensual...")
    archivos_json = exportar_json_rangos(df_fusion)
    print(f"\n✅ Ingesta completa — {len(archivos_json)} archivos JSON generados")
    print(f"   Directorio: {_EXPORT_DIR}")
