"""Самообновление лаунчера: качает установщик из GitHub Releases и запускает его.

В релизе должен лежать файл YroveeLauncher-Setup.exe (его собирает build_exe.bat).
Если файла нет — открываем страницу релиза в браузере.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from config import LAUNCHER_VERSION, REPO
from net import session

API = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def latest_release():
    """{tag, setup_url, page} или None, если GitHub недоступен или релизов нет."""
    r = session.get(API, timeout=15, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    rel = r.json()
    assets = rel.get("assets", [])
    setup = next((a for a in assets
                  if "setup" in a["name"].lower() and a["name"].endswith(".exe")), None)
    return {
        "tag": (rel.get("tag_name") or "").lstrip("v"),
        "setup_url": setup["browser_download_url"] if setup else "",
        "page": rel.get("html_url", ""),
    }


def is_newer(remote, local=LAUNCHER_VERSION):
    return parse_version(remote) > parse_version(local)


def download_and_run(setup_url, status=None):
    """Скачивает установщик в %TEMP% и запускает его. Возвращает путь к файлу."""
    say = status or (lambda t: None)
    if not setup_url:
        raise RuntimeError("В последнем релизе нет файла YroveeLauncher-Setup.exe — "
                           "скачай обновление вручную со страницы релиза")
    dest = Path(tempfile.gettempdir()) / "YroveeLauncher-Setup.exe"
    say("Скачивание обновления…")
    with session.get(setup_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                f.write(chunk)
    say("Запуск установщика…")
    kwargs = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}
    subprocess.Popen([str(dest)], **kwargs)
    return dest
