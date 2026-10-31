import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageTk

import visuals
import auth
import cosmetics as cos
import rpc
import updater
from shop_pages import CharacterPage, ShopPage, show_drop_dialog
from auth import ensure_msa_token
from builds import install_modpack, install_pack_zip
from config import (BACKUPS_DIR, MSA_CLIENT_ID, NATIVES_DIR, REPO, SITE_URL, CACHE_DIR,
                    INSTANCES_DIR, LAUNCHER_NAME, LAUNCHER_VERSION, SKINS_DIR,
                    instance_dir, load_config, save_config)
from export_pack import detect_loader_version, export_modpack
from fabric import fabric_id, install_fabric
from forge import ensure_forge, find_forge_id
from gamelog import LogWriter, crash_hint
from maintenance import backup_saves, import_from_official, restore_backup
from neoforge import ensure_neoforge, find_neoforge_id
from pages_extra import (BuildsPage, LogPage, ScreenshotsPage, ServersPage,
                         StatsPage, WorldsPage)
from quilt import install_quilt, quilt_id
from java_installer import ensure_java
from launcher import launch, required_java
from modrinth import (KIND_DIRS, analyze, fill_missing_icons, install_mod,
                      list_installed, remove_mod, search_mods)
from net import friendly_error, get_bytes
from optimize import OPT_MODS, PRESETS, preset_args, recommended_ram
from versions import (extract_natives, get_all_versions_cached, install_version,
                      installed_versions, load_version)

# ---------- палитра ----------
BG = "#0b0d13"
SIDEBAR = "#0e1118"
CARD = "#131722"
FIELD = "#0c0f16"
BORDER = "#222839"
HOVER = "#1b2233"
ACTIVE = "#15202b"
TEXT = "#eef1f7"
MUTED = "#8a93a6"
ACCENT = "#4ade80"
ACCENT2 = "#22d3ee"
ACCENT_HOVER = "#3cc972"
ACCENT_TEXT = "#06121a"
SEG_ON = "#1f5a3c"
SEG_ON_HOVER = "#27704a"
ERROR = "#f87171"
FONT = "Segoe UI"

SKIN_MOD_ID = "idMHQ4n2"  # CustomSkinLoader на Modrinth
NICK_RE = r"[A-Za-z0-9_]{3,16}"
OLDEST_VERSION = "1.5.2"  # самая старая версия в списке
BANNER_H = 160  # устаревшее имя; лобби использует LOBBY_H
LOBBY_H = 400   # высота фона лобби с персонажем
PLAY_H = 58
ICON = 52  # размер иконки мода
LOADERS = {"fabric", "forge", "quilt", "neoforge", "liteloader", "rift", "modloader"}


THEMES = {
    "Мята": ("#4ade80", "#22d3ee"),
    "Лаванда": ("#a78bfa", "#f472b6"),
    "Океан": ("#38bdf8", "#818cf8"),
    "Закат": ("#fb923c", "#f43f5e"),
    "Лимон": ("#facc15", "#4ade80"),
}


def rgbhex(c):
    return "#%02x%02x%02x" % tuple(int(x) for x in c)


def apply_theme(name):
    """Подменяет акцентные цвета ДО построения окна (смена темы = перезапуск)."""
    global ACCENT, ACCENT2, ACCENT_HOVER, SEG_ON, SEG_ON_HOVER, ACTIVE
    a, b = THEMES.get(name, THEMES["Мята"])
    ra, rbg = visuals.hex_rgb(a), visuals.hex_rgb(BG)
    ACCENT, ACCENT2 = a, b
    ACCENT_HOVER = rgbhex(visuals.mix(ra, (0, 0, 0), 0.12))
    SEG_ON = rgbhex(visuals.mix(ra, rbg, 0.72))
    SEG_ON_HOVER = rgbhex(visuals.mix(ra, rbg, 0.62))
    ACTIVE = rgbhex(visuals.mix(ra, rbg, 0.9))


def font(size, weight="normal"):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


def ctkimg(pil, size):
    return ctk.CTkImage(light_image=pil, dark_image=pil, size=size)


def total_ram_mb():
    try:
        if sys.platform.startswith("win"):
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullTotalPhys // (1024 * 1024))
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // (1024 * 1024)
    except Exception:
        return 16384


def short_number(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def open_folder(path):
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def parse_site_data(text):
    """data.js сайта -> словарь SITE (достаточно строгий парсер для нашего формата)."""
    body = re.sub(r"(?m)^\s*//.*$", "", text)  # комментарии-строки
    # ключи вида `v:` после { [ или , — в кавычки (JSON-подобный формат сайта)
    body = re.sub(r"([{\[,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', body)
    start, end = body.find("{"), body.rfind("}")
    return json.loads(body[start:end + 1])


# ======================================================================
#  Окно «Что нового» — показывается после обновления лаунчера
# ======================================================================
class WhatsNewDialog(ctk.CTkToplevel):
    def __init__(self, master, entry):
        super().__init__(master)
        v, date, items = entry.get("v", ""), entry.get("date", ""), entry.get("items", [])
        self.title(f"Что нового — v{v}")
        self.geometry("480x460")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.transient(master)
        self.grab_set()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = f"YroveeLauncher v{v}"
        if date:
            head += f"  ·  {date}"
        ctk.CTkLabel(self, text="🎉 Что нового", font=font(24, "bold"),
                     text_color=TEXT).grid(row=0, column=0, sticky="w", padx=24, pady=(22, 2))
        ctk.CTkLabel(self, text=head, font=font(13), text_color=ACCENT,
                     anchor="w").grid(row=1, column=0, sticky="w", padx=24, pady=(0, 12))
        box = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                     scrollbar_button_color=BORDER,
                                     scrollbar_button_hover_color=MUTED)
        box.grid(row=2, column=0, sticky="nsew", padx=16)
        box.grid_columnconfigure(0, weight=1)
        for it in items:
            row = ctk.CTkFrame(box, fg_color=CARD, corner_radius=12, border_width=1,
                               border_color=BORDER)
            row.grid(sticky="ew", padx=6, pady=4)
            ctk.CTkLabel(row, text="•  " + it, font=font(13), text_color=TEXT, anchor="w",
                         justify="left", wraplength=390).pack(anchor="w", padx=14, pady=10)
        ctk.CTkButton(self, text="Понятно", height=42, corner_radius=12, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT, font=font(14, "bold"),
                      command=self.destroy).grid(row=3, column=0, sticky="ew", padx=24, pady=14)
        self.after(250, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass


# ======================================================================
#  Окно выбора версии: поиск, вкладки «Релизы / Снапшоты»
# ======================================================================
class VersionPicker(ctk.CTkToplevel):
    MAX_ROWS = 100

    def __init__(self, master, data, on_pick):
        super().__init__(master)
        self.data = data
        self.on_pick = on_pick
        self.title("Выбор версии")
        self.geometry("400x600")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="Версия Minecraft", font=font(20, "bold"),
                     text_color=TEXT, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(20, 12))

        self.search = ctk.CTkEntry(
            self, height=42, corner_radius=12, border_width=1, fg_color=FIELD,
            border_color=BORDER, text_color=TEXT, font=font(14),
            placeholder_text="Поиск или своя версия + Enter",
            placeholder_text_color=MUTED,
        )
        self.search.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.search.bind("<KeyRelease>", lambda e: self._render())
        self.search.bind("<Return>", self._accept_typed)

        self.tab = ctk.CTkSegmentedButton(
            self, values=list(data.keys()), command=lambda _: self._render(),
            fg_color=FIELD, selected_color=SEG_ON, selected_hover_color=SEG_ON_HOVER,
            unselected_color=FIELD, unselected_hover_color=HOVER, text_color=TEXT,
            font=font(13), height=34,
        )
        self.tab.set(list(data.keys())[0])
        self.tab.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))

        self.list = ctk.CTkScrollableFrame(
            self, fg_color="transparent", scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED)
        self.list.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 14))
        self._render()
        self.after(250, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
            self.search.focus_set()
            self.grab_set()
        except Exception:
            pass

    def _items(self):
        q = self.search.get().strip().lower()
        return [v for v in self.data[self.tab.get()] if q in v.lower()]

    def _render(self):
        for w in self.list.winfo_children():
            w.destroy()
        items = self._items()
        for v in items[: self.MAX_ROWS]:
            ctk.CTkButton(
                self.list, text=v, anchor="w", height=36, corner_radius=10,
                fg_color="transparent", hover_color=HOVER, text_color=TEXT,
                font=font(14), command=lambda v=v: self._pick(v),
            ).pack(fill="x", pady=1)
        if not items:
            ctk.CTkLabel(self.list, text="Ничего не найдено.\nEnter — использовать как есть",
                         font=font(13), text_color=MUTED).pack(pady=30)
        elif len(items) > self.MAX_ROWS:
            ctk.CTkLabel(self.list, text=f"Показаны первые {self.MAX_ROWS}, уточни поиск",
                         font=font(12), text_color=MUTED).pack(pady=10)

    def _accept_typed(self, _event=None):
        text = self.search.get().strip()
        items = self._items()
        if text in items:
            self._pick(text)
        elif items:
            self._pick(items[0])
        elif text:
            self._pick(text)

    def _pick(self, version):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        self.on_pick(version)


def apply_local_skin(acc, game_dir):
    """Кладёт скин туда, где его ищет мод CustomSkinLoader (папка LocalSkin)."""
    if not acc.get("skin"):
        return
    src = SKINS_DIR / acc["skin"]
    if not src.exists():
        return
    dst = (Path(game_dir) / "CustomSkinLoader" / "LocalSkin" / "skins"
           / f'{acc["name"]}.png')
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


# ======================================================================
#  Аккаунты: быстрая смена, добавление, ник, скин
# ======================================================================
class AccountsDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._imgs = []
        self.title("Аккаунты")
        self.geometry("460x720")
        self.minsize(460, 560)
        self.configure(fg_color=BG)
        self.transient(app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.body = ctk.CTkScrollableFrame(
            self, fg_color="transparent", scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED)
        self.body.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.body.grid_columnconfigure(0, weight=1)
        self.rebuild()
        self.after(250, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def set_status(self, text, error=False):
        self.status.configure(text=text, text_color=ERROR if error else MUTED)

    def _bind_click(self, widget, command):
        widget.bind("<Button-1>", lambda e: command())
        for child in widget.winfo_children():
            self._bind_click(child, command)

    def rebuild(self):
        app = self.app
        for w in self.body.winfo_children():
            w.destroy()
        self._imgs = []
        active = app.account()

        ctk.CTkLabel(self.body, text="Аккаунты", font=font(22, "bold"), text_color=TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 10))

        # --- список: клик = смена ---
        for i, acc in enumerate(app.cfg["accounts"], start=1):
            is_active = acc["id"] == active["id"]
            row = ctk.CTkFrame(self.body, fg_color=ACTIVE if is_active else CARD, corner_radius=14,
                               border_width=1, border_color=ACCENT if is_active else BORDER,
                               cursor="hand2")
            row.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            row.grid_columnconfigure(1, weight=1)
            img = app.account_avatar(acc, 36)
            self._imgs.append(img)
            ctk.CTkLabel(row, text="", image=img, width=36, height=36).grid(
                row=0, column=0, rowspan=2, padx=(12, 12), pady=10)
            ctk.CTkLabel(row, text=acc["name"], font=font(14, "bold"), text_color=TEXT,
                         anchor="w").grid(row=0, column=1, sticky="sw", pady=(10, 0))
            kind = "Microsoft · " if acc.get("type") == "msa" else ""
            ctk.CTkLabel(row, text=kind + ("Выбран" if is_active else "Нажми, чтобы переключиться"),
                         font=font(11), text_color=ACCENT if is_active else MUTED,
                         anchor="w").grid(row=1, column=1, sticky="nw", pady=(0, 10))
            if not is_active:
                self._bind_click(row, lambda a=acc["id"]: self._switch(a))
        n = len(app.cfg["accounts"])

        # --- добавление ---
        add = ctk.CTkFrame(self.body, fg_color="transparent")
        add.grid(row=n + 1, column=0, sticky="ew", padx=6, pady=(10, 4))
        add.grid_columnconfigure(0, weight=1)
        self.new_entry = app._entry(add, "Ник нового аккаунта")
        self.new_entry.grid(row=0, column=0, sticky="ew")
        self.new_entry.bind("<Return>", lambda e: self._add())
        ctk.CTkButton(add, text="+ Добавить", width=110, height=42, corner_radius=12,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
                      font=font(13, "bold"), command=self._add).grid(row=0, column=1, padx=(10, 0))
        if MSA_CLIENT_ID:
            ctk.CTkButton(add, text="Войти через Microsoft", width=200, height=40, corner_radius=12,
                          border_width=1, fg_color="transparent", hover_color=HOVER,
                          border_color=BORDER, text_color=TEXT, font=font(13),
                          command=self._msa_login).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.msa_label = ctk.CTkLabel(add, text="", font=font(13, "bold"), text_color=ACCENT,
                                      anchor="w", justify="left", wraplength=400)
        self.msa_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # --- настройки выбранного аккаунта ---
        card = app._card(self.body)
        card.grid(row=n + 2, column=0, sticky="ew", padx=6, pady=(14, 6))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text="Настройки аккаунта", font=font(13, "bold"), text_color=MUTED,
                     anchor="w").grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(16, 10))
        big = app.account_avatar(active, 72)
        self._imgs.append(big)
        ctk.CTkLabel(card, text="", image=big, width=72, height=72).grid(
            row=1, column=0, rowspan=2, padx=(20, 16), pady=(0, 10))
        ctk.CTkLabel(card, text=active["name"], font=font(20, "bold"), text_color=TEXT,
                     anchor="w").grid(row=1, column=1, sticky="sw")
        ctk.CTkLabel(card, text="Скин: свой" if active.get("skin") else "Скин: стандартный",
                     font=font(12), text_color=MUTED, anchor="w").grid(row=2, column=1, sticky="nw")

        app._caption(card, "Ник").grid(row=3, column=0, columnspan=2, sticky="w", padx=20, pady=(8, 6))
        nrow = ctk.CTkFrame(card, fg_color="transparent")
        nrow.grid(row=4, column=0, columnspan=2, sticky="ew", padx=20)
        nrow.grid_columnconfigure(0, weight=1)
        self.nick_entry = app._entry(nrow, "Ник")
        self.nick_entry.insert(0, active["name"])
        self.nick_entry.grid(row=0, column=0, sticky="ew")
        self.nick_entry.bind("<Return>", lambda e: self._rename())
        ctk.CTkButton(nrow, text="Сохранить", width=100, height=42, corner_radius=12, border_width=1,
                      fg_color=FIELD, hover_color=HOVER, border_color=BORDER, text_color=TEXT,
                      font=font(13), command=self._rename).grid(row=0, column=1, padx=(10, 0))
        if active.get("type") == "msa":
            self.nick_entry.configure(state="disabled")
            ctk.CTkLabel(card, text="Ник Microsoft-аккаунта берётся из профиля и не меняется",
                         font=font(11), text_color=MUTED, anchor="w").grid(
                row=5, column=0, columnspan=2, sticky="w", padx=20)

        app._caption(card, "Скин").grid(row=6, column=0, columnspan=2, sticky="w", padx=20, pady=(16, 6))
        srow = ctk.CTkFrame(card, fg_color="transparent")
        srow.grid(row=7, column=0, columnspan=2, sticky="ew", padx=20)
        ctk.CTkButton(srow, text="Загрузить скин (PNG)", height=38, corner_radius=12,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
                      font=font(13, "bold"), command=self._pick_skin).pack(side="left")
        ctk.CTkButton(srow, text="Взять по нику", height=38, corner_radius=12, border_width=1,
                      fg_color="transparent", hover_color=HOVER, border_color=BORDER,
                      text_color=TEXT, font=font(13),
                      command=self._nick_skin).pack(side="left", padx=(8, 0))
        if active.get("skin"):
            ctk.CTkButton(srow, text="Убрать", width=80, height=38, corner_radius=12, border_width=1,
                          fg_color="transparent", hover_color=HOVER, border_color=BORDER,
                          text_color=TEXT, font=font(13), command=self._clear_skin
                          ).pack(side="left", padx=(8, 0))

        mods_dir_ok = app.cfg["loader"] != "Vanilla" and app.cfg["last_version"]
        has_mod = bool(mods_dir_ok) and SKIN_MOD_ID in list_installed(app._game_dir() / "mods")
        ctk.CTkLabel(
            card, font=font(12), text_color=ACCENT if has_mod else MUTED, anchor="w", justify="left",
            wraplength=360,
            text=("✓ Поддержка скинов установлена: скин будет виден в игре" if has_mod else
                  "В оффлайн-режиме скин показывает мод CustomSkinLoader (Fabric/Forge). "
                  "Без него в игре будет стандартный скин."),
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=20, pady=(10, 0))
        if not has_mod:
            ctk.CTkButton(card, text="Установить поддержку скинов", height=36, corner_radius=12,
                          border_width=1, fg_color="transparent", hover_color=HOVER,
                          border_color=BORDER, text_color=TEXT, font=font(13),
                          command=self._install_skin_mod).grid(
                row=9, column=0, columnspan=2, sticky="w", padx=20, pady=(8, 0))

        ctk.CTkButton(card, text="Удалить аккаунт", height=36, corner_radius=12, border_width=1,
                      fg_color="transparent", hover_color=HOVER, border_color=ERROR, text_color=ERROR,
                      font=font(13), state="normal" if n > 1 else "disabled",
                      command=self._delete).grid(row=10, column=0, columnspan=2, sticky="w",
                                                 padx=20, pady=(18, 8))
        self.status = ctk.CTkLabel(card, text="", font=font(12), text_color=MUTED, anchor="w",
                                   justify="left", wraplength=380)
        self.status.grid(row=11, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 16))

    # --- действия ---
    def _valid_name(self, name, skip_id=None):
        if not re.fullmatch(NICK_RE, name):
            self.set_status("Ник: 3–16 символов, латиница, цифры или _", True)
            return False
        if any(a["name"].lower() == name.lower() and a["id"] != skip_id
               for a in self.app.cfg["accounts"]):
            self.set_status("Такой аккаунт уже есть", True)
            return False
        return True

    def _switch(self, aid):
        self.app.switch_account(aid)
        self.rebuild()

    def _add(self):
        name = self.new_entry.get().strip()
        if self._valid_name(name):
            self.app.add_account(name)
            self.rebuild()

    def _rename(self):
        acc = self.app.account()
        name = self.nick_entry.get().strip()
        if name == acc["name"]:
            return
        if self._valid_name(name, acc["id"]):
            self.app.rename_account(acc["id"], name)
            self.rebuild()
            self.set_status("Ник изменён")

    def _pick_skin(self):
        path = filedialog.askopenfilename(
            parent=self, title="Выбери файл скина",
            filetypes=[("PNG", "*.png"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            self.app.set_skin(self.app.account()["id"], Path(path))
            self.rebuild()
            self.set_status("Скин сохранён")
        except Exception as e:
            self.set_status(f"Не удалось загрузить скин: {e}", True)

    def _clear_skin(self):
        self.app.clear_skin(self.app.account()["id"])
        self.rebuild()

    def _delete(self):
        self.app.delete_account(self.app.account()["id"])
        self.rebuild()

    def _install_skin_mod(self):
        app = self.app
        if app.cfg["loader"] == "Vanilla" or not app.cfg["last_version"]:
            self.set_status("Выбери версию и загрузчик Fabric или Forge на странице «Играть»", True)
            return
        if app.mod_busy:
            self.set_status("Подожди, пока закончится текущая установка", True)
            return
        app.mod_busy = True
        self.set_status("Установка CustomSkinLoader…")
        threading.Thread(
            target=app._install_worker,
            args=(SKIN_MOD_ID, "CustomSkinLoader", app.cfg["last_version"], app._game_dir() / "mods"),
            daemon=True,
        ).start()

    # --- Microsoft и скин по нику ---
    def _msa_login(self):
        if getattr(self, "_msa_busy", False):
            return
        self._msa_busy = True
        self.msa_label.configure(text="Связываюсь с Microsoft…", text_color=MUTED)
        threading.Thread(target=self._msa_worker, daemon=True).start()

    def _msa_worker(self):
        try:
            code, uri, device_code, interval = auth.device_code_start()
        except Exception as e:
            self.app.q.put(("msa_done", None, str(e)))
            return
        self.app.q.put(("msa_code", code, uri))
        try:
            acc = auth.device_code_wait(device_code, interval)
        except Exception as e:
            self.app.q.put(("msa_done", None, str(e)))
            return
        self.app.q.put(("msa_done", acc, ""))

    def on_msa_code(self, code, uri):
        webbrowser.open(uri)
        self.msa_label.configure(
            text="Открылась страница Microsoft — войди там и введи код:\n"
                 f"{code}",
            text_color=ACCENT)

    def on_msa_done(self, acc, err):
        self._msa_busy = False
        if err or acc is None:
            self.msa_label.configure(text=f"Вход не удался: {err}" if err else "", text_color=ERROR)
            return
        self.msa_label.configure(text="")
        self.app.add_msa_account(acc)
        self.rebuild()
        self.set_status(f"Аккаунт Microsoft «{acc['name']}» добавлен")

    def _nick_skin(self):
        acc = self.app.account()
        self.set_status(f"Ищу скин для «{acc['name']}»…")
        threading.Thread(target=self._nick_skin_worker, args=(acc["name"],), daemon=True).start()

    def _nick_skin_worker(self, name):
        url = auth.skin_by_nick(name)
        if not url:
            self.app.q.put(("acc_status",
                            f"Скин для «{name}» не найден — скорее всего, этот ник без лицензии", True))
            return
        self.app.q.put(("acc_skin_url", url))

    def on_nick_skin(self, url):
        acc = self.app.account()
        try:
            self.app.set_skin_url(acc["id"], url)
            self.rebuild()
            self.set_status("Скин загружен")
        except Exception as e:
            self.set_status(f"Не удалось скачать скин: {e}", True)


# ======================================================================
#  Главное окно
# ======================================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.acc_dialog = None
        self._init_accounts()
        self.q = queue.Queue()
        self.busy = False
        self.mod_busy = False
        self.mod_loading = False
        self.mod_queue = []  # очередь установки: [(pid, title, version, dest, kind)]
        self.mod_queued = set()  # pid'ы в очереди — чтобы помечать кнопки
        self.current_page = None
        self.available_version = ""  # новая версия лаунчера, если нашли
        self._tray = None
        self._quitting = False
        self._search_job = None
        self._last_search = None
        self.all_versions = []
        self.mod_hits = []
        self.mod_hits_key = None
        self.analysis = None
        self.picker = None

        # иконки модов: кэш в памяти + загрузка в фоне
        self.icon_pool = ThreadPoolExecutor(max_workers=6)
        self.icon_cache = {}
        self.icon_pending = set()
        self.icon_failed = set()
        self.icon_waiters = {}
        self.placeholders = {}
        self.desc_labels = []
        self.mod_wrap = 420
        self.backfilled = set()

        # картинки, которые зависят от ширины окна
        self.banner_w = 0
        self.play_w = 0
        self.play_imgs = {}
        self.play_hover = False
        self._banner_job = None
        self._play_job = None

        self.title(LAUNCHER_NAME)
        self.geometry("1000x700")
        self.minsize(920, 660)
        self.configure(fg_color=BG)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=36, pady=30)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.pages = {
            "play": self._build_play(),
            "shop": ShopPage(self),
            "char": CharacterPage(self),
            "mods": self._build_mods(),
            "builds": BuildsPage(self),
            "servers": ServersPage(self),
            "worlds": WorldsPage(self),
            "shots": ScreenshotsPage(self),
            "log": LogPage(self),
            "stats": StatsPage(self),
            "settings": self._build_settings(),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self.show_page("play")

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(50, self._poll)
        self.after(400, self._set_window_icon)
        threading.Thread(target=self._load_versions, daemon=True).start()
        threading.Thread(target=self._check_update, daemon=True).start()
        if self.cfg.get("minimize_to_tray"):
            self._make_tray()
        # .mrpack, переданный лаунчеру (двойной клик по файлу)
        packs = [a for a in sys.argv[1:] if a.lower().endswith(".mrpack")]
        if packs:
            self.after(900, lambda: self.install_pack_files(packs))

    def _set_window_icon(self):
        try:
            self._icon_photo = ImageTk.PhotoImage(visuals.logo(64, ACCENT, ACCENT2))
            self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    # ---------- помощники ----------
    def _caption(self, parent, text):
        return ctk.CTkLabel(parent, text=text, font=font(12), text_color=MUTED, anchor="w")

    def _entry(self, parent, placeholder=""):
        return ctk.CTkEntry(
            parent, height=42, corner_radius=12, border_width=1,
            fg_color=FIELD, border_color=BORDER, text_color=TEXT,
            placeholder_text=placeholder, placeholder_text_color=MUTED,
            font=font(14),
        )

    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=18,
                            border_width=1, border_color=BORDER)

    def _segmented(self, parent, values, command, height=36):
        return ctk.CTkSegmentedButton(
            parent, values=values, command=command, height=height, corner_radius=10,
            fg_color=FIELD, selected_color=SEG_ON, selected_hover_color=SEG_ON_HOVER,
            unselected_color=FIELD, unselected_hover_color=HOVER, text_color=TEXT,
            font=font(13),
        )

    def _title(self, page, title, subtitle):
        ctk.CTkLabel(page, text=title, font=font(30, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w")
        sub = ctk.CTkLabel(page, text=subtitle, font=font(14), text_color=MUTED)
        sub.grid(row=1, column=0, sticky="w", pady=(2, 20))
        return sub

    def _loader_key(self):
        return {"Fabric": "fabric", "Forge": "forge", "Quilt": "quilt",
                "NeoForge": "neoforge"}.get(self.cfg["loader"], "")

    def _build(self):
        bid = self.cfg.get("active_build")
        return next((b for b in self.cfg["builds"] if b["id"] == bid), None) if bid else None

    def _instance_name(self):
        v = self.cfg["last_version"] or "default"
        return {"Fabric": fabric_id(v), "Quilt": quilt_id(v), "Forge": f"forge-{v}",
                "NeoForge": f"neoforge-{v}"}.get(self.cfg["loader"], v)

    def _game_dir(self):
        """Папка игры: у сборки своя, иначе одна на пару версия+загрузчик."""
        b = self._build()
        if b:
            return INSTANCES_DIR / f"build-{b['id']}"
        return instance_dir(self._instance_name())

    # ---------- боковая панель ----------
    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, width=232, fg_color=SIDEBAR, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ns")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(10, weight=1)

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(26, 18))
        self.img_logo = ctkimg(visuals.logo(44, ACCENT, ACCENT2), (44, 44))
        ctk.CTkLabel(brand, text="", image=self.img_logo, width=44, height=44).grid(
            row=0, column=0, rowspan=2, sticky="w")
        ctk.CTkLabel(brand, text=LAUNCHER_NAME, font=font(18, "bold"),
                     text_color=TEXT, anchor="w").grid(row=0, column=0, sticky="sw", padx=(56, 0))
        ctk.CTkLabel(brand, text="Minecraft launcher", font=font(11),
                     text_color=MUTED, anchor="w").grid(row=1, column=0, sticky="nw", padx=(56, 0))

        self.nav = {}
        self.nav_icons = {}
        items = [("play", "Играть"), ("shop", "Магазин"), ("char", "Персонаж"),
                 ("mods", "Моды и паки"), ("builds", "Сборки"),
                 ("servers", "Серверы"), ("worlds", "Миры"), ("shots", "Скриншоты"),
                 ("log", "Лог игры"), ("stats", "Статистика"), ("settings", "Настройки")]
        for i, (key, text) in enumerate(items, start=1):
            off = ctkimg(visuals.nav_icon(key, MUTED), (20, 20))
            on = ctkimg(visuals.nav_icon(key, ACCENT), (20, 20))
            self.nav_icons[key] = (off, on)
            row = ctk.CTkFrame(bar, fg_color="transparent", height=40)
            row.grid(row=i, column=0, sticky="ew", padx=(0, 14), pady=1)
            row.grid_columnconfigure(1, weight=1)
            ind = ctk.CTkFrame(row, width=4, height=20, corner_radius=2, fg_color="transparent")
            ind.grid(row=0, column=0, padx=(8, 6))
            btn = ctk.CTkButton(
                row, text="  " + text, image=off, compound="left", anchor="w",
                height=38, corner_radius=12, fg_color="transparent", hover_color=HOVER,
                text_color=MUTED, font=font(13, "bold"), command=lambda k=key: self.show_page(k),
            )
            btn.grid(row=0, column=1, sticky="ew")
            self.nav[key] = (btn, ind)

        # карточка аккаунта внизу: клик открывает быструю смену и настройки
        prof = ctk.CTkFrame(bar, fg_color=CARD, corner_radius=16, border_width=1,
                            border_color=BORDER, cursor="hand2")
        prof.grid(row=11, column=0, sticky="ew", padx=14, pady=(0, 18))
        prof.grid_columnconfigure(1, weight=1)
        self.avatar_lbl = ctk.CTkLabel(prof, text="", width=40, height=40, cursor="hand2")
        self.avatar_lbl.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=12)
        self.side_name = ctk.CTkLabel(prof, text="", font=font(14, "bold"),
                                      text_color=TEXT, anchor="w", cursor="hand2")
        self.side_name.grid(row=0, column=1, sticky="sw", pady=(12, 0))
        sub = ctk.CTkLabel(prof, text=f"💎 {cos.balance(self.cfg)}  ·  v{LAUNCHER_VERSION}", font=font(11),
                           text_color=MUTED, anchor="w", cursor="hand2")
        self.side_sub = sub
        sub.grid(row=1, column=1, sticky="nw", pady=(0, 12))
        chev = ctk.CTkLabel(prof, text="⇅", font=font(15), text_color=MUTED, cursor="hand2")
        chev.grid(row=0, column=2, rowspan=2, padx=(0, 14))
        for w in (prof, self.avatar_lbl, self.side_name, sub, chev):
            w.bind("<Button-1>", lambda e: self.open_accounts())
        self._update_profile()

    # ---------- аккаунты ----------
    def _init_accounts(self):
        if not self.cfg.get("accounts"):
            acc = {"id": uuid.uuid4().hex[:8], "name": self.cfg.get("username") or "Player", "skin": ""}
            self.cfg["accounts"] = [acc]
            self.cfg["active_account"] = acc["id"]
        self._sync_account()

    def account(self, aid=None):
        aid = aid or self.cfg.get("active_account")
        for a in self.cfg["accounts"]:
            if a["id"] == aid:
                return a
        return self.cfg["accounts"][0]

    def _sync_account(self):
        acc = self.account()
        self.cfg["active_account"] = acc["id"]
        self.cfg["username"] = acc["name"]  # остальной код лаунчера читает ник отсюда

    def account_avatar(self, acc, size):
        skin = SKINS_DIR / acc["skin"] if acc.get("skin") else None
        try:
            if skin and skin.exists():
                return ctkimg(visuals.skin_face(skin, size), (size, size))
        except Exception:
            pass
        return ctkimg(visuals.identicon(acc["name"], size), (size, size))

    def _update_profile(self):
        acc = self.account()
        self.side_name.configure(text=acc["name"])
        self._avatar_img = self.account_avatar(acc, 40)
        self.avatar_lbl.configure(image=self._avatar_img)
        if hasattr(self, "acc_btn"):
            self.acc_btn.configure(text=f"{acc['name']}   ▾")

    def accounts_changed(self):
        self._sync_account()
        save_config(self.cfg)
        self._update_profile()
        if hasattr(self, "tile_mods"):
            self._refresh_tiles()

    def switch_account(self, aid):
        self.cfg["active_account"] = aid
        self.accounts_changed()

    def add_account(self, name):
        acc = {"id": uuid.uuid4().hex[:8], "name": name, "skin": ""}
        self.cfg["accounts"].append(acc)
        self.cfg["active_account"] = acc["id"]
        self.accounts_changed()

    def add_msa_account(self, msa_acc):
        aid = uuid.uuid4().hex[:8]
        acc = {"id": aid, "name": msa_acc["name"], "skin": "", "type": "msa",
               "uuid": msa_acc.get("uuid", ""), "access_token": msa_acc.get("access_token", ""),
               "expires_at": msa_acc.get("expires_at", 0),
               "refresh_token": msa_acc.get("refresh_token", "")}
        if msa_acc.get("skin_url"):
            try:
                auth.download_skin(msa_acc["skin_url"], SKINS_DIR / f"{aid}.png")
                acc["skin"] = f"{aid}.png"
            except Exception:
                pass
        for a in self.cfg["accounts"]:  # этот аккаунт уже есть — просто обновим токены
            if a.get("type") == "msa" and a.get("uuid") and a["uuid"] == acc["uuid"]:
                a.update(acc)
                self.cfg["active_account"] = a["id"]
                self.accounts_changed()
                return
        self.cfg["accounts"].append(acc)
        self.cfg["active_account"] = aid
        self.accounts_changed()

    def set_skin_url(self, aid, url):
        tmp = SKINS_DIR / f"{aid}_tmp.png"
        try:
            auth.download_skin(url, tmp)
            self.set_skin(aid, tmp)
        finally:
            tmp.unlink(missing_ok=True)

    def rename_account(self, aid, name):
        self.account(aid)["name"] = name
        self.accounts_changed()

    def set_skin(self, aid, path):
        im = Image.open(path)
        im.load()
        w, h = im.size
        if w % 64 or h not in (w, w // 2):
            raise ValueError("Скин должен быть PNG 64×64 (или 64×32)")
        SKINS_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{aid}.png"
        im.convert("RGBA").save(SKINS_DIR / name, "PNG")
        self.account(aid)["skin"] = name
        self.accounts_changed()

    def clear_skin(self, aid):
        acc = self.account(aid)
        if acc.get("skin"):
            (SKINS_DIR / acc["skin"]).unlink(missing_ok=True)
        acc["skin"] = ""
        self.accounts_changed()

    def delete_account(self, aid):
        if len(self.cfg["accounts"]) < 2:
            return
        self.clear_skin(aid)
        self.cfg["accounts"] = [a for a in self.cfg["accounts"] if a["id"] != aid]
        if self.cfg["active_account"] == aid:
            self.cfg["active_account"] = self.cfg["accounts"][0]["id"]
        self.accounts_changed()

    def open_accounts(self):
        if self.acc_dialog is not None and self.acc_dialog.winfo_exists():
            self.acc_dialog.lift()
            self.acc_dialog.focus_force()
            return
        self.acc_dialog = AccountsDialog(self)

    def show_page(self, key):
        if hasattr(self, "ram"):
            self.save_all()
        old = getattr(self, "current_page", None)
        if old and old != key and hasattr(self.pages[old], "on_hide"):
            self.pages[old].on_hide()
        self.current_page = key
        self.pages[key].tkraise()
        for k, (btn, ind) in self.nav.items():
            active = k == key
            btn.configure(fg_color=ACTIVE if active else "transparent",
                          text_color=ACCENT if active else MUTED,
                          image=self.nav_icons[k][1 if active else 0])
            ind.configure(fg_color=ACCENT if active else "transparent")
        page = self.pages[key]
        if key == "mods":
            self._on_mods_shown()
        elif key == "play":
            self._refresh_tiles()
        elif hasattr(page, "on_show"):
            page.on_show()

    # ================== страница «Играть» (лобби) ==================
    def _build_play(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(4, weight=1)

        self.banner_lbl = ctk.CTkLabel(page, text="", height=LOBBY_H)
        self.banner_lbl.grid(row=0, column=0, sticky="ew")
        self._set_banner(700)
        page.bind("<Configure>", self._on_play_page_configure)

        # быстрые переходы в стиле современных лаунчеров
        quick = ctk.CTkFrame(page, fg_color="transparent")
        quick.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        quick.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="quick")
        for col, (key, label, color, hover) in enumerate((
                ("shop", "🎁  Магазин", "#7c3aed", "#8b5cf6"),
                ("char", "👤  Персонаж", "#0284c7", "#0ea5e9"),
                ("builds", "🧱  Сборки", "#b45309", "#f59e0b"),
                ("servers", "🌐  Серверы", "#059669", "#10b981"))):
            ctk.CTkButton(quick, text=label, height=56, corner_radius=14,
                          fg_color=color, hover_color=hover, text_color="#ffffff",
                          font=font(15, "bold"), command=lambda k=key: self.show_page(k)
                          ).grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))

        card = self._card(page)
        card.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=22, pady=16)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=1)

        self._caption(inner, "Аккаунт").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.acc_btn = ctk.CTkButton(
            inner, text=f"{self.account()['name']}   ▾", anchor="w", height=42, corner_radius=12,
            border_width=1, fg_color=FIELD, hover_color=HOVER, border_color=BORDER,
            text_color=TEXT, font=font(14), command=self.open_accounts,
        )
        self.acc_btn.grid(row=1, column=0, sticky="ew")

        self._caption(inner, "Версия").grid(row=0, column=1, sticky="w", padx=(14, 0), pady=(0, 6))
        self.version_btn = ctk.CTkButton(
            inner, text=self._version_text(), anchor="w", height=42, corner_radius=12,
            border_width=1, fg_color=FIELD, hover_color=HOVER, border_color=BORDER,
            text_color=TEXT, font=font(14), command=self.open_picker,
        )
        self.version_btn.grid(row=1, column=1, sticky="ew", padx=(14, 0))

        self._caption(inner, "Загрузчик").grid(row=0, column=2, sticky="w", padx=(14, 0), pady=(0, 6))
        self.loader = self._segmented(
            inner, ["Vanilla", "Fabric", "Forge", "Quilt", "NeoForge"], self._set_loader, height=42)
        self.loader.set(self.cfg["loader"])
        self.loader.grid(row=1, column=2, sticky="e", padx=(14, 0))

        tiles = ctk.CTkFrame(page, fg_color="transparent")
        tiles.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        tiles.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="tile")
        self.tile_ram = self._tile(tiles, "Память", 0)
        self.tile_loader = self._tile(tiles, "Загрузчик", 1)
        self.tile_mods = self._tile(tiles, "Модов", 2)
        self.tile_crystals = self._tile_btn(tiles, "Кристаллы", 3, lambda: self.show_page("shop"))

        bottom = ctk.CTkFrame(page, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        bottom.grid_columnconfigure(0, weight=1)

        self.status = ctk.CTkLabel(bottom, text="", font=font(13), text_color=MUTED,
                                   anchor="w", justify="left", wraplength=640)
        self.status.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.progress = ctk.CTkProgressBar(bottom, height=8, corner_radius=4,
                                           fg_color=BORDER, progress_color=ACCENT)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        # кнопка «Играть»: обычная скруглённая кнопка (раньше была картинка — на некоторых ПК не рисовалась)
        self.play_btn = ctk.CTkButton(
            bottom, text="Играть", height=PLAY_H, corner_radius=16, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT, text_color_disabled=TEXT,
            font=font(19, "bold"), command=self.on_play,
        )
        self.play_btn.grid(row=2, column=0, sticky="ew")

        self.chest_btn = ctk.CTkButton(
            bottom, text="🎁 Сундук за игру", height=PLAY_H, corner_radius=16,
            fg_color=FIELD, hover_color=FIELD, text_color=MUTED, text_color_disabled=MUTED,
            font=font(15, "bold"), command=self.claim_chest, state="disabled",
        )
        self.chest_btn.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self._refresh_chest_btn()
        return page

    def _tile_btn(self, parent, caption, col, command):
        """Плитка-кнопка (для кристаллов: клик открывает магазин)."""
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14, border_width=1,
                         border_color=BORDER, cursor="hand2")
        f.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 12, 0))
        ctk.CTkLabel(f, text=caption, font=font(12), text_color=MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 0))
        value = ctk.CTkLabel(f, text="", font=font(18, "bold"), text_color=ACCENT, anchor="w")
        value.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 14))
        for w in (f, value):
            w.bind("<Button-1>", lambda e: command())
        return value

    def _refresh_chest_btn(self):
        if not hasattr(self, "chest_btn"):
            return
        ready, total, need = cos.playtime_chest_state(self.cfg)
        if ready > 0:
            self.chest_btn.configure(
                text=f"🎁 Забрать сундук{'ы' if ready > 1 else ''} ({ready})",
                state="normal", fg_color="#f59e0b", hover_color="#d97706",
                text_color="#231400", text_color_disabled=MUTED)
        else:
            self.chest_btn.configure(text=f"🎁 Сундук через {cos.fmt_wait(need)} игры",
                                     state="disabled", fg_color=FIELD, hover_color=FIELD,
                                     text_color=MUTED, text_color_disabled=MUTED)

    def claim_chest(self):
        events, err = cos.claim_playtime_chest(self.cfg)
        if err:
            return self._set_status(err, ERROR)
        save_config(self.cfg)
        self._refresh_lobby()
        show_drop_dialog(self, events, "Сундук за игру")

    def _refresh_lobby(self):
        """Обновляет всё, что зависит от кристаллов и косметики."""
        self._refresh_banner()
        self._refresh_chest_btn()
        self._refresh_tiles()
        if hasattr(self, "side_sub"):
            self.side_sub.configure(text=f"💎 {cos.balance(self.cfg)}  ·  v{LAUNCHER_VERSION}")

    def _lobby_character(self):
        try:
            acc = self.account()
            path = SKINS_DIR / acc["skin"] if acc.get("skin") else None
            skin = path.read_bytes() if path and path.exists() else None
            return cos.render_character(skin, cos.equipped(self.cfg), view="front", scale=6)
        except Exception:
            return None

    def _tile(self, parent, caption, col):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        f.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 12, 0))
        ctk.CTkLabel(f, text=caption, font=font(12), text_color=MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 0))
        value = ctk.CTkLabel(f, text="", font=font(18, "bold"), text_color=TEXT, anchor="w")
        value.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 14))
        return value

    def _refresh_tiles(self):
        self.tile_ram.configure(text=f"{self.cfg['ram_mb'] / 1024:.1f} ГБ")
        self.tile_loader.configure(text=self.cfg["loader"])
        count = "—"
        if self.cfg["loader"] != "Vanilla" and self.cfg["last_version"]:
            count = str(len(list_installed(self._game_dir() / "mods")))
        self.tile_mods.configure(text=count)
        self.tile_crystals.configure(text=f"{cos.balance(self.cfg)} 💎")

    # --- фон лобби: лучи, блёстки и твой персонаж с косметикой ---
    def _set_banner(self, w):
        self.banner_w = w
        pil = visuals.lobby_backdrop(w, LOBBY_H, character=self._lobby_character(),
                                     accent=ACCENT)
        self._banner_img = ctkimg(pil, (w, LOBBY_H))
        self.banner_lbl.configure(image=self._banner_img)

    def _refresh_banner(self):
        if hasattr(self, "banner_lbl"):
            self._set_banner(self.banner_w or 700)

    def _on_play_page_configure(self, event):
        w = max(480, event.width)
        if abs(w - self.banner_w) < 8:
            return
        if self._banner_job:
            self.after_cancel(self._banner_job)
        self._banner_job = self.after(150, lambda: self._set_banner(w))

    def _apply_play_image(self):
        """Внешний вид кнопки: обычная / занята (идёт подготовка или игра запущена)."""
        if self.busy:
            dim = rgbhex(visuals.mix(visuals.hex_rgb(ACCENT), visuals.hex_rgb(BG), 0.62))
            self.play_btn.configure(fg_color=dim, hover_color=dim)
        else:
            self.play_btn.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER)

    # --- версия и загрузчик ---
    def _version_text(self):
        v = self.cfg["last_version"]
        return f"{v}   ▾" if v else "Выбрать версию   ▾"

    def _version_lists(self):
        if self.all_versions:
            ids = [v for v, _ in self.all_versions]
            cut = ids.index(OLDEST_VERSION) + 1 if OLDEST_VERSION in ids else len(ids)
            window = self.all_versions[:cut]
            return {
                "Релизы": [v for v, t in window if t == "release"],
                "Снапшоты": [v for v, t in window if t == "snapshot"],
            }
        offline = [v for v in installed_versions() if not v.startswith("fabric-")]
        return {"Релизы": offline, "Снапшоты": []}

    def open_picker(self):
        if self.picker is not None and self.picker.winfo_exists():
            self.picker.focus_force()
            return
        self.picker = VersionPicker(self, self._version_lists(), self._user_set_version)

    def _user_set_version(self, version):
        self.cfg["active_build"] = ""  # ручной выбор версии = выход из сборки
        self._set_version(version)

    def _set_version(self, version):
        self.cfg["last_version"] = version
        self.version_btn.configure(text=self._version_text())
        save_config(self.cfg)
        self._refresh_tiles()
        self._refresh_banner()

    def _set_loader(self, value):
        self.cfg["loader"] = value
        self.cfg["active_build"] = ""
        save_config(self.cfg)
        self._refresh_tiles()
        self._refresh_banner()

    # ================== страница «Моды / Ресурспаки / Шейдеры» ==================
    KINDS = {"Моды": "mod", "Ресурспаки": "resourcepack", "Шейдеры": "shader"}

    # слаги категорий Modrinth (только для модов; пусто = все)
    CATS = {"Все": [], "Оптимизация": ["optimization"], "Технологии": ["technology"],
            "Магия": ["magic"], "Приключения": ["adventure"], "Утилиты": ["utility"],
            "Декор": ["decoration"], "Еда": ["food"], "Транспорт": ["transport"]}

    def _kind(self):
        return self.KINDS[self.kind_tabs.get()]

    def _kind_dir(self, kind=None):
        return self._game_dir() / KIND_DIRS[kind or self._kind()]

    def _cats(self):
        return self.CATS.get(self.cat_tabs.get(), []) if hasattr(self, "cat_tabs") else []

    def _mods_key(self):
        return (self.cfg["last_version"], self._kind(), self._loader_key(), tuple(self._cats()))

    def _kind_ready(self):
        """None — можно работать; иначе (заголовок, подсказка)."""
        if not self.cfg["last_version"]:
            return ("Версия не выбрана", "Выбери версию Minecraft на странице «Играть»")
        if self._kind() == "mod" and self.cfg["loader"] == "Vanilla":
            return ("Моды ставятся на Fabric, Forge, Quilt или NeoForge",
                    "Переключи загрузчик на странице «Играть»")
        return None

    def _build_mods(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(5, weight=1)
        ctk.CTkLabel(page, text="Моды и паки", font=font(30, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w")
        self.mods_subtitle = ctk.CTkLabel(page, text="", font=font(14), text_color=MUTED)
        self.mods_subtitle.grid(row=1, column=0, sticky="w", pady=(2, 16))
        page.bind("<Configure>", self._on_mods_page_configure)

        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        self.mod_query = self._entry(bar, "Поиск на Modrinth")
        self.mod_query.grid(row=0, column=0, sticky="ew")
        self.mod_query.bind("<Return>", lambda e: self.mods_search(force=True))
        self.mod_query.bind("<KeyRelease>", self._on_query_key)
        ctk.CTkButton(
            bar, text="Найти", width=96, height=42, corner_radius=12,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
            font=font(14, "bold"), command=self.mods_search,
        ).grid(row=0, column=1, padx=(10, 0))
        ctk.CTkButton(
            bar, text="Из файла", width=110, height=42, corner_radius=12, border_width=1,
            fg_color=FIELD, hover_color=HOVER, border_color=BORDER, text_color=TEXT,
            font=font(13), command=self.mod_from_file,
        ).grid(row=0, column=2, padx=(10, 0))
        ctk.CTkButton(
            bar, text="Папка", width=84, height=42, corner_radius=12, border_width=1,
            fg_color=FIELD, hover_color=HOVER, border_color=BORDER, text_color=TEXT,
            font=font(13), command=self.open_mods_folder,
        ).grid(row=0, column=3, padx=(10, 0))

        tabsbar = ctk.CTkFrame(page, fg_color="transparent")
        tabsbar.grid(row=3, column=0, sticky="ew", pady=(14, 4))
        tabsbar.grid_columnconfigure(2, weight=1)
        self.kind_tabs = self._segmented(tabsbar, list(self.KINDS), lambda _: self._on_kind_changed(), 34)
        self.kind_tabs.set("Моды")
        self.kind_tabs.grid(row=0, column=0)
        self.mod_tabs = self._segmented(tabsbar, ["Поиск", "Установленные"],
                                        lambda _: self._render_mods(), height=34)
        self.mod_tabs.set("Поиск")
        self.mod_tabs.grid(row=0, column=1, padx=(10, 0))
        ctk.CTkButton(
            tabsbar, text="Проверить обновления", height=34, corner_radius=10, border_width=1,
            fg_color=FIELD, hover_color=HOVER, border_color=BORDER, text_color=TEXT,
            font=font(13), command=self.mods_check,
        ).grid(row=0, column=3)
        ctk.CTkButton(
            tabsbar, text="⚡ Оптимизировать", height=34, corner_radius=10, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT, font=font(13, "bold"),
            command=self.optimize_click,
        ).grid(row=0, column=4, padx=(10, 0))

        self.cat_tabs = self._segmented(page, list(self.CATS), lambda _: self._on_cat_changed(), 30)
        self.cat_tabs.set("Все")
        self.cat_tabs.grid(row=4, column=0, sticky="w", pady=(2, 8))

        self.mod_list = ctk.CTkScrollableFrame(
            page, fg_color="transparent", scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED)
        self.mod_list.grid(row=5, column=0, sticky="nsew")

        self.mod_status = ctk.CTkLabel(page, text="", font=font(13), text_color=MUTED,
                                       anchor="w", justify="left", wraplength=640)
        self.mod_status.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        return page

    def _on_mods_page_configure(self, event):
        wrap = max(260, event.width - 290)
        if abs(wrap - self.mod_wrap) < 10:
            return
        self.mod_wrap = wrap
        for lbl in list(self.desc_labels):
            try:
                lbl.configure(wraplength=wrap)
            except tk.TclError:
                self.desc_labels.remove(lbl)

    def _on_kind_changed(self):
        self.mod_hits, self.mod_hits_key, self.analysis = [], None, None
        # категории имеют смысл только для модов
        if hasattr(self, "cat_tabs"):
            if self._kind() == "mod":
                self.cat_tabs.grid()
            else:
                self.cat_tabs.grid_remove()
        self._on_mods_shown()

    def _on_cat_changed(self):
        self.mod_hits, self.mod_hits_key = [], None
        self._on_mods_shown()

    def _on_mods_shown(self):
        ready = self._kind_ready()
        if ready:
            self.mods_subtitle.configure(text=ready[0])
            self._render_mods()
            return
        b = self._build()
        extra = f" · сборка «{b['name']}»" if b else ""
        self.mods_subtitle.configure(
            text=f"{self.cfg['loader']} · Minecraft {self.cfg['last_version']}{extra}")
        if self.mod_hits_key != self._mods_key():
            self.mods_search()
            return
        self._render_mods()

    def _set_mod_status(self, text, error=False):
        color = ERROR if error else (ACCENT if text.startswith("Установлено") else MUTED)
        self.mod_status.configure(text=text, text_color=color)

    def _search_key(self):
        """Ключ результата поиска: версия, тип, загрузчик, категории и сам запрос."""
        return (self.cfg["last_version"], self._kind(), self._loader_key(),
                tuple(self._cats()), self.mod_query.get().strip())

    def _on_query_key(self, event):
        if event.keysym in ("Return", "Escape", "Up", "Down", "Left", "Right", "Home", "End"):
            return
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(700, self._live_search)

    def _live_search(self):
        self._search_job = None
        if self._kind_ready():
            return
        if self.mod_query.get().strip() != self._last_search:
            self.mods_search()

    def mods_search(self, force=False):
        if self._kind_ready():
            self._render_mods()
            return
        key = self._search_key()
        if not force and self.mod_hits_key == key:
            self._render_mods()
            return
        self._last_search = key[4]
        self.mod_loading = True
        self._set_mod_status("Поиск…")
        self._render_mods()
        threading.Thread(target=self._search_worker, args=(key[4], key),
                         daemon=True).start()

    def _search_worker(self, query, key):
        version, kind, loader, cats, _q = key
        try:
            hits = search_mods(query, version, loader, kind=kind, categories=cats)
            self.q.put(("mods_hits", hits, key))
        except Exception as e:
            self.q.put(("mods_status", f"Ошибка поиска: {e}", True))

    # --- иконки ---
    def _placeholder(self, title, color):
        key = (title, color)
        if key not in self.placeholders:
            self.placeholders[key] = ctkimg(visuals.placeholder_icon(title, color, ICON), (ICON, ICON))
        return self.placeholders[key]

    def _attach_icon(self, label, title, color, url):
        if url and url in self.icon_cache:
            label.configure(image=self.icon_cache[url])
            return
        label.configure(image=self._placeholder(title, color))
        if url and url not in self.icon_failed:
            self.icon_waiters.setdefault(url, []).append(label)
            if url not in self.icon_pending:
                self.icon_pending.add(url)
                self.icon_pool.submit(self._icon_worker, url)

    def _icon_worker(self, url):
        try:
            cache = CACHE_DIR / "icons"
            cache.mkdir(parents=True, exist_ok=True)
            path = cache / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".bin")
            if path.exists():
                raw = path.read_bytes()
            else:
                raw = get_bytes(url)
                path.write_bytes(raw)
            self.q.put(("icon", url, visuals.process_icon(raw, ICON)))
        except Exception:
            self.q.put(("icon", url, None))

    def _on_icon(self, url, pil):
        self.icon_pending.discard(url)
        labels = self.icon_waiters.pop(url, [])
        if pil is None:
            self.icon_failed.add(url)
            return
        img = ctkimg(pil, (ICON, ICON))
        self.icon_cache[url] = img
        for lbl in labels:
            try:
                if lbl.winfo_exists():
                    lbl.configure(image=img)
            except tk.TclError:
                pass

    # --- строки списка ---
    def _mod_row(self, title, desc, downloads, tags, btn_text, command, icon_url="", color=None,
                 state="normal", danger=False, parent=None, extra=None):
        row = ctk.CTkFrame(parent or self.mod_list, fg_color=CARD, corner_radius=16,
                           border_width=1, border_color=BORDER)
        row.pack(fill="x", padx=(0, 8), pady=5)
        row.grid_columnconfigure(1, weight=1)

        icon = ctk.CTkLabel(row, text="", width=ICON, height=ICON)
        icon.grid(row=0, column=0, rowspan=3, padx=(14, 14), pady=14)
        self._attach_icon(icon, title, color, icon_url)

        ctk.CTkLabel(row, text=title, font=font(15, "bold"), text_color=TEXT,
                     anchor="w").grid(row=0, column=1, sticky="sw", pady=(14, 0))
        if desc:
            d = ctk.CTkLabel(row, text=desc, font=font(12), text_color=MUTED, anchor="w",
                             justify="left", wraplength=self.mod_wrap)
            d.grid(row=1, column=1, sticky="w")
            self.desc_labels.append(d)
        meta = ctk.CTkFrame(row, fg_color="transparent")
        meta.grid(row=2, column=1, sticky="w", pady=(4, 14))
        if downloads:
            ctk.CTkLabel(meta, text=downloads, font=font(12, "bold"),
                         text_color=ACCENT, anchor="w").pack(side="left", padx=(0, 8))
        for tag in tags:
            ctk.CTkLabel(meta, text=f" {tag} ", font=font(11), text_color=MUTED, height=20,
                         corner_radius=8, fg_color=FIELD).pack(side="left", padx=(0, 6))

        if danger:
            style = dict(fg_color="transparent", hover_color=HOVER, border_width=1,
                         border_color=ERROR, text_color=ERROR)
        else:
            style = dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
                         text_color_disabled=MUTED, border_width=0)
        if state == "disabled":
            style = dict(fg_color=FIELD, hover_color=FIELD, border_width=1, border_color=BORDER,
                         text_color=MUTED, text_color_disabled=MUTED)
        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.grid(row=0, column=2, rowspan=3, padx=(10, 16))
        ctk.CTkButton(btns, text=btn_text, width=124, height=36, corner_radius=10,
                      font=font(13, "bold"), state=state, command=command, **style).pack()
        for text, cmd in (extra or []):
            ctk.CTkButton(btns, text=text, width=124, height=28, corner_radius=10, border_width=1,
                          fg_color="transparent", hover_color=HOVER, border_color=BORDER,
                          text_color=MUTED, font=font(12), command=cmd).pack(pady=(6, 0))

    def _hint(self, title, sub="", parent=None):
        box = ctk.CTkFrame(parent or self.mod_list, fg_color="transparent")
        box.pack(pady=50)
        ctk.CTkLabel(box, text=title, font=font(16, "bold"), text_color=TEXT).pack()
        if sub:
            ctk.CTkLabel(box, text=sub, font=font(13), text_color=MUTED,
                         justify="center").pack(pady=(6, 0))

    def _render_mods(self):
        for w in self.mod_list.winfo_children():
            w.destroy()
        self.desc_labels = []
        self.icon_waiters = {}  # старые строки уничтожены
        ready = self._kind_ready()
        if ready:
            self._hint(*ready)
            return
        kind, dest = self._kind(), self._kind_dir()
        installed = list_installed(dest)

        if self.mod_tabs.get() == "Установленные":
            self._render_analysis()
            if not installed:
                self._hint("Пока ничего не установлено", "Найди что-нибудь на вкладке «Поиск»")
            self._maybe_backfill(installed)
            upd = {u["pid"]: u for u in self._analysis_data().get("updates", [])}
            for pid, info in installed.items():
                tags = [f"↑ {upd[pid]['new']}"] if pid in upd else []
                self._mod_row(info["title"], info["filename"], info.get("version", ""), tags,
                              "Удалить", lambda pid=pid: self.remove_click(pid),
                              icon_url=info.get("icon_url", ""), danger=True)
            return

        if kind == "shader":
            self._shader_hint()
        if self.mod_loading:
            self._hint("Ищу…")
            return
        if not self.mod_hits:
            self._hint("Ничего не найдено", "Попробуй другой запрос")
        for hit in self.mod_hits:
            desc = hit.get("description", "")
            if len(desc) > 130:
                desc = desc[:127] + "…"
            tags = [c.capitalize() for c in hit.get("display_categories", [])
                    if c not in LOADERS][:3]
            meta = f'↓ {short_number(hit.get("downloads", 0))}  ·  {hit.get("author", "")}'
            done = hit["project_id"] in installed
            queued = hit["project_id"] in self.mod_queued
            self._mod_row(hit["title"], desc, meta, tags,
                          "✓ Установлен" if done else ("В очереди…" if queued else "Установить"),
                          lambda h=hit: self.install_click(h),
                          icon_url=hit.get("icon_url") or "", color=hit.get("color"),
                          state="disabled" if (done or queued) else "normal")

    def _shader_hint(self):
        mods = list_installed(self._game_dir() / "mods")
        if any(i["title"].lower().startswith(("iris", "oculus")) for i in mods.values()):
            return
        card = self._card(self.mod_list)
        card.pack(fill="x", padx=(0, 8), pady=(0, 8))
        fabric = self.cfg["loader"] == "Fabric"
        text = ("Шейдерам нужен мод Iris. Поставь его один раз — и паки заработают." if fabric else
                "Шейдерам нужен загрузчик с поддержкой шейдеров: на Fabric это Iris, на Forge — Oculus "
                "(найди на вкладке «Моды»). На Vanilla шейдеры не работают.")
        ctk.CTkLabel(card, text=text, font=font(13), text_color=TEXT, anchor="w", justify="left",
                     wraplength=self.mod_wrap + 100).pack(side="left", padx=18, pady=14)
        if fabric:
            ctk.CTkButton(card, text="Установить Iris", height=36, corner_radius=10, fg_color=ACCENT,
                          hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT, font=font(13, "bold"),
                          command=self.install_iris).pack(side="right", padx=18)

    def install_iris(self):
        if self.mod_busy:
            return
        self.mod_busy = True
        threading.Thread(target=self._install_worker,
                         args=("iris", "Iris Shaders", self.cfg["last_version"],
                               self._game_dir() / "mods", "mod"), daemon=True).start()

    # --- проверка обновлений и конфликтов ---
    def _analysis_key(self):
        return (str(self._kind_dir()),) + self._mods_key()

    def _analysis_data(self):
        a = self.analysis
        return a if a and a.get("key") == self._analysis_key() else {}

    def _render_analysis(self):
        a = self._analysis_data()
        if not a:
            return
        problems, updates = a["problems"], a["updates"]
        card = ctk.CTkFrame(self.mod_list, fg_color=CARD, corner_radius=16, border_width=1,
                            border_color="#fbbf24" if problems else ACCENT)
        card.pack(fill="x", padx=(0, 8), pady=(0, 8))
        if not problems and not updates:
            ctk.CTkLabel(card, text="✓ Всё актуально, конфликтов не найдено", font=font(14, "bold"),
                         text_color=ACCENT).pack(anchor="w", padx=18, pady=14)
            return
        for line in problems:
            ctk.CTkLabel(card, text="⚠ " + line, font=font(13), text_color="#fbbf24", anchor="w",
                         justify="left", wraplength=self.mod_wrap + 120).pack(anchor="w", padx=18, pady=(10, 0))
        if updates:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=12)
            ctk.CTkLabel(row, text=f"Доступно обновлений: {len(updates)}", font=font(14, "bold"),
                         text_color=TEXT).pack(side="left")
            ctk.CTkButton(row, text=f"Обновить все ({len(updates)})", height=34, corner_radius=10,
                          fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
                          font=font(13, "bold"), command=self.update_all_click).pack(side="right")
        else:
            ctk.CTkFrame(card, height=8, fg_color="transparent").pack()

    def mods_check(self):
        if self._kind_ready() or self.mod_busy:
            return
        self.mod_tabs.set("Установленные")
        dest = self._kind_dir()
        version, kind, loader = self._mods_key()
        self.mod_busy = True
        threading.Thread(target=self._check_worker,
                         args=(dest, version, loader, kind, self._analysis_key()), daemon=True).start()
        self._render_mods()

    def _check_worker(self, dest, version, loader, kind, key):
        q = self.q
        try:
            res = analyze(dest, version, loader, kind, status=lambda t: q.put(("mods_status", t, False)))
            res["key"] = key
            q.put(("mods_analysis", res))
            q.put(("mods_status", "Проверка завершена", False))
        except Exception as e:
            q.put(("mods_status", f"Ошибка проверки: {e}", True))
        finally:
            q.put(("mods_idle",))

    def optimize_click(self):
        """Ставит набор модов-ускорителей (Sodium, Lithium, FerriteCore…) для выбранной версии."""
        if self.mod_busy:
            return
        if self.cfg["loader"] == "Vanilla" or not self.cfg["last_version"]:
            self._set_mod_status("Для оптимизации выбери Fabric или Forge на странице «Играть»", True)
            return
        self.kind_tabs.set("Моды")
        self.mod_tabs.set("Установленные")
        self.mod_busy = True
        threading.Thread(target=self._optimize_worker,
                         args=(self._game_dir() / "mods", self.cfg["last_version"], self._loader_key()),
                         daemon=True).start()

    def _optimize_worker(self, dest, version, loader):
        q = self.q
        items = OPT_MODS.get(loader, [])
        ok, no_version, net_fail = [], [], []
        for slug, title in items:
            try:
                q.put(("mods_status", f"Оптимизация: {title}…", False))
                install_mod(slug, version, loader, dest, kind="mod")
                ok.append(title)
            except Exception as e:
                (no_version if "нет версии" in str(e) else net_fail).append(title)
        text = f"Установлено: {len(ok)} из {len(items)} модов-ускорителей"
        if no_version:
            text += f". Нет под {version}: {', '.join(no_version)}"
        if net_fail:
            text += f". Ошибка сети: {', '.join(net_fail)}"
        q.put(("mods_status", text, bool(net_fail) and not ok))
        q.put(("mods_idle",))

    def update_all_click(self):
        updates = self._analysis_data().get("updates")
        if not updates or self.mod_busy:
            return
        self.mod_busy = True
        version, kind, loader = self._mods_key()
        threading.Thread(target=self._update_worker,
                         args=(self._kind_dir(), version, loader, kind, list(updates)), daemon=True).start()

    def _update_worker(self, dest, version, loader, kind, updates):
        q = self.q
        try:
            for u in updates:
                install_mod(u["pid"], version, loader, dest,
                            status=lambda t: q.put(("mods_status", t, False)), kind=kind)
            q.put(("analysis_clear",))
            q.put(("mods_status", f"Установлено: обновлено {len(updates)}", False))
        except Exception as e:
            traceback.print_exc()
            q.put(("mods_status", f"Ошибка обновления: {e}", True))
        finally:
            q.put(("mods_idle",))

    # --- фоновое дополнение иконок ---
    def _maybe_backfill(self, installed):
        """Поставленное старой версией лаунчера не знает свою иконку — узнаём один раз."""
        key = str(self._kind_dir())
        if key in self.backfilled or self.mod_busy:
            return
        if any("icon_url" not in info for info in installed.values()):
            self.backfilled.add(key)
            threading.Thread(target=self._backfill_worker, args=(self._kind_dir(),),
                             daemon=True).start()

    def _backfill_worker(self, dest):
        try:
            fill_missing_icons(dest)
        except Exception:
            pass
        self.q.put(("mods_refresh",))

    # --- установка / удаление (очередь: можно нажимать на несколько модов подряд) ---
    def _enqueue_mod(self, pid, title, version, dest, kind="mod"):
        self.mod_queue.append((pid, title, version, dest, kind))
        self.mod_queued.add(pid)
        if not self.mod_busy:
            self.mod_busy = True
            self._run_next_mod()

    def _run_next_mod(self):
        if not self.mod_queue:
            self.q.put(("mods_idle",))
            return
        pid, title, version, dest, kind = self.mod_queue[0]
        threading.Thread(target=self._install_worker,
                         args=(pid, title, version, dest, kind), daemon=True).start()

    def install_click(self, hit):
        if self._kind_ready():
            return
        if hit["project_id"] in self.mod_queued:
            return
        self._enqueue_mod(hit["project_id"], hit["title"], self.cfg["last_version"],
                          self._kind_dir(), self._kind())
        self._set_mod_status(f"В очереди: {hit['title']}")
        self._render_mods()

    def mod_from_file(self):
        """Копирует .jar из файла в папку модов/паков текущей версии (ставил сам — знаю имя файла)."""
        ready = self._kind_ready()
        if ready and self._kind() == "mod":
            self._set_mod_status(ready[0], True)
            return
        ext = "*.jar" if self._kind() == "mod" else "*.zip"
        paths = filedialog.askopenfilenames(
            title="Выбери файлы", filetypes=[("Файлы", ext), ("Все файлы", "*.*")])
        if not paths:
            return
        dest = self._kind_dir()
        dest.mkdir(parents=True, exist_ok=True)
        n = 0
        for p in paths:
            src = Path(p)
            try:
                shutil.copyfile(src, dest / src.name)
                n += 1
            except Exception as e:
                self._set_mod_status(f"Не удалось скопировать {src.name}: {e}", True)
                return
        self.mod_tabs.set("Установленные")
        self._set_mod_status(f"Установлено из файла: {n}")
        self._render_mods()

    def _install_worker(self, pid, title, version, dest, kind="mod"):
        q = self.q
        try:
            q.put(("mods_status", f"Установка: {title}", False))
            install_mod(pid, version, self._loader_key(), dest,
                        status=lambda t: q.put(("mods_status", t, False)), kind=kind)
            q.put(("mods_status", f"Установлено: {title}", False))
            cos.bump_counter(self.cfg, "mods")
            save_config(self.cfg)
        except Exception as e:
            traceback.print_exc()
            q.put(("mods_status", f"Ошибка: {e}", True))
        finally:
            self.mod_queued.discard(pid)
            if self.mod_queue and self.mod_queue[0][0] == pid:
                self.mod_queue.pop(0)
            if self.mod_queue:
                self._run_next_mod()
            else:
                q.put(("mods_idle",))

    def remove_click(self, pid):
        if self.mod_busy:
            return
        remove_mod(pid, self._kind_dir())
        self._set_mod_status("Удалено")
        self._render_mods()

    def open_mods_folder(self):
        if self.cfg["last_version"]:
            open_folder(self._kind_dir())

    # ================== страница «Настройки» ==================
    def _build_settings(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)
        self._title(page, "Настройки", "Память, Java и папка игры")

        scroll = ctk.CTkScrollableFrame(
            page, fg_color="transparent", scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED)
        scroll.grid(row=2, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # --- память ---
        card = self._card(scroll)
        card.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 14))
        card.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 8))
        head.grid_columnconfigure(0, weight=1)
        self._caption(head, "Оперативная память").grid(row=0, column=0, sticky="w")
        self.ram_label = ctk.CTkLabel(head, text="", font=font(20, "bold"), text_color=ACCENT)
        self.ram_label.grid(row=0, column=1, sticky="e")

        self.ram_cap = max(2048, min(32768, int(total_ram_mb() * 0.75) // 512 * 512))
        self.ram = ctk.CTkSlider(
            card, from_=1024, to=self.ram_cap, number_of_steps=(self.ram_cap - 1024) // 512,
            command=self._on_ram, progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, fg_color=BORDER, height=18,
        )
        self.ram.set(min(max(self.cfg["ram_mb"], 1024), self.ram_cap))
        self.ram.grid(row=1, column=0, sticky="ew", padx=24)
        self._on_ram(self.ram.get())

        presets = ctk.CTkFrame(card, fg_color="transparent")
        presets.grid(row=2, column=0, sticky="w", padx=24, pady=(14, 0))
        for i, mb in enumerate(m for m in (2048, 4096, 6144, 8192, 12288) if m <= self.ram_cap):
            ctk.CTkButton(
                presets, text=f"{mb // 1024} ГБ", width=64, height=32, corner_radius=10,
                border_width=1, fg_color=FIELD, hover_color=HOVER, border_color=BORDER,
                text_color=TEXT, font=font(13), command=lambda m=mb: self._set_ram(m),
            ).grid(row=0, column=i, padx=(0 if i == 0 else 8, 0))

        ctk.CTkButton(
            presets, text="Подобрать авто", width=130, height=32, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
            font=font(13, "bold"), command=self.auto_ram,
        ).grid(row=0, column=20, padx=(14, 0))

        self._caption(card, "Профиль производительности (аргументы Java)").grid(
            row=3, column=0, sticky="w", padx=24, pady=(20, 6))
        self.perf_seg = self._segmented(card, list(PRESETS), self._on_preset, height=36)
        saved = self.cfg.get("perf_preset", "Баланс")
        self.perf_seg.set(saved if saved in PRESETS else "Баланс")
        self.perf_seg.grid(row=4, column=0, sticky="w", padx=24)
        self.perf_desc = ctk.CTkLabel(card, text=PRESETS[self.perf_seg.get()][0], font=font(12),
                                      text_color=MUTED, anchor="w", justify="left", wraplength=620)
        self.perf_desc.grid(row=5, column=0, sticky="w", padx=24, pady=(8, 22))

        # --- Java ---
        card = self._card(scroll)
        card.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 14))
        card.grid_columnconfigure(0, weight=1)
        self._caption(card, "Java (пусто = найду или скачаю нужную сам)").grid(
            row=0, column=0, sticky="w", padx=24, pady=(22, 6))
        jrow = ctk.CTkFrame(card, fg_color="transparent")
        jrow.grid(row=1, column=0, sticky="ew", padx=24)
        jrow.grid_columnconfigure(0, weight=1)
        self.java_entry = self._entry(jrow, "Авто")
        self.java_entry.insert(0, self.cfg["java_path"])
        self.java_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            jrow, text="Обзор", width=90, height=42, corner_radius=12, border_width=1,
            fg_color=FIELD, hover_color=HOVER, border_color=BORDER, text_color=TEXT,
            font=font(13), command=self.browse_java,
        ).grid(row=0, column=1, padx=(10, 0))

        self._caption(card, "Дополнительные аргументы JVM").grid(
            row=2, column=0, sticky="w", padx=24, pady=(18, 6))
        self.jvm_entry = self._entry(card, "Например: -XX:+UseG1GC")
        self.jvm_entry.insert(0, self.cfg["extra_jvm_args"])
        self.jvm_entry.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 22))

        # --- тема ---
        card = self._card(scroll)
        card.grid(row=2, column=0, sticky="ew", padx=(0, 8), pady=(0, 14))
        self._caption(card, "Цветовая тема").grid(row=0, column=0, sticky="w", padx=24, pady=(22, 10))
        chips = ctk.CTkFrame(card, fg_color="transparent")
        chips.grid(row=1, column=0, sticky="w", padx=24)
        for i, (tname, (ta, tb)) in enumerate(THEMES.items()):
            sel = tname == self.cfg.get("theme", "Мята")
            ctk.CTkButton(chips, text=tname, width=92, height=36, corner_radius=12, fg_color=ta,
                          hover_color=tb, text_color=ACCENT_TEXT, font=font(13, "bold"),
                          border_width=3 if sel else 0, border_color=TEXT,
                          command=lambda n=tname: self._pick_theme(n)).grid(
                row=0, column=i, padx=(0 if i == 0 else 8, 0))
        self.theme_note = ctk.CTkLabel(card, text="", font=font(12), text_color=MUTED, anchor="w")
        self.theme_note.grid(row=2, column=0, sticky="w", padx=24, pady=(10, 0))
        self.restart_btn = ctk.CTkButton(card, text="Перезапустить лаунчер", height=36, corner_radius=12,
                                         fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
                                         font=font(13, "bold"), command=self.restart)
        ctk.CTkFrame(card, height=14, fg_color="transparent").grid(row=4, column=0)

        # --- папка ---
        card = self._card(scroll)
        card.grid(row=3, column=0, sticky="ew", padx=(0, 8))
        card.grid_columnconfigure(0, weight=1)
        self._caption(card, "Файлы игры: сохранения, моды, options.txt").grid(
            row=0, column=0, sticky="w", padx=24, pady=(22, 10))
        frow = ctk.CTkFrame(card, fg_color="transparent")
        frow.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 22))
        ctk.CTkButton(
            frow, text="Открыть папку игры", height=40, corner_radius=12, border_width=1,
            fg_color="transparent", hover_color=HOVER, border_color=BORDER,
            text_color=TEXT, font=font(13), command=self.open_game_folder,
        ).pack(side="left")
        ctk.CTkButton(
            frow, text="Починить файлы игры", height=40, corner_radius=12, border_width=1,
            fg_color="transparent", hover_color=HOVER, border_color=BORDER,
            text_color=TEXT, font=font(13), command=self.repair_files,
        ).pack(side="left", padx=(10, 0))

        # --- обслуживание: бэкапы и перенос ---
        card = self._card(scroll)
        card.grid(row=4, column=0, sticky="ew", padx=(0, 8), pady=(0, 14))
        card.grid_columnconfigure(0, weight=1)
        self._caption(card, "Обслуживание игры").grid(
            row=0, column=0, sticky="w", padx=24, pady=(22, 10))
        self.backup_var = ctk.BooleanVar(value=bool(self.cfg.get("backup_on_launch")))
        ctk.CTkCheckBox(
            card, text="Делать бэкап миров перед каждым запуском (хранятся последние 5)",
            variable=self.backup_var, font=font(13), text_color=TEXT,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=BORDER, corner_radius=6,
        ).grid(row=1, column=0, sticky="w", padx=24)
        mrow = ctk.CTkFrame(card, fg_color="transparent")
        mrow.grid(row=2, column=0, sticky="w", padx=24, pady=(12, 0))
        for text, cmd in (("Сделать бэкап сейчас", self.backup_now),
                          ("Восстановить из бэкапа", self.restore_pick),
                          ("Перенести из .minecraft", self.import_official)):
            ctk.CTkButton(mrow, text=text, height=38, corner_radius=12, border_width=1,
                          fg_color=FIELD, hover_color=HOVER, border_color=BORDER,
                          text_color=TEXT, font=font(13), command=cmd).pack(side="left", padx=(0, 10))

        self._caption(card, "Рендер графики").grid(
            row=3, column=0, sticky="w", padx=24, pady=(18, 6))
        self.vulkan_switch = ctk.CTkSwitch(
            card, text="Включить Vulkan (мод VulkanMod вместо OpenGL)",
            command=self.vulkan_toggle, font=font(13), text_color=TEXT,
            progress_color=ACCENT, button_color=FIELD, button_hover_color=HOVER)
        self.vulkan_switch.grid(row=4, column=0, sticky="w", padx=24)
        self.vulkan_note = ctk.CTkLabel(
            card, font=font(12), text_color=MUTED, anchor="w", justify="left", wraplength=620,
            text="Vulkan на некоторых ПК даёт заметно больше FPS, чем обычный OpenGL, но "
                 "несовместим с шейдерами Iris и бывает нестабилен. Работает на Fabric.")
        self.vulkan_note.grid(row=5, column=0, sticky="w", padx=24, pady=(8, 22))
        self._refresh_vulkan()

        # --- поведение и прочее ---
        card = self._card(scroll)
        card.grid(row=5, column=0, sticky="ew", padx=(0, 8))
        card.grid_columnconfigure(0, weight=1)
        self._caption(card, "Поведение").grid(
            row=0, column=0, sticky="w", padx=24, pady=(22, 10))
        self.close_var = ctk.BooleanVar(value=bool(self.cfg.get("close_on_launch")))
        self.tray_var = ctk.BooleanVar(value=bool(self.cfg.get("minimize_to_tray")))
        self.autoupd_var = ctk.BooleanVar(value=bool(self.cfg.get("auto_update_mods")))
        for r, (var, text) in enumerate((
                (self.close_var, "Закрывать лаунчер, когда игра запустилась"),
                (self.tray_var, "Крестик сворачивает в трей (иконка возле часов)"),
                (self.autoupd_var, "Проверять обновления модов при запуске игры")),
                start=1):
            ctk.CTkCheckBox(
                card, text=text, variable=var, font=font(13), text_color=TEXT,
                fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=BORDER,
                corner_radius=6,
            ).grid(row=r, column=0, sticky="w", padx=24, pady=3)

        self._caption(card, "Discord Rich Presence (необязательно)").grid(
            row=4, column=0, sticky="w", padx=24, pady=(18, 6))
        drow = ctk.CTkFrame(card, fg_color="transparent")
        drow.grid(row=5, column=0, sticky="ew", padx=24)
        drow.grid_columnconfigure(0, weight=1)
        self.discord_entry = self._entry(drow, "Application ID из discord.com/developers")
        self.discord_entry.insert(0, self.cfg.get("discord_app_id", ""))
        self.discord_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(card, text="Пока ты играешь, в Discord показывается «играет в Minecraft <версия>». "
                                "Application ID создаётся бесплатно на discord.com/developers → Applications.",
                     font=font(12), text_color=MUTED, anchor="w", justify="left",
                     wraplength=620).grid(row=6, column=0, sticky="w", padx=24, pady=(8, 0))

        self._caption(card, "Обновление лаунчера").grid(
            row=7, column=0, sticky="w", padx=24, pady=(18, 6))
        self.update_btn = ctk.CTkButton(
            card, text="Обновить лаунчер до последней версии", height=38, corner_radius=12,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
            font=font(13, "bold"), command=self.self_update_click)
        self.update_btn.grid(row=8, column=0, sticky="w", padx=24, pady=(0, 6))
        self.update_note = ctk.CTkLabel(card, text="", font=font(12), text_color=MUTED,
                                        anchor="w", justify="left", wraplength=620)
        self.update_note.grid(row=9, column=0, sticky="w", padx=24, pady=(0, 6))
        ctk.CTkButton(
            card, text="Сообщить о баге (создать вопрос на GitHub)", height=34, corner_radius=12,
            border_width=1, fg_color="transparent", hover_color=HOVER, border_color=BORDER,
            text_color=MUTED, font=font(12), command=self.report_bug,
        ).grid(row=10, column=0, sticky="w", padx=24, pady=(0, 18))
        self.after(3000, self._refresh_update_note)
        return page

    # --- обслуживание ---
    def _maintenance_worker(self, fn, done_msg):
        def run():
            try:
                res = fn(self._game_dir(), status=lambda t: self.q.put(("status", t)))
                self.q.put(("status", res or done_msg))
            except Exception as e:
                self.q.put(("status", f"Ошибка: {e}", True))
        threading.Thread(target=run, daemon=True).start()

    def backup_now(self):
        self._set_status("Бэкап миров…")
        self._maintenance_worker(
            lambda gd, status: backup_saves(gd, status) and "Бэкап готов (data/backups)" or "Сохранений нет — бэкапить нечего",
            "Бэкап готов")

    def restore_pick(self):
        inst = BACKUPS_DIR / self._game_dir().name
        if not inst.is_dir() or not list(inst.glob("*.zip")):
            self._set_status("Бэкапов для этой папки игры ещё нет", ERROR)
            return
        path = filedialog.askopenfilename(title="Выбери бэкап", initialdir=str(inst),
                                          filetypes=[("Бэкапы", "*.zip")])
        if not path:
            return

        def run():
            try:
                n = restore_backup(path, self._game_dir())
                self.q.put(("status", f"Восстановлено файлов: {n} (текущие миры не удалялись)"))
            except Exception as e:
                self.q.put(("status", f"Ошибка восстановления: {e}", True))
        threading.Thread(target=run, daemon=True).start()

    def import_official(self):
        self._set_status("Перенос из .minecraft…")
        self._maintenance_worker(import_from_official, "Перенос завершён")

    # --- рендер Vulkan ---
    def _vulkan_pid(self):
        mods = list_installed(self._game_dir() / "mods")
        for pid, info in mods.items():
            if info["title"].lower().replace(" ", "") == "vulkanmod" or \
                    "vulkanmod" in info["filename"].lower():
                return pid
        return None

    def _refresh_vulkan(self):
        if not hasattr(self, "vulkan_switch"):
            return
        if self.cfg["loader"] != "Fabric":
            self.vulkan_switch.configure(state="disabled",
                                         text="Vulkan доступен только на Fabric")
            self.vulkan_switch.deselect()
            return
        self.vulkan_switch.configure(state="normal",
                                     text="Включить Vulkan (мод VulkanMod вместо OpenGL)")
        if self._vulkan_pid():
            self.vulkan_switch.select()
        else:
            self.vulkan_switch.deselect()

    def vulkan_toggle(self):
        if self.cfg["loader"] != "Fabric" or not self.cfg["last_version"]:
            self._refresh_vulkan()
            self._set_status("VulkanMod работает на Fabric — переключи загрузчик на странице «Играть»", ERROR)
            return
        pid = self._vulkan_pid()
        if pid:
            remove_mod(pid, self._game_dir() / "mods")
            self._set_status("VulkanMod удалён, игра снова на OpenGL")
        else:
            self._enqueue_mod("vulkanmod", "VulkanMod", self.cfg["last_version"],
                              self._game_dir() / "mods", "mod")
            self._set_status("Устанавливаю VulkanMod… после установки игра будет рендерить через Vulkan")
        self.after(2000, self._refresh_vulkan)

    # --- починка файлов игры ---
    def repair_files(self):
        if not self.cfg["last_version"]:
            self._set_status("Сначала выбери версию на странице «Играть»", ERROR)
            return
        self._set_status("Проверяю файлы игры (это может занять пару минут)…")
        b = self._build()
        threading.Thread(target=self._repair_worker,
                         args=(self.cfg["last_version"], self.cfg["loader"],
                               b.get("forge_version", "") if b else ""),
                         daemon=True).start()

    def _repair_worker(self, version, loader, forge_version):
        q = self.q
        try:
            launch_id = version
            if loader == "Fabric":
                launch_id = fabric_id(version)
            elif loader == "Quilt":
                launch_id = quilt_id(version)
            elif loader == "Forge":
                launch_id = find_forge_id(version, forge_version or None) or version
            elif loader == "NeoForge":
                launch_id = find_neoforge_id(version) or version

            def progress(done, total):
                q.put(("progress", done / total if total else 1,
                       f"Проверка файлов: {done} / {total}"))

            install_version(launch_id, progress)  # битые и отсутствующие файлы перекачаются
            data = load_version(launch_id)
            shutil.rmtree(NATIVES_DIR / data["id"], ignore_errors=True)
            extract_natives(data)
            q.put(("progress_reset",))
            q.put(("status", "Файлы игры проверены, повреждённые перекачаны"))
        except Exception as e:
            q.put(("progress_reset",))
            q.put(("status", f"Не удалось проверить файлы: {friendly_error(e)}", True))

    def report_bug(self):
        webbrowser.open(f"https://github.com/{REPO}/issues/new")

    def _auto_mod_check(self, cfg):
        """Молча проверяет обновления модов, пока игра запускается."""
        try:
            if cfg.get("loader") == "Vanilla":
                return
            dest = Path(cfg["game_dir"]) / "mods"
            if not list_installed(dest):
                return
            loader = {"Fabric": "fabric", "Forge": "forge", "Quilt": "quilt",
                      "NeoForge": "neoforge"}.get(cfg.get("loader"), "")
            res = analyze(dest, cfg["last_version"], loader, "mod")
            if res["updates"]:
                res["key"] = (str(dest), cfg["last_version"], "mod", loader, ())
                self.q.put(("mods_analysis", res))
                self.q.put(("status", f"Моды: доступно обновлений: {len(res['updates'])} "
                                      f"— страница «Моды → Установленные»"))
        except Exception:
            pass  # проверка фоновая: нет сети — не страшно

    def _on_preset(self, name):
        self.perf_desc.configure(text=PRESETS[name][0])
        self.cfg["perf_preset"] = name
        save_config(self.cfg)

    def auto_ram(self):
        self._set_ram(min(recommended_ram(total_ram_mb()), self.ram_cap))

    def _pick_theme(self, name):
        self.cfg["theme"] = name
        save_config(self.cfg)
        self.theme_note.configure(text=f"Тема «{name}» применится после перезапуска")
        self.restart_btn.grid(row=3, column=0, sticky="w", padx=24, pady=(10, 0))

    def restart(self):
        self.save_all()
        args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable] + sys.argv
        subprocess.Popen(args)
        self._really_close()

    def _on_ram(self, value):
        self.ram_label.configure(text=f"{value / 1024:.1f} ГБ")

    def _set_ram(self, mb):
        self.ram.set(mb)
        self._on_ram(mb)

    def browse_java(self):
        path = filedialog.askopenfilename(
            title="Выбери java.exe",
            filetypes=[("Java", "java.exe java"), ("Все файлы", "*.*")],
        )
        if path:
            self.java_entry.delete(0, "end")
            self.java_entry.insert(0, path)

    def open_game_folder(self):
        open_folder(self._game_dir())

    # ---------- конфиг ----------
    def save_all(self):
        c = self.cfg
        c["ram_mb"] = int(self.ram.get())
        c["java_path"] = self.java_entry.get().strip()
        c["extra_jvm_args"] = self.jvm_entry.get().strip()
        c["perf_preset"] = self.perf_seg.get()
        if hasattr(self, "backup_var"):
            c["backup_on_launch"] = bool(self.backup_var.get())
        if hasattr(self, "close_var"):
            c["close_on_launch"] = bool(self.close_var.get())
            c["minimize_to_tray"] = bool(self.tray_var.get())
            c["auto_update_mods"] = bool(self.autoupd_var.get())
        if hasattr(self, "discord_entry"):
            c["discord_app_id"] = self.discord_entry.get().strip()
        save_config(c)

    def on_close(self):
        # крестик: если включён трей — прячем окно, иконка в трее остаётся
        if self.cfg.get("minimize_to_tray") and not self._quitting and self._make_tray():
            self.withdraw()
            return
        self._really_close()

    def _really_close(self):
        self._quitting = True
        try:
            if self._tray is not None:
                self._tray.stop()
        except Exception:
            pass
        self._tray = None
        try:
            self.save_all()
        finally:
            self.icon_pool.shutdown(wait=False, cancel_futures=True)
            self.destroy()

    # ---------- трей ----------
    def _make_tray(self):
        """Создаёт иконку в трее. True — трей работает."""
        if self._tray is not None:
            return True
        try:
            import pystray
            menu = pystray.Menu(
                pystray.MenuItem("Открыть", self._tray_open, default=True),
                pystray.MenuItem("Выход", self._tray_quit),
            )
            self._tray = pystray.Icon(LAUNCHER_NAME, visuals.logo(64, ACCENT, ACCENT2),
                                      LAUNCHER_NAME, menu)
            threading.Thread(target=self._tray.run, daemon=True).start()
            return True
        except Exception:
            self._tray = None
            return False

    def _tray_open(self, icon=None, item=None):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _tray_quit(self, icon=None, item=None):
        self.after(0, self._really_close)

    # ---------- обновления лаунчера ----------
    def _check_update(self):
        """Читает сайт (data.js): версия для проверки обновлений + «Что нового»."""
        try:
            text = get_bytes(SITE_URL.rstrip("/") + "/data.js", timeout=8).decode("utf-8", "replace")
            m = re.search(r'version:\s*"([\d.]+)"', text)
            if m:
                self.q.put(("update", m.group(1)))
            try:
                site = parse_site_data(text)
                self.q.put(("whatsnew", site.get("changelog", [])))
                self.q.put(("site_promos", site.get("promos", {})))
            except Exception:
                pass
        except Exception:
            pass

    def _refresh_update_note(self):
        """Текст возле кнопки «Обновить»: что лежит в GitHub Releases."""
        def run():
            try:
                rel = updater.latest_release()
                self.q.put(("update_info", rel))
            except Exception:
                self.q.put(("update_info", None))
        threading.Thread(target=run, daemon=True).start()

    def self_update_click(self):
        def run():
            q = self.q
            try:
                rel = updater.latest_release()
                if not updater.is_newer(rel["tag"]):
                    q.put(("status", f"У тебя уже последняя версия (v{LAUNCHER_VERSION})"))
                    return
                if not rel["setup_url"]:
                    q.put(("status", "В релизе нет установщика — открываю страницу в браузере"))
                    webbrowser.open(rel["page"])
                    return
                updater.download_and_run(rel["setup_url"],
                                         status=lambda t: q.put(("status", t)))
                q.put(("status", "Установщик запущен — лаунчер закроется, обновись и заходи снова", ))
                q.put(("close_app",))
            except Exception as e:
                q.put(("status", f"Не удалось обновить: {friendly_error(e)}", True))
        threading.Thread(target=run, daemon=True).start()

    # ---------- список версий ----------
    def _load_versions(self):
        try:
            self.q.put(("versions", get_all_versions_cached()))
        except Exception:
            self.q.put(("versions", None))

    # ---------- запуск игры ----------
    def _set_status(self, text, color=MUTED):
        self.status.configure(text=text, text_color=color)

    def _set_busy(self, busy, text="Играть"):
        self.busy = busy
        self.play_btn.configure(state="disabled" if busy else "normal", text=text)
        self._apply_play_image()

    def on_play(self, join=None):
        if self.busy:
            return
        self.save_all()
        name = self.cfg["username"]
        if not re.fullmatch(NICK_RE, name):
            self._set_status("Ник: 3–16 символов, латиница, цифры или _ (поменяй в аккаунте)", ERROR)
            return
        version = self.cfg["last_version"]
        if not version:
            self._set_status("Выбери версию", ERROR)
            return

        c = dict(self.cfg)
        c["game_dir"] = str(self._game_dir())
        c["join_server"] = join or ""
        c["extra_jvm_args"] = " ".join(x for x in (
            preset_args(self.cfg.get("perf_preset", "Баланс"), self.cfg["ram_mb"]),
            self.cfg.get("extra_jvm_args", "")) if x)
        b = self._build()
        c["forge_version"] = b.get("forge_version", "") if b else ""

        acc = dict(self.account())
        c["auth_uuid"] = acc.get("uuid") or ""
        c["auth_access_token"] = acc.get("access_token") or ""

        self._set_busy(True, "Подготовка…")
        self.progress.set(0)
        self._set_status("Проверка файлов…")
        threading.Thread(
            target=self._play_worker,
            args=(version, self.cfg["loader"], c, acc), daemon=True,
        ).start()

    def play_on_server(self, address):
        self.show_page("play")
        self.on_play(join=address)

    def _play_worker(self, version, loader, cfg, acc):
        q = self.q
        tail = []
        log_file = LogWriter().start()
        try:
            def files_progress(done, total):
                q.put(("progress", done / total if total else 1,
                       f"Скачивание файлов: {done} / {total}"))

            def java_progress(done, total):
                if total:
                    q.put(("progress", done / total, f"Скачивание Java: {done * 100 // total}%"))
                else:
                    q.put(("progress", 0, f"Скачивание Java: {done // (1024 * 1024)} МБ"))

            if acc.get("type") == "msa":
                q.put(("status", "Проверка входа Microsoft…"))
                ensure_msa_token(acc)
                q.put(("account_token", acc))

            launch_id = version
            if loader == "Fabric":
                q.put(("status", "Подготовка Fabric…"))
                launch_id = install_fabric(version)
            elif loader == "Quilt":
                q.put(("status", "Подготовка Quilt…"))
                launch_id = install_quilt(version)
            elif loader == "Forge":
                q.put(("status", "Загрузка Minecraft…"))
                install_version(version, files_progress)
                q.put(("status", "Проверка Java…"))
                java0 = ensure_java(required_java(version), cfg["java_path"], java_progress)
                launch_id = ensure_forge(version, java0, cfg.get("forge_version") or None,
                                         status=lambda t: q.put(("status", t)))
            elif loader == "NeoForge":
                q.put(("status", "Загрузка Minecraft…"))
                install_version(version, files_progress)
                q.put(("status", "Проверка Java…"))
                java0 = ensure_java(required_java(version), cfg["java_path"], java_progress)
                launch_id = ensure_neoforge(version, java0, cfg.get("forge_version") or None,
                                            status=lambda t: q.put(("status", t)))

            q.put(("status", "Загрузка версии…"))
            install_version(launch_id, files_progress)

            q.put(("status", "Проверка Java…"))
            java = ensure_java(required_java(launch_id), cfg["java_path"], java_progress)

            apply_local_skin(acc, Path(cfg["game_dir"]))
            if cfg.get("backup_on_launch"):
                backup_saves(cfg["game_dir"], status=lambda t: q.put(("status", t)))
            q.put(("status", "Запуск игры…"))
            proc = launch(launch_id, cfg, java=java)
            q.put(("log_clear",))
            q.put(("running",))
            rpc.start_game(cfg.get("discord_app_id", ""), version, loader)
            q.put(("launch_minimize",))
            if cfg.get("auto_update_mods"):
                threading.Thread(target=self._auto_mod_check, args=(dict(cfg),),
                                 daemon=True).start()
            started = time.time()
            for line in proc.stdout:
                tail.append(line)
                if len(tail) > 300:
                    del tail[:100]
                log_file.write(line)
                q.put(("log", line))
            code = proc.wait()
            q.put(("played", f"{version} · {loader}", acc["name"], time.time() - started))
            if code == 0:
                q.put(("finished", "Игра закрыта", False))
            else:
                q.put(("log_done", crash_hint("".join(tail))))
                q.put(("finished", f"Игра завершилась с ошибкой (код {code}). "
                                   f"Причина и подсказка — на странице «Лог».", True))
        except Exception as e:
            traceback.print_exc()
            q.put(("finished", f"Ошибка: {friendly_error(e)}", True))
        finally:
            rpc.stop()
            log_file.close()

    # ---------- сборки ----------
    def add_build(self, build):
        self.cfg["builds"].append(build)
        cos.bump_counter(self.cfg, "builds")
        self.select_build(build["id"])

    def select_build(self, bid):
        self.cfg["active_build"] = bid
        b = self._build()
        if b:
            self.cfg["last_version"] = b["version"]
            self.cfg["loader"] = b["loader"]
            self.version_btn.configure(text=self._version_text())
            self.loader.set(b["loader"])
        save_config(self.cfg)
        self._refresh_tiles()
        self._refresh_banner()

    def remove_build(self, bid):
        self.cfg["builds"] = [b for b in self.cfg["builds"] if b["id"] != bid]
        if self.cfg["active_build"] == bid:
            self.cfg["active_build"] = ""
        save_config(self.cfg)
        self._refresh_tiles()

    def _modpack_worker(self, project_id):
        q = self.q
        bid = uuid.uuid4().hex[:8]
        try:
            info = install_modpack(
                project_id, INSTANCES_DIR / f"build-{bid}",
                status=lambda t: q.put(("builds_status", t)),
                progress=lambda d, t: q.put(("builds_status", f"Файлы сборки: {d} / {t}")))
            q.put(("build_done", {"id": bid, "name": info["title"], "version": info["version"],
                                  "loader": info["loader"], "forge_version": info["forge_version"],
                                  "icon_url": info["icon_url"]}, ""))
        except Exception as e:
            traceback.print_exc()
            q.put(("build_done", None, str(e)))

    # ---------- сборки из файла и экспорт ----------
    def pick_pack_file(self):
        paths = filedialog.askopenfilenames(
            title="Выбери .mrpack", filetypes=[("Сборки Modrinth", "*.mrpack"), ("Все файлы", "*.*")])
        if paths:
            self.install_pack_files(list(paths))

    def install_pack_files(self, paths):
        self.show_page("builds")
        self.pages["builds"].tabs.set("Мои сборки")
        threading.Thread(target=self._pack_files_worker, args=(list(paths),), daemon=True).start()

    def _pack_files_worker(self, paths):
        q = self.q
        for path in paths:
            bid = uuid.uuid4().hex[:8]
            try:
                name = Path(path).stem
                q.put(("builds_status", f"Установка «{name}»…"))
                info = install_pack_zip(
                    Path(path), INSTANCES_DIR / f"build-{bid}", title=name,
                    status=lambda t: q.put(("builds_status", t)),
                    progress=lambda d, t: q.put(("builds_status", f"Файлы сборки: {d} / {t}")))
                q.put(("build_done", {"id": bid, "name": info["title"], "version": info["version"],
                                      "loader": info["loader"], "forge_version": info["forge_version"],
                                      "icon_url": info["icon_url"]}, ""))
            except Exception as e:
                traceback.print_exc()
                q.put(("build_done", None, str(e)))

    def export_build_dialog(self, bid):
        b = next((x for x in self.cfg["builds"] if x["id"] == bid), None)
        if not b:
            return
        safe = re.sub(r'[^\w\-]+', "_", b["name"]).strip("_") or "build"
        dest = filedialog.asksaveasfilename(
            title="Куда сохранить .mrpack", defaultextension=".mrpack",
            initialfile=f"{safe}.mrpack", filetypes=[("Сборки Modrinth", "*.mrpack")])
        if not dest:
            return

        def run():
            q = self.q
            try:
                q.put(("builds_status", "Собираю .mrpack…"))
                loader_version = detect_loader_version(b["loader"], b["version"],
                                                       b.get("forge_version", ""))
                export_modpack(INSTANCES_DIR / f"build-{bid}", b["name"], b["version"],
                               b["loader"], loader_version, dest)
                q.put(("export_done", True, f"Готово: сборка сохранена в {dest}"))
            except Exception as e:
                traceback.print_exc()
                q.put(("export_done", False, f"Ошибка экспорта: {e}"))
        threading.Thread(target=run, daemon=True).start()

    # ---------- сообщения из потоков ----------
    def _flush_log(self, lines):
        self.pages["log"].append("".join(lines))

    def _poll(self):
        pending, logbuf = None, []
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "progress":
                    pending = msg  # из пачки прогрессов показываем только последний
                elif msg[0] == "log":
                    logbuf.append(msg[1])
                else:
                    if logbuf:
                        self._flush_log(logbuf)
                        logbuf = []
                    if pending:
                        self._handle(pending)
                        pending = None
                    self._handle(msg)
        except queue.Empty:
            pass
        if logbuf:
            self._flush_log(logbuf)
        if pending:
            self._handle(pending)
        self.after(50, self._poll)

    def _handle(self, msg):
        kind = msg[0]
        if kind == "status":
            self._set_status(msg[1])
        elif kind == "progress":
            self.progress.set(max(0, min(1, msg[1])))
            self._set_status(msg[2])
        elif kind == "running":
            self.progress.set(0)
            self._set_busy(True, "Игра запущена")
            self._set_status("Игра запущена. Приятной игры!", ACCENT)
            self.cfg["stats"]["launches"] = self.cfg["stats"].get("launches", 0) + 1
            cos.bump_counter(self.cfg, "launches")
            save_config(self.cfg)
        elif kind == "finished":
            self.progress.set(0)
            self._set_busy(False)
            self._set_status(msg[1], ERROR if msg[2] else MUTED)
        elif kind == "played":
            st = self.cfg["stats"]
            for bucket, name in (("by_version", msg[1]), ("by_account", msg[2])):
                st.setdefault(bucket, {})
                st[bucket][name] = st[bucket].get(name, 0) + msg[3]
            secs = int(msg[3])
            lines = []
            cos.add_playtime(self.cfg, secs)
            earned = cos.playtime_reward(secs)
            if earned:
                cos.add_crystals(self.cfg, earned)
                lines.append(f"+{earned} 💎 за игру")
            for d in cos.hourly_rolls(self.cfg, secs):
                if d[0] == "crystals":
                    lines.append(f"+{d[1]} 💎 часовой дроп")
            save_config(self.cfg)
            if lines:
                self.status.configure(text="  ·  ".join(lines), text_color=ACCENT)
            self._refresh_lobby()
        elif kind == "update":
            self.available_version = msg[1]
            parse = lambda v: tuple(int(x) for x in v.split("."))
            if parse(msg[1]) > parse(LAUNCHER_VERSION):
                self._set_status(f"Доступна новая версия v{msg[1]} — обновись в Настройках "
                                 f"или нажми сюда, чтобы открыть сайт", ACCENT)
                self.status.bind("<Button-1>", lambda e: webbrowser.open(SITE_URL))
        elif kind == "update_info":
            rel = msg[1]
            if not hasattr(self, "update_note"):
                return
            if rel is None:
                self.update_note.configure(
                    text=f"У тебя v{LAUNCHER_VERSION}. GitHub недоступен — проверю позже.")
            elif updater.is_newer(rel["tag"]):
                how = "кнопка выше обновит сама" if rel["setup_url"] else "скачай вручную со страницы релиза"
                self.update_note.configure(
                    text=f"Доступна v{rel['tag']} ({how}).", text_color=ACCENT)
                self.update_btn.configure(text=f"Обновить до v{rel['tag']}")
            else:
                self.update_note.configure(
                    text=f"У тебя последняя версия (v{LAUNCHER_VERSION}).")
        elif kind == "msa_code":
            if self.acc_dialog is not None and self.acc_dialog.winfo_exists():
                self.acc_dialog.on_msa_code(msg[1], msg[2])
        elif kind == "msa_done":
            if self.acc_dialog is not None and self.acc_dialog.winfo_exists():
                self.acc_dialog.on_msa_done(msg[1], msg[2])
        elif kind == "acc_status":
            if self.acc_dialog is not None and self.acc_dialog.winfo_exists():
                self.acc_dialog.set_status(msg[1], msg[2])
        elif kind == "acc_skin_url":
            if self.acc_dialog is not None and self.acc_dialog.winfo_exists():
                self.acc_dialog.on_nick_skin(msg[1])
        elif kind == "account_token":
            acc = msg[1]
            for a in self.cfg["accounts"]:
                if a["id"] == acc["id"]:
                    a.update({k: acc[k] for k in ("access_token", "expires_at", "refresh_token",
                                                  "uuid", "name") if k in acc})
                    break
            save_config(self.cfg)
            self._update_profile()
        elif kind == "site_promos":
            self.site_promos = msg[1] or {}
        elif kind == "close_app":
            self.on_close()
        elif kind == "launch_minimize":
            if self.cfg.get("close_on_launch"):
                self._really_close()
            else:
                self.iconify()
        elif kind == "whatsnew":
            if self.cfg.get("whatsnew_seen") != LAUNCHER_VERSION:
                self.cfg["whatsnew_seen"] = LAUNCHER_VERSION
                save_config(self.cfg)
                log = msg[1]
                entry = next((e for e in log if str(e.get("v")) == LAUNCHER_VERSION),
                             log[0] if log else None)
                if entry and entry.get("items"):
                    try:
                        WhatsNewDialog(self, entry)
                    except Exception:
                        pass
        elif kind == "worlds_done":
            if self._copy_dlg is not None:
                try:
                    self._copy_dlg.destroy()
                except Exception:
                    pass
                self._copy_dlg = None
            if msg[1]:
                self._set_status(msg[1])
                self.pages["worlds"].render()
            else:
                self._set_status(msg[2], ERROR)
        elif kind == "progress_reset":
            self.progress.set(0)
            self._set_status("")
        elif kind == "export_done":
            self.pages["builds"].finished(msg[1], msg[2])
        elif kind == "log_clear":
            self.pages["log"].clear()
        elif kind == "log_done":
            self.pages["log"].show_hint(msg[1])
        elif kind == "versions":
            if msg[1] is None:
                self._set_status("Нет сети: доступны только установленные версии")
            else:
                self.all_versions = msg[1]
                if not self.cfg["last_version"]:
                    releases = self._version_lists()["Релизы"]
                    if releases:
                        self._set_version(releases[0])
        elif kind == "mods_status":
            self._set_mod_status(msg[1], msg[2])
            if self.acc_dialog is not None and self.acc_dialog.winfo_exists():
                self.acc_dialog.set_status(msg[1], msg[2])
            if msg[2] and self.mod_loading:
                self.mod_loading = False
                self._render_mods()
        elif kind == "mods_hits":
            if msg[2] == self._search_key():
                self.mod_hits, self.mod_hits_key = msg[1], msg[2]
            self.mod_loading = False
            self._set_mod_status("")
            self._render_mods()
        elif kind == "mods_analysis":
            self.analysis = msg[1]
        elif kind == "analysis_clear":
            self.analysis = None
        elif kind == "mods_idle":
            self.mod_busy = False
            if self.acc_dialog is not None and self.acc_dialog.winfo_exists():
                self.acc_dialog.rebuild()
            self._render_mods()
            self._refresh_tiles()
        elif kind == "mods_refresh":
            if self.mod_tabs.get() == "Установленные":
                self._render_mods()
        elif kind == "icon":
            self._on_icon(msg[1], msg[2])
        elif kind == "server":
            self.pages["servers"].on_result(msg[1], msg[2])
        elif kind == "thumb":
            self.pages["shots"].on_thumb(msg[1], msg[2])
        elif kind == "builds_hits":
            self.pages["builds"].on_hits(msg[1])
        elif kind == "builds_status":
            self.pages["builds"].set_status(msg[1])
        elif kind == "build_done":
            if msg[1]:
                self.add_build(msg[1])
                self.pages["builds"].finished(
                    True, f"Готово: «{msg[1]['name']}» установлена и выбрана. Нажми «Играть» — "
                          f"Minecraft и загрузчик докачаются сами.")
            else:
                self.pages["builds"].finished(False, f"Ошибка: {msg[2]}")


def run():
    ctk.set_appearance_mode("dark")
    apply_theme(load_config().get("theme", "Мята"))
    App().mainloop()
