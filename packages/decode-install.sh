#!/bin/sh
# Собирает архив установки из base64-частей и проверяет его целостность.
set -e
cd "$(dirname "$0")"
OUT="tiberium-0.2.0-install.zip"
B64="tiberium-0.2.0-install.zip.b64"

# Части лежат рядом: склеиваем их по порядку и декодируем.
cat "$B64".part* > "$B64.full"
base64 -d "$B64.full" > "$OUT"
rm -f "$B64.full"

python3 - "$OUT" "6a43946f42a3ea17d503a481f1f22a6fef0fc9241f43469553995df4c585e66f" <<'PYEOF'
import sys, zipfile, hashlib
data = open(sys.argv[1], "rb").read()
if hashlib.sha256(data).hexdigest() != sys.argv[2]:
    raise SystemExit("не совпадает sha256 архива")
z = zipfile.ZipFile(sys.argv[1])
bad = z.testzip()
if bad:
    raise SystemExit(f"битый файл в архиве: {bad}")
names = z.namelist()
need = ["horizon-mods/tiberium.hmod", "horizon-native-mods/tiberium-0.2.0.hnmod"]
missing = [n for n in need if n not in names]
if missing:
    raise SystemExit(f"в архиве нет: {missing}")
print("архив в порядке, sha256 совпал:", ", ".join(names))
PYEOF
echo
echo "Распакуйте в папку Horizon (рядом с options.txt):"
echo "  unzip -o $OUT -d /путь/к/horizon/instance"
