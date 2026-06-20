#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ejecutar_proyecto.py — Punto de entrada único del proyecto
===========================================================
Orquesta en orden:
  1. Verifica que las librerías C++ cargan correctamente
  2. Carga y cura los datos WeatherLink (EEP + UES)
  3. Carga y cura los datos SMA Solar
  4. Corre el motor estadístico C++ sobre todas las variables
  5. Exporta JSON mensuales a dashboard/exportaciones/
  6. Genera dashboard_fusion.html  (Rad Solar vs Potencia, date pickers)
  7. Genera dashboard_solar.html   (planta fotovoltaica)
  8. Genera dashboard_msn_interactivo.html (sensores climáticos)
  9. Abre todas las páginas web en el navegador
"""

import os
import sys
import time
import webbrowser

# ─── Rutas base ───────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, "src")
CORE = os.path.join(ROOT, "core_math")
DASH = os.path.join(ROOT, "dashboard")
EXPO = os.path.join(DASH, "exportaciones")

sys.path.insert(0, SRC)
sys.path.insert(0, CORE)

os.makedirs(EXPO, exist_ok=True)

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
    """Abre un archivo HTML en el navegador si existe."""
    if os.path.exists(ruta):
        webbrowser.open(f"file://{os.path.abspath(ruta)}")
        ok(f"Abierto: {os.path.basename(ruta)}")
    else:
        warn(f"No encontrado: {os.path.basename(ruta)}")


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
    carpetas = [
        SMA_DIR / "2023-2024" / "2023",
        SMA_DIR / "2023-2024" / "2024",
        SMA_DIR / "SMA-EIE-2025-2026",
    ]
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
                                         calcular_correlaciones)
        WL_DIR = os.path.join(ROOT, "datos_crudos", "weatherlink")
        ARCHIVOS_EEP = [
            os.path.join(WL_DIR, "7GT-EEP_1-1-25_12-00_AM_1_Year_1779324867_v2.csv"),
            os.path.join(WL_DIR, "7GT-EEP_1-1-26_12-00_AM_1_Year_1779324876_v2.csv"),
        ]
        ARCHIVOS_UES = [
            os.path.join(WL_DIR, "7GT-UES_1-1-25_12-00_AM_1_Year_1779324630_v2.csv"),
            os.path.join(WL_DIR, "7GT-UES_1-1-26_12-00_AM_1_Year_1779324751_v2.csv"),
        ]
        print("  Cargando EEP...")
        df_eep = concatenar_estacion(ARCHIVOS_EEP)
        print(f"    → {len(df_eep):,} registros EEP")
        print("  Cargando UES...")
        df_ues = concatenar_estacion(ARCHIVOS_UES)
        print(f"    → {len(df_ues):,} registros UES")
        print("  Calculando correlaciones de Pearson inter-estacional (C++)...")
        correlaciones = calcular_correlaciones(df_eep, df_ues)
        print(f"    → {len(correlaciones)} pares de variables")
        salida_msn = os.path.join(DASH, "dashboard_msn_interactivo.html")
        generar_dashboard_msn_interactivo(
            df_eep, df_ues, figs={}, correlaciones=correlaciones,
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

def abrir_dashboards(fusion, solar, msn):
    paso("→", "Abriendo dashboards en el navegador")
    time.sleep(0.5)
    abiertos = 0
    # Abrir en orden de importancia
    for ruta in [fusion, solar, msn]:
        if ruta and os.path.exists(ruta):
            webbrowser.open(f"file://{os.path.abspath(ruta)}")
            ok(f"{os.path.basename(ruta)}")
            abiertos += 1
            time.sleep(1.2)  # evitar que el navegador bloquee múltiples tabs
    if abiertos == 0:
        warn("No se generó ningún dashboard")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    titulo("PROYECTO PROGRAMACIÓN NUMÉRICA — ANÁLISIS CLIMÁTICO/FOTOVOLTAICO")
    print(f"  Directorio: {ROOT}")
    print(f"  Python:     {sys.version.split()[0]}")
    t0 = time.time()

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

    # Abrir navegador
    abrir_dashboards(salida_fusion, salida_solar, salida_msn)

    print(f"\n{'═'*62}\n")


if __name__ == "__main__":
    main()
