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
# Наклон скопления: ось, угол и сдвиг (для осей, отличных от оси наклона).
LEANS = {
    "": (None, 0.0, 0.0, 0.0),
    "xp": ("z", 14.0, 1.2, 0.0),
    "xn": ("z", -14.0, -1.2, 0.0),
    "zp": ("x", 14.0, 0.0, 1.2),
    "zn": ("x", -14.0, 0.0, -1.2),
}
SHAPE_NAMES = ["a", "b", "c", "j"]

# Ширина сечения по стадии, px.
STAGES = ["p0", "p1", "p2", "p3", "p4", "p5", "p6"]
STAGE_WIDTH = {"p0": 4, "p1": 6, "p2": 8, "p3": 9, "p4": 10, "p5": 11, "p6": 12}
SEGMENTS = ["shaft", "tip"]
ROTATIONS = ["r0", "r1", "r2", "r3"]

# Настенные кристаллы: прижимаются к стене, как факелы, и растут из угла.
WALL_SHAPES = {
    "wall_e": [
        (5.0, 0.0, 2.0, 13.0, "z", 0.0),
        (5.0, 2.6, 1.5, 9.0, "z", 10.0),
        (5.0, -2.6, 1.5, 10.5, "z", -10.0),
    ],
    "wall_w": [
        (-5.0, 0.0, 2.0, 13.0, "z", 0.0),
        (-5.0, 2.6, 1.5, 9.0, "z", 10.0),
        (-5.0, -2.6, 1.5, 10.5, "z", -10.0),
    ],
    "wall_n": [
        (0.0, -5.0, 2.0, 13.0, "x", 0.0),
        (2.6, -5.0, 1.5, 9.0, "x", 10.0),
        (-2.6, -5.0, 1.5, 10.5, "x", -10.0),
    ],
    "wall_s": [
        (0.0, 5.0, 2.0, 13.0, "x", 0.0),
        (2.6, 5.0, 1.5, 9.0, "x", 10.0),
        (-2.6, 5.0, 1.5, 10.5, "x", -10.0),
    ],
    # Потолок: кристаллы свисают сверху.
    "wall_up": [
        (0.0, 0.0, 2.2, 12.0, "z", 0.0),
        (2.8, 0.6, 1.6, 8.0, "z", 10.0),
        (-2.8, -0.6, 1.6, 9.0, "z", -10.0),
    ],
}


# Стиль = форма + наклон.
STYLES = []
for _shape in SHAPE_NAMES:
    for _lean in LEANS:
        STYLES.append(_shape + _lean)
for _wall in WALL_SHAPES:
    STYLES.append(_wall)
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


def element(x1, y1, z1, x2, y2, z2, rot=None, tex="#crystal", origin=None):
    el = {
        "from": [x1, y1, z1],
        "to": [x2, y2, z2],
        "faces": {
            face: {"texture": tex, "shade": False}
            for face in ("down", "up", "north", "south", "west", "east")
        },
    }
    if rot:
        el["rotation"] = {
            "origin": origin or [8, 0, 8],
            "axis": rot[0],
            "angle": rot[1],
        }
    return el


# Скопления кристаллов: (сдвиг X, сдвиг Z, полуширина, высота, ось, угол).
# Сдвиги — от центра блока (8, 8); полуширина и высота — в пикселях.
# Каждый блок — это не одна игла, а гроздь из нескольких кристаллов разной
# высоты: так выглядит тиберий в референсах.
CLUSTER_SHAPES = {
    # высокий центральный и два боковых
    "a": [
        (0.0, 0.0, 3.0, 16.0, "z", 0.0),
        (-4.2, 1.4, 2.3, 11.0, "z", 16.0),
        (4.2, -1.2, 2.3, 12.5, "z", -14.0),
    ],
    # плотная гроздь из четырёх
    "b": [
        (0.0, 0.0, 3.4, 9.0, "z", 0.0),
        (-3.4, 0.6, 2.2, 14.0, "z", 12.0),
        (3.4, -0.6, 2.2, 13.0, "z", -12.0),
        (0.6, -3.4, 2.1, 11.0, "x", 8.0),
    ],
    # два крупных и один мелкий
    "c": [
        (-2.4, 0.4, 3.0, 15.0, "z", 10.0),
        (3.0, -1.0, 2.6, 12.0, "z", -10.0),
        (0.4, 3.4, 1.9, 8.5, "x", 0.0),
    ],
    # пять кристаллов
    "j": [
        (0.0, 0.0, 2.5, 15.0, "z", 0.0),
        (-3.8, -2.2, 1.9, 10.0, "z", 14.0),
        (3.8, -2.2, 1.9, 11.0, "z", -14.0),
        (-2.6, 3.6, 1.7, 8.0, "x", 10.0),
        (3.0, 3.4, 1.7, 9.0, "x", -10.0),
    ],
}


def rotate_layout(dx, dz, axis, angle, rot):
    """Поворот раскладки скопления на 90/180/270°."""
    if rot == "r0":
        return dx, dz, axis, angle
    if rot == "r1":  # 90°
        return dz, -dx, ("x" if axis == "z" else "z"), angle
    if rot == "r2":  # 180°
        return -dx, -dz, axis, angle
    return -dz, dx, ("x" if axis == "z" else "z"), angle  # r3: 270°


def crystal_model(style, stage, rot, segment):
    """Модель кристалла: скопление разной формы, наклон, стадия и поворот."""
    shape, lean = style_shape(style)
    lean_axis, lean_angle, lean_dx, lean_dz = LEANS[lean]
    scale_w = STAGE_WIDTH[stage] / 12.0
    scale_h = 0.55 + 0.45 * scale_w
    # Настенный кристалл прижат к стене и не должен от неё отползать.
    wall = shape.startswith("wall_")
    spread = 1.0 if wall else 0.4 + 0.6 * scale_w
    elements = []
    cluster = CLUSTER_SHAPES.get(shape) or WALL_SHAPES[shape]
    for dx, dz, half, height, axis, angle in cluster:
        dx, dz, axis, angle = rotate_layout(dx, dz, axis, angle, rot)
        if lean_axis == axis:
            angle += lean_angle
        else:
            dx += lean_dx
            dz += lean_dz
        hw = half * (0.45 + 0.55 * scale_w)
        h = height * scale_h
        if segment == "tip":
            h = min(h, 12.0)
        cx = 8.0 + dx * spread
        cz = 8.0 + dz * spread
        x1 = max(0.0, cx - hw)
        x2 = min(16.0, cx + hw)
        z1 = max(0.0, cz - hw)
        z2 = min(16.0, cz + hw)
        if x2 - x1 < 1.0 or z2 - z1 < 1.0:
            continue
        origin = [(x1 + x2) / 2, 0, (z1 + z2) / 2]
        tilt = (axis, angle) if angle else None
        if shape == "wall_up":
            # С потолка: кристаллы свисают вниз.
            elements.append(element(x1, 16 - h, z1, x2, 16, z2, tilt, "#crystal", origin))
        else:
            elements.append(element(x1, 0, z1, x2, h, z2, tilt, "#crystal", origin))
        # Каждый кристалл скопления — ровно один элемент. Наконечник отличается
        # только высотой, а не второй коробкой поверх первой.
    if not elements:
        elements.append(element(6, 0, 6, 10, 8, 10, None, "#crystal"))
    # Сплошная сердцевина: без неё между кристалнами скопления видно
    # землю, а блок выглядит пустым. Сверху её не видно — она ниже
    # вершин кристаллов.
    core_h = max(el["to"][1] for el in elements)
    if shape == "wall_up":
        core_h = 16
    core_w = 3.4 * (0.45 + 0.55 * scale_w)
    elements.append(element(8 - core_w, 0, 8 - core_w, 8 + core_w, core_h, 8 + core_w, None, "#crystal"))
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
    # Иконки предметов взяты из 0.1.13 как есть (LEGACY_PNG): капсулы,
    # броня и приборы там нарисованы хорошо, перерисовывать их незачем.
}
# Оригинальные текстуры мода 0.1.13: их вид устраивает, поэтому они
# переносятся как есть (в base64, чтобы репозиторий оставался текстовым).
LEGACY_PNG = {
    "block/crystal.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVklEQVR4nGMUSzD5z8LCxPD3"
        "7z8GCP2fAcZHZuOSY2JiYmSA4d+//0HpvwzI4vjlSNaALkeR7YwMTJTZDvcCebZD5CiynZGB"
        "iTLbGUejcTQaGZiYGBkAbErl3eSvTOoAAAAASUVORK5CYII="
    ),
    "block/sonic_pylon.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAfUlEQVR4nGPUMLf6z0ABYGFg"
        "YGAwMtcnS/O5kxchBjAwMDD4uDsxMDMzM7x//56BmZkZA6OL7z5wFOECBgYGho8fPzIwMzMz"
        "sLKyYtWMLo7iBQYGBpwacRmK1wB8GmFyOA3A5lxshmIYMBoGwyIMdu47zEAOYGFggOQqcgEA"
        "2FlMStQTlBcAAAAASUVORK5CYII="
    ),
    "block/tainted_soil.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAB/klEQVR4nFWTQW4bMQxFH0lJ"
        "4zhOvApyh97/VAVaJG1sz4xEsgsNAnQhEAJI8fPzSd5/vOZ1aSxFuXdnsSMWZTHj3gdLmTEz"
        "uZ7af3n6dj7hmeweXFoBQAQWMx7DGRHc9oGKcGmVR3fO1UggSXRE4pGoCI/uAOzu3Pqge/C6"
        "NJop52pEJk/V2EaQOWt0RHCuxu/HRo8AoKpxaYVTMb72Mbsl3Lqze9DDSSAyKSOSpQivS6N7"
        "oCJcT5U/WwegmbJ7AIGJUFS4d4CgmaIvS8Ej6R6YCutw7t15aRUTqKoI8q1KRQAoKow4FDRT"
        "TIXMZHOniLIOpwcsgGdSVIlMSDhXwyMpyjRx88FtH1Sb3ZIkMlGB2z64tEKPoEewjkEznXeH"
        "MiI4Hv6eOQFRwUi6J7/uK++XpyPD+Fw711Odo7y0eqwu2EagAgIEwTqSU1Gu1vjaB0WFosrz"
        "wcvXPuYa54zCx7ohMpNAWEypOrcQOTWuw4lMft4eqAjla+9UMzLh7fmEihCZVJ1Gbh4Igmcy"
        "IvCA1pTnWlEBLWoIUE3IhI+1EwmbBz2SERNdAUwmkbd9MGIqmhzkNOvvPjARPteNyJzMp/AY"
        "/u28iJBwKOUg0YweThHhqRimchg2TySYCbtPfE1giyQjp4kikCmYCJsHHomJHN96EnjbO8+t"
        "IMDuUx3AP6I9X2L8W1RwAAAAAElFTkSuQmCC"
    ),
    "item/bio_boots.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAUklEQVR4nGNgGAUUA0YY48KL"
        "6/+xKTCQ0GTEJ8eCLNC3ZA6KgqKYFIJyTKQ5GBMMvAEoYbDXTgxFsogIORQDnA+9QjU+hrAc"
        "xV6gOB1Q6gDKAQDYvh2zbomV6AAAAABJRU5ErkJggg=="
    ),
    "item/bio_chestplate.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAhklEQVR4nGNgoAW48OL6/wsv"
        "rv8nJMbAwMDAgq6IgYGBoW/JHDjfQEKT8cKL6/+RxRgYGBgMJDQZGRgYGJjQTYQpxAXQ5TEM"
        "QFeMbDs2wIJL4oAqlD45h4EByna4jakOrwuIAdQzgJBfkQEsbKjiApyBiC3AsIGBD0RGGANb"
        "OicEYMl5YAEAAPs/8YFBxTIAAAAASUVORK5CYII="
    ),
    "item/bio_helmet.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAgklEQVR4nGNgoBAw4pK48OL6"
        "f3QxAwlNDPUsuDT3LZmDVRzdECZiNTMwMDD0LZmD4TIUA/BpxmUI3ABiNGMzBMMLpAJ4gGAL"
        "dULAQEKTESMW+pbMYdix/iBOTR6B9gxFMSlwPtwL2OKYkO0oBpALsCYkj0B7og1AcTYpAUmq"
        "lwcxAABa4T1cc0wHMgAAAABJRU5ErkJggg=="
    ),
    "item/bio_leggings.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAU0lEQVR4nGNgGGjAiMy58OL6"
        "f2I1GkhoMjIwMDCwoEv0LZlDUHNRTAqczUSsjbgAdQ3A5nxk52JTR9AFsMAiygXkANoasKik"
        "lxGZpr8LhoYBFAMAw+8PpFx6nzMAAAAASUVORK5CYII="
    ),
    "item/empty_capsule.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAb0lEQVR4nGNgoBAwYhPMb2r5"
        "j0vDxLoaFD1MlLoAw4AnH1/htB2bPIYXnnx89d/CyQunASf2bWOQ4ReD66PYCyy4JDwrmirR"
        "xbZ31LWji1E/EIeeATgDEVuAEW1AY10V0S6g2AtYMxO+5IycCqkCAGpVHllIrCctAAAAAElF"
        "TkSuQmCC"
    ),
    "item/raw_shard.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAe0lEQVR4nMXTMQ6AIAwF0NZ4"
        "AuPgneQehE1mZmZGwj2433dyESyYGPwjpS/tUCIhCRlSnYhokpo3WprII3DF2SgiVSAhw9nY"
        "hRTAvbmFNFdoIa+AWsYCPhjSrPi/CcYAmhX7YIqPtf0/mWCuPWpW3HOJYhIy1mNHQoaEnaoX"
        "PUPv+MtRAAAAAElFTkSuQmCC"
    ),
    "item/sealed_capsule.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAbklEQVR4nGNgoBAwYhPMb2r5"
        "j0vDxLoaFD1MlLoAw4AnH1/htB2bPIYXnnx89d/CyQunASf2bWOQ4ReD66PYCyy4JP5WWWCI"
        "MbedwBCjfiAOPQNwBiK2ACPagMa6KqJdQLEXsGYmfMkZORVSBQAA81QcZlXeL5oAAAAASUVO"
        "RK5CYII="
    ),
    "item/sonic_charge.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAXUlEQVR4nGNgGPKAEV3g+MMz"
        "//FpsJQ3QdHDgk3RvBnLsWpOyojEEMNqAAMDA8OtNEUUvtqs+1jVMeEygFiA14DFCl6UGRD7"
        "YBtlBhADBt4AnNGIK9rQAcUpceABAAIwErrchv0WAAAAAElFTkSuQmCC"
    ),
    "item/sonic_disruptor.png": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAeUlEQVR4nGNgoBAw4pI4f//G"
        "f3QxQ0UNDPUs+Ezv6Z8NZ5cUpmJVg9eAEwWG+KQZGBgYGJgIqiAAUPykY+eM4u/vCxLhbM6E"
        "+XD2lUN74foodgHeMEC2FRegbhggg/P3b/xHj0Zs6YB2LnAJC8NIiXtWraK+C4aBAQC0JBuS"
        "ERqEuQAAAABJRU5ErkJggg=="
    ),
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
    """Блок крупной структуры.

    Блок массива — целый куб: кубы смыкаются вплотную, без зазоров и без
    прозрачных дыр, а форма всей структуры получается произвольной — её
    задаёт не блок, а набор блоков. Только на вершине куб дополнен
    кристаллическим гребнем.
    """
    elements = [element(0, 0, 0, 16, 16, 16, None, "#column")]
    if style == "tip":
        # Кромка вершины: кристаллический гребень поверх куба.
        shards = [
            (5.0, 6.0, 2.6, 15.0, "z", 9.0),
            (10.5, 7.5, 2.2, 16.0, "z", -11.0),
            (8.0, 11.0, 2.0, 13.0, "x", 8.0),
        ]
        for dx, dz, half, height, axis, angle in shards:
            cx = min(max(dx, 4.0), 12.0)
            cz = min(max(dz, 4.0), 12.0)
            elements.append(
                element(
                    cx - half, 0, cz - half, cx + half, height, cz + half,
                    (axis, angle), "#column", [cx, 0, cz],
                )
            )
    tex = f"{NS}:block/crystal"
    return {
        "ambientocclusion": False,
        "render_type": "minecraft:cutout",
        "textures": {"particle": tex, "column": tex},
        "elements": elements,
    }
# --------------------------------------------------------------- текстуры ---

def write_png(path, rgba_rows):
    """Минимальный PNG writer (RGBA, 8 бит)."""
    h = len(rgba_rows)
    # Ширина в пикселях, а не в байтах: в строке 4 байта на пиксель (RGBA).
    w = len(rgba_rows[0]) // 4

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


def write_legacy(rel):
    """Пишет оригинальную текстуру 0.1.13 как есть (в репозитории она в base64)."""
    import base64

    path = os.path.join(CONTENT, "assets", NS, "textures", rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(base64.b64decode(LEGACY_PNG[rel]))


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
            elif kind == "column":
                # шестигранная колонна: конус сверху и снизу, светлая грань
                w = 3.6 if abs(cy) <= 3.2 else 1.9
                if abs(cx) <= w:
                    c = light if -2.5 < cx < 0.5 else base
                else:
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


# ------------------------------------------------------- форма и коллизия ---

def model_bounds(model):
    """Габариты модели в пикселях 0..16 по всем её элементам."""
    xs, ys, zs = [], [], []
    for el in model["elements"]:
        for index, acc in ((0, xs), (1, ys), (2, zs)):
            acc.append(el["from"][index])
            acc.append(el["to"][index])
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def box_px(x1, y1, z1, x2, y2, z2):
    """Бокс в единицах блока (0..1) — так их ждёт Horizon."""
    return [
        round(x1 / 16.0, 4), round(y1 / 16.0, 4), round(z1 / 16.0, 4),
        round(x2 / 16.0, 4), round(y2 / 16.0, 4), round(z2 / 16.0, 4),
    ]


def crystal_collision(stage):
    """Коллизия кристалла по стадии роста: от узкого столбика до
    почти полного блока. Считается по настоящей модели, чтобы форма
    и коллизия не расходились."""
    # Габариты берём по всем формам и поворотам: коллизия должна
    # покрывать любой кристалл этой стадии.
    lo = [99.0, 99.0, 99.0]
    hi = [-99.0, -99.0, -99.0]
    for style in STYLES:
        for rot in ROTATIONS:
            x1, y1, z1, x2, y2, z2 = model_bounds(crystal_model(style, stage, rot, "shaft"))
            for i, v in enumerate((x1, y1, z1)):
                lo[i] = min(lo[i], v)
            for i, v in enumerate((x2, y2, z2)):
                hi[i] = max(hi[i], v)
    x1, y1, z1 = lo
    x2, y2, z2 = hi
    return box_px(x1, 0, z1, x2, y2, z2)


def column_collision(style):
    """Коллизия блока массива: сердцевина — целый блок, бок — половина."""
    model = column_model(style)
    boxes = []
    for el in model["elements"]:
        f, t = el["from"], el["to"]
        boxes.append(box_px(f[0], f[1], f[2], t[0], t[1], t[2]))
    return boxes


def write_block_data():
    """Описание блоков: форма и коллизия считаются из моделей."""
    data_dir = os.path.join(CONTENT, "data", NS, "horizon", "block")

    crystal_shapes = {}
    crystal_collision_shapes = {}
    for stage in STAGES:
        box = crystal_collision(stage)
        crystal_shapes[stage] = [box]
        crystal_collision_shapes[stage] = [box]
    write_json(os.path.join(data_dir, "crystal.json"), {
        "template": "minecraft:glass",
        "properties": {
            "hardness": 50.0,
            "explosion_resistance": 6.0,
            "light": 5,
            "sounds": "minecraft:amethyst_block",
            "requires_tool": True,
        },
        "state_properties": {
            "segment": {"type": "enum", "values": SEGMENTS},
            "style": {"type": "enum", "values": STYLES},
            "shift": {"type": "enum", "values": STAGES},
            "rotation": {"type": "enum", "values": ROTATIONS},
        },
        "default_state": {"segment": "shaft", "style": "a", "shift": "p0", "rotation": "r0"},
        # Форма и коллизия — по стадии роста: маленький кристалл узкий,
        # зрелый почти полный. Без этого кристалл проходится насквозь.
        "shapes": {"properties": ["shift"], "values": crystal_shapes,
                   "default": crystal_shapes["p0"]},
        "collision_shapes": {"properties": ["shift"], "values": crystal_collision_shapes,
                             "default": crystal_collision_shapes["p0"]},
        "item": True,
    })

    column_shapes = {}
    column_collision_shapes = {}
    for style in COLUMN_STYLES:
        boxes = column_collision(style)
        column_shapes[style] = boxes
        column_collision_shapes[style] = boxes
    write_json(os.path.join(data_dir, "column.json"), {
        "template": "minecraft:obsidian",
        "properties": {
            "hardness": 50.0,
            "explosion_resistance": 6.0,
            "light": 4,
            "sounds": "minecraft:amethyst_block",
            "requires_tool": True,
        },
        "state_properties": {
            "style": {"type": "enum", "values": COLUMN_STYLES},
        },
        "default_state": {"style": "core"},
        "shapes": {"properties": ["style"], "values": column_shapes,
                   "default": column_shapes["core"]},
        "collision_shapes": {"properties": ["style"], "values": column_collision_shapes,
                             "default": column_collision_shapes["core"]},
        "item": True,
    })


def main():
    models_dir = os.path.join(CONTENT, "assets", NS, "models", "block")
    bs_dir = os.path.join(CONTENT, "assets", NS, "blockstates")
    tex_dir = os.path.join(CONTENT, "assets", NS, "textures", "block")

    # Старые модели подчищаем: иначе в сборку попадают лишние файлы.
    for stale in os.listdir(models_dir):
        if stale.startswith(("crystal_", "column_")) and stale.endswith(".json"):
            os.remove(os.path.join(models_dir, stale))

    # 1. Модели кристаллов
    variants = {}
    for segment in SEGMENTS:
        for style in STYLES:
            for stage in STAGES:
                for rot in ROTATIONS:
                    name = f"crystal_{segment}_{style}_{stage}_{rot}"
                    key = f"segment={segment},style={style},shift={stage},rotation={rot}"
                    if style.startswith("wall_") and rot != "r0":
                        # У настенного кристала сторона задана стилем, поворот
                        # не нужен: все четыре поворота ссылаются на одну модель.
                        variants[key] = {
                            "model": f"{NS}:block/crystal_{segment}_{style}_{stage}_r0"
                        }
                        continue
                    write_json(os.path.join(models_dir, name + ".json"),
                               crystal_model(style, stage, rot, segment))
                    variants[key] = {"model": f"{NS}:block/{name}"}

    # 2. Модели колонн
    for style in COLUMN_STYLES:
        write_json(os.path.join(models_dir, f"column_{style}.json"), column_model(style))

    # 3. Бло��стейты
    write_json(os.path.join(bs_dir, "crystal.json"), {"variants": variants})
    write_json(os.path.join(bs_dir, "column.json"),
               {"variants": {f"style={s}": {"model": f"{NS}:block/column_{s}"} for s in COLUMN_STYLES}})

    # 4. Текстуры. Оригинальные из 0.1.13 (кристалл, земля, пилон и все
    #    иконки предметов) переносятся как есть — их вид устраивает.
    #    Остальное рисуется кодом.
    for rel in LEGACY_PNG:
        write_legacy(rel)
    # Своих текстур у колонн нет: все они берут зелёную текстуру кристалла,
    # чтобы шпиль выглядел цельной массой, а не набором разных кубов.

    # 4. Описание блоков: форма и коллизия по моделям.
    write_block_data()

    print(f"стилей: {len(STYLES)} | стадий: {len(STAGES)} | поворотов: {len(ROTATIONS)}")
    print(f"моделей кристаллов: {len(SEGMENTS) * len(STYLES) * len(STAGES) * len(ROTATIONS)}")
    print(f"вариантов бло��стейта crystal: {len(variants)}")
    print(f"моделей колонн: {len(COLUMN_STYLES)}")


if __name__ == "__main__":
    main()
