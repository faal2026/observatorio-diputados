#!/usr/bin/env python3
"""Recolector inicial para el piloto del Distrito 8.

No requiere librerías externas. Usa los servicios de Datos Abiertos de la
Cámara para actividad legislativa y las fichas públicas para validar el
territorio de cada diputada o diputado.

La primera fase genera la nómina, las fichas territoriales y las métricas
anuales que ya están disponibles en Datos Abiertos. Las fuentes mensuales de
transparencia se incorporan en una segunda fase mediante sus postbacks ASP.NET.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
# Estos archivos se publican tal como se descargan para que el tablero estático
# pueda mostrarlos y cualquier persona pueda revisar el dato de origen.
DATA_DIR = ROOT / "public" / "data" / "distrito-8"
RAW_DIR = DATA_DIR / "raw"
OPEN_DATA = "https://opendata.camara.cl/camaradiputados/WServices"
PROFILE_URL = "https://www.camara.cl/diputados/detalle/personaldepoyo.aspx?prmId={deputy_id}"
USER_AGENT = "ObservatorioParlamentarioPilot/0.1 (+https://felipealcerreca.lat)"

METHODS = {
    "deputies": ("WSDiputado.asmx/retornarDiputadosPeriodoActual", {}),
    "motions": ("WSLegislativo.asmx/retornarMocionesXAnno", {"prmAnno": "{year}"}),
    "agreements": ("WSProyectosAcuerdo.asmx/retornarProyectosAcuerdoXAnno", {"prmAnno": "{year}"}),
    "resolutions": ("WSProyectosResolucion.asmx/retornarProyectosResolucionXAnno", {"prmAnno": "{year}"}),
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    result = " ".join(unescape(value).split())
    return result or None


def request_text(url: str, *, delay: float) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/html"})
    with urlopen(request, timeout=45) as response:  # noqa: S310 - las URLs se definen arriba.
        payload = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    time.sleep(delay)
    return payload


def method_url(name: str, year: int | None = None) -> str:
    path, params = METHODS[name]
    resolved = {key: value.format(year=year) if "{year}" in value else value for key, value in params.items()}
    query = f"?{urlencode(resolved)}" if resolved else ""
    return f"{OPEN_DATA}/{path}{query}"


def child_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if local_name(child.tag) == name:
            return clean_text(child.text)
    return None


def descendant_text(element: ET.Element, names: Iterable[str]) -> str | None:
    wanted = set(names)
    for child in element.iter():
        if local_name(child.tag) in wanted:
            value = clean_text(child.text)
            if value:
                return value
    return None


def flatten(element: ET.Element) -> str:
    return " ".join(text for text in (clean_text(node.text) for node in element.iter()) if text)


def parse_xml(xml_text: str) -> ET.Element:
    return ET.fromstring(xml_text)


def parse_deputies(xml_text: str) -> list[dict[str, str]]:
    root = parse_xml(xml_text)
    deputies: list[dict[str, str]] = []
    for node in root.iter():
        if local_name(node.tag) != "Diputado":
            continue
        deputy_id = child_text(node, "Id")
        if not deputy_id:
            continue
        name_parts = [
            child_text(node, "Nombre"),
            child_text(node, "Nombre2"),
            child_text(node, "ApellidoPaterno"),
            child_text(node, "ApellidoMaterno"),
        ]
        deputies.append({"id": deputy_id, "name": " ".join(part for part in name_parts if part)})
    return deputies


def html_to_text(html: str) -> str:
    without_noise = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    return clean_text(re.sub(r"<[^>]+>", " ", without_noise)) or ""


def labelled_value(text: str, label: str, next_labels: Iterable[str]) -> str | None:
    marker = re.escape(label)
    endings = "|".join(re.escape(item) for item in next_labels)
    match = re.search(rf"{marker}\s*:?\s*(.+?)(?=\s*(?:{endings})\s*:|$)", text, flags=re.IGNORECASE)
    return clean_text(match.group(1)) if match else None


def profile_from_html(deputy: dict[str, str], html: str) -> dict[str, Any]:
    text = html_to_text(html)
    labels = ["Distrito", "Región", "Período", "Partido", "Bancada", "Contacto", "Trabajo Parlamentario"]
    values = {
        "district": labelled_value(text, "Distrito", labels[1:]),
        "region": labelled_value(text, "Región", labels[2:]),
        "period": labelled_value(text, "Período", labels[3:]),
        "party": labelled_value(text, "Partido", labels[4:]),
        "bench": labelled_value(text, "Bancada", labels[5:]),
    }
    return {**deputy, **values, "source_url": PROFILE_URL.format(deputy_id=deputy["id"])}


def parse_projects(xml_text: str, element_name: str) -> list[dict[str, Any]]:
    root = parse_xml(xml_text)
    projects: list[dict[str, Any]] = []
    for node in root.iter():
        if local_name(node.tag) != element_name:
            continue
        authors = next((child for child in node if local_name(child.tag) == "Autores"), None)
        projects.append(
            {
                "id": child_text(node, "Id"),
                "date": descendant_text(node, ("FechaIngreso", "Fecha")),
                "state": descendant_text(node, ("Estado", "Adminisible", "Admisible")),
                "authors_text": flatten(authors) if authors is not None else "",
                "source": flatten(node),
            }
        )
    return projects


def is_author(project: dict[str, Any], deputy_id: str) -> bool:
    return bool(re.search(rf"(?<!\d){re.escape(deputy_id)}(?!\d)", project["authors_text"]))


def month_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    for parser in (datetime.fromisoformat,):
        try:
            return parser(normalized).strftime("%Y-%m")
        except ValueError:
            pass
    return None


def summarize_projects(projects: list[dict[str, Any]], deputy_id: str) -> dict[str, dict[str, int]]:
    result: dict[str, Counter[str]] = defaultdict(Counter)
    for project in projects:
        if not is_author(project, deputy_id):
            continue
        month = month_key(project["date"])
        if month:
            state = project["state"] or "Sin estado publicado"
            result[month][state] += 1
    return {month: dict(counts) for month, counts in sorted(result.items())}


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect(args: argparse.Namespace) -> None:
    retrieved_at = datetime.now(UTC).isoformat()
    urls = {name: method_url(name, args.year) if "{year}" in str(METHODS[name]) else method_url(name) for name in METHODS}
    if args.dry_run:
        print(json.dumps({"district": args.district, "year": args.year, "urls": urls, "profile_url": PROFILE_URL}, indent=2))
        return

    deputies_xml = request_text(urls["deputies"], delay=args.delay)
    save_json(RAW_DIR / "deputies.xml.json", {"retrieved_at": retrieved_at, "url": urls["deputies"], "payload": deputies_xml})
    deputies = parse_deputies(deputies_xml)

    district_profiles: list[dict[str, Any]] = []
    for deputy in deputies:
        profile_html = request_text(PROFILE_URL.format(deputy_id=deputy["id"]), delay=args.delay)
        profile = profile_from_html(deputy, profile_html)
        if profile.get("district") and re.search(rf"\b{re.escape(str(args.district))}\b", profile["district"]):
            district_profiles.append(profile)

    open_data: dict[str, list[dict[str, Any]]] = {}
    for name, element_name in (("motions", "ProyectoLey"), ("agreements", "ProyectoAcuerdo"), ("resolutions", "ProyectoResolucion")):
        payload = request_text(urls[name], delay=args.delay)
        open_data[name] = parse_projects(payload, element_name)

    deputy_records = []
    for profile in district_profiles:
        deputy_id = profile["id"]
        deputy_records.append(
            {
                "profile": profile,
                "activity": {
                    "motions_by_month_and_state": summarize_projects(open_data["motions"], deputy_id),
                    "agreements_by_month_and_state": summarize_projects(open_data["agreements"], deputy_id),
                    "resolutions_by_month_and_state": summarize_projects(open_data["resolutions"], deputy_id),
                },
                "transparency": {"availability": "pending_second_phase", "reason": "monthly_postback_collection_not_run"},
                "retrieved_at": retrieved_at,
            }
        )

    for record in deputy_records:
        save_json(DATA_DIR / "deputies" / f"{record['profile']['id']}.json", record)

    summary = {
        "district": args.district,
        "year": args.year,
        "retrieved_at": retrieved_at,
        "deputies_count": len(deputy_records),
        "deputies": [{"id": item["profile"]["id"], "name": item["profile"]["name"]} for item in deputy_records],
        "availability": "phase_one_complete",
        "sources": urls,
    }
    save_json(DATA_DIR / "monthly-summary.json", summary)
    print(f"Distrito {args.district}: {len(deputy_records)} diputadas y diputados guardados en {DATA_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Recolecta la primera fase del piloto Distrito 8.")
    parser.add_argument("--district", type=int, default=8)
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--delay", type=float, default=0.8, help="Pausa mínima entre solicitudes, en segundos.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra las fuentes sin realizar solicitudes.")
    collect(parser.parse_args())


if __name__ == "__main__":
    main()
