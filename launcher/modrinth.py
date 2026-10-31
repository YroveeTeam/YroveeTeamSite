import json

from net import download_file, get_json

API = "https://api.modrinth.com/v2"
REGISTRY_NAME = ".launcher_mods.json"

# kind -> (папка внутри папки игры)
KIND_DIRS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}


# ---------- список установленных (лежит рядом с файлами) ----------

def _registry_path(dest_dir):
    return dest_dir / REGISTRY_NAME


def list_installed(dest_dir):
    """{project_id: {title, filename, version, version_id, icon_url, incompatible}}"""
    path = _registry_path(dest_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_registry(dest_dir, registry):
    dest_dir.mkdir(parents=True, exist_ok=True)
    _registry_path(dest_dir).write_text(
        json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------- поиск ----------

def _loaders_for(kind, loader):
    if kind == "resourcepack":
        return ["minecraft"]
    if kind == "shader":
        return ["iris", "optifine"]
    return [loader] if loader else []


def search_mods(query, game_version, loader="fabric", limit=30, kind="mod", categories=()):
    """kind: mod | resourcepack | shader | modpack; categories: теги Modrinth (decoration, technology...)"""
    facets = [[f"project_type:{kind}"]]
    if kind == "shader":
        facets.append(["categories:iris", "categories:optifine"])  # внутри списка — ИЛИ
    elif kind in ("mod", "modpack") and loader:
        facets.append([f"categories:{loader}"])
    if categories:
        facets.append([f"categories:{c}" for c in categories])  # ИЛИ внутри списка
    if game_version:
        facets.append([f"versions:{game_version}"])
    params = {
        "query": query,
        "facets": json.dumps(facets),
        "limit": limit,
        "index": "relevance" if query else "downloads",
    }
    return get_json(f"{API}/search", params)["hits"]


def _pick_version(project_id, game_version, loaders):
    params = {}
    if game_version:
        params["game_versions"] = json.dumps([game_version])
    if loaders:
        params["loaders"] = json.dumps(list(loaders))
    versions = get_json(f"{API}/project/{project_id}/version", params)
    if not versions:
        return None
    releases = [v for v in versions if v.get("version_type") == "release"]
    return (releases or versions)[0]  # список приходит от новых к старым


# ---------- установка ----------

def install_mod(project_id, game_version, loader, dest_dir, status=None, _stack=None, kind="mod"):
    """Ставит мод/ресурспак/шейдер. Для модов — вместе с обязательными зависимостями."""
    stack = _stack if _stack is not None else set()
    if project_id in stack:
        return
    stack.add(project_id)

    project = get_json(f"{API}/project/{project_id}")
    pid = project["id"]  # project_id может быть и slug'ом
    title = project["title"]
    # конфликт с уже установленным — проверяем ДО скачивания
    registry = list_installed(dest_dir)
    if pid in registry:
        raise RuntimeError(f"«{title}» уже установлен")
    for other_pid, info in registry.items():
        if pid in info.get("incompatible", []):
            raise RuntimeError(f"«{title}» конфликтует с установленным "
                               f"«{info['title']}» — сначала удали один из них")
    version = _pick_version(pid, game_version, _loaders_for(kind, loader))
    if version is None:
        raise RuntimeError(f"У «{title}» нет версии под {game_version}")

    incompatible = []
    for dep in version.get("dependencies", []):
        dtype = dep.get("dependency_type")
        dep_id = dep.get("project_id")
        if dtype == "incompatible" and dep_id:
            incompatible.append(dep_id)
        if kind != "mod" or dtype != "required":
            continue
        if not dep_id and dep.get("version_id"):
            dep_id = get_json(f"{API}/version/{dep['version_id']}")["project_id"]
        if dep_id and dep_id not in list_installed(dest_dir):
            install_mod(dep_id, game_version, loader, dest_dir, status, stack, kind)

    if status:
        status(f"Установка: {title}")
    files = version["files"]
    file = next((f for f in files if f.get("primary")), files[0])

    registry = list_installed(dest_dir)
    old = registry.get(pid)
    if old and old["filename"] != file["filename"]:
        (dest_dir / old["filename"]).unlink(missing_ok=True)

    download_file(file["url"], dest_dir / file["filename"],
                  file.get("hashes", {}).get("sha1"), file.get("size"))
    registry[pid] = {
        "title": title,
        "filename": file["filename"],
        "version": version.get("version_number", ""),
        "version_id": version.get("id", ""),
        "icon_url": project.get("icon_url") or "",
        "incompatible": incompatible,
    }
    _save_registry(dest_dir, registry)


def remove_mod(project_id, dest_dir):
    registry = list_installed(dest_dir)
    info = registry.pop(project_id, None)
    if info:
        (dest_dir / info["filename"]).unlink(missing_ok=True)
        _save_registry(dest_dir, registry)


def fill_missing_icons(dest_dir):
    """Дописывает ссылки на иконки тем, что поставила старая версия лаунчера."""
    registry = list_installed(dest_dir)
    changed = False
    for pid, info in registry.items():
        if "icon_url" in info:
            continue
        try:
            info["icon_url"] = get_json(f"{API}/project/{pid}").get("icon_url") or ""
            changed = True
        except Exception:
            continue
    if changed:
        _save_registry(dest_dir, registry)
    return registry


# ---------- обновления и конфликты ----------

def analyze(dest_dir, game_version, loader, kind="mod", status=None):
    """Проверяет установленное: что можно обновить и что не в порядке.
    Возвращает {"updates": [{pid, title, old, new}], "problems": [str]}"""
    registry = list_installed(dest_dir)
    updates, problems = [], []
    for n, (pid, info) in enumerate(registry.items(), start=1):
        if status:
            status(f"Проверка {n}/{len(registry)}: {info['title']}")
        if not (dest_dir / info["filename"]).exists():
            problems.append(f"«{info['title']}»: файл {info['filename']} пропал из папки")
        try:
            version = _pick_version(pid, game_version, _loaders_for(kind, loader))
        except Exception:
            continue  # нет сети для этого запроса — пропускаем
        if version is None:
            problems.append(f"«{info['title']}»: нет версии под Minecraft {game_version}")
            continue
        files = version["files"]
        primary = next((f for f in files if f.get("primary")), files[0])
        same = (version.get("id") == info.get("version_id") if info.get("version_id")
                else primary["filename"] == info["filename"])
        if not same:
            updates.append({"pid": pid, "title": info["title"], "old": info.get("version", "?"),
                            "new": version.get("version_number", "?")})
    for pid, info in registry.items():
        for other in info.get("incompatible", []):
            if other in registry:
                problems.append(f"«{info['title']}» конфликтует с «{registry[other]['title']}»")
    return {"updates": updates, "problems": problems}
