"""从 assets/icon_source.jpg 生成蓝色底盘状态 PNG 与 exe 图标。"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
BALL_SIZE = 96
DISC_COLOR = (255, 255, 255, 255)
CAT_COLOR = (43, 65, 78, 255)
RINGS = {
    "ok": None,
    "warn": (243, 156, 18, 255),
    "err": (231, 76, 60, 255),
    "idle": (154, 167, 184, 255),
}


def main():
    src = Image.open(os.path.join(ASSETS, "icon_source.jpg")).convert("RGB")
    src = src.resize((512, 512), Image.LANCZOS)
    gray = src.convert("L")
    alpha = gray.point(lambda p: max(0, min(255, (180 - p) * 4)))

    cat = Image.new("RGBA", src.size, CAT_COLOR)
    cat.putalpha(alpha)
    cat = cat.resize((BALL_SIZE, BALL_SIZE), Image.LANCZOS)

    for name, ring in RINGS.items():
        disc = Image.new("RGBA", (BALL_SIZE, BALL_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(disc)
        draw.ellipse((0, 0, BALL_SIZE - 1, BALL_SIZE - 1), fill=DISC_COLOR)
        if ring:
            draw.ellipse((2, 2, BALL_SIZE - 3, BALL_SIZE - 3), outline=ring, width=4)
        disc.alpha_composite(cat)
        disc.save(os.path.join(ASSETS, "ball_%s.png" % name))

    icon = Image.new("RGBA", (BALL_SIZE, BALL_SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(icon).ellipse((0, 0, BALL_SIZE - 1, BALL_SIZE - 1), fill=DISC_COLOR)
    icon.alpha_composite(cat)
    icon.save(
        os.path.join(ASSETS, "icon.ico"),
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("generated:", sorted(os.listdir(ASSETS)))


if __name__ == "__main__":
    main()