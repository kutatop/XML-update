#!/usr/bin/env python3
"""
Скачивает исходный YML/XML-фид, исключает офферы, относящиеся
(прямо или через вложенные категории) к категориям из EXCLUDED_CATEGORIES,
и сохраняет результат в output/filtered_feed.xml.
"""

import re
import sys
import time
import urllib.request

SOURCE_URL = "https://knigovan.com/price/exportPrice.xml"
OUTPUT_PATH = "output/filtered_feed.xml"

# ID категорий, которые нужно ИСКЛЮЧИТЬ (вместе со всеми их подкатегориями)
EXCLUDED_CATEGORIES = {
    "36", "34", "143", "144", "145", "122", "123", "124", "125", "126",
    "127", "128", "130", "131", "134", "132", "133", "103", "104", "105",
    "120", "91", "92", "93", "94", "95", "118", "119", "96", "97", "98",
    "99", "100", "101", "106", "109", "111", "110", "108", "107", "112",
    "113", "114", "115", "116", "117", "77", "89", "82", "83", "84", "85",
    "86", "87", "88", "78", "79", "80", "81", "152", "168", "158", "159",
    "160", "161", "163", "162", "153", "155", "156", "154", "157", "169",
    "164", "165", "166", "167", "173", "174", "175", "176", "177", "178",
    "146", "148", "151", "147", "149", "150", "170", "172", "171",
}


def fetch_source(url: str, attempts: int = 4, delay_seconds: int = 8) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6",
        "Accept-Encoding": "identity",  # без gzip, чтобы не усложнять декодирование
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "no-cache",
        "Referer": "https://knigovan.com/",
    }

    last_content = ""
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            last_content = resp.read().decode("utf-8", errors="replace")

        # Признак JS-заглушки антибот-защиты
        if "One moment, please" in last_content or len(last_content) < 1_000_000:
            print(
                f"Попытка {attempt}/{attempts}: получена заглушка/маленький ответ "
                f"({len(last_content)} байт). Жду {delay_seconds} сек. и пробую снова..."
            )
            if attempt < attempts:
                time.sleep(delay_seconds)
                continue
        else:
            return last_content

    return last_content


def parse_categories(content: str):
    """Возвращает dict: cid -> parentId (или None)."""
    pattern = re.compile(r'<category id="(\d+)"\s*(?:parentId="(\d+)")?\s*>')
    parent_of = {}
    for m in pattern.finditer(content):
        cid, pid = m.group(1), m.group(2)
        parent_of[cid] = pid
    return parent_of


def build_is_excluded(parent_of: dict, excluded_roots: set):
    cache = {}

    def is_excluded(cid: str) -> bool:
        if cid in cache:
            return cache[cid]
        cur = cid
        seen = set()
        result = False
        while cur is not None and cur not in seen:
            seen.add(cur)
            if cur in excluded_roots:
                result = True
                break
            cur = parent_of.get(cur)
        cache[cid] = result
        return result

    return is_excluded


def filter_offers(content: str, is_excluded) -> tuple[str, int, int, int]:
    """Удаляет из content блоки <offer>...</offer>, чья categoryId исключена.
    У оставшихся офферов, если есть тег <oldprice>, заменяет <price> на
    значение из <oldprice> (т.е. убирает скидку, возвращая полную цену)
    и удаляет сам тег <oldprice>.
    Возвращает (новый_content, оставлено, удалено_по_категории, скидок_убрано).
    """
    offer_pattern = re.compile(r"<offer\b.*?</offer>", re.DOTALL)
    price_pattern = re.compile(r"<price>\d+(?:\.\d+)?</price>")
    oldprice_pattern = re.compile(r"<oldprice>(\d+(?:\.\d+)?)</oldprice>")

    kept = 0
    removed_category = 0
    discounts_removed = 0

    def repl(match: re.Match) -> str:
        nonlocal kept, removed_category, discounts_removed
        block = match.group(0)

        cat_match = re.search(r"<categoryId>(\d+)</categoryId>", block)
        if cat_match and is_excluded(cat_match.group(1)):
            removed_category += 1
            return ""

        old_match = oldprice_pattern.search(block)
        if old_match:
            old_value = old_match.group(1)
            block = price_pattern.sub(f"<price>{old_value}</price>", block, count=1)
            block = oldprice_pattern.sub("", block, count=1)
            discounts_removed += 1

        kept += 1
        return block

    new_content = offer_pattern.sub(repl, content)
    return new_content, kept, removed_category, discounts_removed


def main():
    print(f"Скачиваю фид: {SOURCE_URL}")
    content = fetch_source(SOURCE_URL)
    print(f"Скачано {len(content)} байт")

    if len(content) < 1_000_000:
        print("ВНИМАНИЕ: файл подозрительно маленький, возможно это не фид, а страница ошибки.")
        print("Первые 1000 символов ответа:")
        print(content[:1000])

    parent_of = parse_categories(content)
    print(f"Найдено категорий: {len(parent_of)}")

    is_excluded = build_is_excluded(parent_of, EXCLUDED_CATEGORIES)

    new_content, kept, removed_category, discounts_removed = filter_offers(content, is_excluded)
    print(f"Оставлено офферов: {kept}")
    print(f"Удалено по категории: {removed_category}")
    print(f"Скидок убрано (price <- oldprice): {discounts_removed}")

    import os
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"Сохранено в {OUTPUT_PATH}")

    if kept == 0:
        print("ОШИБКА: ни одного оффера не осталось — что-то не так", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
