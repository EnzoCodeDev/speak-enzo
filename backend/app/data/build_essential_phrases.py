#!/usr/bin/env python3
"""Valida los archivos de categorías de frases y genera essential_phrases.json.

- Lee los 20 archivos JSON de backend/app/data/phrases/
- Valida que cada uno tenga exactamente 50 frases con la estructura correcta
- Genera backend/app/data/essential_phrases.json con ids globales consecutivos
"""

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
PHRASES_DIR = DATA_DIR / "phrases"
OUTPUT_FILE = DATA_DIR / "essential_phrases.json"

EXPECTED_FILES = 20
EXPECTED_PER_CATEGORY = 50
VALID_LEVELS = {"A1", "A2", "B1"}
REQUIRED_CATEGORY_KEYS = {"id", "name_es", "name_en", "emoji", "phrases"}
REQUIRED_PHRASE_KEYS = {"en", "es", "level"}


def fail(msg: str) -> None:
    print(f"ERROR: {msg}")
    sys.exit(1)


def main() -> None:
    files = sorted(PHRASES_DIR.glob("*.json"))
    if len(files) != EXPECTED_FILES:
        fail(f"Se esperaban {EXPECTED_FILES} archivos en {PHRASES_DIR}, se encontraron {len(files)}")

    categories = []
    seen_category_ids = set()
    seen_en = {}
    duplicates = []
    next_id = 1

    for path in files:
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            fail(f"JSON inválido en {path.name}: {e}")

        missing = REQUIRED_CATEGORY_KEYS - data.keys()
        if missing:
            fail(f"{path.name}: faltan claves de categoría {sorted(missing)}")

        if data["id"] in seen_category_ids:
            fail(f"{path.name}: id de categoría duplicado '{data['id']}'")
        seen_category_ids.add(data["id"])

        phrases = data["phrases"]
        if not isinstance(phrases, list) or len(phrases) != EXPECTED_PER_CATEGORY:
            fail(f"{path.name}: tiene {len(phrases)} frases, se esperaban {EXPECTED_PER_CATEGORY}")

        out_phrases = []
        for i, p in enumerate(phrases, start=1):
            missing = REQUIRED_PHRASE_KEYS - p.keys()
            if missing:
                fail(f"{path.name}, frase #{i}: faltan claves {sorted(missing)}")
            if p["level"] not in VALID_LEVELS:
                fail(f"{path.name}, frase #{i}: nivel inválido '{p['level']}'")
            if not p["en"].strip() or not p["es"].strip():
                fail(f"{path.name}, frase #{i}: texto vacío")

            key = p["en"].strip().lower()
            if key in seen_en:
                duplicates.append(f"'{p['en']}' en {path.name} y {seen_en[key]}")
            else:
                seen_en[key] = path.name

            out_phrases.append({"id": next_id, "en": p["en"], "es": p["es"], "level": p["level"]})
            next_id += 1

        categories.append({
            "id": data["id"],
            "name_es": data["name_es"],
            "name_en": data["name_en"],
            "emoji": data["emoji"],
            "phrases": out_phrases,
        })
        print(f"OK  {path.name}: {len(out_phrases)} frases")

    if duplicates:
        print("ADVERTENCIA: frases en inglés repetidas entre categorías:")
        for d in duplicates:
            print(f"  - {d}")

    total = next_id - 1
    result = {"version": 1, "total": total, "categories": categories}

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nArchivo generado: {OUTPUT_FILE}")
    print(f"Total de frases: {total}")
    if total == 1000:
        print("Confirmado: el dataset tiene exactamente 1000 frases.")
    else:
        fail(f"El total es {total}, no 1000")


if __name__ == "__main__":
    main()
