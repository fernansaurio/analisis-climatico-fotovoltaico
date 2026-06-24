#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ejecutar_proyecto.py — Punto de entrada único del proyecto
===========================================================
Uso:
  python3 ejecutar_proyecto.py

Antes de correr, coloca tus archivos CSV en datos_crudos/:
  • WeatherLink (7GT-EEP / 7GT-UES): exportados de weatherlink.com
  • SMA Solar: archivos CSV diarios del portal del inversor SMA

El script hace TODO automáticamente:
  0. Valida dependencias Python (pandas, numpy)
  1. Detecta y ordena los CSV en datos_crudos/   ← automático
  2. Verifica las librerías C++ compiladas
  3. Carga y cura los datos WeatherLink (EEP + UES)
  4. Carga y cura los datos SMA Solar
  5. Corre el motor estadístico C++ sobre todas las variables
  6. Exporta JSON mensuales a dashboard/exportaciones/
  7. Genera dashboard_fusion.html   (Rad Solar vs Potencia)
  8. Genera dashboard_solar.html    (planta fotovoltaica)
  9. Genera dashboard_msn_interactivo.html (sensores climáticos)
 10. Abre todas las páginas en el navegador
 11. Sincroniza docs/ para GitHub Pages

Dónde quedan los datos:
  dashboard/  → archivos HTML listos para abrir en el navegador
  docs/       → copia sincronizada para GitHub Pages (./publicar.sh)
  datos_crudos/weatherlink/ → CSVs WeatherLink ordenados
  datos_crudos/sma_solar/   → CSVs SMA ordenados y renombrados
"""

import os
import sys
import time
import shutil
import webbrowser
import subprocess

# ─── Detección de WSL ─────────────────────────────────────────────────
def _detectar_wsl():
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False

_EN_WSL = _detectar_wsl()

# ─── Rutas base ───────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, "src")
CORE = os.path.join(ROOT, "core_math")
DASH = os.path.join(ROOT, "dashboard")
DOCS = os.path.join(ROOT, "docs")
EXPO = os.path.join(DASH, "exportaciones")

sys.path.insert(0, SRC)
sys.path.insert(0, CORE)

os.makedirs(EXPO, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════
# GENERADOR DE INDEX.HTML (funciona en file:// y GitHub Pages)
# ══════════════════════════════════════════════════════════════════════

def _generar_index_html() -> str:
    """Genera la página de inicio de navegación entre dashboards.
    No usa CDN ni recursos externos — funciona offline con file://."""
    return """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dashboards — Análisis Climático y Fotovoltaico</title>
  <style>
    :root {
      --bg:#0f172a; --card:#1e293b; --brd:#334155;
      --tx:#e2e8f0; --tx2:#94a3b8;
      --blue:#38bdf8; --green:#4ade80; --yellow:#fbbf24; --purple:#a78bfa;
    }
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:var(--bg);color:var(--tx);
      font-family:'Segoe UI',Arial,sans-serif;
      min-height:100vh;display:flex;flex-direction:column;
      align-items:center;justify-content:center;padding:32px 16px}
    h1{font-size:1.6rem;font-weight:700;margin-bottom:6px;text-align:center}
    .sub{color:var(--tx2);font-size:.85rem;margin-bottom:40px;text-align:center;line-height:1.6}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
      gap:20px;width:100%;max-width:920px}
    .card{background:var(--card);border:1px solid var(--brd);border-radius:16px;
      padding:28px 24px;text-decoration:none;color:inherit;
      transition:border-color .2s,transform .2s;display:flex;flex-direction:column;gap:10px}
    .card:hover{border-color:var(--blue);transform:translateY(-3px)}
    .icon{font-size:2.2rem}
    .card-title{font-size:1.05rem;font-weight:600}
    .card-desc{font-size:.8rem;color:var(--tx2);line-height:1.5}
    .badge{display:inline-block;font-size:.65rem;font-weight:600;
      padding:2px 8px;border-radius:99px;margin-top:6px}
    footer{margin-top:48px;color:var(--tx2);font-size:.7rem;text-align:center;line-height:1.9}
    footer code{color:#475569;font-size:.65rem}
  </style>
</head>
<body>
  <h1>&#127774; Análisis Climático y Fotovoltaico</h1>
  <p class="sub">
    &#128205; 7GT-EEP: San Luis Talpa, La Paz &nbsp;·&nbsp;
    7GT-UES: Universidad de El Salvador &nbsp;·&nbsp; SMA Solar: EIE<br>
    AEL115 · Ciclo I-2026 · Facultad de Ingeniería y Arquitectura, UES
  </p>

  <div class="grid">
    <a class="card" href="dashboard_msn_interactivo.html">
      <div class="icon">&#127780;</div>
      <div class="card-title">Dashboard Climático</div>
      <div class="card-desc">
        Análisis estadístico completo de temperatura, humedad, radiación solar,
        lluvia, viento y presión. Gráficas uPlot interactivas, tendencia lineal C++,
        mapa de calor horario, rosa de vientos, eventos extremos y modelo predictivo.
      </div>
      <span class="badge" style="background:#0ea5e920;color:#38bdf8">EEP + UES · Histórico completo</span>
    </a>

    <a class="card" href="dashboard_solar.html">
      <div class="icon">&#9728;&#65039;</div>
      <div class="card-title">Dashboard Solar SMA</div>
      <div class="card-desc">
        Producción fotovoltaica del sistema SMA EIE. Potencia AC/DC,
        energía diaria y mensual, rendimiento, horas de sol pico e irradiancia.
      </div>
      <span class="badge" style="background:#fbbf2420;color:#fbbf24">Sistema SMA · 2023–2026</span>
    </a>

    <a class="card" href="dashboard_fusion.html">
      <div class="icon">&#128279;</div>
      <div class="card-title">Fusión Radiación &#8596; Potencia</div>
      <div class="card-desc">
        Correlación directa entre la radiación solar medida por las estaciones
        climáticas y la potencia generada por el sistema fotovoltaico SMA.
      </div>
      <span class="badge" style="background:#a78bfa20;color:#a78bfa">WeatherLink + SMA fusionados</span>
    </a>
  </div>

  <footer>
    <div>Generado localmente con Python · C++ (AjusteCurvas, MetodosRaices, AlgebraLineal) · Chart.js · uPlot</div>
    <div style="margin-top:8px">
      MAURICIO A. MUÑOZ CONTRERAS <code>MC24021</code> &nbsp;·&nbsp;
      MARCELO X. MOLINA GOMEZ <code>MG24048</code> &nbsp;·&nbsp;
      DIEGO J. MENDOZA PRUDENCIO <code>MP24048</code><br>
      FERNANDO J. PADILLA CRUZ <code>PC24039</code> &nbsp;·&nbsp;
      OSCAR M. VELASQUEZ VILLANUEVA <code>VV24002</code>
    </div>
    <div style="margin-top:6px;font-size:.62rem;color:#4b5563">
      &copy; 2026 · Universidad de El Salvador, Facultad de Ingeniería y Arquitectura
    </div>
  </footer>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════
# UTILIDADES DE TERMINAL
# ══════════════════════════════════════════════════════════════════════

def titulo(texto):
    linea = "═" * 62
    print(f"\n{linea}")
    print(f"  {texto}")
    print(linea)

def paso(n, texto):
    print(f"\n[{n}] {texto}")
    print("─" * 50)

def ok(texto):
    print(f"  ✅ {texto}")

def warn(texto):
    print(f"  ⚠️  {texto}")

def err(texto):
    print(f"  ❌ {texto}")

def abrir_html(ruta):
    """Abre un archivo HTML en el navegador si existe. Compatible con WSL."""
    if not os.path.exists(ruta):
        warn(f"No encontrado: {os.path.basename(ruta)}")
        return
    abspath = os.path.abspath(ruta)
    nombre  = os.path.basename(ruta)
    if _EN_WSL:
        # En WSL, webbrowser.open("file:///home/...") llama al navegador de
        # Windows con una ruta Linux que Windows no puede resolver.
        # wslpath -w convierte a "\\wsl.localhost\Ubuntu\home\..." y
        # cmd.exe /c start lo abre correctamente en el browser de Windows.
        try:
            win_path = subprocess.check_output(
                ["wslpath", "-w", abspath],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "", win_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            ok(f"Abierto (WSL→Windows): {nombre}")
        except Exception:
            warn(f"WSL: no se pudo abrir automáticamente.")
            print(f"       Abre manualmente: {abspath}")
    else:
        webbrowser.open(f"file://{abspath}")
        ok(f"Abierto: {nombre}")


# ══════════════════════════════════════════════════════════════════════
# PASO 0A — VALIDAR DEPENDENCIAS PYTHON
# ══════════════════════════════════════════════════════════════════════

def verificar_dependencias():
    """Comprueba que pandas y numpy están instalados antes de importarlos."""
    paso("0a", "Validando dependencias Python")
    REQUERIDAS = [
        ("pandas",  "Manipulación de datos CSV"),
        ("numpy",   "Cálculos numéricos y arrays ctypes"),
    ]
    faltantes = []
    for modulo, descripcion in REQUERIDAS:
        try:
            __import__(modulo)
            version = __import__(modulo).__version__
            ok(f"{modulo} {version}  — {descripcion}")
        except ImportError:
            err(f"{modulo}  NO instalado  — {descripcion}")
            faltantes.append(modulo)

    if faltantes:
        print()
        print("  ┌─────────────────────────────────────────────────────┐")
        print("  │  Faltan dependencias. Instálalas con:               │")
        print(f"  │    pip install {' '.join(faltantes):<37}│")
        print("  │                                                     │")
        print("  │  Si no tienes pip:  sudo apt install python3-pip   │")
        print("  └─────────────────────────────────────────────────────┘")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════
# PASO 0B — AUTO-DETECCIÓN Y ORDENADO DE DATOS CSV
# ══════════════════════════════════════════════════════════════════════

def auto_ordenar_datos():
    """
    Escanea datos_crudos/ recursivamente y mueve cada CSV al subdirectorio
    correcto (weatherlink/ o sma_solar/) según su contenido.
    Llama la lógica de ordenar_datos.py directamente.
    """
    paso("0b", "Auto-detección y ordenado de archivos CSV")

    WL_DEST  = os.path.join(ROOT, "datos_crudos", "weatherlink")
    SMA_DEST = os.path.join(ROOT, "datos_crudos", "sma_solar")
    ENTRADA  = os.path.join(ROOT, "datos_crudos")

    os.makedirs(WL_DEST,  exist_ok=True)
    os.makedirs(SMA_DEST, exist_ok=True)

    import re, shutil as _sh

    _PAT_ISO   = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:\(\d+\))?\.csv$", re.I)
    _PAT_LEGAC = re.compile(r"^(\d{2})-(\d{2})-(\d{4})(?:\(\d+\))?\.csv$", re.I)

    def _identificar(ruta):
        for enc in ("utf-8", "latin-1"):
            try:
                with open(ruta, encoding=enc, errors="replace") as f:
                    l0 = f.readline().strip().strip('"')
                    f.readline()
                if "7GT-EEP" in l0.upper(): return "WL-EEP"
                if "7GT-UES" in l0.upper(): return "WL-UES"
                if l0.upper().startswith("CSV-EXPORT"): return "SMA"
                break
            except Exception:
                continue
        return "DESCONOCIDO"

    def _dest_sma(src, dest_dir):
        base = os.path.basename(src)
        m = _PAT_ISO.match(base)
        if m:
            nombre = f"{m.group(1)}-{m.group(2)}-{m.group(3)}.csv"
        else:
            m = _PAT_LEGAC.match(base)
            nombre = f"{m.group(3)}-{m.group(1)}-{m.group(2)}.csv" if m else base
        dest = os.path.join(dest_dir, nombre)
        if os.path.exists(dest) and os.path.abspath(dest) != os.path.abspath(src):
            stem, n = nombre[:-4], 1
            while os.path.exists(dest):
                dest = os.path.join(dest_dir, f"{stem}({n}).csv"); n += 1
        return dest

    n_wl = n_sma = n_lugar = n_unk = 0
    todos = []
    for dp, _, fnames in os.walk(ENTRADA):
        for fn in sorted(fnames):
            if fn.lower().endswith(".csv") and not fn.endswith("_clean.csv"):
                todos.append(os.path.join(dp, fn))

    if not todos:
        warn("No se encontraron CSVs en datos_crudos/ — coloca tus archivos allí")
        return

    for ruta in todos:
        tipo = _identificar(ruta)
        fname = os.path.basename(ruta)
        if tipo in ("WL-EEP", "WL-UES"):
            dest = os.path.join(WL_DEST, fname)
            if os.path.abspath(ruta) == os.path.abspath(dest):
                n_lugar += 1
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                _sh.move(ruta, dest)
                n_wl += 1
        elif tipo == "SMA":
            dest = _dest_sma(ruta, SMA_DEST)
            if os.path.abspath(ruta) == os.path.abspath(dest):
                n_lugar += 1
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                _sh.move(ruta, dest)
                n_sma += 1
        else:
            n_unk += 1

    ok(f"WeatherLink movidos: {n_wl}  |  SMA movidos: {n_sma}  "
       f"|  Ya en lugar: {n_lugar}  |  Desconocidos: {n_unk}")

    # Verificar que hay datos mínimos para continuar
    wl_files = [f for f in os.listdir(WL_DEST)
                if f.endswith(".csv") and not f.endswith("_clean.csv")]
    sma_files = [f for f in os.listdir(SMA_DEST) if f.endswith(".csv")]
    if not wl_files:
        print()
        print("  ┌─────────────────────────────────────────────────────┐")
        print("  │  No se encontraron datos WeatherLink.               │")
        print("  │                                                     │")
        print("  │  Coloca en datos_crudos/ los archivos CSV de las   │")
        print("  │  estaciones 7GT-EEP y 7GT-UES (weatherlink.com).  │")
        print("  └─────────────────────────────────────────────────────┘")
        sys.exit(1)
    if not sma_files:
        warn("No se encontraron datos SMA — el dashboard solar quedará vacío")

    print(f"  Archivos WeatherLink listos: {len(wl_files)}")
    print(f"  Archivos SMA listos:         {len(sma_files)}")


# ══════════════════════════════════════════════════════════════════════
# PASO 1 — VERIFICAR LIBRERÍAS C++
# ══════════════════════════════════════════════════════════════════════

def verificar_cpp():
    paso(1, "Verificando librerías C++ (wrappers ctypes)")
    resultados = {}

    try:
        from ajuste_curvas import AjusteCurvas
        import numpy as np
        ac = AjusteCurvas()
        # Prueba real: calcular media de [1,2,3,4,5] → debe dar 3.0
        datos = np.ascontiguousarray([[1.0],[2.0],[3.0],[4.0],[5.0]], dtype=np.float64)
        ac.establecer_datos(datos)
        mu = ac.media(0)
        assert abs(mu - 3.0) < 1e-9, f"media esperada 3.0, obtenida {mu}"
        sigma = ac.desviacion_estandar_metodo3(0)
        assert abs(sigma - 1.5811) < 0.001, f"sigma esperada ~1.581, obtenida {sigma}"
        p50 = ac.mediana(0)
        assert abs(p50 - 3.0) < 0.01, f"p50 esperada 3.0, obtenida {p50}"
        ok(f"AjusteCurvas  ✓  media={mu:.4f}  σ={sigma:.4f}  p50={p50:.4f}")
        resultados["ac"] = ac
    except Exception as e:
        err(f"AjusteCurvas: {e}")
        resultados["ac"] = None

    try:
        from metodos_raices import MetodosRaices
        mr = MetodosRaices()
        # Prueba: √2 via Newton-Raphson  f(x)=x²-2, f'(x)=2x
        raiz2, iters = mr.newton_raphson(
            lambda x: x*x - 2.0, lambda x: 2.0*x, 1.5, tol=1e-12, max_iter=100
        )
        assert abs(raiz2 - 1.41421356) < 1e-6, f"√2 esperado 1.41421, obtenido {raiz2}"
        ok(f"MetodosRaices ✓  √2 = {raiz2:.8f}  ({iters} iters Newton-Raphson)")
        resultados["mr"] = mr
    except Exception as e:
        err(f"MetodosRaices: {e}")
        resultados["mr"] = None

    try:
        from algebra_lineal_lib import AlgebraLineal
        al = AlgebraLineal(filas=2, cols=2)
        ok(f"AlgebraLineal ✓  (métodos: gauss, gauss_jordan, inversa, determinante...)")
        resultados["al"] = al
    except Exception as e:
        err(f"AlgebraLineal: {e}")
        resultados["al"] = None

    n_ok = sum(1 for v in resultados.values() if v is not None)
    print(f"\n  Librerías C++ activas: {n_ok}/3")
    if n_ok == 0:
        err("Ninguna librería C++ disponible — abortando")
        sys.exit(1)
    return resultados


# ══════════════════════════════════════════════════════════════════════
# PASO 2-3 — CARGA Y CURACIÓN DE DATOS
# ══════════════════════════════════════════════════════════════════════

def cargar_datos():
    from ingesta import (cargar_weatherlink, cargar_sma, fusionar_datos,
                          exportar_json_rangos, detectar_frecuencia,
                          reporte_curacion, FECHA_INICIO)
    import pandas as pd
    from pathlib import Path

    WL_DIR  = Path(ROOT) / "datos_crudos" / "weatherlink"
    SMA_DIR = Path(ROOT) / "datos_crudos" / "sma_solar"

    # ── WeatherLink ───────────────────────────────────────────────────
    paso(2, "Cargando y curando datos WeatherLink (EEP + UES)")
    archivos_wl = sorted(
        f for f in WL_DIR.glob("7GT-*v2.csv") if "_clean" not in f.name
    )
    if not archivos_wl:
        err(f"No se encontraron CSVs WeatherLink en {WL_DIR}")
        return None, None, None

    dfs_wl, freq_wl = [], 5
    for ruta in archivos_wl:
        estacion = "EEP" if "EEP" in ruta.name else "UES"
        print(f"  Procesando {estacion}: {ruta.name}")
        df_c, freq = cargar_weatherlink(str(ruta))
        dfs_wl.append(df_c)
        freq_wl = freq
        nan_pct = df_c.isna().sum().sum() / max(df_c.size, 1) * 100
        print(f"    → {len(df_c):,} registros  |  freq={freq} min  |  NaN={nan_pct:.1f}%")

    df_wl = (pd.concat(dfs_wl)
               .sort_values("Date & Time")
               .drop_duplicates("Date & Time")
               .reset_index(drop=True))
    freq_wl = detectar_frecuencia(df_wl)
    ok(f"WeatherLink total: {len(df_wl):,} registros  |  freq={freq_wl} min  |  "
       f"rango: {df_wl['Date & Time'].iloc[0].date()} → {df_wl['Date & Time'].iloc[-1].date()}")

    # ── SMA Solar ─────────────────────────────────────────────────────
    paso(3, "Cargando y curando datos SMA Solar")
    # Descubrimiento dinámico: cualquier subdirectorio (o la raíz) que tenga CSVs
    carpetas = []
    for dirpath, _, fnames in os.walk(str(SMA_DIR)):
        if any(f.lower().endswith(".csv") for f in fnames):
            carpetas.append(Path(dirpath))
    carpetas = sorted(carpetas)
    df_sma = cargar_sma(carpetas)
    freq_sma = df_sma.attrs.get("freq_min", 15)
    if df_sma.empty:
        warn("No se cargaron datos SMA")
    else:
        nan_pac = df_sma["pac_total"].isna().sum()
        pct_pac = 100 * nan_pac / len(df_sma)
        ok(f"SMA total: {len(df_sma):,} registros  |  freq={freq_sma} min  |  "
           f"rango: {df_sma['ts'].iloc[0].date()} → {df_sma['ts'].iloc[-1].date()}")
        print(f"    pac_total NaN={nan_pac:,} ({pct_pac:.1f}%) — esperado: horas nocturnas")

    return df_wl, df_sma, freq_wl, freq_sma


# ══════════════════════════════════════════════════════════════════════
# PASO 4 — MOTOR ESTADÍSTICO C++
# ══════════════════════════════════════════════════════════════════════

def calcular_estadisticos_cpp(df_wl, df_sma, libs):
    """
    Ejecuta el motor estadístico C++ (AjusteCurvas) sobre variables clave.
    Muestra tabla de resultados. Sin .mean()/.std()/.max()/.min() de pandas/numpy.
    """
    paso(4, "Motor Estadístico C++ — Variables clave")
    import numpy as np

    ac_cls = None
    try:
        from ajuste_curvas import AjusteCurvas
        ac_cls = AjusteCurvas
    except Exception:
        pass

    mr = libs.get("mr")

    def _sqrt_nr(x):
        """√x via Newton-Raphson C++ (mr.newton_raphson) o Babilónico Python."""
        x = float(x)
        if x <= 0:
            return 0.0
        if mr is not None:
            try:
                val, _ = mr.newton_raphson(
                    lambda v: v*v - x, lambda v: 2.0*v, x/2.0, tol=1e-12, max_iter=100
                )
                return val
            except Exception:
                pass
        # Fallback Babilónico (sin math.sqrt)
        g = x / 2.0
        for _ in range(60):
            g2 = (g + x / g) / 2.0
            if abs(g2 - g) < 1e-12:
                return g2
            g = g2
        return g

    def _media_m(lst):
        n = len(lst)
        return sum(lst) / n if n else float("nan")

    def _maximo_m(lst):
        m = lst[0]
        for v in lst[1:]: m = v if v > m else m
        return m

    def _minimo_m(lst):
        m = lst[0]
        for v in lst[1:]: m = v if v < m else m
        return m

    def stats_cpp(serie, nombre):
        """Calcula estadísticos usando C++ (AjusteCurvas), con fallback manual."""
        vals = [float(v) for v in serie if v == v and v is not None]
        n = len(vals)
        if n == 0:
            return None

        if ac_cls is not None:
            try:
                ac = ac_cls()
                datos = np.ascontiguousarray([[v] for v in vals], dtype=np.float64)
                ac.establecer_datos(datos)
                ac.ordenar_por_columna(0, ascendente=True)
                return {
                    "nombre":  nombre,
                    "n":       n,
                    "media":   ac.media(0),
                    "sigma":   ac.desviacion_estandar_metodo3(0),
                    "vmax":    ac.maximo(0),
                    "vmin":    ac.minimo(0),
                    "p25":     ac.percentil(0, 25.0),
                    "p50":     ac.mediana(0),
                    "p75":     ac.percentil(0, 75.0),
                    "motor":   "C++ AjusteCurvas",
                }
            except Exception as e:
                warn(f"C++ fallo en {nombre}: {e} → Python manual")

        # Fallback Python puro (sin .mean/.std)
        mu = _media_m(vals)
        var = sum((v - mu)**2 for v in vals) / (n - 1) if n > 1 else 0.0
        return {
            "nombre": nombre,
            "n":      n,
            "media":  mu,
            "sigma":  _sqrt_nr(var),
            "vmax":   _maximo_m(vals),
            "vmin":   _minimo_m(vals),
            "p25":    float("nan"),
            "p50":    float("nan"),
            "p75":    float("nan"),
            "motor":  "Python manual",
        }

    # Variables a analizar
    variables_wl = [
        ("Temp - °C",            "Temperatura WL (°C)"),
        ("Hum - %",              "Humedad WL (%)"),
        ("Solar Rad - W/m^2",    "Radiación Solar WL (W/m²)"),
        ("Barometer - mb",       "Presión Barométrica WL (mb)"),
        ("Avg Wind Speed - km/h","Velocidad Viento WL (km/h)"),
        ("Rain - mm",            "Precipitación WL (mm)"),
    ]
    variables_sma = [
        ("pac_total", "Potencia AC Total SMA (W)"),
        ("irr",       "Irradiancia SMA (W/m²)"),
        ("tamb",      "T. Ambiente SMA (°C)"),
        ("tmod",      "T. Módulo Solar (°C)"),
    ]

    # También calcular correlación Radiación Solar WL ↔ Potencia SMA
    print(f"\n  {'Variable':<36} {'N':>8} {'Media':>10} {'σ':>10} "
          f"{'Mín':>8} {'Máx':>8} {'Motor'}")
    print("  " + "─" * 96)

    resultados = {}
    for col, nombre in variables_wl:
        if col not in df_wl.columns:
            continue
        s = stats_cpp(df_wl[col].dropna().tolist(), nombre)
        if s:
            resultados[nombre] = s
            print(f"  {nombre:<36} {s['n']:>8,} {s['media']:>10.3f} {s['sigma']:>10.3f} "
                  f"{s['vmin']:>8.2f} {s['vmax']:>8.2f}  {s['motor']}")

    print("  " + "─" * 96)
    if not df_sma.empty:
        for col, nombre in variables_sma:
            if col not in df_sma.columns:
                continue
            s = stats_cpp(df_sma[col].dropna().tolist(), nombre)
            if s:
                resultados[nombre] = s
                print(f"  {nombre:<36} {s['n']:>8,} {s['media']:>10.3f} {s['sigma']:>10.3f} "
                      f"{s['vmin']:>8.2f} {s['vmax']:>8.2f}  {s['motor']}")

    # Correlación de Pearson Radiación WL ↔ Potencia SMA (vía fusión)
    print()
    if "Solar Rad - W/m^2" in df_wl.columns and not df_sma.empty:
        from ingesta import fusionar_datos
        df_f_test = fusionar_datos(df_wl, df_sma, freq_min=15)
        if not df_f_test.empty and "wl_solar_rad" in df_f_test.columns \
                and "sma_pac" in df_f_test.columns:
            xs = df_f_test["wl_solar_rad"].dropna().tolist()
            ys = df_f_test["sma_pac"].dropna().tolist()
            # Pearson manual (sin scipy/numpy)
            n_p = min(len(xs), len(ys))
            if n_p > 1 and ac_cls is not None:
                try:
                    import numpy as np
                    ac_p = ac_cls()
                    mat = np.ascontiguousarray(
                        [[xs[i], ys[i]] for i in range(n_p)], dtype=np.float64
                    )
                    ac_p.establecer_datos(mat)
                    r = ac_p.pearson_correlation(0, 1)   # método correcto
                    ok(f"Correlación Pearson C++  Rad.Solar WL ↔ Potencia SMA: r = {r:.6f}")
                    print(f"    Interpretación: {'Muy fuerte' if abs(r)>0.9 else 'Fuerte' if abs(r)>0.7 else 'Moderada'}")
                except Exception as e:
                    warn(f"Pearson C++ falló: {e}")
            del df_f_test

    return resultados


# ══════════════════════════════════════════════════════════════════════
# PASO 5-8 — EXPORTAR JSON + GENERAR DASHBOARDS
# ══════════════════════════════════════════════════════════════════════

def exportar_y_generar(df_wl, df_sma, freq_wl, freq_sma):
    from ingesta import fusionar_datos, exportar_json_rangos
    import pandas as pd

    # ── Fusionar datos ─────────────────────────────────────────────────
    paso(5, "Fusionando WeatherLink + SMA Solar (merge_asof)")
    df_fusion = fusionar_datos(df_wl, df_sma, freq_min=max(freq_wl, freq_sma))
    n_f = len(df_fusion)
    if df_fusion.empty:
        warn("Fusión vacía — sin datos solapados")
    else:
        wl_ok  = df_fusion["wl_solar_rad"].notna().sum() if "wl_solar_rad" in df_fusion.columns else 0
        sma_ok = df_fusion["sma_pac"].notna().sum() if "sma_pac" in df_fusion.columns else 0
        ok(f"Fusión: {n_f:,} registros  |  wl_solar_rad={wl_ok:,}  |  sma_pac={sma_ok:,}")

    # ── Exportar JSON mensual ──────────────────────────────────────────
    paso(6, f"Exportando JSON mensual → dashboard/exportaciones/")
    if not df_fusion.empty:
        archivos_json = exportar_json_rangos(df_fusion, EXPO)
        ok(f"{len(archivos_json)} archivos JSON exportados")
    else:
        warn("Sin datos fusionados para exportar")
        archivos_json = []

    # ── Dashboard fusión (Rad Solar vs Potencia, date pickers) ────────
    paso(7, "Generando dashboard_fusion.html")
    salida_fusion = None
    try:
        from exportar_fusion import construir_json_fusion, generar_dashboard_fusion
        data_json = construir_json_fusion(df_fusion)
        salida_fusion = os.path.join(DASH, "dashboard_fusion.html")
        generar_dashboard_fusion(data_json, salida_fusion)
        ok(f"dashboard_fusion.html generado ({os.path.getsize(salida_fusion)/1024/1024:.1f} MB)")
    except Exception as e:
        err(f"Dashboard fusión: {e}")
        import traceback; traceback.print_exc()

    # ── Dashboard Solar SMA ───────────────────────────────────────────
    paso(8, "Generando dashboard_solar.html")
    salida_solar = None
    try:
        from analisis_sma import analizar_sistema_solar, generar_dashboard_solar_canvas
        resultado_sma = analizar_sistema_solar(verbose=True)
        if resultado_sma:
            salida_solar = os.path.join(DASH, "dashboard_solar.html")
            generar_dashboard_solar_canvas(resultado_sma, salida_solar)
            ok(f"dashboard_solar.html ({os.path.getsize(salida_solar)/1024/1024:.1f} MB)")
        else:
            warn("analizar_sistema_solar() devolvió None")
    except Exception as e:
        err(f"Dashboard solar: {e}")
        import traceback; traceback.print_exc()

    # ── Dashboard Climático MSN ───────────────────────────────────────
    paso(9, "Generando dashboard_msn_interactivo.html")
    salida_msn = None
    try:
        from analisis_climatico import (concatenar_estacion,
                                         generar_dashboard_msn_interactivo,
                                         calcular_correlaciones,
                                         _cargar_cache, _guardar_cache,
                                         _hash_archivos,
                                         calcular_estadisticos,
                                         calcular_estadisticos_mensuales,
                                         grafico_comparativo, grafico_serie,
                                         histograma, boxplot_mensual,
                                         rosa_de_vientos, grafico_pearson,
                                         _serie, log2_manual)
        import math
        WL_DIR = os.path.join(ROOT, "datos_crudos", "weatherlink")
        ARCHIVOS_EEP = [
            os.path.join(WL_DIR, "7GT-EEP_1-1-25_12-00_AM_1_Year_1779324867_v2.csv"),
            os.path.join(WL_DIR, "7GT-EEP_1-1-26_12-00_AM_1_Year_1779324876_v2.csv"),
        ]
        ARCHIVOS_UES = [
            os.path.join(WL_DIR, "7GT-UES_1-1-25_12-00_AM_1_Year_1779324630_v2.csv"),
            os.path.join(WL_DIR, "7GT-UES_1-1-26_12-00_AM_1_Year_1779324751_v2.csv"),
        ]

        # Intentar cargar desde caché primero
        hash_actual = _hash_archivos(ARCHIVOS_EEP + ARCHIVOS_UES)
        cache = _cargar_cache(hash_actual)

        if cache and cache.get("figs"):
            print("  Usando caché existente con figuras...")
            df_eep        = cache["df_eep"]
            df_ues        = cache["df_ues"]
            figs          = cache["figs"]
            correlaciones = cache["correlaciones"]
            print(f"    → {len(df_eep):,} registros EEP · {len(df_ues):,} registros UES")
            print(f"    → {len(figs)} figuras cargadas desde caché")
        else:
            print("  Calculando desde cero (sin caché)...")
            print("  Cargando EEP...")
            df_eep = concatenar_estacion(ARCHIVOS_EEP)
            print(f"    → {len(df_eep):,} registros EEP")
            print("  Cargando UES...")
            df_ues = concatenar_estacion(ARCHIVOS_UES)
            print(f"    → {len(df_ues):,} registros UES")

            figs = {}
            # Comparativa y series
            for col, clave, tit, ylabel in [
                ("Temp - °C", "comp_temp",
                 "Temperatura Exterior — 7GT-EEP vs 7GT-UES", "Temp (°C)"),
            ]:
                figs[clave] = grafico_comparativo(df_eep, df_ues, col, tit, ylabel)

            for col, clave, color, lbl in [
                ("Temp - °C",         "serie_temp_ues", "#fca5a5", "Temp (°C)"),
                ("Hum - %",           "serie_hum_ues",  "#93c5fd", "Hum (%)"),
                ("Barometer - mb",    "serie_bar_ues",  "#6ee7b7", "Bar (mb)"),
                ("Solar Rad - W/m^2", "serie_solar_ues","#fde68a", "Solar (W/m²)"),
            ]:
                if col in df_ues.columns:
                    figs[clave] = grafico_serie(
                        df_ues, col,
                        f"Evolución Temporal: {lbl} (7GT-UES)", lbl, color)

            # Histogramas
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
                            figs[key] = histograma(s, f"{col} ({prefijo.upper()})", col, color)

            # Boxplots
            for col, clave, tit in [
                ("Temp - °C",      "box_temp_eep", "Boxplot Mensual — Temperatura (EEP)"),
                ("Temp - °C",      "box_temp_ues", "Boxplot Mensual — Temperatura (UES)"),
                ("Hum - %",        "box_hum_ues",  "Boxplot Mensual — Humedad (UES)"),
                ("Barometer - mb", "box_bar_ues",  "Boxplot Mensual — Presión (UES)"),
            ]:
                df_r = df_eep if "eep" in clave else df_ues
                if col in df_r.columns:
                    figs[clave] = boxplot_mensual(df_r, col, tit)

            # Rosas de vientos
            for df_r, clave, tit in [
                (df_eep, "wind_eep", "Rosa de los Vientos (7GT-EEP)"),
                (df_ues, "wind_ues", "Rosa de los Vientos (7GT-UES)"),
            ]:
                figs[clave] = rosa_de_vientos(df_r, tit)

            print("  Calculando correlaciones de Pearson inter-estacional (C++)...")
            correlaciones = calcular_correlaciones(df_eep, df_ues)
            figs["pearson"] = grafico_pearson(correlaciones)
            print(f"    → {len(correlaciones)} pares · {len(figs)} figuras generadas")

            # Guardar en caché para próximas ejecuciones
            _guardar_cache({
                "df_eep": df_eep, "df_ues": df_ues,
                "st_eep": {}, "st_ues": {},
                "st_mensual_ues": {},
                "figs": figs,
                "correlaciones": correlaciones,
            }, hash_actual)

        salida_msn = os.path.join(DASH, "dashboard_msn_interactivo.html")
        generar_dashboard_msn_interactivo(
            df_eep, df_ues, figs=figs, correlaciones=correlaciones,
            nombre=salida_msn
        )
        ok(f"dashboard_msn_interactivo.html ({os.path.getsize(salida_msn)/1024/1024:.1f} MB)")
    except Exception as e:
        err(f"Dashboard MSN: {e}")
        import traceback; traceback.print_exc()

    return salida_fusion, salida_solar, salida_msn


# ══════════════════════════════════════════════════════════════════════
# PASO FINAL — ABRIR EN NAVEGADOR
# ══════════════════════════════════════════════════════════════════════

def _iniciar_servidor_local(carpeta, puerto=8765):
    """Levanta un servidor HTTP en carpeta:puerto en un hilo daemon."""
    import http.server, threading, socketserver
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=carpeta, **kwargs)
        def log_message(self, *args):
            pass  # silenciar logs
    try:
        srv = socketserver.TCPServer(("", puerto), Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return puerto
    except OSError:
        return None  # puerto ocupado, no crítico


def abrir_dashboards(fusion, solar, msn):
    paso("→", "Abriendo dashboards en el navegador")
    time.sleep(0.5)

    if _EN_WSL:
        # En WSL, levantamos un servidor HTTP local y abrimos via localhost.
        # Esto evita tanto el problema de rutas como las restricciones CORS de
        # file:// en navegadores Windows (Chrome/Edge bloquean JS de rutas UNC).
        print("  ℹ️  Detectado WSL: iniciando servidor HTTP local en puerto 8765")
        puerto = _iniciar_servidor_local(DASH, 8765)
        if puerto:
            url_base = f"http://localhost:{puerto}"
            time.sleep(0.3)
            # Abrir en el navegador de Windows via cmd.exe
            try:
                url = f"{url_base}/index.html"
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "", url],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                ok(f"Servidor en {url_base}  →  abierto en el navegador de Windows")
                print(f"       Si no abre solo, ve a: {url}")
                print(f"       El servidor se detiene al cerrar esta terminal.")
            except Exception:
                warn("No se pudo abrir automáticamente.")
                print(f"       Abre manualmente en Windows: http://localhost:{puerto}/index.html")
        else:
            warn("Puerto 8765 ocupado. Intentando apertura directa...")
            abrir_html(os.path.join(DASH, "index.html"))
    else:
        # Linux normal: abrir con file://
        idx_local = os.path.join(DASH, "index.html")
        if os.path.exists(idx_local):
            abrir_html(idx_local)
            time.sleep(1.2)
        else:
            for ruta in [fusion, solar, msn]:
                if ruta and os.path.exists(ruta):
                    abrir_html(ruta)
                    time.sleep(1.2)


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    titulo("PROYECTO PROGRAMACIÓN NUMÉRICA — ANÁLISIS CLIMÁTICO/FOTOVOLTAICO")
    print(f"  Directorio: {ROOT}")
    print(f"  Python:     {sys.version.split()[0]}")
    print()
    print("  ╔═══════════════════════════════════════════════════════╗")
    print("  ║  CÓMO USAR ESTE PROYECTO                             ║")
    print("  ╠═══════════════════════════════════════════════════════╣")
    print("  ║  1. Coloca tus CSV en:  datos_crudos/                ║")
    print("  ║     • WeatherLink (7GT-EEP, 7GT-UES) de weatherlink.com ║")
    print("  ║     • SMA Solar: archivos diarios del portal SMA     ║")
    print("  ║  2. Corre:  python3 ejecutar_proyecto.py             ║")
    print("  ║     (los datos se detectan y ordenan automáticamente) ║")
    print("  ╠═══════════════════════════════════════════════════════╣")
    print("  ║  DÓNDE QUEDAN LOS RESULTADOS                         ║")
    print("  ║  dashboard/  → HTMLs listos para abrir               ║")
    print("  ║  docs/       → copia para GitHub Pages               ║")
    print("  ║  datos_crudos/weatherlink/ → CSVs WeatherLink        ║")
    print("  ║  datos_crudos/sma_solar/   → CSVs SMA normalizados   ║")
    print("  ╚═══════════════════════════════════════════════════════╝")
    t0 = time.time()

    # 0a. Validar dependencias Python
    verificar_dependencias()

    # 0b. Auto-detectar y ordenar datos CSV
    auto_ordenar_datos()

    # 1. Verificar C++
    libs = verificar_cpp()

    # 2-3. Cargar datos
    resultado_carga = cargar_datos()
    if resultado_carga[0] is None:
        err("Carga de datos fallida — revisa datos_crudos/")
        sys.exit(1)
    df_wl, df_sma, freq_wl, freq_sma = resultado_carga

    # 4. Motor estadístico C++
    calcular_estadisticos_cpp(df_wl, df_sma, libs)

    # 5-9. Exportar JSON + generar dashboards
    salida_fusion, salida_solar, salida_msn = exportar_y_generar(
        df_wl, df_sma, freq_wl, freq_sma
    )

    # Resumen final
    titulo("RESUMEN FINAL")
    elapsed = time.time() - t0
    print(f"  Tiempo total: {elapsed:.1f} s")
    print()
    for lbl, ruta in [
        ("Dashboard Fusión (Rad↔Potencia + date pickers)", salida_fusion),
        ("Dashboard Solar SMA",                             salida_solar),
        ("Dashboard MSN Climático",                         salida_msn),
        ("JSON exportaciones",                              EXPO),
    ]:
        estado = "✅" if (ruta and os.path.exists(ruta)) else "❌"
        print(f"  {estado}  {lbl}")
        if ruta and os.path.exists(ruta) and os.path.isfile(ruta):
            print(f"       {ruta} ({os.path.getsize(ruta)/1024/1024:.1f} MB)")
    print()

    # Generar index.html de navegación (funciona local y en GitHub Pages)
    index_contenido = _generar_index_html()
    for carpeta in [DASH, DOCS]:
        os.makedirs(carpeta, exist_ok=True)
        idx_path = os.path.join(carpeta, "index.html")
        with open(idx_path, "w", encoding="utf-8") as fh:
            fh.write(index_contenido)
    ok("index.html generado en dashboard/ y docs/")

    # Sincronizar docs/ con dashboard/ para GitHub Pages
    paso("→", "Sincronizando docs/ para GitHub Pages")
    os.makedirs(DOCS, exist_ok=True)
    for fname in ["dashboard_fusion.html", "dashboard_solar.html",
                  "dashboard_msn_interactivo.html"]:
        src_path = os.path.join(DASH, fname)
        dst_path = os.path.join(DOCS, fname)
        if os.path.exists(src_path):
            shutil.copy2(src_path, dst_path)
            ok(f"{fname} → docs/")

    # Abrir navegador con la página de inicio
    abrir_dashboards(salida_fusion, salida_solar, salida_msn)

    print(f"\n{'═'*62}\n")


if __name__ == "__main__":
    main()
