import re
import json
from config import BASE_DIR, MAX_CHARS_PER_FRAGMENT

GLOSSARY_FILE = BASE_DIR / "glossary.json"
with open(GLOSSARY_FILE, 'r', encoding='utf-8') as f:
    GLOSSARY = json.load(f)


def extract_conditions(text):
    pattern = r'([а-яА-Яa-zA-Z0-9\s]+?)\s*(<=|>=|=|<|>)\s*(\d+\.?\d*)\s*([а-яА-Яa-zA-Z/]+)'
    matches = re.findall(pattern, text)
    results = []
    for param, op, val, unit in matches:
        param = param.strip().lower()
        try:
            val_float = float(val)
        except ValueError:
            continue
        results.append({
            'parameter': param,
            'operator': op,
            'value': val_float,
            'unit': unit.lower()
        })
    return results


def extract_numbers_with_units(text):
    pattern = r'(\d+\.?\d*)\s*([а-яА-Яa-zA-Z/]+)'
    matches = re.findall(pattern, text)
    results = []
    for val, unit in matches:
        try:
            val_float = float(val)
        except ValueError:
            continue
        results.append({'value': val_float, 'unit': unit.lower()})
    return results


def extract_geography(text):
    text_lower = text.lower()
    if re.search(r'\b(россия|russia|рф|rf|сибирь|siberia|якутия|yakutia|урал|ural)\b', text_lower):
        return 'RU'
    elif re.search(r'\b(зарубеж|foreign|international|global|world|сша|usa|европа|europe|австралия|australia)\b', text_lower):
        return 'foreign'
    return None


def extract_years(text):
    years = re.findall(r'\b(19\d{2}|20\d{2})\b', text)
    return [int(y) for y in years]


def normalize_term(term):
    term_lower = term.lower().strip()
    for category in ['materials', 'processes', 'equipment']:
        for ru, en in GLOSSARY.get(category, {}).items():
            if term_lower == ru.lower() or term_lower == en.lower():
                return {
                    'type': category.rstrip('s'),
                    'canonical': ru,
                    'english': en
                }
    return None


def normalize_entity(name):
    if not name:
        return "unknown"
    name = re.sub(r'\s+', ' ', name.strip())
    name = re.sub(r'[^\w\s\-]', '', name)
    return name.lower().strip()


def normalize_predicate(pred):
    pred = pred.upper().strip()
    mapping = {
        "HAS": "HAS_PROPERTY",
        "PROPERTY": "HAS_PROPERTY",
        "USED": "USES_EQUIPMENT",
        "EQUIPMENT": "USES_EQUIPMENT",
        "PERFORM": "PERFORMED_BY",
        "AUTHOR": "PERFORMED_BY",
        "RESULT": "LEADS_TO",
        "CONCLUSION": "LEADS_TO",
        "MODE": "IN_MODE",
        "CONDITION": "IN_MODE",
        "VALUE": "HAS_VALUE",
        "REF": "REFERENCES",
        "CITE": "REFERENCES",
    }
    return mapping.get(pred, "RELATES_TO")


def clean_json_text(text):
    text = text.strip()
    text = re.sub(r'```json\s*|\s*```', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'^```.*?\n', '', text, flags=re.DOTALL)
    return text.strip()


def split_text_into_chunks(text, max_chars=MAX_CHARS_PER_FRAGMENT):
    """
    Разбивает текст на фрагменты приблизительно равной длины (по символам).
    Используется для чанков (маленьких кусков).
    """
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            search_start = max(start, end - 200)
            last_period = text.rfind('.', search_start, end)
            last_newline = text.rfind('\n', search_start, end)
            cut_pos = max(last_period, last_newline)
            if cut_pos > search_start:
                end = cut_pos + 1
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def split_text_into_fragments(text, max_chars=MAX_CHARS_PER_FRAGMENT):
    """
    Разбивает текст на большие фрагменты (до max_chars символов)
    для отправки в LLM. Отличается от split_text_into_chunks тем,
    что ищет границы предложений (точка, вопросительный знак, восклицательный)
    на большем интервале (500 символов).
    """
    if len(text) <= max_chars:
        return [text]
    fragments = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            search_start = max(start, end - 500)
            last_period = text.rfind('.', search_start, end)
            last_question = text.rfind('?', search_start, end)
            last_excl = text.rfind('!', search_start, end)
            last_newline = text.rfind('\n', search_start, end)
            cut_pos = max(last_period, last_question, last_excl, last_newline)
            if cut_pos > search_start:
                end = cut_pos + 1
        fragments.append(text[start:end].strip())
        start = end
    return [f for f in fragments if f]