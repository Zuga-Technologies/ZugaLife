#!/usr/bin/env bash
#
# ZugaLife Setup — one command to get running.
#
# Usage: bash setup.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo "=== ZugaLife Setup ==="
echo ""

# ── 1. Git submodule (ZugaCore) ──────────────────────────────────────
echo "[1/5] Initializing ZugaCore submodule..."
git submodule update --init --recursive
echo "  Done."
echo ""

# ── 2. Backend symlinks ──────────────────────────────────────────────
echo "[2/5] Creating backend symlinks to ZugaCore..."
BACKEND_CORE="$REPO_DIR/backend/core"
mkdir -p "$BACKEND_CORE"

create_link() {
    local target="$1"
    local link="$2"
    local name="$(basename "$link")"

    # Remove existing (broken symlink, file, or directory)
    if [ -L "$link" ] || [ -e "$link" ]; then
        rm -rf "$link"
    fi

    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        # Windows: use cmd mklink /d for directory symlinks
        local win_target win_link
        win_target="$(cygpath -w "$target")"
        win_link="$(cygpath -w "$link")"
        cmd //c "mklink /d \"$win_link\" \"$win_target\"" > /dev/null
    else
        ln -s "$target" "$link"
    fi
    echo "  $name -> $target"
}

CORE_DIR="$REPO_DIR/core"
create_link "$CORE_DIR/auth"     "$BACKEND_CORE/auth"
create_link "$CORE_DIR/database" "$BACKEND_CORE/database"
create_link "$CORE_DIR/plugins"  "$BACKEND_CORE/plugins"
create_link "$CORE_DIR/credits"  "$BACKEND_CORE/credits"

# Ensure __init__.py exists
touch "$BACKEND_CORE/__init__.py"
echo ""

# ── 3. Python dependencies ───────────────────────────────────────────
echo "[3/5] Installing Python dependencies..."
if command -v pip &> /dev/null; then
    pip install -r backend/requirements.txt -q
    echo "  Done."
else
    echo "  WARNING: pip not found. Install Python 3.10+ and run:"
    echo "    pip install -r backend/requirements.txt"
fi
echo ""

# ── 4. Frontend dependencies ─────────────────────────────────────────
echo "[4/5] Installing frontend dependencies..."
if command -v npm &> /dev/null; then
    (cd frontend && npm install --silent)
    echo "  Done."
else
    echo "  WARNING: npm not found. Install Node.js 18+ and run:"
    echo "    cd frontend && npm install"
fi
echo ""

# ── 5. Environment file ──────────────────────────────────────────────
echo "[5/5] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from .env.example"
    echo "  (Optional) Add your VENICE_API_KEY for AI features."
else
    echo "  .env already exists — skipping."
fi
echo ""

echo "=== Setup complete! ==="
echo ""
echo "  Start the app:  bash start.sh"
echo "  Then open:       http://localhost:5174"
echo ""
