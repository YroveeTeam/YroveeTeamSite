"""Вся графика лаунчера рисуется кодом (Pillow): баннер, логотип, иконки, аватар.
Картинки делаются в 2x-разрешении, чтобы быть чёткими на HiDPI-экранах."""
import colorsys
import hashlib
import math
import random
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

S = 2  # во сколько раз рендерим больше, чем размер на экране
RS = Image.Resampling

_BOLD = ["C:/Windows/Fonts/segoeuib.ttf", "segoeuib.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf",
         "arialbd.ttf"]
_REG = ["C:/Windows/Fonts/segoeui.ttf", "segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf", "arial.ttf"]


def pil_font(size, bold=False):
    for name in (_BOLD if bold else _REG):
        try:
            return ImageFont.truetype(name, int(size))
        except OSError:
            continue
    try:
        return ImageFont.load_default(int(size))
    except TypeError:
        return ImageFont.load_default()


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _hsv(h, s, v):
    return tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, s, v))


# ---------- базовые кирпичики ----------

def rounded_mask(size, radius):
    w, h = size
    k = 4
    m = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * k - 1, h * k - 1), radius=radius * k, fill=255)
    return m.resize(size, RS.LANCZOS)


def round_corners(img, radius):
    img = img.convert("RGBA")
    alpha = ImageChops.multiply(img.getchannel("A"), rounded_mask(img.size, radius))
    img.putalpha(alpha)
    return img


def gradient(w, h, c1, c2, vertical=False):
    base = Image.linear_gradient("L")  # чёрный сверху -> белый снизу
    if not vertical:
        base = base.rotate(90, expand=True)  # чёрный слева -> белый справа
    mask = base.resize((w, h), RS.BILINEAR)
    img = Image.composite(Image.new("RGB", (w, h), tuple(c2)),
                          Image.new("RGB", (w, h), tuple(c1)), mask)
    return img.convert("RGBA")


def pill(w, h, c1, c2, radius=14):
    """Градиентная кнопка с лёгким бликом сверху (размер в логических пикселях)."""
    img = gradient(w * S, h * S, c1, c2)
    gloss = Image.new("RGBA", img.size, (255, 255, 255, 0))
    ImageDraw.Draw(gloss).rectangle((0, 0, img.width, img.height // 2), fill=(255, 255, 255, 24))
    return round_corners(Image.alpha_composite(img, gloss), radius * S)


# ---------- баннер на главной ----------

PALETTES = {
    "sunset": dict(stops=[(0.0, (14, 18, 48)), (0.45, (66, 34, 118)), (0.75, (224, 92, 148)), (1.0, (255, 172, 112))],
                   far=(98, 54, 138), mid=(58, 38, 112), body=(20, 48, 46), top=(72, 214, 124), grid=(16, 40, 40),
                   sun=(255, 244, 214), glow=(255, 190, 130, 150), stars=(255, 255, 255)),
    "day": dict(stops=[(0.0, (60, 140, 232)), (0.7, (140, 200, 250)), (1.0, (214, 240, 255))],
                far=(104, 156, 134), mid=(70, 134, 100), body=(40, 100, 62), top=(96, 204, 100), grid=(30, 80, 48),
                sun=(255, 250, 205), glow=(255, 240, 170, 140), stars=None),
    "night": dict(stops=[(0.0, (4, 7, 22)), (0.6, (18, 26, 64)), (1.0, (42, 54, 112))],
                  far=(28, 36, 84), mid=(20, 26, 64), body=(14, 34, 40), top=(44, 156, 104), grid=(10, 26, 30),
                  sun=(228, 233, 248), glow=(150, 170, 255, 110), stars=(255, 255, 255)),
    "nether": dict(stops=[(0.0, (36, 5, 6)), (0.6, (110, 20, 12)), (1.0, (236, 92, 22))],
                   far=(92, 20, 18), mid=(60, 12, 12), body=(40, 10, 12), top=(196, 62, 30), grid=(28, 6, 8),
                   sun=(255, 206, 90), glow=(255, 120, 40, 170), stars=(255, 150, 60)),
    "end": dict(stops=[(0.0, (6, 3, 14)), (0.7, (26, 14, 46)), (1.0, (56, 40, 90))],
                far=(64, 52, 94), mid=(46, 38, 76), body=(166, 166, 118), top=(214, 214, 152), grid=(128, 128, 88),
                sun=(36, 12, 48), glow=(174, 72, 236, 130), stars=(255, 255, 255)),
}
PALETTE_ORDER = ["sunset", "day", "night", "nether", "end"]


def palette_for(version):
    """Каждой версии Minecraft — свой фон баннера (стабильно: одна версия = один пейзаж)."""
    import re
    m = re.search(r"(\d+)\.(\d+)", version or "")
    if not m:
        return "end" if version else "sunset"
    return PALETTE_ORDER[(int(m.group(1)) * 7 + int(m.group(2))) % len(PALETTE_ORDER)]


def banner(w, h, badge, title, subtitle, palette="sunset", accent="#4ade80", seed=11):
    """Пиксельный пейзаж в стиле игры; цвета зависят от палитры."""
    P = PALETTES.get(palette, PALETTES["sunset"])
    W, H = w * S, h * S
    rnd = random.Random(seed)

    stops = P["stops"]
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / max(1, H - 1)
        col = stops[-1][1]
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                col = mix(c0, c1, (t - t0) / (t1 - t0))
                break
        d.line([(0, y), (W, y)], fill=col)
    img = img.convert("RGBA")

    if P["stars"]:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for _ in range(max(24, W * H // 14000)):
            x, y = rnd.randrange(W), rnd.randrange(int(H * 0.5))
            s = rnd.choice((S, S, 2 * S))
            od.rectangle((x, y, x + s - 1, y + s - 1), fill=P["stars"] + (rnd.randrange(70, 200),))
        img = Image.alpha_composite(img, ov)

    sx, sy, ss = int(W * 0.74), int(H * 0.30), 30 * S
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    k = ss * 2.2
    ImageDraw.Draw(glow).ellipse((sx - k, sy - k, sx + k, sy + k), fill=P["glow"])
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(ss * 0.9)))
    d = ImageDraw.Draw(img)
    d.rectangle((sx - ss // 2, sy - ss // 2, sx + ss // 2, sy + ss // 2), fill=P["sun"])
    d.rectangle((sx - ss // 2 + 3 * S, sy - ss // 2 + 3 * S, sx + ss // 2 - 3 * S, sy + ss // 2 - 3 * S),
                fill=mix(P["sun"], (255, 255, 255), 0.5))

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    b = 12 * S
    for _ in range(4):
        cx = rnd.randrange(int(W * 0.1), W)
        cy = rnd.randrange(int(H * 0.12), int(H * 0.42))
        n = rnd.randrange(4, 8)
        od.rectangle((cx, cy, cx + n * b, cy + b), fill=(255, 255, 255, 30))
        od.rectangle((cx + b, cy - b, cx + (n - 1) * b, cy), fill=(255, 255, 255, 30))
    img = Image.alpha_composite(img, ov)

    d = ImageDraw.Draw(img)

    def hills(bs, base, amp, body, top=None, grid=None):
        hgt, tops = 0, []
        for c in range(W // bs + 2):
            hgt = max(-amp, min(amp, hgt + rnd.choice((-1, 0, 0, 1))))
            x, y = c * bs, min(int(H * base) - hgt * bs, H - bs)
            d.rectangle((x, y, x + bs, H), fill=body)
            if top:
                d.rectangle((x, y, x + bs, y + bs), fill=top)
            if grid:
                d.line([(x, y), (x, H)], fill=grid)
                for gy in range(y + bs, H, bs):
                    d.line([(x, gy), (x + bs, gy)], fill=grid)
            tops.append((x, y))
        return tops

    hills(10 * S, 0.74, 5, P["far"])
    hills(14 * S, 0.82, 4, P["mid"])
    bs = 16 * S
    tops = hills(bs, 0.91, 3, P["body"], P["top"], P["grid"])
    if palette in ("sunset", "day", "night"):
        last = -10 ** 9
        for x, y in tops:
            if x > W * 0.5 and x - last > 6 * bs and rnd.random() < 0.2:
                last = x
                d.rectangle((x, y - 3 * bs, x + bs, y), fill=(96, 64, 44))
                d.rectangle((x - bs, y - 5 * bs, x + 2 * bs, y - 3 * bs), fill=(34, 138, 86))
                d.rectangle((x, y - 6 * bs, x + bs, y - 5 * bs), fill=(52, 176, 108))

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    span = int(W * 0.65)
    for x in range(span):
        a = int(205 * (1 - x / span) ** 1.5)
        od.line([(x, 0), (x, H)], fill=(9, 11, 18, a))
    img = Image.alpha_composite(img, ov)
    img = round_corners(img, 22 * S)

    t = ImageDraw.Draw(img, "RGBA")
    t.text((30 * S, 26 * S), badge.upper(), font=pil_font(11 * S, True), fill=hex_rgb(accent) + (255,))
    t.text((30 * S + S, 46 * S + S), title, font=pil_font(34 * S, True), fill=(0, 0, 0, 110))
    t.text((30 * S, 46 * S), title, font=pil_font(34 * S, True), fill=(255, 255, 255, 255))
    t.text((31 * S, 100 * S), subtitle, font=pil_font(14 * S), fill=(214, 220, 234, 235))
    return img


# ---------- логотип и иконки ----------

def logo(size=44, c1="#4ade80", c2="#22d3ee"):
    N = size * S * 2
    img = round_corners(gradient(N, N, hex_rgb(c1), hex_rgb(c2)), int(N * 0.28))
    d = ImageDraw.Draw(img, "RGBA")
    f = pil_font(N * 0.50, True)
    bb = d.textbbox((0, 0), "YL", font=f)
    x = (N - (bb[2] - bb[0])) / 2 - bb[0]
    y = (N - (bb[3] - bb[1])) / 2 - bb[1]
    d.text((x + N * 0.012, y + N * 0.016), "YL", font=f, fill=(0, 0, 0, 60))
    d.text((x, y), "YL", font=f, fill=(5, 35, 19, 255))
    return img.resize((size * S, size * S), RS.LANCZOS)


def nav_icon(kind, color, size=20):
    c = hex_rgb(color) + (255,)
    clear = hex_rgb(color) + (0,)
    N = 96
    im = Image.new("RGBA", (N, N), clear)
    d = ImageDraw.Draw(im)
    if kind == "play":
        pts = [(30, 18), (30, 78), (80, 48)]
        d.polygon(pts, fill=c)
        d.line(pts + [pts[0]], fill=c, width=10, joint="curve")
    elif kind == "mods":
        d.rounded_rectangle((14, 14, 44, 44), 9, fill=c)
        d.rounded_rectangle((52, 14, 82, 44), 9, outline=c, width=7)
        d.rounded_rectangle((14, 52, 44, 82), 9, outline=c, width=7)
        d.rounded_rectangle((52, 52, 82, 82), 9, fill=c)
    elif kind == "builds":  # слои
        for y, a in ((16, 255), (38, 200), (60, 150)):
            d.rounded_rectangle((12, y, 84, y + 20), 8, fill=c[:3] + (a,))
    elif kind == "servers":
        for y in (14, 52):
            d.rounded_rectangle((12, y, 84, y + 30), 9, outline=c, width=7)
            d.ellipse((24, y + 9, 34, y + 19), fill=c)
    elif kind == "worlds":  # глобус
        d.ellipse((14, 14, 82, 82), outline=c, width=7)
        d.ellipse((34, 14, 62, 82), outline=c, width=5)
        d.line([(14, 48), (82, 48)], fill=c, width=5)
    elif kind == "shop":  # пакет с покупками
        d.line([(30, 26), (30, 20), (38, 12), (58, 12), (66, 20), (66, 26)], fill=c, width=6, joint="curve")
        d.rounded_rectangle((18, 26, 78, 82), 10, outline=c, width=7)
    elif kind == "char":  # человек
        d.ellipse((36, 12, 60, 36), outline=c, width=7)
        d.line([(48, 36), (48, 58)], fill=c, width=7)
        d.line([(26, 48), (48, 44), (70, 48)], fill=c, width=7, joint="curve")
        d.line([(48, 58), (34, 82)], fill=c, width=7)
        d.line([(48, 58), (62, 82)], fill=c, width=7)
    elif kind == "shots":
        d.rounded_rectangle((10, 18, 86, 78), 12, outline=c, width=7)
        d.ellipse((24, 30, 38, 44), fill=c)
        d.polygon([(20, 70), (44, 46), (58, 60), (68, 52), (78, 70)], fill=c)
    elif kind == "log":
        d.rounded_rectangle((10, 16, 86, 80), 12, outline=c, width=7)
        d.line([(26, 36), (40, 48), (26, 60)], fill=c, width=7, joint="curve")
        d.line([(48, 62), (68, 62)], fill=c, width=7)
    elif kind == "stats":
        for x, top in ((16, 50), (40, 20), (64, 36)):
            d.rounded_rectangle((x, top, x + 18, 80), 6, fill=c)
    else:  # settings: ползунки
        for y, kx in ((24, 62), (48, 34), (72, 64)):
            d.line([(12, y), (84, y)], fill=c, width=8)
            d.ellipse((kx - 13, y - 13, kx + 13, y + 13), fill=c)
            d.ellipse((kx - 6, y - 6, kx + 6, y + 6), fill=clear)
    return im.resize((size * S, size * S), RS.LANCZOS)


def identicon(name, size=40):
    """Симметричный пиксельный аватар, одинаковый для одного и того же ника."""
    h = hashlib.md5((name or "?").encode("utf-8")).digest()
    hue = h[0] / 255
    fg, bg = _hsv(hue, 0.55, 0.96), _hsv(hue, 0.5, 0.22)
    N, cell = 80, 12
    off = (N - 5 * cell) // 2
    im = Image.new("RGBA", (N, N), bg + (255,))
    d = ImageDraw.Draw(im)
    for i in range(15):
        if h[1 + i] & 1:
            r, c = divmod(i, 3)
            for cc in {c, 4 - c}:
                x, y = off + cc * cell, off + r * cell
                d.rounded_rectangle((x, y, x + cell - 1, y + cell - 1), 2, fill=fg)
    return round_corners(im.resize((size * S, size * S), RS.LANCZOS), 12 * S)


# ---------- иконки модов ----------

def placeholder_icon(title, color=None, size=52):
    """Плитка с первой буквой, пока настоящая иконка грузится (или её нет)."""
    if isinstance(color, int):
        base = ((color >> 16) & 255, (color >> 8) & 255, color & 255)
    else:
        base = _hsv(hashlib.md5(title.encode("utf-8")).digest()[0] / 255, 0.5, 0.8)
    px = size * S
    im = Image.new("RGBA", (px, px), mix((20, 24, 36), base, 0.45) + (255,))
    d = ImageDraw.Draw(im, "RGBA")
    f = pil_font(px * 0.46, True)
    ch = (title.strip()[:1] or "?").upper()
    bb = d.textbbox((0, 0), ch, font=f)
    d.text(((px - (bb[2] - bb[0])) / 2 - bb[0], (px - (bb[3] - bb[1])) / 2 - bb[1]),
           ch, font=f, fill=(255, 255, 255, 235))
    return round_corners(im, 12 * S)


def process_icon(raw, size=52):
    """Байты картинки -> квадратная иконка со скруглением. Бросает исключение для svg и мусора."""
    px = size * S
    src = Image.open(BytesIO(raw))
    src.load()
    src = ImageOps.fit(src.convert("RGBA"), (px, px), RS.LANCZOS)
    tile = Image.new("RGBA", (px, px), (24, 29, 43, 255))
    return round_corners(Image.alpha_composite(tile, src), 12 * S)


def skin_face(path, size=40):
    """Голова из файла скина (с внешним слоем) для аватарки аккаунта."""
    im = Image.open(path).convert("RGBA")
    k = max(1, im.width // 64)
    face = im.crop((8 * k, 8 * k, 16 * k, 16 * k))
    hat = im.crop((40 * k, 8 * k, 48 * k, 16 * k))
    face = Image.alpha_composite(face, hat)
    return round_corners(face.resize((size * S, size * S), RS.NEAREST), 10 * S)


def lobby_backdrop(w, h, character=None, accent="#4ade80", light=False):
    """Фон лобби: лучи из центра, блёстки, посередине — персонаж. light = светлая тема."""
    W, H = max(w, 64), max(h, 64)
    bgc = (246, 245, 243) if light else (11, 13, 19)
    bg = Image.new("RGBA", (W, H), bgc + (255,))
    d = ImageDraw.Draw(bg, "RGBA")
    cx, cy = W // 2, int(H * 0.44)
    acc = hex_rgb(accent)
    # расходящиеся лучи
    n = 18
    far = int(math.hypot(W, H))
    for i in range(n):
        ang = i / n * math.tau
        spread = math.tau / n * 0.30
        alpha = (9 if i % 2 else 16) if light else (14 if i % 2 else 22)
        shade = (20, 20, 24) if light else (255, 255, 255)
        pts = [(cx, cy),
               (cx + math.cos(ang - spread) * far, cy + math.sin(ang - spread) * far),
               (cx + math.cos(ang + spread) * far, cy + math.sin(ang + spread) * far)]
        d.polygon(pts, fill=shade + (alpha,))
    # мягкое свечение за персонажем
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((cx - W // 4, cy - W // 4, cx + W // 4, cy + W // 4),
                                 fill=acc + (30 if light else 36,))
    bg = Image.alpha_composite(bg, glow.filter(ImageFilter.GaussianBlur(60)))
    d = ImageDraw.Draw(bg, "RGBA")
    # блёстки
    rnd = random.Random(42)
    for _ in range(max(30, W * H // 9000)):
        x, y = rnd.randrange(W), rnd.randrange(H)
        s = rnd.choice((2 * S, 3 * S, 4 * S))
        if light:
            col = (28, 25, 22) if rnd.random() < 0.7 else acc
            a = rnd.randrange(30, 90)
        else:
            col = (255, 255, 255) if rnd.random() < 0.7 else acc
            a = rnd.randrange(40, 140)
        d.rectangle((x, y, x + s, y + s), fill=col + (a,))
    if character is not None:
        ch = character
        target_h = int(H * 0.86)
        tw = int(ch.width * target_h / ch.height)
        ch = ch.resize((tw, target_h), RS.LANCZOS)
        shadow = Image.new("RGBA", (tw * 2, target_h // 5), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).ellipse((tw // 3, 0, tw + tw // 3, target_h // 5),
                                       fill=(0, 0, 0, 70 if light else 90))
        bg.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8)), (cx - tw, int(H * 0.95)))
        bg.alpha_composite(ch, (cx - tw // 2, int(H * 0.97) - target_h))
    return round_corners(bg, 22 * S)


