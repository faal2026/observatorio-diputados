#!/usr/bin/env python3
"""Construye el índice territorial nacional de diputadas y diputados vigentes.

Es una recolección ligera: consulta una sola vez el servicio oficial de la
Cámara, asigna cada persona a su distrito y región, y no descarga todavía las
fichas legislativas individuales. Eso permite publicar el mapa nacional rápido
y dejar la carga detallada para procesos por zona y con caché.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
REGIONS_PATH = ROOT / "data" / "chile-regions.json"
OUTPUT_PATH = ROOT / "data" / "generated" / "chile-summary.json"
RAW_PATH = ROOT / "public" / "data" / "chile" / "raw" / "diputados-periodo-actual.xml.json"
SOURCE_URL = "https://opendata.camara.cl/camaradiputados/WServices/WSDiputado.asmx/retornarDiputadosPeriodoActual?"
DIET_MONTHLY_CLP = 8_239_091
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ObservatorioParlamentario/1.0)",
    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(node: ET.Element | None, name: str) -> str:
    if node is None:
        return ""
    for child in node:
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def child(node: ET.Element, name: str) -> ET.Element | None:
    return next((item for item in node if local_name(item.tag) == name), None)


def request_text(url: str) -> str:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=45) as response:  # noqa: S310 - URL fija arriba.
        return response.read().decode("utf-8-sig")


def parse_roster(xml_text: str, regions: list[dict[str, object]]) -> list[dict[str, object]]:
    district_to_region = {
        district: region
        for region in regions
        for district in region["districts"]  # type: ignore[index]
    }
    root = ET.fromstring(xml_text)
    roster: list[dict[str, object]] = []
    for item in root.iter():
        if local_name(item.tag) != "DiputadoPeriodo":
            continue
        deputy = child(item, "Diputado")
        district_node = child(item, "Distrito")
        deputy_id = child_text(deputy, "Id")
        district_number = child_text(district_node, "Numero")
        if not deputy_id or not district_number:
            continue
        district = int(district_number)
        region = district_to_region.get(district)
        if not region:
            raise RuntimeError(f"Distrito {district} no está definido en chile-regions.json")
        names = [
            child_text(deputy, "Nombre"),
            child_text(deputy, "Nombre2"),
            child_text(deputy, "ApellidoPaterno"),
            child_text(deputy, "ApellidoMaterno"),
        ]
        roster.append(
            {
                "id": deputy_id,
                "name": " ".join(part for part in names if part),
                "district": district,
                "district_label": f"Distrito {district}",
                "region_code": region["code"],
                "region": region["name"],
                "profile_url": f"https://www.camara.cl/diputados/detalle/biografia.aspx?prmId={deputy_id}",
            }
        )
    return sorted(roster, key=lambda item: (int(item["district"]), str(item["name"])))


def save_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    regions = json.loads(REGIONS_PATH.read_text(encoding="utf-8"))
    retrieved_at = datetime.now(UTC).isoformat()
    xml_text = request_text(SOURCE_URL)
    roster = parse_roster(xml_text, regions)
    if len(roster) != 155:
        raise RuntimeError(f"La nómina oficial devolvió {len(roster)} integrantes; se esperaban 155.")

    by_region = {region["code"]: [] for region in regions}
    for deputy in roster:
        by_region[deputy["region_code"]].append(deputy)

    summary_regions = [
        {
            **region,
            "deputies_count": len(by_region[region["code"]]),
            "diet_monthly_clp": len(by_region[region["code"]]) * DIET_MONTHLY_CLP,
            "activity_availability": "pending_national_backfill",
            "transparency_availability": "pending_national_backfill",
        }
        for region in regions
    ]
    summary = {
        "schema_version": 1,
        "retrieved_at": retrieved_at,
        "availability": "national_index_complete",
        "source_url": SOURCE_URL.rstrip("?"),
        "deputies_count": len(roster),
        "diet_monthly_clp": DIET_MONTHLY_CLP,
        "deputies": roster,
        "regions": summary_regions,
    }
    save_json(RAW_PATH, {"retrieved_at": retrieved_at, "url": SOURCE_URL, "payload": xml_text})
    save_json(OUTPUT_PATH, summary)
    save_json(ROOT / "public" / "data" / "chile" / "index.json", summary)
    print(f"Índice nacional: {len(roster)} diputadas y diputados en {len(regions)} regiones.")


if __name__ == "__main__":
    main()
