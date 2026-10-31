# -*- coding: utf-8 -*-
"""Язык интерфейса: T("русская строка") -> перевод для выбранного языка.
Русский — язык ключей; EN dict содержит переводы. Непереведённое остаётся русским."""

_lang = "ru"

EN = {
    # сайдбар
    "Играть": "Play", "Магазин": "Shop", "Персонаж": "Character",
    "Моды и паки": "Mods & packs", "Сборки": "Modpacks", "Серверы": "Servers",
    "Миры": "Worlds", "Скриншоты": "Screenshots", "Лог игры": "Game log",
    "Статистика": "Stats", "Настройки": "Settings",
    # лобби
    "Играть": "Play",
    "🎁  Магазин": "🎁  Shop", "👤  Персонаж": "👤  Character",
    "🧱  Сборки": "🧱  Modpacks", "🌐  Серверы": "🌐  Servers",
    "Память": "Memory", "Загрузчик": "Loader", "Модов": "Mods",
    "Кристаллы": "Crystals", "Сборка": "Modpack",
    "Аккаунт": "Account", "Версия": "Version",
    "Выбрать версию   ▾": "Choose version   ▾",
    "▶ Запустить ещё одну": "▶ Launch another one",
    "Игра запущена": "Game running",
    "🎁 Забрать сундук": "🎁 Claim chest",
    "🎮 Konami code! Секретные +100 💎 за смекалку": "🎮 Konami code! Secret +100 💎",
    # страницы: заголовки
    "Магазин": "Shop",
    "Кристаллы за игру, сундуки и косметика — всё честно, без доната":
        "Crystals for playtime, chests and cosmetics — fair, no donations",
    "Персонаж": "Character",
    "Твой скин и косметика: крути мышкой. Плащ, голова и лицо видны в игре":
        "Your skin & cosmetics: drag to rotate. Cape, hat and face show in game",
    "Сборки": "Modpacks",
    "У каждой сборки своя папка: моды, сохранения, ресурспаки":
        "Each modpack has its own folder: mods, saves, resource packs",
    "Серверы": "Servers",
    "Список любимых серверов с онлайном и пингом": "Favorite servers with online & ping",
    "Миры": "Worlds",
    "Сохранения из всех версий и сборок: копируй между версиями":
        "Saves from all versions: copy between them",
    "Скриншоты": "Screenshots", "Все скриншоты из всех папок игры": "All screenshots",
    "Лог игры": "Game log",
    "Здесь появляется всё, что пишет Minecraft во время запуска":
        "Everything Minecraft prints while running",
    "Статистика": "Stats", "Сколько ты играешь и во что": "How much and what you play",
    "Настройки": "Settings", "Память, Java и папка игры": "Memory, Java and game folder",
    "Моды и паки": "Mods & packs",
    # магазин
    "Сундуки": "Chests", "Бонусы": "Bonuses", "Сезон": "Season",
    "Задания": "Quests", "Коллекция": "Collection",
    "🎯 Предмет дня — скидка 50%": "🎯 Item of the day — 50% off",
    "Купить": "Buy", "✓ Уже есть": "✓ Owned",
    "🎁 Открыть дверцу": "🎁 Open the door",
    "Дверца открыта — завтра новая": "Door opened — new one tomorrow",
    "Забрать": "Claim", "Завтра": "Tomorrow",
    "Обменять": "Redeem", "Получить": "Get",
    "Надеть": "Equip", "Снять": "Unequip",
    "Применить в игре": "Apply in game",
    "Поставить на лицензию": "Set on licensed account",
    "Перед": "Front", "Бок": "Side", "Спина": "Back",
    "Спокойно": "Idle", "👋 Привет": "👋 Wave",
    "Экспорт .mrpack": "Export .mrpack", "Убрать": "Remove",
    "Папка": "Folder", "Из файла": "From file",
    "🪄 Собрать за меня": "🪄 Build for me",
    "Проверить обновления": "Check updates",
    "⚡ Оптимизировать": "⚡ Optimize",
    "Поиск": "Search", "Установленные": "Installed",
    "Найти": "Search",
    "Обновить": "Refresh", "Открыть папку": "Open folder",
    "Очистить": "Clear", "Копировать всё": "Copy all",
    "💾 Сохранить картинку": "💾 Save image",
    "Время в игре — последние 14 дней": "Playtime — last 14 days",
    "Всего в игре": "Total played", "Запусков": "Launches",
    "Любимая версия": "Favorite version",
    # настройки: часто
    "Оформление": "Appearance", "Тёмная тема": "Dark theme", "Светлая тема": "Light theme",
    "Цветовой акцент": "Accent color", "🎨 Свой цвет": "🎨 Custom color",
    "Язык интерфейса": "Interface language",
    "Поведение": "Behavior",
    "Экспериментальные функции": "Experimental features",
    "Рендер графики": "Graphics renderer",
    "Обслуживание игры": "Game maintenance",
    "Файлы игры: сохранения, моды, options.txt": "Game files: saves, mods, options.txt",
    "Открыть папку игры": "Open game folder",
    "Починить файлы игры": "Repair game files",
    "Сделать бэкап сейчас": "Back up now",
    "Восстановить из бэкапа": "Restore backup",
    "Перенести из .minecraft": "Import from .minecraft",
    "Импорт из папки": "Import from folder",
    "Обновление лаунчера": "Launcher updates",
    "Сообщить о баге (создать вопрос на GitHub)": "Report a bug (open a GitHub issue)",
    "Перезапустить лаунчер": "Restart launcher",
    "Понятно": "Got it",
    "Играть с файлами": "Play with files",
}


def set_lang(lang):
    global _lang
    _lang = lang if lang in ("ru", "en") else "ru"


def get_lang():
    return _lang


def T(s):
    if _lang == "en":
        return EN.get(s, s)
    return s
