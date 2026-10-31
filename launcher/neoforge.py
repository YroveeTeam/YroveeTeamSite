"""Установка NeoForge через официальный установщик (--installClient, как у Forge).

Версии NeoForge: 1.20.1 — 47.1.x, дальше старший разбор номера совпадает
с версией игры (1.20.4 -> 20.4.x, 1.21.1 -> 21.1.x, 1.21.8 -> 21.8.x...).
"""
import re
import subprocess
import sys

from config import CACHE_DIR, DATA, VERSIONS_DIR
from net import download_file, get_json

MAVEN_API = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"


def neoforge_prefix(mc):
    """Префикс версий NeoForge для версии Minecraft (None = NeoForge не бывает)."""
    parts = mc.split(".")
    if len(parts) < 3 or parts[0] != "1":
        return None
    try:
        nums = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None
    if nums < (1, 20, 1):  # NeoForge существует начиная с 1.20.1
        return None
    if nums == (1, 20, 1):
        return "47.1"  # старая нумерация, действовавшая до 1.20.2
    return f"{parts[1]}.{parts[2]}"


def _version_key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def pick_neoforge_version(mc):
    """Свежая версия NeoForge под эту игру или None."""
    prefix = neoforge_prefix(mc)
    if not prefix:
        return None
    try:
        data = get_json(MAVEN_API)
    except Exception:
        return None  # нет сети до maven.neoforged.net (может быть недоступен в некоторых сетях)
    versions = data.get("versions", []) if isinstance(data, dict) else data
    matches = [v for v in versions if v.startswith(prefix + ".")]
    return sorted(matches, key=_version_key)[-1] if matches else None


def find_neoforge_id(mc, nf_ver=None):
    """Ищет уже установленную версию NeoForge в data/versions."""
    if not VERSIONS_DIR.exists():
        return None
    best = None
    for d in VERSIONS_DIR.iterdir():
        name = d.name
        if not d.is_dir() or "neoforge" not in name.lower():
            continue
        if f"1.{mc}" not in name and mc not in name:
            # имена вида neoforge-21.1.77 (без версии игры) и 1.20.1-ветка 47.1.x
            if not (nf_ver and nf_ver in name):
                continue
        if nf_ver and nf_ver not in name:
            continue
        if (d / f"{name}.json").exists():
            if best is None or d.stat().st_mtime > best[0]:
                best = (d.stat().st_mtime, name)
    return best[1] if best else None


def ensure_neoforge(mc, java, nf_ver=None, status=None):
    """Возвращает id версии NeoForge, при необходимости скачивая и запуская установщик."""
    say = status or (lambda t: None)
    nf_ver = nf_ver or pick_neoforge_version(mc)
    if not nf_ver:
        raise RuntimeError(f"Для Minecraft {mc} нет NeoForge (поддержка с 1.20.1)")
    existing = find_neoforge_id(mc, nf_ver)
    if existing:
        return existing

    jar = CACHE_DIR / "neoforge" / f"neoforge-{nf_ver}-installer.jar"
    say(f"Скачивание NeoForge {nf_ver}…")
    download_file(f"{MAVEN}/{nf_ver}/neoforge-{nf_ver}-installer.jar", jar)

    DATA.mkdir(parents=True, exist_ok=True)
    profiles = DATA / "launcher_profiles.json"  # установщик без него отказывается работать
    if not profiles.exists():
        profiles.write_text('{"profiles": {}, "version": 3}', encoding="utf-8")

    before = {d.name for d in VERSIONS_DIR.iterdir()} if VERSIONS_DIR.exists() else set()
    say("Установка NeoForge (до пары минут)…")
    kwargs = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}
    result = subprocess.run(
        [str(java), "-jar", str(jar), "--installClient", str(DATA)],
        cwd=str(DATA), capture_output=True, text=True, errors="replace",
        timeout=1800, **kwargs,
    )
    fid = find_neoforge_id(mc, nf_ver)
    if not fid:
        after = {d.name for d in VERSIONS_DIR.iterdir()} if VERSIONS_DIR.exists() else set()
        new = [n for n in after - before if "neoforge" in n.lower()]
        fid = new[0] if new else None
    if not fid:
        tail = (result.stdout + result.stderr).strip().splitlines()[-8:]
        raise RuntimeError("Установщик NeoForge не создал версию:\n" + "\n".join(tail))
    return fid
