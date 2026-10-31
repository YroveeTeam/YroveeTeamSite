"""Discord Rich Presence: «играет в Minecraft <версия>». Необязательная фича.

Работает только если в config.py указан discord_app_id (Application ID из
discord.com/developers → Applications → New Application) и установлен
pypresence (попадает в requirements). Любая ошибка — молча выключаемся.
"""
import time

_STARTED = None
_START_TS = 0


def _available(app_id):
    if not app_id:
        return False
    try:
        import pypresence  # noqa: F401
        return True
    except Exception:
        return False


def start_game(app_id, version, loader):
    """Показывает присутствие; возвращает True, если получилось."""
    global _STARTED, _START_TS
    stop()
    if not _available(app_id):
        return False
    try:
        from pypresence import Presence
        _STARTED = Presence(str(app_id))
        _STARTED.connect()
        _START_TS = int(time.time())
        _STARTED.update(
            details=f"Minecraft {version} · {loader}",
            start=_START_TS,
            large_image="minecraft",
            large_text="Minecraft",
        )
        return True
    except Exception:
        _STARTED = None
        return False


def stop():
    """Прячет присутствие при выходе из игры или закрытии лаунчера."""
    global _STARTED
    if _STARTED is None:
        return
    try:
        _STARTED.clear()
        _STARTED.close()
    except Exception:
        pass
    _STARTED = None
