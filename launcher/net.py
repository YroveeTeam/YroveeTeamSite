import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session = requests.Session()
_session.headers["User-Agent"] = "YroveeLauncher/0.12"
# обрывы соединения (ConnectionReset 10054 и т.п.) и ошибки серверов повторяем с паузами
_retry = Retry(total=5, connect=5, read=5, backoff_factor=0.8,
               status_forcelist=(429, 500, 502, 503, 504))
_session.mount("https://", HTTPAdapter(max_retries=_retry, pool_maxsize=20))
_session.mount("http://", HTTPAdapter(max_retries=_retry, pool_maxsize=20))
session = _session

# Зеркало загрузок Mojang: "" — официальный сервер, иначе база зеркала
# (например "https://bmclapi2.bangbang93.com"). Ставится в Настройках.
MIRROR = ""
_MIRROR_CANDIDATES = {
    "official": "",
    "bmclapi": "https://bmclapi2.bangbang93.com",
}


def pick_fastest_mirror():
    """Авто: замеряет отклик официального сервера и зеркала, ставит быстрый."""
    import time
    best_name, best_ms = "official", 10 ** 9
    for name, base in _MIRROR_CANDIDATES.items():
        url = (base or "https://piston-meta.mojang.com") + "/mc/game/version_manifest_v2.json"
        t0 = time.perf_counter()
        try:
            r = _session.head(url, timeout=6, allow_redirects=True)
            if r.status_code >= 500:
                continue
            ms = (time.perf_counter() - t0) * 1000
        except Exception:
            continue
        if ms < best_ms:
            best_name, best_ms = name, ms
    globals()["MIRROR"] = _MIRROR_CANDIDATES[best_name]
    return best_name


def apply_mirror(url):
    """Перенаправляет файлы Mojang на выбранное зеркало (если оно задано)."""
    if not MIRROR:
        return url
    for prefix in ("https://piston-meta.mojang.com", "https://piston-data.mojang.com",
                   "https://launchermeta.mojang.com"):
        if url.startswith(prefix):
            return MIRROR + url[len(prefix):]
    if url.startswith("https://resources.download.minecraft.net"):
        return MIRROR + "/assets" + url[len("https://resources.download.minecraft.net"):]
    if url.startswith("https://libraries.minecraft.net"):
        return MIRROR + "/maven" + url[len("https://libraries.minecraft.net"):]
    return url


def friendly_error(e):
    """Понятный текст вместо технической ошибки сети."""
    text = str(e)
    markers = ("10054", "Connection aborted", "ConnectionReset", "Max retries", "timed out",
               "Temporary failure", "getaddrinfo", "10060", "10061")
    if isinstance(e, (requests.ConnectionError, requests.Timeout, ConnectionError)) or \
            any(m in text for m in markers):
        return ("Обрыв соединения при скачивании. Проверь интернет, отключи VPN/прокси и "
                "посмотри, не блокирует ли антивирус или брандмауэр Python. Нажми «Играть» ещё раз — "
                "уже скачанное не качается заново.")
    return text


def get_json(url, params=None):
    r = _session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def get_bytes(url, timeout=20):
    r = _session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def sha1_of(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid(path, sha1=None, size=None):
    if not path.exists():
        return False
    if size is not None and path.stat().st_size != size:
        return False
    if sha1 is not None and sha1_of(path) != sha1:
        return False
    return True


def download_file(url, dest, sha1=None, size=None, quick=False):
    dest = Path(dest)
    if quick and size is not None and dest.exists() and dest.stat().st_size == size:
        return  # ускоренный старт: совпал размер — считаем файл целым
    if is_valid(dest, sha1, size):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    last_error = None
    for attempt in range(5):
        try:
            with _session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
            if sha1 is not None and sha1_of(tmp) != sha1:
                raise IOError(f"Не совпал sha1: {url}")
            tmp.replace(dest)
            return
        except Exception as e:
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Не удалось скачать {url}: {last_error}")


def download_many(tasks, progress=None, workers=8, quick=False):
    """tasks: список словарей {url, dest, sha1?, size?}"""
    unique = {}
    for t in tasks:
        unique[str(t["dest"])] = t
    tasks = list(unique.values())
    total = len(tasks)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(download_file, t["url"], t["dest"], t.get("sha1"),
                        t.get("size"), quick)
            for t in tasks
        ]
        for fut in as_completed(futures):
            fut.result()
            done += 1
            if progress:
                progress(done, total)
