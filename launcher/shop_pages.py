"""Магазин (сундуки, бонусы, задания) и Персонаж (скин + косметика).
Всё за кристаллы — без доната."""
import customtkinter as ctk

import gui as G  # цвета читаем как G.ACCENT в момент вызова
import cosmetics as C
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

        self.tabs = app._segmented(self, ["Сундуки", "Бонусы", "Задания"], lambda _: self.render(), 34)
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
        else:
            self._render_quests()

    # --- сундуки ---
    def _render_chests(self):
        app = self.app
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

    def open_chest(self, cid):
        app = self.app
        events, err = C.open_chest(app.cfg, cid)
        if err:
            return self.set_status(err, True)
        C.bump_counter(app.cfg, "chests")
        app.save_cfg()
        self._show_events(events, C.CHESTS[cid][0])
        self.render()

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

    def redeem(self):
        app = self.app
        n, err = C.redeem_promo(app.cfg, self.promo_entry.get(), getattr(app, "site_promos", {}))
        if err:
            return self.set_status(err, True)
        app.save_cfg()
        self.set_status(f"Промокод принят: +{n} 💎")
        self.promo_entry.delete(0, "end")
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
    VIEWS = {"Перед": "front", "Бок": "side", "Спина": "back"}
    SLOT_TABS = ["Все", "Плащ", "Крылья", "Голова", "Лицо", "Аура"]

    def __init__(self, app):
        super().__init__(app, "Персонаж", "Твой скин и косметика: плащ, голова и лицо видны в игре")
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.view = "front"
        self.slot_tab = "Все"
        self._imgs = {}

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=2, column=0, sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.char_lbl = ctk.CTkLabel(left, text="", cursor="hand2")
        self.char_lbl.grid(row=0, column=0, sticky="nsew")
        vrow = ctk.CTkFrame(left, fg_color="transparent")
        vrow.grid(row=2, column=0, pady=(6, 0))
        self.view_seg = app._segmented(vrow, list(self.VIEWS), self._on_view, 34)
        self.view_seg.set("Перед")
        self.view_seg.grid(row=0, column=0)
        ctk.CTkButton(vrow, text="Применить в игре", height=34, corner_radius=10,
                      fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                      font=G.font(13, "bold"), command=self.apply_game).grid(
            row=0, column=1, padx=(10, 0))

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

    def _on_view(self, _):
        self.view = self.VIEWS[self.view_seg.get()]
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
            self.char_lbl.configure(image=None,
                                    text="Загрузи скин в окне аккаунта\n(клик по карточке аккаунта внизу слева)",
                                    font=G.font(14), text_color=G.MUTED)
            return
        im = C.render_character(bytes_, C.equipped(app.cfg), view=self.view, scale=7)
        self._big = G.ctkimg(im, im.size)
        self.char_lbl.configure(image=self._big, text="")

    def _slot_label(self):
        return {"cape": "Плащ", "wings": "Крылья", "hat": "Голова",
                "face": "Лицо", "aura": "Аура"}

    def _render_slots(self):
        app = self.app
        for w in self.slots_row.winfo_children():
            w.destroy()
        eq = C.equipped(app.cfg)
        for slot, label in self._slot_label().items():
            item_id = eq.get(slot)
            rcolor = C.RARITIES[C.ITEM_MAP[item_id][3]][1] if item_id else G.BORDER
            frame = ctk.CTkFrame(self.slots_row, fg_color=G.CARD, corner_radius=12,
                                 border_width=2 if item_id else 1, border_color=rcolor)
            frame.grid(row=0, column=len(self.slots_row.winfo_children()), padx=(0, 6))
            if item_id:
                img = G.ctkimg(C.item_image(item_id, 30), (30, 30))
                self._imgs[item_id] = img
                ctk.CTkLabel(frame, text="", image=img).pack(pady=(8, 0))
                text = C.ITEM_MAP[item_id][1]
            else:
                text = "— пусто"
            ctk.CTkButton(frame, text=f"{label}\n{text}", width=96, height=66,
                          corner_radius=10, fg_color="transparent", hover_color=G.HOVER,
                          text_color=G.TEXT if item_id else G.MUTED, font=G.font(11),
                          command=lambda s=slot: self.unequip(s)).pack()
            ctk.CTkLabel(frame, text="✕" if item_id else "", font=G.font(11),
                         text_color=G.MUTED).pack(pady=(0, 6))

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
            ctk.CTkButton(frame, text="Снять" if equipped_here else "Надеть",
                          height=28, corner_radius=9, border_width=1,
                          fg_color="transparent", hover_color=G.HOVER, border_color=G.BORDER,
                          text_color=G.TEXT, font=G.font(12),
                          command=lambda s=slot, i=item_id: self.equip(s, i)
                          ).pack(fill="x", padx=10, pady=(2, 12))

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
