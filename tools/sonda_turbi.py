"""Sonda temporária: imagem dos slides de market share da apresentação institucional da Randoncorp."""
import io
import json
from pathlib import Path

import pdfplumber
import requests

OUT = Path("sonda_out")
OUT.mkdir(exist_ok=True)
URL = "https://api.mziq.com/mzfilemanager/v2/d/a8409c46-1419-4694-b935-b868e0b64e35/f53a3946-7943-c73b-c0a8-2edfab47c536?origin=2"
r = requests.get(URL, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
with pdfplumber.open(io.BytesIO(r.content)) as pdf:
    for n in (44, 45):
        pg = pdf.pages[n - 1]
        pg.to_image(resolution=110).save(OUT / f"randon_p{n}.png")
        words = [{"t": w["text"], "x": round(w["x0"]), "y": round(w["top"])} for w in pg.extract_words()]
        (OUT / f"randon_p{n}.json").write_text(json.dumps(words, ensure_ascii=False))
        print(f"WORDS{n}", json.dumps(words, ensure_ascii=False))
        print("ok", n, len(words))
