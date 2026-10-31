"""Косметика Yrovee: каталог, редкости, отрисовка картинок, сундуки и экономика.

Все картинки предметов рисуются кодом (Pillow) — рисовать вручную ничего не нужно.
В игре видны: плащи и голова/лицо (через CustomSkinLoader). Крылья и аура —
на вкладке «Персонаж» в лаунчере.
"""
import random
from datetime import date
from io import BytesIO

from PIL import Image, ImageDraw

# ---------- каталог ----------

RARITIES = {  # ключ: (название, цвет, возврат за повтор)
    "common":   ("Обычный",    "#9aa3b2", 20),
    "uncommon": ("Необычный",  "#4ade80", 40),
    "rare":     ("Редкий",     "#38bdf8", 80),
    "epic":     ("Эпический",  "#a78bfa", 160),
    "mythic":   ("Мифический", "#fbbf24", 320),
}
SLOTS = {"cape": "Плащ", "wings": "Крылья", "hat": "Голова", "face": "Лицо", "aura": "Аура"}

# (id, название, слот, редкость)
ITEMS = [
    ("cape_gray", "Серый плащ", "cape", "common"),
    ("cape_stripe", "Полосатый плащ", "cape", "common"),
    ("cape_travel", "Плащ путешественника", "cape", "uncommon"),
    ("cape_pattern", "Плащ с узором", "cape", "uncommon"),
    ("cape_space", "Космо-плащ", "cape", "rare"),
    ("cape_beacon", "Плащ маяка", "cape", "rare"),
    ("cape_phoenix", "Плащ феникса", "cape", "epic"),
    ("cape_astro", "Плащ астронавта", "cape", "epic"),
    ("cape_yrovee", "Плащ Yrovee", "cape", "mythic"),
    ("cape_rainbow", "Радужный плащ", "cape", "mythic"),
    ("wings_paper", "Бумажные крылья", "wings", "common"),
    ("wings_wood", "Деревянные крылья", "wings", "uncommon"),
    ("wings_butterfly", "Крылья бабочки", "wings", "rare"),
    ("wings_crystal", "Кристалльные крылья", "wings", "epic"),
    ("wings_dragon", "Крылья дракона", "wings", "mythic"),
    ("hat_beanie", "Шапочка", "hat", "common"),
    ("hat_wizard", "Шляпа волшебника", "hat", "uncommon"),
    ("hat_headphones", "Наушники", "hat", "uncommon"),
    ("hat_crown", "Коронка", "hat", "rare"),
    ("hat_halo", "Нимб", "hat", "epic"),
    ("hat_fire", "Огненная корона", "hat", "mythic"),
    ("face_glasses", "Очки", "face", "common"),
    ("face_smile", "Маска смайла", "face", "uncommon"),
    ("face_bandana", "Бандана", "face", "uncommon"),
    ("face_fox", "Маска лисы", "face", "rare"),
    ("face_dragon", "Маска дракона", "face", "epic"),
    ("face_yl", "Маска YL", "face", "mythic"),
    ("fx_sparks", "Искры", "aura", "common"),
    ("fx_hearts", "Сердечки", "aura", "uncommon"),
    ("fx_snow", "Снежинки", "aura", "rare"),
    ("fx_aura", "Аура мифика", "aura", "mythic"),
    # зимний набор 0.12
    ("hat_ushanka", "Зимняя ушанка", "hat", "rare"),
    ("hat_elf", "Колпак эльфа", "hat", "uncommon"),
    ("hat_santa", "Шапка Деда Мороза", "hat", "epic"),
    ("hat_ice", "Ледяная корона", "hat", "mythic"),
    ("face_snowman", "Маска снеговика", "face", "uncommon"),
    ("wings_ice", "Ледяные крылья", "wings", "epic"),
    ("wings_gift", "Праздничные крылья", "wings", "rare"),
    ("cape_frost", "Морозный плащ", "cape", "rare"),
    ("cape_ny", "Новогодний плащ", "cape", "epic"),
    ("aura_snow", "Снежная аура", "aura", "rare"),
]
ITEM_MAP = {i[0]: i for i in ITEMS}

CHESTS = {  # id: (название, цена, шансы редкостей)
    "wood": ("Деревянный сундук", 50,
             {"common": .55, "uncommon": .27, "rare": .12, "epic": .05, "mythic": .01}),
    "iron": ("Железный сундук", 120,
             {"common": .36, "uncommon": .34, "rare": .21, "epic": .07, "mythic": .02}),
    "gold": ("Золотой сундук", 250,
             {"common": 0, "uncommon": .475, "rare": .35, "epic": .15, "mythic": .025}),
}
CHEST_IN_CHEST = 0.015     # шанс выпадения ещё одного сундука при открытии
HOURLY_CHANCE = 0.01       # шанс часового дропа за каждый полный час игры
HOURLY_CRYSTALS = (20, 100)
SECONDS_PER_CRYSTAL = 600  # 1 кристалл за 10 минут игры
DAILY_BONUS = 10
START_CRYSTALS = 50

# ---------- экономика (хранилище — config.json лаунчера) ----------

def balance(cfg):
    return int(cfg.get("crystals", START_CRYSTALS))


def add_crystals(cfg, n):
    cfg["crystals"] = max(0, balance(cfg) + int(n))


def owned(cfg):
    return set(cfg.get("cosmetics", {}).get("owned", []))


def equipped(cfg):
    return dict(cfg.get("cosmetics", {}).get("equipped", {}))


def set_equipped(cfg, slot, item_id):
    cos = cfg.setdefault("cosmetics", {"owned": list(owned(cfg)), "equipped": {}})
    cos.setdefault("owned", [])
    if item_id is None:
        cos["equipped"].pop(slot, None)
    else:
        cos["equipped"][slot] = item_id


def add_item(cfg, item_id):
    cos = cfg.setdefault("cosmetics", {"owned": [], "equipped": {}})
    if item_id not in cos["owned"]:
        cos["owned"].append(item_id)
        return True
    return False


def open_chest(cfg, chest_id, free=False):
    """Открывает сундук: списывает кристаллы (кроме бесплатных), выдаёт предмет
    (с дубликатами в кристаллы) и, с шансом CHEST_IN_CHEST, второй сундук каскадом.
    Возвращает (список_событий, ошибка). События: ("item", id, dup_bool) / ("chest", id)."""
    name, price, chances = CHESTS[chest_id]
    if not free:
        if balance(cfg) < price:
            return None, f"Не хватает кристаллов: нужно {price} 💎"
        add_crystals(cfg, -price)
    events = []
    pending = [chest_id]
    while pending:
        cid = pending.pop()
        rarity = random.choices(list(CHESTS[cid][2].keys()),
                                weights=list(CHESTS[cid][2].values()))[0]
        pool = [i for i in ITEMS if i[3] == rarity]
        item = random.choice(pool)
        dup = not add_item(cfg, item[0])
        events.append(("item", item[0], dup))
        if random.random() < CHEST_IN_CHEST:
            events.append(("chest", cid))
            pending.append(cid)
    return events, None


def playtime_reward(seconds):
    """Кристаллы за время игры."""
    return int(seconds // SECONDS_PER_CRYSTAL)


def hourly_rolls(cfg, seconds_played):
    """За каждый новый полный час игры — бросок 1%: предмет или 20-100 кристаллов.
    Возвращает (список_дропов, новый_итоговый_счётчик_часов)."""
    before = float(cfg.get("drop_hours", 0))
    after = before + seconds_played / 3600
    drops = []
    n = int(after) - int(before)
    for _ in range(min(n, 12)):  # защита от абсурдно больших значений
        if random.random() < HOURLY_CHANCE:
            if random.random() < 0.5:
                rarity = random.choices(
                    ["common", "uncommon", "rare", "epic", "mythic"],
                    weights=[55, 27, 12, 5, 1])[0]
                item = random.choice([i for i in ITEMS if i[3] == rarity])
                dup = not add_item(cfg, item[0])
                drops.append(("item", item[0], dup))
            else:
                amount = random.randint(*HOURLY_CRYSTALS)
                add_crystals(cfg, amount)
                drops.append(("crystals", amount))
    cfg["drop_hours"] = after
    return drops


def claim_daily(cfg):
    """Ежедневный бонус. Возвращает (получено, ошибка)."""
    today = date.today().isoformat()
    if cfg.get("last_daily") == today:
        return 0, "Ежедневный бонус уже получен — приходи завтра"
    cfg["last_daily"] = today
    add_crystals(cfg, DAILY_BONUS)
    return DAILY_BONUS, None


def redeem_promo(cfg, code, promos):
    """Промокод из data.js сайта. Возвращает (начислено, ошибка)."""
    code = (code or "").strip().upper()
    used = cfg.setdefault("promo_used", [])
    if not code:
        return 0, "Введи код"
    if code not in (promos or {}):
        return 0, "Такого кода нет (проверь канал и регистр)"
    if code in used:
        return 0, "Этот код уже использован"
    amount = int(promos[code])
    used.append(code)
    add_crystals(cfg, amount)
    return amount, None


# ---------- сундуки за игру (3 в день, каждый после часа игры) ----------

DAILY_CHESTS = 3
CHEST_HOUR = 3600  # секунд игры на один сундук


def today_str():
    return date.today().isoformat()


def _daily(cfg, key):
    d = cfg.setdefault(key, {"date": today_str(), "seconds": 0, "claimed": 0})
    if d.get("date") != today_str():
        cfg[key] = {"date": today_str(), "seconds": 0, "claimed": 0}
        return cfg[key]
    return d


def add_playtime(cfg, seconds):
    """Учитывает время игры за сегодня (для сундуков) и всего (для уровня)."""
    d = _daily(cfg, "daily_play")
    d["seconds"] = int(d.get("seconds", 0)) + int(seconds)
    cfg["playtime_hours"] = float(cfg.get("playtime_hours", 0)) + seconds / 3600
    ph = cfg.setdefault("play_history", {})
    ph[today_str()] = int(ph.get(today_str(), 0)) + int(seconds)


def playtime_chest_state(cfg):
    """(сколько можно забрать сейчас, всего за день, секунд до следующего)."""
    d = _daily(cfg, "daily_play")
    claimed = int(_daily(cfg, "daily_chests").get("claimed", 0))
    ready = min(int(d.get("seconds", 0) // CHEST_HOUR), DAILY_CHESTS) - claimed
    need = (claimed + max(ready, 0) + 1) * CHEST_HOUR - d.get("seconds", 0)
    return max(ready, 0), DAILY_CHESTS, max(need, 0)


def claim_playtime_chest(cfg):
    """Забирает заслуженный сундук (бесплатный, случайного уровня).
    Возвращает (события, ошибка) как open_chest."""
    ready, total, _need = playtime_chest_state(cfg)
    if ready <= 0:
        return None, "Сундук ещё не готов — играй в Minecraft"
    chest_id = random.choices(["wood", "iron", "gold"], weights=[60, 30, 10])[0]
    events, err = open_chest(cfg, chest_id, free=True)
    if err:
        return None, err
    _daily(cfg, "daily_chests")["claimed"] = int(_daily(cfg, "daily_chests").get("claimed", 0)) + 1
    bump_counter(cfg, "chests")
    out = []
    for ev in events:
        if ev[0] == "item":
            out.append(("item", chest_id, ev[1], ev[2]))
        else:
            out.append(("chest", chest_id))
    return out, None


def fmt_wait(seconds):
    m = int(seconds // 60)
    return f"{m // 60} ч {m % 60:02d} мин" if m >= 60 else f"{m} мин"


# ---------- уровень аккаунта и задания ----------

# (id, название, описание, цель, награда, метрика в cfg["quests"])
QUESTS = [
    ("launch10", "Разогрев", "Запусти игру 10 раз", 10, 50, "launches"),
    ("launch50", "Ветеран лаунчера", "Запусти игру 50 раз", 50, 150, "launches"),
    ("play1h", "Первый час", "Проведи в игре 1 час", 3600, 40, "playtime"),
    ("play10h", "Марафонец", "Проведи в игре 10 часов", 36000, 200, "playtime"),
    ("play50h", "Легенда", "Проведи в игре 50 часов", 180000, 500, "playtime"),
    ("mods5", "Коллекционер модов", "Установи 5 модов", 5, 50, "mods"),
    ("mods20", "Модоман", "Установи 20 модов", 20, 150, "mods"),
    ("build1", "Сборщик", "Установи сборку", 1, 30, "builds"),
    ("chest10", "Открыватель сундуков", "Открой 10 сундуков", 10, 60, "chests"),
    ("cos10", "Модник", "Получи 10 разных косметических предметов", 10, 100, "items"),
]

LEVEL_STEP = 3600  # каждый уровень = час суммарной игры


def level_of(cfg):
    return 1 + int(float(cfg.get("playtime_hours", 0)) // LEVEL_STEP)


def quest_progress(cfg, qid):
    q = next(q for q in QUESTS if q[0] == qid)
    claimed = cfg.get("quests_claimed", [])
    if qid in claimed:
        return None  # уже получено
    st = cfg.setdefault("quests", {})
    if q[5] == "playtime":
        cur = int(float(cfg.get("playtime_hours", 0)) * 3600)
    elif q[5] == "items":
        cur = len(owned(cfg))
    else:
        cur = int(st.get(q[5], 0))
    return min(cur, q[3]), q[3], q[4]


def claim_quest(cfg, qid):
    prog = quest_progress(cfg, qid)
    if prog is None:
        return 0, "Награда уже получена"
    cur, goal, reward = prog
    if cur < goal:
        return 0, f"Не выполнено: {cur}/{goal}"
    cfg.setdefault("quests_claimed", []).append(qid)
    add_crystals(cfg, reward)
    return reward, None


def bump_counter(cfg, metric, n=1):
    """Учитывает действия для заданий: launches/mods/builds/chests."""
    st = cfg.setdefault("quests", {})
    st[metric] = int(st.get(metric, 0)) + n


# ---------- адвент-календарь (1–24 декабря) ----------

ADVENT_ITEMS = ["hat_elf", "face_snowman", "hat_ushanka", "cape_frost",
                "wings_gift", "cape_ny", "aura_snow", "hat_santa",
                "wings_ice", "hat_ice"]
ADVENT_BIG_DAYS = {6: 40, 12: 60, 18: 80, 24: 120}


def advent_state(cfg):
    """None — не сезон. Иначе (открытые дни, доступна ли сегодняшняя дверца)."""
    today = date.today()
    if today.month != 12 or today.day > 24:
        return None
    a = cfg.setdefault("advent", {})
    if a.get("year") != today.year:
        cfg["advent"] = {"year": today.year, "opened": []}
    opened = cfg["advent"].setdefault("opened", [])
    return opened, today.day not in opened


def claim_advent(cfg):
    """Открывает сегодняшнюю дверцу. Возвращает (событие, ошибка)."""
    st = advent_state(cfg)
    if st is None:
        return None, "Адвент-календарь работает с 1 по 24 декабря"
    opened, can = st
    if not can:
        return None, "Дверца уже открыта — приходи завтра"
    day = date.today().day
    opened.append(day)
    if day in ADVENT_BIG_DAYS:
        item = ADVENT_ITEMS[(day // 6 - 1) % len(ADVENT_ITEMS)]
        dup = not add_item(cfg, item)
        add_crystals(cfg, ADVENT_BIG_DAYS[day])
        return ("item", item, dup, ADVENT_BIG_DAYS[day]), None
    amount = 20 + (day * 7) % 80
    add_crystals(cfg, amount)
    return ("crystals", amount), None


# ---------- сезонный пропуск (28 дней, бесплатно) ----------

SEASON_DAYS = 28


def season_state(cfg):
    """(день сезона 1..28, полученные дни). Автоматически начинает новый сезон."""
    from datetime import date as _d
    s = cfg.setdefault("season", {})
    if s.get("start"):
        try:
            start = _d.fromisoformat(s["start"])
        except ValueError:
            start = None
        if start and (_d.today() - start).days + 1 > SEASON_DAYS:
            s = {}
    if not s.get("start"):
        cfg["season"] = {"start": today_str(), "claimed": []}
        s = cfg["season"]
    day = min((_d.today() - _d.fromisoformat(s["start"])).days + 1, SEASON_DAYS)
    return day, s.setdefault("claimed", [])


def season_reward_preview(day):
    """(кристаллы, предмет или None) за день сезона."""
    crystals = 30 + day * 5
    item = None
    if day in (7, 14, 21):
        rarity = {7: "rare", 14: "epic", 21: "epic"}[day]
        item = random.choice([i for i in ITEMS if i[3] == rarity])[0]
    elif day == SEASON_DAYS:
        item = "cape_ny"
    return crystals, item


def claim_season(cfg):
    """Забирает награду текущего дня сезона. Возвращает (кристаллы, предмет, ошибка)."""
    day, claimed = season_state(cfg)
    if day in claimed:
        return None, None, "Награда за сегодня уже получена — приходи завтра"
    claimed.append(day)
    crystals, item = season_reward_preview(day)
    add_crystals(cfg, crystals)
    dup = False
    if item:
        dup = not add_item(cfg, item)
    return crystals, (item, dup), None


# ---------- отрисовка предметов ----------

def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _px(d, x, y, w, h, color):
    d.rectangle((x, y, x + w - 1, y + h - 1), fill=color)


def _rainbow(x, y):
    import colorsys
    return tuple(int(v * 255) for v in colorsys.hsv_to_rgb((x * 0.05 + y * 0.03) % 1.0, 0.9, 1.0))


def _cape_image(item_id):
    """Плащ в формате скина 64x32 (как у OptiFine/CSL)."""
    im = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    P = {
        "cape_gray":    [(70, 74, 88), (56, 60, 72)],
        "cape_stripe":  [(70, 74, 88), (222, 90, 90)],
        "cape_travel":  [(96, 74, 50), (222, 190, 120)],
        "cape_pattern": [(44, 62, 92), (120, 160, 220)],
        "cape_space":   [(16, 16, 40), (140, 130, 255)],
        "cape_beacon":  [(30, 80, 90), (120, 240, 230)],
        "cape_phoenix": [(140, 30, 20), (255, 150, 40)],
        "cape_astro":   [(230, 232, 240), (60, 70, 110)],
        "cape_yrovee":  [(46, 148, 96), (255, 255, 255)],
        "cape_rainbow": [None],
        "cape_frost":   [(70, 130, 190), (220, 245, 255)],
        "cape_ny":      [(30, 40, 60), (240, 70, 90)],
    }[item_id]
    base, accent = (P[0], P[1]) if len(P) == 2 else (None, None)
    if item_id == "cape_rainbow":
        for y in range(32):
            for x in range(0, 64, 2):
                _px(d, x, y, 2, 1, _rainbow(x // 2, y) + (255,))
        return im
    for y in range(32):
        for x in range(0, 64, 2):
            c = base if (x // 2 + y) % 7 else mix_dark(base)
            _px(d, x, y, 2, 1, c + (255,))
    # акцентная полоса/эмблема
    if item_id == "cape_stripe":
        _px(d, 0, 12, 64, 6, accent + (255,))
    elif item_id == "cape_travel":
        _px(d, 0, 4, 64, 3, accent + (255,))
        _px(d, 0, 24, 64, 3, accent + (255,))
    elif item_id == "cape_pattern":
        for y in range(0, 32, 8):
            for x in range(0, 64, 8):
                _px(d, x + 2, y + 2, 4, 4, accent + (255,))
    elif item_id == "cape_space":
        rnd = random.Random(7)
        for _ in range(40):
            x, y = rnd.randrange(62), rnd.randrange(30)
            _px(d, x, y, 1, 1, (255, 255, 255, 255))
    elif item_id == "cape_beacon":
        for y in range(4, 28, 6):
            _px(d, 0, y, 64, 2, accent + (255,))
    elif item_id == "cape_phoenix":
        for y in range(0, 32):
            k = 1 - abs(y - 16) / 16
            _px(d, 0, y, 64, 1, mix_dark(accent, 1 - k * 0.7) + (255,))
    elif item_id == "cape_astro":
        _px(d, 0, 6, 64, 20, accent + (255,))
        _px(d, 24, 10, 16, 12, (255, 90, 90, 255))
    elif item_id == "cape_yrovee":
        _px(d, 24, 8, 16, 14, (255, 255, 255, 255))
        _px(d, 27, 11, 4, 8, (6, 30, 16, 255))
        _px(d, 33, 11, 4, 8, (6, 30, 16, 255))
    elif item_id == "cape_frost":
        rndf = random.Random(11)
        for _ in range(30):
            x, y = rndf.randrange(62), rndf.randrange(30)
            _px(d, x, y, 1, 1, (230, 250, 255, 255))
        _px(d, 0, 14, 64, 2, (220, 245, 255, 255))
    elif item_id == "cape_ny":
        for y in range(0, 32):
            for x in range(0, 64, 2):
                _px(d, x, y, 2, 1, ((30, 40, 60) if (x // 2 + y) % 2 else (240, 70, 90)) + (255,))
        _px(d, 26, 10, 12, 6, (250, 210, 90, 255))
    return im


def mix_dark(c, k=0.72):
    return tuple(int(v * k) for v in c)


def _wings_image(item_id, size=64):
    """Превью крыльев: два симметричных крыла из слоёв-перьев."""
    S = 2
    W = size * S
    im = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    P = {
        "wings_paper":   ((228, 226, 214), (188, 186, 174)),
        "wings_wood":    ((128, 92, 54), (94, 66, 38)),
        "wings_butterfly": ((64, 124, 235), (242, 104, 184)),
        "wings_crystal": ((124, 222, 255), (62, 132, 232)),
        "wings_dragon":  ((74, 38, 104), (208, 70, 238)),
        "wings_ice":     ((190, 235, 255), (110, 180, 240)),
        "wings_gift":    ((240, 70, 90), (250, 210, 90)),
    }[item_id]
    c1 = tuple(P[0]) + (238,)
    c2 = tuple(P[1]) + (238,)
    cx, cy = W // 2, int(W * 0.18)
    for side in (-1, 1):
        for i in range(4):  # перья сверху вниз, каждое короче
            length = int(W * (0.42 - i * 0.075))
            thick = max(int(W * 0.10) - i * 2 * S, 2 * S)
            y = cy + i * int(W * 0.115)
            x0 = cx + (3 * S if side > 0 else -3 * S - length) + (0 if side > 0 else 0)
            if side > 0:
                box = (cx + 3 * S + i * S, y, cx + 3 * S + i * S + length, y + thick)
            else:
                box = (cx - 3 * S - i * S - length, y, cx - 3 * S - i * S, y + thick)
            d.rounded_rectangle(box, radius=thick // 2, fill=c1 if i % 2 == 0 else c2)
        # косточка-основание
        d.rounded_rectangle((cx - 2 * S, cy, cx + 2 * S, cy + int(W * 0.42)),
                            radius=S, fill=c2)
    return im.resize((size, size), Image.Resampling.LANCZOS)


def _overlay_image(item_id):
    """Голова/лицо: PNG 64x64 в формате скина, заполнен только шляпный слой."""
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    FACE = (40, 8, 48, 16)   # перед шляпного слоя
    HAT_TOP = (40, 0, 48, 8)
    HAT_L, HAT_R, HAT_BACK = (32, 8, 40, 16), (48, 8, 56, 16), (56, 8, 64, 16)

    if item_id == "hat_beanie":
        _px(d, *FACE[:2], 8, 4, (70, 130, 210, 255))
        _px(d, *HAT_TOP[:2], 8, 8, (60, 115, 190, 255))
        _px(d, *HAT_L[:2], 8, 4, (55, 105, 175, 255))
        _px(d, *HAT_R[:2], 8, 4, (55, 105, 175, 255))
        _px(d, *HAT_BACK[:2], 8, 4, (55, 105, 175, 255))
    elif item_id == "hat_wizard":
        _px(d, 41, 8, 6, 2, (70, 50, 160, 255))
        _px(d, *HAT_TOP[:2], 8, 4, (90, 60, 200, 255))
        _px(d, *FACE[:2], 8, 2, (70, 50, 160, 255))
        _px(d, *HAT_L[:2], 8, 2, (70, 50, 160, 255))
        _px(d, *HAT_R[:2], 8, 2, (70, 50, 160, 255))
        _px(d, *HAT_BACK[:2], 8, 2, (70, 50, 160, 255))
        _px(d, 43, 1, 2, 3, (255, 220, 120, 255))  # звезда
    elif item_id == "hat_headphones":
        _px(d, 40, 8, 8, 1, (30, 30, 34, 255))
        _px(d, *HAT_L[:2], 2, 6, (30, 30, 34, 255))
        _px(d, 54, 8, 2, 6, (30, 30, 34, 255))
        _px(d, *HAT_R[:2], 2, 6, (74, 222, 128, 255))
    elif item_id == "hat_crown":
        _px(d, 40, 6, 8, 2, (250, 210, 90, 255))
        for x in (40, 43, 46):
            _px(d, x, 4, 2, 2, (250, 210, 90, 255))
        _px(d, 43, 6, 2, 2, (230, 70, 70, 255))
        _px(d, 40, 8, 8, 2, (250, 210, 90, 255))  # видна и спереди
    elif item_id == "hat_halo":
        _px(d, 40, 2, 8, 1, (255, 240, 150, 230))
        _px(d, 39, 3, 10, 1, (255, 240, 150, 160))
    elif item_id == "hat_fire":
        rnd = random.Random(3)
        for x in range(40, 48):
            h = rnd.randrange(2, 5)
            _px(d, x, 8 - h, 1, h, (255, 140 + rnd.randrange(80), 40, 255))
        _px(d, 40, 6, 8, 2, (250, 170, 60, 255))
        _px(d, 40, 8, 8, 2, (255, 150, 50, 255))  # фронтальная полоса короны
    elif item_id == "face_glasses":
        _px(d, 40, 11, 8, 1, (20, 20, 24, 255))
        _px(d, 40, 10, 3, 3, (40, 60, 110, 240))
        _px(d, 45, 10, 3, 3, (40, 60, 110, 240))
    elif item_id == "face_smile":
        _px(d, *FACE[:2], 8, 8, (250, 210, 70, 255))
        _px(d, 42, 10, 1, 2, (30, 30, 30, 255))
        _px(d, 45, 10, 1, 2, (30, 30, 30, 255))
        _px(d, 42, 13, 4, 1, (30, 30, 30, 255))
    elif item_id == "face_bandana":
        _px(d, *FACE[:2], 8, 3, (200, 60, 60, 255))
        _px(d, *HAT_BACK[:2], 8, 3, (200, 60, 60, 255))
        _px(d, 39, 8, 2, 3, (200, 60, 60, 255))
    elif item_id == "face_fox":
        _px(d, *FACE[:2], 8, 8, (230, 130, 60, 255))
        _px(d, 40, 8, 3, 2, (250, 240, 230, 255))
        _px(d, 45, 8, 3, 2, (250, 240, 230, 255))
        _px(d, 43, 13, 2, 2, (30, 20, 15, 255))
        _px(d, 41, 15, 1, 1, (30, 20, 15, 255))
        _px(d, 46, 15, 1, 1, (30, 20, 15, 255))
    elif item_id == "face_dragon":
        _px(d, *FACE[:2], 8, 8, (40, 60, 50, 255))
        _px(d, 40, 8, 2, 3, (250, 210, 80, 255))
        _px(d, 46, 8, 2, 3, (250, 210, 80, 255))
        for x in (41, 43, 45):
            _px(d, x, 13, 1, 2, (240, 240, 240, 255))
    elif item_id == "face_yl":
        _px(d, *FACE[:2], 8, 8, (16, 24, 38, 255))
        _px(d, 42, 10, 4, 4, (74, 222, 128, 255))
        _px(d, 43, 11, 1, 2, (16, 24, 38, 255))
        _px(d, 44, 11, 1, 2, (16, 24, 38, 255))
    elif item_id == "face_snowman":
        _px(d, *FACE[:2], 8, 8, (240, 245, 250, 255))
        _px(d, 42, 10, 1, 1, (30, 30, 30, 255))
        _px(d, 45, 10, 1, 1, (30, 30, 30, 255))
        _px(d, 42, 12, 4, 2, (240, 140, 50, 255))  # морковка
    elif item_id == "hat_ushanka":
        _px(d, *HAT_TOP[:2], 8, 6, (110, 75, 45, 255))
        _px(d, *FACE[:2], 8, 3, (110, 75, 45, 255))
        _px(d, *HAT_L[:2], 2, 8, (140, 100, 60, 255))
        _px(d, *HAT_R[:2], 2, 8, (140, 100, 60, 255))
        _px(d, 40, 11, 8, 1, (200, 170, 130, 255))  # опушка
    elif item_id == "hat_elf":
        _px(d, 41, 6, 6, 2, (60, 170, 90, 255))
        _px(d, *HAT_TOP[:2], 8, 4, (60, 170, 90, 255))
        _px(d, 43, 1, 2, 2, (250, 210, 90, 255))
        _px(d, *FACE[:2], 8, 1, (60, 170, 90, 255))
    elif item_id == "hat_santa":
        _px(d, *HAT_TOP[:2], 8, 5, (220, 50, 60, 255))
        _px(d, *FACE[:2], 8, 2, (220, 50, 60, 255))
        _px(d, 40, 10, 8, 1, (245, 245, 245, 255))
        _px(d, 46, 3, 2, 2, (245, 245, 245, 255))
    elif item_id == "hat_ice":
        rndi = random.Random(9)
        for x in range(40, 48):
            h = rndi.randrange(2, 5)
            _px(d, x, 8 - h, 1, h, (190, 235, 255, 255))
        _px(d, 40, 6, 8, 2, (150, 210, 245, 255))
        _px(d, 40, 8, 8, 2, (190, 235, 255, 255))
    return im


def _aura_image(item_id, size=64):
    """Частицы ауры: по краям силуэта, не поверх персонажа."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rnd = random.Random(hash(item_id) % 9999)
    colors = {
        "fx_sparks": (255, 220, 120), "fx_hearts": (250, 100, 120),
        "fx_snow": (200, 230, 255), "fx_aura": (190, 120, 255),
        "aura_snow": (225, 245, 255),
    }[item_id]
    placed = 0
    while placed < 14:  # только боковые и верхние зоны — центр не трогаем
        x = rnd.randrange(2, size - 6)
        y = rnd.randrange(2, size - 8)
        if size * 0.32 < x < size * 0.68:  # центр — там персонаж
            continue
        placed += 1
        s = rnd.choice((2, 3, 3))
        col = colors + (rnd.randrange(90, 200),)
        if item_id == "fx_hearts":
            d.ellipse((x, y, x + s, y + s), fill=col)
            d.ellipse((x + s, y, x + 2 * s, y + s), fill=col)
            d.polygon([(x, y + s // 2 + 1), (x + 2 * s, y + s // 2 + 1), (x + s, y + 2 * s)],
                      fill=col)
        else:
            d.ellipse((x, y, x + s, y + s), fill=col)
    return im


def item_image(item_id, size=48):
    """Картинка предмета для интерфейса (по слоту)."""
    item = ITEM_MAP.get(item_id)
    if item is None:
        im = Image.new("RGBA", (size, size), (30, 34, 48, 255))
        return im
    slot = item[2]
    if slot == "cape":
        im = _cape_image(item_id)
        im = im.crop((0, 0, 64, 32)).resize((size, size // 2), Image.Resampling.NEAREST)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(im, (0, size // 4))
        return canvas
    if slot == "wings":
        return _wings_image(item_id, size)
    if slot in ("hat", "face"):
        im = _overlay_image(item_id).crop((30, 0, 58, 24))
        return im.resize((size, int(size * 24 / 28)), Image.Resampling.NEAREST)
    return _aura_image(item_id, size)


def chest_image(chest_id, size=84):
    """Сундук в духе Minecraft: изометрический ящик с доской, крышкой и защёлкой."""
    K = 3
    W = size * K
    im = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    PAL = {  # (крышка, корпус, контур, бок)
        "wood": ((168, 122, 66), (136, 96, 50), (86, 60, 30), (112, 78, 40)),
        "iron": ((214, 220, 228), (176, 184, 194), (110, 118, 130), (152, 160, 172)),
        "gold": ((250, 208, 84), (232, 178, 44), (158, 116, 18), (216, 164, 34)),
    }[chest_id]
    lid_c, body_c, edge_c, side_c = (c + (255,) for c in PAL)
    x0, x1 = int(W * 0.15), int(W * 0.64)
    y0, y_split = int(W * 0.32), int(W * 0.50)
    y1 = int(W * 0.82)
    skew = int(W * 0.09)
    lift = int(skew * 0.55)

    # боковая грань
    d.polygon([(x1, y0), (x1 + skew, y0 - lift), (x1 + skew, y1 - lift), (x1, y1)],
              fill=side_c)
    # верх крышки (уходит в перспективу)
    d.polygon([(x0, y0), (x1, y0), (x1 + skew, y0 - lift), (x0 + skew, y0 - lift)],
              fill=tuple(min(255, c + 26) for c in lid_c[:3]) + (255,))
    # передняя крышка и корпус
    d.rectangle((x0, y0, x1, y_split), fill=lid_c)
    d.rectangle((x0, y_split, x1, y1), fill=body_c)
    # полосы-доски
    for fy in (y_split, y_split + (y1 - y_split) // 2):
        d.line([(x0 + K, fy), (x1 - K, fy)], fill=edge_c, width=K)
    for fx in (x0 + (x1 - x0) // 3, x0 + 2 * (x1 - x0) // 3):
        d.line([(fx, y_split + K), (fx, y1 - K)], fill=edge_c, width=K)
    # тёмный шов между крышкой и корпусом
    d.line([(x0, y_split), (x1, y_split)], fill=edge_c, width=K * 2)
    # контуры
    d.rectangle((x0, y0, x1, y_split), outline=edge_c, width=K)
    d.rectangle((x0, y_split, x1, y1), outline=edge_c, width=K)
    d.polygon([(x1, y0), (x1 + skew, y0 - lift), (x1 + skew, y1 - lift), (x1, y1)],
              outline=edge_c, width=K)
    d.line([(x0 + skew, y0 - lift), (x0, y0)], fill=edge_c, width=K)
    # защёлка
    lw, lh = int(W * 0.045), int(W * 0.075)
    lx = (x0 + x1) // 2 - lw // 2
    latch = (250, 214, 96) if chest_id != "gold" else (96, 84, 60)
    d.rounded_rectangle((lx, y_split - lh // 2, lx + 2 * lw, y_split + lh), radius=K * 2,
                        fill=latch + (255,), outline=edge_c, width=K)
    d.ellipse((lx + lw // 2 - K, y_split, lx + lw // 2 + K * 2, y_split + K * 3),
              fill=edge_c)
    return im.resize((size, size), Image.Resampling.LANCZOS)


# ---------- рендер персонажа ----------

def default_skin():
    """Скин Стива (64x64) — показывается, если игрок не загрузил свой."""
    rnd = random.Random(4)
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    skin, skin_d = (181, 136, 104), (162, 118, 88)
    hair, hair_d = (59, 42, 28), (48, 34, 22)
    shirt, shirt_d = (0, 148, 148), (0, 122, 122)
    pants, pants_d = (70, 92, 190), (58, 78, 165)
    shoe = (95, 95, 102)

    def px(x, y, w, h, c):
        d.rectangle((x, y, x + w - 1, y + h - 1), fill=tuple(c) + (255,))

    # голова: макушка, затылок, бока
    px(8, 0, 8, 8, hair)
    px(24, 8, 8, 8, hair)
    px(0, 8, 8, 8, hair); px(0, 11, 8, 5, skin)
    px(16, 8, 8, 8, hair); px(16, 11, 8, 5, skin)
    px(16, 8, 1, 8, hair_d)
    # лицо
    px(8, 8, 8, 8, skin)
    px(8, 8, 8, 2, hair)
    px(8, 8, 1, 6, hair)
    px(15, 8, 1, 6, hair)
    px(9, 12, 1, 1, (255, 255, 255))
    px(10, 12, 1, 1, (82, 62, 158))
    px(13, 12, 1, 1, (82, 62, 158))
    px(14, 12, 1, 1, (255, 255, 255))
    px(11, 13, 2, 1, skin_d)
    px(11, 14, 2, 1, (122, 82, 62))
    # тело (рубашка)
    px(20, 20, 8, 12, shirt)
    px(20, 20, 8, 1, shirt_d)
    px(32, 20, 8, 12, shirt)
    px(28, 20, 4, 12, shirt_d)
    # руки: рукав + кожа
    for ax, ay in ((44, 20), (36, 20), (52, 20), (60, 20)):
        px(ax, ay, 4, 4, shirt)
        px(ax, ay + 4, 4, 8, skin)
    # ноги: джинсы + ботинки
    for lx, ly in ((4, 20), (20, 20), (12, 20), (28, 20), (0, 20)):
        px(lx, ly, 4, 9, pants)
        px(lx, ly + 9, 4, 3, shoe)
    # лёгкий шум для живости
    for _ in range(60):
        x, y = rnd.randrange(64), rnd.randrange(64)
        p = im.getpixel((x, y))
        if p[3]:
            im.putpixel((x, y), tuple(max(0, v - 12) for v in p[:3]) + (255,))
    return im


def _region(skin, box):
    x1, y1, x2, y2 = box
    return skin.crop((x1, y1, x2, y2))


def _hat_front(skin):
    return _region(skin, (40, 8, 48, 16))


def render_character(skin_bytes, equipped=None, view="front", scale=6, aura=True):
    """Псевдо-3D персонаж: перед/бок/спина + косметика. Возвращает RGBA.
    Без загруженного скина рисует Стива."""
    equipped = equipped or {}
    if skin_bytes:
        try:
            skin = Image.open(BytesIO(skin_bytes)).convert("RGBA")
        except Exception:
            skin = default_skin()
        if skin.size not in ((64, 64), (64, 32)):
            skin = default_skin()
    else:
        skin = default_skin()

    W, H = 32, 36  # логическое поле (с запасом по бокам для крыльев)
    ox = 4  # сдвиг персонажа от левого края
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # аура, крылья и плащ — ПОЗАДИ персонажа
    if aura and equipped.get("aura"):
        canvas.alpha_composite(_aura_image(equipped["aura"], W), (0, 0))
    if equipped.get("wings"):
        wimg = _wings_image(equipped["wings"], 24)
        canvas.alpha_composite(wimg, (W // 2 - 12, 5))
    if equipped.get("cape") and view != "front":
        cape = _cape_image(equipped["cape"]).crop((12, 1, 22, 17)).resize((10, 13),
                                                                          Image.Resampling.NEAREST)
        canvas.alpha_composite(cape, (W // 2 - 5, 7))

    if view == "front":
        parts = [(ox, 0, (8, 8, 16, 16)), (ox, 8, (20, 20, 28, 32)),
                 (ox - 4, 8, (44, 20, 48, 32)), (ox + 8, 8, (36, 20, 40, 32)),
                 (ox, 20, (4, 20, 8, 32)), (ox + 4, 20, (20, 20, 24, 32))]
        head_hat = True
    elif view == "back":
        parts = [(ox, 0, (16, 8, 24, 16)), (ox, 8, (32, 20, 40, 32)),
                 (ox - 4, 8, (52, 20, 56, 32)), (ox + 8, 8, (60, 20, 64, 32)),
                 (ox, 20, (12, 20, 16, 32)), (ox + 4, 20, (28, 20, 32, 32))]
        head_hat = True
    else:  # side
        parts = [(ox, 0, (0, 8, 8, 16)), (ox, 8, (28, 20, 32, 32)),
                 (ox, 20, (0, 20, 4, 32))]
        head_hat = True

    for x, y, box in parts:
        region = _region(skin, box).resize((box[2] - box[0], box[3] - box[1]))
        canvas.alpha_composite(region, (x, y))

    if head_hat:
        hat = _hat_front(skin) if view == "front" else (
            _region(skin, (56, 8, 64, 16)) if view == "back" else _region(skin, (32, 8, 40, 16)))
        canvas.alpha_composite(hat, (ox, 0))

    # косметика: лицо рисуем первым, шляпу — поверх него
    if equipped.get("face") and view == "front":
        ov = _overlay_image(equipped["face"])
        canvas.alpha_composite(_region(ov, (40, 8, 48, 16)), (ox, 0))
    if equipped.get("hat"):
        ov = _overlay_image(equipped["hat"])
        canvas.alpha_composite(_region(ov, (40, 0, 48, 8)), (ox, 0))   # верх шляпы
        canvas.alpha_composite(_hat_layer(skin, ov, view), (ox, 0))    # бока шляпы

    out = canvas.resize((W * scale, H * scale), Image.Resampling.NEAREST)
    return out


def _hat_layer(skin, overlay, view):
    """Шляпный слой предмета для нужного вида (использует те же UV, что и голова)."""
    if view == "front":
        return _region(overlay, (40, 8, 48, 16))
    if view == "back":
        return _region(overlay, (56, 8, 64, 16))
    return _region(overlay, (32, 8, 40, 16))


def apply_to_game(skin_path, equipped, csl_dir):
    """Кладёт косметику туда, где её показывает CustomSkinLoader:
    скин (с наложенными шляпой/лицом) -> LocalSkin/skins, плащ -> LocalSkin/capes."""
    from pathlib import Path
    import shutil
    csl_dir = Path(csl_dir)
    skin_path = Path(skin_path)
    if not skin_path.exists():
        return "Скин аккаунта не найден — загрузи его в окне аккаунтов"
    csl_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(skin_path, csl_dir / "LocalSkin" / "skins" / (skin_path.name))
    equipped = equipped or {}
    if equipped.get("cape"):
        cape = _cape_image(equipped["cape"])
        cape_dir = csl_dir / "LocalSkin" / "capes"
        cape_dir.mkdir(parents=True, exist_ok=True)
        cape.save(cape_dir / (skin_path.stem + ".png"))
    return "Косметика применена — видна в игре через CustomSkinLoader"

# ---------- подарки друзьям (код обмена) ----------

def make_gift(cfg, item_id):
    """Отдаёт предмет из инвентаря в подарок: возвращает код обмена или None."""
    cos = cfg.setdefault("cosmetics", {"owned": [], "equipped": {}})
    if item_id not in cos.get("owned", []):
        return None
    if item_id in cos.get("equipped", {}).values():
        for slot, iid in list(cos["equipped"].items()):
            if iid == item_id:
                cos["equipped"].pop(slot)
    cos["owned"].remove(item_id)
    import secrets
    code = "YL-" + secrets.token_hex(3).upper()
    cfg.setdefault("gifts", {})[code] = item_id
    return code


def redeem_gift(cfg, code):
    """Получает подарок по коду. Возвращает (item_id, ошибка)."""
    code = (code or "").strip().upper()
    gifts = cfg.setdefault("gifts", {})
    if not code:
        return None, "Введи код подарка"
    if code not in gifts:
        return None, "Такого кода нет или он уже использован"
    item_id = gifts.pop(code)
    add_item(cfg, item_id)
    return item_id, None


# ---------- коллекционный альбом ----------

def album_progress(cfg):
    """По редкости: (собрано, всего, закрыта_ли_и_награда_получена)."""
    have = owned(cfg)
    out = {}
    for rarity in RARITIES:
        pool = [i for i in ITEMS if i[3] == rarity]
        got = sum(1 for i in pool if i[0] in have)
        out[rarity] = (got, len(pool), f"album_{rarity}" in cfg.get("album_rewards", []))
    return out


def claim_album(cfg, rarity):
    """Награда за полностью собранную редкость: (кристаллы, ошибка)."""
    got, total, claimed = album_progress(cfg)[rarity]
    if claimed:
        return 0, "Награда уже получена"
    if got < total:
        return 0, f"Собрано {got}/{total} — нужны все предметы этой редкости"
    cfg.setdefault("album_rewards", []).append(f"album_{rarity}")
    reward = {"common": 100, "uncommon": 150, "rare": 250,
              "epic": 400, "mythic": 800}[rarity]
    add_crystals(cfg, reward)
    return reward, None


# ---------- ежедневные задания ----------

DAILY_POOL = [
    ("Запусти игру", "launches", 1, 20),
    ("Проведи в игре 30 минут", "play_sec", 1800, 25),
    ("Установи любой мод", "mods", 1, 20),
    ("Открой сундук", "chests", 1, 20),
    ("Забери подарок дня", "daily", 1, 15),
    ("Открой сундук за игру", "playchest", 1, 20),
]


def daily_quests(cfg):
    """3 случайных задания на сегодня (детерминированно по дате)."""
    import hashlib
    seed = int(hashlib.md5(today_str().encode()).hexdigest(), 16)
    rnd = random.Random(seed)
    picked = rnd.sample(DAILY_POOL, 3)
    done = cfg.setdefault("daily_quests", {})
    if done.get("date") != today_str():
        cfg["daily_quests"] = {"date": today_str(), "claimed": []}
    claimed = cfg["daily_quests"].setdefault("claimed", [])
    st = cfg.setdefault("quests", {})
    out = []
    for i, (name, metric, goal, reward) in enumerate(picked):
        if metric == "play_sec":
            cur = int(_daily(cfg, "daily_play").get("seconds", 0))
        elif metric == "daily":
            cur = 1 if cfg.get("last_daily") == today_str() else 0
        elif metric == "playchest":
            cur = int(_daily(cfg, "daily_chests").get("claimed", 0))
        else:
            cur = int(st.get(metric, 0))
        out.append({"name": name, "goal": goal, "cur": min(cur, goal),
                    "reward": reward, "claimed": i in claimed, "idx": i})
    return out


def claim_daily_quest(cfg, idx):
    qs = daily_quests(cfg)
    if idx >= len(qs):
        return 0, "Нет такого задания"
    q = qs[idx]
    if q["claimed"]:
        return 0, "Уже получено"
    if q["cur"] < q["goal"]:
        return 0, f"Не выполнено: {q['cur']}/{q['goal']}"
    cfg["daily_quests"]["claimed"].append(idx)
    add_crystals(cfg, q["reward"])
    return q["reward"], None


def daily_all_bonus_ready(cfg):
    qs = daily_quests(cfg)
    return (all(q["claimed"] for q in qs)
            and "bonus" not in cfg["daily_quests"].get("claimed", []))


def claim_daily_bonus(cfg):
    dq = cfg.setdefault("daily_quests", {})
    claimed = dq.setdefault("claimed", [])
    if "bonus" in claimed:
        return 0, "Бонус уже получен"
    claimed.append("bonus")
    add_crystals(cfg, 30)
    return 30, None


# ---------- прокачка предметов и предмет дня ----------

def item_level(cfg, item_id):
    """1..3 — уровень предмета, растёт с общим временем игры."""
    if item_levelable(item_id):
        return min(3, 1 + int(float(cfg.get("playtime_hours", 0)) // 10))
    return 1


def item_levelable(item_id):
    return ITEM_MAP.get(item_id, ("", "", "cape", ""))[2] == "cape"


def item_of_day():
    """Предмет дня (детерминированно по дате, не мифический)."""
    import hashlib
    pool = [i for i in ITEMS if i[3] != "mythic"]
    seed = int(hashlib.md5(("day" + today_str()).encode()).hexdigest(), 16)
    return pool[seed % len(pool)]


def day_item_price(item_id):
    """Обычная цена предмета дня (скидка 50% применяется в магазине)."""
    rarity = ITEM_MAP[item_id][3]
    return {"common": 40, "uncommon": 80, "rare": 150, "epic": 280, "mythic": 500}[rarity]


# ---------- рамка профиля ----------

def profile_frame(cfg):
    """Цвет рамки аватарки по лучшей собранной редкости."""
    owned = owned(cfg)
    best = None
    for iid in owned:
        r = ITEM_MAP.get(iid, (0, 0, 0, "common"))[3]
        order = ["common", "uncommon", "rare", "epic", "mythic"]
        if best is None or order.index(r) > order.index(best):
            best = r
    return RARITIES.get(best, ("", "#4ade80", 0))[1] if best else None
