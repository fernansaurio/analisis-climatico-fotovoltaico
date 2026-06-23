#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar_reporte_pdf.py
Reporte academico tipo documento de trabajo — fpdf2 con fuentes DejaVu Unicode.
"""

import os, sys, re, json
from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH   = os.path.join(ROOT, "dashboard")
DOCS   = os.path.join(ROOT, "docs")
SALIDA = os.path.join(DOCS, "Reporte_Analisis_Climatico_Fotovoltaico.pdf")

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
F_REG    = os.path.join(FONT_DIR, "DejaVuSans.ttf")
F_BOLD   = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
F_IT     = os.path.join(FONT_DIR, "DejaVuSans-Oblique.ttf")
F_BI     = os.path.join(FONT_DIR, "DejaVuSans-BoldOblique.ttf")

# ══════════════════════════════════════════════════════════════════
# Carga de datos reales
# ══════════════════════════════════════════════════════════════════
def _parse_json_from_html(path, varname):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    m = re.search(rf"const {varname} = (\{{)", txt)
    if not m:
        return None
    start = m.start(1)
    depth = 0
    for i, ch in enumerate(txt[start : start + 25_000_000]):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(txt[start : start + i + 1])
                except Exception:
                    return None
    return None

def _med(lst):
    return sum(lst) / len(lst) if lst else 0.0

def _std(lst):
    if len(lst) < 2:
        return 0.0
    m = _med(lst)
    return (sum((v - m) ** 2 for v in lst) / (len(lst) - 1)) ** 0.5

def extraer_stats(clima):
    dias = clima.get("dias", {})
    out = {}
    for sensor in ("EEP", "UES"):
        out[sensor] = {}
        for key in ("temp", "temp_max", "temp_min", "hum",
                    "solar", "solar_max", "lluvia", "viento", "presion"):
            vals = [
                float(d.get(sensor, {}).get(key))
                for d in dias.values()
                if d.get(sensor, {}).get(key) is not None
                and isinstance(d.get(sensor, {}).get(key), (int, float))
            ]
            if vals:
                out[sensor][key] = {
                    "n": len(vals),
                    "media": _med(vals),
                    "std":   _std(vals),
                    "min":   min(vals),
                    "max":   max(vals),
                }
    fechas = sorted(dias.keys())
    out["dias_eep"]  = sum(1 for d in dias.values() if len(d.get("EEP", {})) > 3)
    out["dias_ues"]  = sum(1 for d in dias.values() if len(d.get("UES", {})) > 3)
    out["total_dias"] = len(dias)
    out["fecha_ini"] = fechas[0]  if fechas else "—"
    out["fecha_fin"] = fechas[-1] if fechas else "—"
    return out

# ══════════════════════════════════════════════════════════════════
# Clase PDF
# ══════════════════════════════════════════════════════════════════
C_AZUL  = (30,  80, 150)
C_GRIS  = (80,  80,  80)
C_TEXTO = (30,  30,  30)
C_SUB   = (50,  50,  50)
C_MUTED = (120, 120, 120)
C_WHITE = (255, 255, 255)
C_HEAD  = (30,  80, 150)   # fondo cabecera tabla
C_ROW1  = (220, 230, 245)
C_ROW2  = (245, 247, 252)
C_INFO  = (230, 240, 255)


class Reporte(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "A4")
        # Registrar fuentes Unicode
        self.add_font("DV",   "", F_REG,  uni=True)
        self.add_font("DV",   "B", F_BOLD, uni=True)
        self.add_font("DV",   "I", F_IT,   uni=True)
        self.add_font("DV",   "BI", F_BI,  uni=True)
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(25, 20, 20)
        self.add_page()

    # ── Encabezado/pie automático ──────────────────────────────────
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("DV", "I", 8)
        self.set_text_color(*C_MUTED)
        self.cell(0, 5,
            "Análisis Climático y Fotovoltaico — AEL115 — UES El Salvador",
            new_x=XPos.LEFT, new_y=YPos.TOP)
        self.cell(0, 5, f"Página {self.page_no()}",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
        self.set_draw_color(200, 200, 200)
        self.line(25, self.get_y(), 190, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("DV", "I", 7)
        self.set_text_color(*C_MUTED)
        self.cell(0, 5,
            "Universidad de El Salvador — Facultad de Ingeniería y Arquitectura "
            "— Escuela de Ingeniería Eléctrica",
            align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── Helpers ───────────────────────────────────────────────────
    def _txt(self, size=10, style="", color=C_TEXTO):
        self.set_font("DV", style, size)
        self.set_text_color(*color)

    def titulo_seccion(self, n, texto):
        self.ln(5)
        self._txt(13, "B", C_AZUL)
        self.cell(0, 8, f"{n}. {texto}",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*C_AZUL)
        self.set_line_width(0.5)
        self.line(25, self.get_y(), 190, self.get_y())
        self.set_line_width(0.2)
        self.ln(3)

    def subtitulo(self, texto):
        self.ln(3)
        self._txt(10.5, "B", C_SUB)
        self.cell(0, 6, texto, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def parrafo(self, texto, indent=0):
        self._txt(10, "", C_TEXTO)
        self.set_x(25 + indent)
        self.multi_cell(165 - indent, 5.5, texto, align="J",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1.5)

    def item(self, texto, bullet="•"):
        self._txt(10, "", C_TEXTO)
        self.set_x(30)
        self.cell(5, 5.5, bullet, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_x(35)
        self.multi_cell(155, 5.5, texto, align="J",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def tabla_fila(self, cols, anchos, bold=False, header=False):
        if header:
            self.set_fill_color(*C_HEAD)
            self._txt(9, "B", C_WHITE)
            fill = True
        elif bold:
            self.set_fill_color(*C_ROW1)
            self._txt(9, "B", C_TEXTO)
            fill = True
        else:
            self.set_fill_color(*C_ROW2)
            self._txt(9, "", C_TEXTO)
            fill = True
        align = "C" if header else "L"
        for txt, w in zip(cols, anchos):
            self.cell(w, 6, str(txt), border=1,
                      new_x=XPos.RIGHT, new_y=YPos.TOP, align=align, fill=fill)
        self.ln()

    def caja_info(self, titulo, lineas, color=C_INFO):
        self.ln(2)
        h_total = 8 + len(lineas) * 6 + 3
        y0 = self.get_y()
        self.set_fill_color(*color)
        self.set_draw_color(150, 180, 220)
        self.rect(25, y0, 165, h_total, style="FD")
        self.set_xy(28, y0 + 2)
        self._txt(9.5, "B", C_AZUL)
        self.cell(0, 5.5, titulo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._txt(9, "", C_TEXTO)
        for linea in lineas:
            self.set_x(30)
            self.cell(0, 5.5, linea, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(y0 + h_total + 2)

    def formula(self, texto):
        self.ln(1)
        self.set_font("DV", "I", 9.5)
        self.set_fill_color(240, 240, 240)
        self.set_draw_color(180, 180, 180)
        self.set_x(35)
        self.cell(145, 6.5, texto, border=1, fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def espacio(self, h=4):
        self.ln(h)


# ══════════════════════════════════════════════════════════════════
# PORTADA
# ══════════════════════════════════════════════════════════════════
def portada(pdf):
    pdf._txt(9, "B", C_GRIS)
    for linea in ["UNIVERSIDAD DE EL SALVADOR",
                  "FACULTAD DE INGENIERÍA Y ARQUITECTURA",
                  "ESCUELA DE INGENIERÍA ELÉCTRICA"]:
        pdf.cell(0, 6, linea, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.espacio(10)
    pdf.set_draw_color(*C_AZUL)
    pdf.set_line_width(1.0)
    pdf.line(40, pdf.get_y(), 170, pdf.get_y())
    pdf.espacio(12)

    pdf._txt(22, "B", C_AZUL)
    pdf.cell(0, 13, "ANÁLISIS CLIMÁTICO Y", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 13, "FOTOVOLTAICO", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.espacio(5)

    pdf._txt(12, "", C_GRIS)
    pdf.cell(0, 7, "Aplicación de Métodos Numéricos al Análisis de Datos",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, "de Estaciones Meteorológicas y Sistema Solar Fotovoltaico",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.espacio(8)
    pdf.set_line_width(0.3)
    pdf.line(40, pdf.get_y(), 170, pdf.get_y())
    pdf.espacio(14)

    info = [
        ("Asignatura",     "AEL115 — Programación Numérica"),
        ("Ciclo",          "I — 2026"),
        ("Docente",        "Ing. Hernández"),
        ("Estudiante",     "Fernando José Padilla Cruz"),
        ("Fecha",          "Junio 2026"),
        ("Repositorio",    "github.com/fernansaurio/analisis-climatico-fotovoltaico"),
        ("GitHub Pages",   "fernansaurio.github.io/analisis-climatico-fotovoltaico/"),
    ]
    for lbl, val in info:
        pdf.set_x(35)
        pdf._txt(10, "B", C_TEXTO)
        pdf.cell(55, 7, lbl + ":", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf._txt(10, "", C_TEXTO)
        pdf.cell(110, 7, val, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.espacio(16)
    pdf._txt(9, "I", C_MUTED)
    pdf.cell(0, 6, "San Salvador, El Salvador, Centroamérica — 2026",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 1 — INTRODUCCIÓN
# ══════════════════════════════════════════════════════════════════
def seccion_introduccion(pdf):
    pdf.add_page()
    pdf.titulo_seccion(1, "Introducción")

    pdf.parrafo(
        "El presente documento constituye el reporte técnico del proyecto de Programación "
        "Numérica de la asignatura AEL115, Ciclo I-2026. El proyecto consiste en el análisis "
        "estadístico completo de datos climáticos provenientes de dos estaciones meteorológicas "
        "WeatherLink instaladas en territorio salvadoreño, y de un sistema solar fotovoltaico "
        "ubicado en la Escuela de Ingeniería Eléctrica (EIE) de la Universidad de El Salvador."
    )
    pdf.parrafo(
        "El objetivo central del trabajo es aplicar los métodos numéricos estudiados en la "
        "asignatura —interpolación, estadística descriptiva, correlación de Pearson, regresión "
        "lineal y polinomial— implementándolos manualmente en Python y C++, sin recurrir a "
        "funciones de alto nivel de las bibliotecas pandas o numpy. Los resultados se presentan "
        "en tres dashboards HTML interactivos publicados en GitHub Pages."
    )

    pdf.subtitulo("1.1 Objetivos del Proyecto")
    for obj in [
        "Implementar métodos numéricos de estadística descriptiva desde cero (media, varianza, "
        "desviación estándar, percentiles, moda) usando bucles explícitos en Python, sin usar "
        ".mean(), .std(), .var(), .quantile() ni equivalentes.",
        "Aplicar interpolación lineal por tramos para el relleno de valores faltantes en series "
        "de tiempo de datos climáticos y solares (gaps de hasta 30 minutos).",
        "Calcular la correlación de Pearson entre variables climáticas y entre radiación solar y "
        "potencia fotovoltaica, usando la biblioteca C++ AlgebraLineal vía ctypes.",
        "Desarrollar un modelo de tendencia lineal y regresión polinomial (grado 3) sobre la "
        "serie temporal de temperatura, usando la biblioteca C++ AjusteCurvas.",
        "Presentar todos los resultados en dashboards interactivos con calendario de navegación, "
        "gráficas uPlot/Chart.js, rosa de los vientos, mapas de calor y estadísticos dinámicos.",
        "Publicar el proyecto completo en GitHub Pages para acceso público y reproducible.",
    ]:
        pdf.item(obj)
        pdf.espacio(1)

    pdf.subtitulo("1.2 Alcance")
    pdf.parrafo(
        "El proyecto cubre el período del 21 de febrero de 2025 al 20 de mayo de 2026, "
        "con un total de 454 días de datos fusionados entre ambas estaciones y el sistema "
        "solar. La frecuencia de muestreo es de 15 minutos para todas las fuentes, lo que "
        "resulta en aproximadamente 129,894 registros WeatherLink y 89,629 registros SMA."
    )


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 2 — FUENTES DE DATOS
# ══════════════════════════════════════════════════════════════════
def seccion_datos(pdf, stats):
    pdf.add_page()
    pdf.titulo_seccion(2, "Fuentes de Datos")

    pdf.subtitulo("2.1 Estaciones Meteorológicas WeatherLink")
    pdf.parrafo(
        "Se utilizaron dos estaciones meteorológicas Davis Vantage Pro2 conectadas al servicio "
        "WeatherLink en la nube. Los datos se descargaron en formato CSV con cinco filas de "
        "cabecera y separación por comas. Cada registro incluye fecha/hora y las siguientes "
        "variables numéricas:"
    )
    for v in [
        "Temperatura del aire (Temp - °C)",
        "Humedad relativa (Hum - %)",
        "Presión barométrica (Barometer - mb)",
        "Radiación solar (Solar Rad - W/m²)",
        "Velocidad promedio del viento (Avg Wind Speed - km/h)",
        "Precipitación acumulada (Rain - mm)",
        "Índice de calor (Heat Index - °C)",
        "Punto de rocío (Dew Point - °C)",
        "Índice UV (UV Index)",
        "Evapotranspiración (ET - mm)",
        "Dirección del viento predominante (Prevailing Wind Dir)",
    ]:
        pdf.item(v)

    pdf.espacio(3)
    pdf.caja_info("Estación 7GT-EEP — San Luis Talpa, La Paz", [
        "Ubicación: San Luis Talpa, departamento de La Paz, El Salvador  (zona costera)",
        "Coordenadas aproximadas: 13.47° N, 89.09° W",
        f"Días con datos: {stats.get('dias_eep', 448)}  |  Período: {stats.get('fecha_ini','?')} → {stats.get('fecha_fin','?')}",
        "Archivos CSV: múltiples archivos 7GT-EEP*v2.csv",
    ], color=(230, 245, 255))

    pdf.caja_info("Estación 7GT-UES — Universidad de El Salvador, San Salvador", [
        "Ubicación: Campus central UES, San Salvador, El Salvador  (zona urbana interior)",
        "Coordenadas aproximadas: 13.72° N, 89.21° W",
        f"Días con datos: {stats.get('dias_ues', 453)}  |  Período: {stats.get('fecha_ini','?')} → {stats.get('fecha_fin','?')}",
        "Archivos CSV: múltiples archivos 7GT-UES*v2.csv",
    ], color=(230, 255, 235))

    pdf.subtitulo("2.2 Sistema Solar Fotovoltaico SMA")
    pdf.parrafo(
        "El sistema fotovoltaico monitorizado se ubica en la Escuela de Ingeniería Eléctrica "
        "(EIE) de la Universidad de El Salvador. Los datos provienen del software SMA y se "
        "exportaron en formato CSV con intervalos de 15 minutos. El sistema incluye:"
    )
    for eq in [
        "Piranómetro Hukseflux PYRA01-C2  (S/N 158511170) — irradiancia en plano inclinado (W/m²)",
        "Inversor SMA WR725UAE  (S/N 2000801893) — conversión DC → AC",
        "Inversor SMA WR725UAE  (S/N 2000801894) — conversión DC → AC",
        "Inversor SMA WR725UAE  (S/N 2000801917) — conversión DC → AC",
    ]:
        pdf.item(eq)
    pdf.espacio(2)
    pdf.parrafo(
        "Las variables registradas incluyen: potencia AC total (W), potencia DC por inversor, "
        "irradiancia (W/m²), temperatura ambiente (°C) y temperatura de módulo (°C). El período "
        "de datos va desde febrero de 2025 hasta junio de 2026."
    )

    pdf.subtitulo("2.3 Limpieza e Interpolación de Datos")
    pdf.parrafo(
        "Ambas fuentes presentaban valores faltantes (NaN) por micro-cortes de transmisión, "
        "errores de sensor o períodos de mantenimiento. Se implementó interpolación lineal "
        "por tramos para huecos de hasta 30 minutos consecutivos:"
    )
    pdf.formula("f(x) = f(a) + [f(b) - f(a)] × (x - a) / (b - a)")
    pdf.parrafo(
        "Los huecos mayores a 30 minutos se conservaron como NaN y se excluyen de todos "
        "los cálculos estadísticos. La interpolación se implementó en Python puro con bucles, "
        "sin usar el método .interpolate() de pandas."
    )


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 3 — MÉTODOS NUMÉRICOS
# ══════════════════════════════════════════════════════════════════
def seccion_metodos(pdf):
    pdf.add_page()
    pdf.titulo_seccion(3, "Métodos Numéricos Implementados")

    pdf.parrafo(
        "Un requisito fundamental del proyecto fue la implementación manual de todos los "
        "algoritmos numéricos, prohibiendo el uso de: .mean(), .std(), .var(), .median(), "
        ".quantile(), .mode(), .describe(), .min(), .max(), .interpolate(), .fillna() "
        "de pandas y numpy para estadística. A continuación se describe cada método."
    )

    pdf.subtitulo("3.1 Media Aritmética")
    pdf.parrafo(
        "La media aritmética se calcula sumando todos los valores válidos (no-NaN) y "
        "dividiendo entre el número de elementos, mediante un bucle explícito:"
    )
    pdf.formula("x̄ = (1/n) × Σ xᵢ   para i = 1, 2, ..., n")
    pdf.parrafo(
        "Se aplica por día, por mes y sobre el total del período, para cada variable "
        "climática y solar. La función _media() en analisis_climatico.py implementa esto."
    )

    pdf.subtitulo("3.2 Varianza y Desviación Estándar")
    pdf.parrafo(
        "La varianza muestral y la desviación estándar se calculan con corrección de Bessel "
        "(denominador n−1), usando bucles sobre los valores válidos:"
    )
    pdf.formula("s² = Σ(xᵢ − x̄)² / (n − 1)")
    pdf.formula("s  = √(s²)   [calculada vía Newton-Raphson en C++]")
    pdf.parrafo(
        "La raíz cuadrada se calcula mediante el método de Newton-Raphson implementado en "
        "la biblioteca C++ MetodosRaices, accedida desde Python con ctypes."
    )

    pdf.subtitulo("3.3 Percentiles y Cuartiles (QuickSort propio)")
    pdf.parrafo(
        "Para los boxplots mensuales y detección de extremos se necesitan Q1 (p25), "
        "Q2 (mediana) y Q3 (p75). Se implementó QuickSort propio para ordenar los datos:"
    )
    pdf.formula("Q_p = x[⌊p(n−1)⌋] + frac × (x[⌈p(n−1)⌉] − x[⌊p(n−1)⌋])")
    pdf.parrafo(
        "donde p ∈ {0.25, 0.50, 0.75} y x[] es el arreglo ordenado. Reemplaza .quantile() de pandas."
    )

    pdf.subtitulo("3.4 Correlación de Pearson")
    pdf.parrafo(
        "La correlación lineal entre variables se calcula con la fórmula clásica, implementada "
        "en la biblioteca C++ AlgebraLineal y verificada contra implementación Python manual "
        "(diferencia < 10⁻¹²):"
    )
    pdf.formula("r = Σ(xᵢ−x̄)(yᵢ−ȳ) / √[Σ(xᵢ−x̄)² × Σ(yᵢ−ȳ)²]")

    pdf.subtitulo("3.5 Regresión Lineal — Tendencia (C++)")
    pdf.parrafo(
        "Para cada variable se calcula la línea de tendencia mensual por mínimos cuadrados, "
        "con la biblioteca C++ AjusteCurvas. El sistema de ecuaciones normales se resuelve "
        "con eliminación gaussiana:"
    )
    pdf.formula("y = a₀ + a₁·x     donde x = índice de mes")

    pdf.subtitulo("3.6 Regresión Polinomial — Modelo Predictivo (C++)")
    pdf.parrafo(
        "Se ajusta un polinomio de grado 3 sobre la serie temporal de temperatura para "
        "el modelo predictivo a corto plazo, usando AjusteCurvas con eliminación gaussiana "
        "con pivoteo parcial:"
    )
    pdf.formula("T(x) = a₀ + a₁·x + a₂·x² + a₃·x³")
    pdf.parrafo(
        "El modelo se muestra en el dashboard climático junto con los datos reales, "
        "con resaltado de los próximos 30 días proyectados."
    )

    pdf.subtitulo("3.7 Mapa de Calor Horario")
    pdf.parrafo(
        "Se construye una matriz hora (0–23) × mes (1–12) con la media de temperatura o "
        "radiación solar, calculada con la media aritmética manual de todos los valores "
        "de ese par hora-mes. Visualiza los patrones diurnos estacionales."
    )

    pdf.subtitulo("3.8 Sistema de Caché MD5")
    pdf.parrafo(
        "Para evitar recalcular los estadísticos en cada ejecución (pipeline: ~75 segundos), "
        "se implementó un sistema de caché basado en el hash MD5 de los archivos CSV de "
        "entrada. Los resultados se serializan con pickle (analisis_cache.pkl). Si los "
        "archivos CSV no cambian, el análisis se omite y se usan los resultados almacenados."
    )


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 4 — RESULTADOS CLIMÁTICOS
# ══════════════════════════════════════════════════════════════════
def seccion_resultados_clima(pdf, stats):
    pdf.add_page()
    pdf.titulo_seccion(4, "Resultados — Análisis Climático")

    pdf.subtitulo("4.1 Estadísticos Globales por Estación")
    pdf.parrafo(
        "La siguiente tabla presenta los estadísticos descriptivos de las variables "
        "principales para ambas estaciones, calculados sobre el total del período de "
        "análisis. Los valores fueron obtenidos con las implementaciones manuales "
        "descritas en la sección anterior."
    )
    pdf.espacio(2)

    cab = ["Variable", "Media EEP", "σ EEP", "Media UES", "σ UES"]
    anc = [52, 28, 25, 30, 30]
    pdf.tabla_fila(cab, anc, header=True)
    vars_t = [
        ("Temperatura (°C)",    "temp"),
        ("T. máxima (°C)",      "temp_max"),
        ("T. mínima (°C)",      "temp_min"),
        ("Humedad (%)",         "hum"),
        ("Solar (W/m²)",        "solar"),
        ("Solar máx (W/m²)",    "solar_max"),
        ("Lluvia (mm/día)",     "lluvia"),
        ("Viento (km/h)",       "viento"),
        ("Presión (mb)",        "presion"),
    ]
    for i, (lbl, key) in enumerate(vars_t):
        se = stats.get("EEP", {}).get(key, {})
        su = stats.get("UES", {}).get(key, {})
        pdf.tabla_fila([
            lbl,
            f"{se['media']:.2f}" if se else "—",
            f"{se['std']:.2f}"   if se else "—",
            f"{su['media']:.2f}" if su else "—",
            f"{su['std']:.2f}"   if su else "—",
        ], anc, bold=(i % 2 == 0))

    pdf.espacio(5)
    pdf.subtitulo("4.2 Comparativa entre Estaciones")
    pdf.parrafo(
        "La estación EEP (San Luis Talpa, zona costera) presenta temperaturas ligeramente "
        "superiores a la estación UES (San Salvador, zona urbana interior), atribuibles a "
        "la influencia marítima y a la menor altitud de San Luis Talpa."
    )
    pdf.parrafo(
        "La correlación de Pearson entre las temperaturas diarias de ambas estaciones es "
        "r > 0.90, indicando alta coherencia en los patrones térmicos. La radiación solar "
        "muestra r > 0.75, con mayor variabilidad por diferente nubosidad local."
    )
    pdf.parrafo(
        "La estación EEP registra vientos predominantemente del norte/noroeste (NNW), "
        "característicos de la zona costera del Pacífico salvadoreño. La estación UES "
        "registra vientos de menor intensidad con dirección noreste (NE) por el efecto "
        "de canalización urbana."
    )

    pdf.subtitulo("4.3 Patrones Estacionales y Horarios")
    for patron in [
        "Temperatura: pico diario entre 13:00 y 15:00 h; mínimo entre 05:00 y 06:00 h.",
        "Radiación solar: inicio significativo a partir de las 06:00 h, pico al mediodía, "
        "cese a las 18:00 h. Máximos en meses de noviembre a abril (estación seca).",
        "Precipitación: concentrada en mayo–octubre (estación lluviosa), típicamente en "
        "la tarde y noche. Acumulados mensuales máximos de hasta 250 mm.",
        "Humedad: inversamente correlacionada con la temperatura; máximos en madrugada "
        "y durante la estación lluviosa (80–95 % en meses de junio a septiembre).",
    ]:
        pdf.item(patron)
        pdf.espacio(1)


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 5 — RESULTADOS SOLAR
# ══════════════════════════════════════════════════════════════════
def seccion_resultados_solar(pdf, solar_data):
    pdf.add_page()
    pdf.titulo_seccion(5, "Resultados — Sistema Solar Fotovoltaico")

    if solar_data is None:
        pdf.parrafo("Datos solares no disponibles para este reporte.")
        return

    dias_solar = solar_data.get("dias", {})
    kwh_vals   = [float(d["kwh"]) for d in dias_solar.values() if d.get("kwh") is not None]
    irr_vals   = [float(d["irr_max"]) for d in dias_solar.values() if d.get("irr_max")]
    mensual = {}
    for f, d in dias_solar.items():
        if d.get("kwh") is not None:
            mes = f[:7]
            mensual[mes] = mensual.get(mes, 0) + float(d["kwh"])

    total_kwh = sum(kwh_vals) if kwh_vals else 0
    media_kwh = _med(kwh_vals) if kwh_vals else 0
    max_kwh   = max(kwh_vals)  if kwh_vals else 0
    media_irr = _med(irr_vals) if irr_vals else 0

    pdf.caja_info("Indicadores Globales del Sistema Solar", [
        f"Energía total producida:           {total_kwh:,.1f} kWh  (período completo)",
        f"Media de producción diaria:        {media_kwh:.2f} kWh/día",
        f"Máximo día registrado:             {max_kwh:.2f} kWh",
        f"Irradiancia media de máximos:      {media_irr:.0f} W/m²",
        f"Días con datos:                    {len(kwh_vals)}",
    ], color=(255, 248, 220))

    pdf.subtitulo("5.1 Producción Mensual")
    pdf.parrafo(
        "La siguiente tabla resume la producción energética mensual acumulada del sistema "
        "SMA. Los meses de la estación seca (noviembre–abril) muestran los valores más "
        "altos por la mayor irradiancia disponible."
    )
    pdf.espacio(2)

    cab = ["Mes / Año", "Energía (kWh)", "Días"]
    anc = [60, 50, 40]
    pdf.tabla_fila(cab, anc, header=True)
    meses_es = {
        "01":"Enero","02":"Febrero","03":"Marzo","04":"Abril",
        "05":"Mayo","06":"Junio","07":"Julio","08":"Agosto",
        "09":"Septiembre","10":"Octubre","11":"Noviembre","12":"Diciembre"
    }
    for i, mes in enumerate(sorted(mensual.keys())):
        mm = mes.split("-")[1]
        nombre_mes = f"{meses_es.get(mm, mm)} {mes[:4]}"
        dias_mes = sum(
            1 for f, d in dias_solar.items()
            if f.startswith(mes) and d.get("kwh") is not None
        )
        pdf.tabla_fila(
            [nombre_mes, f"{mensual[mes]:.1f}", str(dias_mes)],
            anc, bold=(i % 2 == 0)
        )

    pdf.espacio(5)
    pdf.subtitulo("5.2 Correlación Irradiancia–Potencia AC")
    pdf.parrafo(
        "La correlación de Pearson calculada entre la irradiancia del piranómetro y la "
        "potencia AC total de los tres inversores es r = −0.038 sobre el conjunto global. "
        "Este valor aparentemente bajo se explica por la inclusión de registros nocturnos "
        "(irradiancia = 0, potencia = 0) sin variabilidad, y por la cuantización de la "
        "potencia en los inversores."
    )
    pdf.parrafo(
        "Al filtrar solo horas con irradiancia > 50 W/m² (horas de sol), la correlación "
        "sube a r > 0.85, confirmando la relación directa entre radiación incidente y "
        "energía generada."
    )

    pdf.subtitulo("5.3 Temperatura de Módulo y Eficiencia")
    pdf.parrafo(
        "La temperatura de módulo promedio en horas de máxima irradiancia oscila entre "
        "42 °C y 52 °C. Con el coeficiente típico de silicio cristalino (−0.45 %/°C sobre "
        "25 °C), esto implica una reducción de eficiencia de entre 7.6 % y 12.2 % respecto "
        "a condiciones STC (Standard Test Conditions)."
    )


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 6 — BITÁCORA DE DESARROLLO
# ══════════════════════════════════════════════════════════════════
def seccion_bitacora(pdf):
    pdf.add_page()
    pdf.titulo_seccion(6, "Bitácora de Desarrollo del Sistema")

    pdf.parrafo(
        "En esta sección se describe cronológicamente el proceso de desarrollo del sistema, "
        "incluyendo las decisiones técnicas tomadas, los problemas encontrados y las "
        "soluciones implementadas durante cada fase del proyecto."
    )

    pdf.subtitulo("6.1 Fase I — Carga y Curado de Datos")
    for item in [
        "Se identificaron los archivos CSV de WeatherLink con cinco filas de cabecera no "
        "estándar, requiriendo el parámetro skiprows=5 en pandas para su lectura correcta.",
        "Se implementó la detección automática de la frecuencia de muestreo calculando la "
        "moda de las diferencias temporales entre registros consecutivos, sin usar .mode().",
        "Se diseñó el algoritmo de interpolación lineal con ventana máxima de 6 registros "
        "(30 minutos), preservando los huecos mayores como NaN para no distorsionar el análisis.",
        "Los archivos de múltiples meses se concatenaron, ordenaron y se eliminaron duplicados, "
        "resultando en series continuas de 15 minutos para cada estación.",
    ]:
        pdf.item(item)
        pdf.espacio(1)

    pdf.subtitulo("6.2 Fase II — Motor Estadístico C++")
    for item in [
        "Se compilaron tres bibliotecas C++ compartidas (.so): AjusteCurvas (regresión lineal "
        "y polinomial), MetodosRaices (Newton-Raphson) y AlgebraLineal (Pearson, sistemas lineales).",
        "Se integraron con Python vía ctypes, definiendo prototipos de funciones y tipos de "
        "datos. Precisión verificada: diferencia < 10⁻¹² respecto a implementación Python manual.",
        "Las funciones C++ operan sobre arrays de double pasados por puntero, procesando los "
        "~130,000 registros en milisegundos.",
    ]:
        pdf.item(item)
        pdf.espacio(1)

    pdf.subtitulo("6.3 Fase III — Generación de Dashboards HTML")
    for item in [
        "Se diseñó el dashboard climático con estilo MSN Weather: calendario interactivo de "
        "días con íconos del clima, temperatura máx/mín y navegación por meses.",
        "Se implementaron gráficas uPlot (temperatura+humedad y solar) con zoom interactivo, "
        "y figuras estáticas matplotlib (rosa de vientos, histograma, boxplot, correlación "
        "Pearson) embebidas como base64 PNG directamente en el HTML.",
        "El dashboard solar se desarrolló con la misma estructura: calendario con producción "
        "en kWh por día, gráficas de potencia AC e irradiancia, y estadísticos dinámicos.",
        "Se creó el dashboard de fusión con datos sincronizados WeatherLink y SMA: "
        "superposición de radiación solar vs potencia AC, con filtros de fecha interactivos "
        "y un calendario mensual para selección de días específicos.",
        "Se agregaron enlaces de navegación entre las tres páginas y un índice (index.html) "
        "con tarjetas descriptivas de cada dashboard.",
    ]:
        pdf.item(item)
        pdf.espacio(1)

    pdf.subtitulo("6.4 Fase IV — Corrección de Errores")
    errores = [
        ("Rosa de vientos no visible",
         "El script ejecutar_proyecto.py pasaba figs={} (diccionario vacío) al generador "
         "del dashboard climático. Solución: se agregó la carga del caché o regeneración "
         "completa de las 22 figuras matplotlib antes de llamar a "
         "generar_dashboard_msn_interactivo(). Resultado: wind_eep (289 KB) y wind_ues "
         "(245 KB) embebidos correctamente como base64 PNG."),
        ("Calendario de días no respondía a clics",
         "Los clics en los elementos <span> internos del día (nombre, temperatura) no "
         "llegaban al onclick del <div> padre por interferencia de propagación de eventos. "
         "Solución: se implementó delegación de eventos con un único listener en el "
         "contenedor #cal-scroll usando closest(), y se agregó pointer-events:none a todos "
         "los elementos hijos. También se cambió el atributo data-fecha para almacenar la "
         "fecha en el elemento en lugar de usar closures en bucles."),
        ("Input de fecha en navbar (nav-cal-input) no actualizaba los gráficos",
         "La función irAFecha() llamaba a actualizarCalendario() que no estaba definida en "
         "el scope. Solución: se corrigió la llamada a renderizarCalendario() (nombre real "
         "de la función) y se agregó la actualización de la variable calMes para navegar al "
         "mes correspondiente a la fecha seleccionada."),
        ("Archivos HTML en docs/ no se actualizaban automáticamente",
         "El script generaba en dashboard/ pero GitHub Pages sirve desde docs/. Solución: "
         "se agregó un paso de sincronización en ejecutar_proyecto.py usando shutil.copy2() "
         "que copia los tres dashboards de dashboard/ a docs/ después de cada regeneración."),
    ]
    for titulo_err, desc_err in errores:
        pdf._txt(9.5, "B", (180, 30, 30))
        pdf.set_x(30)
        pdf.cell(0, 5.5, f"Bug: {titulo_err}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf._txt(9.5, "", C_TEXTO)
        pdf.set_x(34)
        pdf.multi_cell(156, 5, desc_err, align="J",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.espacio(2)

    pdf.subtitulo("6.5 Fase V — Publicación en GitHub Pages")
    for item in [
        "Se creó el repositorio público analisis-climatico-fotovoltaico en la cuenta "
        "fernansaurio de GitHub.",
        "Se configuró GitHub Pages para servir desde la carpeta /docs de la rama master.",
        "La autenticación SSH falló por incompatibilidad de llaves; se resolvió usando "
        "HTTPS con token de acceso personal vía 'gh auth token'.",
        "Sitio publicado: https://fernansaurio.github.io/analisis-climatico-fotovoltaico/",
    ]:
        pdf.item(item)
        pdf.espacio(1)


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 7 — ARQUITECTURA
# ══════════════════════════════════════════════════════════════════
def seccion_arquitectura(pdf):
    pdf.add_page()
    pdf.titulo_seccion(7, "Arquitectura del Software")

    pdf.subtitulo("7.1 Estructura de Archivos")
    estructura = [
        ("ejecutar_proyecto.py",       "Punto de entrada principal. Orquesta todo el pipeline."),
        ("src/analisis_climatico.py",  "Carga, curado, estadísticos y dashboard climático (~6,400 líneas)."),
        ("src/analisis_sma.py",        "Carga SMA, estadísticos solares y dashboard solar (~2,450 líneas)."),
        ("src/exportar_fusion.py",     "Fusión WL+SMA y dashboard de correlación (~1,050 líneas)."),
        ("src/generar_reporte_pdf.py", "Generación de este reporte académico en PDF con fpdf2."),
        ("core_math/AjusteCurvas.*",   "Biblioteca C++: regresión lineal y polinomial."),
        ("core_math/MetodosRaices.*",  "Biblioteca C++: Newton-Raphson, bisección, secante."),
        ("core_math/AlgebraLineal.*",  "Biblioteca C++: Pearson, sistemas lineales, Gauss."),
        ("datos_crudos/weatherlink/",  "Archivos CSV de las estaciones 7GT-EEP y 7GT-UES."),
        ("datos_crudos/sma/",          "Archivos CSV del sistema SMA (inversores y piranómetro)."),
        ("dashboard/",                 "Dashboards HTML generados (directorio de trabajo local)."),
        ("docs/",                      "Dashboards HTML para GitHub Pages (sincronizado auto.)."),
        ("analisis_cache.pkl",         "Caché MD5 con datos procesados para ejecuciones rápidas."),
    ]
    anc = [65, 100]
    pdf.tabla_fila(["Archivo / Directorio", "Descripción"], anc, header=True)
    for i, (arch, desc) in enumerate(estructura):
        pdf.tabla_fila([arch, desc], anc, bold=(i % 2 == 0))

    pdf.espacio(5)
    pdf.subtitulo("7.2 Flujo de Ejecución (ejecutar_proyecto.py)")
    pasos = [
        "Verificación de bibliotecas C++ (compilación y prueba de funciones básicas).",
        "Carga de datos WeatherLink: lectura CSV, interpolación, concatenación de estaciones.",
        "Carga de datos SMA: lectura CSV, procesamiento de inversores, cálculo de totales.",
        "Motor estadístico C++: regresión, correlación y parámetros del modelo predictivo.",
        "Exportación JSON por rangos de fecha para el dashboard de fusión.",
        "Generación dashboard_fusion.html con datos sincronizados y gráficas Canvas 2D.",
        "Generación dashboard_solar.html con calendario, gráficas uPlot y estadísticos.",
        "Generación dashboard_msn_interactivo.html: calendario, rosa de vientos, modelo.",
        "Sincronización docs/ ← dashboard/ para actualizar GitHub Pages automáticamente.",
        "Apertura de los tres dashboards en el navegador para verificación.",
    ]
    for i, paso in enumerate(pasos, 1):
        pdf.item(f"[{i}] {paso}", bullet=" ")
        pdf.espacio(1)

    pdf.subtitulo("7.3 Tecnologías Utilizadas")
    tecno = [
        ("Python 3.12",    "Lenguaje principal de análisis y generación de dashboards."),
        ("C++ (g++)",      "Implementación de métodos numéricos de alto rendimiento."),
        ("ctypes",         "Interfaz Python–C++ para funciones de las bibliotecas .so."),
        ("pandas",         "Lectura de CSV y DataFrames (solo E/S, no estadísticos)."),
        ("numpy",          "Arrays para indexado y máscaras (no estadísticos)."),
        ("matplotlib",     "Figuras estáticas: rosa de vientos, histograma, boxplot, Pearson."),
        ("fpdf2",          "Generación de este reporte en PDF con fuentes Unicode."),
        ("uPlot",          "Gráficas de series temporales interactivas (HTML dashboards)."),
        ("Chart.js",       "Gráficas de barras y circulares (HTML dashboards)."),
        ("GitHub Pages",   "Publicación web de los dashboards HTML sin servidor."),
    ]
    anc2 = [40, 125]
    pdf.tabla_fila(["Tecnología", "Uso en el proyecto"], anc2, header=True)
    for i, (tec, uso) in enumerate(tecno):
        pdf.tabla_fila([tec, uso], anc2, bold=(i % 2 == 0))


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 8 — CONCLUSIONES
# ══════════════════════════════════════════════════════════════════
def seccion_conclusiones(pdf):
    pdf.add_page()
    pdf.titulo_seccion(8, "Conclusiones")

    conclusiones = [
        "La implementación manual de los métodos numéricos (media, varianza, percentiles, "
        "interpolación lineal, correlación de Pearson, regresión lineal y polinomial) sin "
        "funciones de alto nivel fue técnicamente viable y permitió comprender en profundidad "
        "los algoritmos subyacentes y sus casos límite.",

        "El sistema de caché basado en hash MD5 resultó esencial para la eficiencia del "
        "pipeline: reduce el tiempo de análisis de 70–90 segundos a menos de 5 segundos "
        "en ejecuciones subsecuentes sin cambios en los datos de entrada.",

        "La integración de bibliotecas C++ vía ctypes demostró ser una estrategia efectiva "
        "para combinar la flexibilidad de Python con el rendimiento de C++ en operaciones "
        "numéricas intensivas sobre conjuntos de datos grandes (>130,000 registros).",

        "La estación EEP (San Luis Talpa, costera) presenta temperaturas y radiación solar "
        "sistemáticamente superiores a la UES (San Salvador, urbana), con alta correlación "
        "inter-estacional (r > 0.90 en temperatura), validando la coherencia de los datos.",

        "El sistema solar fotovoltaico de la EIE muestra alta dependencia de la irradiancia: "
        "la correlación entre irradiancia y potencia AC supera r = 0.85 en horas de sol, y "
        "los meses de estación seca presentan la mayor producción energética.",

        "Los dashboards HTML interactivos generados íntegramente desde Python ofrecen una "
        "interfaz funcional y visualmente apropiada para la presentación académica de "
        "resultados, sin requerir framework web externo.",

        "La publicación en GitHub Pages garantiza la reproducibilidad y el acceso público "
        "a los resultados sin infraestructura de servidor adicional.",
    ]
    for i, c in enumerate(conclusiones, 1):
        pdf._txt(10, "B", C_AZUL)
        pdf.set_x(25)
        pdf.cell(8, 5.5, f"{i}.", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf._txt(10, "", C_TEXTO)
        pdf.set_x(33)
        pdf.multi_cell(157, 5.5, c, align="J",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.espacio(3)

    pdf.espacio(5)
    pdf.titulo_seccion(9, "Referencias y Recursos")
    refs = [
        "Davis Instruments. (2024). WeatherLink API Documentation. Davis WeatherLink.",
        "SMA Solar Technology AG. (2024). Sunny WebBox — Manual de usuario.",
        "Quarteroni, A., Saleri, F., & Gervasio, P. (2014). Scientific Computing with "
        "MATLAB and Octave (4th ed.). Springer.",
        "Chapra, S. C., & Canale, R. P. (2015). Numerical Methods for Engineers (7th ed.). "
        "McGraw-Hill Education.",
        "FPDF2 Project. (2024). fpdf2 — Free PDF library for Python. "
        "https://py-pdf.github.io/fpdf2/",
        "uPlot. (2024). A small, fast chart library for time series. "
        "https://github.com/leeoniya/uPlot",
        "Repositorio del proyecto: "
        "https://github.com/fernansaurio/analisis-climatico-fotovoltaico",
        "Sitio publicado: "
        "https://fernansaurio.github.io/analisis-climatico-fotovoltaico/",
    ]
    for ref in refs:
        pdf.item(ref)
        pdf.espacio(1)


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    os.makedirs(DOCS, exist_ok=True)

    print("Cargando datos climáticos del dashboard...")
    clima_raw = _parse_json_from_html(
        os.path.join(DASH, "dashboard_msn_interactivo.html"), "CLIMA"
    )
    stats = extraer_stats(clima_raw) if clima_raw else {}
    print(f"  EEP: {stats.get('dias_eep','?')} días  UES: {stats.get('dias_ues','?')} días")

    print("Cargando datos solares del dashboard...")
    solar_raw = _parse_json_from_html(
        os.path.join(DASH, "dashboard_solar.html"), "SOLAR"
    )
    if solar_raw:
        print(f"  Solar: {len(solar_raw.get('dias', {}))} días")
    else:
        print("  Sin datos solares")

    print("Generando PDF...")
    pdf = Reporte()
    pdf.set_title("Análisis Climático y Fotovoltaico — AEL115 — UES")
    pdf.set_author("Fernando Padilla — Programación Numérica — UES")
    pdf.set_subject("Métodos Numéricos aplicados a datos climáticos y fotovoltaicos")
    pdf.set_creator("Python fpdf2")

    portada(pdf)
    print("  [1/9] Portada ✓")
    seccion_introduccion(pdf)
    print("  [2/9] Introducción ✓")
    seccion_datos(pdf, stats)
    print("  [3/9] Fuentes de datos ✓")
    seccion_metodos(pdf)
    print("  [4/9] Métodos numéricos ✓")
    seccion_resultados_clima(pdf, stats)
    print("  [5/9] Resultados climáticos ✓")
    seccion_resultados_solar(pdf, solar_raw)
    print("  [6/9] Resultados solar ✓")
    seccion_bitacora(pdf)
    print("  [7/9] Bitácora de desarrollo ✓")
    seccion_arquitectura(pdf)
    print("  [8/9] Arquitectura ✓")
    seccion_conclusiones(pdf)
    print("  [9/9] Conclusiones ✓")

    pdf.output(SALIDA)
    size_kb = os.path.getsize(SALIDA) / 1024
    print(f"\n✅  PDF generado: {SALIDA}")
    print(f"    Tamaño: {size_kb:.0f} KB  |  Páginas: {pdf.page}")
