#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exportar_fusion.py — Misiones 3, 4 y 5
========================================
Orquesta:
  1. Carga WeatherLink + SMA usando wrappers C++ para estadísticos
  2. Fusiona ambas fuentes por timestamp
  3. Exporta JSON mensual a dashboard/exportaciones/
  4. Genera dashboard/dashboard_fusion.html con:
       · Selectores de fecha (sin recarga de página)
       · Gráfica superpuesta Radiación Solar vs Potencia AC
       · Panel de temperatura + humedad
       · KPIs calculados vía C++ (sin .mean()/.std() nativos)
"""

import os
import sys
import json
import datetime
import math

import pandas as pd
import numpy as np

# ─── Rutas base ───────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT  = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
_DASH_DIR   = os.path.join(_PROJ_ROOT, "dashboard")
_EXPORT_DIR = os.path.join(_DASH_DIR, "exportaciones")

sys.path.insert(0, os.path.join(_PROJ_ROOT, "core_math"))
sys.path.insert(0, _SCRIPT_DIR)

# ── Intentar cargar wrappers C++ (Misión 3) ───────────────────────────
_AC = None
_MR = None
try:
    from ajuste_curvas import AjusteCurvas
    _AC = AjusteCurvas()
    print("[C++] AjusteCurvas ✓")
except Exception as e:
    print(f"[WARN C++] AjusteCurvas no cargado ({e}) — fallback Python")

try:
    from metodos_raices import MetodosRaices
    _MR = MetodosRaices()
    print("[C++] MetodosRaices ✓")
except Exception as e:
    print(f"[WARN C++] MetodosRaices no cargado ({e}) — fallback Python")

from ingesta import (cargar_weatherlink, cargar_sma,
                     fusionar_datos, exportar_json_rangos,
                     detectar_frecuencia, _WL_DIR, _SMA_DIR, FECHA_INICIO)


# ══════════════════════════════════════════════════════════════════════
# MOTOR ESTADÍSTICO — usa C++ si disponible, Python puro si no
# ══════════════════════════════════════════════════════════════════════

def _nan_check(v: float) -> bool:
    """True si v es NaN (IEEE 754: NaN ≠ NaN)."""
    try:
        return v != v
    except TypeError:
        return False


def _media(serie: list) -> float:
    """Media aritmética manual. Sin .mean()."""
    vals = [v for v in serie if not _nan_check(v)]
    if not vals:
        return float("nan")
    return sum(vals) / len(vals)


def _varianza(serie: list) -> float:
    """Varianza insesgada (n-1) manual. Sin .var()."""
    vals = [v for v in serie if not _nan_check(v)]
    n = len(vals)
    if n < 2:
        return float("nan")
    m = _media(vals)
    return sum((x - m) ** 2 for x in vals) / (n - 1)


def _sqrt_nr(x: float, tol: float = 1e-9, max_iter: int = 50) -> float:
    """Raíz cuadrada por Newton-Raphson (Método Babilónico)."""
    if _nan_check(x) or x < 0:
        return float("nan")
    if x == 0:
        return 0.0
    if _MR is not None:
        try:
            # MetodosRaices.newton_raphson(f, df, x0, tol, max_iter)
            val, _ = _MR.newton_raphson(
                lambda v: v*v - x, lambda v: 2.0*v, x/2.0, tol=tol, max_iter=max_iter
            )
            return val
        except Exception:
            pass
    # Fallback Newton-Raphson manual
    g = x / 2.0
    for _ in range(max_iter):
        g_next = (g + x / g) / 2.0
        if abs(g_next - g) < tol:
            return g_next
        g = g_next
    return g


def _maximo(serie: list) -> float:
    vals = [v for v in serie if not _nan_check(v)]
    if not vals:
        return float("nan")
    m = vals[0]
    for v in vals[1:]:
        if v > m:
            m = v
    return m


def _minimo(serie: list) -> float:
    vals = [v for v in serie if not _nan_check(v)]
    if not vals:
        return float("nan")
    m = vals[0]
    for v in vals[1:]:
        if v < m:
            m = v
    return m


def _quicksort(arr: list) -> list:
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    izq = [x for x in arr if x < pivot]
    med = [x for x in arr if x == pivot]
    der = [x for x in arr if x > pivot]
    return _quicksort(izq) + med + _quicksort(der)


def _percentil(serie: list, p: float) -> float:
    vals = [v for v in serie if not _nan_check(v)]
    if not vals:
        return float("nan")
    sorted_v = _quicksort(vals)
    n = len(sorted_v)
    idx = p / 100.0 * (n - 1)
    lo, hi = int(idx), min(int(idx) + 1, n - 1)
    frac = idx - lo
    return sorted_v[lo] * (1 - frac) + sorted_v[hi] * frac


def calcular_stats_cpp(serie: "pd.Series", nombre: str) -> dict:
    """
    Calcula estadísticos usando AjusteCurvas de C++ si está disponible,
    o implementación Python pura si no. Nunca usa .mean()/.std() nativos.
    """
    vals_raw = serie.dropna().tolist()
    n = len(vals_raw)
    if n == 0:
        return {"n": 0, "media": None, "sigma": None,
                "vmin": None, "vmax": None, "p25": None, "p50": None, "p75": None}

    if _AC is not None:
        try:
            # Cargar datos en AjusteCurvas como matriz Nx1
            datos = np.ascontiguousarray([[v] for v in vals_raw], dtype=np.float64)
            _AC.establecer_datos(datos)
            _AC.ordenar_por_columna(0, ascendente=True)
            media  = _AC.media(0)
            sigma  = _AC.desviacion_estandar_metodo3(0)
            p25    = _AC.percentil(0, 25.0)
            p50    = _AC.mediana(0)
            p75    = _AC.percentil(0, 75.0)
            vmin   = _AC.minimo(0)
            vmax   = _AC.maximo(0)
            return {"n": n, "media": round(media, 4), "sigma": round(sigma, 4),
                    "vmin": round(vmin, 4), "vmax": round(vmax, 4),
                    "p25": round(p25, 4), "p50": round(p50, 4), "p75": round(p75, 4)}
        except Exception as e:
            print(f"  [WARN C++ stats] {nombre}: {e} — fallback Python")

    # Python puro
    media = _media(vals_raw)
    sigma = _sqrt_nr(_varianza(vals_raw))
    return {
        "n":     n,
        "media": round(media, 4),
        "sigma": round(sigma, 4),
        "vmin":  round(_minimo(vals_raw), 4),
        "vmax":  round(_maximo(vals_raw), 4),
        "p25":   round(_percentil(vals_raw, 25), 4),
        "p50":   round(_percentil(vals_raw, 50), 4),
        "p75":   round(_percentil(vals_raw, 75), 4),
    }


def _pearson_manual(x: list, y: list) -> float:
    """Correlación de Pearson manual. Sin NumPy ni scipy."""
    pairs = [(xi, yi) for xi, yi in zip(x, y)
             if not _nan_check(xi) and not _nan_check(yi)]
    n = len(pairs)
    if n < 2:
        return float("nan")
    mx = _media([p[0] for p in pairs])
    my = _media([p[1] for p in pairs])
    num = sum((xi - mx) * (yi - my) for xi, yi in pairs)
    den_x = _sqrt_nr(sum((xi - mx) ** 2 for xi, yi in pairs))
    den_y = _sqrt_nr(sum((yi - my) ** 2 for xi, yi in pairs))
    if den_x == 0 or den_y == 0:
        return float("nan")
    return num / (den_x * den_y)


# ══════════════════════════════════════════════════════════════════════
# PREPARACIÓN DE DATOS PARA EL DASHBOARD
# ══════════════════════════════════════════════════════════════════════

def _jv(v):
    """JSON-safe: NaN → None, numpy → Python nativo."""
    if v is None:
        return None
    try:
        if v != v:
            return None
    except TypeError:
        pass
    if hasattr(v, "item"):
        return v.item()
    return v


def construir_json_fusion(df: pd.DataFrame) -> dict:
    """
    Construye window.FUSION_DATA para el dashboard.

    Estructura:
    {
      "rango": {"min": "YYYY-MM-DD", "max": "YYYY-MM-DD"},
      "freq_min": int,
      "stats": { col: {n, media, sigma, vmin, vmax, p25, p50, p75} },
      "correlacion_rad_pac": float,
      "dias": {
        "YYYY-MM-DD": {
          "t":        ["HH:MM", ...],
          "sol_rad":  [float|null, ...],
          "sma_pac":  [float|null, ...],
          "wl_temp":  [float|null, ...],
          "wl_hum":   [float|null, ...],
          "wl_lluvia":[float|null, ...],
          "wl_viento":[float|null, ...]
        }
      }
    }
    """
    if df.empty:
        return {}

    cols_num = ["wl_solar_rad", "sma_pac", "wl_temp", "wl_hum",
                "wl_lluvia", "wl_viento", "sma_irr", "sma_tamb"]
    cols_pres = [c for c in cols_num if c in df.columns]

    print("  Calculando estadísticos vía C++/Python manual...")
    stats = {}
    for col in cols_pres:
        stats[col] = calcular_stats_cpp(df[col], col)

    # Correlación de Pearson Radiación WL ↔ Potencia SMA  (C++ primero, fallback manual)
    r = float("nan")
    if "wl_solar_rad" in df.columns and "sma_pac" in df.columns:
        xs = df["wl_solar_rad"].dropna().tolist()
        ys = df["sma_pac"].dropna().tolist()
        n_p = min(len(xs), len(ys))
        if n_p > 1 and _AC is not None:
            try:
                mat = np.ascontiguousarray([[xs[i], ys[i]] for i in range(n_p)], dtype=np.float64)
                _AC.establecer_datos(mat)
                r = _AC.pearson_correlation(0, 1)
                print(f"  Correlación Pearson C++ Rad.Solar WL ↔ Potencia AC: r = {r:.4f}")
            except Exception as e:
                print(f"  [WARN Pearson C++] {e} → manual")
                r = _pearson_manual(xs[:n_p], ys[:n_p])
                print(f"  Correlación Pearson manual Rad.Solar ↔ Potencia: r = {r:.4f}")
        else:
            r = _pearson_manual(xs[:n_p], ys[:n_p])
            print(f"  Correlación Pearson manual Rad.Solar ↔ Potencia: r = {r:.4f}")

    # Agrupar por día
    df = df.copy()
    df["_fecha"] = df["ts"].dt.strftime("%Y-%m-%d")
    df["_hora"]  = df["ts"].dt.strftime("%H:%M")

    dias = {}
    for fecha, grp in df.groupby("_fecha"):
        d: dict[str, list] = {"t": grp["_hora"].tolist()}
        for col in cols_pres:
            if col in grp.columns:
                d[col] = [_jv(v) for v in grp[col].tolist()]
        dias[fecha] = d

    # Rango por iloc[0]/iloc[-1] — df ya está ordenado por ts
    rango_min = df["ts"].iloc[0].strftime("%Y-%m-%d") if len(df) else ""
    rango_max = df["ts"].iloc[-1].strftime("%Y-%m-%d") if len(df) else ""

    return {
        "rango":              {"min": rango_min, "max": rango_max},
        "freq_min":           detectar_frecuencia(df, "ts") if len(df) > 2 else 5,
        "stats":              {k: {sk: _jv(sv) for sk, sv in v.items()}
                               for k, v in stats.items()},
        "correlacion_rad_pac": _jv(r),
        "dias":               dias,
    }


# ══════════════════════════════════════════════════════════════════════
# GENERADOR DEL DASHBOARD FUSIÓN
# ══════════════════════════════════════════════════════════════════════

def generar_dashboard_fusion(data_json: dict,
                              nombre: str = None) -> str:
    """
    Genera dashboard_fusion.html con:
      · Selectores de fecha (sin recarga)
      · Gráfica superpuesta Radiación Solar (W/m²) vs Potencia AC (W)
      · Gráfica Temperatura + Humedad
      · Tabla de estadísticos (calculados con C++)
      · KPIs de correlación y energía total
    """
    if nombre is None:
        nombre = os.path.join(_DASH_DIR, "dashboard_fusion.html")

    # Serializar datos para embebido en HTML
    data_str = json.dumps(data_json, ensure_ascii=False, separators=(",", ":"))
    stats = data_json.get("stats", {})

    def _fmt(col, key, dec=2):
        v = stats.get(col, {}).get(key)
        return f"{v:.{dec}f}" if v is not None else "—"

    r_rad_pac = data_json.get("correlacion_rad_pac")
    r_str = f"{r_rad_pac:.4f}" if r_rad_pac is not None else "—"
    rango = data_json.get("rango", {})
    n_dias = len(data_json.get("dias", {}))

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard Fusión — Clima + Solar</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0f1117;--card:#1a1d27;--brd:#2a2d3e;
  --blue:#60a5fa;--green:#34d399;--amber:#fbbf24;
  --red:#f87171;--purple:#a78bfa;--text:#e2e8f0;
  --muted:#94a3b8;--radius:12px;
}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;
      font-size:14px;line-height:1.5}}
header{{background:linear-gradient(135deg,#1e3a5f,#0f2444);
        padding:14px 24px;border-bottom:1px solid var(--brd);
        display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100;flex-wrap:wrap}}
header h1{{font-size:1.2rem;font-weight:700;color:#fff}}
header span{{font-size:.8rem;color:var(--muted)}}
.hdr-nav{{display:flex;gap:8px;margin-left:auto;flex-shrink:0}}
.hdr-nav a{{display:inline-flex;align-items:center;gap:5px;padding:5px 11px;
            border-radius:8px;text-decoration:none;font-size:.78rem;font-weight:600;
            border:1px solid;transition:.2s;white-space:nowrap}}
.hdr-nav a:hover{{transform:translateY(-1px);opacity:.85}}
.hdr-link-home{{color:#38bdf8;border-color:rgba(56,189,248,.35);background:rgba(56,189,248,.08)}}
.hdr-link-clima{{color:#4ade80;border-color:rgba(74,222,128,.35);background:rgba(74,222,128,.08)}}
.hdr-link-solar{{color:#fbbf24;border-color:rgba(251,191,36,.35);background:rgba(251,191,36,.08)}}
.container{{max-width:1400px;margin:0 auto;padding:20px}}
.kpi-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}}
.kpi{{background:var(--card);border:1px solid var(--brd);border-radius:var(--radius);
      padding:14px 16px}}
.kpi-label{{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
.kpi-val{{font-size:1.5rem;font-weight:700;margin-top:4px}}
.kpi-sub{{font-size:.7rem;color:var(--muted);margin-top:2px}}
.kpi-val.blue{{color:var(--blue)}} .kpi-val.green{{color:var(--green)}}
.kpi-val.amber{{color:var(--amber)}} .kpi-val.red{{color:var(--red)}}
.kpi-val.purple{{color:var(--purple)}}
.filter-bar{{background:var(--card);border:1px solid var(--brd);border-radius:var(--radius);
             padding:14px 18px;margin-bottom:20px;display:flex;flex-wrap:wrap;
             gap:14px;align-items:center}}
.filter-bar label{{font-size:.78rem;color:var(--muted)}}
.filter-bar input[type=date]{{
  background:#0f1117;border:1px solid var(--brd);color:var(--text);
  border-radius:8px;padding:6px 10px;font-size:.82rem;cursor:pointer}}
.filter-bar input[type=date]:focus{{outline:none;border-color:var(--blue)}}
.btn{{background:var(--blue);color:#fff;border:none;border-radius:8px;
      padding:7px 16px;font-size:.82rem;cursor:pointer;font-weight:600;
      transition:background .15s}}
.btn:hover{{background:#3b82f6}}
.btn.sec{{background:var(--brd);color:var(--text)}}
.btn.sec:hover{{background:#374151}}
.period-btns{{display:flex;gap:8px;flex-wrap:wrap}}
.pbtn{{background:var(--brd);color:var(--muted);border:none;border-radius:8px;
       padding:5px 12px;font-size:.78rem;cursor:pointer;transition:all .15s}}
.pbtn.active,.pbtn:hover{{background:var(--blue);color:#fff}}
.charts-grid{{display:grid;grid-template-columns:1fr;gap:16px}}
@media(min-width:1100px){{.charts-grid{{grid-template-columns:1fr 1fr}}}}
.chart-card{{background:var(--card);border:1px solid var(--brd);border-radius:var(--radius);
             padding:16px}}
.chart-card h3{{font-size:.85rem;color:var(--muted);margin-bottom:12px;
                text-transform:uppercase;letter-spacing:.06em}}
canvas{{width:100%!important}}
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
             gap:12px;margin-top:20px}}
.stats-card{{background:var(--card);border:1px solid var(--brd);border-radius:var(--radius);
             padding:14px 16px}}
.stats-card h4{{font-size:.78rem;color:var(--muted);text-transform:uppercase;
                letter-spacing:.05em;margin-bottom:10px;border-bottom:1px solid var(--brd);
                padding-bottom:6px}}
.stats-row{{display:flex;justify-content:space-between;padding:3px 0;font-size:.8rem}}
.stats-row span:first-child{{color:var(--muted)}}
.no-data{{color:var(--muted);font-size:.85rem;text-align:center;padding:40px}}
footer{{text-align:center;padding:20px;color:var(--muted);font-size:.75rem;
        border-top:1px solid var(--brd);margin-top:30px}}
.cal-section{{background:var(--card);border:1px solid var(--brd);border-radius:var(--radius);
              padding:14px 18px;margin-bottom:20px}}
.cal-header{{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}}
.cal-label{{font-size:.7rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted)}}
.cal-nav button{{background:none;border:1px solid var(--brd);color:var(--muted);
  border-radius:6px;padding:3px 10px;cursor:pointer;font-size:.85rem;transition:.2s}}
.cal-nav button:hover{{color:var(--text);border-color:var(--blue)}}
#cal-month-label{{font-size:.9rem;color:var(--text);font-weight:600;min-width:140px;text-align:center}}
.cal-scroll{{display:flex;gap:6px;overflow-x:auto;padding-bottom:8px;
  scrollbar-width:thin;scrollbar-color:var(--brd) transparent}}
.fus-cal-day{{display:flex;flex-direction:column;align-items:center;min-width:64px;
  padding:8px 5px;border-radius:10px;border:1px solid transparent;
  background:rgba(255,255,255,.04);cursor:pointer;transition:.2s;user-select:none}}
.fus-cal-day:hover{{background:rgba(96,165,250,.1);border-color:rgba(96,165,250,.3)}}
.fus-cal-day.active{{background:rgba(96,165,250,.18);border-color:rgba(96,165,250,.5)}}
.fus-cal-day.no-data{{opacity:.3;cursor:not-allowed;pointer-events:none}}
.fus-cal-day>*{{pointer-events:none}}
.fus-dname{{font-size:.58rem;color:var(--muted);margin-bottom:2px}}
.fus-dnum{{font-size:.9rem;font-weight:700}}
.fus-dpac{{font-size:.62rem;color:var(--green);margin-top:3px}}
</style>
</head>
<body>
<header>
  <div>
    <h1>🔗 Dashboard Fusión — Clima + Solar</h1>
    <span>Estaciones 7GT-EEP / 7GT-UES &nbsp;·&nbsp; SMA EIE &nbsp;·&nbsp;
          {rango.get('min','?')} → {rango.get('max','?')} &nbsp;·&nbsp; {n_dias} días</span>
  </div>
  <div class="hdr-nav">
    <a class="hdr-link-home" href="index.html">🏠 Inicio</a>
    <a class="hdr-link-clima" href="dashboard_msn_interactivo.html">🌤 Clima</a>
    <a class="hdr-link-solar" href="dashboard_solar.html">☀️ Solar</a>
  </div>
</header>

<div class="container">

<!-- KPIs -->
<div class="kpi-row" id="kpi-row">
  <div class="kpi">
    <div class="kpi-label">Corr. Rad ↔ Potencia</div>
    <div class="kpi-val purple">{r_str}</div>
    <div class="kpi-sub">Pearson (C++ / Python)</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Irr. Media (SMA)</div>
    <div class="kpi-val amber">{_fmt('sma_irr','media')} W/m²</div>
    <div class="kpi-sub">σ = {_fmt('sma_irr','sigma')}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Potencia AC Media</div>
    <div class="kpi-val green">{_fmt('sma_pac','media')} W</div>
    <div class="kpi-sub">Máx = {_fmt('sma_pac','vmax')} W</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Temp. Media WL</div>
    <div class="kpi-val red">{_fmt('wl_temp','media')} °C</div>
    <div class="kpi-sub">Rango {_fmt('wl_temp','vmin')} – {_fmt('wl_temp','vmax')} °C</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Humedad Media</div>
    <div class="kpi-val blue">{_fmt('wl_hum','media')} %</div>
    <div class="kpi-sub">σ = {_fmt('wl_hum','sigma')}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Radiación Solar WL</div>
    <div class="kpi-val amber">{_fmt('wl_solar_rad','media')} W/m²</div>
    <div class="kpi-sub">Máx = {_fmt('wl_solar_rad','vmax')}</div>
  </div>
</div>

<!-- Calendario por día -->
<div class="cal-section">
  <div class="cal-header">
    <span class="cal-label">📅 Selecciona un día</span>
    <div class="cal-nav" style="display:flex;align-items:center;gap:8px">
      <button onclick="calNavFusion(-1)">‹</button>
      <span id="cal-month-label">—</span>
      <button onclick="calNavFusion(1)">›</button>
    </div>
    <button class="btn sec" onclick="resetDia()" style="margin-left:auto;font-size:.75rem;padding:5px 12px">Ver todo el período</button>
  </div>
  <div class="cal-scroll" id="cal-scroll"></div>
</div>

<!-- Filtros de fecha -->
<div class="filter-bar">
  <div>
    <label>Desde</label><br>
    <input type="date" id="inp-desde">
  </div>
  <div>
    <label>Hasta</label><br>
    <input type="date" id="inp-hasta">
  </div>
  <button class="btn" onclick="aplicarFiltro()">Aplicar</button>
  <button class="btn sec" onclick="resetFiltro()">Todo el período</button>
  <div class="period-btns">
    <button class="pbtn" onclick="setPeriodo(7)">7 días</button>
    <button class="pbtn" onclick="setPeriodo(30)">30 días</button>
    <button class="pbtn" onclick="setPeriodo(90)">3 meses</button>
    <button class="pbtn" onclick="setPeriodo(180)">6 meses</button>
    <button class="pbtn" onclick="setPeriodo(365)">1 año</button>
  </div>
  <span id="lbl-rango" style="color:var(--muted);font-size:.78rem;margin-left:auto"></span>
</div>

<!-- Gráficas -->
<div class="charts-grid">
  <div class="chart-card" style="grid-column:1/-1">
    <h3>⚡ Radiación Solar (W/m²) vs Potencia AC (W) — Superpuesto</h3>
    <canvas id="c-overlay" height="260"></canvas>
  </div>
  <div class="chart-card">
    <h3>🌡️ Temperatura Ambiente (°C)</h3>
    <canvas id="c-temp" height="200"></canvas>
  </div>
  <div class="chart-card">
    <h3>💧 Humedad Relativa (%)</h3>
    <canvas id="c-hum" height="200"></canvas>
  </div>
  <div class="chart-card">
    <h3>🌬️ Velocidad del Viento (km/h)</h3>
    <canvas id="c-viento" height="200"></canvas>
  </div>
  <div class="chart-card">
    <h3>🌧️ Precipitación (mm)</h3>
    <canvas id="c-lluvia" height="200"></canvas>
  </div>
</div>

<!-- Estadísticos por variable -->
<div class="stats-grid" id="stats-grid"></div>

</div>
<footer>
  Proyecto Programación Numérica · UES El Salvador · Motor C++: AjusteCurvas, MetodosRaices
  &nbsp;·&nbsp;
  <a href="index.html" style="color:var(--blue);text-decoration:none">🏠 Inicio</a> &nbsp;·&nbsp;
  <a href="dashboard_msn_interactivo.html" style="color:#4ade80;text-decoration:none">🌤 Clima</a> &nbsp;·&nbsp;
  <a href="dashboard_solar.html" style="color:var(--amber);text-decoration:none">☀️ Solar</a>
</footer>

<script>
// ═══════════════════════════════════════════════════════════════════
// DATOS EMBEBIDOS
// ═══════════════════════════════════════════════════════════════════
const RAW = {data_str};

// ═══════════════════════════════════════════════════════════════════
// ESTADO GLOBAL
// ═══════════════════════════════════════════════════════════════════
let _filtroDesde = null;
let _filtroHasta = null;
let _charts = {{}};     // canvas id → Chart context
let _calMes = null;     // 'YYYY-MM' para el calendario de fusión
let _diaActivo = null;  // 'YYYY-MM-DD' día seleccionado (null = todo el período)

// ═══════════════════════════════════════════════════════════════════
// UTILIDADES DE FECHA
// ═══════════════════════════════════════════════════════════════════
function parseFecha(s) {{ return s ? new Date(s + 'T00:00:00') : null; }}
function fechaStr(d) {{
  if (!d) return '';
  return d.getFullYear() + '-' +
         String(d.getMonth()+1).padStart(2,'0') + '-' +
         String(d.getDate()).padStart(2,'0');
}}
function addDays(d, n) {{
  const r = new Date(d); r.setDate(r.getDate() + n); return r;
}}

// ═══════════════════════════════════════════════════════════════════
// CALENDARIO DE FUSIÓN
// ═══════════════════════════════════════════════════════════════════
const _DIAS_ES   = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
const _MESES_ES  = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                   'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

function _padN(n){{ return String(n).padStart(2,'0'); }}

function renderFusionCal(){{
  const scroll = document.getElementById('cal-scroll');
  const lbl    = document.getElementById('cal-month-label');
  if(!scroll) return;
  if(!_calMes){{
    const ks = Object.keys(RAW.dias).sort();
    if(!ks.length) return;
    _calMes = ks[ks.length-1].slice(0,7);
  }}
  const [y,m] = _calMes.split('-').map(Number);
  lbl.textContent = _MESES_ES[m-1] + ' ' + y;
  scroll.innerHTML = '';

  const diasMes = new Date(y, m, 0).getDate();
  for(let d=1; d<=diasMes; d++){{
    const f   = `${{y}}-${{_padN(m)}}-${{_padN(d)}}`;
    const obj = RAW.dias[f];
    const dnom = _DIAS_ES[new Date(y, m-1, d).getDay()];
    const div = document.createElement('div');
    div.className = 'fus-cal-day' + (f===_diaActivo?' active':'') + (!obj?' no-data':'');
    if(obj) div.dataset.fecha = f;
    const pac = obj && obj.sma_pac ? obj.sma_pac.reduce((a,v)=>a+(v||0),0)/1000 : null;
    div.innerHTML = `
      <div class="fus-dname">${{dnom}}</div>
      <div class="fus-dnum">${{d}}</div>
      <div class="fus-dpac">${{pac!=null ? pac.toFixed(1)+' kWh':'—'}}</div>`;
    scroll.appendChild(div);
  }}
  if(_diaActivo){{
    const d = parseInt(_diaActivo.split('-')[2]);
    if(scroll.children[d-1]) scroll.children[d-1].scrollIntoView({{inline:'center',behavior:'smooth'}});
  }}
}}

function _initFusionCalListener(){{
  const scroll = document.getElementById('cal-scroll');
  if(!scroll || scroll._calInit) return;
  scroll._calInit = true;
  scroll.addEventListener('click', function(e){{
    const dayEl = e.target.closest('.fus-cal-day:not(.no-data)');
    if(!dayEl || !dayEl.dataset.fecha) return;
    _diaActivo = dayEl.dataset.fecha;
    // Filtrar al día seleccionado
    _filtroDesde = _diaActivo;
    _filtroHasta = _diaActivo;
    document.getElementById('inp-desde').value = _diaActivo;
    document.getElementById('inp-hasta').value = _diaActivo;
    document.querySelectorAll('.pbtn').forEach(b=>b.classList.remove('active'));
    renderFusionCal();
    render();
  }});
}}

function calNavFusion(dir){{
  if(!_calMes){{ renderFusionCal(); return; }}
  let [y,m] = _calMes.split('-').map(Number);
  m += dir;
  if(m > 12){{ m=1; y++; }} else if(m < 1){{ m=12; y--; }}
  _calMes = `${{y}}-${{_padN(m)}}`;
  _diaActivo = null;
  renderFusionCal();
  // Filtrar al mes completo
  _filtroDesde = `${{_calMes}}-01`;
  const lastDay = new Date(y, m, 0).getDate();
  _filtroHasta = `${{_calMes}}-${{_padN(lastDay)}}`;
  document.getElementById('inp-desde').value = _filtroDesde;
  document.getElementById('inp-hasta').value = _filtroHasta;
  document.querySelectorAll('.pbtn').forEach(b=>b.classList.remove('active'));
  render();
}}

function resetDia(){{
  _diaActivo = null;
  _filtroDesde = null;
  _filtroHasta = null;
  document.getElementById('inp-desde').value = RAW.rango.min||'';
  document.getElementById('inp-hasta').value = RAW.rango.max||'';
  document.querySelectorAll('.pbtn').forEach(b=>b.classList.remove('active'));
  renderFusionCal();
  render();
}}

// ═══════════════════════════════════════════════════════════════════
// FILTRADO DE DATOS
// ═══════════════════════════════════════════════════════════════════
function getDiasFiltrados() {{
  const dias = RAW.dias;
  const keys = Object.keys(dias).sort();
  if (!_filtroDesde && !_filtroHasta) return dias;

  const result = {{}};
  for (const k of keys) {{
    if (_filtroDesde && k < _filtroDesde) continue;
    if (_filtroHasta && k > _filtroHasta) continue;
    result[k] = dias[k];
  }}
  return result;
}}

// Aplana días filtrados en series de tiempo
function buildSeries(diasObj) {{
  const t=[], rad=[], pac=[], temp=[], hum=[], viento=[], lluvia=[], irr=[];
  const fechas = Object.keys(diasObj).sort();
  for (const fecha of fechas) {{
    const d = diasObj[fecha];
    const n = d.t ? d.t.length : 0;
    for (let i=0; i<n; i++) {{
      t.push(fecha + ' ' + (d.t[i]||''));
      rad.push(   d.wl_solar_rad ? d.wl_solar_rad[i] : null);
      pac.push(   d.sma_pac      ? d.sma_pac[i]      : null);
      temp.push(  d.wl_temp      ? d.wl_temp[i]      : null);
      hum.push(   d.wl_hum       ? d.wl_hum[i]       : null);
      viento.push(d.wl_viento    ? d.wl_viento[i]    : null);
      lluvia.push(d.wl_lluvia    ? d.wl_lluvia[i]    : null);
      irr.push(   d.sma_irr      ? d.sma_irr[i]      : null);
    }}
  }}
  return {{t,rad,pac,temp,hum,viento,lluvia,irr}};
}}

// Downsample para rendimiento visual
function downsample(arr, maxPts=1200) {{
  if (!arr || arr.length <= maxPts) return arr;
  const step = Math.ceil(arr.length / maxPts);
  const r = [];
  for (let i=0; i<arr.length; i+=step) r.push(arr[i]);
  return r;
}}

// ═══════════════════════════════════════════════════════════════════
// MOTOR DE GRÁFICAS (Canvas 2D puro — sin librería)
// ═══════════════════════════════════════════════════════════════════
const COLORS = {{
  rad:    '#fbbf24',   // amber
  pac:    '#34d399',   // green
  temp:   '#f87171',   // red
  hum:    '#60a5fa',   // blue
  viento: '#a78bfa',   // purple
  lluvia: '#22d3ee',   // cyan
}};

function clearChart(id) {{
  const cv = document.getElementById(id);
  if (!cv) return;
  const ctx = cv.getContext('2d');
  ctx.clearRect(0,0,cv.width,cv.height);
  // Fondo oscuro
  ctx.fillStyle='#0f1117';
  ctx.fillRect(0,0,cv.width,cv.height);
}}

function _pxDims(canvas) {{
  const dpr = window.devicePixelRatio||1;
  const rect = canvas.getBoundingClientRect();
  const W = rect.width||canvas.offsetWidth||800;
  const H = canvas.height;
  canvas.width  = W*dpr;
  canvas.height = H*dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr,dpr);
  return {{ctx,W,H,dpr}};
}}

function drawLine(ctx, xs, ys, color, alpha=1, dashed=false) {{
  ctx.save();
  ctx.strokeStyle=color;
  ctx.globalAlpha=alpha;
  ctx.lineWidth=1.5;
  if(dashed) ctx.setLineDash([6,3]);
  ctx.beginPath();
  let started=false;
  for(let i=0;i<xs.length;i++) {{
    if(ys[i]==null || ys[i]!=ys[i]) {{ started=false; continue; }}
    if(!started){{ ctx.moveTo(xs[i],ys[i]); started=true; }}
    else ctx.lineTo(xs[i],ys[i]);
  }}
  ctx.stroke();
  ctx.restore();
}}

function drawArea(ctx, xs, ys, color, baseY, alpha=0.12) {{
  const pts = xs.map((x,i)=>ys[i]!=null && ys[i]==ys[i] ? [x,ys[i]] : null).filter(Boolean);
  if(!pts.length) return;
  ctx.save();
  ctx.fillStyle=color;
  ctx.globalAlpha=alpha;
  ctx.beginPath();
  ctx.moveTo(pts[0][0],baseY);
  for(const [x,y] of pts) ctx.lineTo(x,y);
  ctx.lineTo(pts[pts.length-1][0],baseY);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}}

function _autoRange(vals) {{
  let lo=Infinity,hi=-Infinity;
  for(const v of vals) if(v!=null&&v==v){{ if(v<lo)lo=v; if(v>hi)hi=v; }}
  if(!isFinite(lo)) return {{lo:0,hi:1}};
  const pad=(hi-lo)*0.06||1;
  return {{lo:lo-pad,hi:hi+pad}};
}}

function _toX(idx,n,pad,W) {{ return pad + (idx/(n-1||1))*(W-2*pad); }}
function _toY(v,lo,hi,pad,H) {{
  if(v==null||v!=v) return null;
  return pad+(1-(v-lo)/(hi-lo||1))*(H-2*pad);
}}

function _drawAxis(ctx,W,H,pad,lo,hi,label,color,side='left',n_ticks=5) {{
  ctx.save();
  ctx.font='10px monospace';
  ctx.fillStyle=color;
  ctx.strokeStyle='#2a2d3e';
  ctx.lineWidth=1;
  for(let i=0;i<=n_ticks;i++) {{
    const v=lo+(hi-lo)*i/n_ticks;
    const y=pad+(1-i/n_ticks)*(H-2*pad);
    ctx.beginPath();
    ctx.moveTo(pad,y); ctx.lineTo(W-pad,y);
    ctx.stroke();
    const txt=Math.abs(v)<100?v.toFixed(1):Math.round(v).toString();
    if(side==='left')  ctx.fillText(txt,2,y+3);
    else               ctx.fillText(txt,W-pad+2,y+3);
  }}
  // Etiqueta eje
  ctx.save();
  ctx.translate(side==='left'?10:W-4, H/2);
  ctx.rotate(-Math.PI/2);
  ctx.textAlign='center';
  ctx.fillStyle=color;
  ctx.font='11px sans-serif';
  ctx.fillText(label,0,0);
  ctx.restore();
  ctx.restore();
}}

function _drawXTicks(ctx,n,pad,W,H,fechas,maxTick=8) {{
  ctx.save();
  ctx.font='9px monospace';
  ctx.fillStyle='#64748b';
  const step=Math.max(1,Math.floor(n/maxTick));
  for(let i=0;i<n;i+=step) {{
    const x=_toX(i,n,pad,W);
    const lbl=fechas[i]?fechas[i].substring(5):'';
    ctx.fillText(lbl,x-14,H-2);
  }}
  ctx.restore();
}}

// ── Gráfica superpuesta (dos ejes Y) ─────────────────────────────
function drawOverlay(id, ts, data1, data2, label1, label2, color1, color2) {{
  const cv = document.getElementById(id);
  if(!cv) return;
  const {{ctx,W,H}} = _pxDims(cv);
  const pad=44;

  ctx.fillStyle='#0f1117'; ctx.fillRect(0,0,W,H);

  const n=ts.length;
  if(n===0){{ ctx.fillStyle='#475569';ctx.fillText('Sin datos en este rango',W/2-40,H/2);return; }}

  const r1=_autoRange(data1), r2=_autoRange(data2);

  _drawAxis(ctx,W,H,pad,r1.lo,r1.hi,label1,color1,'left');
  _drawAxis(ctx,W,H,pad,r2.lo,r2.hi,label2,color2,'right');
  _drawXTicks(ctx,n,pad,W,H,ts);

  const xs=ts.map((_,i)=>_toX(i,n,pad,W));
  const ys1=data1.map(v=>_toY(v,r1.lo,r1.hi,pad,H));
  const ys2=data2.map(v=>_toY(v,r2.lo,r2.hi,pad,H));

  drawArea(ctx,xs,ys1,color1,_toY(0,r1.lo,r1.hi,pad,H)||H-pad);
  drawArea(ctx,xs,ys2,color2,_toY(0,r2.lo,r2.hi,pad,H)||H-pad);
  drawLine(ctx,xs,ys1,color1,0.9);
  drawLine(ctx,xs,ys2,color2,0.9,true);

  // Leyenda
  ctx.save();
  ctx.font='11px sans-serif';
  [[color1,label1,'─'],[color2,label2,'- -']].forEach(([c,l,s],i)=>{{
    ctx.fillStyle=c;
    ctx.fillText(s+' '+l, pad+10+i*200, 16);
  }});
  ctx.restore();
}}

// ── Gráfica simple de una variable ────────────────────────────────
function drawSimple(id, ts, data, label, color) {{
  const cv = document.getElementById(id);
  if(!cv) return;
  const {{ctx,W,H}} = _pxDims(cv);
  const pad=44;
  ctx.fillStyle='#0f1117'; ctx.fillRect(0,0,W,H);
  const n=ts.length;
  if(n===0) return;
  const r=_autoRange(data);
  _drawAxis(ctx,W,H,pad,r.lo,r.hi,label,color,'left');
  _drawXTicks(ctx,n,pad,W,H,ts);
  const xs=ts.map((_,i)=>_toX(i,n,pad,W));
  const ys=data.map(v=>_toY(v,r.lo,r.hi,pad,H));
  drawArea(ctx,xs,ys,color,H-pad);
  drawLine(ctx,xs,ys,color);
}}

// ═══════════════════════════════════════════════════════════════════
// RENDER PRINCIPAL
// ═══════════════════════════════════════════════════════════════════
function render() {{
  const diasObj = getDiasFiltrados();
  const series  = buildSeries(diasObj);
  const n = series.t.length;

  // Downsample para rendimiento
  const MAX=1500;
  const ts  = downsample(series.t,  MAX);
  const rad = downsample(series.rad, MAX);
  const pac = downsample(series.pac, MAX);
  const temp= downsample(series.temp,MAX);
  const hum = downsample(series.hum, MAX);
  const vie = downsample(series.viento,MAX);
  const llu = downsample(series.lluvia,MAX);

  // Gráfica superpuesta
  drawOverlay('c-overlay', ts, rad, pac,
              'Rad. Solar WL (W/m²)', 'Potencia AC SMA (W)',
              COLORS.rad, COLORS.pac);

  // Gráficas simples
  drawSimple('c-temp',   ts, temp, 'Temp (°C)',   COLORS.temp);
  drawSimple('c-hum',    ts, hum,  'Hum (%)',     COLORS.hum);
  drawSimple('c-viento', ts, vie,  'Viento km/h', COLORS.viento);
  drawSimple('c-lluvia', ts, llu,  'Lluvia mm',   COLORS.lluvia);

  // Actualizar rango label
  const ks = Object.keys(diasObj).sort();
  document.getElementById('lbl-rango').textContent =
    ks.length ? ks[0] + ' → ' + ks[ks.length-1] + '  (' + ks.length + ' días, ' + n + ' puntos)' : '';

  // Estadísticos dinámicos del rango actual
  renderStats(series);
}}

// ═══════════════════════════════════════════════════════════════════
// ESTADÍSTICOS DINÁMICOS (JS manual, sin librerías)
// ═══════════════════════════════════════════════════════════════════
function jsStats(arr) {{
  const vals = arr.filter(v=>v!=null&&v==v);
  const n=vals.length;
  if(!n) return {{n:0,media:null,sigma:null,vmin:null,vmax:null}};
  let s=0,lo=vals[0],hi=vals[0];
  for(const v of vals){{s+=v;if(v<lo)lo=v;if(v>hi)hi=v;}}
  const m=s/n;
  let sv=0;
  for(const v of vals) sv+=(v-m)*(v-m);
  const sigma=n>1?Math.sqrt(sv/(n-1)):0;
  return {{n,media:m,sigma,vmin:lo,vmax:hi}};
}}

function renderStats(series) {{
  const defs = [
    ['wl_solar_rad', series.rad,    'Radiación Solar WL (W/m²)',  COLORS.rad],
    ['sma_pac',      series.pac,    'Potencia AC SMA (W)',         COLORS.pac],
    ['wl_temp',      series.temp,   'Temperatura WL (°C)',         COLORS.temp],
    ['wl_hum',       series.hum,    'Humedad WL (%)',              COLORS.hum],
    ['wl_viento',    series.viento, 'Viento WL (km/h)',            COLORS.viento],
    ['wl_lluvia',    series.lluvia, 'Precipitación WL (mm)',       COLORS.lluvia],
  ];
  const sg = document.getElementById('stats-grid');
  sg.innerHTML = '';
  for(const [_k, data, label, color] of defs) {{
    const s = jsStats(data);
    const fmt = v => v==null?'—':(Math.abs(v)>=100?v.toFixed(1):v.toFixed(2));
    const card = document.createElement('div');
    card.className = 'stats-card';
    card.innerHTML = `
      <h4 style="color:${{color}}">${{label}}</h4>
      <div class="stats-row"><span>N</span><span>${{s.n.toLocaleString()}}</span></div>
      <div class="stats-row"><span>Media (x̄)</span><span>${{fmt(s.media)}}</span></div>
      <div class="stats-row"><span>Desv. Est. (σ)</span><span>${{fmt(s.sigma)}}</span></div>
      <div class="stats-row"><span>Mínimo</span><span>${{fmt(s.vmin)}}</span></div>
      <div class="stats-row"><span>Máximo</span><span>${{fmt(s.vmax)}}</span></div>
    `;
    sg.appendChild(card);
  }}
}}

// ═══════════════════════════════════════════════════════════════════
// CONTROLES DE FECHA
// ═══════════════════════════════════════════════════════════════════
function aplicarFiltro() {{
  _filtroDesde = document.getElementById('inp-desde').value || null;
  _filtroHasta = document.getElementById('inp-hasta').value || null;
  render();
}}

function resetFiltro() {{
  _filtroDesde = null; _filtroHasta = null;
  document.getElementById('inp-desde').value = '';
  document.getElementById('inp-hasta').value = '';
  document.querySelectorAll('.pbtn').forEach(b=>b.classList.remove('active'));
  render();
}}

function setPeriodo(dias) {{
  const max = RAW.rango.max;
  const hasta = new Date(max + 'T00:00:00');
  const desde = addDays(hasta, -dias);
  _filtroDesde = fechaStr(desde);
  _filtroHasta = max;
  document.getElementById('inp-desde').value = _filtroDesde;
  document.getElementById('inp-hasta').value = _filtroHasta;
  document.querySelectorAll('.pbtn').forEach(b=>{{
    b.classList.toggle('active', b.textContent.includes(dias===7?'7':dias===30?'30':dias===90?'3':dias===180?'6':'1'));
  }});
  render();
}}

// ═══════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════
window.addEventListener('load', ()=>{{
  // Pre-rellenar inputs con rango global
  document.getElementById('inp-desde').value = RAW.rango.min||'';
  document.getElementById('inp-hasta').value = RAW.rango.max||'';
  renderFusionCal();
  _initFusionCalListener();
  render();
}});

window.addEventListener('resize', ()=>{{ render(); }});
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(nombre), exist_ok=True)
    with open(nombre, "w", encoding="utf-8") as fh:
        fh.write(html)
    size_mb = os.path.getsize(nombre) / 1024 / 1024
    print(f"  [HTML] {nombre} ({size_mb:.1f} MB)")
    return nombre


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 62)
    print("  EXPORTAR FUSIÓN — Clima + Solar")
    print("=" * 62)

    # ── 1. Cargar WeatherLink ─────────────────────────────────────────
    print("\n[1/5] Cargando WeatherLink...")
    archivos_wl = sorted(
        [f for f in _WL_DIR.glob("7GT-*v2.csv") if "_clean" not in f.name]
        if hasattr(_WL_DIR, 'glob') else []
    )
    from pathlib import Path
    _WL_PATH = Path(os.path.join(_PROJ_ROOT, "datos_crudos", "weatherlink"))
    archivos_wl = sorted(
        f for f in _WL_PATH.glob("7GT-*v2.csv") if "_clean" not in f.name
    )

    dfs_wl, freq_wl = [], 5
    for ruta in archivos_wl:
        print(f"  → {ruta.name}")
        df_c, freq = cargar_weatherlink(str(ruta))
        dfs_wl.append(df_c)
        freq_wl = freq
        print(f"     {len(df_c):,} registros, {freq} min")

    df_wl_total = pd.DataFrame()
    if dfs_wl:
        df_wl_total = (pd.concat(dfs_wl)
                       .sort_values("Date & Time")
                       .drop_duplicates("Date & Time")
                       .reset_index(drop=True))
        print(f"  WL total: {len(df_wl_total):,} registros")

    # ── 2. Cargar SMA ─────────────────────────────────────────────────
    print("\n[2/5] Cargando SMA Solar...")
    df_sma = cargar_sma()
    freq_sma = df_sma.attrs.get("freq_min", 15) if not df_sma.empty else 15
    print(f"  SMA total: {len(df_sma):,} registros, {freq_sma} min")

    # ── 3. Fusionar ───────────────────────────────────────────────────
    print("\n[3/5] Fusionando datos...")
    df_fusion = fusionar_datos(df_wl_total, df_sma,
                                freq_min=max(freq_wl, freq_sma))
    print(f"  Fusión: {len(df_fusion):,} registros")

    # ── 4. Exportar JSON ──────────────────────────────────────────────
    print("\n[4/5] Exportando JSON mensual...")
    os.makedirs(_EXPORT_DIR, exist_ok=True)
    archivos_json = exportar_json_rangos(df_fusion, _EXPORT_DIR)
    print(f"  → {len(archivos_json)} archivos JSON en {_EXPORT_DIR}")

    # ── 5. Dashboard ──────────────────────────────────────────────────
    print("\n[5/5] Generando dashboard de fusión...")
    data_json = construir_json_fusion(df_fusion)
    salida = os.path.join(_DASH_DIR, "dashboard_fusion.html")
    generar_dashboard_fusion(data_json, salida)

    import webbrowser
    webbrowser.open(f"file://{os.path.abspath(salida)}")

    print(f"\n{'='*62}")
    print(f"  ✅ Completado")
    print(f"  Dashboard: {salida}")
    print(f"  JSON:      {_EXPORT_DIR}")
    print(f"{'='*62}\n")
