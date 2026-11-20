"""Generuje statyczne dane dla strony (Cloudflare Pages): web/data/*.

    python scripts/build_static.py

Uruchom po każdej zmianie data/lotto_normalized.csv i zatwierdź wynik (git add web/data).
Pliki są „statycznym API”: działają zawsze, nawet gdy serwer API na Render śpi.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.service import DB_PATH, LottoService  # noqa: E402

OUT = ROOT / "web" / "data"


def build(out: Path = OUT) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    svc = LottoService.from_csv(DB_PATH)
    d = svc.draws
    draws = {
        "meta": svc.meta(),
        "columns": ["draw_id", "draw_date", "n1", "n2", "n3", "n4", "n5", "n6"],
        "rows": [[int(r.draw_id), r.draw_date.date().isoformat(), *(int(getattr(r, c)) for c in
                  ["n1", "n2", "n3", "n4", "n5", "n6"])] for r in d.itertuples()],
    }
    files = {
        "draws.json": json.dumps(draws, ensure_ascii=False, separators=(",", ":")),
        "stats.json": json.dumps(svc.stats, ensure_ascii=False, separators=(",", ":")),
    }
    paths = {}
    for name, text in files.items():
        p = out / name
        p.write_text(text + "\n", encoding="utf-8")
        paths[name] = p
    paths["draws.csv"] = out / "draws.csv"
    shutil.copyfile(DB_PATH, paths["draws.csv"])
    return paths


if __name__ == "__main__":
    for name, p in build().items():
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1024:.0f} KB")
