"""Одно-клик сборка: build_exe.bat запускает этот скрипт, дальше всё само.

Что делает: окружение .venv-build → зависимости → PyInstaller → zip →
установщик через Inno Setup (если он стоит). Результат — в dist_out.
"""
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv-build"
VPY = VENV / "Scripts" / "python.exe"
DIST = ROOT / "dist" / "YroveeLauncher"
OUT = ROOT / "dist_out"

INNO_PATHS = [
    Path(r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 7\ISCC.exe"),
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]
if os.environ.get("LOCALAPPDATA"):  # установка «только для меня»
    INNO_PATHS.append(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Inno Setup 7" / "ISCC.exe")
    INNO_PATHS.append(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Inno Setup 6" / "ISCC.exe")


def run(cmd, **kw):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=str(ROOT), **kw)


def main():
    print("=== Сборка YroveeLauncher ===", flush=True)

    if not VPY.exists():
        print("[1/6] Создаю окружение сборки (один раз)...", flush=True)
        run([sys.executable, "-m", "venv", VENV])
    else:
        print("[1/6] Окружение сборки уже есть.", flush=True)

    print("[2/6] Ставлю зависимости...", flush=True)
    run([VPY, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    run([VPY, "-m", "pip", "install", "--quiet", "-r", "requirements.txt", "pyinstaller"])

    text = (ROOT / "config.py").read_text(encoding="utf-8")
    m = re.search(r'LAUNCHER_VERSION = "([^"]+)"', text)
    version = m.group(1) if m else "0.0"
    print(f"[3/6] Версия: {version}", flush=True)

    print("[4/6] Собираю exe (2-5 минут, не закрывай)...", flush=True)
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    run([VPY, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
         "--name", "YroveeLauncher", "--icon", "assets/icon.ico",
         "--collect-data", "customtkinter", "--collect-submodules", "pystray",
         "--hidden-import", "pypresence",
         "main.py"])

    print("[5/6] Упаковываю zip...", flush=True)
    OUT.mkdir(exist_ok=True)
    zpath = OUT / "YroveeLauncher-win64.zip"
    zpath.unlink(missing_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in DIST.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(DIST.parent))

    setup = OUT / "YroveeLauncher-Setup.exe"
    setup.unlink(missing_ok=True)
    iscc = next((p for p in INNO_PATHS if p.exists()), None)
    if iscc:
        print("[6/6] Собираю установщик (Inno Setup)...", flush=True)
        iss = ROOT / "installer.iss"
        iss.write_text(
            re.sub(r"AppVersion=.*", f"AppVersion={version}",
                   iss.read_text(encoding="utf-8-sig")),
            encoding="utf-8")
        run([iscc, str(iss)])
        produced = ROOT / "installer" / "YroveeLauncher-Setup.exe"
        if produced.exists():
            shutil.copyfile(produced, setup)
    else:
        print("[6/6] Inno Setup не найден — установщик не собран (zip есть).",
              flush=True)
        print("       Поставь с jrsoftware.org/isdl.php и запусти снова — будет Setup.exe.",
              flush=True)

    print()
    print("=== ГОТОВО. Файлы для выкладки — в папке dist_out:", flush=True)
    for f in sorted(OUT.glob("*")):
        print(f"   {f.name}  ({f.stat().st_size / 1024 / 1024:.1f} МБ)", flush=True)
    print("Дальше — инструкция GITHUB.md (GitHub Releases + сайт).", flush=True)
    os.startfile(str(OUT))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"ОШИБКА СБОРКИ (код {e.returncode}) — смотри текст выше.", flush=True)
        sys.exit(1)
