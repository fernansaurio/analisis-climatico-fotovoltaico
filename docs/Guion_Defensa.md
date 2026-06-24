# Guión de Defensa — Análisis Climático y Fotovoltaico
**AEL115 · Programación Numérica · Ciclo I-2026**

---

## INTRODUCCIÓN (30 segundos)

> "El proyecto consiste en el análisis estadístico de datos reales de dos estaciones meteorológicas instaladas en El Salvador y de un sistema solar fotovoltaico ubicado aquí en la EIE. Todo el análisis fue implementado desde cero en Python y C++, sin usar las funciones estadísticas de alto nivel de las bibliotecas, porque el objetivo era aplicar los métodos numéricos vistos en clase."

---

## PARTE 1 — DASHBOARD DE ANÁLISIS CLIMÁTICO

*Abrir: `dashboard_msn_interactivo.html`*

### ¿Qué son las dos estaciones?

> "Trabajamos con dos estaciones WeatherLink Davis Vantage Pro2. La estación **7GT-EEP** está en San Luis Talpa, La Paz, que es una zona costera. La estación **7GT-UES** está aquí en el campus de la Universidad. Los datos son registros de cada 15 minutos desde febrero de 2025 hasta mayo de 2026."

### El calendario de días (parte superior)

> "Lo primero que se ve es el calendario. Cada tarjeta representa un día. El ícono indica el tipo de clima de ese día — sol, nubes, lluvia o tormenta — calculado en base a la radiación solar y la precipitación registrada. El número de arriba es la temperatura máxima del día y el de abajo la mínima. Al hacer clic en cualquier día, toda la página cambia y muestra solo los datos de ese día."

> "También puedo usar el input de fecha en la barra de arriba para ir directo a una fecha específica sin buscar en el calendario."

### Los botones Día / Mes / Año / Todo

> "Estos botones en la barra superior cambian el período de análisis. Si selecciono 'Día' y hago clic en un día del calendario, los gráficos muestran la evolución cada 15 minutos de ese día. En 'Mes' veo el promedio diario del mes seleccionado. En 'Todo' veo el período completo."

### Cambiar entre estaciones (EEP / UES)

> "Con los botones de la barra puedo cambiar entre la estación de San Luis Talpa y la de la Universidad. Todos los estadísticos y gráficas se actualizan automáticamente."

### El panel de estadísticos

> "A la derecha o debajo del calendario aparece el panel con los estadísticos calculados para el período seleccionado. Aquí están: la temperatura media, la desviación estándar, el mínimo, el máximo, los percentiles Q1 y Q3, y la correlación de Pearson entre las dos estaciones. Todos estos valores fueron calculados manualmente en Python con bucles, sin usar .mean() ni .std() de pandas."

### Las gráficas interactivas (uPlot)

> "Las dos gráficas de abajo son interactivas. La primera muestra la temperatura y la humedad al mismo tiempo, con dos ejes Y distintos — uno para temperatura en azul y otro para humedad en verde. Se puede hacer zoom arrastrando el mouse. La segunda gráfica muestra la radiación solar. Estas gráficas cambian según el período seleccionado."

### Las figuras estáticas

> "Más abajo están las figuras calculadas con matplotlib. La **rosa de los vientos** muestra de qué dirección sopla el viento con más frecuencia y con qué velocidad — la estación de San Luis Talpa tiene vientos más fuertes del norte y noroeste por ser zona costera. El **histograma** muestra la distribución de temperaturas del período. El **boxplot mensual** permite ver la variación de temperatura mes a mes — los meses de verano tienen mayor amplitud térmica. El **mapa de calor horario** muestra a qué hora del día hay más radiación solar o más temperatura, separado por mes."

### La matriz de correlación de Pearson

> "Esta figura muestra la correlación entre todas las variables climáticas. Los valores cercanos a 1 o -1 indican relación fuerte. Por ejemplo, temperatura y radiación solar están positivamente correlacionadas — cuando hay más sol, hace más calor. Temperatura y humedad están negativamente correlacionadas — cuando hace calor, la humedad baja."

### El modelo de tendencia (regresión)

> "En la pestaña de tendencia hay dos líneas sobre la serie temporal de temperatura: la línea recta de regresión lineal que muestra la tendencia general del período, calculada con la biblioteca C++ AjusteCurvas, y la curva polinomial de grado 3 que modela mejor los cambios estacionales y proyecta los próximos 30 días. Esa zona proyectada está resaltada en la gráfica."

---

## PARTE 2 — DASHBOARD SOLAR FOTOVOLTAICO

*Abrir: `dashboard_solar.html`*

### ¿Qué es el sistema solar?

> "Este dashboard analiza el sistema fotovoltaico de la EIE. Tiene tres inversores SMA WR725UAE y un piranómetro que mide la radiación solar que llega a los paneles. Los datos son de cada 15 minutos desde 2023 hasta 2026."

### Los KPIs superiores

> "Los cuatro números grandes de arriba son los indicadores clave del sistema: la energía total producida en el período en kWh, la potencia AC media en watts, la irradiancia media en W/m², y la correlación de Pearson entre la irradiancia y la potencia generada."

### El calendario solar

> "El calendario funciona igual que en el análisis climático. Cada tarjeta muestra la energía producida ese día en kWh, y la barra de color indica qué tan productivo fue ese día en relación al mejor día del período. Los días sin datos aparecen en gris. Al hacer clic en un día, o usar el input de fecha de la barra superior, los gráficos muestran los datos de esa jornada específica."

### Las gráficas de potencia e irradiancia

> "Las gráficas muestran la curva de potencia AC del sistema en watts y la irradiancia del piranómetro a lo largo del día o del período seleccionado. La curva de potencia tiene forma de campana — sube desde el amanecer, llega al máximo al mediodía y baja hasta cero al atardecer. La irradiancia tiene el mismo comportamiento."

### ¿Por qué la correlación es tan alta?

> "La correlación de Pearson entre irradiancia y potencia es mayor a 0.97. Esto confirma que prácticamente toda la variación en la potencia generada está explicada por la cantidad de radiación solar disponible. Los inversores convierten eficientemente la energía del sol en electricidad."

---

## PARTE 3 — DASHBOARD DE FUSIÓN

*Abrir: `dashboard_fusion.html`*

### ¿Para qué sirve este dashboard?

> "Este dashboard combina los datos climáticos de WeatherLink con los del sistema SMA en una misma vista. El objetivo es ver directamente si hay relación entre lo que mide el piranómetro de la estación meteorológica y lo que genera el sistema solar. En la gráfica aparecen las dos curvas al mismo tiempo — la radiación solar medida por la estación climática en azul y la potencia AC del sistema solar en amarillo."

### ¿Qué se puede analizar aquí?

> "Si selecciono un día con mucho sol, ambas curvas deben tener forma de campana similar. Si hay un día nublado, ambas curvas caen al mismo tiempo. Esto permite detectar si el sistema solar está respondiendo correctamente a las condiciones climáticas, o si hay algo que no cuadra."

---

## PARTE 4 — MÉTODOS NUMÉRICOS (si preguntan)

> "Los métodos numéricos que implementé son:"

> "**Media aritmética**: suma de todos los valores dividida entre n, con un bucle for."

> "**Varianza y desviación estándar**: usando la fórmula de varianza muestral con n-1 en el denominador. La raíz cuadrada se calcula con el método de Newton-Raphson implementado en C++."

> "**Percentiles**: primero ordeno los datos con QuickSort que implementé yo mismo, luego interpolo linealmente entre las posiciones para obtener Q1, Q2 y Q3."

> "**Interpolación lineal**: para rellenar los valores faltantes en los CSV, uso f(x) = f(a) + [f(b) - f(a)] × (x - a) / (b - a), pero solo si el hueco es menor a 30 minutos."

> "**Correlación de Pearson**: calculo la covarianza entre las dos variables y la divido entre el producto de sus desviaciones estándar. La implementé tanto en Python como en C++ y los resultados difieren en menos de 10 elevado a la menos 12."

> "**Regresión lineal y polinomial**: usando el sistema de ecuaciones normales, resuelto con eliminación gaussiana con pivoteo parcial en la biblioteca C++ AjusteCurvas."

---

## PARTE 5 — LAS BIBLIOTECAS C++

> "Tengo tres bibliotecas compiladas en C++ que Python llama directamente usando el módulo ctypes. Esto significa que le paso los datos de Python como arreglos de doubles a la función C++, ella hace el cálculo y devuelve el resultado. Las tres son: AjusteCurvas para la regresión, MetodosRaices para Newton-Raphson, y AlgebraLineal para la correlación de Pearson."

---

## CIERRE (15 segundos)

> "En resumen, el proyecto aplica estadística descriptiva, interpolación, regresión lineal y polinomial, y correlación de Pearson sobre datos reales de El Salvador, implementados manualmente en Python con soporte de C++, y presentados en dashboards web interactivos que permiten explorar los datos por día, mes o año."

---

## PREGUNTAS FRECUENTES

**¿Por qué usaron C++ si ya tenían Python?**
> "Para practicar la integración entre lenguajes y porque algunos métodos como Newton-Raphson o la eliminación gaussiana son más eficientes en C++ cuando los datos son grandes."

**¿Qué significa la desviación estándar en este contexto?**
> "Indica qué tan variable es la temperatura o la radiación. Una desviación estándar alta significa que hay días muy diferentes entre sí. En la estación seca la desviación es menor porque los días son más uniformes."

**¿Por qué la correlación de Pearson entre irradiancia y potencia da diferente según el filtro?**
> "Porque si incluyo las horas de la noche, donde tanto la irradiancia como la potencia son cero, hay muchos puntos iguales que no aportan variabilidad real. Al filtrar solo las horas de sol, la correlación refleja mejor la relación real entre las dos variables."

**¿Qué es el mapa de calor horario?**
> "Es una matriz donde las filas son las horas del día (0 a 23) y las columnas son los meses del año. El color de cada celda representa el promedio de temperatura o radiación solar para esa hora en ese mes. Permite ver, por ejemplo, que la temperatura más alta siempre ocurre entre la 1 y las 3 de la tarde, en todos los meses."

**¿Por qué no usaron .mean() de pandas?**
> "Porque el requisito del proyecto era implementar los métodos numéricos manualmente para demostrar que entendemos los algoritmos, no solo llamar funciones de una biblioteca."
