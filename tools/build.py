#!/usr/bin/env python3
"""Сборка мода Tiberium: .hmod (контент) + .hnmod (нативный код) + install.zip.

Перед сборкой проверяет:
  * каждый вариант бло��стейта ссылается на существующую модель (иначе игра
    рисует «чёрно-фиолетовый» отсутствующий блок);
  * каждый вариант имеет модель — ни одна комбинация состояний не теряется;
  * все JSON валидны;
  * манифест нативного мода совпадает с API хуков закреплённого коммита Horizon;
  * именованные хуки бандла есть в каталоге Horizon нужной версии.
"""

import json
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")
NATIVE = os.path.join(ROOT, "native")
DIST = os.path.join(ROOT, "dist")
VERSION = "0.2.0"
ID = "tiberium"
HORIZON = "66f3981f522b24c250b21523a70080965b940424"
HOOKS_API = 411
MIXINS = "e8cd0aa38cffef49cb2e088ef716baa107148c02"

errors = []


def fail(msg):
    errors.append(msg)
    print("  ОШИБКА:", msg)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_json_tree(root):
    n = 0
    for dp, _, files in os.walk(root):
        for name in files:
            if name.endswith(".json"):
                path = os.path.join(dp, name)
                try:
                    read_json(path)
                    n += 1
                except Exception as e:
                    fail(f"{os.path.relpath(path, ROOT)}: битый JSON ({e})")
    return n


def model_path(ref, base):
    """tiberium:block/foo -> <base>/models/block/foo.json"""
    ns, rest = ref.split(":", 1)
    tier, path = rest.split("/", 1)
    return os.path.join(base, "assets", ns, "models", tier, path + ".json")


def check_blockstates(base):
    """Каждый вариант состояния обязан иметь модель, и каждая модель — быть на месте."""
    bs_dir = os.path.join(base, "assets", ID, "blockstates")
    total = 0
    for name in sorted(os.listdir(bs_dir)):
        if not name.endswith(".json"):
            continue
        data = read_json(os.path.join(bs_dir, name))
        refs = set()

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "model" and isinstance(v, str):
                        refs.add(v)
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(data)
        for ref in sorted(refs):
            if not os.path.exists(model_path(ref, base)):
                fail(f"{name}: модель {ref} отсутствует — будет «чёрно-фиолетовый» блок")
        total += len(refs)
    return total


def check_states(base):
    """Свойства блока и бло��стейт должны описывать один и тот же набор комбинаций."""
    block_dir = os.path.join(base, "data", ID, "horizon", "block")
    bs_dir = os.path.join(base, "assets", ID, "blockstates")
    for name in sorted(os.listdir(block_dir)):
        if not name.endswith(".json"):
            continue
        block = read_json(os.path.join(block_dir, name))
        props = block.get("state_properties", {})
        if not props:
            continue
        bs_path = os.path.join(bs_dir, name)
        if not os.path.exists(bs_path):
            fail(f"{name}: нет бло��стейта для блока со свойствами")
            continue
        variants = read_json(bs_path).get("variants", {})
        # Ключи сравниваем как множества пар (свойство, значение): порядок в ключе
        # для игры не важен.
        def key_set(key):
            return frozenset(tuple(p.split("=", 1)) for p in key.split(","))

        present = set()
        for key in variants:
            parts = dict(p.split("=", 1) for p in key.split(","))
            for pname, pval in parts.items():
                spec = props.get(pname)
                if spec is None:
                    fail(f"{name}: свойство {pname} не объявлено в блоке")
                elif pval not in spec["values"]:
                    fail(f"{name}: значение {pname}={pval} не входит в {spec['values']}")
            present.add(key_set(key))
        # полнота покрытия: все комбинации свойств должны иметь модель
        combos = [frozenset()]
        for pname, spec in props.items():
            combos = [c | {(pname, v)} for c in combos for v in spec["values"]]
        missing = [sorted(c) for c in combos if c not in present]
        if missing:
            fail(f"{name}: {len(missing)} комбинаций без модели, напр. {missing[:3]}")


def check_native():
    manifest = read_json(os.path.join(NATIVE, "horizon-native.json"))
    for key, want in (("horizon", HORIZON), ("mixins", MIXINS), ("hooks", HOOKS_API),
                      ("version", VERSION), ("id", ID)):
        if manifest.get(key) != want:
            fail(f"horizon-native.json: {key} = {manifest.get(key)!r}, ожидалось {want!r}")
    return manifest


def check_mixin_manifest():
    """Разбираем horizon-mixin.toml простым парсером: нам нужны hook/hook_version."""
    path = os.path.join(NATIVE, "mixins", ID, "horizon-mixin.toml")
    text = open(path, encoding="utf-8").read()
    hooks = []
    for block in text.split("[[injection]]")[1:]:
        hook = None
        version = None
        helper = None
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("hook ="):
                hook = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("hook_version ="):
                version = int(line.split("=", 1)[1].strip())
            elif line.startswith("helper ="):
                helper = line.split("=", 1)[1].strip().strip('"')
        if hook:
            hooks.append((hook, version, helper))
    if not hooks:
        fail("horizon-mixin.toml: не найдено ни одного именованного хука")
    return hooks


def check_hook_catalog(hooks):
    """Именованные хуки должны существовать в native-hooks.json закреплённого коммита."""
    catalog_path = os.path.join(ROOT, "..", "horizon-src", "native-hooks.json")
    if not os.path.exists(catalog_path):
        print("  (каталог хуков Horizon недоступен — проверка пропущена)")
        return
    catalog = read_json(catalog_path)
    known = {}
    for h in catalog.get("hooks", []):
        known.setdefault(h["name"], set()).add(h.get("version"))
    for hook, version, _helper in hooks:
        if hook not in known:
            fail(f"хука {hook!r} нет в каталоге Horizon")
        elif version not in known[hook]:
            fail(f"хука {hook!r}: версии {version} нет, есть {sorted(known[hook])}")


def check_textures(base):
    """Каждая текстура, на которую ссылается модель, должна существовать."""
    models_root = os.path.join(base, "assets")
    missing = 0
    refs = 0
    for dp, _, files in os.walk(models_root):
        for name in files:
            if not name.endswith(".json"):
                continue
            path = os.path.join(dp, name)
            try:
                data = read_json(path)
            except Exception:
                continue
            tex = data.get("textures", {})
            if not isinstance(tex, dict):
                continue
            for value in tex.values():
                if not isinstance(value, str) or value.startswith("#"):
                    continue
                if ":" not in value:
                    continue
                ns, rest = value.split(":", 1)
                tier, tex_path = rest.split("/", 1)
                png = os.path.join(models_root, ns, "textures", tier, tex_path + ".png")
                refs += 1
                if not os.path.exists(png):
                    fail(f"{os.path.relpath(path, base)}: нет текстуры {value}")
                    missing += 1
    return refs, missing


def check_creative_tabs(base):
    """Каждый предмет во вкладке креатива должен доходить до текстуры.

    Цепочка: определение (блок или предмет) -> assets/items/<name>.json ->
    models/item/<name>.json -> текстура. Обрыв в любом месте означает, что
    в игре вместо иконки будет пустота.
    """
    data_root = os.path.join(base, "data")
    assets_root = os.path.join(base, "assets")
    checked = 0
    for dp, _, files in os.walk(data_root):
        if "creative_tab" not in dp.replace(os.sep, "/"):
            continue
        for name in files:
            if not name.endswith(".json"):
                continue
            path = os.path.join(dp, name)
            try:
                tab = read_json(path)
            except Exception:
                continue
            for item in tab.get("items", []):
                checked += 1
                if ":" not in item:
                    fail(f"{os.path.relpath(path, base)}: непонятный предмет {item}")
                    continue
                ns, name = item.split(":", 1)
                has_block = os.path.exists(
                    os.path.join(data_root, ns, "horizon", "block", name + ".json")
                )
                has_item = os.path.exists(
                    os.path.join(data_root, ns, "horizon", "item", name + ".json")
                )
                if not (has_block or has_item):
                    fail(f"{item}: нет ни блока, ни предмета с таким id")
                    continue
                pointer = os.path.join(assets_root, ns, "items", name + ".json")
                if not os.path.exists(pointer):
                    fail(f"{item}: нет указателя модели assets/items/{name}.json")
                    continue
                try:
                    model_id = read_json(pointer)["model"]["model"]
                except Exception:
                    fail(f"{item}: указатель модели битый")
                    continue
                parts = model_id.split(":")
                model_path = os.path.join(assets_root, parts[0], "models", *parts[1].split("/"))
                model_path += ".json"
                if not os.path.exists(model_path):
                    fail(f"{item}: нет модели {model_id}")
                    continue
                try:
                    model = read_json(model_path)
                except Exception:
                    fail(f"{item}: модель {model_id} битая")
                    continue
                textures = model.get("textures", {})
                if not textures:
                    # Иконка может быть блочной моделью: идём по родителю.
                    parent = model.get("parent")
                    if not parent or ":" not in parent:
                        fail(f"{item}: у модели {model_id} нет ни текстур, ни родителя")
                        continue
                    parts = parent.split(":")
                    parent_path = os.path.join(
                        assets_root, parts[0], "models", *parts[1].split("/")
                    ) + ".json"
                    if not os.path.exists(parent_path):
                        fail(f"{item}: нет родителя {parent}")
                        continue
                    try:
                        textures = read_json(parent_path).get("textures", {})
                    except Exception:
                        textures = {}
                    if not textures:
                        fail(f"{item}: ни модель {model_id}, ни её родитель {parent} "
                             "не содержат текстур")
                        continue
                for value in textures.values():
                    if not isinstance(value, str) or ":" not in value or value.startswith("#"):
                        continue
                    ns2, rest = value.split(":", 1)
                    tier, tail = rest.split("/", 1)
                    png = os.path.join(assets_root, ns2, "textures", tier, tail + ".png")
                    if not os.path.exists(png):
                        fail(f"{item}: нет текстуры {value}")
    return checked


def check_png(base):
    """PNG должны быть целыми: сигнатура, CRC чанков и длина данных картинки.

    Игра не показывает битую текстуру, а рисует «отсутствующую» (магента),
    поэтому сломанный PNG видно только в игре. Здесь это ловится сразу.
    """
    import struct
    import zlib

    tex_root = os.path.join(base, "assets")
    count = 0
    for dp, _, files in os.walk(tex_root):
        for name in files:
            if not name.endswith(".png"):
                continue
            path = os.path.join(dp, name)
            rel = os.path.relpath(path, base)
            count += 1
            data = open(path, "rb").read()
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                fail(f"{rel}: не PNG")
                continue
            pos = 8
            idat = b""
            ihdr = None
            while pos + 8 <= len(data):
                length = struct.unpack(">I", data[pos : pos + 4])[0]
                tag = data[pos + 4 : pos + 8]
                body = data[pos + 8 : pos + 8 + length]
                crc = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])[0]
                if zlib.crc32(tag + body) & 0xFFFFFFFF != crc:
                    fail(f"{rel}: битый CRC чанка {tag.decode(errors='replace')}")
                if tag == b"IHDR":
                    ihdr = struct.unpack(">IIBBBBB", body)
                elif tag == b"IDAT":
                    idat += body
                pos += 12 + length
                if tag == b"IEND":
                    break
            if ihdr is None:
                fail(f"{rel}: нет заголовка IHDR")
                continue
            width, height, depth, colour = ihdr[0], ihdr[1], ihdr[2], ihdr[3]
            if depth != 8 or colour != 6:
                fail(f"{rel}: ожидался RGBA 8 бит, а в файле {colour} и {depth} бит")
                continue
            try:
                raw = zlib.decompress(idat)
            except zlib.error as exc:
                fail(f"{rel}: не распаковывается ({exc})")
                continue
            expected = (width * 4 + 1) * height
            if len(raw) != expected:
                fail(f"{rel}: данных {len(raw)} байт, а картинка {width}x{height} "
                     f"требует {expected} — текстура нечитаемая")
    return count


def zip_dir(src_dir, out_path, arc_prefix=""):
    """Собирает zip с фиксированным временем файлов.

    Без этого каждая пересборка даёт другой sha256, и проверка в
    decode-install.sh перестаёт совпадать с тем, что собрано из исходников.
    """
    stamp = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dp, _, files in os.walk(src_dir):
            for name in sorted(files):
                full = os.path.join(dp, name)
                rel = os.path.relpath(full, src_dir)
                arc = os.path.join(arc_prefix, rel) if arc_prefix else rel
                info = zipfile.ZipInfo(arc, date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as fh:
                    z.writestr(info, fh.read())


def main():
    print("== Проверки ==")
    n = check_json_tree(CONTENT)
    print(f"  JSON в контенте: {n} файлов")
    refs = check_blockstates(CONTENT)
    print(f"  ссылок на модели: {refs}")
    tex_refs, _ = check_textures(CONTENT)
    png_count = check_png(CONTENT)
    print(f"  PNG проверено: {png_count}")
    tab_items = check_creative_tabs(CONTENT)
    print(f"  предметов во вкладках креатива: {tab_items}")
    print(f"  ссылок на текстуры: {tex_refs}")
    check_states(CONTENT)
    check_native()
    hooks = check_mixin_manifest()
    print(f"  хуков в бандле: {len(hooks)}")
    check_hook_catalog(hooks)

    if errors:
        print(f"\n== Сборка отменена: {len(errors)} ошибок ==")
        for e in errors:
            print(" -", e)
        return 1

    print("\n== Сборка ==")
    os.makedirs(DIST, exist_ok=True)
    hmod = os.path.join(DIST, f"{ID}.hmod")
    hnmod = os.path.join(DIST, f"{ID}-{VERSION}.hnmod")
    zip_dir(CONTENT, hmod)
    # Нативный бандл: манифест + mixins/<id>/
    stamp = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(hnmod, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        def put(src, arc):
            info = zipfile.ZipInfo(arc, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(src, "rb") as fh:
                z.writestr(info, fh.read())

        put(os.path.join(NATIVE, "horizon-native.json"), "horizon-native.json")
        for dp, _, files in os.walk(os.path.join(NATIVE, "mixins")):
            for name in sorted(files):
                full = os.path.join(dp, name)
                put(full, os.path.relpath(full, NATIVE))
    print(f"  {os.path.relpath(hmod, ROOT)}  {os.path.getsize(hmod)} байт")
    print(f"  {os.path.relpath(hnmod, ROOT)}  {os.path.getsize(hnmod)} байт")

    # Install.zip: две папки, как и раньше.
    stage = os.path.join(DIST, "stage")
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(os.path.join(stage, "horizon-mods"))
    os.makedirs(os.path.join(stage, "horizon-native-mods"))
    shutil.copy(hmod, os.path.join(stage, "horizon-mods", f"{ID}.hmod"))
    shutil.copy(hnmod, os.path.join(stage, "horizon-native-mods", f"{ID}-{VERSION}.hnmod"))
    install = os.path.join(DIST, f"{ID}-{VERSION}-install.zip")
    with zipfile.ZipFile(install, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dp, _, files in os.walk(stage):
            for name in sorted(files):
                full = os.path.join(dp, name)
                arc = os.path.relpath(full, stage)
                info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as fh:
                    z.writestr(info, fh.read())
    shutil.rmtree(stage)
    print(f"  {os.path.relpath(install, ROOT)}  {os.path.getsize(install)} байт")

    # Проверка: архив открывается и содержит ожидаемое.
    with zipfile.ZipFile(install) as z:
        names = z.namelist()
        assert f"horizon-mods/{ID}.hmod" in names, names
        assert f"horizon-native-mods/{ID}-{VERSION}.hnmod" in names, names
        bad = z.testzip()
        if bad:
            fail(f"битый файл в архиве: {bad}")
    print("\n== Готово ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
