"""Оптимизация игры: профили JVM, подбор памяти и набор модов-ускорителей."""

_G1 = ["-XX:+UnlockExperimentalVMOptions", "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled",
       "-XX:MaxGCPauseMillis=130", "-XX:G1NewSizePercent=30", "-XX:G1ReservePercent=20",
       "-XX:+DisableExplicitGC"]

PRESETS = {
    "Стандарт": ("Без дополнительных флагов — как у обычного лаунчера.", []),
    "Баланс": ("Сборщик мусора G1 с короткими паузами: меньше подлагиваний при загрузке чанков.", _G1),
    "Макс. FPS": ("Как «Баланс», но память выделяется сразу целиком: кучу не нужно расширять на лету. "
                  "Основной прирост FPS даёт кнопка «Оптимизировать» на вкладке модов.",
                  _G1 + ["-Xms{ram}M"]),
    "Слабый ПК": ("Лёгкий сборщик мусора для компьютеров с 2–4 ядрами. Не ставь много памяти.",
                  ["-XX:+UseSerialGC", "-XX:+DisableExplicitGC"]),
}

# slug на Modrinth -> название
OPT_MODS = {
    "fabric": [("sodium", "Sodium"), ("lithium", "Lithium"), ("ferritecore", "FerriteCore"),
               ("modernfix", "ModernFix"), ("immediatelyfast", "ImmediatelyFast"),
               ("entityculling", "Entity Culling")],
    "forge": [("embeddium", "Embeddium"), ("ferritecore", "FerriteCore"), ("modernfix", "ModernFix"),
              ("immediatelyfast", "ImmediatelyFast"), ("entityculling", "Entity Culling")],
}


def preset_args(name, ram_mb):
    flags = PRESETS.get(name, PRESETS["Стандарт"])[1]
    return " ".join(f.format(ram=int(ram_mb)) for f in flags)


def recommended_ram(total_mb):
    """Около 45% оперативки, но от 2 до 8 ГБ: больше игре обычно только вредит (паузы GC)."""
    mb = int(total_mb * 0.45) // 512 * 512
    return max(2048, min(8192, mb))
