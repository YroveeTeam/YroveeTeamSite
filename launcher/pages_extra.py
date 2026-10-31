"""Дополнительные страницы лаунчера: Сборки, Серверы, Скриншоты, Лог, Статистика."""
import os
import shutil
import sys
import threading
import uuid

import customtkinter as ctk
from PIL import Image, ImageOps

import gui as G  # цвета читаем как G.ACCENT в момент вызова: тема может меняться
import strings
import visuals
from config import INSTANCES_DIR
from modrinth import search_mods
from servers import ping_server


def fmt_time(seconds):
    seconds = int(seconds)
    h, m = seconds // 3600, seconds % 3600 // 60
    if h:
        return f"{h} ч {m} мин"
    return f"{m} мин" if m else f"{seconds} сек"


def open_path(path):
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}"')


class BasePage(ctk.CTkFrame):
    def __init__(self, app, title, subtitle):
        super().__init__(app.content, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.subtitle = app._title(self, strings.T(title), strings.T(subtitle))

    def on_show(self):
        pass

    def on_hide(self):
        pass

    def scroll(self, row):
        box = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=G.BORDER,
                                     scrollbar_button_hover_color=G.MUTED)
        box.grid(row=row, column=0, sticky="nsew")
        self.grid_rowconfigure(row, weight=1)
        return box

    def hint(self, parent, title, sub=""):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(pady=50)
        ctk.CTkLabel(box, text=title, font=G.font(16, "bold"), text_color=G.TEXT).pack()
        if sub:
            ctk.CTkLabel(box, text=sub, font=G.font(13), text_color=G.MUTED, justify="center").pack(pady=(6, 0))


# ======================================================================
#  Сборки
# ======================================================================
class BuildsPage(BasePage):
    def __init__(self, app):
        super().__init__(app, "Сборки", "У каждой сборки своя папка: моды, сохранения, ресурспаки")
        self.grid_rowconfigure(4, weight=1)

        self.tabs = app._segmented(self, ["Мои сборки", "Каталог Modrinth"], lambda _: self.render(), 34)
        self.tabs.set("Мои сборки")
        self.tabs.grid(row=2, column=0, sticky="w", pady=(0, 12))

        self.bar = ctk.CTkFrame(self, fg_color="transparent")
        self.bar.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.bar.grid_columnconfigure(0, weight=1)
        self.entry = app._entry(self.bar, "")
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda e: self.on_enter())
        self.action = ctk.CTkButton(self.bar, text="", width=170, height=42, corner_radius=12,
                                    fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                                    font=G.font(13, "bold"), command=self.on_enter)
        self.action.grid(row=0, column=1, padx=(10, 0))
        ctk.CTkButton(self.bar, text="Из файла .mrpack", height=42, corner_radius=12, border_width=1,
                      fg_color=G.FIELD, hover_color=G.HOVER, border_color=G.BORDER, text_color=G.TEXT,
                      font=G.font(13), command=app.pick_pack_file).grid(row=0, column=2, padx=(10, 0))

        self.list = self.scroll(4)
        self.status = ctk.CTkLabel(self, text="", font=G.font(13), text_color=G.MUTED, anchor="w",
                                   justify="left", wraplength=640)
        self.status.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        self.hits, self.loading, self.busy = [], False, False
        self.render()

    def set_status(self, text, error=False):
        self.status.configure(text=text, text_color=G.ERROR if error else (
            G.ACCENT if text.startswith("Готово") else G.MUTED))

    def on_show(self):
        self.render()

    def _clear(self):
        for w in self.list.winfo_children():
            w.destroy()
        self.app.icon_waiters = {}

    def render(self):
        app = self.app
        self._clear()
        catalog = self.tabs.get() == "Каталог Modrinth"
        self.entry.delete(0, "end")
        self.entry.configure(placeholder_text="Поиск сборок на Modrinth" if catalog else "Название новой сборки")
        self.action.configure(text="Найти" if catalog else "Создать из текущей")
        if catalog:
            if self.loading:
                return self.hint(self.list, "Ищу сборки…")
            if not self.hits:
                return self.hint(self.list, "Найди сборку", "Введи запрос или нажми «Найти», чтобы увидеть популярные")
            for hit in self.hits:
                desc = hit.get("description", "")
                desc = desc[:127] + "…" if len(desc) > 130 else desc
                tags = [c.capitalize() for c in hit.get("display_categories", [])
                        if c not in G.LOADERS][:3]
                app._mod_row(hit["title"], desc,
                             f'↓ {G.short_number(hit.get("downloads", 0))}  ·  {hit.get("author", "")}', tags,
                             "Установить", lambda h=hit: self.install(h),
                             icon_url=hit.get("icon_url") or "", color=hit.get("color"),
                             state="disabled" if self.busy else "normal", parent=self.list)
            return
        builds = app.cfg["builds"]
        if not builds:
            return self.hint(self.list, "Сборок пока нет",
                             "Создай свою из выбранной версии или поставь готовую из каталога")
        for b in builds:
            active = b["id"] == app.cfg["active_build"]
            app._mod_row(b["name"], f'{b["loader"]} · Minecraft {b["version"]}',
                         "Выбрана" if active else "", [],
                         "✓ Выбрана" if active else "Выбрать", lambda bid=b["id"]: self.select(bid),
                         icon_url=b.get("icon_url", ""), state="disabled" if active else "normal",
                         parent=self.list,
                         extra=[("Экспорт .mrpack", lambda bid=b["id"]: app.export_build_dialog(bid)),
                                ("Убрать", lambda bid=b["id"]: self.remove(bid))])

    def on_enter(self):
        app = self.app
        if self.tabs.get() == "Каталог Modrinth":
            self.loading = True
            self.render()
            threading.Thread(target=self._search, args=(self.entry.get().strip(),), daemon=True).start()
            return
        name = self.entry.get().strip()
        if not name:
            return self.set_status("Введи название сборки", True)
        if not app.cfg["last_version"]:
            return self.set_status("Сначала выбери версию на странице «Играть»", True)
        app.add_build({"id": uuid.uuid4().hex[:8], "name": name, "version": app.cfg["last_version"],
                       "loader": app.cfg["loader"], "forge_version": "", "icon_url": ""})
        self.set_status(f"Готово: сборка «{name}» создана и выбрана")
        self.render()

    def _search(self, query):
        try:
            hits = search_mods(query, None, None, kind="modpack")
            self.app.q.put(("builds_hits", hits))
        except Exception as e:
            self.app.q.put(("builds_hits", e))

    def on_hits(self, hits):
        self.loading = False
        if isinstance(hits, Exception):
            self.hits = []
            self.set_status(f"Ошибка поиска: {hits}", True)
        else:
            self.hits = hits
        self.render()

    def install(self, hit):
        if self.busy:
            return
        self.busy = True
        self.set_status(f"Установка «{hit['title']}»…")
        self.render()
        threading.Thread(target=self.app._modpack_worker, args=(hit["project_id"],), daemon=True).start()

    def finished(self, ok, text):
        self.busy = False
        self.set_status(text, not ok)
        self.render()

    def select(self, bid):
        self.app.select_build(bid)
        self.render()

    def remove(self, bid):
        self.app.remove_build(bid)
        self.set_status("Сборка убрана из списка (папка с файлами осталась на диске)")
        self.render()


# ======================================================================
#  Серверы
# ======================================================================
class ServersPage(BasePage):
    REFRESH_MS = 60000  # обновлять онлайн, пока страница открыта

    def __init__(self, app):
        super().__init__(app, "Серверы", "Список любимых серверов с онлайном и пингом")
        self.grid_rowconfigure(4, weight=1)
        self.results = {}  # address -> dict | None (недоступен)
        self.icons = {}
        self._job = None

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        bar.grid_columnconfigure(1, weight=1)
        self.name = app._entry(bar, "Название")
        self.name.configure(width=170)
        self.name.grid(row=0, column=0)
        self.addr = app._entry(bar, "Адрес, например play.example.com:25565")
        self.addr.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.addr.bind("<Return>", lambda e: self.add())
        ctk.CTkButton(bar, text="+ Добавить", width=110, height=42, corner_radius=12, fg_color=G.ACCENT,
                      hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT, font=G.font(13, "bold"),
                      command=self.add).grid(row=0, column=2, padx=(10, 0))
        ctk.CTkButton(bar, text="Обновить", width=96, height=42, corner_radius=12, border_width=1,
                      fg_color=G.FIELD, hover_color=G.HOVER, border_color=G.BORDER, text_color=G.TEXT,
                      font=G.font(13), command=self.refresh).grid(row=0, column=3, padx=(10, 0))

        self.list = self.scroll(4)
        self.status = ctk.CTkLabel(self, text="", font=G.font(13), text_color=G.MUTED, anchor="w")
        self.status.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        self.render()

    def on_show(self):
        self.refresh()
        self._schedule()

    def on_hide(self):
        self._cancel()

    def _schedule(self):
        self._cancel()
        self._job = self.after(self.REFRESH_MS, self._tick)

    def _cancel(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick(self):
        if self.winfo_ismapped():
            self.refresh()
        self._schedule()

    def add(self):
        name, addr = self.name.get().strip(), self.addr.get().strip()
        if not addr:
            self.status.configure(text="Введи адрес сервера", text_color=G.ERROR)
            return
        self.app.cfg["servers"].append({"name": name or addr, "address": addr})
        self.app.save_all()
        self.name.delete(0, "end")
        self.addr.delete(0, "end")
        self.status.configure(text="")
        self.refresh()

    def remove(self, idx):
        self.app.cfg["servers"].pop(idx)
        self.app.save_all()
        self.render()

    def refresh(self):
        for s in self.app.cfg["servers"]:
            self.results.pop(s["address"], None)
            self.app.icon_pool.submit(self._worker, s["address"])
        self.render()

    def _worker(self, address):
        try:
            res = ping_server(address)
            if res.get("favicon"):
                try:
                    res["icon_pil"] = visuals.process_icon(res["favicon"], G.ICON)
                except Exception:
                    pass
            res.pop("favicon", None)
        except Exception:
            res = None
        self.app.q.put(("server", address, res))

    def on_result(self, address, res):
        self.results[address] = res
        if res and res.get("icon_pil") is not None:
            self.icons[address] = G.ctkimg(res["icon_pil"], (G.ICON, G.ICON))
        self.render()

    def render(self):
        app = self.app
        for w in self.list.winfo_children():
            w.destroy()
        servers = app.cfg["servers"]
        if not servers:
            return self.hint(self.list, "Серверов пока нет", "Добавь адрес выше — покажу онлайн и пинг")
        for i, s in enumerate(servers):
            addr = s["address"]
            row = ctk.CTkFrame(self.list, fg_color=G.CARD, corner_radius=16, border_width=1,
                               border_color=G.BORDER)
            row.pack(fill="x", padx=(0, 8), pady=5)
            row.grid_columnconfigure(1, weight=1)
            icon = ctk.CTkLabel(row, text="", width=G.ICON, height=G.ICON)
            icon.grid(row=0, column=0, rowspan=3, padx=(14, 14), pady=14)
            icon.configure(image=self.icons.get(addr) or app._placeholder(s["name"], None))
            ctk.CTkLabel(row, text=s["name"], font=G.font(15, "bold"), text_color=G.TEXT,
                         anchor="w").grid(row=0, column=1, sticky="sw", pady=(14, 0))
            res = self.results.get(addr, "wait")
            if res == "wait":
                motd, stat, color = addr, "● проверяю…", G.MUTED
            elif res is None:
                motd, stat, color = addr, "● недоступен", G.ERROR
            else:
                motd = res["motd"].replace("\n", "  ")[:90] or addr
                stat = f'● {res["online"]}/{res["max"]}  ·  {res["ping_ms"]} мс  ·  {res["version"]}'
                color = G.ACCENT if res["ping_ms"] < 150 else "#fbbf24"
            ctk.CTkLabel(row, text=motd, font=G.font(12), text_color=G.MUTED, anchor="w").grid(
                row=1, column=1, sticky="w")
            ctk.CTkLabel(row, text=stat, font=G.font(12, "bold"), text_color=color, anchor="w").grid(
                row=2, column=1, sticky="nw", pady=(2, 14))
            ctk.CTkButton(row, text="Играть", width=100, height=36, corner_radius=10, fg_color=G.ACCENT,
                          hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT, font=G.font(13, "bold"),
                          command=lambda a=addr: app.play_on_server(a)).grid(
                row=0, column=2, rowspan=3, padx=(10, 6))
            ctk.CTkButton(row, text="✕", width=36, height=36, corner_radius=10, border_width=1,
                          fg_color="transparent", hover_color=G.HOVER, border_color=G.BORDER,
                          text_color=G.MUTED, font=G.font(13), command=lambda i=i: self.remove(i)).grid(
                row=0, column=3, rowspan=3, padx=(0, 16))


# ======================================================================
#  Скриншоты
# ======================================================================
class ScreenshotsPage(BasePage):
    COLS, THUMB = 3, (214, 120)
    LIMIT = 60

    def __init__(self, app):
        super().__init__(app, "Скриншоты", "Все скриншоты из всех папок игры")
        self.grid_rowconfigure(3, weight=1)
        self.thumbs = {}
        self.cells = {}
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkButton(bar, text="Обновить", width=96, height=38, corner_radius=12, border_width=1,
                      fg_color=G.FIELD, hover_color=G.HOVER, border_color=G.BORDER, text_color=G.TEXT,
                      font=G.font(13), command=self.reload).pack(side="left")
        ctk.CTkButton(bar, text="Открыть папку", width=130, height=38, corner_radius=12, border_width=1,
                      fg_color=G.FIELD, hover_color=G.HOVER, border_color=G.BORDER, text_color=G.TEXT,
                      font=G.font(13), command=self.open_folder).pack(side="left", padx=(10, 0))
        self.list = self.scroll(3)
        for c in range(self.COLS):
            self.list.grid_columnconfigure(c, weight=1, uniform="shot")

    def on_show(self):
        self.reload()

    def open_folder(self):
        folder = self.app._game_dir() / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    def _scan(self):
        found = []
        if INSTANCES_DIR.exists():
            for d in INSTANCES_DIR.iterdir():
                shots = d / "screenshots"
                if shots.is_dir():
                    for f in shots.glob("*.png"):
                        found.append((f.stat().st_mtime, f, d.name))
        found.sort(reverse=True)
        return found[: self.LIMIT]

    def reload(self):
        for w in self.list.winfo_children():
            w.destroy()
        self.cells = {}
        shots = self._scan()
        if not shots:
            return self.hint(self.list, "Скриншотов пока нет", "Нажми F2 в игре — они появятся здесь")
        for i, (_, path, inst) in enumerate(shots):
            cell = ctk.CTkFrame(self.list, fg_color=G.CARD, corner_radius=14, border_width=1,
                                border_color=G.BORDER, cursor="hand2")
            cell.grid(row=i // self.COLS, column=i % self.COLS, padx=5, pady=5, sticky="ew")
            lbl = ctk.CTkLabel(cell, text="", width=self.THUMB[0], height=self.THUMB[1], cursor="hand2")
            lbl.grid(row=0, column=0, padx=8, pady=(8, 2))
            cap = ctk.CTkLabel(cell, text=f"{path.stem[:19]}  ·  {inst[:14]}", font=G.font(11),
                               text_color=G.MUTED, cursor="hand2")
            cap.grid(row=1, column=0, pady=(0, 8))
            for w in (cell, lbl, cap):
                w.bind("<Button-1>", lambda e, p=path: open_path(str(p)))
            key = str(path)
            self.cells.setdefault(key, []).append(lbl)
            if key in self.thumbs:
                lbl.configure(image=self.thumbs[key])
            else:
                self.app.icon_pool.submit(self._thumb_worker, path)

    def _thumb_worker(self, path):
        try:
            im = Image.open(path)
            im.load()
            w, h = self.THUMB
            im = visuals.round_corners(ImageOps.fit(im.convert("RGBA"), (w * 2, h * 2), Image.Resampling.LANCZOS), 16)
            self.app.q.put(("thumb", str(path), im))
        except Exception:
            self.app.q.put(("thumb", str(path), None))

    def on_thumb(self, key, pil):
        if pil is None:
            return
        img = G.ctkimg(pil, self.THUMB)
        self.thumbs[key] = img
        for lbl in self.cells.get(key, []):
            try:
                lbl.configure(image=img)
            except Exception:
                pass


# ======================================================================
#  Живой лог игры
# ======================================================================
class LogPage(BasePage):
    MAX_LINES = 4000

    def __init__(self, app):
        super().__init__(app, "Лог игры", "Здесь появляется всё, что пишет Minecraft во время запуска")
        self.grid_rowconfigure(4, weight=1)
        self.count = 0

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for text, cmd in (("Очистить", self.clear), ("Копировать всё", self.copy),
                          ("Папка crash-reports", self.open_crashes)):
            ctk.CTkButton(bar, text=text, height=36, corner_radius=12, border_width=1,
                          fg_color=G.FIELD, hover_color=G.HOVER, border_color=G.BORDER, text_color=G.TEXT,
                          font=G.font(13), command=cmd).pack(side="left", padx=(0, 10))

        self.hint_card = ctk.CTkFrame(self, fg_color=G.CARD, corner_radius=14, border_width=1,
                                      border_color=G.ERROR)
        self.hint_label = ctk.CTkLabel(self.hint_card, text="", font=G.font(13), text_color=G.TEXT,
                                       anchor="w", justify="left", wraplength=640)
        self.hint_label.pack(fill="x", padx=18, pady=14)

        mono = "Consolas" if sys.platform.startswith("win") else "Courier"
        self.box = ctk.CTkTextbox(self, fg_color=G.FIELD, border_width=1, border_color=G.BORDER,
                                  corner_radius=14, text_color=G.TEXT, font=(mono, 12), wrap="none",
                                  state="disabled")
        self.box.grid(row=4, column=0, sticky="nsew")
        self.append("Лог появится здесь после запуска игры.\n")

    def append(self, line):
        self.box.configure(state="normal")
        self.box.insert("end", line if line.endswith("\n") else line + "\n")
        self.count += max(1, line.count("\n"))
        if self.count > self.MAX_LINES:
            self.box.delete("1.0", "1001.0")
            self.count -= 1000
        self.box.see("end")
        self.box.configure(state="disabled")

    def clear(self):
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.configure(state="disabled")
        self.count = 0
        self.show_hint("")

    def show_hint(self, text):
        if text:
            self.hint_label.configure(text="💡 " + text)
            self.hint_card.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        else:
            self.hint_card.grid_remove()

    def copy(self):
        self.app.clipboard_clear()
        self.app.clipboard_append(self.box.get("1.0", "end"))

    def open_crashes(self):
        folder = self.app._game_dir() / "crash-reports"
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)


# ======================================================================
#  Миры: сохранения из всех версий и сборок
# ======================================================================
class WorldsPage(BasePage):
    LIMIT = 60
    BAD_CHARS = '\\/:*?"<>|'

    def __init__(self, app):
        super().__init__(app, "Миры", "Сохранения из всех версий и сборок: копируй между версиями")
        self.grid_rowconfigure(3, weight=1)
        self._imgs = {}
        self._copy_dlg = None
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkButton(bar, text="Обновить", width=96, height=38, corner_radius=12, border_width=1,
                      fg_color=G.FIELD, hover_color=G.HOVER, border_color=G.BORDER, text_color=G.TEXT,
                      font=G.font(13), command=self.render).pack(side="left")
        self.list = self.scroll(3)
        self.list.grid_columnconfigure(0, weight=1)

    def on_show(self):
        self.render()

    def _scan(self):
        found = []
        if INSTANCES_DIR.exists():
            for inst in INSTANCES_DIR.iterdir():
                saves = inst / "saves"
                if saves.is_dir():
                    for w in saves.iterdir():
                        if w.is_dir() and (w / "level.dat").exists():
                            found.append((w.stat().st_mtime, w, inst.name))
        found.sort(reverse=True)
        return found[: self.LIMIT]

    def render(self):
        app = self.app
        for w in self.list.winfo_children():
            w.destroy()
        self._imgs = {}
        worlds = self._scan()
        if not worlds:
            return self.hint(self.list, "Миров пока нет",
                             "Создай мир в игре — он появится здесь, и его можно будет скопировать на другую версию")
        from datetime import datetime
        for mtime, w, inst in worlds:
            row = ctk.CTkFrame(self.list, fg_color=G.CARD, corner_radius=16, border_width=1,
                               border_color=G.BORDER)
            row.pack(fill="x", padx=(0, 8), pady=5)
            row.grid_columnconfigure(1, weight=1)
            icon_lbl = ctk.CTkLabel(row, text="", width=48, height=48)
            icon_lbl.grid(row=0, column=0, rowspan=2, padx=(14, 14), pady=12)
            icon = w / "icon.png"
            if icon.exists():
                try:
                    img = G.ctkimg(visuals.process_icon(icon.read_bytes(), 48), (48, 48))
                    self._imgs[str(w)] = img
                    icon_lbl.configure(image=img)
                except Exception:
                    pass
            if not icon_lbl.cget("image"):
                icon_lbl.configure(image=app._placeholder(w.name, None))
            when = datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
            ctk.CTkLabel(row, text=w.name, font=G.font(15, "bold"), text_color=G.TEXT,
                         anchor="w").grid(row=0, column=1, sticky="sw")
            ctk.CTkLabel(row, text=f"{inst} · играли {when}", font=G.font(12),
                         text_color=G.MUTED, anchor="w").grid(row=1, column=1, sticky="nw")
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.grid(row=0, column=2, rowspan=2, padx=(10, 14), pady=8)
            ctk.CTkButton(btns, text="Копировать →", width=110, height=32, corner_radius=10,
                          fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER, text_color=G.ACCENT_TEXT,
                          font=G.font(12, "bold"), command=lambda w=w: self.copy_dialog(w)
                          ).pack(side="left", padx=(0, 6))
            ctk.CTkButton(btns, text="✎", width=40, height=32, corner_radius=10, border_width=1,
                          fg_color="transparent", hover_color=G.HOVER, border_color=G.BORDER,
                          text_color=G.TEXT, font=G.font(13),
                          command=lambda w=w: self.rename_world(w)).pack(side="left", padx=(0, 6))
            del_btn = ctk.CTkButton(btns, text="🗑", width=40, height=32, corner_radius=10,
                                    border_width=1, fg_color="transparent", hover_color=G.HOVER,
                                    border_color=G.ERROR, text_color=G.ERROR, font=G.font(13))
            del_btn.configure(command=lambda w=w, b=del_btn: self.delete_world(w, b))
            del_btn.pack(side="left")

    # --- действия ---
    def _status(self, text, error=False):
        self.app.q.put(("status", text, error))

    def copy_dialog(self, world):
        src_inst = world.parent.parent.name
        insts = sorted((p.name for p in INSTANCES_DIR.iterdir() if p.is_dir()),
                       reverse=True) if INSTANCES_DIR.exists() else []
        insts = [i for i in insts if i != src_inst]
        if not insts:
            return self._status("Других версий и сборок нет — копировать некуда", True)
        dlg = ctk.CTkToplevel(self)
        dlg.title("Копировать мир")
        dlg.geometry("430x230")
        dlg.resizable(False, False)
        dlg.configure(fg_color=G.BG)
        dlg.transient(self)
        dlg.grab_set()
        dlg.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(dlg, text=f"Мир «{world.name}»", font=G.font(17, "bold"),
                     text_color=G.TEXT).grid(row=0, column=0, sticky="w", padx=22, pady=(22, 4))
        ctk.CTkLabel(dlg, text="Куда скопировать?", font=G.font(13), text_color=G.MUTED,
                     anchor="w").grid(row=1, column=0, sticky="w", padx=22)
        menu = ctk.CTkOptionMenu(dlg, values=insts, height=40, corner_radius=12,
                                 fg_color=G.FIELD, button_color=G.BORDER,
                                 button_hover_color=G.HOVER, text_color=G.TEXT,
                                 font=G.font(13))
        menu.set(insts[0])
        menu.grid(row=2, column=0, sticky="ew", padx=22, pady=(6, 14))
        self._copy_btn = ctk.CTkButton(dlg, text="Скопировать", height=42, corner_radius=12,
                                       fg_color=G.ACCENT, hover_color=G.ACCENT_HOVER,
                                       text_color=G.ACCENT_TEXT, font=G.font(13, "bold"),
                                       command=lambda: self._do_copy(world, menu.get(), dlg))
        self._copy_btn.grid(row=3, column=0, sticky="ew", padx=22, pady=(0, 22))
        self._copy_dlg = dlg

    def _do_copy(self, world, target_inst, dlg):
        self._copy_btn.configure(state="disabled", text="Копирую…")

        def run():
            try:
                dst_root = INSTANCES_DIR / target_inst / "saves"
                dst_root.mkdir(parents=True, exist_ok=True)
                dst, n = dst_root / world.name, 2
                while dst.exists():
                    dst = dst_root / f"{world.name} ({n})"
                    n += 1
                shutil.copytree(world, dst)
                self.app.q.put(("worlds_done", f"Мир скопирован в «{target_inst}» как «{dst.name}»"))
            except Exception as e:
                self.app.q.put(("worlds_done", None, f"Не удалось скопировать: {e}"))
        threading.Thread(target=run, daemon=True).start()

    def rename_world(self, world):
        dlg = ctk.CTkInputDialog(text="Новое название мира:", title="Переименовать мир")
        name = (dlg.get_input() or "").strip()
        name = "".join(c for c in name if c not in self.BAD_CHARS)
        if not name or name == world.name:
            return
        try:
            world.rename(world.parent / name)
            self._status("Мир переименован")
            self.render()
        except Exception as e:
            self._status(f"Не удалось переименовать: {e}", True)

    def delete_world(self, world, btn):
        if getattr(btn, "_armed", False):
            try:
                shutil.rmtree(world)
                self._status(f"Мир «{world.name}» удалён")
                self.render()
            except Exception as e:
                self._status(f"Не удалось удалить: {e}", True)
            return
        btn._armed = True
        btn.configure(text="Точно?")
        self.after(3500, lambda: self._disarm(btn))

    def _disarm(self, btn):
        try:
            if btn.winfo_exists():
                btn._armed = False
                btn.configure(text="🗑")
        except Exception:
            pass


# ======================================================================
#  Статистика
# ======================================================================
class StatsPage(BasePage):
    def __init__(self, app):
        super().__init__(app, "Статистика", "Сколько ты играешь и во что")
        self.grid_rowconfigure(3, weight=1)
        tiles = ctk.CTkFrame(self, fg_color="transparent")
        tiles.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        tiles.grid_columnconfigure((0, 1, 2), weight=1, uniform="st")
        self.t_time = app._tile(tiles, "Всего в игре", 0)
        self.t_runs = app._tile(tiles, "Запусков", 1)
        self.t_fav = app._tile(tiles, "Любимая версия", 2)
        ctk.CTkButton(tiles, text="💾 Сохранить картинку", height=44, corner_radius=12,
                      border_width=1, fg_color=G.FIELD, hover_color=G.HOVER,
                      border_color=G.BORDER, text_color=G.TEXT, font=G.font(13),
                      command=self._export_image).grid(row=0, column=3, sticky="ew", padx=(12, 0))
        self.body = self.scroll(3)
        self.body.grid_columnconfigure(0, weight=1)

    def on_show(self):
        for w in self.body.winfo_children():
            w.destroy()
        st = self.app.cfg["stats"]
        by_v, by_a = st.get("by_version", {}), st.get("by_account", {})
        self.t_time.configure(text=fmt_time(sum(by_v.values())))
        self.t_runs.configure(text=str(st.get("launches", 0)))
        self.t_fav.configure(text=max(by_v, key=by_v.get) if by_v else "—")
        self._chart()
        if not by_v:
            return self.hint(self.body, "Пока пусто", "Сыграй пару минут — и тут появятся цифры")
        self._section("По версиям", by_v, 1)
        self._section("По аккаунтам", by_a, 2)

    def _export_image(self):
        """Красивая PNG-картинка со статистикой — сохранить и похвастаться."""
        import datetime
        from PIL import Image, ImageDraw
        app = self.app
        st = app.cfg["stats"]
        by_v = st.get("by_version", {})
        dest = filedialog.asksaveasfilename(
            title="Куда сохранить картинку", defaultextension=".png",
            initialfile="yrovee_stats.png", filetypes=[("PNG", "*.png")])
        if not dest:
            return
        W, H = 900, 560
        S = 2
        img = Image.new("RGBA", (W * S, H * S), (11, 13, 19, 255))
        d = ImageDraw.Draw(img)
        acc = G.hex_rgb(G.ACCENT)
        d.rounded_rectangle((20 * S, 20 * S, (W - 20) * S, (H - 20) * S), radius=18 * S,
                            outline=acc + (255,), width=2 * S)
        d.text((50 * S, 44 * S), "YroveeLauncher — моя статистика", font=visuals.pil_font(30 * S, True),
               fill=(238, 241, 247, 255))
        d.text((50 * S, 90 * S), datetime.date.today().strftime("%d.%m.%Y"),
               font=visuals.pil_font(15 * S), fill=(138, 147, 166, 255))
        total = fmt_time(sum(by_v.values()))
        d.text((50 * S, 140 * S), f"Всего в игре: {total}", font=visuals.pil_font(20 * S, True),
               fill=(74, 222, 128, 255))
        d.text((50 * S, 180 * S), f"Запусков: {st.get('launches', 0)}   ·   "
               f"Уровень: {__import__('cosmetics').level_of(app.cfg)}",
               font=visuals.pil_font(16 * S), fill=(238, 241, 247, 255))
        top = sorted(by_v.items(), key=lambda kv: kv[1], reverse=True)[:5]
        d.text((50 * S, 240 * S), "Любимые версии:", font=visuals.pil_font(16 * S, True),
               fill=(238, 241, 247, 255))
        for i, (name, secs) in enumerate(top):
            d.text((50 * S, (280 + i * 36) * S), f"{name} — {fmt_time(secs)}",
                   font=visuals.pil_font(15 * S), fill=(199, 208, 224, 255))
        try:
            ch = app.pages["char"]
            skin = ch._skin_bytes()
            if skin:
                import skin3d as S3
                import cosmetics as C
                im = S3.render_3d(skin, C.equipped(app.cfg), yaw=-0.32, pitch=-0.08, height=340)
                im = im.resize((int(im.width * 1.6), 340 * 1), Image.Resampling.LANCZOS)
                img.alpha_composite(im, ((W - im.width - 60) * S, 60 * S))
        except Exception:
            pass
        d.text((50 * S, (H - 60) * S), "сделано в YroveeLauncher",
               font=visuals.pil_font(13 * S), fill=(120, 128, 145, 255))
        img = img.resize((W, H), Image.Resampling.LANCZOS)
        img.convert("RGB").save(dest)
        app._set_status(f"Картинка сохранена: {dest}", G.ACCENT)

    def _chart(self):
        """Столбики времени игры за последние 14 дней (рисуются Pillow)."""
        import datetime
        from PIL import Image, ImageDraw
        hist = self.app.cfg.get("play_history", {})
        days = [(datetime.date.today() - datetime.timedelta(days=i)) for i in range(13, -1, -1)]
        vals = [int(hist.get(d.isoformat(), 0)) for d in days]
        if not any(vals):
            return
        W, H, pad = 640, 190, 30
        S = 2
        img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        acc = G.hex_rgb(G.ACCENT)
        bar_w = (W - pad * 2) / 14
        peak = max(vals)
        for i, (day, v) in enumerate(zip(days, vals)):
            h = int((H - pad * 2) * (v / peak) * S) if peak else 0
            x = int((pad + i * bar_w + bar_w * 0.15) * S)
            bw = int(bar_w * 0.7 * S)
            y_base = (H - pad) * S
            d.rounded_rectangle((x, y_base - h, x + bw, y_base), radius=4 * S,
                                fill=acc + (255,) if v else (120, 120, 130, 90))
            if i % 2 == 0 or v:
                lbl = day.strftime("%d.%m")
                f = visuals.pil_font(11 * S)
                tw = d.textbbox((0, 0), lbl, font=f)
                d.text((x + bw / 2 - (tw[2] - tw[0]) / 2, y_base + 6 * S), lbl, font=f,
                       fill=(140, 140, 150, 255))
        img = img.resize((W, H), Image.Resampling.LANCZOS)
        card = self.app._card(self.body)
        card.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 14))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="Время в игре — последние 14 дней", font=G.font(14, "bold"),
                     text_color=G.TEXT, anchor="w").grid(row=0, column=0, sticky="w",
                                                          padx=18, pady=(14, 4))
        self._chart_img = G.ctkimg(img, (W, H))
        ctk.CTkLabel(card, text="", image=self._chart_img).grid(row=1, column=0, sticky="ew",
                                                                 padx=18, pady=(0, 14))

    def _section(self, title, data, row):
        card = self.app._card(self.body)
        card.grid(row=row, column=0, sticky="ew", padx=(0, 8), pady=(0, 14))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text=title, font=G.font(13, "bold"), text_color=G.MUTED, anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=22, pady=(18, 8))
        items = sorted(data.items(), key=lambda kv: kv[1], reverse=True)[:8]
        top = max((v for _, v in items), default=1) or 1
        for i, (name, secs) in enumerate(items, start=1):
            ctk.CTkLabel(card, text=name, font=G.font(13), text_color=G.TEXT, anchor="w", width=150).grid(
                row=i, column=0, sticky="w", padx=(22, 10), pady=4)
            bar = ctk.CTkProgressBar(card, height=10, corner_radius=5, fg_color=G.BORDER,
                                     progress_color=G.ACCENT)
            bar.set(secs / top)
            bar.grid(row=i, column=1, sticky="ew", pady=4)
            ctk.CTkLabel(card, text=fmt_time(secs), font=G.font(12), text_color=G.MUTED, anchor="e",
                         width=90).grid(row=i, column=2, padx=(10, 22), pady=4)
        ctk.CTkFrame(card, height=10, fg_color="transparent").grid(row=len(items) + 1, column=0)
