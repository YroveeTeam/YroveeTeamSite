"""Экспорт своей сборки в .mrpack — файл, который ставится любым лаунчером.

Моды, у которых известен Modrinth-идентификатор версии, попадают в index как
ссылки (pack лёгкий). Прочие .jar из mods/ кладутся внутрь overrides.
Мира, скриншотов и настроек внутри не будет — в сборку идёт только игра.
"""
import json
import zipfile
from pathlib import Path

from fabric import fabric_id
from modrinth import KIND_DIRS, list_installed
from net import get_json
from quilt import quilt_id
from versions import version_json_path


def _loader_from_version_json(vid):
    """Версия fabric-loader / quilt-loader из профиля установленной версии."""
    try:
        data = json.loads(version_json_path(vid).read_text(encoding="utf-8"))
    except Exception:
        return ""
    for lib in data.get("libraries", []):
        name = lib.get("name", "")
        for prefix in ("net.fabricmc:fabric-loader:", "org.quiltmc:quilt-loader:"):
            if name.startswith(prefix):
                return name[len(prefix):]
    return ""


def detect_loader_version(loader, mc_version, forge_version=""):
    if loader == "Fabric":
        return _loader_from_version_json(fabric_id(mc_version)) or "0.16.14"
    if loader == "Quilt":
        return _loader_from_version_json(quilt_id(mc_version)) or "0.26.4"
    if loader == "Forge" and forge_version:
        return forge_version
    if loader == "Forge":
        from forge import find_forge_id
        fid = find_forge_id(mc_version) or ""
        return fid.replace(f"forge-{mc_version}-", "") if fid else ""
    if loader == "NeoForge":
        from neoforge import find_neoforge_id
        fid = find_neoforge_id(mc_version) or ""
        return fid.split("-", 1)[-1] if fid else ""
    return ""


def export_modpack(instance_dir, name, mc_version, loader, loader_version, dest):
    """Собирает .mrpack. Возвращает путь к файлу."""
    if loader in ("Forge", "NeoForge") and not loader_version:
        raise RuntimeError("Не удалось определить версию загрузчика — запусти игру один раз и попробуй снова")

    files, overrides = [], []
    for kind, dirname in KIND_DIRS.items():
        d = Path(instance_dir) / dirname
        registry = list_installed(d)
        registered = set()
        for pid, info in registry.items():
            registered.add(info["filename"])
            if not info.get("version_id"):
                overrides.append(d / info["filename"])
                continue
            try:
                v = get_json(f"https://api.modrinth.com/v2/version/{info['version_id']}")
                f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
            except Exception:
                overrides.append(d / info["filename"])
                continue
            files.append({
                "path": f"{dirname}/{info['filename']}",
                "hashes": f.get("hashes", {}),
                "downloads": [f["url"]],
                "fileSize": f.get("size", 0),
            })
        for f in d.glob("*.jar"):
            if f.name not in registered:
                overrides.append(f)

    deps = {"minecraft": mc_version}
    if loader == "Fabric":
        deps["fabric-loader"] = loader_version
    elif loader == "Quilt":
        deps["quilt-loader"] = loader_version
    elif loader == "Forge":
        deps["forge"] = loader_version
    elif loader == "NeoForge":
        deps["neoforge"] = loader_version

    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "1.0.0",
        "name": name,
        "files": files,
        "dependencies": deps,
    }

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("modrinth.index.json", json.dumps(index, indent=2, ensure_ascii=False))
        for f in overrides:
            if f.is_file():
                z.write(f, f"overrides/{f.parent.name}/{f.name}")
    return dest
