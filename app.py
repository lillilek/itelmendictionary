from flask import Flask, render_template, request, jsonify, redirect, url_for
import pandas as pd
import re
from difflib import SequenceMatcher

app = Flask(__name__)

# Загрузка словарей
itelmen_russian_df = pd.read_csv("itelmen_russian_dictionary.csv", dtype=str).fillna("")
russian_itelmen_df = pd.read_csv("russian_itelmen_dictionary.csv", dtype=str).fillna("")
affix_df = pd.read_csv("affixes_transliterated.csv", dtype=str).fillna("")

itelmen_russian_dict = dict(zip(itelmen_russian_df.iloc[:, 0].astype(str), itelmen_russian_df.iloc[:, 1].astype(str)))
russian_itelmen_dict = dict(zip(russian_itelmen_df.iloc[:, 0].astype(str), russian_itelmen_df.iloc[:, 1].astype(str)))
gloss_dict = dict(zip(affix_df["Аффикс"], affix_df["Описание"]))

def transliterate_to_latin(text):
    mapping = {
        "ты": "ti", "лы": "li", "ны": "ni", "ы": "ɨ",
        "п": "p",  "пʼ": "pʼ",  "т": "t",  "тʼ": "tʼ",
        "к": "k",  "кʼ": "kʼ",  "ӄ": "q",  "ӄʼ": "qʼ",
        "ч": "č",  "чʼ": "čʼ",  "ф": "f",  "с": "s",
        "х": "x",  "ӽ": "χ",    "в": "w",  "з": "z",
        "й": "j",  "г": "g",    "ԓ": "ɬ",  "л": "l",
        "љ": "ʎ",  "р": "r",    "м": "m",  "н": "n",
        "њ": "ɲ",  "ӈ": "ŋ",    "ʔ": "ʔ",  "д": "d",
        "б": "b",  "ш": "ʂ",    "щ": "ɕː", "ж": "ʐ",
        "ц": "t͡s",
        "и": "i", "у": "u", "е": "e", "о": "o", "а": "a", "ә": "ə", "э": "e",
        "ь": "'", "˚": "ʷ", "ў": "ŭ", "ŏ": "ŏ", "ǎ": "ǎ"
    }

    result = ""
    i = 0

    while i < len(text):
        if i + 1 < len(text) and text[i:i+2] in mapping:
            result += mapping[text[i:i+2]]
            i += 2
        else:
            result += mapping.get(text[i], text[i])
            i += 1

    return result

def normalize_for_fuzzy(text):
    replace_pairs = [("w", "ф"), ("ф", "w")]
    vowels = "iuoeaəэŭŏǎɨ"

    text = text.lower()
    for a, b in replace_pairs:
        text = text.replace(a, b)

    text = re.sub(r"[ʼ'ʷ˚]", "", text)
    text = "".join(c for c in text if c not in vowels)
    return text

def fuzzy_match(query, dictionary, threshold=0.75):
    norm_q = normalize_for_fuzzy(query)
    matches = {}
    for word in dictionary:
        norm_w = normalize_for_fuzzy(word)
        ratio = SequenceMatcher(None, norm_q, norm_w).ratio()
        if ratio >= threshold:
            matches[word] = dictionary[word]
    return matches

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/glosses")
def gloss_search_page():
    return render_template("glosses.html")

@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q", "").strip().lower()
    direction = request.args.get("direction", "itelmen_to_russian")
    regex_mode = request.args.get("regex", "false").lower() == "true"

    if not query:
        return jsonify([])

    if direction == "itelmen_to_russian":
        query = transliterate_to_latin(query)

    dictionary = itelmen_russian_dict if direction == "itelmen_to_russian" else russian_itelmen_dict

    if regex_mode:
        try:
            pattern = re.compile(query)
            results = {word: dictionary[word] for word in dictionary if pattern.search(word)}
        except re.error:
            results = {}
    else:
        results = {word: dictionary[word] for word in dictionary if query in word.lower()}

    if not results:
        results = fuzzy_match(query, dictionary)

    return jsonify(results)

@app.route("/search_gloss", methods=["GET"])
def search_gloss():
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify([])

    results = {affix: gloss for affix, gloss in gloss_dict.items() if query in gloss.lower()}
    if not results:
        results = fuzzy_match(query, gloss_dict)
    return jsonify(results)

if __name__ == "__main__":
    app.run(debug=True)
    