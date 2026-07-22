#!/usr/bin/env python3
"""Actualiza transparencia mensual sin repetir la extracción legislativa nacional.

Las fichas de la Cámara usan un selector WebForms. Esta tarea consulta solamente
un mes por ficha y categoría, por lo que es mucho más corta que volver a bajar
mociones, acuerdos, resoluciones y asistencias de los 155 representantes.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from collect_district import TRANSPARENCY_SOURCES, collect_transparency_month, empty_monthly_money, load_json, save_json


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data" / "generated" / "chile-summary.json"
SUMMARY_PATH = ROOT / "data" / "generated" / "chile-details-summary.json"
DATA_DIR = ROOT / "public" / "data" / "chile"

CATEGORIES = {
    "operational_expenses": "Gastos operacionales",
    "external_advisories": "Asesorías externas",
    "flights": "Pasajes aéreos nacionales",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Actualiza un mes de transparencia para la nómina nacional.")
    parser.add_argument("--month", required=True, help="Mes publicado a consultar, con formato AAAA-MM.")
    parser.add_argument("--workers", type=int, default=5, help="Consultas simultáneas (máximo seguro: 5).")
    parser.add_argument("--delay", type=float, default=0.2, help="Pausa mínima entre consultas oficiales.")
    return parser.parse_args()


def money_summary(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    totals: defaultdict[str, int] = defaultdict(int)
    coverage: defaultdict[str, int] = defaultdict(int)
    for record in records:
        for month, amount in (record.get("transparency", {}).get(field, {}).get("by_month", {}) or {}).items():
            totals[month] += int(amount)
            coverage[month] += 1
    values = list(totals.values())
    latest_month = max(totals) if totals else None
    return {
        "by_month": dict(sorted(totals.items())),
        "coverage_by_month": dict(sorted(coverage.items())),
        "latest_month": latest_month,
        "latest_amount": totals.get(latest_month) if latest_month else None,
        "average_monthly": round(sum(values) / len(values)) if values else None,
        "median_monthly": round(median(values)) if values else None,
        "months_with_records": len(values),
        "methodology": "Suma de montos publicados por la Cámara para cada mes. La cobertura indica cuántas fichas tuvieron un registro publicado; las fichas sin publicación no se imputan como $0.",
        "metadata": {"availability": "published_partial" if values else "not_published", "label": CATEGORIES[field], "source_url": TRANSPARENCY_SOURCES[field].format(deputy_id="{id}")},
    }


def update_record(record: dict[str, Any], category: str, month_key: str, amount: int | None) -> bool:
    deputy_id = str(record["profile"]["id"])
    transparency = record.setdefault("transparency", {})
    money = transparency.get(category)
    if not isinstance(money, dict):
        money = empty_monthly_money(source_url=TRANSPARENCY_SOURCES[category].format(deputy_id=deputy_id), label=CATEGORIES[category])
        transparency[category] = money
    if amount is None:
        return False
    by_month = money.setdefault("by_month", {})
    previous = by_month.get(month_key)
    by_month[month_key] = amount
    values = list(by_month.values())
    money.update({
        "latest_month": max(by_month),
        "latest_amount": by_month[max(by_month)],
        "average_monthly": round(sum(values) / len(values)),
        "median_monthly": round(median(values)),
        "months_with_records": len(by_month),
        "methodology": "Monto mensual publicado en la ficha de transparencia de la Cámara. Un mes ausente permanece pendiente y no representa $0.",
        "metadata": {"availability": "published", "label": CATEGORIES[category], "source_url": TRANSPARENCY_SOURCES[category].format(deputy_id=deputy_id)},
    })
    return previous != amount


def main() -> None:
    args = parse_args()
    try:
        year, month = (int(part) for part in args.month.split("-", 1))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError as error:
        raise SystemExit("--month debe usar el formato AAAA-MM.") from error
    index = load_json(INDEX_PATH, {})
    deputies = index.get("deputies", [])
    if len(deputies) != 155:
        raise RuntimeError("Se requieren 155 integrantes en el índice nacional antes de actualizar transparencia.")
    records: list[dict[str, Any]] = []
    for deputy in deputies:
        path = DATA_DIR / "deputies" / f"{deputy['id']}.json"
        record = load_json(path, None)
        if not isinstance(record, dict):
            raise RuntimeError(f"No existe la ficha legislativa de {deputy['id']}; ejecuta primero la carga nacional de fichas.")
        records.append(record)

    workers = max(1, min(args.workers, 5))
    results: dict[tuple[str, str], int | None] = {}
    failures: list[dict[str, str]] = []

    def fetch(deputy_id: str, category: str) -> tuple[str, str, int | None, str | None]:
        try:
            amount = collect_transparency_month(
                deputy_id=deputy_id,
                source_url=TRANSPARENCY_SOURCES[category],
                year=year,
                month=month,
                delay=args.delay,
            )
            return deputy_id, category, amount, None
        except RuntimeError as error:
            return deputy_id, category, None, str(error)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch, str(deputy["id"]), category) for deputy in deputies for category in CATEGORIES]
        for future in as_completed(futures):
            deputy_id, category, amount, failure = future.result()
            results[(deputy_id, category)] = amount
            if failure:
                failures.append({"deputy_id": deputy_id, "category": category, "reason": failure})

    changed = 0
    for record in records:
        deputy_id = str(record["profile"]["id"])
        for category in CATEGORIES:
            if update_record(record, category, args.month, results[(deputy_id, category)]):
                changed += 1
        published = any(record["transparency"].get(category, {}).get("by_month") for category in CATEGORIES)
        record["transparency"]["availability"] = "published_partial" if published else "not_published"
        record["retrieved_at"] = datetime.now(UTC).isoformat()
        save_json(DATA_DIR / "deputies" / f"{deputy_id}.json", record)

    summary = load_json(SUMMARY_PATH, {})
    summary["transparency"] = {category: money_summary(records, category) for category in CATEGORIES}
    summary["transparency"]["retrieved_at"] = datetime.now(UTC).isoformat()
    summary["transparency"]["month_requested"] = args.month
    summary["transparency"]["failures"] = failures
    save_json(SUMMARY_PATH, summary)
    save_json(DATA_DIR / "details-summary.json", summary)
    print(json.dumps({"month": args.month, "records_changed": changed, "published": sum(amount is not None for amount in results.values()), "queries": len(results), "failures": len(failures)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
