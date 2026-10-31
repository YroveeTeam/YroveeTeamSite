import platform
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

import requests

from config import RUNTIME_DIR
from net import session
from java_finder import EXE, find_java, find_java_at_least, java_major

# Minecraft просит 8, 16, 17, 21, 25... Берём ближайшую LTS-версию Temurin не ниже нужной.
LTS = [8, 11, 17, 21, 25]
API = ("https://api.adoptium.net/v3/binary/latest/"
       "{feature}/ga/{os}/{arch}/jre/hotspot/normal/eclipse")


def pick_feature(required):
    for v in LTS:
        if v >= required:
            return v
    return required


def _os_name():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


def _arch():
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "aarch64"
    return "x64"


def download_java(feature, progress=None):
    """Скачивает JRE Temurin нужной версии в data/runtime/java<N>. progress(done, total)."""
    url = API.format(feature=feature, os=_os_name(), arch=_arch())
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    target = RUNTIME_DIR / f"java{feature}"
    tmp_dir = RUNTIME_DIR / f"java{feature}.tmp"
    archive = RUNTIME_DIR / f"java{feature}.download"

    with session.get(url, stream=True, timeout=60, allow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with open(archive, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmp_dir)
    else:
        with tarfile.open(archive) as t:
            try:
                t.extractall(tmp_dir, filter="data")
            except TypeError:  # старый Python без filter
                t.extractall(tmp_dir)
    archive.unlink()

    if target.exists():
        shutil.rmtree(target)
    tmp_dir.rename(target)

    java = next(target.rglob(f"bin/{EXE}"), None)
    if java is None or java_major(java) is None:
        raise RuntimeError("Java скачалась, но не запускается")
    return java


def ensure_java(required, custom="", progress=None):
    """Возвращает путь к java нужной версии, при необходимости скачивая её."""
    # 1. Путь, который пользователь указал сам, уважаем всегда
    if custom:
        p = Path(custom)
        if p.is_file() and java_major(p):
            return p

    # 2. Подходящая Java уже есть в системе или в data/runtime
    feature = pick_feature(required)
    found = find_java({required, feature})
    if found:
        return found

    # 3. Качаем сами
    try:
        return download_java(feature, progress)
    except Exception as e:
        fallback = find_java_at_least(required)
        if fallback:
            return fallback
        raise RuntimeError(f"Не удалось установить Java {feature}: {e}")
