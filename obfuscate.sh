#!/bin/bash
#
# Ofuscare cod Python cu PyArmor.
# Transformă .py în bytecode criptat — codul sursă nu mai e vizibil.
#
# Utilizare:
#   bash obfuscate.sh           # ofusază toate .py (cu backup .py.bak)
#   bash obfuscate.sh --restore  # restaurează backup-ul (.py.bak → .py)
#
# Păstrăm neofuscate: license.py (rulează PRIMUL, înainte de PyArmor runtime)
# ==============================================================================

set -e
cd "$(dirname "$0")"

# Fișiere de ofuscat
FILES=(
    app.py
    detector.py
    camera.py
    camera_manager.py
    database.py
    jetson_profile.py
    logger_config.py
    notifier.py
    loophole_tunnel.py
)

# license.py NU se ofuscură — verifică codul de acces ÎNAINTE
# ca PyArmor să_poată_înlocui restul fișierelor.

if [ "$1" == "--restore" ]; then
    echo "🔄 Restaurăm fișierele originale din backup..."
    for f in "${FILES[@]}"; do
        if [ -f "${f}.bak" ]; then
            cp "${f}.bak" "$f"
            echo "  ✅ $f restaurat"
        fi
    done
    echo "✅ Restaurare completă."
    exit 0
fi

# Verifică pyarmor
if ! command -v pyarmor &>/dev/null; then
    echo "❌ PyArmor nu e instalat. Rulează: pip install pyarmor"
    exit 1
fi

echo "🛡️  Ofuscare cod cu PyArmor..."
echo "   Fișiere: ${#FILES[@]} .py"
echo ""

# Backup original + ofuscare
for f in "${FILES[@]}"; do
    if [ ! -f "$f" ]; then
        echo "  ⚠️  $f nu există — salt"
        continue
    fi
    # Backup original
    cp "$f" "${f}.bak"
    # Ofuscare (în loc — suprascrie fișierul)
    pyarmor gen -O /tmp/pyarmor_output "$f" 2>/dev/null
    if [ -f "/tmp/pyarmor_output/$f" ]; then
        cp "/tmp/pyarmor_output/$f" "$f"
        echo "  ✅ $f ofuscat"
    else
        echo "  ❌ $f eroare ofuscare"
        cp "${f}.bak" "$f"
    fi
done

# Curățare
rm -rf /tmp/pyarmor_output

echo ""
echo "✅ Ofuscare completă!"
echo "   - Codul sursă e acum illegibil (bytecode criptat AES)"
echo "   - Aplicația rămâne funcțională"
echo "   - Backup: *.py.bak (nu le pune pe Git)"
echo ""
echo "Pentru a restaura: bash obfuscate.sh --restore"
