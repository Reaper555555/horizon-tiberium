#!/usr/bin/env python3
"""Рисует модели мода в изометрии: видно, как будет выглядеть блок в игре.

Без запуска Horizon можно оценить форму кристаллов, шпиля и иконок:
скрипт читает JSON моделей, рисует их грани в изометрии и складывает
превью в один PNG.

    python3 tools/preview.py [файл.json ...] [-o превью.png]
"""

import argparse
import json
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.abspath(os.path.join(HERE, "..", "content"))
MODELS = os.path.join(CONTENT, "assets", "tiberium", "models", "block")

COS30 = math.cos(math.radians(30))
SIN30 = math.sin(math.radians(30))
# Условный цвет тиберия: тот же зелёный, что в текстуре 0.1.13.
COLOR = (0.22, 0.47, 0.20)


def project(x, y, z):
    """Точка блока -> координаты на экране (изометрия)."""
    return ((x - z) * COS30, (x + z) * SIN30 - y)


def rotate_point(p, origin, axis, angle):
    """Поворачивает точку вокруг оси, как это делает формат модели."""
    x, y, z = p
    ox, oy, oz = origin
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    dx, dy, dz = x - ox, y - oy, z - oz
    if axis == "x":
        dy, dz = dy * cos_a - dz * sin_a, dy * sin_a + dz * cos_a
    elif axis == "y":
        dx, dz = dx * cos_a + dz * sin_a, -dx * sin_a + dz * cos_a
    else:
        dx, dy = dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a
    return (ox + dx, oy + dy, oz + dz)


def corners(el):
    x1, y1, z1 = el["from"]
    x2, y2, z2 = el["to"]
    rot = el.get("rotation")
    pts = {}
    for x in (x1, x2):
        for y in (y1, y2):
            for z in (z1, z2):
                p = (x, y, z)
                if rot:
                    p = rotate_point(p, rot["origin"], rot["axis"], rot["angle"])
                pts[(x, y, z)] = project(*p)
    return pts


def model_polygons(model):
    """Грани модели: (полигон, яркость)."""
    out = []
    for el in model.get("elements", []):
        p = corners(el)
        x1, y1, z1 = el["from"]
        x2, y2, z2 = el["to"]
        faces = [
            ([(x1, y2, z1), (x2, y2, z1), (x2, y2, z2), (x1, y2, z2)], 1.00),
            ([(x2, y1, z1), (x2, y2, z1), (x2, y2, z2), (x2, y1, z2)], 0.72),
            ([(x1, y1, z2), (x1, y2, z2), (x2, y2, z2), (x2, y1, z2)], 0.52),
        ]
        for face, shade in faces:
            poly = [p[c] for c in face]
            out.append((poly, shade))
    return out


def render(model, ax):
    polys = model_polygons(model)
    polys.sort(key=lambda item: -sum(p[0] for p in item[0]))
    collection = PolyCollection(
        [poly for poly, _ in polys],
        facecolors=[tuple(min(1.0, c * shade) for c in COLOR) for _, shade in polys],
        edgecolors=(0.05, 0.12, 0.05),
        linewidths=0.4,
    )
    ax.add_collection(collection)
    ax.set_xlim(-22, 22)
    ax.set_ylim(-26, 18)
    ax.set_aspect("equal")
    ax.axis("off")


# --- сборка сцены: крупная структура целиком ------------------------------

EDGE_DIRS = {
    "e": (1, 0),
    "ne": (1, 1),
    "nw": (-1, 1),
    "w": (-1, 0),
    "sw": (-1, -1),
    "se": (1, -1),
}


def footprint(seed, area):
    """Произвольная форма сечения: пятно клеток от центра.

    Тот же алгоритм, что в рантайме мода, — превью показывает ровно то,
    что вырастет в игре.
    """
    cells = [(0, 0)]
    state = seed | 1
    mask = (1 << 64) - 1
    while len(cells) < area:
        state = (state * 6364136223846793005 + 1442695040888963407) & mask
        idx = (state >> 17) % len(cells)
        x, z = cells[idx]
        d = [(1, 0), (-1, 0), (0, 1), (0, -1)][(state >> 33) % 4]
        nxt = (x + d[0], z + d[1])
        if nxt not in cells:
            cells.append(nxt)
    return cells


def column_model_for(x, z, cells):
    """Внутренние клетки — ровная колонна, крайние — повёрнутые."""
    inside = set(cells)
    for name, (dx, dz) in EDGE_DIRS.items():
        if (x + dx, z + dz) not in inside:
            return "column_edge_%s" % name
    return "column_core"


def render_scene(scene, ax):
    """Рисует блоки сцены (модель -> список позиций) в изометрии."""
    # Блоки рисуются от дальних к ближним, а в пределах высоты — снизу
    # вверх: иначе верхние блоки закрывают нижние.
    items = []
    for model_name, positions in scene:
        for px, py, pz in positions:
            items.append((-(px + pz), py, model_name, (px, py, pz)))
    items.sort()
    all_polys = []
    for _, _, model_name, (px, py, pz) in items:
        with open(os.path.join(MODELS, model_name + ".json"), encoding="utf-8") as fh:
            model = json.load(fh)
        polys = model_polygons(model)
        # Модели в координатах 0..16, смещение блока — в тех же единицах.
        ox, oy = px * 16.0, py * 16.0
        for poly, shade in polys:
            moved = [((p[0] + ox), (p[1] + oy)) for p in poly]
            all_polys.append((moved, shade))
    all_polys.sort(key=lambda item: -sum(p[0] for p in item[0]))
    collection = PolyCollection(
        [poly for poly, _ in all_polys],
        facecolors=[tuple(min(1.0, c * shade) for c in COLOR) for _, shade in all_polys],
        edgecolors=(0.05, 0.12, 0.05),
        linewidths=0.35,
    )
    ax.add_collection(collection)
    xs = [p[0] for poly, _ in all_polys for p in poly]
    ys = [p[1] for poly, _ in all_polys for p in poly]
    if xs and ys:
        pad = 4
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")
    ax.axis("off")


def spire_scene():
    """Массив, каким он вырастает в игре: произвольное сечение из кубов,
    верхние слои съезжают по одной координате."""
    scene = []
    cells = footprint(0x1234_5678, 14)
    lean = (1, 0)
    lean_step = 2
    for layer in range(5):
        # Сдвиг ограничен двумя шагами — как в игре.
        shift = min(layer // lean_step, 2) * lean[0]
        shift_z = min(layer // lean_step, 2) * lean[1]
        for x, z in cells:
            style = "column_tip" if layer == 4 else "column_core"
            scene.append((style, [(x + shift, layer, z + shift_z)]))
    return scene


def wall_scene():
    """Настенные кристаллы: прижаты к стене, как факелы."""
    scene = []
    for style, x, z in (
        ("wall_e", 0, 0),
        ("wall_w", 2, 0),
        ("wall_n", 4, 0),
        ("wall_s", 6, 0),
        ("wall_up", 8, 0),
    ):
        name = f"crystal_shaft_{style}_p6_r0"
        scene.append((name, [(x, 0, z)]))
    return scene


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*", default=None)
    ap.add_argument("--scene", choices=("spire", "wall"), default=None)
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "..", "dist", "preview.png"))
    args = ap.parse_args()

    if args.scene in ("spire", "wall"):
        fig, ax = plt.subplots(figsize=(6.4, 6.4))
        if args.scene == "spire":
            render_scene(spire_scene(), ax)
            ax.set_title("крупная структура: кубы, произвольное сечение, верхние слои съезжают", fontsize=9)
        else:
            render_scene(wall_scene(), ax)
            ax.set_title("настенные кристаллы: прижаты к стене", fontsize=9)
        fig.tight_layout()
        out = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        fig.savefig(out, dpi=110)
        print("превью:", out)
        return

    files = args.models
    if not files:
        files = [
            os.path.join(MODELS, f"crystal_shaft_{style}_p{stage}_r0.json")
            for style in ("a", "b", "c", "j")
            for stage in (2, 6)
        ] + [
            os.path.join(MODELS, "column_core.json"),
            os.path.join(MODELS, "column_edge_ne.json"),
            os.path.join(MODELS, "column_tip.json"),
        ]

    cols = 4
    rows = (len(files) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.6, rows * 2.6))
    axes = axes.flatten() if hasattr(axes, "flatten") else [axes]
    for ax, path in zip(axes, files):
        model = json.load(open(path, encoding="utf-8"))
        render(model, ax)
        ax.set_title(os.path.basename(path).replace(".json", ""), fontsize=7)
    for ax in axes[len(files):]:
        ax.axis("off")
    fig.tight_layout()
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=110)
    print("превью:", out)


if __name__ == "__main__":
    main()
