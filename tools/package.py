#!/usr/bin/env python3
"""Готовит packages/ для раздачи: архив, base64-части и скрипт сборки.

Готовый архив нельзя залить в репозиторий напрямую (двоичные файлы
GitHub-инструмент принимает плохо), поэтому рядом лежат его base64-части
и скрипт decode-install.sh, который их склеивает и сверяет контрольную сумму.

    python3 tools/package.py
"""

import base64
import hashlib
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
PACKAGES = os.path.join(ROOT, "packages")
NAME = "tiberium-0.2.0-install.zip"
# Часть не больше 270 КБ: большие запросы GitHub-инструмент отклоняет.
PART_SIZE = 270000

SCRIPT = """#!/bin/sh
# Собирает архив установки из base64-частей и проверяет его целостность.
set -e
cd "$(dirname "$0")"
OUT="{name}"
B64="{name}.b64"

# Части лежат рядом: склеиваем их по порядку и декодируем.
cat "$B64".part* > "$B64.full"
base64 -d "$B64.full" > "$OUT"
rm -f "$B64.full"

python3 - "$OUT" "{sha}" <<'PYEOF'
import sys, zipfile, hashlib
data = open(sys.argv[1], "rb").read()
if hashlib.sha256(data).hexdigest() != sys.argv[2]:
    raise SystemExit("не совпадает sha256 архива")
z = zipfile.ZipFile(sys.argv[1])
bad = z.testzip()
if bad:
    raise SystemExit(f"битый файл в архиве: {{bad}}")
names = z.namelist()
need = ["horizon-mods/tiberium.hmod", "horizon-native-mods/tiberium-0.2.0.hnmod"]
missing = [n for n in need if n not in names]
if missing:
    raise SystemExit(f"в архиве нет: {{missing}}")
print("архив в порядке, sha256 совпал:", ", ".join(names))
PYEOF
echo
echo "Распакуйте в папку Horizon (рядом с options.txt):"
echo "  unzip -o $OUT -d /путь/к/horizon/instance"
"""


def main():
    src = os.path.join(DIST, NAME)
    if not os.path.exists(src):
        raise SystemExit("нет dist/%s: сначала python3 tools/build.py" % NAME)
    os.makedirs(PACKAGES, exist_ok=True)
    shutil.copyfile(src, os.path.join(PACKAGES, NAME))

    data = open(src, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    b64 = base64.b64encode(data).decode("ascii")

    for old in os.listdir(PACKAGES):
        if old.startswith(NAME + ".b64.part"):
            os.remove(os.path.join(PACKAGES, old))
    parts = [b64[i:i + PART_SIZE] for i in range(0, len(b64), PART_SIZE)]
    for i, part in enumerate(parts):
        with open(os.path.join(PACKAGES, "%s.b64.part%d" % (NAME, i)), "w", encoding="ascii") as fh:
            fh.write(part)

    script = os.path.join(PACKAGES, "decode-install.sh")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(SCRIPT.format(name=NAME, sha=sha))
    os.chmod(script, 0o755)

    print("архив:      packages/%s (%d байт)" % (NAME, len(data)))
    print("sha256:     %s" % sha)
    print("base64:     %d частей по %d байт" % (len(parts), PART_SIZE))
    print("скрипт:     packages/decode-install.sh")


if __name__ == "__main__":
    main()
