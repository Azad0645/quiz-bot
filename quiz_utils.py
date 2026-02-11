import json
from typing import List, Dict


def load_questions(path: str = "questions.json") -> List[Dict[str, str]]:
    """Загрузить список вопросов из JSON-файла."""
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def normalize_answer(text: str) -> str:
    """
    Нормализовать ответ:
    - обрезать по первой точке или скобке;
    - убрать лишнюю пунктуацию;
    - привести к нижнему регистру;
    - нормализовать ё -> е.
    """
    if not text:
        return ""

    text = text.strip().lower()

    cut_pos = len(text)
    for separator in (".", "("):
        index = text.find(separator)
        if index != -1 and index < cut_pos:
            cut_pos = index

    core = text[:cut_pos].strip()
    core = core.strip(" .,!?:;—-\"'«»")
    core = core.replace("ё", "е")

    return core