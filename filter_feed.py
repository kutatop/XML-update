#!/usr/bin/env python3
"""
Скачивает исходный YML/XML-фид, исключает офферы, относящиеся
(прямо или через вложенные категории) к категориям из EXCLUDED_CATEGORIES,
и сохраняет результат в output/filtered_feed.xml.
"""

import re
import sys
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


def fetch_source(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


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


def filter_offers(content: str, is_excluded) -> tuple[str, int, int]:
    """Удаляет из content блоки <offer>...</offer>, чья categoryId исключена.
    Возвращает (новый_content, оставлено, удалено).
    """
    offer_pattern = re.compile(r"<offer\b.*?</offer>", re.DOTALL)

    kept = 0
    removed = 0

    def repl(match: re.Match) -> str:
        nonlocal kept, removed
        block = match.group(0)
        cat_match = re.search(r"<categoryId>(\d+)</categoryId>", block)
        if cat_match and is_excluded(cat_match.group(1)):
            removed += 1
            return ""
        kept += 1
        return block

    new_content = offer_pattern.sub(repl, content)
    return new_content, kept, removed


def main():
    print(f"Скачиваю фид: {SOURCE_URL}")
    content = fetch_source(SOURCE_URL)
    print(f"Скачано {len(content)} байт")

    parent_of = parse_categories(content)
    print(f"Найдено категорий: {len(parent_of)}")

    is_excluded = build_is_excluded(parent_of, EXCLUDED_CATEGORIES)

    new_content, kept, removed = filter_offers(content, is_excluded)
    print(f"Оставлено офферов: {kept}")
    print(f"Удалено офферов: {removed}")

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
