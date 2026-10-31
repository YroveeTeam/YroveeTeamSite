"""Обслуживание игры: бэкапы миров и перенос данных из официального .minecraft."""
import os
import shutil
import time
import zipfile
from pathlib import Path

from config import BACKUPS_DIR

KEEP = 5  # сколько последних бэкапов хранить на инстанс


def backup_saves(game_dir, status=None):
    """Запаковывает saves текущей игры в data/backups/<папка игры>/<дата>.zip.
    Возвращает путь к архиву или None, если сохранений нет."""
    say = status or (lambda t: None)
    game_dir = Path(game_dir)
    saves = game_dir / "saves"
    if not saves.is_dir() or not any(saves.iterdir()):
        return None

    dest_dir = BACKUPS_DIR / game_dir.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H-%M")
    dest = dest_dir / f"{stamp}.zip"
    say("Создаю бэкап миров…")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in saves.rglob("*"):
            if f.is_file():
                z.write(f, f"saved/{f.relative_to(saves)}")
    olds = sorted(dest_dir.glob("*.zip"))
    for old in olds[:-KEEP]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def restore_backup(zip_path, game_dir):
    """Возвращает миры из бэкапа (папки с конфликтами переименуются в <мир>_restore)."""
    saves = Path(game_dir) / "saves"
    saves.mkdir(parents=True, exist_ok=True)
    restored = 0
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.startswith("saved/") or name.endswith("/"):
                continue
            rel = name[len("saved/"):]
            dest = saves / rel
            if dest.exists():  # не затираем текущий мир
                dest = dest.with_name(dest.stem + "_restore" + dest.suffix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(name))
            restored += 1
    return restored


def import_from_official(game_dir, status=None):
    """Переносит сохранения, servers.dat и options.txt из %APPDATA%\\.minecraft.
    Существующие файлы не трогает. Возвращает краткий отчёт."""
    say = status or (lambda t: None)
    src_root = Path(os.environ.get("APPDATA", str(Path.home()))) / ".minecraft"
    if not src_root.is_dir():
        raise RuntimeError("Папка .minecraft не найдена — официальный лаунчер не установлен?")

    game_dir = Path(game_dir)
    game_dir.mkdir(parents=True, exist_ok=True)
    copied = []

    def copy_tree(src, dst):
        n = 0
        for f in src.rglob("*"):
            if not f.is_file():
                continue
            target = dst / f.relative_to(src)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
            n += 1
        return n

    for name in ("saves", "screenshots", "resourcepacks", "shaderpacks"):
        src = src_root / name
        if src.is_dir():
            say(f"Переношу {name}…")
            n = copy_tree(src, game_dir / name)
            if n:
                copied.append(f"{name}: {n}")

    for name in ("servers.dat", "servers.dat_old"):
        src = src_root / name
        if src.is_file() and not (game_dir / name).exists():
            shutil.copyfile(src, game_dir / name)
            copied.append(name)

    src = src_root / "options.txt"
    if src.is_file() and not (game_dir / "options.txt").exists():
        shutil.copyfile(src, game_dir / "options.txt")
        copied.append("options.txt")

    if not copied:
        return "В .minecraft не нашлось ничего нового — всё уже перенесено."
    return "Перенесено: " + ", ".join(copied) + "."
