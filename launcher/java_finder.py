import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from config import RUNTIME_DIR

IS_WIN = sys.platform.startswith("win")
EXE = "java.exe" if IS_WIN else "java"

_major_cache = {}


def java_major(java_path):
    """Главная версия Java (8, 17, 21...) или None, если файл не запускается."""
    key = str(java_path)
    if key in _major_cache:
        return _major_cache[key]
    kwargs = {"creationflags": 0x08000000} if IS_WIN else {}  # без мигания окна
    try:
        out = subprocess.run(
            [key, "-version"], capture_output=True, text=True,
            errors="replace", timeout=15, **kwargs
        ).stderr
    except Exception:
        return None
    m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
    if not m:
        return None
    major = int(m.group(1))
    if major == 1 and m.group(2):  # "1.8.0_391" -> 8
        major = int(m.group(2))
    _major_cache[key] = major
    return major


def candidate_paths(custom=""):
    found = []
    if custom:
        found.append(Path(custom))
    if RUNTIME_DIR.exists():  # Java, которую поставил сам лаунчер
        found.extend(RUNTIME_DIR.rglob(f"bin/{EXE}"))
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        found.append(Path(java_home) / "bin" / EXE)
    which = shutil.which("java")
    if which:
        found.append(Path(which))
    if IS_WIN:
        roots = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ]
        vendors = ["Java", "Eclipse Adoptium", "Microsoft", "Zulu",
                   "BellSoft", "Amazon Corretto", "Semeru"]
        for root in roots:
            for vendor in vendors:
                base = Path(root) / vendor
                if base.is_dir():
                    found.extend(base.glob(f"*/bin/{EXE}"))
    return found


def _iter_existing(custom=""):
    seen = set()
    for p in candidate_paths(custom):
        key = str(p).lower()
        if key in seen or not p.is_file():
            continue
        seen.add(key)
        yield p


def find_java(accepted, custom=""):
    """Первая найденная Java, главная версия которой входит в множество accepted."""
    for p in _iter_existing(custom):
        if java_major(p) in accepted:
            return p
    return None


def find_java_at_least(required, custom=""):
    """Запасной вариант: самая близкая Java не ниже required."""
    best = None
    for p in _iter_existing(custom):
        major = java_major(p)
        if major and major >= required and (best is None or major < best[0]):
            best = (major, p)
    return best[1] if best else None
