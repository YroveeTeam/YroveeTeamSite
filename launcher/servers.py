"""Пинг серверов по протоколу Server List Ping (без сторонних библиотек)."""
import json
import re
import socket
import struct
import time


def _varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise IOError("соединение закрыто")
        buf += chunk
    return buf


def _read_varint(sock):
    result = 0
    for i in range(5):
        b = _recv_exact(sock, 1)[0]
        result |= (b & 0x7F) << (7 * i)
        if not b & 0x80:
            return result
    raise IOError("плохой varint")


def parse_address(address):
    address = address.strip()
    if ":" in address:
        host, _, port = address.rpartition(":")
        if port.isdigit():
            return host, int(port)
    return address, 25565


def _flatten_motd(desc):
    if isinstance(desc, str):
        text = desc
    elif isinstance(desc, dict):
        text = desc.get("text", "") + "".join(_flatten_motd(e) for e in desc.get("extra", []))
    elif isinstance(desc, list):
        text = "".join(_flatten_motd(e) for e in desc)
    else:
        text = ""
    return re.sub(r"§.", "", text)


def ping_server(address, timeout=4):
    """-> {online, max, motd, version, ping_ms, favicon(bytes|None)}; бросает исключение, если сервер недоступен."""
    host, port = parse_address(address)
    with socket.create_connection((host, port), timeout) as s:
        s.settimeout(timeout)
        h = host.encode("utf-8")
        handshake = b"\x00" + _varint(765) + _varint(len(h)) + h + struct.pack(">H", port) + _varint(1)
        s.sendall(_varint(len(handshake)) + handshake + b"\x01\x00")

        _read_varint(s)  # длина пакета
        _read_varint(s)  # id пакета
        size = _read_varint(s)
        data = json.loads(_recv_exact(s, size).decode("utf-8", errors="replace"))

        payload = b"\x01" + struct.pack(">q", int(time.time() * 1000))
        t0 = time.perf_counter()
        s.sendall(_varint(len(payload)) + payload)
        try:
            _read_varint(s)
            _recv_exact(s, 9)
            ping_ms = int((time.perf_counter() - t0) * 1000)
        except Exception:
            ping_ms = int((time.perf_counter() - t0) * 1000)

    favicon = None
    fav = data.get("favicon", "")
    if fav.startswith("data:image"):
        import base64
        try:
            favicon = base64.b64decode(fav.split(",", 1)[1])
        except Exception:
            favicon = None
    players = data.get("players", {})
    return {
        "online": players.get("online", 0),
        "max": players.get("max", 0),
        "motd": _flatten_motd(data.get("description", "")).strip(),
        "version": data.get("version", {}).get("name", ""),
        "ping_ms": ping_ms,
        "favicon": favicon,
    }
