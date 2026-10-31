"""Установка Forge через официальный установщик (--installClient в папку data)."""
import json
import subprocess
import sys

from config import CACHE_DIR, DATA, VERSIONS_DIR
from net import download_file, get_json

PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"


def forge_promos():
    return get_json(PROMOS)["promos"]


def pick_forge_version(mc):
    promos = forge_promos()
    return promos.get(f"{mc}-recommended") or promos.get(f"{mc}-latest")


def find_forge_id(mc, forge_ver=None):
    """Ищет уже установленную версию Forge в data/versions."""
    if not VERSIONS_DIR.exists():
        return None
    best = None
    for d in VERSIONS_DIR.iterdir():
        name = d.name
        if not d.is_dir() or "forge" not in name.lower() or mc not in name:
            continue
        if forge_ver and forge_ver not in name:
            continue
        if (d / f"{name}.json").exists():
            if best is None or d.stat().st_mtime > best[0]:
                best = (d.stat().st_mtime, name)
    return best[1] if best else None


def ensure_forge(mc, java, forge_ver=None, status=None):
    """Возвращает id версии Forge, при необходимости скачивая и запуская установщик.
    Ваниль mc должна быть уже скачана (install_version)."""
    say = status or (lambda t: None)
    forge_ver = forge_ver or pick_forge_version(mc)
    if not forge_ver:
        raise RuntimeError(f"Для Minecraft {mc} нет Forge")
    existing = find_forge_id(mc, forge_ver)
    if existing:
        return existing

    full = f"{mc}-{forge_ver}"
    jar = CACHE_DIR / "forge" / f"forge-{full}-installer.jar"
    say(f"Скачивание Forge {forge_ver}…")
    download_file(f"{MAVEN}/{full}/forge-{full}-installer.jar", jar)

    DATA.mkdir(parents=True, exist_ok=True)
    profiles = DATA / "launcher_profiles.json"  # установщик без него отказывается работать
    if not profiles.exists():
        profiles.write_text(json.dumps({"profiles": {}, "version": 3}), encoding="utf-8")

    before = {d.name for d in VERSIONS_DIR.iterdir()} if VERSIONS_DIR.exists() else set()
    say("Установка Forge (до пары минут)…")
    kwargs = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}
    result = subprocess.run(
        [str(java), "-jar", str(jar), "--installClient", str(DATA)],
        cwd=str(DATA), capture_output=True, text=True, errors="replace",
        timeout=1800, **kwargs,
    )
    fid = find_forge_id(mc, forge_ver)
    if not fid:
        after = {d.name for d in VERSIONS_DIR.iterdir()} if VERSIONS_DIR.exists() else set()
        new = [n for n in after - before if "forge" in n.lower()]
        fid = new[0] if new else None
    if not fid:
        tail = (result.stdout + result.stderr).strip().splitlines()[-8:]
        raise RuntimeError("Установщик Forge не создал версию:\n" + "\n".join(tail))
    return fid
