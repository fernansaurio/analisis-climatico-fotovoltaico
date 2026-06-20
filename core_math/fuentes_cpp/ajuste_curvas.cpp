#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <fstream>
#include <sstream>
#include <map>
#include <numeric>
#include <iomanip>

class AjusteCurvas {
private:
    std::vector<std::vector<double>> matriz;

public:
    AjusteCurvas() {}
    ~AjusteCurvas() {}

    // =============== MÉTODOS DE DATOS ===============

    bool leer_csv(const char* filename) {
        std::ios_base::sync_with_stdio(false);
        std::ifstream file(filename, std::ios::binary);
        if (!file.is_open()) return false;

        file.rdbuf()->pubsetbuf(nullptr, 1024 * 1024);
        matriz.clear();
        
        file.seekg(0, std::ios::end);
        std::streamsize file_size = file.tellg();
        file.seekg(0, std::ios::beg);
        int estimated_rows = std::max(100, (int)(file_size / 50));
        matriz.reserve(estimated_rows);

        std::string line;
        line.reserve(1024);

        while (std::getline(file, line)) {
            if (line.empty()) continue;

            std::vector<double> row;
            row.reserve(10);

            std::stringstream ss(line);
            std::string value;
            value.reserve(50);

            while (std::getline(ss, value, ',')) {
                size_t start = value.find_first_not_of(" \t\r\n");
                size_t end = value.find_last_not_of(" \t\r\n");
                if (start != std::string::npos) {
                    value = value.substr(start, end - start + 1);
                }
                if (!value.empty()) {
                    try {
                        row.push_back(std::stod(value));
                    } catch (...) {
                        file.close();
                        return false;
                    }
                }
            }
            if (!row.empty()) {
                matriz.push_back(row);
            }
            line.clear();
        }
        file.close();
        return !matriz.empty();
    }

    // =============== NUEVOS MÉTODOS PARA PMU_FDR ===============

    bool leer_csv_filtrado(const char* filename, const char* fecha_filtro, int col_fecha, int col_valor) {
        std::ios_base::sync_with_stdio(false);
        std::ifstream file(filename);
        if (!file.is_open()) return false;

        matriz.clear();
        std::string line;
        std::string fecha_str = fecha_filtro;

        while (std::getline(file, line)) {
            if (line.empty()) continue;

            std::stringstream ss(line);
            std::string value;
            std::vector<std::string> tokens;
            
            while (std::getline(ss, value, ',')) {
                tokens.push_back(value);
            }

            if (tokens.size() > std::max(col_fecha, col_valor)) {
                if (tokens[col_fecha].find(fecha_str) != std::string::npos) {
                    try {
                        std::vector<double> row;
                        row.push_back(std::stod(tokens[col_valor]));
                        matriz.push_back(row);
                    } catch (...) {
                        // Ignora errores y cabeceras
                    }
                }
            }
        }
        file.close();
        return !matriz.empty();
    }

    double desviacion_estandar_metodo3(int columna) {
        if (matriz.size() < 2 || columna >= (int)matriz[0].size()) return 0.0;
        
        double sum_y = 0.0;
        double sum_y2 = 0.0;
        double n = matriz.size();

        for (const auto& row : matriz) {
            double val = row[columna];
            sum_y += val;
            sum_y2 += (val * val);
        }

        double numerador = sum_y2 - ((sum_y * sum_y) / n);
        return std::sqrt(numerador / (n - 1));
    }

    double varianza_metodo3(int columna) {
        double s = desviacion_estandar_metodo3(columna);
        return s * s;
    }

    int contar_eventos_rango(int columna, double min_val, double max_val) {
        if (matriz.empty() || columna >= (int)matriz[0].size()) return 0;
        
        int conteo = 0;
        for (const auto& row : matriz) {
            double val = row[columna];
            if (val >= min_val && val <= max_val) {
                conteo++;
            }
        }
        return conteo;
    }

    // =============== MÉTODOS AUXILIARES Y ESTADÍSTICA ===============

    void escribir_csv(const char* filename) {
        std::ofstream file(filename);
        for (const auto& row : matriz) {
            for (size_t i = 0; i < row.size(); ++i) {
                file << row[i];
                if (i < row.size() - 1) file << ",";
            }
            file << "\n";
        }
        file.close();
    }

    void imprimir() {
        for (const auto& row : matriz) {
            for (double val : row) {
                std::cout << std::fixed << std::setprecision(6) << val << "\t";
            }
            std::cout << "\n";
        }
    }

    int obtener_filas() const {
        return matriz.size();
    }

    int obtener_columnas() const {
        return matriz.empty() ? 0 : matriz[0].size();
    }

    void establecer_matriz(double* datos, int filas, int columnas) {
        matriz.clear();
        for (int i = 0; i < filas; ++i) {
            std::vector<double> row;
            for (int j = 0; j < columnas; ++j) {
                row.push_back(datos[i * columnas + j]);
            }
            matriz.push_back(row);
        }
    }

    void obtener_matriz(double* datos, int filas, int columnas) {
        int idx = 0;
        for (int i = 0; i < filas; ++i) {
            for (int j = 0; j < columnas; ++j) {
                datos[idx++] = matriz[i][j];
            }
        }
    }

    double media(int columna) {
        if (matriz.empty() || columna >= (int)matriz[0].size()) return 0.0;
        double sum = 0.0;
        for (const auto& row : matriz) {
            sum += row[columna];
        }
        return sum / matriz.size();
    }

    double desviacion_estandar(int columna, bool con_media) {
        if (matriz.empty() || columna >= (int)matriz[0].size()) return 0.0;
        double med = con_media ? media(columna) : 0.0;
        double sum_sq_diff = 0.0;
        for (const auto& row : matriz) {
            double diff = row[columna] - med;
            sum_sq_diff += diff * diff;
        }
        return std::sqrt(sum_sq_diff / matriz.size());
    }

    double varianza(int columna) {
        double desv = desviacion_estandar(columna, true);
        return desv * desv;
    }

    double minimo(int columna) {
        if (matriz.empty() || columna >= (int)matriz[0].size()) return 0.0;
        double min_val = matriz[0][columna];
        for (const auto& row : matriz) {
            min_val = std::min(min_val, row[columna]);
        }
        return min_val;
    }

    double maximo(int columna) {
        if (matriz.empty() || columna >= (int)matriz[0].size()) return 0.0;
        double max_val = matriz[0][columna];
        for (const auto& row : matriz) {
            max_val = std::max(max_val, row[columna]);
        }
        return max_val;
    }

    double percentil(int columna, double p) {
        if (matriz.empty() || columna >= (int)matriz[0].size()) return 0.0;
        std::vector<double> col_data;
        for (const auto& row : matriz) {
            col_data.push_back(row[columna]);
        }
        std::sort(col_data.begin(), col_data.end());
        size_t idx = (size_t)((p / 100.0) * (col_data.size() - 1));
        return col_data[idx];
    }

    double mediana(int columna) {
        return percentil(columna, 50.0);
    }

    int buscar_valor(int columna, double valor) {
        for (size_t i = 0; i < matriz.size(); ++i) {
            if (columna < (int)matriz[i].size() && 
                std::abs(matriz[i][columna] - valor) < 1e-9) {
                return i;
            }
        }
        return -1;
    }

    void ordenar_por_columna(int columna, bool ascendente) {
        std::sort(matriz.begin(), matriz.end(),
                  [columna, ascendente](const std::vector<double>& a, 
                                        const std::vector<double>& b) {
                      if (ascendente)
                          return a[columna] < b[columna];
                      else
                          return a[columna] > b[columna];
                  });
    }

    double rango(int columna) {
        return maximo(columna) - minimo(columna);
    }

    double moda(int columna) {
        if (matriz.empty() || columna >= (int)matriz[0].size()) return 0.0;
        std::map<double, int> freq;
        for (const auto& row : matriz) {
            freq[row[columna]]++;
        }
        double moda_val = matriz[0][columna];
        int max_freq = 0;
        for (const auto& p : freq) {
            if (p.second > max_freq) {
                max_freq = p.second;
                moda_val = p.first;
            }
        }
        return moda_val;
    }

    double coeficiente_variacion(int columna) {
        double med = media(columna);
        if (std::abs(med) < 1e-9) return 0.0;
        return (desviacion_estandar(columna, true) / std::abs(med)) * 100.0;
    }

    double pearson_correlation(int col_x, int col_y) {
        if (matriz.size() < 2) return 0.0;
        double sum_x = 0.0, sum_y = 0.0, sum_xy = 0.0, sum_x2 = 0.0, sum_y2 = 0.0;
        int n = 0;
        for (const auto& row : matriz) {
            if (col_x >= (int)row.size() || col_y >= (int)row.size()) continue;
            double x = row[col_x];
            double y = row[col_y];
            if (std::isnan(x) || std::isnan(y)) continue;
            sum_x += x;
            sum_y += y;
            sum_xy += x * y;
            sum_x2 += x * x;
            sum_y2 += y * y;
            n++;
        }
        if (n < 2) return 0.0;
        double mean_x = sum_x / n;
        double mean_y = sum_y / n;
        double cov = (sum_xy - n * mean_x * mean_y) / (n - 1);
        double var_x = (sum_x2 - n * mean_x * mean_x) / (n - 1);
        double var_y = (sum_y2 - n * mean_y * mean_y) / (n - 1);
        if (var_x <= 0.0 || var_y <= 0.0) return 0.0;
        return cov / std::sqrt(var_x * var_y);
    }

    void diagrama_frecuencias(int columna, int num_bins, double* bins, int* frecuencias) {
        if (matriz.empty() || columna >= (int)matriz[0].size()) return;

        double min_val = minimo(columna);
        double max_val = maximo(columna);
        double bin_width = (max_val - min_val) / num_bins;

        for (int i = 0; i < num_bins; ++i) {
            bins[i] = min_val + i * bin_width;
            frecuencias[i] = 0;
        }

        for (const auto& row : matriz) {
            int bin_idx = (int)((row[columna] - min_val) / bin_width);
            if (bin_idx >= num_bins) bin_idx = num_bins - 1;
            if (bin_idx >= 0) frecuencias[bin_idx]++;
        }
    }

    void limpiar_datos(int columna, double min_val, double max_val) {
        matriz.erase(
            std::remove_if(matriz.begin(), matriz.end(),
                           [columna, min_val, max_val](const std::vector<double>& row) {
                               if (columna >= (int)row.size()) return true;
                               double val = row[columna];
                               return std::isnan(val) || val < min_val || val > max_val;
                           }),
            matriz.end());
    }

    void interpolar_linealmente(int columna) {
        if (matriz.size() < 2) return;

        for (size_t i = 0; i < matriz.size() - 1; ++i) {
            if (std::isnan(matriz[i][columna])) {
                size_t j = i + 1;
                while (j < matriz.size() && std::isnan(matriz[j][columna])) j++;

                if (i == 0 || j >= matriz.size()) {
                    continue;
                }

                double y1 = matriz[i - 1][columna];
                double y2 = matriz[j][columna];
                size_t gap = j - i + 1;
                for (size_t k = 1; k < gap; ++k) {
                    matriz[i + k - 1][columna] = y1 + (y2 - y1) * k / gap;
                }
            }
        }
    }

    // =============== MÉTODOS DE AJUSTE DE CURVAS ===============

    void regresion_lineal(int col_x, int col_y, double* coef) { 
        int n = matriz.size();
        double sum_x = 0, sum_y = 0, sum_xy = 0, sum_x2 = 0;
        for (const auto& row : matriz) {
            double x = row[col_x];
            double y = row[col_y];
            sum_x += x; sum_y += y; sum_xy += x * y; sum_x2 += x * x;
        }
        double denom = n * sum_x2 - sum_x * sum_x;
        if (std::abs(denom) < 1e-12) { coef[0] = 0; coef[1] = 0; return; }
        coef[1] = (n * sum_xy - sum_x * sum_y) / denom;
        coef[0] = (sum_y - coef[1] * sum_x) / n;
    }

    void regresion_potencial(int col_x, int col_y, double* coef) { 
        int n = 0;
        double sum_log_x = 0, sum_log_y = 0, sum_log_x_log_y = 0, sum_log_x2 = 0;
        for (const auto& row : matriz) {
            if (row[col_x] > 0 && row[col_y] > 0) {
                double log_x = std::log(row[col_x]);
                double log_y = std::log(row[col_y]);
                sum_log_x += log_x; sum_log_y += log_y;
                sum_log_x_log_y += log_x * log_y; sum_log_x2 += log_x * log_x;
                n++;
            }
        }
        if (n < 2) { coef[0] = 1; coef[1] = 1; return; }
        double denom = n * sum_log_x2 - sum_log_x * sum_log_x;
        if (std::abs(denom) < 1e-12) { coef[0] = 1; coef[1] = 1; return; }
        coef[1] = (n * sum_log_x_log_y - sum_log_x * sum_log_y) / denom;
        double log_a = (sum_log_y - coef[1] * sum_log_x) / n;
        coef[0] = std::exp(log_a);
    }

    void regresion_logaritmica(int col_x, int col_y, double* coef) {
        int n = 0;
        double sum_ln_x = 0, sum_y = 0, sum_ln_x_y = 0, sum_ln_x2 = 0;
        for (const auto& row : matriz) {
            if (row[col_x] > 0) {
                double ln_x = std::log(row[col_x]);
                double y = row[col_y];
                sum_ln_x += ln_x; sum_y += y; sum_ln_x_y += ln_x * y; sum_ln_x2 += ln_x * ln_x;
                n++;
            }
        }
        if (n < 2) { coef[0] = 0; coef[1] = 0; return; }
        double denom = n * sum_ln_x2 - sum_ln_x * sum_ln_x;
        if (std::abs(denom) < 1e-12) { coef[0] = 0; coef[1] = 0; return; }
        coef[1] = (n * sum_ln_x_y - sum_ln_x * sum_y) / denom;
        coef[0] = (sum_y - coef[1] * sum_ln_x) / n;
    }

    void regresion_exponencial(int col_x, int col_y, double* coef) {
        int n = 0;
        double sum_x = 0, sum_log_y = 0, sum_x_log_y = 0, sum_x2 = 0;
        for (const auto& row : matriz) {
            if (row[col_y] > 0) {
                double x = row[col_x];
                double log_y = std::log(row[col_y]);
                sum_x += x; sum_log_y += log_y; sum_x_log_y += x * log_y; sum_x2 += x * x;
                n++;
            }
        }
        if (n < 2) { coef[0] = 1; coef[1] = 0; return; }
        double denom = n * sum_x2 - sum_x * sum_x;
        if (std::abs(denom) < 1e-12) { coef[0] = 1; coef[1] = 0; return; }
        coef[1] = (n * sum_x_log_y - sum_x * sum_log_y) / denom;
        double log_a = (sum_log_y - coef[1] * sum_x) / n;
        coef[0] = std::exp(log_a);
    }

    void regresion_polinomial(int col_x, int col_y, int grado, double* coef) {
        int n = matriz.size();
        std::vector<std::vector<double>> A(grado + 1, std::vector<double>(grado + 2, 0));
        for (const auto& row : matriz) {
            double x = row[col_x];
            double y = row[col_y];
            double x_pow = 1.0;
            for (int i = 0; i <= grado; ++i) {
                for (int j = 0; j <= grado; ++j) { A[i][j] += x_pow * std::pow(x, j); }
                A[i][grado + 1] += x_pow * y;
                x_pow *= x;
            }
        }
        for (int i = 0; i <= grado; ++i) {
            int max_row = i;
            for (int k = i + 1; k <= grado; ++k) {
                if (std::abs(A[k][i]) > std::abs(A[max_row][i])) max_row = k;
            }
            std::swap(A[i], A[max_row]);
            for (int k = i + 1; k <= grado; ++k) {
                double c = A[k][i] / A[i][i];
                for (int j = i; j <= grado + 1; ++j) A[k][j] -= c * A[i][j];
            }
        }
        for (int i = grado; i >= 0; --i) {
            coef[i] = A[i][grado + 1];
            for (int j = i + 1; j <= grado; ++j) coef[i] -= A[i][j] * coef[j];
            coef[i] /= A[i][i];
        }
    }

    double interpolar_lineal(double x0, double y0, double x1, double y1, double x) {
        if (std::abs(x1 - x0) < 1e-12) return y0;
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0);
    }

    double interpolar_cuadratica(double x0, double y0, double x1, double y1, double x2, double y2, double x) {
        double L0 = ((x - x1) * (x - x2)) / ((x0 - x1) * (x0 - x2));
        double L1 = ((x - x0) * (x - x2)) / ((x1 - x0) * (x1 - x2));
        double L2 = ((x - x0) * (x - x1)) / ((x2 - x0) * (x2 - x1));
        return y0 * L0 + y1 * L1 + y2 * L2;
    }

    double interpolar_polinomial(double* x_vals, double* y_vals, int n, double x) {
        double result = 0.0;
        for (int i = 0; i < n; ++i) {
            double L = 1.0;
            for (int j = 0; j < n; ++j) {
                if (i != j) L *= (x - x_vals[j]) / (x_vals[i] - x_vals[j]);
            }
            result += y_vals[i] * L;
        }
        return result;
    }

    double spline_lineal(double* x_vals, double* y_vals, int n, double x) {
        for (int i = 0; i < n - 1; ++i) {
            if (x >= x_vals[i] && x <= x_vals[i + 1]) {
                return interpolar_lineal(x_vals[i], y_vals[i], x_vals[i + 1], y_vals[i + 1], x);
            }
        }
        return y_vals[0];
    }

    void spline_cuadratico(double* x_vals, double* y_vals, int n, double* a, double* b, double* c) {
        std::vector<double> h(n - 1);
        for (int i = 0; i < n - 1; ++i) h[i] = x_vals[i + 1] - x_vals[i];
        std::vector<std::vector<double>> A(n, std::vector<double>(n + 1, 0));
        for (int i = 0; i < n - 1; ++i) a[i] = y_vals[i];
        for (int i = 1; i < n - 1; ++i) {
            A[i][i - 1] = h[i - 1];
            A[i][i] = 2 * (h[i - 1] + h[i]);
            A[i][i + 1] = h[i];
            A[i][n] = 6 * ((y_vals[i + 1] - y_vals[i]) / h[i] - (y_vals[i] - y_vals[i - 1]) / h[i - 1]);
        }
        for (int i = 0; i < n - 1; ++i) {
            b[i] = 0;
            c[i] = (y_vals[i + 1] - y_vals[i]) / h[i];
        }
    }

    void spline_cubico(double* x_vals, double* y_vals, int n, double* a, double* b, double* c, double* d) {
        std::vector<double> h(n - 1);
        for (int i = 0; i < n - 1; ++i) h[i] = x_vals[i + 1] - x_vals[i];
        for (int i = 0; i < n - 1; ++i) a[i] = y_vals[i];
        std::vector<double> alpha(n);
        for (int i = 1; i < n - 1; ++i) {
            alpha[i] = (3.0 / h[i]) * (y_vals[i + 1] - y_vals[i]) - (3.0 / h[i - 1]) * (y_vals[i] - y_vals[i - 1]);
        }
        std::vector<double> l(n), mu(n), z(n);
        l[0] = 1; mu[0] = 0; z[0] = 0;
        for (int i = 1; i < n - 1; ++i) {
            l[i] = 2 * (x_vals[i + 1] - x_vals[i - 1]) - h[i - 1] * mu[i - 1];
            mu[i] = h[i] / l[i];
            z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i];
        }
        l[n - 1] = 1; z[n - 1] = 0;
        std::vector<double> coeff_c(n);
        coeff_c[n - 1] = 0;
        for (int j = n - 2; j >= 0; --j) {
            coeff_c[j] = z[j] - mu[j] * coeff_c[j + 1];
            b[j] = (y_vals[j + 1] - y_vals[j]) / h[j] - h[j] * (coeff_c[j + 1] + 2 * coeff_c[j]) / 3.0;
            d[j] = (coeff_c[j + 1] - coeff_c[j]) / (3.0 * h[j]);
        }
        for (int i = 0; i < n - 1; ++i) c[i] = coeff_c[i];
    }

    void evaluar_regresion_lineal(int col_x, int col_y, double* x_pred, double* y_pred, int n_pred) {
        double coef[2];
        regresion_lineal(col_x, col_y, coef);
        for (int i = 0; i < n_pred; ++i) y_pred[i] = coef[0] + coef[1] * x_pred[i];
    }

    void evaluar_regresion_potencial(int col_x, int col_y, double* x_pred, double* y_pred, int n_pred) {
        double coef[2];
        regresion_potencial(col_x, col_y, coef);
        for (int i = 0; i < n_pred; ++i) {
            if (x_pred[i] > 0) y_pred[i] = coef[0] * std::pow(x_pred[i], coef[1]);
            else y_pred[i] = 0;
        }
    }

    void evaluar_regresion_logaritmica(int col_x, int col_y, double* x_pred, double* y_pred, int n_pred) {
        double coef[2];
        regresion_logaritmica(col_x, col_y, coef);
        for (int i = 0; i < n_pred; ++i) {
            if (x_pred[i] > 0) y_pred[i] = coef[0] + coef[1] * std::log(x_pred[i]);
            else y_pred[i] = 0;
        }
    }

    void evaluar_regresion_exponencial(int col_x, int col_y, double* x_pred, double* y_pred, int n_pred) {
        double coef[2];
        regresion_exponencial(col_x, col_y, coef);
        for (int i = 0; i < n_pred; ++i) y_pred[i] = coef[0] * std::exp(coef[1] * x_pred[i]);
    }

    void evaluar_regresion_polinomial(int col_x, int col_y, int grado, double* x_pred, double* y_pred, int n_pred) {
        std::vector<double> coef(grado + 1);
        regresion_polinomial(col_x, col_y, grado, coef.data());
        for (int i = 0; i < n_pred; ++i) {
            y_pred[i] = 0;
            double x_pow = 1.0;
            for (int j = 0; j <= grado; ++j) {
                y_pred[i] += coef[j] * x_pow;
                x_pow *= x_pred[i];
            }
        }
    }

    double evaluar_spline_lineal(double* x_vals, double* y_vals, int n, double x) {
        return spline_lineal(x_vals, y_vals, n, x);
    }
};


// =============== INTERFAZ C ===============

extern "C" {

    double interpolar_polinomial(void* ptr, double* x_vals, double* y_vals, int n, double x) { 
        return ((AjusteCurvas*)ptr)->interpolar_polinomial(x_vals, y_vals, n, x); 
    }

    void* create_ajuste_curvas() { return new AjusteCurvas(); }
    void destroy_ajuste_curvas(void* ptr) { delete (AjusteCurvas*)ptr; }

    int leer_csv(void* ptr, const char* filename) { return ((AjusteCurvas*)ptr)->leer_csv(filename); }
    void escribir_csv(void* ptr, const char* filename) { ((AjusteCurvas*)ptr)->escribir_csv(filename); }
    void imprimir(void* ptr) { ((AjusteCurvas*)ptr)->imprimir(); }
    
    int obtener_filas(void* ptr) { return ((AjusteCurvas*)ptr)->obtener_filas(); }
    int obtener_columnas(void* ptr) { return ((AjusteCurvas*)ptr)->obtener_columnas(); }
    void establecer_matriz(void* ptr, double* datos, int filas, int columnas) { ((AjusteCurvas*)ptr)->establecer_matriz(datos, filas, columnas); }
    void obtener_matriz(void* ptr, double* datos, int filas, int columnas) { ((AjusteCurvas*)ptr)->obtener_matriz(datos, filas, columnas); }

    double media(void* ptr, int columna) { return ((AjusteCurvas*)ptr)->media(columna); }
    double desviacion_estandar(void* ptr, int columna, int con_media) { return ((AjusteCurvas*)ptr)->desviacion_estandar(columna, con_media != 0); }
    double varianza(void* ptr, int columna) { return ((AjusteCurvas*)ptr)->varianza(columna); }
    double minimo(void* ptr, int columna) { return ((AjusteCurvas*)ptr)->minimo(columna); }
    double maximo(void* ptr, int columna) { return ((AjusteCurvas*)ptr)->maximo(columna); }
    double percentil(void* ptr, int columna, double p) { return ((AjusteCurvas*)ptr)->percentil(columna, p); }
    double mediana(void* ptr, int columna) { return ((AjusteCurvas*)ptr)->mediana(columna); }
    
    int buscar_valor(void* ptr, int columna, double valor) { return ((AjusteCurvas*)ptr)->buscar_valor(columna, valor); }
    void ordenar_por_columna(void* ptr, int columna, int ascendente) { ((AjusteCurvas*)ptr)->ordenar_por_columna(columna, ascendente != 0); }
    double rango(void* ptr, int columna) { return ((AjusteCurvas*)ptr)->rango(columna); }
    double moda(void* ptr, int columna) { return ((AjusteCurvas*)ptr)->moda(columna); }
    double coeficiente_variacion(void* ptr, int columna) { return ((AjusteCurvas*)ptr)->coeficiente_variacion(columna); }

    void diagrama_frecuencias(void* ptr, int columna, int num_bins, double* bins, int* frecuencias) { ((AjusteCurvas*)ptr)->diagrama_frecuencias(columna, num_bins, bins, frecuencias); }
    void limpiar_datos(void* ptr, int columna, double min_val, double max_val) { ((AjusteCurvas*)ptr)->limpiar_datos(columna, min_val, max_val); }
    void interpolar_linealmente(void* ptr, int columna) { ((AjusteCurvas*)ptr)->interpolar_linealmente(columna); }

    void regresion_lineal(void* ptr, int col_x, int col_y, double* coef) { ((AjusteCurvas*)ptr)->regresion_lineal(col_x, col_y, coef); }
    void regresion_potencial(void* ptr, int col_x, int col_y, double* coef) { ((AjusteCurvas*)ptr)->regresion_potencial(col_x, col_y, coef); }
    void regresion_logaritmica(void* ptr, int col_x, int col_y, double* coef) { ((AjusteCurvas*)ptr)->regresion_logaritmica(col_x, col_y, coef); }
    void regresion_exponencial(void* ptr, int col_x, int col_y, double* coef) { ((AjusteCurvas*)ptr)->regresion_exponencial(col_x, col_y, coef); }
    void regresion_polinomial(void* ptr, int col_x, int col_y, int grado, double* coef) { ((AjusteCurvas*)ptr)->regresion_polinomial(col_x, col_y, grado, coef); }

    void evaluar_regresion_lineal(void* ptr, int col_x, int col_y, double* x_pred, double* y_pred, int n_pred) { ((AjusteCurvas*)ptr)->evaluar_regresion_lineal(col_x, col_y, x_pred, y_pred, n_pred); }
    void evaluar_regresion_potencial(void* ptr, int col_x, int col_y, double* x_pred, double* y_pred, int n_pred) { ((AjusteCurvas*)ptr)->evaluar_regresion_potencial(col_x, col_y, x_pred, y_pred, n_pred); }
    void evaluar_regresion_logaritmica(void* ptr, int col_x, int col_y, double* x_pred, double* y_pred, int n_pred) { ((AjusteCurvas*)ptr)->evaluar_regresion_logaritmica(col_x, col_y, x_pred, y_pred, n_pred); }
    void evaluar_regresion_exponencial(void* ptr, int col_x, int col_y, double* x_pred, double* y_pred, int n_pred) { ((AjusteCurvas*)ptr)->evaluar_regresion_exponencial(col_x, col_y, x_pred, y_pred, n_pred); }
    void evaluar_regresion_polinomial(void* ptr, int col_x, int col_y, int grado, double* x_pred, double* y_pred, int n_pred) { ((AjusteCurvas*)ptr)->evaluar_regresion_polinomial(col_x, col_y, grado, x_pred, y_pred, n_pred); }

    double spline_lineal(void* ptr, double* x_vals, double* y_vals, int n, double x) { return ((AjusteCurvas*)ptr)->spline_lineal(x_vals, y_vals, n, x); }
    void spline_cuadratico(void* ptr, double* x_vals, double* y_vals, int n, double* a, double* b, double* c) { ((AjusteCurvas*)ptr)->spline_cuadratico(x_vals, y_vals, n, a, b, c); }
    void spline_cubico(void* ptr, double* x_vals, double* y_vals, int n, double* a, double* b, double* c, double* d) { ((AjusteCurvas*)ptr)->spline_cubico(x_vals, y_vals, n, a, b, c, d); }
    double evaluar_spline_lineal(void* ptr, double* x_vals, double* y_vals, int n, double x) { return ((AjusteCurvas*)ptr)->evaluar_spline_lineal(x_vals, y_vals, n, x); }

    // --- NUEVOS ENLACES (CORRECTOS) ---
    int leer_csv_filtrado(void* ptr, const char* filename, const char* fecha_filtro, int col_fecha, int col_valor) {
        return ((AjusteCurvas*)ptr)->leer_csv_filtrado(filename, fecha_filtro, col_fecha, col_valor);
    }
    double desviacion_estandar_metodo3(void* ptr, int columna) {
        return ((AjusteCurvas*)ptr)->desviacion_estandar_metodo3(columna);
    }
    double varianza_metodo3(void* ptr, int columna) {
        return ((AjusteCurvas*)ptr)->varianza_metodo3(columna);
    }
    int contar_eventos_rango(void* ptr, int columna, double min_val, double max_val) {
        return ((AjusteCurvas*)ptr)->contar_eventos_rango(columna, min_val, max_val);
    }
    double pearson_correlation(void* ptr, int col_x, int col_y) {
        return ((AjusteCurvas*)ptr)->pearson_correlation(col_x, col_y);
    }
}