"""Настоящий вращаемый 3D-персонаж: модель игрока собирается из боксов,
натянутых на текстуры скина, с перспективой и сортировкой граней.
Крутится мышкой (yaw/pitch). Косметика: шляпа/маска (шляпный слой скина),
плащ и крылья — тоже объёмные."""
import math
from io import BytesIO

from PIL import Image

from cosmetics import _cape_image, _wings_image, default_skin, _overlay_image

F = 60.0  # фокусное расстояние (мягкая перспектива)


# ---------- построение модели ----------

def _mkbox(cx, cy, cz, sx, sy, sz, faces):
    """faces: {сторона: (u1,v1,u2,v2)}. Грани: +x -x +y -y +z -z.
    Возвращает [(нормаль, [4 угла TL,TR,BR,BL], uv)] в координатах модели."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    x0, x1 = cx - hx, cx + hx
    y0, y1 = cy - hy, cy + hy
    z0, z1 = cz - hz, cz + hz
    corners = {
        "+x": [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)],
        "-x": [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
        "+z": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        "-z": [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)],
        "+y": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
        "-y": [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
    }
    normals = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1),
               "-z": (0, 0, -1), "+y": (0, -1, 0), "-y": (0, 1, 0)}
    return [(normals[k], corners[k], uv) for k, uv in faces.items()]


HEAD_FACES = {"+x": (0, 8, 8, 16), "-x": (16, 8, 24, 16), "+z": (24, 8, 32, 16),
              "-z": (8, 8, 16, 16), "+y": (8, 0, 16, 8), "-y": (16, 0, 24, 8)}
BODY_FACES = {"+x": (16, 20, 20, 32), "-x": (28, 20, 32, 32), "+z": (32, 20, 40, 32),
              "-z": (20, 20, 28, 32), "+y": (20, 16, 28, 20), "-y": (28, 16, 36, 20)}
ARM_R_FACES = {"+x": (40, 20, 44, 32), "-x": (48, 20, 52, 32), "+z": (52, 20, 56, 32),
               "-z": (44, 20, 48, 32), "+y": (44, 16, 48, 20), "-y": (48, 16, 52, 20)}
LEG_R_FACES = {"+x": (0, 20, 4, 32), "-x": (8, 20, 12, 32), "+z": (12, 20, 16, 32),
               "-z": (4, 20, 8, 32), "+y": (4, 16, 8, 20), "-y": (8, 16, 12, 20)}
HAT_FACES = {"+x": (32, 8, 40, 16), "-x": (48, 8, 56, 16), "+z": (56, 8, 64, 16),
             "-z": (40, 8, 48, 16), "+y": (40, 0, 48, 8), "-y": (48, 0, 56, 8)}

# второй слой скина (64x64): объёмные волосы, куртки, накладки
OVERLAYS = [
    # (центр, размер, uv-карта)
    ((0, -10, 0), (8.6, 8.6, 8.6),
     {"+x": (32, 8, 40, 16), "-x": (48, 8, 56, 16), "+z": (56, 8, 64, 16),
      "-z": (40, 8, 48, 16), "+y": (40, 0, 48, 8), "-y": (48, 0, 56, 8)}),
    ((0, 0, 0), (8.4, 12.4, 4.4),
     {"+x": (16, 36, 20, 48), "-x": (28, 36, 32, 48), "+z": (32, 36, 40, 48),
      "-z": (20, 36, 28, 48), "+y": (20, 32, 28, 36), "-y": (28, 32, 36, 36)}),
    ((6, 0, 0), (4.3, 12.3, 4.3),
     {"+x": (40, 36, 44, 48), "-x": (48, 36, 52, 48), "+z": (52, 36, 56, 48),
      "-z": (44, 36, 48, 48), "+y": (44, 32, 48, 36), "-y": (48, 32, 52, 36)}),
    ((-6, 0, 0), (4.3, 12.3, 4.3),
     {"+x": (56, 52, 60, 64), "-x": (48, 52, 52, 64), "+z": (60, 52, 64, 64),
      "-z": (52, 52, 56, 64), "+y": (52, 48, 56, 52), "-y": (56, 48, 60, 52)}),
    ((2, 12, 0), (4.3, 12.3, 4.3),
     {"+x": (0, 36, 4, 48), "-x": (8, 36, 12, 48), "+z": (12, 36, 16, 48),
      "-z": (4, 36, 8, 48), "+y": (4, 32, 8, 36), "-y": (8, 32, 12, 36)}),
    ((-2, 12, 0), (4.3, 12.3, 4.3),
     {"+x": (8, 52, 12, 64), "-x": (0, 52, 4, 64), "+z": (12, 52, 16, 64),
      "-z": (4, 52, 8, 64), "+y": (4, 48, 8, 52), "-y": (8, 48, 12, 52)}),
]


def _region_used(tex, uv):
    """Есть ли в области скина хоть один непрозрачный пиксель."""
    x1, y1, x2, y2 = [int(v) for v in uv]
    lo, hi = tex.crop((x1, y1, x2, y2)).getchannel("A").getextrema()
    return hi > 0


def build_model(skin, equipped, pose=None, item_levels=None):
    """Список граней: [(нормаль, углы, uv, texture_image)].
    HD-скины (128+): модель и UV умножаются на k. pose: эмоция правой руки."""
    k = skin.width / 64.0
    tall = skin.height >= 64
    faces = []
    for f in _mkbox(0, -10, 0, 8, 8, 8, HEAD_FACES):
        faces.append((*f, skin))
    for f in _mkbox(0, 0, 0, 8, 12, 4, BODY_FACES):
        faces.append((*f, skin))
    # левые конечности в 64x64 лежат в нижней половине текстуры (y 48-64)
    arm_l = {"+x": (40, 52, 44, 64), "-x": (32, 52, 36, 64), "+z": (44, 52, 48, 64),
             "-z": (36, 52, 40, 64), "+y": (36, 48, 40, 52), "-y": (40, 48, 44, 52)}
    leg_l = {"+x": (24, 52, 28, 64), "-x": (16, 52, 20, 64), "+z": (28, 52, 32, 64),
             "-z": (20, 52, 24, 64), "+y": (20, 48, 24, 52), "-y": (24, 48, 28, 52)}
    if not tall:  # старый формат 64x32: левые конечности — зеркала правых
        arm_l = ARM_R_FACES
        leg_l = LEG_R_FACES
    for f in _mkbox(6, 0, 0, 4, 12, 4, ARM_R_FACES):
        faces.append((*f, skin))
    for f in _mkbox(-6, 0, 0, 4, 12, 4, arm_l):
        faces.append((*f, skin))
    for f in _mkbox(2, 12, 0, 4, 12, 4, LEG_R_FACES):
        faces.append((*f, skin))
    for f in _mkbox(-2, 12, 0, 4, 12, 4, leg_l):
        faces.append((*f, skin))

    # второй слой скина: рисуем только непустые области
    if tall:
        for (ccx, ccy, ccz), (sx, sy, sz), uvmap in OVERLAYS:
            if not any(_region_used(skin, uv) for uv in uvmap.values()):
                continue
            for f in _mkbox(ccx, ccy, ccz, sx, sy, sz, uvmap):
                faces.append((*f, skin))

    eq = equipped or {}
    if eq.get("cape"):
        tex = _cape_image(eq["cape"]).crop((12, 1, 22, 17))
        lvl = (item_levels or {}).get(eq["cape"], 1)
        if lvl and lvl > 1:
            from PIL import ImageEnhance
            tex = ImageEnhance.Brightness(tex).enhance(1.0 + 0.15 * (lvl - 1))
        uv = (0, 0, 9, 15)
        thin = {side: uv for side in ("+x", "-x", "+y", "-y")}
        # плащ висит на спине: уже корпуса, ниже плеч — руки не перекрывает
        for f in _mkbox(0, 1, 3.2, 9, 15, 0.8, {**thin, "+z": uv, "-z": uv}):
            faces.append((*f, tex))
    if eq.get("wings"):
        wimg = _wings_image(eq["wings"], 64)
        for side in (1, -1):
            tex = wimg.crop((2, 6, 30, 60) if side > 0 else (34, 6, 62, 60))
            uv = (0, 0, 28, 54)
            thin = {s: uv for s in ("+x", "-x", "+y", "-y")}
            for f in _mkbox(side * 2.6, -1, 3.4, 4.4, 13, 0.7,
                            {**thin, "+z": uv, "-z": uv}):
                faces.append((*f, tex))
    hat_item = eq.get("hat")
    if hat_item:
        tex = _overlay_image(hat_item)
        for f in _mkbox(0, -10, 0, 9.2, 9.2, 9.2, HAT_FACES):
            faces.append((*f, tex))
    if eq.get("face"):
        tex = _overlay_image(eq["face"])
        for f in _mkbox(0, -10, 0, 8.6, 8.6, 8.6, HAT_FACES):
            faces.append((*f, tex))

    # HD-скин: масштабируем ВСЕ боксы (косметика тоже)
    if k != 1.0:
        faces = [(n, [(x * k, y * k, z * k) for x, y, z in corners], uv, tex)
                 for n, corners, uv, tex in faces]

    # эмоции: правая рука поднимается от плеча
    if pose == "wave":
        piv = (4 * k, -2 * k, 0)
        ang = -1.1
        ca, sa = math.cos(ang), math.sin(ang)
        waved = []
        for n, corners, uv, tex in faces:
            xs = [c[0] for c in corners]
            ys = [c[1] for c in corners]
            is_rarm = (4 * k - 0.1 <= min(xs) and max(xs) <= 8 * k + 0.1
                       and -6 * k - 0.1 <= min(ys) and max(ys) <= 6 * k + 0.1)
            if not is_rarm:
                waved.append((n, corners, uv, tex))
                continue
            nc = []
            for x, y, z in corners:
                dx, dy = x - piv[0], y - piv[1]
                nc.append((piv[0] + dx, piv[1] + dx * sa + dy * ca, z))
            waved.append((n, nc, uv, tex))
        faces = waved
    return faces


# ---------- математика ----------

def _rotate(p, yaw, pitch):
    x, y, z = p
    xr = x * math.cos(yaw) + z * math.sin(yaw)
    zr = -x * math.sin(yaw) + z * math.cos(yaw)
    yr = y * math.cos(pitch) - zr * math.sin(pitch)
    zr2 = y * math.sin(pitch) + zr * math.cos(pitch)
    return xr, yr, zr2


def _solve8(A, b):
    """Гаусс для системы 8x8 (коэффициенты перспективы)."""
    M = [row[:] + [bv] for row, bv in zip(A, b)]
    n = 8
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        if abs(pv) < 1e-12:
            return None
        M[col] = [v / pv for v in M[col]]
        for r in range(n):
            if r != col and M[r][col]:
                k = M[r][col]
                M[r] = [v - k * w for v, w in zip(M[r], M[col])]
    return [M[i][n] for i in range(n)]


def _perspective_coeffs(dst, src):
    """coeffs для PIL PERSPECTIVE: выход (dst-квад) -> источник (src-квад)."""
    A, b = [], []
    for (dx, dy), (sx, sy) in zip(dst, src):
        A.append([dx, dy, 1, 0, 0, 0, -dx * sx, -dy * sx]); b.append(sx)
        A.append([0, 0, 0, dx, dy, 1, -dx * sy, -dy * sy]); b.append(sy)
    return _solve8(A, b)


# ---------- рендер ----------

def render_3d(skin_bytes, equipped=None, yaw=0.0, pitch=-0.10, height=560, aura=True, pose=None, item_levels=None):
    """Рисует персонажа под углом (yaw — вращение мышкой, pitch — наклон камеры)."""
    from cosmetics import _aura_image
    if skin_bytes:
        try:
            skin = Image.open(BytesIO(skin_bytes)).convert("RGBA")
        except Exception:
            skin = default_skin()
    else:
        skin = default_skin()

    cw = max(120, int(height * 0.75))
    ch = int(height)
    mk = skin.width / 64.0  # HD-скины: модель крупнее во столько же раз
    scale = ch * 0.92 / (34.0 * mk)
    cx, cy = cw / 2, ch / 2 - 2 * scale * mk
    faces = build_model(skin, equipped, pose=pose)

    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    if aura and (equipped or {}).get("aura"):
        canvas.alpha_composite(_aura_image((equipped or {})["aura"], cw // 2),
                               (cw // 4, ch // 5))

    prepared = []
    for normal, corners, uv, tex in faces:
        pts3 = [_rotate(p, yaw, pitch) for p in corners]
        n = _rotate(normal, yaw, pitch)
        center = sum(p[0] for p in pts3) / 4, sum(p[1] for p in pts3) / 4, \
            sum(p[2] for p in pts3) / 4
        view = (center[0], center[1], center[2] + F)  # камера в (0,0,-F)
        if n[0] * view[0] + n[1] * view[1] + n[2] * view[2] >= 0:
            continue  # грань отвёрнута
        pts2 = []
        depth = 0.0
        for x, y, z in pts3:
            s = scale * F / (F + z)
            pts2.append((cx + x * s, cy + y * s))
            depth += z
        prepared.append((depth / 4, pts2, uv, tex))

    prepared.sort(key=lambda f: -f[0])  # дальние раньше
    for _depth, pts2, (u1, v1, u2, v2), tex in prepared:
        fk = tex.width / 64.0
        tex_face = tex.crop((int(u1 * fk), int(v1 * fk), int(u2 * fk), int(v2 * fk)))
        fw, fh = int(u2 - u1), int(v2 - v1)
        src = [(0, 0), (fw, 0), (fw, fh), (0, fh)]
        xs = [p[0] for p in pts2]
        ys = [p[1] for p in pts2]
        bx0, by0 = int(min(xs)) - 2, int(min(ys)) - 2
        bx1, by1 = int(max(xs)) + 3, int(max(ys)) + 3
        bw, bh = max(bx1 - bx0, 2), max(by1 - by0, 2)
        dst = [(x - bx0, y - by0) for x, y in pts2]
        coeffs = _perspective_coeffs(dst, src)
        if coeffs is None:
            continue
        try:
            tile = tex_face.transform((bw, bh), Image.PERSPECTIVE, coeffs,
                                      resample=Image.NEAREST, fillcolor=(0, 0, 0, 0))
        except Exception:
            continue
        canvas.alpha_composite(tile, (bx0, by0))
    return canvas
