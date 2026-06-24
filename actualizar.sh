#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# actualizar.sh  —  Descarga la última versión del código desde GitHub
#                   y (opcional) regenera los dashboards con tus datos.
#
# Uso:
#   chmod +x actualizar.sh   (solo la primera vez)
#   ./actualizar.sh
# ──────────────────────────────────────────────────────────────────────

set -e
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Actualizador — Análisis Climático y Fotovoltaico"
echo "════════════════════════════════════════════════════════════════"
echo ""

# ── 1. Verificar que git está disponible ─────────────────────────────
if ! command -v git &>/dev/null; then
  echo "  ✖  git no está instalado. Instálalo con:"
  echo "       sudo apt install git"
  exit 1
fi

# ── 2. Verificar que hay un remoto configurado ───────────────────────
if ! git remote get-url origin &>/dev/null; then
  echo "  ✖  No hay un remoto 'origin' configurado."
  echo "     Clona el repositorio primero:"
  echo "       git clone https://github.com/fernansaurio/analisis-climatico-fotovoltaico.git"
  exit 1
fi

# ── 3. Mostrar estado actual ─────────────────────────────────────────
RAMA=$(git branch --show-current 2>/dev/null || echo "master")
echo "  Rama actual : $RAMA"
echo "  Último commit local:"
git log --oneline -1 | sed 's/^/    /'
echo ""

# ── 4. Descargar cambios ─────────────────────────────────────────────
echo "  Descargando cambios desde GitHub..."
git fetch origin "$RAMA" 2>&1 | sed 's/^/    /'

CAMBIOS=$(git log HEAD..origin/"$RAMA" --oneline 2>/dev/null)
if [ -z "$CAMBIOS" ]; then
  echo ""
  echo "  ✅  Ya tienes la versión más reciente. Sin cambios."
else
  echo ""
  echo "  Cambios disponibles:"
  echo "$CAMBIOS" | sed 's/^/    • /'
  echo ""
  git pull origin "$RAMA" 2>&1 | sed 's/^/    /'
  echo ""
  echo "  ✅  Código actualizado correctamente."
fi

# ── 5. Preguntar si regenerar dashboards ─────────────────────────────
echo ""
echo "────────────────────────────────────────────────────────────────"
echo "  ¿Quieres regenerar los dashboards con tus datos locales?"
echo "  (Requiere tener datos en datos_crudos/ y Python instalado)"
echo ""
read -rp "  Regenerar ahora? [s/N]: " RESP

if [[ "$RESP" =~ ^[Ss]$ ]]; then
  echo ""
  python3 ejecutar_proyecto.py
else
  echo ""
  echo "  Para regenerar más tarde corre:"
  echo "    python3 ejecutar_proyecto.py"
  echo ""
fi

echo "════════════════════════════════════════════════════════════════"
echo ""
