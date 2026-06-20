"""
/*
COMANDO DE COMPILACIÓN (Linux/Mac - RECOMENDADO):
    g++ -shared -fPIC -O3 ajuste_curvas.cpp -o ajuste_curvas_lib.so

COMANDO DE COMPILACIÓN (Windows):
    g++ -shared -O3 ajuste_curvas.cpp -o ajuste_curvas_lib.dll

NOTA: El flag -O3 activa optimizaciones matemáticas máximas para cálculos de alto rendimiento.
*/
"""

import ctypes
import numpy as np
import os
import platform
from pathlib import Path


class AjusteCurvas:
    """
    Clase Python wrapper para la librería C++ de Ajuste de Curvas.
    Usa ctypes (CDLL) para interactuar con las funciones compiladas.
    """

    def __init__(self):
        """Inicializa la clase cargando la librería compilada."""
        self._load_library()
        self.instance = self.lib.create_ajuste_curvas()

    def _load_library(self):
        """Carga la librería compilada (.so o .dll)."""
        lib_dir = Path(__file__).parent
        
        if platform.system() == "Windows":
            lib_name = "ajuste_curvas_lib.dll"
        else:  # Linux, Mac
            lib_name = "ajuste_curvas_lib.so"
        
        lib_path = lib_dir / lib_name
        
        if not lib_path.exists():
            raise FileNotFoundError(
                f"Librería no encontrada: {lib_path}\n"
                f"Por favor compila primero con:\n"
                f"  g++ -shared -fPIC ajuste_curvas.cpp -o {lib_name}"
            )
        
        self.lib = ctypes.CDLL(str(lib_path))
        self._configure_signatures()

    def _configure_signatures(self):
        """Configura los tipos de retorno y argumentos de las funciones C."""
        # Nuevas configuraciones
        self.lib.interpolar_polinomial.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_double
        ]

        self.lib.interpolar_polinomial.restype = ctypes.c_double
        self.lib.leer_csv_filtrado.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        self.lib.leer_csv_filtrado.restype = ctypes.c_int

        self.lib.desviacion_estandar_metodo3.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.desviacion_estandar_metodo3.restype = ctypes.c_double

        self.lib.varianza_metodo3.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.varianza_metodo3.restype = ctypes.c_double

        self.lib.contar_eventos_rango.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_double, ctypes.c_double]
        self.lib.contar_eventos_rango.restype = ctypes.c_int
        
        # Creación y destrucción
        self.lib.create_ajuste_curvas.restype = ctypes.c_void_p
        self.lib.destroy_ajuste_curvas.argtypes = [ctypes.c_void_p]

        # Funciones de Datos
        self.lib.leer_csv.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.leer_csv.restype = ctypes.c_int
        
        self.lib.escribir_csv.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        
        self.lib.imprimir.argtypes = [ctypes.c_void_p]
        
        self.lib.obtener_filas.argtypes = [ctypes.c_void_p]
        self.lib.obtener_filas.restype = ctypes.c_int
        
        self.lib.obtener_columnas.argtypes = [ctypes.c_void_p]
        self.lib.obtener_columnas.restype = ctypes.c_int
        
        self.lib.establecer_matriz.argtypes = [
            ctypes.c_void_p, 
            ctypes.POINTER(ctypes.c_double), 
            ctypes.c_int, 
            ctypes.c_int
        ]
        
        self.lib.obtener_matriz.argtypes = [
            ctypes.c_void_p, 
            ctypes.POINTER(ctypes.c_double), 
            ctypes.c_int, 
            ctypes.c_int
        ]

        # Funciones de Estadística
        self.lib.media.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.media.restype = ctypes.c_double
        
        self.lib.desviacion_estandar.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self.lib.desviacion_estandar.restype = ctypes.c_double
        
        self.lib.varianza.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.varianza.restype = ctypes.c_double
        
        self.lib.minimo.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.minimo.restype = ctypes.c_double
        
        self.lib.maximo.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.maximo.restype = ctypes.c_double
        
        self.lib.percentil.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_double]
        self.lib.percentil.restype = ctypes.c_double
        
        self.lib.mediana.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.mediana.restype = ctypes.c_double
        
        self.lib.buscar_valor.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_double]
        self.lib.buscar_valor.restype = ctypes.c_int
        
        self.lib.ordenar_por_columna.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        
        self.lib.rango.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.rango.restype = ctypes.c_double
        
        self.lib.moda.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.moda.restype = ctypes.c_double
        
        self.lib.coeficiente_variacion.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.coeficiente_variacion.restype = ctypes.c_double
        
        self.lib.pearson_correlation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self.lib.pearson_correlation.restype = ctypes.c_double

        self.lib.diagrama_frecuencias.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int)
        ]

        self.lib.limpiar_datos.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_double, ctypes.c_double]

        self.lib.interpolar_linealmente.argtypes = [ctypes.c_void_p, ctypes.c_int]

        # Funciones de Ajuste de Curvas
        self.lib.regresion_lineal.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double)
        ]
        
        self.lib.regresion_potencial.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double)
        ]
        
        self.lib.regresion_logaritmica.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double)
        ]
        
        self.lib.regresion_exponencial.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double)
        ]
        
        self.lib.regresion_polinomial.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double)
        ]

        self.lib.evaluar_regresion_lineal.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int
        ]

        self.lib.evaluar_regresion_potencial.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int
        ]

        self.lib.evaluar_regresion_logaritmica.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int
        ]

        self.lib.evaluar_regresion_exponencial.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int
        ]

        self.lib.evaluar_regresion_polinomial.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int
        ]

        self.lib.spline_lineal.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_double
        ]
        self.lib.spline_lineal.restype = ctypes.c_double

        self.lib.spline_cuadratico.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double)
        ]

        self.lib.spline_cubico.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double)
        ]

        self.lib.evaluar_spline_lineal.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_double
        ]
        self.lib.evaluar_spline_lineal.restype = ctypes.c_double

        # Configuración de las nuevas funciones
        self.lib.leer_csv_filtrado.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, 
            ctypes.c_int, ctypes.c_int
        ]

        self.lib.leer_csv_filtrado.restype = ctypes.c_int

        self.lib.desviacion_estandar_metodo3.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.desviacion_estandar_metodo3.restype = ctypes.c_double

        self.lib.varianza_metodo3.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.varianza_metodo3.restype = ctypes.c_double

        self.lib.contar_eventos_rango.argtypes = [
            ctypes.c_void_p, ctypes.c_int, 
            ctypes.c_double, ctypes.c_double
        ]
        self.lib.contar_eventos_rango.restype = ctypes.c_int

    def __del__(self):
        """Destruye la instancia y libera memoria."""
        try:
            self.lib.destroy_ajuste_curvas(self.instance)
        except:
            pass

    # =============== MÉTODOS DE DATOS ===============

    def leer_csv_filtrado(self, filename, fecha_filtro, col_fecha, col_valor):
        """Lee el CSV y extrae únicamente una columna de valor para una fecha específica."""
        result = self.lib.leer_csv_filtrado(
            self.instance, 
            filename.encode('utf-8'), 
            fecha_filtro.encode('utf-8'), 
            int(col_fecha), 
            int(col_valor)
        )
        return result != 0

    def desviacion_estandar_metodo3(self, columna):
        """Calcula la desviación estándar usando la fórmula 3 (sin media previa)."""
        return self.lib.desviacion_estandar_metodo3(self.instance, columna)

    def varianza_metodo3(self, columna):
        """Calcula la varianza usando la fórmula 3."""
        return self.lib.varianza_metodo3(self.instance, columna)

    def contar_eventos_rango(self, columna, min_val, max_val):
        """Cuenta cuántos registros caen dentro del intervalo dado."""
        return self.lib.contar_eventos_rango(
            self.instance, columna, float(min_val), float(max_val)
        )

    def leer_csv(self, filename):
        """Lee datos de un archivo CSV."""
        result = self.lib.leer_csv(self.instance, filename.encode('utf-8'))
        return result != 0

    def escribir_csv(self, filename):
        """Escribe los datos a un archivo CSV."""
        self.lib.escribir_csv(self.instance, filename.encode('utf-8'))

    def imprimir(self):
        """Imprime la matriz en consola."""
        self.lib.imprimir(self.instance)

    def obtener_filas(self):
        """Obtiene el número de filas."""
        return self.lib.obtener_filas(self.instance)

    def obtener_columnas(self):
        """Obtiene el número de columnas."""
        return self.lib.obtener_columnas(self.instance)

    def establecer_datos(self, datos_np):
        """
        Establece la matriz desde un array NumPy.
        
        Args:
            datos_np: Array NumPy 2D de tipo float64
        """
        datos_np = np.asarray(datos_np, dtype=np.float64)
        filas, columnas = datos_np.shape
        datos_c = datos_np.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        self.lib.establecer_matriz(self.instance, datos_c, filas, columnas)

    def obtener_datos(self):
        """
        Obtiene los datos como un array NumPy.
        
        Returns:
            Array NumPy 2D
        """
        filas = self.obtener_filas()
        columnas = self.obtener_columnas()
        
        if filas == 0 or columnas == 0:
            return np.array([])
        
        datos = np.zeros((filas, columnas), dtype=np.float64)
        datos_c = datos.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        self.lib.obtener_matriz(self.instance, datos_c, filas, columnas)
        return datos

    # =============== MÉTODOS DE ESTADÍSTICA ===============

    def leer_csv_filtrado(self, filename, fecha_filtro, col_fecha, col_valor):
        return self.lib.leer_csv_filtrado(self.instance, filename.encode('utf-8'), fecha_filtro.encode('utf-8'), col_fecha, col_valor) != 0

    def desviacion_estandar_metodo3(self, columna):
        return self.lib.desviacion_estandar_metodo3(self.instance, columna)

    def varianza_metodo3(self, columna):
        return self.lib.varianza_metodo3(self.instance, columna)

    def contar_eventos_rango(self, columna, min_val, max_val):
        return self.lib.contar_eventos_rango(self.instance, columna, float(min_val), float(max_val))

    def media(self, columna):
        """Calcula la media de una columna."""
        return self.lib.media(self.instance, columna)

    def desviacion_estandar(self, columna, con_media=True):
        """Calcula la desviación estándar."""
        return self.lib.desviacion_estandar(self.instance, columna, int(con_media))

    def varianza(self, columna):
        """Calcula la varianza."""
        return self.lib.varianza(self.instance, columna)

    def minimo(self, columna):
        """Encuentra el valor mínimo."""
        return self.lib.minimo(self.instance, columna)

    def maximo(self, columna):
        """Encuentra el valor máximo."""
        return self.lib.maximo(self.instance, columna)

    def percentil(self, columna, p):
        """Calcula un percentil (p debe estar entre 0 y 100)."""
        return self.lib.percentil(self.instance, columna, float(p))

    def mediana(self, columna):
        """Calcula la mediana (percentil 50)."""
        return self.lib.mediana(self.instance, columna)

    def buscar_valor(self, columna, valor):
        """Busca la fila que contiene un valor."""
        idx = self.lib.buscar_valor(self.instance, columna, float(valor))
        return idx if idx >= 0 else None

    def ordenar_por_columna(self, columna, ascendente=True):
        """Ordena la matriz por una columna."""
        self.lib.ordenar_por_columna(self.instance, columna, int(ascendente))

    def rango(self, columna):
        """Calcula el rango (máx - mín)."""
        return self.lib.rango(self.instance, columna)

    def moda(self, columna):
        """Calcula la moda."""
        return self.lib.moda(self.instance, columna)

    def coeficiente_variacion(self, columna):
        """Calcula el coeficiente de variación (%)."""
        return self.lib.coeficiente_variacion(self.instance, columna)

    def pearson_correlation(self, col_x, col_y):
        """Calcula el coeficiente de correlación de Pearson entre dos columnas."""
        return self.lib.pearson_correlation(self.instance, int(col_x), int(col_y))

    def diagrama_frecuencias(self, columna, num_bins=10):
        """
        Calcula un histograma de frecuencias.
        
        Returns:
            (bins, frecuencias): Tupla con arrays NumPy
        """
        bins = np.zeros(num_bins, dtype=np.float64)
        frecuencias = np.zeros(num_bins, dtype=ctypes.c_int)
        
        bins_c = bins.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        freq_c = frecuencias.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
        
        self.lib.diagrama_frecuencias(self.instance, columna, num_bins, bins_c, freq_c)
        return bins, frecuencias

    def limpiar_datos(self, columna, min_val, max_val):
        """Elimina filas con valores fuera del rango especificado."""
        self.lib.limpiar_datos(self.instance, columna, float(min_val), float(max_val))

    def interpolar_linealmente(self, columna):
        """Interpola linealmente valores faltantes (NaN)."""
        self.lib.interpolar_linealmente(self.instance, columna)

    # =============== MÉTODOS DE AJUSTE DE CURVAS ===============

    def interpolar_polinomial(self, x_vals, y_vals, x_eval):
        """Interpola usando un polinomio global (Lagrange)."""
        x_arr = np.asarray(x_vals, dtype=np.float64)
        y_arr = np.asarray(y_vals, dtype=np.float64)
        x_c = x_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        return self.lib.interpolar_polinomial(self.instance, x_c, y_c, len(x_arr), float(x_eval))
    
    def regresion_lineal(self, col_x, col_y):
        """
        Regresión Lineal: y = a + b*x
        
        Returns:
            (a, b): Tupla con los coeficientes
        """
        coef = (ctypes.c_double * 2)()
        self.lib.regresion_lineal(self.instance, col_x, col_y, coef)
        return float(coef[0]), float(coef[1])

    def regresion_potencial(self, col_x, col_y):
        """
        Regresión Potencial: y = a*x^b
        
        Returns:
            (a, b): Tupla con los coeficientes
        """
        coef = (ctypes.c_double * 2)()
        self.lib.regresion_potencial(self.instance, col_x, col_y, coef)
        return float(coef[0]), float(coef[1])

    def regresion_logaritmica(self, col_x, col_y):
        """
        Regresión Logarítmica: y = a + b*ln(x)
        
        Returns:
            (a, b): Tupla con los coeficientes
        """
        coef = (ctypes.c_double * 2)()
        self.lib.regresion_logaritmica(self.instance, col_x, col_y, coef)
        return float(coef[0]), float(coef[1])

    def regresion_exponencial(self, col_x, col_y):
        """
        Regresión Exponencial: y = a*e^(b*x)
        
        Returns:
            (a, b): Tupla con los coeficientes
        """
        coef = (ctypes.c_double * 2)()
        self.lib.regresion_exponencial(self.instance, col_x, col_y, coef)
        return float(coef[0]), float(coef[1])

    def regresion_polinomial(self, col_x, col_y, grado):
        """
        Regresión Polinomial: y = a0 + a1*x + a2*x^2 + ... + an*x^n
        
        Args:
            grado: Grado del polinomio
            
        Returns:
            Array con los coeficientes [a0, a1, ..., an]
        """
        coef = (ctypes.c_double * (grado + 1))()
        self.lib.regresion_polinomial(self.instance, col_x, col_y, grado, coef)
        return np.array([float(coef[i]) for i in range(grado + 1)])

    def evaluar_regresion_lineal(self, col_x, col_y, x_prediccion):
        """Evalúa la regresión lineal en nuevos puntos X."""
        x_pred = np.asarray(x_prediccion, dtype=np.float64)
        y_pred = np.zeros_like(x_pred)
        
        x_c = x_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        
        self.lib.evaluar_regresion_lineal(self.instance, col_x, col_y, x_c, y_c, len(x_pred))
        return y_pred

    def evaluar_regresion_potencial(self, col_x, col_y, x_prediccion):
        """Evalúa la regresión potencial en nuevos puntos X."""
        x_pred = np.asarray(x_prediccion, dtype=np.float64)
        y_pred = np.zeros_like(x_pred)
        
        x_c = x_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        
        self.lib.evaluar_regresion_potencial(self.instance, col_x, col_y, x_c, y_c, len(x_pred))
        return y_pred

    def evaluar_regresion_logaritmica(self, col_x, col_y, x_prediccion):
        """Evalúa la regresión logarítmica en nuevos puntos X."""
        x_pred = np.asarray(x_prediccion, dtype=np.float64)
        y_pred = np.zeros_like(x_pred)
        
        x_c = x_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        
        self.lib.evaluar_regresion_logaritmica(self.instance, col_x, col_y, x_c, y_c, len(x_pred))
        return y_pred

    def evaluar_regresion_exponencial(self, col_x, col_y, x_prediccion):
        """Evalúa la regresión exponencial en nuevos puntos X."""
        x_pred = np.asarray(x_prediccion, dtype=np.float64)
        y_pred = np.zeros_like(x_pred)
        
        x_c = x_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        
        self.lib.evaluar_regresion_exponencial(self.instance, col_x, col_y, x_c, y_c, len(x_pred))
        return y_pred

    def evaluar_regresion_polinomial(self, col_x, col_y, grado, x_prediccion):
        """Evalúa la regresión polinomial en nuevos puntos X."""
        x_pred = np.asarray(x_prediccion, dtype=np.float64)
        y_pred = np.zeros_like(x_pred)
        
        x_c = x_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_pred.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        
        self.lib.evaluar_regresion_polinomial(self.instance, col_x, col_y, grado, 
                                              x_c, y_c, len(x_pred))
        return y_pred

    def spline_lineal(self, x_vals, y_vals, x_eval):
        """
        Spline Lineal (1er orden).
        
        Args:
            x_vals, y_vals: Puntos conocidos
            x_eval: Valor a evaluar
            
        Returns:
            Valor interpolado en x_eval
        """
        x_arr = np.asarray(x_vals, dtype=np.float64)
        y_arr = np.asarray(y_vals, dtype=np.float64)
        
        x_c = x_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        
        return self.lib.spline_lineal(self.instance, x_c, y_c, len(x_arr), float(x_eval))

    def spline_cuadratico(self, x_vals, y_vals):
        """
        Spline Cuadrático (2do orden).
        
        Returns:
            (a, b, c): Coeficientes de cada segmento
        """
        x_arr = np.asarray(x_vals, dtype=np.float64)
        y_arr = np.asarray(y_vals, dtype=np.float64)
        n = len(x_arr)
        
        a = np.zeros(n - 1, dtype=np.float64)
        b = np.zeros(n - 1, dtype=np.float64)
        c = np.zeros(n - 1, dtype=np.float64)
        
        x_c = x_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        a_c = a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        b_c = b.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        c_c = c.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        
        self.lib.spline_cuadratico(self.instance, x_c, y_c, n, a_c, b_c, c_c)
        return a, b, c

    def spline_cubico(self, x_vals, y_vals):
        """
        Spline Cúbico (3er orden).
        
        Returns:
            (a, b, c, d): Coeficientes de cada segmento
        """
        x_arr = np.asarray(x_vals, dtype=np.float64)
        y_arr = np.asarray(y_vals, dtype=np.float64)
        n = len(x_arr)
        
        a = np.zeros(n - 1, dtype=np.float64)
        b = np.zeros(n - 1, dtype=np.float64)
        c = np.zeros(n - 1, dtype=np.float64)
        d = np.zeros(n - 1, dtype=np.float64)
        
        x_c = x_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        a_c = a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        b_c = b.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        c_c = c.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        d_c = d.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        
        self.lib.spline_cubico(self.instance, x_c, y_c, n, a_c, b_c, c_c, d_c)
        return a, b, c, d

    def evaluar_spline_lineal(self, x_vals, y_vals, x_eval):
        """Evalúa el spline lineal en un punto."""
        x_arr = np.asarray(x_vals, dtype=np.float64)
        y_arr = np.asarray(y_vals, dtype=np.float64)
        
        x_c = x_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        y_c = y_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        
        return self.lib.evaluar_spline_lineal(self.instance, x_c, y_c, len(x_arr), float(x_eval))

    # =============== MÉTODOS DE GRÁFICOS ===============

    def grafico_regresion(self, col_x, col_y, tipo="lineal", titulo="Regresión", 
                         x_min=None, x_max=None):
        """
        Grafica una regresión con matplotlib.
        
        Args:
            col_x, col_y: Columnas para X e Y
            tipo: "lineal", "potencial", "logaritmica", "exponencial", "polinomial"
            titulo: Título del gráfico
            x_min, x_max: Rango de X para la predicción
        """
        import matplotlib.pyplot as plt
        
        datos = self.obtener_datos()
        x_datos = datos[:, col_x]
        y_datos = datos[:, col_y]
        
        if x_min is None:
            x_min = np.min(x_datos) * 0.9
        if x_max is None:
            x_max = np.max(x_datos) * 1.1
        
        x_pred = np.linspace(x_min, x_max, 100)
        
        if tipo == "lineal":
            y_pred = self.evaluar_regresion_lineal(col_x, col_y, x_pred)
        elif tipo == "potencial":
            y_pred = self.evaluar_regresion_potencial(col_x, col_y, x_pred)
        elif tipo == "logaritmica":
            y_pred = self.evaluar_regresion_logaritmica(col_x, col_y, x_pred)
        elif tipo == "exponencial":
            y_pred = self.evaluar_regresion_exponencial(col_x, col_y, x_pred)
        elif tipo == "polinomial":
            grado = 3  # Por defecto, polinomio de grado 3
            y_pred = self.evaluar_regresion_polinomial(col_x, col_y, grado, x_pred)
        else:
            raise ValueError(f"Tipo de regresión desconocido: {tipo}")
        
        plt.figure(figsize=(10, 6))
        plt.scatter(x_datos, y_datos, color='blue', label='Datos', s=50)
        plt.plot(x_pred, y_pred, color='red', label=f'Regresión {tipo}', linewidth=2)
        plt.xlabel('X')
        plt.ylabel('Y')
        plt.title(titulo)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.show()

    def grafico_interpolacion(self, x_vals, y_vals, tipo="lineal", 
                             titulo="Interpolación", puntos_evaluacion=100):
        """
        Grafica una interpolación con matplotlib.
        
        Args:
            x_vals, y_vals: Puntos conocidos
            tipo: "lineal", "cuadratica", "cubica"
            titulo: Título del gráfico
            puntos_evaluacion: Número de puntos para interpolar
        """
        import matplotlib.pyplot as plt
        
        x_arr = np.asarray(x_vals, dtype=np.float64)
        y_arr = np.asarray(y_vals, dtype=np.float64)
        
        x_min, x_max = np.min(x_arr), np.max(x_arr)
        x_pred = np.linspace(x_min, x_max, puntos_evaluacion)
        
        if tipo == "lineal":
            y_pred = np.array([self.spline_lineal(x_arr, y_arr, x) for x in x_pred])
        elif tipo == "cuadratica":
            y_pred = np.array([self.spline_lineal(x_arr, y_arr, x) for x in x_pred])
        elif tipo == "cubica":
            y_pred = np.array([self.spline_lineal(x_arr, y_arr, x) for x in x_pred])
        else:
            raise ValueError(f"Tipo de interpolación desconocido: {tipo}")
        
        plt.figure(figsize=(10, 6))
        plt.scatter(x_arr, y_arr, color='blue', label='Puntos conocidos', s=80, zorder=5)
        plt.plot(x_pred, y_pred, color='red', label=f'Interpolación {tipo}', linewidth=2)
        plt.xlabel('X')
        plt.ylabel('Y')
        plt.title(titulo)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.show()

    def grafico_histograma(self, columna, num_bins=10, titulo="Histograma"):
        """
        Grafica un histograma de frecuencias.
        
        Args:
            columna: Columna a graficar
            num_bins: Número de bins
            titulo: Título del gráfico
        """
        import matplotlib.pyplot as plt
        
        bins, frecuencias = self.diagrama_frecuencias(columna, num_bins)
        
        plt.figure(figsize=(10, 6))
        plt.bar(bins, frecuencias, width=bins[1]-bins[0] if len(bins) > 1 else 1, 
                color='skyblue', edgecolor='black')
        plt.xlabel('Valores')
        plt.ylabel('Frecuencia')
        plt.title(titulo)
        plt.grid(True, alpha=0.3, axis='y')
        plt.show()
