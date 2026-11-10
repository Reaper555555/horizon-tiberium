#!/bin/sh
# Собе��ает архив установки из base64 и проверяет его целостность.
set -e
cd "$(dirname "$0")"
OUT="tiberium-0.2.0-install.zip"
base64 -d tiberium-0.2.0-install.zip.b64 > "$OUT"
python3 - "$OUT" <<'PYEOF'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
bad = z.testzip()
if bad:
    raise SystemExit(f"битый файл в архиве: {bad}")
names = z.namelist()
need = ["horizon-mods/tiberium.hmod", "horizon-native-mods/tiberium-0.2.0.hnmod"]
missing = [n for n in need if n not in names]
if missing:
    raise SystemExit(f"в архиве нет: {missing}")
print("архив в порядке:", ", ".join(names))
PYEOF
echo
echo "Распакуйте в папку Horizon (рядом с options.txt):"
echo "  unzip -o $OUT -d /путь/к/horizon/instance"
