"""Renders Knowledge/Assets.xcassets/AppIcon.appiconset/AppIcon.png (1024x1024).

Four rounded tiles in topic colors, matching the in-app wordmark.
Run with any Python that has Pillow: tools/content/.venv/bin/python tools/make_app_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
SCALE = 4  # draw large, then downsample for smooth corners
BACKGROUND = (255, 248, 240)
TILES = [(242, 84, 27), (45, 91, 227), (14, 159, 134), (227, 161, 0)]  # math, vocabulary, geography, estimation

canvas = SIZE * SCALE
image = Image.new("RGB", (canvas, canvas), BACKGROUND)
draw = ImageDraw.Draw(image)
tile, gap = 300 * SCALE, 44 * SCALE
origin = (canvas - (2 * tile + gap)) // 2
for index, color in enumerate(TILES):
    row, column = divmod(index, 2)
    x, y = origin + column * (tile + gap), origin + row * (tile + gap)
    draw.rounded_rectangle((x, y, x + tile, y + tile), radius=78 * SCALE, fill=color)

output = Path(__file__).resolve().parent.parent / "Knowledge/Assets.xcassets/AppIcon.appiconset/AppIcon.png"
image.resize((SIZE, SIZE), Image.LANCZOS).save(output)
print(f"Wrote {output}")
