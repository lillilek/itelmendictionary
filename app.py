import os
import re
import unicodedata
from collections import Counter
from datetime import date

import pandas as pd
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

WEST_DICTIONARY_FILE = "west_itelmen_dictionary.csv"
AFFIX_FILE = "affixes_transliterated.csv"
QUERY_LOG_FILE = "query_log.csv"
PAGE_SIZE = 50

ITELMEN_SEARCH_FIELDS = [
    ("word", "слово"),
    ("phonetic_variant", "фонетический вариант"),
    ("northern_variant", "северный диалектный вариант"),
    ("infinitive", "инфинитив"),
    ("plural", "множественное число"),
    ("common_number", "общее число"),
]
FORM_FIELD_PRIORITY = {field: index for index, (field, _) in enumerate(ITELMEN_SEARCH_FIELDS)}
FORM_FIELD_PRIORITY["see_also"] = len(FORM_FIELD_PRIORITY)
DOMAIN_PRIORITY = {"forms": 0, "senses": 1}
LANGUAGE_PRIORITY = {"itelmen": 0, "russian": 1}
SEARCH_LANGUAGE_OPTIONS = [
    {"value": "itelmen", "label": "Ительменский"},
    {"value": "russian", "label": "Русский"},
]
SEARCH_DOMAIN_OPTIONS = [
    {"value": "forms", "label": "Словоформы"},
    {"value": "senses", "label": "Толкования"},
]

VERB_MARKERS = ("переходный1", "переходный2", "непереходный")
GRAMMAR_FIXES = {
    "неперходный": "непереходный",
    "непреходный": "непереходный",
    "-": "",
}
PART_OF_SPEECH_FIXES = {
    "глагол ": "глагол",
    "имя собственное ": "имя собственное",
    "прилагательной": "прилагательное",
}
PART_OF_SPEECH_ORDER = [
    "существительное",
    "глагол",
    "прилагательное",
    "наречие",
    "местоимение",
    "междометие",
    "союз",
    "частица",
    "числительное",
    "имя собственное",
    "предлог",
]
FEATURE_LABELS = [
    "есть фонетический вариант",
    "есть северный вариант",
    "есть инфинитив",
    "есть множественное число",
    "есть общее число",
]
LABEL_GROUP_DEFINITIONS = [
    {
        "key": "grammar",
        "title": "Грамматические пометы",
        "order": ["непереходный", "переходный1", "переходный2"],
    },
    {
        "key": "dialects",
        "title": "Диалекты",
        "order": ["северный диалект", "западный диалект"],
    },
    {
        "key": "features",
        "title": "Дополнительные признаки",
        "order": FEATURE_LABELS,
    },
]


def clean_value(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_csv_argument(value, default=None):
    if value is None:
        return list(default or [])
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def parse_int(value, default=1, minimum=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def transliterate_to_latin(text):
    text = clean_value(text).lower()
    text = re.sub(r"[ʹ'’]", "ʼ", text)
    mapping = {
        "ты": "ti",
        "лы": "li",
        "ны": "ni",
        "п": "p",
        "пʼ": "pʼ",
        "т": "t",
        "тʼ": "tʼ",
        "к": "k",
        "кʼ": "kʼ",
        "ӄ": "q",
        "ӄʼ": "qʼ",
        "ч": "č",
        "чʼ": "čʼ",
        "ф": "f",
        "с": "s",
        "х": "x",
        "ӽ": "χ",
        "в": "w",
        "з": "z",
        "й": "j",
        "г": "g",
        "ԓ": "ɬ",
        "л": "l",
        "љ": "ʎ",
        "р": "r",
        "м": "m",
        "н": "n",
        "њ": "ɲ",
        "ӈ": "ŋ",
        "ʔ": "ʔ",
        "д": "d",
        "б": "b",
        "ш": "ʂ",
        "щ": "ɕː",
        "ж": "ʐ",
        "ц": "t͡s",
        "и": "i",
        "у": "u",
        "е": "e",
        "о": "o",
        "а": "a",
        "ә": "ə",
        "э": "e",
        "ь": "ʼ",
        "˚": "ʷ",
        "ў": "ŭ",
        "ŏ": "ŏ",
        "ǎ": "ǎ",
        "ɣ": "ɣ",
        "ɣʼ": "ɣʼ",
    }

    result = []
    index = 0
    while index < len(text):
        if index + 2 <= len(text) and text[index : index + 2] in mapping:
            result.append(mapping[text[index : index + 2]])
            index += 2
            continue
        result.append(mapping.get(text[index], text[index]))
        index += 1
    return "".join(result)


def normalize_case(text, ignore_case):
    return text.lower() if ignore_case else text


def strip_unicode_diacritics(text):
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def simplify_itelmen_text(text):
    simplified = strip_unicode_diacritics(text)
    replacements = {
        "č": "c",
        "χ": "x",
        "ɬ": "l",
        "ʎ": "l",
        "ɲ": "n",
        "ŋ": "n",
        "ʂ": "s",
        "ʐ": "z",
        "ɕ": "s",
        "ə": "e",
        "ɨ": "y",
        "ŭ": "u",
        "ŏ": "o",
        "ǎ": "a",
        "ː": "",
        "ʼ": "",
        "'": "",
        "ʔ": "",
    }
    return "".join(replacements.get(char, char) for char in simplified)


def normalize_search_text(text, language, ignore_case=True, ignore_diacritics=True):
    value = clean_value(text).replace("=", "-")
    if language == "itelmen":
        value = transliterate_to_latin(value)
        if ignore_diacritics:
            value = simplify_itelmen_text(value)
    else:
        if ignore_diacritics:
            value = strip_unicode_diacritics(value)
    return normalize_case(value, ignore_case)


def normalize_part_of_speech(value):
    value = clean_value(value)
    return PART_OF_SPEECH_FIXES.get(value, value)


def normalize_grammar_note(value):
    value = clean_value(value)
    return GRAMMAR_FIXES.get(value, value)


def unique_nonempty(values):
    seen = set()
    result = []
    for value in values:
        cleaned = clean_value(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def split_grammar_labels(value):
    if not value:
        return []
    matches = []
    for marker in VERB_MARKERS:
        if marker in value:
            matches.append(marker)
    return matches


def build_entry_labels(entry):
    labels = []
    labels.extend(entry["verb_labels"])
    if entry["dialect"]:
        labels.append(entry["dialect"])
    if entry["grammar_note"]:
        labels.append(entry["grammar_note"])
    if entry["phonetic_variant"]:
        labels.append("есть фонетический вариант")
    if entry["northern_variant"]:
        labels.append("есть северный вариант")
    if entry["infinitive"]:
        labels.append("есть инфинитив")
    if entry["plural"]:
        labels.append("есть множественное число")
    if entry["common_number"]:
        labels.append("есть общее число")
    return unique_nonempty(labels)


def build_search_targets(entry):
    targets = []
    for field_name, _ in ITELMEN_SEARCH_FIELDS:
        value = entry[field_name]
        if value:
            targets.append(
                {
                    "domain": "forms",
                    "language": "itelmen",
                    "field": field_name,
                    "value": value,
                }
            )
    if entry["translation"]:
        targets.append(
            {
                "domain": "senses",
                "language": "russian",
                "field": "translation",
                "value": entry["translation"],
            }
        )
    return targets


def load_dictionary_entries():
    df = pd.read_csv(WEST_DICTIONARY_FILE, dtype=str).fillna("")
    df = df.apply(lambda column: column.map(clean_value))
    link_columns = ["ссылка"] + [column for column in df.columns if column.startswith("Unnamed:")]

    entries = []
    for index, row in df.iterrows():
        part_of_speech = normalize_part_of_speech(row["часть речи"])
        grammar_note = normalize_grammar_note(row["грамматические пометы"])
        verb_labels = split_grammar_labels(grammar_note)

        entry = {
            "id": index,
            "word": row["слово"],
            "translation": row["толкование"],
            "part_of_speech": part_of_speech,
            "dialect": row["диалект"],
            "phonetic_variant": row["фонетический вариант"],
            "northern_variant": row["северный диалектный вариант"],
            "verb_labels": verb_labels,
            "grammar_note": grammar_note if grammar_note and not verb_labels else "",
            "infinitive": row["инфинитив"],
            "plural": row["множественное число"],
            "common_number": row["общее число"],
            "see_also": unique_nonempty([row[column] for column in link_columns if column in row]),
        }
        entry["labels"] = build_entry_labels(entry)
        entry["search_targets"] = build_search_targets(entry)
        entries.append(entry)

    return entries


dictionary_entries = load_dictionary_entries()
affix_df = pd.read_csv(AFFIX_FILE, dtype=str, quotechar='"', engine="python").fillna("")
affix_df = affix_df.apply(lambda column: column.map(clean_value))
affix_dict = dict(zip(affix_df["Аффикс"], affix_df["Описание"]))


def build_ordered_options(counts, preferred_order):
    options = []
    seen = set()

    for value in preferred_order:
        if counts.get(value):
            options.append({"value": value, "count": counts[value]})
            seen.add(value)

    for value in sorted(counts):
        if value in seen or not counts[value]:
            continue
        options.append({"value": value, "count": counts[value]})

    return options


def build_search_filters(entries):
    part_counts = Counter(entry["part_of_speech"] for entry in entries if entry["part_of_speech"])
    label_counts = Counter(label for entry in entries for label in entry["labels"])

    used_labels = set()
    label_groups = []
    for group in LABEL_GROUP_DEFINITIONS:
        options = []
        for label in group["order"]:
            if label_counts.get(label):
                options.append({"value": label, "count": label_counts[label]})
                used_labels.add(label)
        if options:
            label_groups.append({"key": group["key"], "title": group["title"], "options": options})

    remaining_labels = {
        label: count for label, count in label_counts.items() if label not in used_labels and count
    }
    if remaining_labels:
        label_groups.append(
            {
                "key": "other",
                "title": "Прочие пометы",
                "options": build_ordered_options(remaining_labels, []),
            }
        )

    return {
        "languages": SEARCH_LANGUAGE_OPTIONS,
        "domains": SEARCH_DOMAIN_OPTIONS,
        "parts_of_speech": build_ordered_options(part_counts, PART_OF_SPEECH_ORDER),
        "label_groups": label_groups,
        "defaults": {
            "languages": ["itelmen", "russian"],
            "domains": ["forms", "senses"],
            "ignore_case": True,
            "ignore_diacritics": True,
            "whole_word": False,
        },
    }


SEARCH_FILTERS = build_search_filters(dictionary_entries)


def serialize_entry(entry):
    return {
        "id": entry["id"],
        "word": entry["word"],
        "translation": entry["translation"],
        "part_of_speech": entry["part_of_speech"],
        "dialect": entry["dialect"],
        "phonetic_variant": entry["phonetic_variant"],
        "northern_variant": entry["northern_variant"],
        "verb_labels": entry["verb_labels"],
        "grammar_note": entry["grammar_note"],
        "infinitive": entry["infinitive"],
        "plural": entry["plural"],
        "common_number": entry["common_number"],
        "see_also": entry["see_also"],
        "labels": entry["labels"],
    }


def entry_sort_key(entry):
    return (
        entry["word"].lower(),
        entry["translation"].lower(),
        entry["part_of_speech"].lower(),
    )


def rank_entry_match(
    entry,
    query,
    languages,
    domains,
    whole_word=False,
    ignore_case=True,
    ignore_diacritics=True,
):
    best_score = None

    for target in entry["search_targets"]:
        if target["language"] not in languages or target["domain"] not in domains:
            continue

        query_normalized = normalize_search_text(
            query,
            target["language"],
            ignore_case=ignore_case,
            ignore_diacritics=ignore_diacritics,
        )
        target_normalized = normalize_search_text(
            target["value"],
            target["language"],
            ignore_case=ignore_case,
            ignore_diacritics=ignore_diacritics,
        )
        if not query_normalized or not target_normalized:
            continue

        field_priority = FORM_FIELD_PRIORITY.get(target["field"], 0)
        score_base = (
            DOMAIN_PRIORITY.get(target["domain"], 99),
            LANGUAGE_PRIORITY.get(target["language"], 99),
            field_priority,
            len(target_normalized),
        )

        if whole_word:
            if query_normalized != target_normalized:
                continue
            score = (0,) + score_base
        else:
            if query_normalized == target_normalized:
                score = (0,) + score_base
            elif target_normalized.startswith(query_normalized):
                score = (1,) + score_base
            elif query_normalized in target_normalized:
                score = (2,) + score_base
            else:
                continue

        if best_score is None or score < best_score:
            best_score = score

    if best_score is None:
        return None

    return best_score + (entry["word"].lower(), entry["translation"].lower())


def search_dictionary(
    query="",
    languages=None,
    domains=None,
    whole_word=False,
    ignore_case=True,
    ignore_diacritics=True,
    parts_of_speech=None,
    labels=None,
    page=1,
):
    languages = set(languages or SEARCH_FILTERS["defaults"]["languages"])
    domains = set(domains or SEARCH_FILTERS["defaults"]["domains"])
    parts_of_speech = set(parts_of_speech or [])
    labels = set(labels or [])
    query = clean_value(query)
    filter_only_mode = not query and bool(parts_of_speech or labels)
    page = parse_int(page, default=1, minimum=1)

    ranked_results = []
    filtered_entries = []
    for entry in dictionary_entries:
        if parts_of_speech and entry["part_of_speech"] not in parts_of_speech:
            continue
        if labels and not labels.issubset(set(entry["labels"])):
            continue
        if filter_only_mode:
            filtered_entries.append(entry)
            continue

        rank = rank_entry_match(
            entry,
            query,
            languages,
            domains,
            whole_word=whole_word,
            ignore_case=ignore_case,
            ignore_diacritics=ignore_diacritics,
        )
        if rank is not None:
            ranked_results.append((rank, entry))

    if filter_only_mode:
        filtered_entries.sort(key=entry_sort_key)
        total_count = len(filtered_entries)
        total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        current_page = min(page, total_pages)
        start = (current_page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        entries = [serialize_entry(entry) for entry in filtered_entries[start:end]]
        return {
            "entries": entries,
            "total_count": total_count,
            "shown_count": len(entries),
            "limited": total_pages > 1,
            "page": current_page,
            "per_page": PAGE_SIZE,
            "total_pages": total_pages,
        }

    ranked_results.sort(key=lambda item: item[0])
    total_count = len(ranked_results)
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    current_page = min(page, total_pages)
    start = (current_page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    entries = [serialize_entry(entry) for _, entry in ranked_results[start:end]]
    return {
        "entries": entries,
        "total_count": total_count,
        "shown_count": len(entries),
        "limited": total_pages > 1,
        "page": current_page,
        "per_page": PAGE_SIZE,
        "total_pages": total_pages,
    }


def log_query(query, direction, found):
    log_df = pd.DataFrame(
        [
            {
                "date": date.today().isoformat(),
                "query": clean_value(query),
                "direction": direction,
                "found": found,
            }
        ]
    )
    log_df.to_csv(
        QUERY_LOG_FILE,
        mode="a",
        index=False,
        header=not os.path.exists(QUERY_LOG_FILE),
    )


@app.route("/")
def index():
    return render_template("index.html", search_filters=SEARCH_FILTERS)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/affixes")
def affix_search_page():
    return render_template("affixes.html")


@app.route("/search", methods=["GET"])
def search():
    query = clean_value(request.args.get("q", ""))
    languages = parse_csv_argument(
        request.args.get("languages"),
        default=SEARCH_FILTERS["defaults"]["languages"],
    )
    domains = parse_csv_argument(
        request.args.get("domains"),
        default=SEARCH_FILTERS["defaults"]["domains"],
    )
    parts_of_speech = parse_csv_argument(request.args.get("parts_of_speech"))
    labels = parse_csv_argument(request.args.get("labels"))
    page = parse_int(request.args.get("page"), default=1, minimum=1)
    whole_word = parse_bool(
        request.args.get("whole_word"),
        default=SEARCH_FILTERS["defaults"]["whole_word"],
    )
    ignore_case = parse_bool(
        request.args.get("ignore_case"),
        default=SEARCH_FILTERS["defaults"]["ignore_case"],
    )
    ignore_diacritics = parse_bool(
        request.args.get("ignore_diacritics"),
        default=SEARCH_FILTERS["defaults"]["ignore_diacritics"],
    )

    if not query and not parts_of_speech and not labels:
        return jsonify(
            {
                "entries": [],
                "total_count": 0,
                "shown_count": 0,
                "limited": False,
                "page": 1,
                "per_page": PAGE_SIZE,
                "total_pages": 1,
            }
        )

    results = search_dictionary(
        query,
        languages=languages,
        domains=domains,
        whole_word=whole_word,
        ignore_case=ignore_case,
        ignore_diacritics=ignore_diacritics,
        parts_of_speech=parts_of_speech,
        labels=labels,
        page=page,
    )
    if query:
        log_query(query, ",".join(sorted(languages)), bool(results["total_count"]))
    return jsonify(results)


@app.route("/search_affix", methods=["GET"])
def search_affix():
    query = clean_value(request.args.get("q", "")).lower()
    if not query:
        results = dict(sorted(affix_dict.items(), key=lambda item: item[0].lower()))
        return jsonify(results)

    results = dict(
        sorted(
            {
                affix: gloss
                for affix, gloss in affix_dict.items()
                if query in gloss.lower() or query in affix.lower()
            }.items(),
            key=lambda item: item[0].lower(),
        )
    )
    return jsonify(results)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
