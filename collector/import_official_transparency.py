#!/usr/bin/env python3
"""Incorpora exportaciones oficiales de transparencia al sitio estático.

La Cámara entrega directorios nacionales mediante botones de exportación. Este
script los transforma en una serie verificable, sin volver a consultar las 155
fichas individuales ni imputar ceros donde la fuente no publicó información.

Archivos esperados en data/imports/official/:
  - asesorias-AAAA-MM.xls, .xlsx, .csv o .html
  - personal-apoyo-AAAA-MM.xls, .xlsx, .csv o .html

Los .xls producidos por el botón de la Cámara suelen contener una tabla HTML.
También se aceptan CSV y XLSX. Si Excel descarga un XLS binario no compatible,
se debe abrir y guardar como XLSX antes de incorporarlo.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from statistics import median
from typing import Any
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
IMPORT_DIR = ROOT / "data" / "imports" / "official"
DETAILS_PATH = ROOT / "data" / "generated" / "chile-details-summary.json"
PUBLIC_SUMMARY_PATH = ROOT / "public" / "data" / "chile" / "details-summary.json"
DEPUTIES_DIR = ROOT / "public" / "data" / "chile" / "deputies"
COVERAGE_PATH = ROOT / "public" / "data" / "chile" / "transparency-coverage.json"

CATEGORIES = {
    "external_advisories": {
        "label": "Asesorías externas",
        "filename": "asesorias",
        "source_url": "https://www.camara.cl/transparencia/asesoriasexternasgral.aspx",
        "methodology": "Suma de filas del directorio mensual nacional de asesorías externas publicado por la Cámara. Cada fila se cruza con la nómina vigente; los nombres no conciliados quedan reportados y no se asignan a otra persona.",
    },
    "personnel_support": {
        "label": "Personal de apoyo",
        "filename": "personal-apoyo",
        "source_url": "https://www.camara.cl/transparencia/personalapoyogral.aspx",
        "methodology": "Suma de remuneraciones informadas para el personal de apoyo vigente en el directorio nacional. Es una fotografía de contratos informados, no una rendición mensual de gasto.",
    },
}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa exportaciones oficiales nacionales de transparencia.")
    parser.add_argument("--directory", type=Path, default=IMPORT_DIR, help="Directorio de archivos oficiales.")
    parser.add_argument("--dry-run", action="store_true", help="Valida archivos y muestra cobertura sin modificar datos.")
    return parser.parse_args()


def load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


# Erratas verificadas en los directorios oficiales. Cada alias apunta a la
# persona de la nómina vigente; no se realizan aproximaciones genéricas para
# evitar atribuir gastos a un diputado distinto.
VERIFIED_DEPUTY_ALIASES = {
    normalized("Zamorano P., Fernado"): "Fernando Zamorano Peralta",
}


def clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value).replace("\xa0", " ")).strip()


def parse_amount(value: str) -> int | None:
    compact = re.sub(r"[^0-9-]", "", str(value))
    if not compact or compact == "-":
        return None
    try:
        amount = int(compact)
    except ValueError:
        return None
    return amount if amount >= 0 else None


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self.current_row = []
        elif tag.lower() in {"td", "th"} and self.current_row is not None:
            self.current_cell = []
        elif tag.lower() == "br" and self.current_cell is not None:
            self.current_cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self.current_cell is not None and self.current_row is not None:
            self.current_row.append(clean_cell("".join(self.current_cell)))
            self.current_cell = None
        elif tag.lower() == "tr" and self.current_row is not None:
            if any(self.current_row):
                self.rows.append(self.current_row)
            self.current_row = None


def rows_from_html(raw: bytes) -> list[list[str]]:
    text = raw.decode("utf-8", errors="replace")
    if text.count("�") > 10:
        text = raw.decode("latin-1", errors="replace")
    # Los archivos .xls exportados por la Cámara son HTML y contienen celdas
    # mal formadas como ``<td/>Texto</td>``. En un navegador se toleran, pero
    # HTMLParser interpreta ese ``td`` como una celda ya cerrada. Normalizarlo
    # permite conservar el contenido y sus encabezados oficiales.
    text = re.sub(r"<(td|th)\s*/>", r"<\1>", text, flags=re.IGNORECASE)
    parser = TableParser()
    parser.feed(text)
    return parser.rows


def column_index(reference: str) -> int:
    value = 0
    for letter in re.match(r"[A-Z]+", reference).group(0):
        value = value * 26 + ord(letter) - 64
    return value - 1


def rows_from_xlsx(path: Path) -> list[list[str]]:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    relation_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    with zipfile.ZipFile(path) as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared_strings = ["".join(node.itertext()) for node in root.findall(f"{namespace}si")]
        sheet_path = "xl/worksheets/sheet1.xml"
        if sheet_path not in workbook.namelist():
            sheet_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
            first_sheet = sheet_root.find(f"{namespace}sheets/{namespace}sheet")
            relation_id = first_sheet.get(f"{relation_namespace}id") if first_sheet is not None else None
            relations = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
            relationship = next((node for node in relations if node.get("Id") == relation_id), None)
            target = relationship.get("Target") if relationship is not None else None
            if not target:
                raise ValueError("No fue posible identificar la primera hoja del XLSX.")
            sheet_path = f"xl/{target.lstrip('/')}"
        root = ElementTree.fromstring(workbook.read(sheet_path))
        rows: list[list[str]] = []
        for row in root.findall(f".//{namespace}sheetData/{namespace}row"):
            values: dict[int, str] = {}
            for cell in row.findall(f"{namespace}c"):
                reference = cell.get("r", "A1")
                value_node = cell.find(f"{namespace}v")
                inline_node = cell.find(f"{namespace}is")
                raw = value_node.text if value_node is not None else ""
                if cell.get("t") == "s" and raw and raw.isdigit():
                    raw = shared_strings[int(raw)]
                elif inline_node is not None:
                    raw = "".join(inline_node.itertext())
                values[column_index(reference)] = clean_cell(raw or "")
            if values:
                rows.append([values.get(index, "") for index in range(max(values) + 1)])
        return rows


def rows_from_csv(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    if text.count("�") > 10:
        text = raw.decode("latin-1", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [[clean_cell(cell) for cell in row] for row in csv.reader(text.splitlines(), dialect) if any(clean_cell(cell) for cell in row)]


def read_rows(path: Path) -> list[list[str]]:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return rows_from_xlsx(path)
    if suffix == ".csv":
        return rows_from_csv(path)
    raw = path.read_bytes()
    if raw.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError("El archivo XLS es binario. Ábrelo con Excel y guárdalo como XLSX antes de subirlo.")
    return rows_from_html(raw)


def find_header(rows: list[list[str]], category: str) -> tuple[int, dict[str, int]]:
    expected = ("folio", "asesor", "monto", "diputado") if category == "external_advisories" else ("distrito", "diputado", "sueldo")
    for row_number, row in enumerate(rows[:20]):
        headers = [normalized(cell) for cell in row]
        if sum(any(word in header for header in headers) for word in expected) < len(expected) - 1:
            continue
        positions: dict[str, int] = {}
        for index, header in enumerate(headers):
            if "diputado" in header:
                positions["deputy"] = index
            if category == "external_advisories" and ("monto" in header or "valor" in header):
                positions["amount"] = index
            if category == "personnel_support" and ("sueldo" in header or "remuneracion" in header):
                positions["amount"] = index
        if {"deputy", "amount"}.issubset(positions):
            return row_number, positions
    label = CATEGORIES[category]["label"]
    raise ValueError(f"No se reconocieron las columnas oficiales de {label}. No se importó el archivo.")


def deputy_id(source_name: str, deputies: list[dict[str, Any]]) -> str | None:
    source = normalized(source_name)
    if not source:
        return None
    alias = VERIFIED_DEPUTY_ALIASES.get(source)
    if alias:
        alias_normalized = normalized(alias)
        match = next((str(deputy["id"]) for deputy in deputies if normalized(str(deputy["name"])) == alias_normalized), None)
        if match:
            return match
    surname_part, _, given_part = source.partition(" ")
    # La exportación de la Cámara usa normalmente "Apellido I., Nombre".
    if "," in source_name:
        raw_surname, raw_given = source_name.split(",", 1)
        surname_tokens = normalized(raw_surname).split()
        given_tokens = normalized(raw_given).split()
    else:
        tokens = source.split()
        surname_tokens, given_tokens = tokens[-2:], tokens[:1]
    surname_tokens = [token for token in surname_tokens if len(token) > 1]
    given_tokens = [token for token in given_tokens if len(token) > 1]
    candidates: list[str] = []
    for deputy in deputies:
        candidate = normalized(str(deputy["name"]))
        words = set(candidate.split())
        if surname_tokens and given_tokens and surname_tokens[0] in words and given_tokens[0] in words:
            candidates.append(str(deputy["id"]))
        elif source and (source in candidate or candidate in source):
            candidates.append(str(deputy["id"]))
    return candidates[0] if len(candidates) == 1 else None


def parse_records(rows: list[list[str]], category: str, deputies: list[dict[str, Any]]) -> tuple[dict[str, int], int, list[str]]:
    header_row, positions = find_header(rows, category)
    totals: defaultdict[str, int] = defaultdict(int)
    unmatched: list[str] = []
    parsed = 0
    for row in rows[header_row + 1:]:
        if max(positions.values()) >= len(row):
            continue
        amount = parse_amount(row[positions["amount"]])
        deputy_name = row[positions["deputy"]]
        if amount is None or not deputy_name:
            continue
        parsed += 1
        match = deputy_id(deputy_name, deputies)
        if match is None:
            unmatched.append(deputy_name)
            continue
        totals[match] += amount
    return dict(totals), parsed, sorted(set(unmatched))


def update_money(record: dict[str, Any], category: str, month: str, amount: int, source_file: str, imported_at: str) -> None:
    detail = record.setdefault("transparency", {})
    money = detail.setdefault(category, {"by_month": {}})
    by_month = money.setdefault("by_month", {})
    by_month[month] = amount
    values = list(by_month.values())
    configuration = CATEGORIES[category]
    money.update({
        "latest_month": max(by_month),
        "latest_amount": by_month[max(by_month)],
        "average_monthly": round(sum(values) / len(values)),
        "median_monthly": round(median(values)),
        "months_with_records": len(by_month),
        "methodology": configuration["methodology"],
        "metadata": {
            "availability": "published_official_import",
            "label": configuration["label"],
            "source_url": configuration["source_url"],
            "source_file": source_file,
            "imported_at": imported_at,
            "month": month,
        },
    })
    if category == "personnel_support":
        detail["personnel_support_metadata"] = money["metadata"]
        money["contracts_count"] = money.get("contracts_count", 0)
    detail["availability"] = "published_partial"


def summarize(records: list[dict[str, Any]], category: str) -> dict[str, Any]:
    totals: defaultdict[str, int] = defaultdict(int)
    coverage: defaultdict[str, int] = defaultdict(int)
    import_files: set[str] = set()
    imported_at: list[str] = []
    for record in records:
        item = record.get("transparency", {}).get(category, {})
        for month, amount in (item.get("by_month") or {}).items():
            totals[month] += int(amount)
            coverage[month] += 1
        metadata = item.get("metadata") or {}
        if metadata.get("source_file"):
            import_files.add(str(metadata["source_file"]))
        if metadata.get("imported_at"):
            imported_at.append(str(metadata["imported_at"]))
    values = list(totals.values())
    latest = max(totals) if totals else None
    configuration = CATEGORIES[category]
    return {
        "by_month": dict(sorted(totals.items())),
        "coverage_by_month": dict(sorted(coverage.items())),
        "latest_month": latest,
        "latest_amount": totals.get(latest) if latest else None,
        "average_monthly": round(sum(values) / len(values)) if values else None,
        "median_monthly": round(median(values)) if values else None,
        "months_with_records": len(values),
        "methodology": configuration["methodology"],
        "metadata": {
            "availability": "published_official_import" if values else "pending_official_import",
            "label": configuration["label"],
            "source_url": configuration["source_url"],
            "source_files": sorted(import_files),
            "last_imported_at": max(imported_at) if imported_at else None,
        },
    }


def files_to_import(directory: Path) -> list[tuple[str, str, Path]]:
    results: list[tuple[str, str, Path]] = []
    expression = re.compile(r"^(asesorias|personal-apoyo)-(20\d{2}-\d{2})\.(csv|xlsx|xls|html?)$", re.IGNORECASE)
    for path in sorted(directory.glob("*")):
        match = expression.match(path.name)
        if not match:
            continue
        file_kind, month = match.group(1).lower(), match.group(2)
        category = "external_advisories" if file_kind == "asesorias" else "personnel_support"
        results.append((category, month, path))
    return results


def main() -> None:
    args = parse_args()
    files = files_to_import(args.directory)
    if not files:
        print(json.dumps({"imports": [], "files_found": 0, "dry_run": args.dry_run}, ensure_ascii=False, indent=2))
        return
    details = load_json(DETAILS_PATH, {})
    deputies = load_json(ROOT / "public" / "data" / "chile" / "index.json", {}).get("deputies", [])
    if len(deputies) != 155:
        raise RuntimeError("La nómina nacional debe contener 155 diputados(as) antes de importar transparencia.")
    records: list[dict[str, Any]] = []
    for deputy in deputies:
        path = DEPUTIES_DIR / f"{deputy['id']}.json"
        record = load_json(path, None)
        if not isinstance(record, dict):
            raise RuntimeError(f"No existe la ficha nacional de {deputy['id']}.")
        records.append(record)

    reports: list[dict[str, Any]] = []
    imported_at = datetime.now(timezone.utc).isoformat()
    for category, month, path in files:
        rows = read_rows(path)
        totals, rows_read, unmatched = parse_records(rows, category, deputies)
        reports.append({
            "category": category,
            "month": month,
            "file": path.name,
            "rows_read": rows_read,
            "deputies_matched": len(totals),
            "unmatched_names": unmatched,
        })
        for record in records:
            deputy_id_value = str(record["profile"]["id"])
            if deputy_id_value in totals:
                update_money(record, category, month, totals[deputy_id_value], path.name, imported_at)

    transparency = details.setdefault("transparency", {})
    for category in CATEGORIES:
        transparency[category] = summarize(records, category)
    for district in details.get("districts", []):
        district_label = f"Distrito {district.get('district', '')}"
        district_records = [record for record in records if record.get("profile", {}).get("district") == district_label]
        district_transparency = district.setdefault("transparency", {})
        for category in CATEGORIES:
            district_transparency[category] = summarize(district_records, category)
    transparency["official_imports"] = reports
    transparency["retrieved_at"] = imported_at
    coverage = {
        "schema_version": 1,
        "generated_at": imported_at,
        "source": "Exportaciones mensuales oficiales de Transparencia Activa de la Cámara",
        "categories": {category: transparency[category] for category in CATEGORIES},
        "imports": reports,
    }

    if not args.dry_run:
        for record in records:
            save_json(DEPUTIES_DIR / f"{record['profile']['id']}.json", record)
        save_json(DETAILS_PATH, details)
        save_json(PUBLIC_SUMMARY_PATH, details)
        save_json(COVERAGE_PATH, coverage)
    print(json.dumps({"imports": reports, "files_found": len(files), "dry_run": args.dry_run}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
