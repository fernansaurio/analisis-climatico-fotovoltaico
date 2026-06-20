#!/usr/bin/env bash
# publicar.sh — Regenera dashboards localmente y los sube a GitHub Pages
set -e

cd "$(dirname "$0")"

echo "=============================================="
echo "  PUBLICAR DASHBOARDS EN GITHUB PAGES"
echo "=============================================="

# 1. Regenerar (opcional — comentar si los HTML ya están actualizados)
if [[ "$1" != "--solo-push" ]]; then
  echo ""
  echo "▶  Regenerando dashboards con datos locales..."
  python3 ejecutar_proyecto.py
fi

# 2. Copiar a docs/ (fuente de GitHub Pages)
echo ""
echo "▶  Copiando a docs/..."
mkdir -p docs
cp dashboard/dashboard_msn_interactivo.html docs/
cp dashboard/dashboard_solar.html           docs/
cp dashboard/dashboard_fusion.html          docs/
cp dashboard/chart.umd.min.js               docs/
cp dashboard/uPlot.iife.min.js              docs/
cp dashboard/uPlot.min.css                  docs/

echo "   ✓  $(du -sh docs/*.html | awk '{print $1, $2}' | tr '\n' '  ')"

# 3. Commit y push
echo ""
echo "▶  Commiteando..."
git add docs/ \
        src/ \
        core_math/*.py \
        ejecutar_proyecto.py \
        reportes/ \
        claude.md \
        .gitignore \
        publicar.sh

FECHA=$(date '+%Y-%m-%d %H:%M')
git commit -m "dashboards $FECHA" 2>/dev/null || echo "   (sin cambios desde el último commit)"

echo ""
echo "▶  Haciendo push..."
git push origin master

echo ""
echo "=============================================="
echo "  LISTO"
echo "=============================================="
echo ""
echo "  GitHub Pages actualizará en ~1 minuto."
echo "  URL del sitio:"
REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$REMOTE" =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
  USUARIO="${BASH_REMATCH[1]}"
  REPO="${BASH_REMATCH[2]}"
  echo "  https://${USUARIO}.github.io/${REPO}/"
else
  echo "  https://TU_USUARIO.github.io/TU_REPO/"
fi
echo ""
echo "  Uso:"
echo "    ./publicar.sh              → regenerar + push"
echo "    ./publicar.sh --solo-push  → push sin regenerar"
echo "=============================================="
