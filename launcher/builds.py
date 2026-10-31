"""Сборки: установка модпаков Modrinth (.mrpack) в отдельную папку игры."""
import json
import zipfile
from pathlib import Path

from modrinth import API, _pick_version
from net import download_file, download_many, get_json


def _safe_join(root, rel):
    root = Path(root).resolve()
    dest = (root / rel).resolve()
    if root != dest and root not in dest.parents:
        raise RuntimeError(f"Небезопасный путь в сборке: {rel}")
    return dest


def install_modpack(project_id, target_dir, status=None, progress=None):
    """Скачивает .mrpack и раскладывает всё по target_dir.
    Возвращает {title, icon_url, version, loader, forge_version}."""
    say = status or (lambda t: None)
    project = get_json(f"{API}/project/{project_id}")
    version = _pick_version(project["id"], None, None)
    if not version:
        raise RuntimeError("У этой сборки нет версий")
    files = version["files"]
    f = next((x for x in files if x.get("primary")), files[0])

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    pack = target_dir / ".pack.mrpack"
    say(f"Скачивание сборки «{project['title']}»…")
    download_file(f["url"], pack, f.get("hashes", {}).get("sha1"), f.get("size"))
    try:
        return install_pack_zip(pack, target_dir, project["title"], project.get("icon_url") or "",
                                status=status, progress=progress)
    finally:
        pack.unlink(missing_ok=True)


def install_pack_zip(pack, target_dir, title, icon_url="", status=None, progress=None):
    """Раскладывает локальный .mrpack по target_dir. Возвращает info сборки."""
    say = status or (lambda t: None)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(pack) as z:
        index = json.loads(z.read("modrinth.index.json"))
        deps = index.get("dependencies", {})
        mc = deps.get("minecraft", "")
        if "fabric-loader" in deps:
            loader = "Fabric"
        elif "forge" in deps:
            loader = "Forge"
        elif "quilt-loader" in deps:
            loader = "Quilt"
        elif "neoforge" in deps:
            loader = "NeoForge"
        else:
            raise RuntimeError("Сборка без известного загрузчика (Fabric/Forge/Quilt/NeoForge)")

        tasks = []
        for e in index.get("files", []):
            if e.get("env", {}).get("client") == "unsupported":
                continue
            tasks.append({
                "url": e["downloads"][0],
                "dest": _safe_join(target_dir, e["path"]),
                "sha1": e.get("hashes", {}).get("sha1"),
                "size": e.get("fileSize"),
            })
        say(f"Скачивание файлов сборки: {len(tasks)}")
        download_many(tasks, progress=progress)

        for prefix in ("overrides/", "client-overrides/"):
            for name in z.namelist():
                if name.startswith(prefix) and not name.endswith("/"):
                    dest = _safe_join(target_dir, name[len(prefix):])
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(z.read(name))
    return {
        "title": title,
        "icon_url": icon_url,
        "version": mc,
        "loader": loader,
        "forge_version": deps.get("forge", ""),
    }
