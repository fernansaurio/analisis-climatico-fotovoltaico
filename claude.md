# claude.md — Registro de Aprendizaje del Proyecto

**Directorio:** `/home/kioryu/Escritorio/Tarea`
**Proyecto:** Programación Numérica y Análisis Climático/Fotovoltaico
**Última actualización:** 2026-06-19

---

## ESTRUCTURA DEL PROYECTO (post-reorganización 2026-06-19)

```
Tarea/
├── datos_crudos/
│   ├── weatherlink/          ← CSVs 7GT-EEP y 7GT-UES (8 archivos)
│   └── sma_solar/            ← 2023-2024/ y SMA-EIE-2025-2026/
├── core_math/                ← .so compilados + wrappers Python + fuentes_cpp/
├── src/                      ← Scripts principales Python
├── dashboard/                ← HTML, JS, CSS
│   └── exportaciones/        ← JSON exportados por mes
├── reportes/                 ← bitacora, README, PDF, apuntes
└── analisis_cache.pkl        ← Caché de resultados (raíz del proyecto)
```

**Paths base en los scripts (`src/`):**
```python
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))   # → src/
_PROJ_ROOT  = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
_WL_DIR     = os.path.join(_PROJ_ROOT, "datos_crudos", "weatherlink")
_DASH_DIR   = os.path.join(_PROJ_ROOT, "dashboard")
_EXPORT_DIR = os.path.join(_DASH_DIR, "exportaciones")
sys.path.insert(0, os.path.join(_PROJ_ROOT, "core_math"))  # wrappers C++
```

---

## RESTRICCIONES ACADÉMICAS (NO VIOLAR)

1. **Estadísticos**: Nunca usar `.mean()`, `.std()`, `.var()`, `.median()`,
   `.min()`, `.max()`, `.quantile()`, `.describe()`, `.interpolate()`,
   `.fillna()` ni equivalentes NumPy/SciPy. Toda estadística va por C++ (.so)
   o implementación manual en Python puro.
2. **Gráficas frontend**: Solo Canvas/uPlot/Chart.js. No matplotlib en output final.
3. **Directorio**: Solo trabajar en `/home/kioryu/Escritorio/Tarea`.

---

## ERRORES CONOCIDOS Y SOLUCIONES

### Error 1: Segmentation Fault con ctypes
**Causa:** Pasar array de Python sin convertir explícitamente a `ctypes.POINTER(ctypes.c_double)`.
**Solución:** Siempre hacer `arr = np.ascontiguousarray(data, dtype=np.float64)` y luego
`arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))` antes de pasar a la función C++.

### Error 2: Parseo de fechas WeatherLink
**Causa:** Las fechas del CSV usan formato `M/D/YY H:MM AM/PM` (ej: `2/25/25 1:00 PM`).
**Solución:** `pd.to_datetime(col, errors="coerce")` maneja este formato automáticamente.
Las primeras 5 filas son metadata de WeatherLink y se saltan con `skiprows=5`.

### Error 3: CSV SMA con separador variable
**Causa:** Algunos archivos SMA usan `;` y otros `,` como separador.
**Solución:** Leer la primera línea para detectar: `sep = ";" if ";" in lineas[0] else ","`.
Las primeras 4 filas son metadata SMA.

### Error 4: `json.dumps()` con NaN
**Causa:** `json.dumps()` no acepta `float('nan')` — lanza ValueError.
**Solución:** Antes de serializar, sustituir NaN por None:
```python
def _jv(v):
    return None if (v != v) else (v.item() if hasattr(v, 'item') else v)
```

### Error 5: Import de wrappers C++ al mover scripts a `/src/`
**Causa:** Los wrappers (`ajuste_curvas.py`, etc.) están en `core_math/`, no en `src/`.
**Solución:** Añadir al inicio de CADA script en `src/`:
```python
sys.path.insert(0, os.path.join(_PROJ_ROOT, "core_math"))
```

### Error 6: f-string con dict comprehension → TypeError: unhashable type: 'dict'
**Causa:** Usar `{dict_comp}` dentro de f-strings en JS embebido.
**Solución:** Pre-computar la serialización JSON fuera del f-string y usar variable:
```python
json_str = json.dumps(mi_dict)
html = f"<script>window.DATA = {json_str};</script>"
```

### Error 8: Detección de separador SMA con `lineas[0].count(";") > 3`
**Causa:** La primera línea del CSV SMA es `"CSV-Export;Version: 1.01;Separator: Semicolon"` que
solo tiene 2 `;`, por lo que `> 3` da False → se detecta `,` incorrectamente.
**Solución:** Detectar desde la línea de cabeceras (índice 4) que tiene muchos campos:
```python
hdr = lineas[4] if len(lineas) > 4 else lineas[0]
sep = ";" if hdr.count(";") > hdr.count(",") else ","
```
Además, las líneas 4 y 5 son columnas y unidades. Los datos empiezan en línea 6 (`lineas[6:]`).

### Error 9: `pd.to_datetime` sin `format` lanza UserWarning en pandas ≥ 2.0
**Causa:** WeatherLink usa formato `M/D/YY H:MM AM/PM` no estándar.
**Solución:** Usar `format="mixed"` para pandas ≥ 2.0:
```python
pd.to_datetime(col, errors="coerce", format="mixed")
```

### Error 7: Caché analisis_cache.pkl con paths relativos
**Causa:** Al mover scripts a `src/`, la caché se buscaba en `src/analisis_cache.pkl`.
**Solución:** Usar path absoluto: `CACHE_CALC_PATH = os.path.join(_PROJ_ROOT, "analisis_cache.pkl")`.

### Error 10: Nombres de métodos incorrectos en los wrappers C++
**Causa:** Los métodos reales difieren de los nombres asumidos.
**Solución verificada:**
```python
# AjusteCurvas — API real:
ac = AjusteCurvas()
datos = np.ascontiguousarray([[v] for v in lista], dtype=np.float64)
ac.establecer_datos(datos)
ac.ordenar_por_columna(0, ascendente=True)
ac.media(0)                       # ← NO calcular_media()
ac.desviacion_estandar_metodo3(0) # ← NO calcular_desviacion()
ac.maximo(0)  / ac.minimo(0)
ac.mediana(0) / ac.percentil(0, 25.0)
ac.pearson_correlation(col_x, col_y)  # ← NO correlacion_pearson()

# MetodosRaices — API real:
mr = MetodosRaices()
val, iters = mr.newton_raphson(f, df, x0, tol=1e-12, max_iter=100)
# Para √x: f=lambda v: v*v-x, df=lambda v: 2*v, x0=x/2.0
# NO existe mr.newton_raphson_sqrt()

# AlgebraLineal — requiere dimensiones:
al = AlgebraLineal(filas=N, cols=M)  # ← NO AlgebraLineal() sin parámetros
```

---

## LECCIONES DE DISEÑO

- **Detección de frecuencia SMA**: Los CSV son de 15 min. Verificarlo calculando
  `delta = (ts[i] - ts[i-1]).total_seconds() / 60` para las primeras 50 filas.
- **Merge WeatherLink + SMA**: Usar `pd.merge_asof` con tolerancia = `freq_min/2` minutos.
  WL puede ser 5 min, SMA 15 min → alinear con tolerancia de 8 min.
- **Interpolación manual**: Solo interpolar gaps ≤ 3 muestras. Gaps mayores → NaN.
  Nunca inventar datos en períodos nocturnos de irradiancia.
- **JSON export para file://**: No usar fetch() para cargar JSON locales (bloqueado por CORS).
  Embeber datos como `window.DATA = {...}` directamente en el HTML.
- **Paths de librerías JS locales**: Chart.js y uPlot están en `dashboard/`, NO en la raíz.
  El HTML generado también va a `dashboard/`, así que usar `chart.umd.min.js` (sin `../`).
  Si se pone `../chart.umd.min.js` se busca en `Tarea/` donde NO existe → gráficas en blanco.

### Error 11: mkChart falla silenciosamente si Chart.js no carga
**Causa:** `Chart.getChart(canvas)` lanza ReferenceError si `Chart` es undefined.
  El error propaga y bloquea todo lo que sigue (stats table, etc.).
**Solución:** Envolver `mkChart` en try-catch con `_mostrarErrorCanvas()` de fallback.
  Cada llamada a `mkChart` en `actualizarGraficosAcad` también va en try-catch individual.
