"""
Script one-shot : récupère description + copyright depuis Amazon.fr
pour tous les livres de library.json qui ont un ASIN mais pas encore
de description.

Usage :
    python fetch_summaries.py [--force] [--dry-run]

Options :
    --force     Ré-écrit même les livres qui ont déjà une description
    --dry-run   Affiche ce qui serait fait sans modifier library.json
"""
import sys
import os
import io
import re
import json
import time
import argparse

# Force UTF-8 sur le terminal Windows (évite les UnicodeEncodeError sur les accents)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.fetcher import fetch_amazon_meta


LIBRARY_PATH = os.path.join(os.path.dirname(__file__), "library.json")
DELAY_S      = 2.5   # délai entre requêtes pour ne pas se faire bloquer
REGION       = "fr"
_ASIN_RE     = re.compile(r"^B[A-Z0-9]{9}$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force",   action="store_true", help="Ré-écrire même si description déjà présente")
    ap.add_argument("--dry-run", action="store_true", help="Ne pas modifier library.json")
    args = ap.parse_args()

    with open(LIBRARY_PATH, encoding="utf-8") as f:
        data = json.load(f)

    to_fetch = []
    for key, book in data.items():
        cfg  = book.get("config", {})
        asin = cfg.get("asin", "").strip()
        desc = cfg.get("description", "").strip()
        if not _ASIN_RE.match(asin):
            if asin:
                print(f"  ⚠  ASIN invalide ignoré : {key!r} → {asin!r}")
            continue
        if args.force or not desc:
            to_fetch.append((key, asin, cfg.get("title", key)))

    total = len(to_fetch)
    print(f"Livres à traiter : {total}  (sur {len(data)} total)\n")

    updated = 0
    for i, (key, asin, title) in enumerate(to_fetch, 1):
        print(f"[{i}/{total}] {title[:60]}  (ASIN: {asin})")
        result = fetch_amazon_meta(asin, region=REGION)
        desc  = result.get("description") or ""
        copy  = result.get("copyright") or ""

        if desc or copy:
            if not args.dry_run:
                if desc:
                    data[key]["config"]["description"] = desc
                if copy and not data[key]["config"].get("copyright"):
                    data[key]["config"]["copyright"] = copy
            tag = []
            if desc: tag.append(f"description ({len(desc)} car.)")
            if copy: tag.append(f"copyright")
            print(f"  ✓  {' + '.join(tag)}")
            updated += 1
        else:
            print("  ✗  Introuvable sur Amazon.fr")

        if i < total:
            time.sleep(DELAY_S)

    print(f"\n{updated}/{total} livres mis à jour.")

    if not args.dry_run and updated > 0:
        # Sauvegarde de sécurité
        backup = LIBRARY_PATH + ".bak_fetch"
        import shutil
        shutil.copy2(LIBRARY_PATH, backup)
        with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"library.json sauvegardé (backup : {os.path.basename(backup)})")


if __name__ == "__main__":
    main()
