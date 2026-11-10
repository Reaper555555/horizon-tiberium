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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*", default=None)
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "..", "dist", "preview.png"))
    args = ap.parse_args()

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
