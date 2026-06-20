"""
Wrapper de Python para métodos numéricos de búsqueda de raíces.

Este módulo proporciona una interfaz simple para usar los métodos de búsqueda
de raíces compilados en C++ sin necesidad de trabajar directamente con ctypes.

Uso:
    from metodos_wrapper import MetodosRaices
    
    mr = MetodosRaices()
    
    # Definir una función
    f = lambda x: x**2 - 4
    
    # Usar bisección
    raiz = mr.biseccion(f, 0, 5, tol=1e-6)
    print(f"Raíz encontrada: {raiz}")
"""

import ctypes
import os
from ctypes import c_double, c_int, CFUNCTYPE, byref


class MetodosRaices:
    """
    Wrapper para los métodos numéricos de búsqueda de raíces implementados en C++.
    
    Atributos:
        lib: La biblioteca compartida (.so) cargada
    """
    
    def __init__(self, ruta_lib=None):
        """
        Inicializa el wrapper cargando la biblioteca compartida.
        
        Args:
            ruta_lib (str, optional): Ruta a la biblioteca .so. Si no se proporciona,
                                     se busca en el directorio actual.
        """
        if ruta_lib is None:
            # Buscar la biblioteca en el directorio actual
            dir_actual = os.path.dirname(os.path.abspath(__file__))
            ruta_lib = os.path.join(dir_actual, 'libraices.so')
        
        if not os.path.exists(ruta_lib):
            raise FileNotFoundError(
                f"No se encontró la biblioteca: {ruta_lib}\n"
                f"Asegúrate de compilar metodos_cerrados.cpp primero."
            )
        
        try:
            self.lib = ctypes.CDLL(ruta_lib)
        except OSError as e:
            raise RuntimeError(f"Error al cargar la biblioteca: {e}")
        
        # Definir el tipo de función callback
        self.FUNC_TYPE = CFUNCTYPE(c_double, c_double)
        
        # Configurar prototipos de funciones
        self._configurar_prototipos()
    
    def _configurar_prototipos(self):
        """Configura los prototipos de las funciones C++."""
        # biseccion(FuncPtr f, double a, double b, double tol, int max_iter, int* iteraciones)
        self.lib.biseccion.argtypes = [
            self.FUNC_TYPE, c_double, c_double, c_double, c_int, ctypes.POINTER(c_int)
        ]
        self.lib.biseccion.restype = c_double
        
        # falsa_posicion(FuncPtr f, double a, double b, double tol, int max_iter, int* iteraciones)
        self.lib.falsa_posicion.argtypes = [
            self.FUNC_TYPE, c_double, c_double, c_double, c_int, ctypes.POINTER(c_int)
        ]
        self.lib.falsa_posicion.restype = c_double
        
        # newton_raphson(FuncPtr f, FuncPtr df, double p0, double tol, int max_iter, int* iteraciones)
        self.lib.newton_raphson.argtypes = [
            self.FUNC_TYPE, self.FUNC_TYPE, c_double, c_double, c_int, ctypes.POINTER(c_int)
        ]
        self.lib.newton_raphson.restype = c_double
        
        # secante(FuncPtr f, double p0, double p1, double tol, int max_iter, int* iteraciones)
        self.lib.secante.argtypes = [
            self.FUNC_TYPE, c_double, c_double, c_double, c_int, ctypes.POINTER(c_int)
        ]
        self.lib.secante.restype = c_double
        
        # punto_fijo(FuncPtr g, double p0, double tol, int max_iter, int* iteraciones)
        self.lib.punto_fijo.argtypes = [
            self.FUNC_TYPE, c_double, c_double, c_int, ctypes.POINTER(c_int)
        ]
        self.lib.punto_fijo.restype = c_double
    
    def biseccion(self, f, a, b, tol=1e-6, max_iter=100):
        """
        Encuentra la raíz de f(x) en el intervalo [a, b] usando el método de bisección.
        
        Args:
            f (callable): Función para la cual encontrar la raíz
            a (float): Límite inferior del intervalo
            b (float): Límite superior del intervalo
            tol (float, optional): Tolerancia. Por defecto 1e-6
            max_iter (int, optional): Máximo de iteraciones. Por defecto 100
        
        Returns:
            tuple: (raiz, iteraciones)
        
        Raises:
            ValueError: Si el intervalo no contiene una raíz
        """
        callback = self.FUNC_TYPE(f)
        iteraciones = c_int()
        
        raiz = self.lib.biseccion(
            callback, c_double(a), c_double(b), c_double(tol), c_int(max_iter),
            byref(iteraciones)
        )
        
        if self._es_nan(raiz):
            raise ValueError(f"El intervalo [{a}, {b}] no contiene una raíz")
        
        return raiz, iteraciones.value
    
    def falsa_posicion(self, f, a, b, tol=1e-6, max_iter=100):
        """
        Encuentra la raíz de f(x) usando el método de falsa posición.
        
        Args:
            f (callable): Función para la cual encontrar la raíz
            a (float): Límite inferior del intervalo
            b (float): Límite superior del intervalo
            tol (float, optional): Tolerancia. Por defecto 1e-6
            max_iter (int, optional): Máximo de iteraciones. Por defecto 100
        
        Returns:
            tuple: (raiz, iteraciones)
        
        Raises:
            ValueError: Si el intervalo no contiene una raíz
        """
        callback = self.FUNC_TYPE(f)
        iteraciones = c_int()
        
        raiz = self.lib.falsa_posicion(
            callback, c_double(a), c_double(b), c_double(tol), c_int(max_iter),
            byref(iteraciones)
        )
        
        if self._es_nan(raiz):
            raise ValueError(f"El intervalo [{a}, {b}] no contiene una raíz")
        
        return raiz, iteraciones.value
    
    def newton_raphson(self, f, df, p0, tol=1e-6, max_iter=100):
        """
        Encuentra la raíz de f(x) usando el método de Newton-Raphson.
        
        Args:
            f (callable): Función para la cual encontrar la raíz
            df (callable): Derivada de f
            p0 (float): Aproximación inicial
            tol (float, optional): Tolerancia. Por defecto 1e-6
            max_iter (int, optional): Máximo de iteraciones. Por defecto 100
        
        Returns:
            tuple: (raiz, iteraciones)
        
        Raises:
            ValueError: Si la derivada es cero
        """
        callback_f = self.FUNC_TYPE(f)
        callback_df = self.FUNC_TYPE(df)
        iteraciones = c_int()
        
        raiz = self.lib.newton_raphson(
            callback_f, callback_df, c_double(p0), c_double(tol),
            c_int(max_iter), byref(iteraciones)
        )
        
        if self._es_nan(raiz):
            raise ValueError("La derivada fue cero o no convergió")
        
        return raiz, iteraciones.value
    
    def secante(self, f, p0, p1, tol=1e-6, max_iter=100):
        """
        Encuentra la raíz de f(x) usando el método de la secante.
        
        Args:
            f (callable): Función para la cual encontrar la raíz
            p0 (float): Primera aproximación inicial
            p1 (float): Segunda aproximación inicial
            tol (float, optional): Tolerancia. Por defecto 1e-6
            max_iter (int, optional): Máximo de iteraciones. Por defecto 100
        
        Returns:
            tuple: (raiz, iteraciones)
        """
        callback = self.FUNC_TYPE(f)
        iteraciones = c_int()
        
        raiz = self.lib.secante(
            callback, c_double(p0), c_double(p1), c_double(tol),
            c_int(max_iter), byref(iteraciones)
        )
        
        return raiz, iteraciones.value
    
    def punto_fijo(self, g, p0, tol=1e-6, max_iter=100):
        """
        Encuentra el punto fijo de g(x) usando el método de punto fijo.
        
        Args:
            g (callable): Función de iteración (g(x) debe satisfacer g(x) = x en la raíz)
            p0 (float): Aproximación inicial
            tol (float, optional): Tolerancia. Por defecto 1e-6
            max_iter (int, optional): Máximo de iteraciones. Por defecto 100
        
        Returns:
            tuple: (raiz, iteraciones)
        """
        callback = self.FUNC_TYPE(g)
        iteraciones = c_int()
        
        raiz = self.lib.punto_fijo(
            callback, c_double(p0), c_double(tol), c_int(max_iter),
            byref(iteraciones)
        )
        
        return raiz, iteraciones.value
    
    @staticmethod
    def _es_nan(valor):
        """Verifica si un valor es NaN."""
        return valor != valor  # NaN es el único valor que no es igual a sí mismo


# Ejemplo de uso
if __name__ == "__main__":
    print("Wrapper de Métodos Numéricos para Búsqueda de Raíces\n")
    
    mr = MetodosRaices()
    
    # Ejemplo 1: Bisección
    print("=" * 50)
    print("Método de Bisección")
    print("=" * 50)
    f = lambda x: x**2 - 4
    raiz, iters = mr.biseccion(f, 0, 3)
    print(f"f(x) = x² - 4")
    print(f"Raíz: {raiz:.10f}")
    print(f"Iteraciones: {iters}\n")
    
    # Ejemplo 2: Falsa Posición
    print("=" * 50)
    print("Método de Falsa Posición")
    print("=" * 50)
    f = lambda x: x**3 - 2
    raiz, iters = mr.falsa_posicion(f, 1, 2)
    print(f"f(x) = x³ - 2")
    print(f"Raíz: {raiz:.10f}")
    print(f"Iteraciones: {iters}\n")
    
    # Ejemplo 3: Newton-Raphson
    print("=" * 50)
    print("Método de Newton-Raphson")
    print("=" * 50)
    f = lambda x: x**2 - 4
    df = lambda x: 2*x
    raiz, iters = mr.newton_raphson(f, df, 3)
    print(f"f(x) = x² - 4, f'(x) = 2x")
    print(f"Raíz: {raiz:.10f}")
    print(f"Iteraciones: {iters}\n")
    
    # Ejemplo 4: Secante
    print("=" * 50)
    print("Método de la Secante")
    print("=" * 50)
    f = lambda x: x**3 - 2
    raiz, iters = mr.secante(f, 1, 2)
    print(f"f(x) = x³ - 2")
    print(f"Raíz: {raiz:.10f}")
    print(f"Iteraciones: {iters}\n")
    
    # Ejemplo 5: Punto Fijo
    print("=" * 50)
    print("Método de Punto Fijo")
    print("=" * 50)
    g = lambda x: (2 + x) / 3  # Punto fijo de x = (2+x)/3 es x=1
    raiz, iters = mr.punto_fijo(g, 0.5)
    print(f"g(x) = (2 + x) / 3")
    print(f"Raíz: {raiz:.10f}")
    print(f"Iteraciones: {iters}\n")
