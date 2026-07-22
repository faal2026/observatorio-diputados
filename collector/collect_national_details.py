#!/usr/bin/env python3
"""Construye fichas legislativas nacionales reutilizando una sola descarga anual.

La Cámara publica las iniciativas anuales como conjuntos nacionales. Consultarlas
una vez por distrito multiplica innecesariamente las mismas solicitudes y vuelve
la actualización muy lenta. Este proceso obtiene cada conjunto una sola vez,
guarda el caché de autorías y reparte los resultados entre los 155 integrantes.

No inventa transparencia: gastos, asesorías, pasajes y personal permanecen como
pendientes hasta contar con una fuente mensual nacionalmente comparable.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collect_district import (  # El piloto ya contiene parsers probados de las fuentes oficiales.
    DIET_2026,
    METHODS,
    TRANSPARENCY_SOURCES,
    empty_monthly_money,
    hydrate_attendance,
    hydrate_authors,
    hydrate_commissions,
    load_json,
    method_url,
    parse_projects,
    parse_session_ids,
    request_text,
    save_json,
    summarize_district_activity,
    summarize_monthly_field,
    summarize_offices,
    summarize_projects,
)


ROOT = Path(__file__).resolve().parents[1]
NATIONAL_INDEX_PATH = ROOT / "data" / "generated" / "chile-summary.json"
DETAILS_SUMMARY_PATH = ROOT / "data" / "generated" / "chile-details-summary.json"
DATA_DIR = ROOT / "public" / "data" / "chile"
RAW_DIR = DATA_DIR / "raw"


def monthly_pending(deputy_id: str) -> dict[str, Any]:
    return {
        "availability": "not_published",
        "operational_expenses": empty_monthly_money(
            source_url=TRANSPARENCY_SOURCES["operational_expenses"].format(deputy_id=deputy_id),
            label="Gastos operacionales",
        ),
        "external_advisories": empty_monthly_money(
            source_url=TRANSPARENCY_SOURCES["external_advisories"].format(deputy_id=deputy_id),
            label="Asesorías externas",
        ),
        "flights": empty_monthly_money(
            source_url=TRANSPARENCY_SOURCES["flights"].format(deputy_id=deputy_id),
            label="Pasajes aéreos nacionales",
        ),
        "personnel_support": {"by_month": {}, "contracts_count": 0},
        "personnel_support_metadata": {
            "availability": "pending_national_backfill",
            "label": "Personal de apoyo",
            "reason": "La serie nacional comparable aún no ha sido publicada en una fuente automatizable.",
        },
    }


def profile(deputy: dict[str, Any]) -> dict[str, Any]:
    deputy_id = str(deputy["id"])
    return {
        "id": deputy_id,
        "name": deputy["name"],
        "district": deputy["district_label"],
        "region": deputy["region"],
        "period": "2026-2030",
        "source_url": deputy["profile_url"],
        "commissions_source_url": f"https://www.camara.cl/diputados/detalle/comisiones.aspx?prmId={deputy_id}",
        "territory_source_url": deputy["territory_source_url"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recolecta actividad legislativa nacional en una sola pasada.")
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--delay", type=float, default=0.25, help="Pausa mínima entre solicitudes oficiales.")
    parser.add_argument("--workers", type=int, default=5, help="Consultas simultáneas (máximo seguro: 6).")
    parser.add_argument("--dry-run", action="store_true", help="Valida la nómina sin consultar fuentes externas.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index = load_json(NATIONAL_INDEX_PATH, {})
    deputies = index.get("deputies", []) if isinstance(index, dict) else []
    if len(deputies) != 155:
        raise RuntimeError("El índice nacional debe contener 155 integrantes antes de recopilar fichas detalladas.")
    if args.dry_run:
        print(json.dumps({"year": args.year, "deputies": len(deputies), "districts": len({item['district'] for item in deputies})}, ensure_ascii=False))
        return

    retrieved_at = datetime.now(UTC).isoformat()
    workers = max(1, min(args.workers, 6))
    urls = {
        name: method_url(name, args.year) if "{year}" in str(METHODS[name]) else method_url(name)
        for name in METHODS
    }
    author_cache_path = RAW_DIR / f"national-author-cache-{args.year}.json"
    author_cache = load_json(author_cache_path, {"schema_version": 1, "sources": {}})
    if not isinstance(author_cache, dict):
        author_cache = {"schema_version": 1, "sources": {}}
    cache_sources = author_cache.setdefault("sources", {})

    open_data: dict[str, list[dict[str, Any]]] = {}
    detail_failures: dict[str, list[dict[str, str]]] = {}
    for source_name, element_name in (("motions", "ProyectoLey"), ("agreements", "ProyectoAcuerdo"), ("resolutions", "ProyectoResolucion")):
        annual_payload = request_text(urls[source_name], delay=args.delay)
        save_json(RAW_DIR / f"{source_name}-{args.year}.xml.json", {"retrieved_at": retrieved_at, "url": urls[source_name], "payload": annual_payload})
        annual_projects = parse_projects(annual_payload, element_name)
        open_data[source_name], detail_failures[source_name] = hydrate_authors(
            source_name,
            annual_projects,
            element_name,
            delay=args.delay,
            workers=workers,
            author_cache=cache_sources.setdefault(source_name, {}),
        )
    save_json(author_cache_path, author_cache)

    commissions_xml = request_text(urls["commissions"], delay=args.delay)
    save_json(RAW_DIR / "commissions.xml.json", {"retrieved_at": retrieved_at, "url": urls["commissions"], "payload": commissions_xml})
    commissions_by_deputy, commission_failures = hydrate_commissions(commissions_xml, delay=args.delay, workers=workers)
    sessions_xml = request_text(urls["sessions"], delay=args.delay)
    save_json(RAW_DIR / f"sessions-{args.year}.xml.json", {"retrieved_at": retrieved_at, "url": urls["sessions"], "payload": sessions_xml})
    attendance_by_deputy, attendance_failures = hydrate_attendance(parse_session_ids(sessions_xml), delay=args.delay, workers=workers)

    records: list[dict[str, Any]] = []
    for deputy in deputies:
        deputy_id = str(deputy["id"])
        records.append(
            {
                "profile": profile(deputy),
                "activity": {
                    "motions_by_month_and_state": summarize_projects(open_data["motions"], deputy_id),
                    "agreements_by_month_and_state": summarize_projects(open_data["agreements"], deputy_id),
                    "resolutions_by_month_and_state": summarize_projects(open_data["resolutions"], deputy_id),
                    "offices_by_month": summarize_offices(open_data["resolutions"], deputy_id),
                },
                "commissions": commissions_by_deputy.get(deputy_id, []),
                "attendance": attendance_by_deputy.get(
                    deputy_id,
                    {"sessions_recorded": 0, "present": 0, "not_present": 0, "unclassified": 0, "percentage": None, "by_type": {}},
                ),
                "transparency": monthly_pending(deputy_id),
                "retrieved_at": retrieved_at,
            }
        )

    records_by_district: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for deputy, record in zip(deputies, records, strict=True):
        records_by_district[int(deputy["district"])].append(record)
        save_json(DATA_DIR / "deputies" / f"{record['profile']['id']}.json", record)

    district_summaries = []
    for district, district_records in sorted(records_by_district.items()):
        attendance = [record["attendance"]["percentage"] for record in district_records if record["attendance"]["percentage"] is not None]
        district_summaries.append(
            {
                "district": district,
                "region": district_records[0]["profile"]["region"],
                "deputies_count": len(district_records),
                "deputies": [{"id": item["profile"]["id"], "name": item["profile"]["name"]} for item in district_records],
                "activity": {
                    "motions": summarize_district_activity(district_records, "motions_by_month_and_state"),
                    "agreements": summarize_district_activity(district_records, "agreements_by_month_and_state"),
                    "resolutions": summarize_district_activity(district_records, "resolutions_by_month_and_state"),
                    "offices": summarize_monthly_field(district_records, "offices_by_month"),
                },
                "attendance": {"average_percentage": round(sum(attendance) / len(attendance), 1) if attendance else None},
                "diet": {"monthly_gross_district_clp": DIET_2026["monthly_gross_per_deputy_clp"] * len(district_records)},
            }
        )
        save_json(DATA_DIR / "districts" / f"{district}.json", district_summaries[-1])

    attendance = [record["attendance"]["percentage"] for record in records if record["attendance"]["percentage"] is not None]
    summary = {
        "schema_version": 1,
        "retrieved_at": retrieved_at,
        "availability": "national_details_complete" if not any(detail_failures.values()) and not commission_failures and not attendance_failures else "national_details_partial",
        "deputies_with_details": len(records),
        "activity": {
            "motions": summarize_district_activity(records, "motions_by_month_and_state"),
            "agreements": summarize_district_activity(records, "agreements_by_month_and_state"),
            "resolutions": summarize_district_activity(records, "resolutions_by_month_and_state"),
            "offices": summarize_monthly_field(records, "offices_by_month"),
        },
        "attendance": {"average_percentage": round(sum(attendance) / len(attendance), 1) if attendance else None, "deputies_with_classified_records": len(attendance)},
        "districts": district_summaries,
        "detail_failures": detail_failures,
        "commission_detail_failures": commission_failures,
        "attendance_detail_failures": attendance_failures,
        "sources": urls,
    }
    save_json(DETAILS_SUMMARY_PATH, summary)
    save_json(DATA_DIR / "details-summary.json", summary)
    print(f"Fichas nacionales: {len(records)} diputadas y diputados en {len(district_summaries)} distritos.")


if __name__ == "__main__":
    main()
