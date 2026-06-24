# Análisis Climático y Fotovoltaico — Guía de instalación

Proyecto de Programación Numérica · AEL115 · Universidad de El Salvador  
Estaciones 7GT-EEP (San Luis Talpa, La Paz) · 7GT-UES (San Salvador) · Sistema SMA Solar (EIE)

---

## Requisitos del sistema

| Requisito | Versión mínima |
|---|---|
| **Sistema operativo** | Linux 64-bit (Ubuntu 20.04+ / Debian 11+) |
| **Python** | 3.8 o superior |
| **Librerías C++** | Ya compiladas en `core_math/*.so` — **no recompilar** |

Instalar dependencias Python:
```bash
pip install pandas numpy
```

---

## Pasos de instalación

### 1. Clonar el repositorio
```bash
git clone https://github.com/TU_USUARIO/tarea-climatica.git
cd tarea-climatica
pip install pandas numpy
```

### 2. Copiar los archivos de datos

Pega **todos** tus archivos CSV dentro de la carpeta `datos_crudos/`.  
No importa el orden ni si los mezclas — el script los detecta solos.

```
tarea-climatica/
└── datos_crudos/          ← pon aquí todos los CSV (cualquier subestructura)
    ├── 7GT-EEP_1-1-25_....csv
    ├── 7GT-UES_1-1-25_....csv
    ├── 2025-01-01.csv
    ├── 05-12-2025.csv
    └── ... (puedes crear subcarpetas, el script las recorre todas)
```

**Tipos de datos soportados:**
- **WeatherLink** — archivos exportados de weatherlink.com para las estaciones `7GT-EEP` y `7GT-UES`
- **SMA Solar** — archivos CSV exportados del portal del inversor SMA (uno por día)

### 3. Ordenar los datos automáticamente
```bash
python3 ordenar_datos.py
```

El script analiza el contenido de cada CSV, lo identifica y lo mueve al lugar correcto:

```
Escaneando: /home/.../tarea-climatica/datos_crudos/
============================================================
  ✓  7GT-EEP_1-1-25_...csv   →  weatherlink/   [WeatherLink EEP]
  ✓  7GT-UES_1-1-25_...csv   →  weatherlink/   [WeatherLink UES]
  ✓  2025-01-01.csv           →  sma_solar/     [SMA]
  ✓  05-12-2025.csv           →  sma_solar/2025-05-12.csv  [SMA, renombrado]
============================================================
  WeatherLink: 4 movido(s)  |  SMA: 548 movido(s)  |  Desconocidos: 0
```

### 4. Generar los dashboards
```bash
python3 ejecutar_proyecto.py
```
Tiempo aproximado: **2-3 minutos**. Al terminar genera:
- `dashboard/dashboard_msn_interactivo.html` — Análisis climático completo
- `dashboard/dashboard_solar.html` — Producción fotovoltaica SMA
- `dashboard/dashboard_fusion.html` — Correlación radiación ↔ potencia

### 5. Abrir los dashboards

Abrir cualquiera de los HTML directamente en el navegador (Firefox, Chrome).  
No se necesita servidor web — funcionan con el protocolo `file://`.

---

## Estructura del proyecto (referencia)

```
tarea-climatica/
├── src/                        ← scripts Python de análisis
│   ├── analisis_climatico.py   ← dashboard climático principal
│   ├── analisis_sma.py         ← dashboard solar SMA
│   └── exportar_fusion.py      ← fusión radiación-potencia
├── core_math/                  ← librerías C++ compiladas + wrappers Python
│   ├── ajuste_curvas_lib.so    ← estadísticos, regresión polinomial/lineal
│   ├── libraices.so            ← métodos numéricos (Newton-Raphson, etc.)
│   ├── algebra_lineal.so       ← álgebra lineal
│   ├── ajuste_curvas.py        ← wrapper Python para AjusteCurvas
│   ├── metodos_raices.py       ← wrapper Python para MetodosRaices
│   └── algebra_lineal_lib.py   ← wrapper Python para AlgebraLineal
├── datos_crudos/               ← datos CSV (NO incluidos en el repo)
│   ├── weatherlink/            ← generado por ordenar_datos.py
│   └── sma_solar/              ← generado por ordenar_datos.py
├── dashboard/                  ← dashboards HTML generados
├── docs/                       ← copia para GitHub Pages
├── reportes/                   ← bitácora, apuntes, PDF
├── ordenar_datos.py            ← auto-ordenador de datos CSV
├── ejecutar_proyecto.py        ← punto de entrada principal
└── publicar.sh                 ← sube dashboards a GitHub Pages
```

---

## Si usas Windows o macOS (recompilación C++)

Los archivos `.so` son binarios para **Linux x86_64**. En otros sistemas necesitas recompilar:

```bash
cd core_math/fuentes_cpp

# Linux/macOS
g++ -shared -fPIC -O3 ajuste_curvas.cpp   -o ../ajuste_curvas_lib.so
g++ -shared -fPIC -O3 metodos_cerrados.cpp -o ../libraices.so

# Windows (MinGW)
g++ -shared -O3 ajuste_curvas.cpp   -o ../ajuste_curvas_lib.dll
g++ -shared -O3 metodos_cerrados.cpp -o ../libraices.dll
```

> `algebra_lineal.so` no tiene fuente en el repo — contactar al autor para obtenerla.
