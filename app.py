from flask import Flask, render_template, request, jsonify, redirect, url_for
import pandas as pd
import re

app = Flask(__name__)

itelmen_russian_df = pd.read_csv("itelmen_russian_dictionary.csv", dtype=str).fillna("")
russian_itelmen_df = pd.read_csv("russian_itelmen_dictionary.csv", dtype=str).fillna("")

itelmen_russian_dict = dict(zip(itelmen_russian_df.iloc[:, 0].astype(str), itelmen_russian_df.iloc[:, 1].astype(str)))
russian_itelmen_dict = dict(zip(russian_itelmen_df.iloc[:, 0].astype(str), russian_itelmen_df.iloc[:, 1].astype(str)))

def transliterate_to_latin(text):
    mapping = {
        "ты": "ti", "лы": "li", "ны": "ni", "ы": "ɨ",
        "п": "p",  "пʼ": "p'",  "т": "t",  "тʼ": "t'",
        "к": "k",  "кʼ": "k'",  "ӄ": "q",  "ӄʼ": "q'",
        "ч": "č",  "чʼ": "č'",  "ф": "f",  "с": "s",
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

@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html")

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
        pattern = re.compile(query)
        results = {word: dictionary[word] for word in dictionary if pattern.search(word)}
    else:
        results = {word: dictionary[word] for word in dictionary if word.lower().startswith(query)}

    return jsonify(results)

if __name__ == "__main__":
    app.run(debug=True)
