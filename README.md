# psmf-cal

Statická stránka, kde si hráč najde svůj tým a stáhne rozpis zápasů jako `.ics`
kalendář pro Google Kalendář, Apple Kalendář nebo Outlook.

Data se stahují z [psmf.cz](https://www.psmf.cz/). Všechny kalendáře vznikají
při buildu — hotová stránka je jen HTML, CSS a JavaScript, žádný backend.

## Soutěže

Podzim 2026: **Hanspaulská**, **veteránská**, **superveteránská** a
**ultraveteránská liga** — 938 týmů.

V každém kalendáři je datum a čas výkopu (pražský čas včetně přechodu na zimní
čas), soupeř, hřiště s adresou a odkazem na mapu, dresy obou týmů a upozornění
3 hodiny před zápasem.

## Spuštění

```sh
pip install -r requirements.txt
python -m psmf_cal.cli          # zapíše dist/
python -m http.server -d dist 8000
```

Kompletní crawl je asi 1000 stránek, tj. zhruba sedm minut. Odpovědi se cachují
na disk, takže další běhy jsou skoro okamžité.

| Volba | Význam |
| --- | --- |
| `--dist PATH` | výstupní adresář (výchozí `dist`) |
| `--league hl vet` | jen vybrané ligy (`hl`, `vet`, `svet`, `uvet`) |
| `--only 7-h vet:1-a` | jen vybrané skupiny |
| `--no-cache` | ignorovat cache a stáhnout vše znovu |

Kontroly: `ruff check . && mypy --strict . && pytest`, a nad hotovým buildem
navíc `node tests/frontend_check.mjs`.

---

Vytvořeno pomocí AI (Claude).
