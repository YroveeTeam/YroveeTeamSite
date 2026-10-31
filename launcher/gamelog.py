"""Лог игры: сохранение в файл и подсказки, что делать при краше."""
import re
from datetime import datetime

from config import LOGS_DIR

# (шаблон в логе, подсказка). Единственный источник подсказок о крашах.
RULES = [
    (r"UnsupportedClassVersionError|has been compiled by a more recent version of the Java|"
     r"requires Java|class file version",
     "Не подходит версия Java. Оставь поле «Java» в Настройках пустым — лаунчер подберёт "
     "и скачает нужную сам."),
    (r"OutOfMemoryError|GC overhead limit exceeded",
     "Игре не хватило памяти. Увеличь «Оперативную память» в Настройках "
     "(и не ставь больше ~75% от всей RAM) или убери тяжёлые моды."),
    (r"Could not reserve enough space|Invalid maximum heap size|"
     r"Could not create the Java Virtual Machine|Unrecognized VM option",
     "Java не приняла один из аргументов или не смогла выделить память. В Настройках выбери "
     "профиль «Стандарт», очисти «Дополнительные аргументы JVM» и проверь ползунок ОЗУ."),
    (r"Incompatible mod set|Mod resolution failed|Could not find required mod|"
     r"requires (?:any )?version|Mod .* requires|Missing or unsupported mandatory dependencies",
     "Какому-то моду не хватает другого мода или подходящей версии (часто это Fabric API). "
     "Открой «Моды → Установленные → Проверить обновления» и поставь недостающее."),
    (r"Mixin apply failed|MixinApplyError|InvalidInjectionException|InvalidMixinException|"
     r"Mixin transformation|MixinTransformerError",
     "Моды конфликтуют между собой или мод сделан не под эту версию игры. "
     "Удали последний установленный мод и попробуй снова."),
    (r"NoSuchMethodError|NoSuchFieldError|ClassNotFoundException|NoClassDefFoundError",
     "Мод не подходит к этой версии игры или к другому моду. "
     "Проверь версии модов, удали недавно добавленные."),
    (r"GLFW error|OpenGL|pixel format not accelerated|WGL|GLX",
     "Проблема с видеокартой или её драйвером. Обнови драйвер видеокарты; "
     "на ноутбуке запускай игру на дискретной видеокарте."),
    (r"Failed to download|UnknownHostException|Connection timed out|SSLHandshakeException",
     "Проблема с сетью при загрузке файлов. Проверь интернет и запусти ещё раз — "
     "докачается недостающее."),
    (r"Exception in thread \"main\"|Failed to start game",
     "Игра не смогла стартовать. Посмотри последние строки лога и попробуй запустить "
     "ещё раз; если не помогло — скопируй лог и обратись к тому, кто разбирается."),
]

GENERIC = ("Игра завершилась с ошибкой. Посмотри последние строки лога; полный отчёт лежит "
           "в папке crash-reports. Нажми «Копировать всё» и отправь текст тому, кто разбирается.")


def crash_hint(text):
    """Первая подходящая подсказка по тексту лога (как раньше в pages_extra)."""
    for pattern, hint in RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return hint
    return GENERIC


def analyze(lines):
    """Список подсказок (максимум 4) по строкам лога."""
    text = "\n".join(lines)
    hints = []
    for pattern, hint in RULES:
        if re.search(pattern, text, re.IGNORECASE):
            hints.append(hint)
        if len(hints) >= 4:
            break
    if not hints:
        hints.append(GENERIC)
    return hints


class LogWriter:
    """Пишет вывод игры в data/logs/game_<дата>.log, оставляя последние 20 файлов."""

    def __init__(self):
        self._f = None

    def start(self):
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self._f = open(LOGS_DIR / f"game_{stamp}.log", "w", encoding="utf-8", errors="replace")
            files = sorted(LOGS_DIR.glob("game_*.log"))
            for old in files[:-20]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except Exception:
            self._f = None
        return self

    def write(self, line):
        if self._f is None:
            return
        try:
            self._f.write(line)
            self._f.flush()
        except Exception:
            pass

    def close(self):
        if self._f is not None:
            try:
                self._f.close()
            except Exception:
                pass
            self._f = None
