import copy
import json
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):  # запущен как .exe: данные лежат в профиле пользователя
    ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "YroveeLauncher"
else:
    ROOT = Path(__file__).resolve().parent
SITE_URL = "https://yroveeteam.github.io/YroveeTeamSite/"  # адрес сайта на GitHub Pages
REPO = "YroveeTeam/YroveeTeamSite"  # owner/repo на GitHub: для релизов и самообновления
DATA = ROOT / "data"
VERSIONS_DIR = DATA / "versions"
LIBRARIES_DIR = DATA / "libraries"
ASSETS_DIR = DATA / "assets"
NATIVES_DIR = DATA / "natives"
INSTANCES_DIR = DATA / "instances"
RUNTIME_DIR = DATA / "runtime"  # сюда лаунчер сам ставит Java
SKINS_DIR = DATA / "skins"  # скины аккаунтов
CACHE_DIR = DATA / "cache"  # кэш иконок модов
LOGS_DIR = DATA / "logs"  # текстовые логи запусков игры
BACKUPS_DIR = DATA / "backups"  # бэкапы миров по инстансам
CONFIG_FILE = DATA / "config.json"

LAUNCHER_NAME = "YroveeLauncher"
LAUNCHER_VERSION = "0.13"

# Клиентское приложение Azure для входа через Microsoft.
# Создай бесплатно на portal.azure.com (App registrations → Accounts in any
# organizational directory and personal Microsoft accounts, платформа Mobile
# and desktop applications с redirect URI http://localhost) и вставь
# Application (client) ID сюда. Пусто = кнопка входа через Microsoft скрыта.
MSA_CLIENT_ID = ""

DEFAULT_CONFIG = {
    "username": "Player",
    "ram_mb": 4096,
    "java_path": "",
    "last_version": "",
    "loader": "Vanilla",  # Vanilla, Fabric, Forge, Quilt или NeoForge
    "extra_jvm_args": "",
    "accounts": [],  # [{id, name, skin, type, uuid, refresh_token}] (тип: offline|msa)
    "active_account": "",
    "theme": "Мята",
    "perf_preset": "Баланс",
    "builds": [],  # [{id, name, version, loader, forge_version, icon_url}]
    "active_build": "",
    "servers": [],  # [{name, address}]
    "stats": {"launches": 0, "by_version": {}, "by_account": {}},
    "backup_on_launch": False,
    "discord_app_id": "",  # Application ID из Discord Developer Portal для Rich Presence
    "cosmetics_enabled": True,  # косметика, кристаллы и 3D-персонаж (эксперимент)
    "theme_mode": "dark",       # dark | light
    "theme": "Мята",            # имя акцента или "Свой цвет"
    "custom_color": "#7c5cff",  # цвет для «Свой цвет»
    "lang": "ru",               # ru | en
    "mirror": "auto",           # auto | official | bmclapi | своя ссылка
    "fast_start": False,        # не перепроверять файлы перед запуском
    "shared_options": False,    # один options.txt на все версии
    "window_geometry": "",      # размер и позиция окна
    "close_on_launch": False,   # закрывать лаунчер, когда игра запустилась
    "minimize_to_tray": False,  # крестик сворачивает в трей вместо выхода
    "auto_update_mods": False,  # молча проверять обновления модов при запуске
    "whatsnew_seen": "",        # какая версия уже показывала окно «Что нового»
    # --- косметика и кристаллы (всё бесплатно, без доната) ---
    "crystals": 50,             # стартовый баланс
    "cosmetics": {"owned": [], "equipped": {}},
    "promo_used": [],           # использованные промокоды из TG-канала
    "last_daily": "",           # последний ежедневный бонус
    "playtime_hours": 0,        # всего часов в игре (уровень, задания)
    "drop_hours": 0,            # сколько часов уже учтено часовыми дропами
    "quests": {},               # прогресс заданий (launches/mods/builds/chests)
    "quests_claimed": [],
    "daily_play": {},           # время игры за сегодня (сундуки за игру)
    "daily_chests": {},         # сколько сундуков за игру забрано сегодня
    "play_history": {},         # секунды игры по дням (график статистики)
    "season": {},               # сезонный пропуск: старт и полученные дни
    "advent": {},               # адвент-календарь: год и открытые дверцы
}


def instance_dir(version_id):
    """Папка игры (saves, mods, options.txt...) у каждой версии своя."""
    return INSTANCES_DIR / version_id


def load_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return cfg


def save_config(cfg):
    DATA.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
