"""Оптимизация игры: профили JVM, подбор памяти и набор модов-ускорителей."""

# Флаги против фризов при очистке памяти: короткие паузы G1 (по мотивам
# флагов Aikar) + память выделяется сразу целиком (-Xms = -Xmx + AlwaysPreTouch),
# чтобы Java не расширяла кучу на лету — именно такие расширения дают резкие
# подлагивания при сборке мусора.
_G1 = ["-XX:+UnlockExperimentalVMOptions", "-XX:+UseG1GC",
       "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40",
       "-XX:MaxGCPauseMillis=50", "-XX:G1HeapRegionSize=16M",
       "-XX:G1ReservePercent=20", "-XX:G1MixedGCCountTarget=4",
       "-XX:InitiatingHeapOccupancyPercent=15",
       "-XX:+ParallelRefProcEnabled", "-XX:+DisableExplicitGC",
       "-XX:AlwaysPreTouch"]

PRESETS = {
    "Стандарт": ("Без дополнительных флагов — как у обычного лаунчера.", []),
    "Баланс": ("Короткие паузы сборщика мусора: меньше фризов при очистке памяти. "
               "Память выделяется сразу целиком, куча не растёт на лету.",
               _G1 + ["-Xms{ram}M"]),
    "Макс. FPS": ("То же, что «Баланс»: основной прирост FPS даёт кнопка "
                  "«Оптимизировать» на вкладке модов.",
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
