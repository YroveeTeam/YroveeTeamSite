import hashlib
import os
import re
import shlex
import subprocess
import uuid
from pathlib import Path

from config import (ASSETS_DIR, LIBRARIES_DIR, NATIVES_DIR,
                    LAUNCHER_NAME, LAUNCHER_VERSION, instance_dir)
from java_installer import ensure_java
from versions import load_version, rules_allow, build_classpath, prepare_assets


def offline_uuid(name):
    digest = hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest, version=3))


def join_args(version_id, server):
    """Аргументы быстрого входа на сервер: старый и новый формат (с 1.20)."""
    m = re.search(r"(\d+)\.(\d+)", version_id)
    if m and int(m.group(1)) == 1 and int(m.group(2)) < 20:
        host, _, port = server.partition(":")
        return ["--server", host] + (["--port", port] if port else [])
    return ["--quickPlayMultiplayer", server]


def required_java(version_id):
    data = load_version(version_id)
    return data.get("javaVersion", {}).get("majorVersion", 8)


def collect_args(items):
    out = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif rules_allow(item.get("rules")):
            value = item["value"]
            out.extend([value] if isinstance(value, str) else value)
    return out


def substitute(arg, variables):
    return re.sub(
        r"\$\{(\w+)\}", lambda m: str(variables.get(m.group(1), m.group(0))), arg
    )


def build_command(version_id, cfg, java=None):
    data = load_version(version_id)

    if java is None:
        java = ensure_java(required_java(version_id), cfg.get("java_path", ""))

    game_dir = Path(cfg["game_dir"]) if cfg.get("game_dir") else instance_dir(version_id)
    game_dir.mkdir(parents=True, exist_ok=True)
    game_assets = prepare_assets(data, game_dir)

    username = cfg["username"]
    msa = bool(cfg.get("auth_uuid") or (cfg.get("auth_access_token") not in (None, "", "0")))
    variables = {
        "auth_player_name": username,
        "version_name": data["id"],
        "game_directory": str(game_dir),
        "assets_root": str(ASSETS_DIR),
        "assets_index_name": data["assetIndex"]["id"],
        "auth_uuid": cfg.get("auth_uuid") or offline_uuid(username),
        "auth_access_token": cfg.get("auth_access_token") or "0",
        "auth_session": cfg.get("auth_access_token") or "0",
        "clientid": "",
        "auth_xuid": "0",
        "user_type": "msa" if msa else "legacy",
        "version_type": data.get("type", "release"),
        "user_properties": "{}",
        "game_assets": str(game_assets),
        "natives_directory": str(NATIVES_DIR / data["id"]),
        "launcher_name": LAUNCHER_NAME,
        "launcher_version": LAUNCHER_VERSION,
        "library_directory": str(LIBRARIES_DIR),
        "classpath_separator": os.pathsep,
        "classpath": os.pathsep.join(str(p) for p in build_classpath(data)),
    }

    if "arguments" in data:  # версии 1.13+
        jvm = collect_args(data["arguments"].get("jvm", []))
        game = collect_args(data["arguments"].get("game", []))
    else:  # старый формат (1.5.2 - 1.12.2)
        jvm = ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"]
        game = data["minecraftArguments"].split()

    cmd = [str(java), f"-Xmx{cfg['ram_mb']}M", "-Xms512M"]
    cmd += shlex.split(cfg.get("extra_jvm_args", ""))
    cmd += [substitute(a, variables) for a in jvm]
    cmd.append(data["mainClass"])
    cmd += [substitute(a, variables) for a in game]
    if cfg.get("join_server"):
        cmd += join_args(version_id, cfg["join_server"])
    return cmd, game_dir


def launch(version_id, cfg, java=None):
    cmd, game_dir = build_command(version_id, cfg, java)
    kwargs = {"creationflags": 0x08000000} if os.name == "nt" else {}
    return subprocess.Popen(
        cmd, cwd=game_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, **kwargs
    )
