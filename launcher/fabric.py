import json

import requests

from net import get_json
from versions import version_json_path

META = "https://meta.fabricmc.net/v2"


def fabric_id(game_version):
    """Имя версии с Fabric в папке data/versions и в instances."""
    return f"fabric-{game_version}"


def latest_loader(game_version):
    try:
        data = get_json(f"{META}/versions/loader/{game_version}")
    except requests.HTTPError:
        data = []
    if not data:
        raise RuntimeError(
            f"Fabric не поддерживает Minecraft {game_version} "
            f"(он работает с 1.14 и новее)"
        )
    stable = [d for d in data if d["loader"].get("stable")]
    return (stable or data)[0]["loader"]["version"]


def install_fabric(game_version, force=False):
    """Скачивает профиль Fabric и кладёт его как версию fabric-<game_version>.
    Остальное (библиотеки, ассеты, jar игры) докачает install_version."""
    vid = fabric_id(game_version)
    path = version_json_path(vid)
    if path.exists() and not force:
        return vid  # уже стоит, сеть не нужна

    loader = latest_loader(game_version)
    profile = get_json(
        f"{META}/versions/loader/{game_version}/{loader}/profile/json"
    )
    profile["id"] = vid
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return vid
