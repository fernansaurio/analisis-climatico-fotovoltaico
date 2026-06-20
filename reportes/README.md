# PROYECTO — Análisis Climático Avanzado con Métodos Numéricos

## Estructura de archivos

```
proyecto_climatico/
│
├── analisis_climatico.py          ← PUNTO DE ENTRADA PRINCIPAL
│
├── ajuste_curvas.py               ← Wrapper Python → C++ (AjusteCurvas)
├── ajuste_curvas.cpp              ← Motor C++ de estadísticas
│
├── metodos_raices.py              ← Wrapper Python → C++ (Newton-Raphson)
├── metodos_cerrados.cpp           ← Métodos de búsqueda de raíces
│
├── algebra_lineal_lib.py          ← Wrapper Python → C++ (AlgebraLineal)
├── algebra_lineal.cpp             ← Operaciones matriciales C++
├── algebra_lineal_binding.cpp     ← Interfaz C plana para ctypes
│
├── 7GT-EEP_1-1-25_12-00_AM_1_Year.csv
├── 7GT-EEP_1-1-26_12-00_AM_6_Month.csv
├── 7GT-UES_1-1-25_12-00_AM_1_Year.csv
└── 7GT-UES_1-1-26_12-00_AM_6_Month_*.csv
```

---

## Librerías Python requeridas

| Librería      | Uso permitido                                              | Instalar               |
|---------------|------------------------------------------------------------|------------------------|
| `pandas`      | `pd.read_csv`, `pd.to_datetime`, `pd.concat`, `drop_duplicates` | `pip install pandas`   |
| `numpy`       | `np.asarray`, `np.zeros`, `np.float64`, `np.nan`          | `pip install numpy`    |
| `matplotlib`  | Renderizado final de gráficos (backend Agg)               | `pip install matplotlib` |
| `ctypes`      | Carga de bibliotecas `.so`/`.dll`                         | Estándar Python        |
| `os`, `math`, `io`, `base64`, `json`, `webbrowser` | Utilidades estándar | Estándar Python |

> ❌ **PROHIBIDO usar:** `.mean()` `.std()` `.var()` `.median()` `.quantile()` `.mode()`
> `.describe()` `.min()` `.max()` `.interpolate()` `.fillna()` de pandas/numpy/scipy.

---

## Compilación de las bibliotecas C++

Todos los comandos deben ejecutarse en el directorio del proyecto.

### Linux / macOS

```bash
# 1. AjusteCurvas
g++ -shared -fPIC -O3 -std=c++17 ajuste_curvas.cpp -o ajuste_curvas_lib.so

# 2. MetodosRaices
g++ -shared -fPIC -O2 -std=c++17 metodos_cerrados.cpp -o libraices.so

# 3. AlgebraLineal
g++ -O2 -shared -fPIC -std=c++17 \
    algebra_lineal.cpp algebra_lineal_binding.cpp \
    -o algebra_lineal.so
```

### Windows (MinGW / MSYS2)

```bash
g++ -shared -O3 -std=c++17 ajuste_curvas.cpp -o ajuste_curvas_lib.dll
g++ -shared -O2 -std=c++17 metodos_cerrados.cpp -o libraices.dll
g++ -shared -O2 -std=c++17 algebra_lineal.cpp algebra_lineal_binding.cpp -o algebra_lineal.dll
```

### Verificación

```python
python -c "from ajuste_curvas import AjusteCurvas; print('AjusteCurvas OK')"
python -c "from metodos_raices import MetodosRaices; print('MetodosRaices OK')"
python -c "from algebra_lineal_lib import AlgebraLineal; print('AlgebraLineal OK')"
```

---

## Ejecución

```bash
python analisis_climatico.py
```

El script:
1. Carga y cura los CSVs (Fase I)
2. Calcula estadísticos completos (Fase II)
3. Genera todos los gráficos (Fase III)
4. Calcula Pearson inter-estacional (Fase IV)
5. Genera `dashboard_proyecto_climatico.html` y lo abre en el navegador

---

## Algoritmos implementados (sin caja negra)

| Algoritmo                  | Dónde se usa                          | Motor       |
|----------------------------|---------------------------------------|-------------|
| QuickSort mediana-de-tres  | Cálculo de percentiles                | C++ / Python|
| Newton-Raphson (Babilónico)| Raíz cuadrada para σ                  | C++ / Python|
| Interpolación lineal manual| Curación de valores faltantes (NaN)   | Python      |
| Tabla de frecuencias       | Moda, histograma                      | C++ / Python|
| Regla de Sturges           | Número de bins del histograma          | Python      |
| Pearson manual             | Correlación inter-estacional          | C++ / Python|
| Media aritmética manual    | Estadístico base                      | C++ / Python|
| Varianza insesgada (Método 3) | Varianza y σ                       | C++         |

---

## Configurar nombres de archivos CSV

En `analisis_climatico.py`, ajusta las listas al inicio de `main()`:

```python
ARCHIVOS_EEP = [
    "7GT-EEP_1-1-25_12-00_AM_1_Year.csv",
    "7GT-EEP_1-1-26_12-00_AM_6_Month.csv",
]
ARCHIVOS_UES = [
    "7GT-UES_1-1-25_12-00_AM_1_Year.csv",
    "7GT-UES_1-1-26_12-00_AM_6_Month_1778958209_v2.csv",
]
```
