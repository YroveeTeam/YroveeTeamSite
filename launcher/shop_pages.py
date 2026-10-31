"""Магазин (сундуки, бонусы, задания) и Персонаж (скин + косметика).
Всё за кристаллы — без доната."""
import customtkinter as ctk
from PIL import Image

import gui as G  # цвета читаем как G.ACCENT в момент вызова
import strings
import cosmetics as C
import skin3d
from pages_extra import BasePage, fmt_time


# ======================================================================
#  Магазин
# ======================================================================
class ShopPage(BasePage):
    def __init__(self, app):
        super().__init__(app, "Магазин", "Кристаллы за игру, сундуки и косметика — всё честно, без доната")
        self.grid_rowconfigure(5, weight=1)
        self._imgs = {}

        tiles = ctk.CTkFrame(self, fg_color="transparent")
        tiles.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        tiles.grid_columnconfigure((0, 1, 2), weight=1, uniform="sh")
        self.t_bal = app._tile(tiles, "Кристаллы", 0)
        self.t_lvl = app._tile(tiles, "Уровень", 1)
        self.t_chest = app._tile(tiles, "Сундуки за игру", 2)

        self.tabs = app._segmented(self, [strings.T(x) for x in ("Сундуки", "Бонусы", "Сезон", "Задания", "Коллекция")], lambda _: self.render(), 34)
        self.tabs.set("Сундуки")
        self.tabs.grid(row=3, column=0, sticky="w", pady=(2, 8))

        self.list = self.scroll(5)
        self.list.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(self, text="", font=G.font(13), text_color=G.MUTED,
                                   anchor="w", justify="left", wraplength=640)
        self.status.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self.render()

    def set_status(self, text, error=False):
        self.status.configure(text=text, text_color=G.ERROR if error else G.ACCENT)

    def on_show(self):
        self.render()

    def _tiles(self):
        app = self.app
        self.t_bal.configure(text=f"{C.balance(app.cfg)} 💎")
        lvl = C.level_of(app.cfg)
        nxt = lvl * C.LEVEL_STEP - float(app.cfg.get("playtime_hours", 0)) * 3600
        self.t_lvl.configure(text=f"{lvl}  ·  ещё {C.fmt_wait(nxt)}")
        ready, total, need = C.playtime_chest_state(app.cfg)
        self.t_chest.configure(text=f"{ready} из {total} готовы" if ready else
                               f"через {C.fmt_wait(need)} игры")

    def render(self):
        app = self.app
        self._tiles()
        for w in self.list.winfo_children():
            w.destroy()
        self._imgs = {}
        tab = self.tabs.get()
        if tab == "Сундуки":
            self._render_chests()
        elif tab == "Бонусы":
            self._render_bonus()
        elif tab == "Сезон":
            self._render_season()
        elif tab == "Коллекция":
            self._render_album()
        else:
            self._render_quests()

    # --- сундуки ---
    def _render_chests(self):
        app = self.app
        # предмет дня: скидка 50%
        hit = C.item_of_day()
        price = C.day_item_price(hit[0]) // 2
        owned = hit[0] in C.owned(app.cfg)
        card = app._card(self.list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)
        rname, rcolor, _ = C.RARITIES[hit[3]]
        self._imgs["day"] = G.ctkimg(C.item_image(hit[0], 52), (52, 52))
        ctk.CTkLabel(card, text="", image=self._imgs["day"]).grid(
            row=0, column=0, rowspan=2, padx=(16, 12), pady=14)
        ctk.CTkLabel(card, text="🎯 Предмет дня — скидка 50%", font=G.font(13, "bold"),
                     text_color=G.ACCENT, anchor="w").grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(card, text=f"{hit[1]}  ·  {rname}", font=G.font(14, "bold"),
                     text_color=rcolor, anchor="w").grid(row=1, column=1, sticky="nw")
        ctk.CTkButton(card, text=f"{strings.T('Купить')} · {price} 💎" if not owned else strings.T("✓ Уже есть"),
                      height=38, corner_radius=12, fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER,
                      text_color=G.ACCENT_TEXT, font=G.font(13, "bold"),
                      state="disabled" if owned or C.balance(app.cfg) < price else "normal",
                      command=lambda: self.buy_day_item(hit[0], price)).grid(
            row=0, column=2, rowspan=2, padx=16, pady=14)

        ready, total, need = C.playtime_chest_state(app.cfg)
        card = app._card(self.list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=f"🎁 Сундуки за игру — {ready} из {total} готовы",
                     font=G.font(15, "bold"), text_color=G.TEXT, anchor="w").grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text=("Нажми «Забрать сундук» на странице «Играть»" if ready else
                                 f"Следующий через {C.fmt_wait(need)} игры (до {C.DAILY_CHESTS} в день)"),
                     font=G.font(12), text_color=G.MUTED, anchor="w").grid(
            row=1, column=0, sticky="w", padx=18, pady=(0, 14))

        row = ctk.CTkFrame(self.list, fg_color="transparent")
        row.pack(fill="x", padx=(0, 8))
        for i, (cid, (name, price, chances)) in enumerate(C.CHESTS.items()):
            card = app._card(row)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            row.grid_columnconfigure(i, weight=1, uniform="chest")
            img = G.ctkimg(C.chest_image(cid, 84), (84, 84))
            self._imgs[cid] = img
            ctk.CTkLabel(card, text="", image=img).grid(row=0, column=0, pady=(18, 4))
            ctk.CTkLabel(card, text=name, font=G.font(15, "bold"), text_color=G.TEXT).grid(row=1)
            sub = {"iron": "мифический ×2",
                   "gold": "без обычных, редкий+ чаще"}.get(cid, "стандартные шансы")
            ctk.CTkLabel(card, text=sub, font=G.font(12), text_color=G.MUTED).grid(row=2, pady=(0, 4))
            ctk.CTkButton(card, text=f"Открыть · {price} 💎", height=40, corner_radius=12,
                          fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                          font=G.font(13, "bold"),
                          state="normal" if C.balance(app.cfg) >= price else "disabled",
                          command=lambda c=cid: self.open_chest(c)
                          ).grid(row=3, padx=18, pady=(6, 18), sticky="ew")
        self.result_box = ctk.CTkFrame(self.list, fg_color="transparent")
        self.result_box.pack(fill="x", padx=(0, 8), pady=(10, 4))

    # --- анимация сундука перед выдачей результата ---
    def _animate_open(self, cid, events, title):
        frames = [C.chest_image(cid, 84).rotate(a, expand=True, resample=Image.BICUBIC)
                  for a in (-14, -8, 0, 8, 14, 0, -6, 6, 0)]
        self._anim = [G.ctkimg(f, (84, 84)) for f in frames]
        box = getattr(self, "result_box", None)
        parent = box if box is not None and box.winfo_exists() else self.list
        lbl = ctk.CTkLabel(parent, text="", image=self._anim[0])
        lbl.pack(pady=10)
        step = [0]

        def tick():
            if not lbl.winfo_exists():
                return
            step[0] += 1
            if step[0] >= len(self._anim):
                lbl.destroy()
                self._show_events(events, title)
                return
            lbl.configure(image=self._anim[step[0]])
            self.after(80, tick)
        self.after(80, tick)

    def buy_day_item(self, item_id, price):
        app = self.app
        if C.balance(app.cfg) < price:
            return self.set_status("Не хватает кристаллов", True)
        C.add_crystals(app.cfg, -price)
        dup = not C.add_item(app.cfg, item_id)
        app.save_cfg()
        name = C.ITEM_MAP[item_id][1]
        self.set_status(f"Предмет дня куплен: «{name}»" + (" (повтор — кристаллы назад)" if dup else ""))
        app._refresh_lobby()
        self.render()

    def open_chest(self, cid):
        app = self.app
        events, err = C.open_chest(app.cfg, cid)
        if err:
            return self.set_status(err, True)
        C.bump_counter(app.cfg, "chests")
        app.save_cfg()
        self.render()
        self._animate_open(cid, events, C.CHESTS[cid][0])

    def _show_events(self, events, title):
        """Карточка результатов открытия прямо на странице."""
        app = self.app
        box = getattr(self, "result_box", None)
        parent = box if box is not None and box.winfo_exists() else self.list
        for w in parent.winfo_children():
            w.destroy()
        card = app._card(parent)
        card.pack(fill="x", padx=(0, 8), pady=4)
        card.grid_columnconfigure(1, weight=1)
        border = "#a78bfa" if any(e[0] == "chest" for e in events) else "#fbbf24"
        card.configure(border_color=border)
        ctk.CTkLabel(card, text=f"✨ {title}", font=G.font(16, "bold"),
                     text_color=G.TEXT, anchor="w").grid(row=0, column=0, columnspan=3,
                                                         sticky="w", padx=18, pady=(14, 4))
        row = 1
        for ev in events:
            if ev[0] == "chest":
                ctk.CTkLabel(card, text="🎁 Сундук в сундуке! Ещё один открылся бесплатно",
                             font=G.font(13, "bold"), text_color="#a78bfa",
                             anchor="w").grid(row=row, column=0, columnspan=3, sticky="w",
                                              padx=18, pady=4)
                row += 1
                continue
            _, _cid, item_id, dup = ev
            info = C.ITEM_MAP[item_id]
            rname, rcolor, refund = C.RARITIES[info[3]]
            img = G.ctkimg(C.item_image(item_id, 44), (44, 44))
            self._imgs[item_id] = img
            ctk.CTkLabel(card, text="", image=img).grid(row=row, column=0, padx=(18, 8), pady=4)
            ctk.CTkLabel(card, text=f"{info[1]}  ·  {rname}" + ("  ·  повтор!" if dup else ""),
                         font=G.font(14, "bold"), text_color=rcolor,
                         anchor="w").grid(row=row, column=1, sticky="w")
            if dup:
                ctk.CTkLabel(card, text=f"+{refund} 💎", font=G.font(13, "bold"),
                             text_color=G.ACCENT).grid(row=row, column=2, padx=(0, 18))
            row += 1
        ctk.CTkLabel(card, text="Надевай полученное на странице «Персонаж»",
                     font=G.font(12), text_color=G.MUTED, anchor="w").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=18, pady=(4, 14))
        app._refresh_lobby()

    # --- бонусы ---
    def _render_bonus(self):
        import datetime
        app = self.app
        adv = C.advent_state(app.cfg)
        if adv is not None:
            opened, can_today = adv
            card = app._card(self.list)
            card.pack(fill="x", padx=(0, 8), pady=(0, 10))
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text="🎄 Адвент-календарь", font=G.font(16, "bold"),
                         text_color=G.ACCENT, anchor="w").grid(
                row=0, column=0, sticky="w", padx=18, pady=(14, 2))
            ctk.CTkLabel(card, text=f"Открыто дверец: {len(opened)} из 24. "
                                    f"Каждый день декабря — кристаллы, на особых днях — зимняя косметика!",
                         font=G.font(12), text_color=G.MUTED, anchor="w", justify="left",
                         wraplength=560).grid(row=1, column=0, sticky="w", padx=18)
            ctk.CTkButton(card, text="🎁 Открыть дверцу" if can_today else "Дверца открыта — завтра новая",
                          height=42, corner_radius=12, fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER,
                          text_color=G.ACCENT_TEXT, font=G.font(13, "bold"),
                          state="normal" if can_today else "disabled",
                          command=self.claim_advent).grid(row=0, column=1, rowspan=2,
                                                           padx=18, pady=14)

        card = app._card(self.list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        claimed = app.cfg.get("last_daily") == datetime.date.today().isoformat()
        ctk.CTkLabel(card, text="🎁 Подарок дня", font=G.font(15, "bold"), text_color=G.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text=f"+{C.DAILY_BONUS} 💎 каждый день" +
                     ("  ·  уже получен сегодня" if claimed else ""),
                     font=G.font(12), text_color=G.MUTED, anchor="w").grid(
            row=1, column=0, sticky="w", padx=18)
        ctk.CTkButton(card, text="Забрать" if not claimed else "Завтра",
                      height=38, corner_radius=12, fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER,
                      text_color=G.ACCENT_TEXT, font=G.font(13, "bold"),
                      state="disabled" if claimed else "normal",
                      command=self.claim_daily).grid(row=0, column=1, rowspan=2, padx=18, pady=14)

        card = app._card(self.list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text="🎁 Код подарка от друга", font=G.font(15, "bold"),
                     text_color=G.TEXT, anchor="w").grid(row=0, column=0, columnspan=2,
                                                          sticky="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text="Друг на странице «Персонаж» дарит предмет и получает код",
                     font=G.font(12), text_color=G.MUTED, anchor="w").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=18)
        self.gift_entry = app._entry(card, "Код вида YL-XXXXXX")
        self.gift_entry.grid(row=2, column=0, sticky="ew", padx=(18, 10), pady=(8, 14))
        self.gift_entry.bind("<Return>", lambda e: self.redeem_gift())
        ctk.CTkButton(card, text="Получить", height=38, corner_radius=12,
                      fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                      font=G.font(13, "bold"), command=self.redeem_gift).grid(
            row=2, column=1, padx=(0, 18), pady=(8, 14), sticky="w")

        card = app._card(self.list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text="📺 Промокод из Telegram-канала", font=G.font(15, "bold"),
                     text_color=G.TEXT, anchor="w").grid(row=0, column=0, columnspan=2,
                                                         sticky="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text="Коды публикуются в канале — подпишись и введи их здесь",
                     font=G.font(12), text_color=G.MUTED, anchor="w").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=18)
        self.promo_entry = app._entry(card, "Например: YROVEE")
        self.promo_entry.grid(row=2, column=0, sticky="ew", padx=(18, 10), pady=(8, 14))
        self.promo_entry.bind("<Return>", lambda e: self.redeem())
        ctk.CTkButton(card, text="Обменять", height=38, corner_radius=12,
                      fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                      font=G.font(13, "bold"), command=self.redeem).grid(
            row=2, column=1, padx=(0, 18), pady=(8, 14), sticky="w")

        ready, total, need = C.playtime_chest_state(app.cfg)
        card = app._card(self.list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="⏳ Сундуки за игру", font=G.font(15, "bold"), text_color=G.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text=f"Каждый час игры — сундук (до {C.DAILY_CHESTS} в день). "
                                f"Сейчас: {ready} готовы" + ("" if ready else
                                f", следующий через {C.fmt_wait(need)} игры"),
                     font=G.font(12), text_color=G.MUTED, anchor="w", justify="left",
                     wraplength=560).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 14))

    def claim_daily(self):
        app = self.app
        n, err = C.claim_daily(app.cfg)
        if err:
            return self.set_status(err, True)
        app.save_cfg()
        self.set_status(f"+{n} 💎 за ежедневный вход")
        self.render()

    def claim_advent(self):
        app = self.app
        ev, err = C.claim_advent(app.cfg)
        if err:
            return self.set_status(err, True)
        app.save_cfg()
        if ev[0] == "item":
            name = C.ITEM_MAP[ev[1]][1]
            msg = f"🎄 В дверце: «{name}»" + (" (повтор)" if ev[2] else "") + f" и +{ev[3]} 💎"
        else:
            msg = f"🎄 В дверце: +{ev[1]} 💎"
        self.set_status(msg)
        app._refresh_lobby()
        self.render()

    def redeem_gift(self):
        app = self.app
        item_id, err = C.redeem_gift(app.cfg, self.gift_entry.get())
        if err:
            return self.set_status(err, True)
        app.save_cfg()
        name = C.ITEM_MAP[item_id][1]
        self.set_status(f"🎁 Подарок получен: «{name}» — надевай в «Персонаже»!")
        self.gift_entry.delete(0, "end")
        app._refresh_lobby()
        self.render()

    def redeem(self):
        app = self.app
        n, err = C.redeem_promo(app.cfg, self.promo_entry.get(), getattr(app, "site_promos", {}))
        if err:
            return self.set_status(err, True)
        app.save_cfg()
        self.set_status(f"Промокод принят: +{n} 💎")
        self.promo_entry.delete(0, "end")
        self.render()

    # --- коллекционный альбом ---
    def _render_album(self):
        app = self.app
        prog = C.album_progress(app.cfg)
        card = app._card(self.list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="📘 Коллекционный альбом", font=G.font(16, "bold"),
                     text_color=G.TEXT, anchor="w").grid(row=0, column=0, sticky="w",
                                                          padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text="Собери все предметы редкости — получишь крупную награду. "
                                "Силуэты подсказывают, чего не хватает.",
                     font=G.font(12), text_color=G.MUTED, anchor="w", justify="left",
                     wraplength=560).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 6))
        row = 2
        for rarity, (got, total, claimed) in prog.items():
            rname, rcolor, _ = C.RARITIES[rarity]
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.grid(row=row, column=0, sticky="ew", padx=18, pady=3)
            line.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(line, text=rname, font=G.font(13, "bold"), text_color=rcolor,
                         width=110, anchor="w").grid(row=0, column=0, sticky="w")
            bar = ctk.CTkProgressBar(line, height=10, corner_radius=5, fg_color=G.BORDER,
                                     progress_color=rcolor)
            bar.set(got / total)
            bar.grid(row=0, column=1, sticky="ew", padx=10)
            ctk.CTkLabel(line, text=f"{got}/{total}", font=G.font(12),
                         text_color=G.MUTED, width=60).grid(row=0, column=2)
            ctk.CTkButton(line, text="Забрать" if (got >= total and not claimed) else "—",
                          width=90, height=28, corner_radius=9, fg_color=G.ACCENT,
                          hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                          font=G.font(11, "bold"),
                          state="normal" if (got >= total and not claimed) else "disabled",
                          command=lambda r=rarity: self.claim_album(r)).grid(row=0, column=3)
            row += 1
        ctk.CTkFrame(card, height=10, fg_color="transparent").grid(row=row, column=0)

        grid = ctk.CTkScrollableFrame(self.list, fg_color="transparent",
                                      scrollbar_button_color=G.BORDER,
                                      scrollbar_button_hover_color=G.MUTED)
        grid.pack(fill="both", expand=True, padx=(0, 8))
        owned = C.owned(app.cfg)
        for n, (item_id, name, slot, rarity) in enumerate(C.ITEMS):
            rname, rcolor, _ = C.RARITIES[rarity]
            has = item_id in owned
            frame = ctk.CTkFrame(grid, fg_color=G.CARD, corner_radius=12, border_width=1,
                                 border_color=rcolor if has else G.BORDER)
            frame.grid(row=n // 6, column=n % 6, padx=4, pady=4, sticky="nsew")
            img = C.item_image(item_id, 44)
            if not has:
                img = self._silhouette(img)
            self._imgs[item_id + "_a"] = G.ctkimg(img, (44, 44))
            ctk.CTkLabel(frame, text="", image=self._imgs[item_id + "_a"]).pack(pady=(10, 0))
            ctk.CTkLabel(frame, text=name if has else "? ? ?",
                         font=G.font(11, "bold"), text_color=G.TEXT if has else G.MUTED,
                         wraplength=110).pack()
            ctk.CTkLabel(frame, text=rname, font=G.font(10), text_color=rcolor).pack(pady=(0, 10))

    def _silhouette(self, img):
        """Тёмный силуэт для несобранных предметов."""
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = px[x, y]
                px[x, y] = (16, 18, 26, a)
        return img

    def claim_album(self, rarity):
        app = self.app
        reward, err = C.claim_album(app.cfg, rarity)
        if err:
            return self.set_status(err, True)
        app.save_cfg()
        self.set_status(f"Альбом закрыт! +{reward} 💎")
        app._refresh_lobby()
        self.render()

    # --- сезонный пропуск (28 дней, бесплатно) ---
    def _render_season(self):
        import datetime
        app = self.app
        day, claimed = C.season_state(app.cfg)
        card = app._card(self.list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=f"⭐ Сезонный пропуск — день {day} из {C.SEASON_DAYS}",
                     font=G.font(16, "bold"), text_color=G.ACCENT, anchor="w").grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text="Заходи каждый день: награда растёт, на особых днях — косметика. "
                                "Бесплатно, без доната.",
                     font=G.font(12), text_color=G.MUTED, anchor="w").grid(
            row=1, column=0, sticky="w", padx=18)
        can = day not in claimed
        crystals, item = C.season_reward_preview(day)
        text = f"Забрать день {day}: +{crystals} 💎" + (f" + предмет" if item else "")
        ctk.CTkButton(card, text=text if can else "Награда дня получена — приходи завтра",
                      height=42, corner_radius=12, fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER,
                      text_color=G.ACCENT_TEXT, font=G.font(13, "bold"),
                      state="normal" if can else "disabled",
                      command=self.claim_season).grid(row=2, column=0, sticky="w",
                                                       padx=18, pady=(10, 14))

        grid = ctk.CTkFrame(self.list, fg_color="transparent")
        grid.pack(fill="x", padx=(0, 8))
        for i in range(1, C.SEASON_DAYS + 1):
            done = i in claimed
            today = i == day
            col, row = (i - 1) % 7, (i - 1) // 7
            cell = ctk.CTkFrame(grid, fg_color=G.CARD if not done else "#173425",
                                corner_radius=10, border_width=2 if today else 1,
                                border_color=G.ACCENT if today else G.BORDER)
            cell.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            grid.grid_columnconfigure(col, weight=1)
            ctk.CTkLabel(cell, text=f"День {i}", font=G.font(11, "bold"),
                         text_color=G.TEXT if not done else G.ACCENT).pack(pady=(8, 0))
            cr, it = C.season_reward_preview(i)
            ctk.CTkLabel(cell, text=f"+{cr}💎" + ("🎁" if it else ""),
                         font=G.font(11), text_color=G.MUTED).pack(pady=(0, 2))
            ctk.CTkLabel(cell, text="✓" if done else ("•" if today else ""),
                         font=G.font(13, "bold"), text_color=G.ACCENT).pack(pady=(0, 8))

    def claim_season(self):
        app = self.app
        crystals, item, err = C.claim_season(app.cfg)
        if err:
            return self.set_status(err, True)
        app.save_cfg()
        msg = f"Сезон: +{crystals} 💎"
        if item:
            name = C.ITEM_MAP[item[0]][1]
            msg += f" и «{name}»" + (" (повтор — кристаллы назад)" if item[1] else "")
        self.set_status(msg)
        self.render()

    # --- задания ---
    def _render_quests(self):
        app = self.app
        lvl = C.level_of(app.cfg)
        card = app._card(self.list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        hours = float(app.cfg.get("playtime_hours", 0))
        to_next = lvl * C.LEVEL_STEP - hours * 3600
        ctk.CTkLabel(card, text=f"⭐ Уровень {lvl}", font=G.font(16, "bold"),
                     text_color=G.ACCENT, anchor="w").grid(row=0, column=0, sticky="w",
                                                           padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text=f"Всего в игре: {fmt_time(hours * 3600)} · до уровня {lvl + 1}: "
                                f"{C.fmt_wait(to_next)} игры",
                     font=G.font(12), text_color=G.MUTED, anchor="w").grid(
            row=1, column=0, sticky="w", padx=18, pady=(0, 14))
        for qid, name, desc, goal, reward, metric in C.QUESTS:
            prog = C.quest_progress(app.cfg, qid)
            card = app._card(self.list)
            card.pack(fill="x", padx=(0, 8), pady=4)
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=name, font=G.font(14, "bold"), text_color=G.TEXT,
                         anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=(10, 0))
            if prog is None:
                ctk.CTkLabel(card, text="✓ Награда получена", font=G.font(12),
                             text_color=G.ACCENT).grid(row=0, column=2, padx=18, pady=(10, 0))
                bar_val = 1.0
                text = "выполнено"
            else:
                cur, goal_v, reward_v = prog
                bar_val = cur / goal_v
                text = f"{cur} / {goal_v}  ·  +{reward_v} 💎"
                ctk.CTkButton(card, text="Забрать" if cur >= goal_v else "—", width=100,
                              height=32, corner_radius=10, fg_color=G.ACCENT,
                              hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                              font=G.font(12, "bold"),
                              state="normal" if cur >= goal_v else "disabled",
                              command=lambda q=qid: self.claim_quest(q)).grid(
                    row=0, column=2, padx=18, pady=(10, 0))
            bar = ctk.CTkProgressBar(card, height=8, corner_radius=4, fg_color=G.BORDER,
                                     progress_color=G.ACCENT)
            bar.set(bar_val)
            bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=18, pady=(4, 2))
            ctk.CTkLabel(card, text=f"{desc}  ·  {text}", font=G.font(12), text_color=G.MUTED,
                         anchor="w").grid(row=2, column=0, columnspan=3, sticky="w",
                                          padx=18, pady=(0, 10))

    def claim_quest(self, qid):
        app = self.app
        n, err = C.claim_quest(app.cfg, qid)
        if err:
            return self.set_status(err, True)
        app.save_cfg()
        self.set_status(f"Задание выполнено: +{n} 💎")
        self.render()


# ======================================================================
#  Персонаж
# ======================================================================
class CharacterPage(BasePage):
    SLOT_TABS = ["Все", "Плащ", "Крылья", "Голова", "Лицо", "Аура"]

    def __init__(self, app):
        super().__init__(app, "Персонаж", "Твой скин и косметика: крути мышкой. Плащ, голова и лицо видны в игре")
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.yaw = 0.0
        self.pitch = -0.12
        self.slot_tab = "Все"
        self.pose = None
        self._drag = None
        self._render_job = None
        self._imgs = {}

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=2, column=0, sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.char_lbl = ctk.CTkLabel(left, text="", cursor="fleur")
        self.char_lbl.grid(row=0, column=0, sticky="nsew")
        # вращение мышкой
        self.char_lbl.bind("<Button-1>", self._drag_start)
        self.char_lbl.bind("<B1-Motion>", self._drag_move)
        vrow = ctk.CTkFrame(left, fg_color="transparent")
        vrow.grid(row=2, column=0, pady=(6, 0))
        for text, yaw in (("Перед", 0.0), ("Бок", 1.5708), ("Спина", 3.14159)):
            ctk.CTkButton(vrow, text=text, width=86, height=34, corner_radius=10,
                          border_width=1, fg_color=G.FIELD, hover_color=G.HOVER,
                          border_color=G.BORDER, text_color=G.TEXT, font=G.font(13),
                          command=lambda y=yaw: self.set_yaw(y)).pack(side="left", padx=(0, 8))
        self.pose_seg = app._segmented(vrow, ["Спокойно", "👋 Привет"], self._on_pose, 34)
        self.pose_seg.set("Спокойно")
        self.pose_seg.pack(side="left", padx=(4, 0))
        ctk.CTkButton(vrow, text="Применить в игре", height=34, corner_radius=10,
                      fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                      font=G.font(13, "bold"), command=self.apply_game).pack(side="left", padx=(4, 0))
        if self.app.account().get("type") == "msa":
            ctk.CTkButton(vrow, text="Поставить на лицензию", height=34, corner_radius=10,
                          border_width=1, fg_color=G.FIELD, hover_color=G.HOVER,
                          border_color=G.BORDER, text_color=G.TEXT, font=G.font(13),
                          command=self.upload_license).pack(side="left", padx=(8, 0))

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=2, column=1, sticky="nsew", padx=(16, 0))
        right.grid_rowconfigure(3, weight=1)
        right.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(right, text="Экипировано (клик — снять)", font=G.font(14, "bold"),
                     text_color=G.TEXT, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.slots_row = ctk.CTkFrame(right, fg_color="transparent")
        self.slots_row.grid(row=1, column=0, sticky="ew")
        self.inv_seg = app._segmented(right, self.SLOT_TABS, self._on_tab, 32)
        self.inv_seg.set("Все")
        self.inv_seg.grid(row=2, column=0, sticky="w", pady=(12, 8))
        self.inv = ctk.CTkScrollableFrame(right, fg_color="transparent",
                                          scrollbar_button_color=G.BORDER,
                                          scrollbar_button_hover_color=G.MUTED)
        self.inv.grid(row=3, column=0, sticky="nsew")
        self.inv.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="inv")
        self.char_status = ctk.CTkLabel(right, text="", font=G.font(12), text_color=G.MUTED,
                                        anchor="w", justify="left", wraplength=380)
        self.char_status.grid(row=4, column=0, sticky="ew", pady=(8, 0))

    def on_show(self):
        self.render()

    def set_status(self, text, error=False):
        self.char_status.configure(text=text, text_color=G.ERROR if error else G.ACCENT)

    # --- вращение мышкой ---
    def _drag_start(self, event):
        self._drag = (event.x, event.y)

    def _drag_move(self, event):
        if self._drag is None:
            return
        dx, dy = event.x - self._drag[0], event.y - self._drag[1]
        self._drag = (event.x, event.y)
        self.yaw += dx * 0.012
        self.pitch = max(-0.6, min(0.35, self.pitch + dy * 0.006))
        if self._render_job is None:  # не чаще пары десятков раз в секунду
            self._render_job = self.after(33, self._coalesced_render)

    def _coalesced_render(self):
        self._render_job = None
        self._render_character()

    def set_yaw(self, yaw):
        self.yaw = yaw
        self._render_character()

    def _on_pose(self, _):
        self.pose = "wave" if self.pose_seg.get() == "👋 Привет" else None
        self._render_character()

    def _on_tab(self, _):
        self.slot_tab = self.inv_seg.get()
        self._render_inventory()

    def _skin_bytes(self):
        app = self.app
        acc = app.account()
        path = G.SKINS_DIR / acc["skin"] if acc.get("skin") else None
        if path and path.exists():
            return path.read_bytes()
        return None

    def render(self):
        self._render_character()
        self._render_slots()
        self._render_inventory()

    def _render_character(self):
        app = self.app
        bytes_ = self._skin_bytes()
        if bytes_ is None:
            self.set_status("Скин не загружен — показываю Стива. Свой скин можно поставить "
                            "в окне аккаунта (клик по карточке аккаунта)")
        elif not self.char_status.cget("text").startswith("Скин"):
            self.set_status("")
        eq = C.equipped(app.cfg)
        levels = {iid: C.item_level(app.cfg, iid) for iid in eq.values()}
        im = skin3d.render_3d(bytes_, eq, yaw=self.yaw, pitch=self.pitch, height=500,
                              pose=getattr(self, "pose", None), item_levels=levels)
        self._big = G.ctkimg(im, im.size)
        self.char_lbl.configure(image=self._big, text="")

    def _slot_label(self):
        return {"cape": "Плащ", "wings": "Крылья", "hat": "Голова",
                "face": "Лицо", "aura": "Аура"}

    def _render_slots(self):
        """Слоты: аккуратные карточки «название / предмет», клик по всей карточке снимает."""
        app = self.app
        for w in self.slots_row.winfo_children():
            w.destroy()
        eq = C.equipped(app.cfg)
        for slot, label in self._slot_label().items():
            item_id = eq.get(slot)
            has = bool(item_id)
            rcolor = C.RARITIES[C.ITEM_MAP[item_id][3]][1] if has else G.BORDER
            frame = ctk.CTkFrame(self.slots_row, fg_color=G.CARD, corner_radius=12,
                                 border_width=2 if has else 1, border_color=rcolor,
                                 cursor="hand2")
            frame.grid(row=0, column=len(self.slots_row.winfo_children()), padx=(0, 6))
            frame.grid_columnconfigure(0, weight=1)
            if has:
                img = G.ctkimg(C.item_image(item_id, 32), (32, 32))
                self._imgs[item_id] = img
                ctk.CTkLabel(frame, text="", image=img).grid(row=0, column=0, pady=(8, 0))
                name_text = C.ITEM_MAP[item_id][1]
                name_color = G.TEXT
            else:
                name_text = "— пусто"
                name_color = G.MUTED
            ctk.CTkLabel(frame, text=label, font=G.font(10), text_color=G.MUTED).grid(
                row=1, column=0, padx=10, pady=(6, 0))
            ctk.CTkLabel(frame, text=name_text, font=G.font(11, "bold"), text_color=name_color,
                         wraplength=90).grid(row=2, column=0, padx=8, pady=(1, 0))
            ctk.CTkLabel(frame, text=("✕ снять" if has else " "), font=G.font(10),
                         text_color=G.MUTED).grid(row=3, column=0, padx=10, pady=(2, 8))
            frame.bind("<Button-1>", lambda e, s=slot: self.unequip(s))

    def unequip(self, slot):
        app = self.app
        C.set_equipped(app.cfg, slot, None)
        app.save_cfg()
        app._refresh_lobby()
        self.render()

    def _render_inventory(self):
        app = self.app
        for w in self.inv.winfo_children():
            w.destroy()
        self._imgs = {}
        items = [i for i in C.ITEMS if i[0] in C.owned(app.cfg)]
        if self.slot_tab != "Все":
            key = {v: k for k, v in self._slot_label().items()}[self.slot_tab]
            items = [i for i in items if i[2] == key]
        if not items:
            box = ctk.CTkFrame(self.inv, fg_color="transparent")
            box.grid(row=0, column=0, columnspan=4, pady=40)
            ctk.CTkLabel(box, text="Пока ничего нет", font=G.font(15, "bold"),
                         text_color=G.TEXT).pack()
            ctk.CTkLabel(box, text="Открывай сундуки в Магазине и выполняй задания —\nпредметы появятся здесь",
                         font=G.font(12), text_color=G.MUTED, justify="center").pack(pady=(6, 0))
            return
        eq = C.equipped(app.cfg)
        for n, (item_id, name, slot, rarity) in enumerate(items):
            rname, rcolor, _ = C.RARITIES[rarity]
            equipped_here = eq.get(slot) == item_id
            frame = ctk.CTkFrame(self.inv, fg_color=G.CARD, corner_radius=14, border_width=2,
                                 border_color=rcolor if equipped_here else "#222839")
            frame.grid(row=n // 4, column=n % 4, padx=4, pady=4, sticky="nsew")
            img = G.ctkimg(C.item_image(item_id, 56), (56, 56))
            self._imgs[item_id] = img
            ctk.CTkLabel(frame, text="", image=img).pack(pady=(12, 0))
            ctk.CTkLabel(frame, text=name, font=G.font(12, "bold"), text_color=G.TEXT,
                         wraplength=120).pack()
            ctk.CTkLabel(frame, text=rname, font=G.font(11), text_color=rcolor).pack(pady=(0, 2))
            brow = ctk.CTkFrame(frame, fg_color="transparent")
            brow.pack(fill="x", padx=10, pady=(2, 12))
            ctk.CTkButton(brow, text="Снять" if equipped_here else "Надеть",
                          height=28, corner_radius=9, border_width=1,
                          fg_color="transparent", hover_color=G.HOVER, border_color=G.BORDER,
                          text_color=G.TEXT, font=G.font(12),
                          command=lambda s=slot, i=item_id: self.equip(s, i)
                          ).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(brow, text="🎁", width=34, height=28, corner_radius=9, border_width=1,
                          fg_color="transparent", hover_color=G.HOVER, border_color=G.BORDER,
                          text_color=G.MUTED, font=G.font(12),
                          command=lambda i=item_id, n=name: self.gift_dialog(i, n)
                          ).pack(side="left", padx=(6, 0))

    def gift_dialog(self, item_id, name):
        import threading
        import secrets as _secrets
        app = self.app
        dlg = ctk.CTkToplevel(app)
        dlg.title("Подарить предмет")
        dlg.geometry("430x210")
        dlg.resizable(False, False)
        dlg.configure(fg_color=G.BG)
        dlg.transient(app)
        dlg.after(250, lambda: (dlg.lift(), dlg.focus_force(), dlg.grab_set()))
        dlg.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(dlg, text=f"Подарить «{name}» другу?", font=G.font(16, "bold"),
                     text_color=G.TEXT).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(dlg, text="Предмет уйдёт из инвентаря, ты получишь код обмена. "
                               "Друг введёт его в Магазине → Бонусы.",
                     font=G.font(12), text_color=G.MUTED, anchor="w", justify="left",
                     wraplength=380).grid(row=1, column=0, sticky="w", padx=20)
        code_lbl = ctk.CTkLabel(dlg, text="", font=G.font(18, "bold"), text_color=G.ACCENT)
        code_lbl.grid(row=2, column=0, sticky="w", padx=20, pady=(10, 4))

        def do_gift():
            code = C.make_gift(app.cfg, item_id)
            app.save_cfg()
            if code:
                def show():
                    code_lbl.configure(text=code)
                    app.clipboard_clear()
                    app.clipboard_append(code)
                    self.set_status("Код скопирован в буфер — отправь другу!")
                    self.render()
                dlg.after(100, show)

        ctk.CTkButton(dlg, text="Подарить и получить код", height=40, corner_radius=12,
                      fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                      font=G.font(13, "bold"), command=do_gift).grid(
            row=3, column=0, sticky="ew", padx=20, pady=(6, 16))

    def equip(self, slot, item_id):
        app = self.app
        eq = C.equipped(app.cfg)
        C.set_equipped(app.cfg, slot, None if eq.get(slot) == item_id else item_id)
        app.save_cfg()
        app._refresh_lobby()
        self.render()

    def apply_game(self):
        app = self.app
        acc = app.account()
        if not acc.get("skin"):
            return self.set_status("Сначала загрузи скин в окне аккаунта", True)
        path = G.SKINS_DIR / acc["skin"]
        msg = C.apply_to_game(path, C.equipped(app.cfg),
                              app._game_dir() / "CustomSkinLoader")
        self.set_status(msg)

    def upload_license(self):
        """Ставит текущий PNG скином на лицензионный аккаунт (Microsoft)."""
        import threading
        import auth as A
        from auth import ensure_msa_token
        app = self.app
        acc = app.account()
        if acc.get("type") != "msa":
            return self.set_status("Это работает только для Microsoft-аккаунтов", True)
        if not acc.get("skin"):
            return self.set_status("Сначала загрузи PNG-скин в окне аккаунта", True)
        self.set_status("Ставлю скин на лицензию…")
        path = G.SKINS_DIR / acc["skin"]

        def run():
            try:
                token = ensure_msa_token(acc)
                err = A.upload_skin(token, path, "classic")
                app.q.put(("char_status", err or "Скин загружен на твой лицензионный аккаунт!",
                           bool(err)))
            except Exception as e:
                app.q.put(("char_status", f"Ошибка: {e}", True))
        threading.Thread(target=run, daemon=True).start()


def show_drop_dialog(app, events, title):
    """Всплывающее окно с результатами сундука (используется лобби)."""
    dlg = ctk.CTkToplevel(app)
    dlg.title(title)
    dlg.geometry("430x430")
    dlg.resizable(False, False)
    dlg.configure(fg_color=G.BG)
    dlg.transient(app)
    dlg.after(250, lambda: (dlg.lift(), dlg.focus_force(), dlg.grab_set()))
    dlg.grid_columnconfigure(0, weight=1)
    dlg.grid_rowconfigure(1, weight=1)
    ctk.CTkLabel(dlg, text=f"✨ {title}", font=G.font(20, "bold"), text_color=G.TEXT).grid(
        row=0, column=0, sticky="w", padx=20, pady=(18, 8))
    box = ctk.CTkScrollableFrame(dlg, fg_color="transparent",
                                 scrollbar_button_color=G.BORDER,
                                 scrollbar_button_hover_color=G.MUTED)
    box.grid(row=1, column=0, sticky="nsew", padx=12)
    box.grid_columnconfigure(0, weight=1)
    for ev in events:
        if ev[0] == "chest":
            ctk.CTkLabel(box, text="🎁 Сундук в сундуке!", font=G.font(14, "bold"),
                         text_color="#a78bfa").pack(anchor="w", padx=8, pady=4)
            continue
        _, _cid, item_id, dup = ev
        info = C.ITEM_MAP[item_id]
        rname, rcolor, refund = C.RARITIES[info[3]]
        row = ctk.CTkFrame(box, fg_color=G.CARD, corner_radius=12)
        row.pack(fill="x", padx=4, pady=3)
        img = G.ctkimg(C.item_image(item_id, 40), (40, 40))
        ctk.CTkLabel(row, text="", image=img).pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(row, text=f"{info[1]} · {rname}" + (" · повтор" if dup else ""),
                     font=G.font(13, "bold"), text_color=rcolor, anchor="w").pack(
            side="left", padx=4)
        if dup:
            ctk.CTkLabel(row, text=f"+{refund} 💎", font=G.font(12, "bold"),
                         text_color=G.ACCENT).pack(side="right", padx=12)
    ctk.CTkButton(dlg, text="Круто!", height=40, corner_radius=12, fg_color=G.ACCENT,
                  hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT, font=G.font(14, "bold"),
                  command=dlg.destroy).grid(row=2, column=0, sticky="ew", padx=20, pady=14)
