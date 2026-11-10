#!/usr/bin/env python3
"""Генератор моделей, бло��стейтов и текстур мода Tiberium (Horizon 26.3).

Модель Minecraft — это набор осевых боксов (0..16) с необязательным поворотом
элемента вокруг оси. Поэтому:

  * стадия роста p0..p6 задаёт МАСШТАБ сечения (4..12 px) — визуально плавный рост;
  * наклон задаётся element rotation вокруг оси x или z на 22.5° — настоящий
    наклонный кристалл, а не сдвинутый блок;
  * поворот r0..r3 поворачивает сечение в плане на 90° — соседние кристаллы
    перестают выглядеть одинаковыми;
  * tip — не полный блок: основа y 0..12 плюс сужающийся наконечник y 12..16,
    поэтому кристалл реально сужается к вершине.
"""

import json
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")
NS = "tiberium"

# ---------------------------------------------------------------- геометрия ---

# Базовые сечения (пиксели, 0..16). X — ширина, Z — глубина.
SHAPES = {
    # внешний призм + внутренний: даёт двухгранный кристалл, как в референсе
    "a": [((3, 4), (13, 12)), ((4, 3), (12, 13))],
    "b": [((2, 5), (14, 11)), ((4, 3), (12, 13))],
    "c": [((5, 2), (11, 14)), ((3, 4), (13, 12))],
    # «гроздь» из трёх сросшихся призм
    "j": [((1, 2), (15, 8)), ((2, 7), (14, 14)), ((4, 1), (10, 15))],
}
# Наклон: (ось, угол). Положительный угол — наклон в +X (ось z) или +Z (ось x).
LEANS = {
    "": None,
    "xp": ("z", -22.5),
    "xn": ("z", 22.5),
    "zp": ("x", -22.5),
    "zn": ("x", 22.5),
}
SHAPE_NAMES = ["a", "b", "c", "j"]

# Ширина сечения по стадии, px.
STAGES = ["p0", "p1", "p2", "p3", "p4", "p5", "p6"]
STAGE_WIDTH = {"p0": 4, "p1": 6, "p2": 8, "p3": 9, "p4": 10, "p5": 11, "p6": 12}
SEGMENTS = ["shaft", "tip"]
ROTATIONS = ["r0", "r1", "r2", "r3"]

# Стиль = форма + наклон.
STYLES = []
for _shape in SHAPE_NAMES:
    for _lean in LEANS:
        STYLES.append(_shape + _lean)
STYLES.sort()


def style_shape(style):
    """Разбирает имя стиля на форму и наклон: 'axp' -> ('a', 'xp')."""
    for lean in ("xp", "xn", "zp", "zn"):
        if style.endswith(lean):
            return style[: -len(lean)], lean
    return style, ""


def rot_box(x1, z1, x2, z2, rot):
    """Поворачивает сечение в плане на 90/180/270°."""
    if rot == "r0":
        return x1, z1, x2, z2
    if rot == "r1":  # 90°: (x, z) -> (16 - z, x)
        return 16 - z2, x1, 16 - z1, x2
    if rot == "r2":  # 180°
        return 16 - x2, 16 - z2, 16 - x1, 16 - z1
    return z1, 16 - x2, z2, 16 - x1  # r3: 270°


def scale_box(x1, z1, x2, z2, target_w):
    """Масштабирует сечение по ширине до target_w, сохраняя центр блока."""
    w = x2 - x1
    if w <= 0:
        return x1, z1, x2, z2
    f = target_w / w
    cx, cz = (x1 + x2) / 2.0, (z1 + z2) / 2.0
    nx1 = cx - (cx - x1) * f
    nx2 = cx + (x2 - cx) * f
    nz1 = cz - (cz - z1) * f
    nz2 = cz + (z2 - cz) * f
    return (round(nx1, 2), round(nz1, 2), round(nx2, 2), round(nz2, 2))


def element(x1, y1, z1, x2, y2, z2, rot=None, tex="#crystal"):
    el = {
        "from": [x1, y1, z1],
        "to": [x2, y2, z2],
        "faces": {
            face: {"texture": tex, "shade": False}
            for face in ("down", "up", "north", "south", "west", "east")
        },
    }
    if rot:
        el["rotation"] = {"origin": [8, 0, 8], "axis": rot[0], "angle": rot[1]}
    return el


def crystal_model(style, stage, rot, segment):
    """Модель кристалла: форма + наклон + масштаб стадии + поворот в плане."""
    shape, lean = style_shape(style)
    boxes = SHAPES[shape]
    target = STAGE_WIDTH[stage]
    lean_rot = LEANS[lean]
    elements = []
    top_y = 16 if segment == "shaft" else 12
    for (bx1, bz1), (bx2, bz2) in boxes:
        sx1, sz1, sx2, sz2 = scale_box(bx1, bz1, bx2, bz2, target)
        rx1, rz1, rx2, rz2 = rot_box(sx1, sz1, sx2, sz2, rot)
        elements.append(element(rx1, 0, rz1, rx2, top_y, rz2, lean_rot))
    if segment == "tip":
        # наконечник: сужающаяся шапка над основой
        cap_w = max(2.0, target * 0.55)
        cx1, cz1, cx2, cz2 = scale_box(3, 3, 13, 13, cap_w)
        rx1, rz1, rx2, rz2 = rot_box(cx1, cz1, cx2, cz2, rot)
        elements.append(element(rx1, 12, rz1, rx2, 16, rz2, lean_rot))
    return {
        "ambientocclusion": False,
        "render_type": "minecraft:cutout",
        "textures": {"particle": f"{NS}:block/crystal", "crystal": f"{NS}:block/crystal"},
        "elements": elements,
    }


# ---------------------------------------------------------------- колонны ---

# Стили колонны: стержень + шесть граней шестиугольника + вершина.
COLUMN_STYLES = [
    "core",
    "edge_e", "edge_w", "edge_ne", "edge_nw", "edge_se", "edge_sw",
    "tip",
]
# Иконки предметов: имя -> вид рисунка.
ITEM_ICONS = {
    "raw_shard": "shard",
    "sealed_capsule": "capsule",
    "empty_capsule": "empty_capsule",
    "bio_helmet": "bio_helmet",
    "bio_chestplate": "bio_chestplate",
    "bio_leggings": "bio_leggings",
    "bio_boots": "bio_boots",
    "sonic_charge": "sonic",
    "sonic_disruptor": "sonic",
    "crystal": "cluster",
    "sonic_pylon": "pylon",
}
# Насколько блок срезан с каждой стороны (px) для каждого стиля.
COLUMN_INSET = {
    "core": [],
    "edge_e": ["e"], "edge_w": ["w"],
    "edge_ne": ["n", "e"], "edge_nw": ["n", "w"],
    "edge_se": ["s", "e"], "edge_sw": ["s", "w"],
    "tip": ["n", "s", "e", "w"],
}
INSET = 3  # px


def column_model(style):
    sides = COLUMN_INSET[style]
    x1 = INSET if "w" in sides else 0
    x2 = 16 - INSET if "e" in sides else 16
    z1 = INSET if "n" in sides else 0
    z2 = 16 - INSET if "s" in sides else 16
    if style == "tip":
        y1, y2 = 2, 16
    else:
        y1, y2 = 0, 16
    tex = f"{NS}:block/column_{style}"
    return {
        "ambientocclusion": False,
        "render_type": "minecraft:cutout",
        "textures": {"particle": tex, "column": tex},
        "elements": [element(x1, y1, z1, x2, y2, z2, None, "#column")],
    }


# --------------------------------------------------------------- текстуры ---

def write_png(path, rgba_rows):
    """Минимальный PNG writer (RGBA, 8 бит)."""
    h = len(rgba_rows)
    w = len(rgba_rows[0])

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + bytes(row) for row in rgba_rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)


def green_facets(width=16, height=16, base=(52, 138, 48), light=(104, 196, 74), dark=(28, 84, 30)):
    """Зелёная текстура с диагональными гранями — читается как гранёный кристалл."""
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            d = (x + y) % 8
            edge = min(x, width - 1 - x, y, height - 1 - y)
            if d in (0, 1):
                c = light
            elif d in (6, 7):
                c = dark
            else:
                c = base
            if edge == 0:
                c = dark
            row.extend((*c, 255))
        rows.append(row)
    return rows


def item_icon(kind):
    """Простые зелёные иконки предметов: форма отличается от предмета к предмету."""
    base = (58, 150, 52)
    light = (122, 208, 84)
    dark = (26, 76, 28)
    rows = []
    for y in range(16):
        row = []
        for x in range(16):
            cx, cy = x - 7.5, y - 7.5
            c = base
            if kind == "shard":
                # осколок: ромб
                d = abs(cx) + abs(cy)
                c = light if d < 3.5 else (base if d < 6 else dark)
            elif kind == "capsule":
                # капсула: вертикальный круглый контейнер
                d = (cx * cx) / 16.0 + (cy * cy) / 25.0
                c = light if d < 1.0 else (base if d < 1.8 else dark)
            elif kind == "empty_capsule":
                d = (cx * cx) / 16.0 + (cy * cy) / 25.0
                c = dark if d < 1.0 else (base if d < 1.8 else dark)
            elif kind.startswith("bio_"):
                # броня: щит
                if abs(cx) < 5 and -5 < cy < 5:
                    c = light if abs(cx) < 3 else base
                else:
                    c = dark
            elif kind == "sonic":
                # заряд: кольцо
                d = (cx * cx + cy * cy) ** 0.5
                c = light if 3.0 < d < 6.0 else (base if d < 7.5 else dark)
            elif kind == "cluster":
                # гроздь кристаллов: три ромба
                for ox, oy, r in ((-3.0, 1.5, 3.0), (3.0, 1.0, 2.6), (0.0, -3.0, 3.4)):
                    d = abs(cx - ox) + abs(cy - oy)
                    if d < r:
                        c = light if d < r * 0.55 else base
                    elif d < r + 1.2:
                        c = dark
            elif kind == "pylon":
                # пилон: вертикальная колонна
                if abs(cx) < 2.5 and -6 < cy < 6:
                    c = light if abs(cx) < 1.2 else base
                elif abs(cx) < 4.5 and -5 < cy < 4:
                    c = base
                else:
                    c = dark
            else:
                c = base
            row.extend((*c, 255))
        rows.append(row)
    return rows


def soil_texture():
    """Заражённая земля: тёмно-бурая с зелёными вкраплениями."""
    base = (58, 44, 32)
    green = (66, 92, 44)
    dark = (36, 27, 20)
    rows = []
    for y in range(16):
        row = []
        for x in range(16):
            n = (x * 7 + y * 13 + x * y * 3) % 11
            c = green if n < 3 else (dark if n > 8 else base)
            row.extend((*c, 255))
        rows.append(row)
    return rows


def pylon_texture():
    """Пилон: металл с зеленоватым отливом."""
    base = (72, 96, 88)
    light = (126, 158, 146)
    dark = (42, 58, 54)
    rows = []
    for y in range(16):
        row = []
        for x in range(16):
            d = (x + y) % 6
            c = light if d == 0 else (dark if d == 4 else base)
            row.extend((*c, 255))
        rows.append(row)
    return rows


def column_texture(kind):
    """Текстура колонны: у «гранёных» вариантов диагональ тем сильнее."""
    strength = {"core": 1, "tip": 2}.get(kind, 3)
    base = (46, 122, 42)
    light = (92, 176, 66)
    dark = (24, 74, 26)
    rows = []
    for y in range(16):
        row = []
        for x in range(16):
            d = (x + y) % 8
            if d < strength:
                c = light
            elif d >= 8 - strength:
                c = dark
            else:
                c = base
            row.extend((*c, 255))
        rows.append(row)
    return rows


# ------------------------------------------------------------------ запись ---

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    models_dir = os.path.join(CONTENT, "assets", NS, "models", "block")
    bs_dir = os.path.join(CONTENT, "assets", NS, "blockstates")
    tex_dir = os.path.join(CONTENT, "assets", NS, "textures", "block")

    # 1. Модели кристаллов
    variants = {}
    for segment in SEGMENTS:
        for style in STYLES:
            for stage in STAGES:
                for rot in ROTATIONS:
                    name = f"crystal_{segment}_{style}_{stage}_{rot}"
                    write_json(os.path.join(models_dir, name + ".json"),
                               crystal_model(style, stage, rot, segment))
                    key = f"segment={segment},style={style},shift={stage},rotation={rot}"
                    variants[key] = {"model": f"{NS}:block/{name}"}

    # 2. Модели колонн
    for style in COLUMN_STYLES:
        write_json(os.path.join(models_dir, f"column_{style}.json"), column_model(style))

    # 3. Бло��стейты
    write_json(os.path.join(bs_dir, "crystal.json"), {"variants": variants})
    write_json(os.path.join(bs_dir, "column.json"),
               {"variants": {f"style={s}": {"model": f"{NS}:block/column_{s}"} for s in COLUMN_STYLES}})

    # 4. Текстуры: всё рисуется кодом, в репозитории бинарных файлов нет.
    write_png(os.path.join(tex_dir, "crystal.png"), green_facets())
    write_png(os.path.join(tex_dir, "column_core.png"), column_texture("core"))
    write_png(os.path.join(tex_dir, "column_tip.png"), column_texture("tip"))
    for s in COLUMN_STYLES:
        if s not in ("core", "tip"):
            write_png(os.path.join(tex_dir, f"column_{s}.png"), column_texture(s))
    item_dir = os.path.join(CONTENT, "assets", NS, "textures", "item")
    for name, kind in ITEM_ICONS.items():
        write_png(os.path.join(item_dir, f"{name}.png"), item_icon(kind))
    # Заражённая земля и пилон — тоже кодом.
    write_png(os.path.join(tex_dir, "tainted_soil.png"), soil_texture())
    write_png(os.path.join(tex_dir, "sonic_pylon.png"), pylon_texture())

    print(f"стилей: {len(STYLES)} | стадий: {len(STAGES)} | поворотов: {len(ROTATIONS)}")
    print(f"моделей кристаллов: {len(SEGMENTS) * len(STYLES) * len(STAGES) * len(ROTATIONS)}")
    print(f"вариантов бло��стейта crystal: {len(variants)}")
    print(f"моделей колонн: {len(COLUMN_STYLES)}")


if __name__ == "__main__":
    main()
