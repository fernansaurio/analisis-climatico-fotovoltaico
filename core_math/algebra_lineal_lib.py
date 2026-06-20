"""
algebra_lineal.py
Wrapper Python para algebra_lineal.so  (compilado desde C++)
Uso:
    from algebra_lineal import AlgebraLineal, Matriz
"""

import ctypes
import os
import numpy as np
import argparse
from pathlib import Path

# ── Cargar la librería ────────────────────────────────────────────────────────
_LIB_PATH = Path(__file__).parent / "algebra_lineal.so"
try:
    _lib = ctypes.CDLL(str(_LIB_PATH))
except OSError as e:
    raise ImportError(
        f"No se pudo cargar algebra_lineal.so: {e}\n"
        "Compila primero con:\n"
        "  g++ -O2 -shared -fPIC -std=c++17 "
        "algebra_lineal.cpp algebra_lineal_binding.cpp -o algebra_lineal.so"
    )

# ── Tipos alias ───────────────────────────────────────────────────────────────
_ALHandle = ctypes.c_void_p
_Dp       = ctypes.POINTER(ctypes.c_double)
_Ip       = ctypes.POINTER(ctypes.c_int)

# ── Prototipado de funciones C ────────────────────────────────────────────────
def _proto(fname, restype, *argtypes):
    fn = getattr(_lib, fname)
    fn.restype  = restype
    fn.argtypes = list(argtypes)
    return fn

_al_crear           = _proto("al_crear",           _ALHandle, _Dp, ctypes.c_int, ctypes.c_int)
_al_destruir        = _proto("al_destruir",        None,      _ALHandle)
_al_filas           = _proto("al_filas",           ctypes.c_int, _ALHandle)
_al_columnas        = _proto("al_columnas",        ctypes.c_int, _ALHandle)
_al_obtener_datos   = _proto("al_obtener_datos",   None,      _ALHandle, _Dp)
_al_imprimir        = _proto("al_imprimir",        None,      _ALHandle, ctypes.c_int)
_al_leer_csv        = _proto("al_leer_csv",        _ALHandle, ctypes.c_char_p, ctypes.c_char)
_al_escribir_csv    = _proto("al_escribir_csv",    ctypes.c_int, _ALHandle, ctypes.c_char_p, ctypes.c_char)
_al_gauss           = _proto("al_gauss",           _ALHandle, _ALHandle)
_al_gauss_jordan    = _proto("al_gauss_jordan",    _ALHandle, _ALHandle)
_al_resolver_gauss  = _proto("al_resolver_gauss",  ctypes.c_int, _ALHandle, _Dp, _Dp)
_al_resolver_gj     = _proto("al_resolver_gauss_jordan", ctypes.c_int, _ALHandle, _Dp, _Dp)
_al_gauss_seidel    = _proto("al_gauss_seidel",    ctypes.c_int,
                              _ALHandle, _Dp, _Dp, ctypes.c_double, ctypes.c_int, _Dp)
_al_error_relativo  = _proto("al_error_relativo",  ctypes.c_double,
                              ctypes.c_double, ctypes.c_double)
_al_multiplicar     = _proto("al_multiplicar",     _ALHandle, _ALHandle, _ALHandle)
_al_sumar           = _proto("al_sumar",           _ALHandle, _ALHandle, _ALHandle)
_al_restar          = _proto("al_restar",          _ALHandle, _ALHandle, _ALHandle)
_al_hadamard        = _proto("al_hadamard",        _ALHandle, _ALHandle, _ALHandle)
_al_transpuesta     = _proto("al_transpuesta",     _ALHandle, _ALHandle)
_al_inversa         = _proto("al_inversa",         _ALHandle, _ALHandle)
_al_determinante    = _proto("al_determinante",    None, _ALHandle, _Dp)
_al_descomp_lu      = _proto("al_descomposicion_lu", ctypes.c_int, _ALHandle, _Dp, _Dp, _Dp)
_al_mult_pol        = _proto("al_multiplicar_polinomios", None,
                              _Dp, ctypes.c_int, _Dp, ctypes.c_int, _Dp)
_al_div_pol         = _proto("al_dividir_polinomios", None,
                              _Dp, ctypes.c_int, _Dp, ctypes.c_int, _Dp, _Ip, _Dp, _Ip)


# ── Helper arrays ─────────────────────────────────────────────────────────────
def _darray(data):
    """Convierte lista / ndarray a ctypes array de complejos."""
    flat = np.asarray(data, dtype=np.complex128).ravel()
    return flat.ctypes.data_as(_Dp), flat

def _dout(n):
    """Buffer de salida para n complejos."""
    arr = np.zeros(n, dtype=np.complex128)
    return arr, arr.ctypes.data_as(_Dp)


# ═══════════════════════════════════════════════════════════════════════════════
#  Clase AlgebraLineal (Python)
# ═══════════════════════════════════════════════════════════════════════════════
class AlgebraLineal:
    """
    Envuelve un puntero nativo AlgebraLineal C++ mediante ctypes.

    Parámetros de construcción aceptados:
        AlgebraLineal(array_2d)           – np.ndarray o lista de listas
        AlgebraLineal(filas=N, cols=M)    – matriz de ceros
    """

    def __init__(self, datos=None, *, filas: int = 0, cols: int = 0, _handle=None):
        if _handle is not None:
            # Construcción interna desde handle C ya creado
            self._h = _handle
        elif datos is not None:
            arr = np.asarray(datos, dtype=np.complex128)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            f, c = arr.shape
            ptr, _ = _darray(arr)
            self._h = _al_crear(ptr, f, c)
            if not self._h:
                raise ValueError("No se pudo crear AlgebraLineal desde los datos")
        elif filas > 0 and cols > 0:
            arr = np.zeros((filas, cols), dtype=np.complex128)
            ptr, _ = _darray(arr)
            self._h = _al_crear(ptr, filas, cols)
        else:
            raise ValueError("Proporciona datos, o filas= y cols=")

    def __del__(self):
        if hasattr(self, "_h") and self._h:
            _al_destruir(self._h)
            self._h = None

    # ── Propiedades ──────────────────────────────────────────────────────────
    @property
    def filas(self) -> int:
        return _al_filas(self._h)

    @property
    def columnas(self) -> int:
        return _al_columnas(self._h)

    @property
    def shape(self):
        return (self.filas, self.columnas)

    def to_numpy(self) -> np.ndarray:
        """Devuelve los datos como ndarray de NumPy."""
        n = self.filas * self.columnas
        buf, ptr = _dout(n)
        _al_obtener_datos(self._h, ptr)
        return buf.reshape(self.filas, self.columnas)

    def __repr__(self):
        return f"AlgebraLineal({self.filas}×{self.columnas})\n{self.to_numpy()}"

    # ── I/O ──────────────────────────────────────────────────────────────────
    def imprimir(self, decimales: int = 6):
        _al_imprimir(self._h, decimales)

    @classmethod
    def desde_csv(cls, ruta: str, delimitador: str = ",") -> "AlgebraLineal":
        """Lee una matriz desde un archivo CSV (soporta archivos grandes)."""
        h = _al_leer_csv(ruta.encode(), delimitador.encode()[0])
        if not h:
            raise IOError(f"No se pudo leer CSV: {ruta}")
        return cls(_handle=h)

    def a_csv(self, ruta: str, delimitador: str = ",") -> bool:
        """Escribe la matriz a un archivo CSV."""
        ok = _al_escribir_csv(self._h, ruta.encode(), delimitador.encode()[0])
        return bool(ok)

    # ── Métodos numéricos ────────────────────────────────────────────────────
    def gauss(self) -> "AlgebraLineal":
        """Eliminación Gaussiana → triangular superior."""
        h = _al_gauss(self._h)
        if not h: raise RuntimeError("Fallo en Gauss")
        return AlgebraLineal(_handle=h)

    def gauss_jordan(self) -> "AlgebraLineal":
        """Gauss-Jordan → forma escalonada reducida (RREF)."""
        h = _al_gauss_jordan(self._h)
        if not h: raise RuntimeError("Fallo en Gauss-Jordan")
        return AlgebraLineal(_handle=h)

    def resolver(self, b, metodo: str = "gauss") -> np.ndarray:
        """
        Resuelve Ax = b.
        metodo: 'gauss' | 'gauss_jordan'
        """
        bv = np.asarray(b, dtype=np.complex128)
        bptr, _ = _darray(bv)
        xbuf, xptr = _dout(self.filas)
        if metodo == "gauss":
            ok = _al_resolver_gauss(self._h, bptr, xptr)
        elif metodo in ("gauss_jordan", "gaussjordan"):
            ok = _al_resolver_gj(self._h, bptr, xptr)
        else:
            raise ValueError(f"Metodo desconocido: {metodo}")
        if not ok:
            raise RuntimeError(f"No se pudo resolver con {metodo}")
        return xbuf

    def gauss_seidel(
        self,
        b,
        x0=None,
        tolerancia: float = 1e-7,
        max_iter: int = 10000,
    ) -> np.ndarray:
        """Método iterativo Gauss-Seidel."""
        n = self.filas
        bv = np.asarray(b, dtype=np.complex128)
        x0v = np.zeros(n, dtype=np.complex128) if x0 is None else np.asarray(x0, dtype=np.complex128)
        bptr, _ = _darray(bv)
        x0ptr, _ = _darray(x0v)
        xbuf, xptr = _dout(n)
        ok = _al_gauss_seidel(self._h, bptr, x0ptr, tolerancia, max_iter, xptr)
        if not ok:
            raise RuntimeError("Fallo en Gauss-Seidel")
        return xbuf

    # ── Utilidades numéricas ─────────────────────────────────────────────────
    @staticmethod
    def error_relativo(valor_nuevo, valor_anterior) -> float:
        """Retorna error relativo porcentual."""
        nv = complex(valor_nuevo)
        av = complex(valor_anterior)
        denom = abs(nv)
        if denom < 1e-14:
            denom = 1.0
        return abs((nv - av) / denom) * 100.0

    @staticmethod
    def errores_relativos(nuevo, anterior) -> np.ndarray:
        """Error relativo vectorial (%)."""
        n = np.asarray(nuevo, dtype=np.complex128)
        a = np.asarray(anterior, dtype=np.complex128)
        return np.array([AlgebraLineal.error_relativo(ni, ai) for ni, ai in zip(n, a)])

    # ── Operaciones matriciales ──────────────────────────────────────────────
    def __matmul__(self, otro: "AlgebraLineal") -> "AlgebraLineal":
        return self.multiplicar(otro)

    def multiplicar(self, otro: "AlgebraLineal") -> "AlgebraLineal":
        h = _al_multiplicar(self._h, otro._h)
        if not h: raise RuntimeError("Fallo en multiplicacion")
        return AlgebraLineal(_handle=h)

    def __add__(self, otro: "AlgebraLineal") -> "AlgebraLineal":
        h = _al_sumar(self._h, otro._h)
        if not h: raise RuntimeError("Fallo en suma")
        return AlgebraLineal(_handle=h)

    def __sub__(self, otro: "AlgebraLineal") -> "AlgebraLineal":
        h = _al_restar(self._h, otro._h)
        if not h: raise RuntimeError("Fallo en resta")
        return AlgebraLineal(_handle=h)

    def hadamard(self, otro: "AlgebraLineal") -> "AlgebraLineal":
        """Producto elemento a elemento (Hadamard)."""
        h = _al_hadamard(self._h, otro._h)
        if not h: raise RuntimeError("Fallo en Hadamard")
        return AlgebraLineal(_handle=h)

    def transpuesta(self) -> "AlgebraLineal":
        h = _al_transpuesta(self._h)
        if not h: raise RuntimeError("Fallo en transpuesta")
        return AlgebraLineal(_handle=h)

    def inversa(self) -> "AlgebraLineal":
        h = _al_inversa(self._h)
        if not h: raise RuntimeError("Matriz singular o fallo en inversa")
        return AlgebraLineal(_handle=h)

    def determinante(self):
        buf, ptr = _dout(1)
        _al_determinante(self._h, ptr)
        return buf[0]

    def descomposicion_lu(self):
        """
        Descomposición PA = LU con pivoteo parcial.
        Retorna (L, U, P) como objetos AlgebraLineal.
        """
        n = self.filas
        Lb, Lp = _dout(n * n)
        Ub, Up = _dout(n * n)
        Pb, Pp = _dout(n * n)
        ok = _al_descomp_lu(self._h, Lp, Up, Pp)
        if not ok:
            raise RuntimeError("Fallo en descomposicion LU")
        L = AlgebraLineal(Lb.reshape(n, n))
        U = AlgebraLineal(Ub.reshape(n, n))
        P = AlgebraLineal(Pb.reshape(n, n))
        return L, U, P

    # ── Polinomios ────────────────────────────────────────────────────────────
    @staticmethod
    def multiplicar_polinomios(p, q) -> np.ndarray:
        """
        Multiplica dos polinomios representados como listas de coeficientes
        [a0, a1, ..., an]  (índice = grado).
        """
        pv = np.asarray(p, dtype=np.complex128)
        qv = np.asarray(q, dtype=np.complex128)
        rlen = len(pv) + len(qv) - 1
        rbuf, rptr = _dout(rlen)
        pp, _ = _darray(pv)
        qp, _ = _darray(qv)
        _al_mult_pol(pp, len(pv), qp, len(qv), rptr)
        return rbuf

    @staticmethod
    def dividir_polinomios(dividendo, divisor):
        """
        División larga de polinomios.
        Retorna (cociente, residuo) como ndarray.
        """
        dv = np.asarray(dividendo, dtype=np.complex128)
        sv = np.asarray(divisor,   dtype=np.complex128)
        max_coc = len(dv)
        max_res = len(sv)
        cbuf, cptr = _dout(max_coc)
        rbuf, rptr = _dout(max_res)
        cl = ctypes.c_int(0)
        rl = ctypes.c_int(0)
        dp, _ = _darray(dv)
        sp, _ = _darray(sv)
        _al_div_pol(dp, len(dv), sp, len(sv), cptr, ctypes.byref(cl), rptr, ctypes.byref(rl))
        return cbuf[:cl.value], rbuf[:rl.value]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Herramienta de Álgebra Lineal: resolver sistemas, operaciones matriciales y polinomios.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="comando", help="Comandos disponibles", required=True)

    # Subcomando: resolver
    parser_resolver = subparsers.add_parser("resolver", help="Resolver sistema Ax = b desde CSV")
    parser_resolver.add_argument("-f", "--file", required=True, help="Archivo CSV con el sistema")
    parser_resolver.add_argument("-m", "--method", choices=["gauss", "gauss_jordan", "gauss_seidel"],
                                  default="gauss", help="Método de resolución")
    parser_resolver.add_argument("--x0", nargs="*", type=float, help="Valores iniciales para Gauss-Seidel (opcional)")
    parser_resolver.add_argument("--tol", type=float, default=1e-7, help="Tolerancia para Gauss-Seidel")
    parser_resolver.add_argument("--max_iter", type=int, default=10000, help="Máx iteraciones para Gauss-Seidel")

    # Subcomando: crear
    parser_crear = subparsers.add_parser("crear", help="Crear matriz manualmente desde consola")
    parser_crear.add_argument("--filas", type=int, required=True, help="Número de filas")
    parser_crear.add_argument("--columnas", type=int, required=True, help="Número de columnas")
    parser_crear.add_argument("--valores", nargs="*", type=float, help="Valores fila por fila (opcional, si no se da, se pide interactivamente)")
    parser_crear.add_argument("-o", "--output", help="Archivo CSV para guardar la matriz creada (opcional)")

    # Subcomando: imprimir
    parser_imprimir = subparsers.add_parser("imprimir", help="Imprimir matriz desde CSV")
    parser_imprimir.add_argument("-f", "--file", required=True, help="Archivo CSV")
    parser_imprimir.add_argument("--decimales", type=int, default=6, help="Decimales a mostrar")

    # Subcomando: guardar
    parser_guardar = subparsers.add_parser("guardar", help="Guardar matriz a CSV")
    parser_guardar.add_argument("-f", "--file", required=True, help="Archivo CSV de entrada")
    parser_guardar.add_argument("-o", "--output", required=True, help="Archivo CSV de salida")

    # Subcomando: operar
    parser_operar = subparsers.add_parser("operar", help="Operaciones binarias entre matrices")
    parser_operar.add_argument("-a", "--file_a", required=True, help="Archivo CSV de matriz A")
    parser_operar.add_argument("-b", "--file_b", required=True, help="Archivo CSV de matriz B")
    parser_operar.add_argument("--op", choices=["sumar", "restar", "multiplicar", "hadamard"], required=True, help="Operación")

    # Subcomando: unaria
    parser_unaria = subparsers.add_parser("unaria", help="Operaciones unarias en matriz")
    parser_unaria.add_argument("-f", "--file", required=True, help="Archivo CSV de la matriz")
    parser_unaria.add_argument("--op", choices=["transpuesta", "inversa", "determinante", "lu"], required=True, help="Operación")

    # Subcomando: polinomios
    parser_poli = subparsers.add_parser("polinomios", help="Operaciones con polinomios")
    parser_poli.add_argument("--p", nargs="*", type=float, required=True, help="Coeficientes de polinomio P (grado ascendente)")
    parser_poli.add_argument("--q", nargs="*", type=float, help="Coeficientes de polinomio Q (para multiplicar/dividir)")
    parser_poli.add_argument("--op", choices=["multiplicar", "dividir"], required=True, help="Operación")

    args = parser.parse_args()

    try:
        if args.comando == "resolver":
            mat = AlgebraLineal.desde_csv(args.file)
            filas, columnas = mat.shape
            if columnas < 2:
                raise ValueError("El CSV debe tener al menos 2 columnas.")
            n = filas
            m = columnas - 1
            if m != n:
                raise ValueError(f"No cuadrada: {n} ecuaciones, {m} variables.")
            datos = mat.to_numpy()
            A_datos = datos[:, :-1]
            b = datos[:, -1]
            A = AlgebraLineal(A_datos)
            if args.method in ["gauss", "gauss_jordan"]:
                x = A.resolver(b, metodo=args.method.replace("_", "_"))
            elif args.method == "gauss_seidel":
                x0 = args.x0 if args.x0 else [0.0] * n
                x = A.gauss_seidel(b, x0=x0, tolerancia=args.tol, max_iter=args.max_iter)
            print(f"Solución con {args.method}:")
            for i, val in enumerate(x, 1):
                print(f"  x{i} = {val:.6f}")

        elif args.comando == "crear":
            filas = args.filas
            columnas = args.columnas
            if args.valores:
                if len(args.valores) != filas * columnas:
                    raise ValueError("Número de valores no coincide con filas*columnas.")
                datos = np.array(args.valores).reshape(filas, columnas)
            else:
                print(f"Ingrese los valores para una matriz de {filas}x{columnas} fila por fila:")
                datos = []
                for i in range(filas):
                    fila = []
                    for j in range(columnas):
                        while True:
                            try:
                                val = float(input(f"  Fila {i}, Columna {j}: "))
                                fila.append(val)
                                break
                            except ValueError:
                                print("Valor inválido, intente de nuevo.")
                    datos.append(fila)
                datos = np.array(datos)
            mat = AlgebraLineal(datos)
            print("Matriz creada:")
            print(mat)
            if args.output:
                mat.a_csv(args.output)
                print(f"Matriz guardada en {args.output}")

        elif args.comando == "imprimir":
            mat = AlgebraLineal.desde_csv(args.file)
            mat.imprimir(args.decimales)

        elif args.comando == "guardar":
            mat = AlgebraLineal.desde_csv(args.file)
            mat.a_csv(args.output)
            print(f"Guardado en {args.output}")

        elif args.comando == "operar":
            A = AlgebraLineal.desde_csv(args.file_a)
            B = AlgebraLineal.desde_csv(args.file_b)
            if args.op == "sumar":
                res = A + B
            elif args.op == "restar":
                res = A - B
            elif args.op == "multiplicar":
                res = A * B
            elif args.op == "hadamard":
                res = A.hadamard(B)
            print(f"Resultado de {args.op}:")
            print(res)

        elif args.comando == "unaria":
            mat = AlgebraLineal.desde_csv(args.file)
            if args.op == "transpuesta":
                res = mat.transpuesta()
                print("Transpuesta:")
                print(res)
            elif args.op == "inversa":
                res = mat.inversa()
                print("Inversa:")
                print(res)
            elif args.op == "determinante":
                det = mat.determinante()
                print(f"Determinante: {det}")
            elif args.op == "lu":
                L, U, P = mat.descomposicion_lu()
                print("L:")
                print(L)
                print("U:")
                print(U)
                print("P:")
                print(P)

        elif args.comando == "polinomios":
            if args.op == "multiplicar":
                if not args.q:
                    raise ValueError("Se necesita --q para multiplicar.")
                res = AlgebraLineal.multiplicar_polinomios(args.p, args.q)
                print(f"Producto: {res}")
            elif args.op == "dividir":
                if not args.q:
                    raise ValueError("Se necesita --q para dividir.")
                coc, res = AlgebraLineal.dividir_polinomios(args.p, args.q)
                print(f"Cociente: {coc}, Residuo: {res}")

    except Exception as e:
        print(f"Error: {e}")
        exit(1)
