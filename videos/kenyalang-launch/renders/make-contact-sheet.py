"""Build the delivery contact sheet from the final render.

Nine stills across the seven-frame arc, 3x3, 640x360 tiles, labelled with the
timestamp and the beat each one belongs to.
"""
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
MP4 = HERE / "kenyalang-launch.mp4"
OUT = HERE / "contact-sheet.jpg"

# (seconds, beat label)
STILLS = [
    (1.90, "01  HOOK"),
    (5.60, "02  REVEAL"),
    (11.20, "03  INTAKE"),
    (16.60, "04  PROVENANCE"),
    (21.60, "05  AUDIT"),
    (26.50, "06  EXPORT"),
    (30.90, "07  CLOSE"),
]

TILE_W, TILE_H = 640, 360
COLS = 3
PAD = 18
LABEL_H = 34
BG = (246, 241, 231)
INK = (23, 26, 24)
MUTED = (120, 112, 100)
RULE = (217, 210, 195)


def font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("consola.ttf", "CascadiaMono.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def grab(seconds: float, dest: Path) -> Image.Image:
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-ss", f"{seconds:.3f}", "-i", str(MP4),
            "-frames:v", "1", str(dest),
        ],
        check=True,
    )
    return Image.open(dest).convert("RGB")


def main() -> None:
    rows = (len(STILLS) + COLS - 1) // COLS
    width = COLS * TILE_W + (COLS + 1) * PAD
    height = rows * (TILE_H + LABEL_H) + (rows + 1) * PAD
    sheet = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(sheet)
    mono = font(19)

    with tempfile.TemporaryDirectory() as tmp:
        for i, (seconds, label) in enumerate(STILLS):
            still = grab(seconds, Path(tmp) / f"{i}.png")
            still = still.resize((TILE_W, TILE_H), Image.LANCZOS)
            col, row = i % COLS, i // COLS
            x = PAD + col * (TILE_W + PAD)
            y = PAD + row * (TILE_H + LABEL_H + PAD)
            sheet.paste(still, (x, y))
            draw.rectangle([x, y, x + TILE_W - 1, y + TILE_H - 1], outline=RULE)
            draw.text((x, y + TILE_H + 8), label, font=mono, fill=INK)
            draw.text(
                (x + TILE_W, y + TILE_H + 8),
                f"{seconds:05.2f}s",
                font=mono,
                fill=MUTED,
                anchor="ra",
            )

    sheet.save(OUT, quality=92, subsampling=0)
    print(f"{OUT}  {sheet.width}x{sheet.height}")


if __name__ == "__main__":
    main()
