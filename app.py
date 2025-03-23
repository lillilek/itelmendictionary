from flask import Flask, render_template, request, jsonify
import pandas as pd
import re
from difflib import SequenceMatcher
import os
from datetime import date
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import Counter

app = Flask(__name__)

# Загрузка словарей
itelmen_russian_df = pd.read_csv("itelmen_russian_dictionary.csv", dtype=str).fillna("")
russian_itelmen_df = pd.read_csv("russian_itelmen_dictionary.csv", dtype=str).fillna("")
affix_df = pd.read_csv("affixes_transliterated.csv", dtype=str, quotechar="\"", engine="python").fillna("")

itelmen_russian_dict = dict(zip(itelmen_russian_df.iloc[:, 0], itelmen_russian_df.iloc[:, 1]))
russian_itelmen_dict = dict(zip(russian_itelmen_df.iloc[:, 0], russian_itelmen_df.iloc[:, 1]))
affix_dict = dict(zip(affix_df["Аффикс"], affix_df["Описание"]))

# ---------------- Транслитерация ----------------
def transliterate_to_latin(text):
    mapping = {
        "ты": "ti", "лы": "li", "ны": "ni", "ы": "ɨ",
        "п": "p", "пʼ": "pʼ", "т": "t", "тʼ": "tʼ",
        "к": "k", "кʼ": "kʼ", "ӄ": "q", "ӄʼ": "qʼ",
        "ч": "č", "чʼ": "čʼ", "ф": "f", "с": "s",
        "х": "x", "ӽ": "χ", "в": "w", "з": "z",
        "й": "j", "г": "g", "ԓ": "ɬ", "л": "l",
        "љ": "ʎ", "р": "r", "м": "m", "н": "n",
        "њ": "ɲ", "ӈ": "ŋ", "ʔ": "ʔ", "д": "d",
        "б": "b", "ш": "ʂ", "щ": "ɕː", "ж": "ʐ",
        "ц": "t͡s", "и": "i", "у": "u", "е": "e",
        "о": "o", "а": "a", "ә": "ə", "э": "e",
        "ь": "'", "˚": "ʷ", "ў": "ŭ", "ŏ": "ŏ",
        "ǎ": "ǎ", "ɣ": "ɣ", "ɣʼ": "ɣʼ"
    }
    result = ""
    i = 0
    while i < len(text):
        if i + 2 <= len(text) and text[i:i+2] in mapping:
            result += mapping[text[i:i+2]]
            i += 2
        else:
            result += mapping.get(text[i], text[i])
            i += 1
    return result

# ---------------- Fuzzy ----------------
def normalize_for_fuzzy(text):
    fuzzy_equivalents = {'f', 'v', 'w', 'ɣ', 'ԝ̭', 'ф', 'в'}
    vowels = set("iuoeaəэŭŏǎɨыиуеаоэяёю")
    diacritics = "ʼ'ʷ˚"
    text = transliterate_to_latin(text.lower())
    result = ""
    for char in text:
        if char in diacritics or char in vowels:
            continue
        if char in fuzzy_equivalents:
            result += "W"
        else:
            result += char
    return result

def max_allowed_difference(word):
    return max(1, int(len(word) * 0.25))

def simple_edit_distance(a, b):
    sm = SequenceMatcher(None, a, b)
    return int(max(len(a), len(b)) * (1 - sm.ratio()))

def fallback_match(query, dictionary):
    query_translit = transliterate_to_latin(query.lower())
    max_diff = max_allowed_difference(query_translit)
    matches = {}
    for word in dictionary:
        word_translit = transliterate_to_latin(word.lower())
        if simple_edit_distance(query_translit, word_translit) <= max_diff:
            matches[word] = dictionary[word]
    return matches

def fuzzy_match(query, dictionary):
    query_norm = normalize_for_fuzzy(query)
    matches = {}
    for word in dictionary:
        word_norm = normalize_for_fuzzy(word)
        if query_norm == word_norm:
            matches[word] = dictionary[word]
    if matches:
        return matches
    return fallback_match(query, dictionary)

# ---------------- Flask ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/affixes")
def affix_search_page():
    return render_template("affixes.html")

@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q", "").strip().lower()
    direction = request.args.get("direction", "itelmen_to_russian")
    regex_mode = request.args.get("regex", "false").lower() == "true"
    force_fuzzy = request.args.get("fuzzy", "false").lower() == "true"

    if not query:
        return jsonify([])

    dictionary = itelmen_russian_dict if direction == "itelmen_to_russian" else russian_itelmen_dict
    query_translit = transliterate_to_latin(query) if direction == "itelmen_to_russian" else query

    if regex_mode:
        try:
            pattern = re.compile(query_translit)
            results = {word: dictionary[word] for word in dictionary if pattern.search(word)}
        except re.error:
            results = {}
    else:
        results = {word: dictionary[word] for word in dictionary if query_translit in word.lower()}

    if force_fuzzy or not results:
        results = fuzzy_match(query, dictionary)

    # логгирование запроса
    log_df = pd.DataFrame([{
        "date": date.today().isoformat(),
        "query": query,
        "direction": direction,
        "found": bool(results)
    }])
    log_file = "query_log.csv"
    log_df.to_csv(log_file, mode="a", index=False, header=not os.path.exists(log_file))

    return jsonify(results)

@app.route("/search_affix", methods=["GET"])
def search_affix():
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify([])

    results = {affix: gloss for affix, gloss in affix_dict.items() if query in gloss.lower()}
    if not results:
        results = fuzzy_match(query, affix_dict)
    return jsonify(results)

@app.route("/stats")
def stats():
    try:
        log_df = pd.read_csv("query_log.csv", parse_dates=["date"])

        # Фильтрация по словам, которые есть в словарях
        valid_words = set(itelmen_russian_dict.keys()) | set(russian_itelmen_dict.keys())
        log_df = log_df[log_df["query"].isin(valid_words)]

        summary = log_df.groupby(["date", "direction"]).agg({
            "query": "count",
            "found": "sum"
        }).reset_index().rename(columns={"query": "total", "found": "found_count"})

        chart_data = summary.groupby("date").agg({
            "total": "sum",
            "found_count": "sum"
        }).reset_index()

        # График количества запросов по дням
        plt.figure(figsize=(8, 4))
        plt.bar(chart_data["date"].dt.strftime("%Y-%m-%d"), chart_data["total"])
        plt.xticks(rotation=45, ha="right")
        plt.title("Количество запросов по дням")
        plt.tight_layout()
        plt.savefig("static/daily_queries.png")
        plt.close()

        # График самых популярных слов за сегодня (только валидные слова)
        today_df = log_df[log_df['date'].dt.date == date.today()]
        top_words = Counter(today_df['query']).most_common(10)

        if top_words:
            labels, values = zip(*top_words)
            plt.figure(figsize=(8, 4))
            plt.bar(labels, values)
            plt.xticks(rotation=45, ha="right")
            plt.title("Топ-10 слов за сегодня")
            plt.tight_layout()
            plt.savefig("static/top_words_today.png")
            plt.close()

        return render_template(
            "stats.html",
            stats=summary.to_dict(orient="records"),
            chart_data=chart_data.to_dict(orient="records"),
            top_words=top_words
        )
    except Exception as e:
        return f"Ошибка при загрузке статистики: {e}", 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")