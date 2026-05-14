import re

_STRUCT_KEYWORDS = {
    "LIVRE":    ("Livre",    True),
    "PART":     ("Partie",   True),
    "PARTIE":   ("Partie",   True),
    "CH":       ("Chapitre", True),
    "CHAP":     ("Chapitre", True),
    "CHAPITRE": ("Chapitre", True),
}


def normalize_chapter_title(raw: str) -> str:
    """'04_LIVRE_1_CH_01_UNE_FETE_TRES_ATTENDUE'
    → '04 Livre 1 - Chapitre 01 - Une fete tres attendue'"""
    if not raw or "_" not in raw:
        return raw

    tokens = raw.strip().split("_")
    i = 0
    num = ""
    structs: list[str] = []

    if i < len(tokens) and re.match(r"^\d+$", tokens[i]):
        num = tokens[i]
        i += 1

    while i < len(tokens):
        tok_up = tokens[i].upper()
        if tok_up in _STRUCT_KEYWORDS:
            label, takes_num = _STRUCT_KEYWORDS[tok_up]
            if takes_num and i + 1 < len(tokens) and re.match(r"^\d+$", tokens[i + 1]):
                structs.append(f"{label} {tokens[i + 1]}")
                i += 2
            else:
                structs.append(label)
                i += 1
        else:
            break

    words = tokens[i:]
    if words:
        title_part = words[0].capitalize()
        if len(words) > 1:
            title_part += " " + " ".join(w.lower() for w in words[1:])
    else:
        title_part = ""

    all_parts: list[str] = []
    if num and structs:
        all_parts.append(num + " " + structs[0])
        all_parts.extend(structs[1:])
    elif num:
        all_parts.append(num)
    else:
        all_parts.extend(structs)

    if title_part:
        all_parts.append(title_part)

    return " - ".join(all_parts) if all_parts else raw
