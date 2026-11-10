#!/usr/bin/env python3
"""Заливает исходники мода в репозиторий пачками через GitHub-инструмент."""

import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER = "Reaper555555"
REPO = "horizon-tiberium"
BRANCH = "feat/v0.2.0"

INCLUDE_DIRS = [
    "content/data",
    "content/assets/tiberium/models/item",
    "content/assets/tiberium/items",
    "content/assets/tiberium/lang",
    "tools/typecheck",
]
# Модели блоков: только те, что сделаны руками. Остальные генерируются.
HAND_MODELS = [
    "content/assets/tiberium/models/block/sonic_pylon.json",
    "content/assets/tiberium/models/block/tainted_soil.json",
    "content/assets/tiberium/models/block/root_trace.json",
    "content/assets/tiberium/models/block/crystal_cluster.json",
]
INCLUDE_FILES = [
    "README.md",
    "CHANGELOG.md",
    ".gitignore",
    "content/horizon-mod.toml",
    "packages/decode-install.sh",
    "tools/gen_assets.py",
    "tools/build.py",
]
# Сгенерированные модели и текстуры не заливаем: их собирает gen_assets.py.
SKIP_DIRS = {"target", "__pycache__", "models", "blockstates", "textures", "dist"}


def collect():
    files = []
    for rel in INCLUDE_FILES:
        path = os.path.join(ROOT, rel)
        if os.path.exists(path):
            files.append(rel)
    for rel in HAND_MODELS:
        if os.path.exists(os.path.join(ROOT, rel)):
            files.append(rel)
    for d in INCLUDE_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dp, dirnames, names in os.walk(base):
            dirnames[:] = [n for n in dirnames if n not in SKIP_DIRS]
            for n in sorted(names):
                if n.endswith((".pyc",)):
                    continue
                full = os.path.join(dp, n)
                files.append(os.path.relpath(full, ROOT))
    return sorted(set(files))


def push(batch, message, attempts=3):
    payload = {
        "owner": OWNER,
        "repo": REPO,
        "branch": BRANCH,
        "message": message,
        "files": [
            {"path": p, "content": open(os.path.join(ROOT, p), encoding="utf-8").read()}
            for p in batch
        ],
    }
    args_path = os.path.join(ROOT, ".push-args.json")
    with open(args_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    for attempt in range(attempts):
        proc = subprocess.run(
            ["mcode-tools", "connector", "call", "connector__github__push_files",
             "--args-file", args_path],
            capture_output=True, text=True,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        plain = out.replace("\\", "")
        if proc.returncode == 0 and "connector_tool_error" not in out and '"ref"' in plain:
            break
        print(f"  попытка {attempt + 1} не удалась, жду и повторяю…")
        time.sleep(20 + attempt * 15)
    os.remove(args_path)
    if not (proc.returncode == 0 and "connector_tool_error" not in out and '"ref"' in plain):
        print("ОШИБКА заливки:", out[:1200])
        return False
    print(f"  залито {len(batch)} файлов: {batch[0]} … {batch[-1]}")
    return True


def main():
    files = collect()
    print(f"файлов к заливке: {len(files)}")
    size = sum(os.path.getsize(os.path.join(ROOT, p)) for p in files)
    print(f"общий объём: {size/1024:.0f} КБ")
    batch_size = 12
    ok = True
    for i in range(0, len(files), batch_size):
        batch = files[i:i + batch_size]
        msg = f"v0.2.0: исходники мода Tiberium ({batch[0]} … {batch[-1]})"
        if not push(batch, msg):
            ok = False
            break
        time.sleep(8)
    print("готово" if ok else "заливка прервана")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
