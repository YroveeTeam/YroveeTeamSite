import json
import platform
import shutil
import re
import sys
import zipfile

from config import VERSIONS_DIR, LIBRARIES_DIR, ASSETS_DIR, NATIVES_DIR, CACHE_DIR
from net import apply_mirror, get_json, download_file, download_many

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
RESOURCES_URL = "https://resources.download.minecraft.net"

if sys.platform.startswith("win"):
    OS_NAME = "windows"
elif sys.platform == "darwin":
    OS_NAME = "osx"
else:
    OS_NAME = "linux"

IS_64BIT = sys.maxsize > 2 ** 32


# ---------- правила (rules) из json Mojang ----------

def rule_matches(rule, features=None):
    features = features or {}
    os_rule = rule.get("os")
    if os_rule:
        if "name" in os_rule and os_rule["name"] != OS_NAME:
            return False
        if os_rule.get("arch") == "x86" and IS_64BIT:
            return False
        if "version" in os_rule and not re.match(os_rule["version"], platform.version()):
            return False
    for key, value in rule.get("features", {}).items():
        if features.get(key, False) != value:
            return False
    return True


def rules_allow(rules, features=None):
    if not rules:
        return True
    allowed = False
    for rule in rules:
        if rule_matches(rule, features):
            allowed = rule["action"] == "allow"
    return allowed


# ---------- список версий ----------

def list_versions(kinds=("release",)):
    manifest = get_json(MANIFEST_URL)
    return [v["id"] for v in manifest["versions"] if v["type"] in kinds]


def version_json_path(version_id):
    return VERSIONS_DIR / version_id / f"{version_id}.json"


def download_version_json(version_id):
    path = version_json_path(version_id)
    if path.exists():
        return path
    manifest = get_json(apply_mirror(MANIFEST_URL))
    for v in manifest["versions"]:
        if v["id"] == version_id:
            download_file(apply_mirror(v["url"]), path, sha1=v.get("sha1"))
            return path
    raise ValueError(f"Версия {version_id} не найдена")


def load_version(version_id):
    """Читает json версии. Умеет inheritsFrom (понадобится для Fabric/Forge)."""
    path = version_json_path(version_id)
    if not path.exists():
        download_version_json(version_id)
    data = json.loads(path.read_text(encoding="utf-8"))

    parent_id = data.get("inheritsFrom")
    if not parent_id:
        data["_jar_id"] = data.get("jar", version_id)
        return data

    parent = load_version(parent_id)
    merged = dict(parent)
    for key, value in data.items():
        if key == "libraries":
            merged[key] = value + parent.get("libraries", [])
        elif key == "arguments":
            pa = parent.get("arguments", {})
            merged["arguments"] = {
                "game": pa.get("game", []) + value.get("game", []),
                "jvm": pa.get("jvm", []) + value.get("jvm", []),
            }
        else:
            merged[key] = value
    merged["_jar_id"] = parent["_jar_id"]
    return merged


# ---------- библиотеки ----------

def maven_path(name):
    group, artifact, version = name.split(":")[:3]
    return f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.jar"


def lib_artifact(lib):
    art = lib.get("downloads", {}).get("artifact")
    if art:
        return {
            "url": art["url"],
            "dest": LIBRARIES_DIR / art["path"],
            "sha1": art.get("sha1"),
            "size": art.get("size"),
        }
    if "url" in lib and "name" in lib:  # формат Fabric
        rel = maven_path(lib["name"])
        return {
            "url": lib["url"].rstrip("/") + "/" + rel,
            "dest": LIBRARIES_DIR / rel,
            "sha1": None,
            "size": None,
        }
    return None


def native_classifier(lib):
    """Старый формат natives (до 1.19): отдельный jar-классификатор."""
    natives = lib.get("natives")
    if not natives or OS_NAME not in natives:
        return None
    key = natives[OS_NAME].replace("${arch}", "64" if IS_64BIT else "32")
    return lib.get("downloads", {}).get("classifiers", {}).get(key)


def build_classpath(data):
    paths, seen = [], set()
    for lib in data["libraries"]:
        if not rules_allow(lib.get("rules")):
            continue
        art = lib_artifact(lib)
        if art and str(art["dest"]) not in seen:
            seen.add(str(art["dest"]))
            paths.append(art["dest"])
    jar_id = data["_jar_id"]
    paths.append(VERSIONS_DIR / jar_id / f"{jar_id}.jar")
    return paths


def extract_natives(data):
    out = NATIVES_DIR / data["id"]
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        return out
    for lib in data["libraries"]:
        if not rules_allow(lib.get("rules")):
            continue
        cls = native_classifier(lib)
        if not cls:
            continue
        jar = LIBRARIES_DIR / cls["path"]
        excludes = lib.get("extract", {}).get("exclude", [])
        with zipfile.ZipFile(jar) as z:
            for member in z.namelist():
                if member.endswith("/"):
                    continue
                if any(member.startswith(e) for e in excludes):
                    continue
                z.extract(member, out)
    return out


# ---------- установка версии ----------

def install_version(version_id, progress=None, quick=False):
    """quick=True: существующие файлы совпадающего размера не перепроверяются
    по sha1 — старт заметно быстрее, но битый файл не заметит."""
    data = load_version(version_id)
    tasks = []

    # клиентский jar
    jar_id = data["_jar_id"]
    client = data["downloads"]["client"]
    tasks.append({
        "url": apply_mirror(client["url"]),
        "dest": VERSIONS_DIR / jar_id / f"{jar_id}.jar",
        "sha1": client["sha1"],
        "size": client["size"],
    })

    # библиотеки
    for lib in data["libraries"]:
        if not rules_allow(lib.get("rules")):
            continue
        art = lib_artifact(lib)
        if art:
            tasks.append(art)
        cls = native_classifier(lib)
        if cls:
            tasks.append({
                "url": apply_mirror(cls["url"]),
                "dest": LIBRARIES_DIR / cls["path"],
                "sha1": cls.get("sha1"),
                "size": cls.get("size"),
            })

    # ассеты (звуки, языки, иконки)
    ai = data["assetIndex"]
    index_path = ASSETS_DIR / "indexes" / f"{ai['id']}.json"
    download_file(apply_mirror(ai["url"]), index_path, ai.get("sha1"), ai.get("size"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for obj in index["objects"].values():
        h = obj["hash"]
        tasks.append({
            "url": apply_mirror(f"{RESOURCES_URL}/{h[:2]}/{h}"),
            "dest": ASSETS_DIR / "objects" / h[:2] / h,
            "size": obj["size"],
        })

    download_many(tasks, progress, quick=quick)
    extract_natives(data)


def get_all_versions():
    """[(id, type), ...] из манифеста Mojang, новые версии первыми."""
    manifest = get_json(apply_mirror(MANIFEST_URL))
    result = [(v["id"], v["type"]) for v in manifest["versions"]]
    try:  # кэш на случай, когда в следующий раз не будет сети
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / "versions_cache.json").write_text(
            json.dumps(result), encoding="utf-8")
    except Exception:
        pass
    return result


def get_all_versions_cached():
    """Онлайн-список версий; при неудаче — кэш последнего удачного списка."""
    try:
        return get_all_versions()
    except Exception:
        p = CACHE_DIR / "versions_cache.json"
        if p.exists():
            try:
                return [tuple(x) for x in json.loads(p.read_text(encoding="utf-8"))]
            except Exception:
                pass
        raise


def installed_versions():
    """Версии, json которых уже лежит в data/versions (в будущем и Fabric/Forge)."""
    if not VERSIONS_DIR.exists():
        return []
    return sorted(
        (p.name for p in VERSIONS_DIR.iterdir() if (p / f"{p.name}.json").exists()),
        reverse=True,
    )


def prepare_assets(data, game_dir):
    """Для старых версий (до ~1.7) копирует ассеты в «виртуальную» папку.
    Возвращает путь, который подставляется в ${game_assets}."""
    ai = data["assetIndex"]
    index_path = ASSETS_DIR / "indexes" / f"{ai['id']}.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("map_to_resources"):      # 1.5.2 и старее
        dest = game_dir / "resources"
    elif index.get("virtual"):             # примерно 1.6 - 1.7.2
        dest = ASSETS_DIR / "virtual" / ai["id"]
    else:
        return ASSETS_DIR
    for name, obj in index["objects"].items():
        h = obj["hash"]
        src = ASSETS_DIR / "objects" / h[:2] / h
        dst = dest / name
        if dst.exists() and dst.stat().st_size == obj["size"]:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return dest
