# -*- coding: utf-8 -*-
"""обработка_ительменского_словаря.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1JlY239NDLs57W1Tl8SXu1VdkWGeQGEqH
"""

!pip install PyPDF2

!pip3 install pdfminer.six

import re
import pandas as pd
from pdfminer.high_level import extract_text

#########################
# 1) Извлечение текста и очистка от служебных строк
#########################
file_path = "/content/Володин и др._2021_Полный ительменско-русский словарь (1)-397-488.pdf"
text = extract_text(file_path)

clean_lines = []
for line in text.split("\n"):
    stripped = line.strip()

    # Пустая строка
    if not stripped:
        clean_lines.append("")
        continue

    # Удаляем номера страниц (четные, 398..488)
    if re.match(r"^\d+$", stripped):
        num = int(stripped)
        if 398 <= num <= 488 and num % 2 == 0:
            continue  # Пропускаем

    # Удаляем строки вида "русско-ительменский индекс 398"
    if re.search(r"русско-ительменский индекс\s+\d+", stripped, re.IGNORECASE):
        continue

    clean_lines.append(stripped)

clean_text = "\n".join(clean_lines)

#########################
# 2) Определяем теги и функции вспомогательные
#########################
pos_tags = {
    "сущ", "мест", "п1", "п2", "неп", "нареч", "прил", "межд",
    "собств", "инф", "с.", "союз", "предл", "част", "числ", "А"
}

def strip_semicolon(token: str) -> str:
    return token.rstrip(";")

def is_new_russian_line(line: str) -> bool:
    """
    Определяем, является ли строка началом новой записи (русское слово).
    - строка не пуста, не начинается с пробела
    - первое слово (без ";") не тег
    - второе слово (без ";") не тег, если есть
    """
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(" "):
        return False

    words = stripped.split()
    first_word = strip_semicolon(words[0])
    if first_word in pos_tags:
        return False

    if len(words) == 1:
        return True

    second_word = strip_semicolon(words[1])
    if second_word in pos_tags:
        return False

    return True

#########################
# 3) Объединяем многострочные записи в блоки
#########################
lines = clean_text.split("\n")
blocks = []
current_block = []

for line in lines:
    stripped = line.strip()
    if not stripped:
        current_block.append("")
        continue

    if is_new_russian_line(stripped):
        # Начинается новый блок
        if current_block:
            block_text = "\n".join(current_block).strip()
            if block_text:
                blocks.append(block_text)
        current_block = [stripped]
    else:
        # Продолжение предыдущего блока
        current_block.append(stripped)

if current_block:
    block_text = "\n".join(current_block).strip()
    if block_text:
        blocks.append(block_text)

#########################
# 4) Парсим блоки в DataFrame
#########################
data = []

def process_block(block: str):
    """
    Ищем границу (i), где token[i+1] ∈ pos_tags => (русское / ительменское).
    """
    tokens = block.split()
    if not tokens:
        return
    boundary = None
    for i in range(len(tokens) - 1):
        nxt = strip_semicolon(tokens[i+1])
        if nxt in pos_tags:
            boundary = i
            break

    if boundary is None:
        return

    russian_part = tokens[:boundary]
    itelmen_part_tokens = tokens[boundary:]
    itelmen_str = " ".join(itelmen_part_tokens)

    if ";" in itelmen_str:
        pos_value = "multiple translations"
    else:
        if len(itelmen_part_tokens) > 1:
            pos_value = strip_semicolon(itelmen_part_tokens[1])
        else:
            pos_value = ""

    if russian_part and itelmen_part_tokens:
        data.append([
            " ".join(russian_part),
            itelmen_str,
            pos_value
        ])

for block in blocks:
    process_block(block)

df = pd.DataFrame(data, columns=["Русское слово", "Ительменское слово", "Часть речи"])

#########################
# 5) Функция переноса ительменских токенов из "Русского слова" (кроме первого)
#    если они содержат ительменские символы
#########################
itelmen_chars = r"[ʼӄӈӼӽӃӇʔ˚ӑӘәЉљԒԓŎŏЊњЎў]"
def is_itelmen_word(word: str) -> bool:
    return bool(re.search(itelmen_chars, word))

def fix_itelmen_in_russian_skip_first(df: pd.DataFrame) -> pd.DataFrame:
    new_russian_col = []
    new_itelmen_col = []

    for idx, row in df.iterrows():
        russian_text = row["Русское слово"]
        itelmen_text = row["Ительменское слово"]

        russian_tokens = russian_text.split()
        itelmen_tokens = itelmen_text.split()

        keep_tokens = []
        moved_tokens = []

        if len(russian_tokens) > 0:
            # Оставляем первый токен как есть
            keep_tokens.append(russian_tokens[0])
            # Проверяем остальные
            for tok in russian_tokens[1:]:
                if is_itelmen_word(tok):
                    moved_tokens.append(tok)
                else:
                    keep_tokens.append(tok)

        new_russian = " ".join(keep_tokens).strip()
        new_itelmen = " ".join(moved_tokens + itelmen_tokens).strip()

        new_russian_col.append(new_russian)
        new_itelmen_col.append(new_itelmen)

    df["Русское слово"] = new_russian_col
    df["Ительменское слово"] = new_itelmen_col
    return df

df_fixed = fix_itelmen_in_russian_skip_first(df)

#########################
# 6) Удаляем теги из второго столбца, если Часть речи != multiple translations
#########################
def remove_tags_if_not_multiple(df: pd.DataFrame) -> pd.DataFrame:
    new_itelmen = []
    for i, row in df.iterrows():
        itelmen_text = row["Ительменское слово"]
        pos_value = row["Часть речи"]

        if pos_value != "multiple translations":
            tokens = itelmen_text.split()
            cleaned_tokens = []
            for token in tokens:
                stripped = token.rstrip(";")
                if stripped in pos_tags:
                    continue
                cleaned_tokens.append(token)
            new_itelmen.append(" ".join(cleaned_tokens))
        else:
            new_itelmen.append(itelmen_text)

    df["Ительменское слово"] = new_itelmen
    return df

df_fixed = remove_tags_if_not_multiple(df_fixed)

#########################
# 7) Транслитерируем ительменские слова во втором столбце
#    при этом не трогаем теги
#########################
def transliterate(text, reverse=True):
    mapping = {
        # Комбинации
        "ti": "ты", "li": "лы", "ni": "ны", "ɨ": "ы",
        # Согласные
        "p": "п",  "p'": "пʼ",
        "t": "т",  "t'": "тʼ",
        "k": "к",  "k'": "кʼ",
        "q": "ӄ",  "q'": "ӄʼ",
        "č": "ч",  "č'": "чʼ",
        "f": "ф",  "s": "с",
        "x": "х",  "χ": "ӽ",
        "w": "в",  "z": "з",
        "j": "й",  "g": "г",
        "ɬ": "ԓ",  "l": "л",
        "ʎ": "љ",  "r": "р",
        "m": "м",  "n": "н",
        "ɲ": "њ",  "ŋ": "ӈ",
        "ʔ": "ʔ",  "d": "д",
        "b":"б",   "ʂ":"ш",
        "ɕː":"щ", "ʐ":"ж",
        "t͡s":"ц",
        # Гласные
        "i": "и", "u": "у", "e": "е", "o": "о", "a": "а", "ə": "ә", "e":"э",
        # Особые символы
        "'": "ь",  "ʷ": "˚", "ŭ": "ў", "ŏ": "ŏ", "ǎ": "ǎ",
    }
    if reverse:
        mapping = {v: k for k, v in mapping.items()}
    sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
    result = text
    for src in sorted_keys:
        tgt = mapping[src]
        result = result.replace(src, tgt)
    return result

def transliterate_itelmen_words(df: pd.DataFrame) -> pd.DataFrame:
    new_itelmen_column = []
    for i, row in df.iterrows():
        itelmen_text = row["Ительменское слово"]
        tokens = itelmen_text.split()
        converted_tokens = []
        for tok in tokens:
            stripped = tok.rstrip(";")
            if stripped in pos_tags:
                # Тег не трогаем
                converted_tokens.append(tok)
            else:
                # Иначе транслитерируем
                converted = transliterate(tok, reverse=True)
                converted_tokens.append(converted)
        new_itelmen_column.append(" ".join(converted_tokens))
    df_new = df.copy()
    df_new["Ительменское слово"] = new_itelmen_column
    return df_new

df_converted = transliterate_itelmen_words(df_fixed)

#########################
# 8) Сохраняем русско-ительменский итог
#########################
# Удаляем "s." из второго столбца df_converted
df_converted["Ительменское слово"] = (
    df_converted["Ительменское слово"]
    .str.replace(r"\bs\.\b", "", regex=True)
    .str.replace("s.", "")
    .str.strip()
)
df_converted.to_csv("russian_itelmen_dictionary_transliterated_no_s.csv", index=False)

#########################
# 9) Инвертируем DataFrame -> ительменско-русский
#########################
def invert_dictionary(df: pd.DataFrame) -> pd.DataFrame:
    new_rows = []
    for i, row in df.iterrows():
        rus_word = row["Русское слово"]
        itelmen_text = row["Ительменское слово"]
        base_pos = row["Часть речи"]

        parts = itelmen_text.split(";")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            tokens = part.split()
            if not tokens:
                continue

            found_tags = []
            while tokens:
                last = tokens[-1].rstrip(".;")
                if last in pos_tags:
                    found_tags.append(tokens.pop())
                else:
                    break

            itelmen_word = " ".join(tokens).strip()
            if found_tags:
                found_tags.reverse()
                pos_str = " ".join(found_tags)
            else:
                pos_str = ""

            if base_pos and base_pos != pos_str:
                if not pos_str:
                    pos_str = base_pos
                else:
                    pos_str = pos_str + " " + base_pos

            new_rows.append([itelmen_word, rus_word, pos_str])

    df_new = pd.DataFrame(new_rows, columns=["Ительменское слово", "Русское слово", "Часть речи"])
    return df_new

df_inverted = invert_dictionary(df_converted)
df_inverted.to_csv("itelmen_russian_dictionary.csv", index=False)

#########################
# 10) Удаляем "s." из ПЕРВОГО столбца df_inverted
#########################
df_inverted["Ительменское слово"] = (
    df_inverted["Ительменское слово"]
    .str.replace(r"\bs\.\b", "", regex=True)
    .str.replace("s.", "")
    .str.strip()
)

#########################
# 11) Удаляем "multiple translations" из третьего столбца df_inverted
#########################
df_inverted["Часть речи"] = (
    df_inverted["Часть речи"]
    .str.replace("multiple translations", "", regex=False)
    .str.strip()
)

#########################
# Сохраняем финальный ительменско-русский результат
#########################
df_inverted.to_csv("itelmen_russian_dictionary_no_multiple.csv", index=False)
