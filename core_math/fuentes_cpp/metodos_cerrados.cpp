//Fernando José Padilla Cruz - PC24039
#include <iostream>
#include <cmath>

extern "C" {
    // Definimos un tipo para los punteros a funciones de Python
    typedef double (*FuncPtr)(double);

    // 1. Método de Bisección
    double biseccion(FuncPtr f, double a, double b, double tol, int max_iter, int* iteraciones) {
        *iteraciones = 0;
        if (f(a) * f(b) >= 0) {
            std::cerr << "El intervalo no contiene una raiz." << std::endl;
            return NAN;
        }
        double c = a;
        for (int i = 0; i < max_iter; ++i) {
            c = (a + b) / 2.0;
            if (f(c) == 0.0 || (b - a) / 2.0 < tol) return c;
            if (f(c) * f(a) < 0) b = c;
            else a = c;
            (*iteraciones)++;
        }
        return c;
    }

    // 2. Método de Falsa Posición
    double falsa_posicion(FuncPtr f, double a, double b, double tol, int max_iter, int* iteraciones) {
        *iteraciones = 0;
        if (f(a) * f(b) >= 0) {
            std::cerr << "El intervalo no contiene una raiz." << std::endl;
            return NAN;
        }
        double c = a;
        for (int i = 0; i < max_iter; ++i) {
            c = (a * f(b) - b * f(a)) / (f(b) - f(a));
            if (std::abs(f(c)) < tol) return c;
            if (f(c) * f(a) < 0) b = c;
            else a = c;
            (*iteraciones)++;
        }
        return c;
    }

    // 3. Método de Newton-Raphson
    // Nota: Requiere la derivada df
    double newton_raphson(FuncPtr f, FuncPtr df, double p0, double tol, int max_iter, int* iteraciones) {
        *iteraciones = 0;
        double p;
        for (int i = 0; i < max_iter; ++i) {
            double fp = f(p0);
            double dfp = df(p0);
            if (dfp == 0) {
                std::cerr << "Derivada cero." << std::endl;
                return NAN;
            }
            p = p0 - fp / dfp;
            if (std::abs(p - p0) < tol) return p;
            p0 = p;
            (*iteraciones)++;
        }
        return p;
    }

    // 4. Método de la Secante
    double secante(FuncPtr f, double p0, double p1, double tol, int max_iter, int* iteraciones) {
        *iteraciones = 0;
        double p;
        for (int i = 0; i < max_iter; ++i) {
            double fp0 = f(p0);
            double fp1 = f(p1);
            if (fp1 - fp0 == 0) return NAN;
            p = p1 - fp1 * (p1 - p0) / (fp1 - fp0);
            if (std::abs(p - p1) < tol) return p;
            p0 = p1;
            p1 = p;
            (*iteraciones)++;
        }
        return p;
    }

    // 5. Método de Punto Fijo
    // Nota: g(x) debe estar definida de tal forma que g(x) = x
    double punto_fijo(FuncPtr g, double p0, double tol, int max_iter, int* iteraciones) {
        *iteraciones = 0;
        double p;
        for (int i = 0; i < max_iter; ++i) {
            p = g(p0);
            if (std::abs(p - p0) < tol) return p;
            p0 = p;
            (*iteraciones)++;
        }
        return p;
    }
}