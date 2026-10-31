"""Вход через Microsoft-аккаунт: device code flow, обновление токена, профиль и скин.

Нужен MSA_CLIENT_ID в config.py (Application ID бесплатного приложения Azure).
Оффлайн-аккаунты продолжают работать как раньше, без сети.
"""
import time
from pathlib import Path

from config import MSA_CLIENT_ID
from net import get_bytes, session

SCOPE = "XboxLive.signin offline_access"
DEVICE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"
MC_SKIN_URL = "https://api.minecraftservices.com/minecraft/profile/skins"

ERRORS = {
    "authorization_declined": "Вход отклонён в браузере",
    "expired_token": "Код истёк — нажми «Войти через Microsoft» ещё раз",
    "invalid_client": "Неверный MSA_CLIENT_ID в config.py",
    "invalid_grant": "Токен обновления больше не действует — войди заново",
}


class MsaError(RuntimeError):
    pass


def _device_data(extra=None):
    data = {"client_id": MSA_CLIENT_ID, "scope": SCOPE}
    if extra:
        data.update(extra)
    return data


def device_code_start():
    """(user_code, verification_uri, device_code, interval) — код для ввода в браузере."""
    if not MSA_CLIENT_ID:
        raise MsaError(
            "Вход через Microsoft не настроен: в config.py пусто MSA_CLIENT_ID. "
            "Создай бесплатное приложение на portal.azure.com (App registrations, "
            "тип «любые организации и личные аккаунты», платформа Mobile and desktop "
            "applications с redirect URI http://localhost) и вставь его Application ID."
        )
    r = session.post(DEVICE_URL, data=_device_data(), timeout=30)
    if r.status_code != 200:
        raise MsaError(f"Microsoft ответил {r.status_code}: {r.text[:200]}")
    d = r.json()
    return d["user_code"], d["verification_uri"], d["device_code"], int(d.get("interval", 5))


def _token_request(data):
    r = session.post(TOKEN_URL, data=_device_data(data), timeout=30)
    d = r.json()
    if "error" in d:
        raise MsaError(ERRORS.get(d["error"], d.get("error_description") or d["error"]))
    return d


class _Pending(MsaError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _token_request_or_pending(data):
    r = session.post(TOKEN_URL, data=_device_data(data), timeout=30)
    d = r.json()
    if "error" in d:
        if d["error"] in ("authorization_pending", "slow_down"):
            raise _Pending(d["error"])
        raise MsaError(ERRORS.get(d["error"], d.get("error_description", d["error"])))
    return d


def device_code_wait(device_code, interval, status=None):
    """Ждёт подтверждения в браузере. Возвращает готовый аккаунт msa."""
    say = status or (lambda t: None)
    while True:
        try:
            tokens = _token_request_or_pending({"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                                "device_code": device_code})
        except _Pending as p:
            say("Жду подтверждения в браузере…")
            time.sleep(interval + (5 if p.code == "slow_down" else 0))
            continue
        break

    mc = _minecraft_login(tokens["access_token"])
    profile = fetch_profile(mc["access_token"])
    skin_url = ""
    for skin in profile.get("skins", []):
        if skin.get("state") == "ACTIVE" and skin.get("url"):
            skin_url = skin["url"]
            break
    return {
        "type": "msa",
        "name": profile.get("name") or mc.get("name", "Player"),
        "uuid": mc["uuid"],
        "access_token": mc["access_token"],
        "expires_at": time.time() + int(mc.get("expires_in", 86400)) - 120,
        "refresh_token": tokens.get("refresh_token", ""),
        "skin_url": skin_url,
    }


def _minecraft_login(ms_token):
    """MS-токен -> (uuid, name, access_token, expires_in) игровой Minecraft-сессии."""
    r = session.post(XBL_URL, json={
        "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com",
                       "RpsTicket": "d=" + ms_token},
        "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT",
    }, timeout=30)
    if r.status_code != 200:
        raise MsaError(f"Xbox Live не принял вход ({r.status_code})")
    xbl = r.json()["Token"]

    r = session.post(XSTS_URL, json={
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl]},
        "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT",
    }, timeout=30)
    if r.status_code != 200:  # 401 = лицензии Minecraft нет у этого аккаунта
        try:
            ident = r.json().get("XErr")
        except Exception:
            ident = r.status_code
        hints = {2148916233: "У этого аккаунта нет Minecraft (нет лицензии)",
                 2148916235: "Xbox Live недоступен в этой стране",
                 2148916236: "Аккаунт взрослого: добавь Minecraft в список игр ребёнка",
                 2148916237: "Аккаунт ребёнка: нужно разрешение взрослого в настройках Xbox",
                 2148916238: "Аккаунт ребёнка: нужно разрешение взрослого в настройках Xbox"}
        raise MsaError(f"Xbox не авторизовал аккаунт ({ident}). " + hints.get(ident, "Попробуй другой аккаунт."))
    xsts = r.json()
    uhs = xsts["DisplayClaims"]["xui"][0]["uhs"]

    r = session.post(MC_LOGIN_URL, json={"identityToken": f"XBL3.0 x={uhs};{xsts['Token']}"}, timeout=30)
    if r.status_code != 200:
        raise MsaError(f"Minecraft-серверы не приняли вход ({r.status_code})")
    d = r.json()
    return {"uuid": d.get("uuid") or "", "name": d.get("username", ""),
            "access_token": d["access_token"], "expires_in": d.get("expires_in", 86400)}


def fetch_profile(mc_token):
    """Профиль Minecraft: ник, uuid, скины."""
    r = session.get(MC_PROFILE_URL, headers={"Authorization": "Bearer " + mc_token}, timeout=30)
    if r.status_code != 200:
        raise MsaError(f"Не удалось получить профиль ({r.status_code})")
    return r.json()


def refresh_account(acc):
    """Обновляет access_token по refresh_token прямо в словаре аккаунта. Возвращает acc."""
    if not acc.get("refresh_token"):
        raise MsaError("Нет токена обновления — войди через Microsoft заново")
    try:
        tokens = _token_request({"grant_type": "refresh_token",
                                 "refresh_token": acc["refresh_token"],
                                 "scope": SCOPE})
    except MsaError:
        raise
    mc = _minecraft_login(tokens["access_token"])
    acc["access_token"] = mc["access_token"]
    acc["expires_at"] = time.time() + int(mc.get("expires_in", 86400)) - 120
    if tokens.get("refresh_token"):
        acc["refresh_token"] = tokens["refresh_token"]
    if mc.get("name"):
        acc["name"] = mc["name"]
    return acc


def ensure_msa_token(acc):
    """Гарантирует свежий access_token. Оффлайн-аккаунты пропускает (None)."""
    if acc.get("type") != "msa":
        return None
    if acc.get("access_token") and time.time() < acc.get("expires_at", 0):
        return acc["access_token"]
    return refresh_account(acc)["access_token"]


def download_skin(url, dest):
    """Скачивает скин (PNG) из профиля или по нику с серверов Mojang."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(get_bytes(url))
    return dest


def skin_by_nick(name):
    """Ссылка на скин лицензионного ника или None (в т.ч. если аккаунта нет)."""
    try:
        r = session.get(f"https://api.mojang.com/users/profiles/minecraft/{name}", timeout=15)
        if r.status_code != 200:
            return None
        pid = r.json()["id"]
        prof = session.get(f"https://sessionserver.mojang.com/session/minecraft/profile/{pid}",
                           timeout=15).json()
        import base64
        import json
        prop = next(p for p in prof.get("properties", []) if p["name"] == "textures")
        tex = json.loads(base64.b64decode(prop["value"]))
        return tex.get("textures", {}).get("SKIN", {}).get("url")
    except Exception:
        return None


def upload_skin(mc_token, png_path, variant="classic"):
    """Ставит PNG скином лицензионного аккаунта. Возвращает текст ошибки или None."""
    from pathlib import Path
    with open(Path(png_path), "rb") as f:
        r = session.put(MC_SKIN_URL,
                        headers={"Authorization": "Bearer " + mc_token},
                        data={"variant": variant},
                        files={"file": ("skin.png", f, "image/png")}, timeout=60)
    if r.status_code in (200, 204):
        return None
    try:
        msg = r.json().get("errorMessage", "")
    except Exception:
        msg = ""
    return f"Mojang ответил {r.status_code}: {msg or 'не удалось загрузить скин'}"
