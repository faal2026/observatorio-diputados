#!/usr/bin/env python3
"""Recolector inicial para el piloto del Distrito 8.

No requiere librerías externas. Usa los servicios de Datos Abiertos de la
Cámara para identidad y actividad legislativa. La nómina territorial se
mantiene como una lista explícita basada en el reporte oficial de la Biblioteca
del Congreso Nacional, porque la ficha individual de la Cámara bloquea
solicitudes originadas desde GitHub Actions.

La primera fase genera la nómina y las métricas disponibles en Datos Abiertos.
Las fuentes mensuales de transparencia se incorporan en una segunda fase.
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
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
# Estos archivos se publican tal como se descargan para que el tablero estático
# pueda mostrarlos y cualquier persona pueda revisar el dato de origen.
DATA_DIR = ROOT / "public" / "data" / "distrito-8"
RAW_DIR = DATA_DIR / "raw"
BUILD_DATA_DIR = ROOT / "data" / "generated"
OPEN_DATA = "https://opendata.camara.cl/camaradiputados/WServices"
PROFILE_URL = "https://www.camara.cl/diputados/detalle/personaldepoyo.aspx?prmId={deputy_id}"
DISTRICT_8_ROSTER_SOURCE = "https://www.bcn.cl/siit/reportesdistritales/pdf_distrito.html?anno_r=2026&distrito=8"

# Se usan nombre y apellido para no confundir homónimos al cruzar la nómina
# distrital con los identificadores oficiales de Datos Abiertos.
DISTRICT_8_IDENTIFIERS = (
    ("agustin", "romero"),
    ("cristian", "contreras"),
    ("enrique", "bassaletti"),
    ("gustavo", "gatica"),
    ("marcos", "barraza"),
    ("mario", "olavarria"),
    ("pier", "karlezi"),
    ("tatiana", "urrutia"),
)
# Las fuentes públicas de la Cámara rechazan algunos agentes automatizados.
# Se usan cabeceras equivalentes a una visita web normal, sin autenticación ni
# evasión de controles de acceso.
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Referer": "https://www.camara.cl/",
}

METHODS = {
    "deputies": ("WSDiputado.asmx/retornarDiputadosPeriodoActual", {}),
    "motions": ("WSLegislativo.asmx/retornarMocionesXAnno", {"prmAnno": "{year}"}),
    "agreements": ("WSProyectosAcuerdo.asmx/retornarProyectosAcuerdoXAnno", {"prmAnno": "{year}"}),
    "resolutions": ("WSProyectosResolucion.asmx/retornarProyectosResolucionXAnno", {"prmAnno": "{year}"}),
}

DETAIL_METHODS = {
    # El servicio legislativo busca mociones por número de boletín, no por Id.
    "motions": ("WSLegislativo.asmx/retornarProyectoLey", "prmNumeroBoletin", "bulletin"),
    "agreements": ("WSProyectosAcuerdo.asmx/retornarProyectoAcuerdo", "prmProyectoAcuerdoId", "id"),
    "resolutions": ("WSProyectosResolucion.asmx/retornarProyectoResolucion", "prmProyectoResolucionId", "id"),
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    result = " ".join(unescape(value).split())
    return result or None


def normalized(value: str) -> str:
    replacements = str.maketrans("áéíóúüñ", "aeiouun")
    return value.lower().translate(replacements)


def request_text(url: str, *, delay: float, retries: int = 2) -> str:
    request = Request(url, headers=REQUEST_HEADERS)
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=45) as response:  # noqa: S310 - las URLs se definen arriba.
                payload = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            time.sleep(delay)
            return payload
        except HTTPError as error:
            # Errores de parámetro o acceso no mejoran esperando; los errores
            # transitorios del servidor sí se reintentan con pausa creciente.
            if error.code < 500 and error.code != 429:
                raise RuntimeError(f"La fuente oficial rechazó la consulta ({error.code}) en {url}") from error
            last_error: Exception = error
        except URLError as error:
            last_error = error

        if attempt < retries - 1:
            time.sleep((attempt + 1) * 3)

    raise RuntimeError(f"La fuente oficial no respondió después de {retries} intentos en {url}") from last_error


def method_url(name: str, year: int | None = None) -> str:
    path, params = METHODS[name]
    resolved = {key: value.format(year=year) if "{year}" in value else value for key, value in params.items()}
    query = f"?{urlencode(resolved)}" if resolved else ""
    return f"{OPEN_DATA}/{path}{query}"


def project_detail_url(name: str, project: dict[str, Any]) -> str:
    path, parameter_name, project_key = DETAIL_METHODS[name]
    project_value = project.get(project_key)
    if not project_value:
        raise ValueError(f"No hay {project_key} para consultar el detalle de {name}.")
    return f"{OPEN_DATA}/{path}?{urlencode({parameter_name: project_value})}"


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


def belongs_to_district_8(deputy: dict[str, str]) -> bool:
    name = normalized(deputy["name"])
    return any(given_name in name and family_name in name for given_name, family_name in DISTRICT_8_IDENTIFIERS)


def profile_from_roster(deputy: dict[str, str]) -> dict[str, Any]:
    return {
        **deputy,
        "district": "Distrito 8",
        "region": "Región Metropolitana de Santiago",
        "period": "2026-2030",
        "party": None,
        "bench": None,
        "source_url": PROFILE_URL.format(deputy_id=deputy["id"]),
        "territory_source_url": DISTRICT_8_ROSTER_SOURCE,
    }


def parse_projects(xml_text: str, element_name: str) -> list[dict[str, Any]]:
    root = parse_xml(xml_text)
    projects: list[dict[str, Any]] = []
    for node in root.iter():
        if local_name(node.tag) != element_name:
            continue
        authors = next((child for child in node if local_name(child.tag) == "Autores"), None)
        author_ids: list[str] = []
        if authors is not None:
            for author in authors.iter():
                if local_name(author.tag) != "Diputado":
                    continue
                author_id = child_text(author, "Id")
                if author_id:
                    author_ids.append(author_id)
        projects.append(
            {
                "id": child_text(node, "Id"),
                "bulletin": child_text(node, "NumeroBoletin"),
                "date": descendant_text(node, ("FechaIngreso", "Fecha")),
                "state": descendant_text(node, ("Estado", "Adminisible", "Admisible")),
                "authors_text": flatten(authors) if authors is not None else "",
                "author_ids": author_ids,
                "source": flatten(node),
            }
        )
    return projects


def is_author(project: dict[str, Any], deputy_id: str) -> bool:
    return deputy_id in project.get("author_ids", []) or bool(re.search(rf"(?<!\d){re.escape(deputy_id)}(?!\d)", project["authors_text"]))


def hydrate_authors(
    source_name: str,
    projects: list[dict[str, Any]],
    element_name: str,
    *,
    delay: float,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Completa los autores que no vienen expandidos en la respuesta anual."""
    hydrated: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    for project in projects:
        if not project.get("id"):
            continue
        detail_url = project_detail_url(source_name, project)
        try:
            detail = parse_projects(request_text(detail_url, delay=delay), element_name)
        except RuntimeError as error:
            unavailable.append({"id": str(project["id"]), "url": detail_url, "reason": str(error)})
            continue
        if not detail:
            unavailable.append({"id": str(project["id"]), "url": detail_url, "reason": "El detalle no entregó un proyecto."})
            continue
        hydrated.append(detail[0])
    return hydrated, unavailable


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

    if args.district != 8:
        raise ValueError("Este piloto solo tiene configurada la nómina del Distrito 8.")

    district_profiles = [profile_from_roster(deputy) for deputy in deputies if belongs_to_district_8(deputy)]
    if len(district_profiles) != len(DISTRICT_8_IDENTIFIERS):
        found_names = ", ".join(profile["name"] for profile in district_profiles) or "ninguno"
        raise RuntimeError(
            f"La nómina oficial de Datos Abiertos no coincidió con el Distrito 8: se encontraron {len(district_profiles)} de "
            f"{len(DISTRICT_8_IDENTIFIERS)} integrantes ({found_names})."
        )

    open_data: dict[str, list[dict[str, Any]]] = {}
    detail_failures: dict[str, list[dict[str, str]]] = {}
    for name, element_name in (("motions", "ProyectoLey"), ("agreements", "ProyectoAcuerdo"), ("resolutions", "ProyectoResolucion")):
        payload = request_text(urls[name], delay=args.delay)
        annual_projects = parse_projects(payload, element_name)
        open_data[name], detail_failures[name] = hydrate_authors(name, annual_projects, element_name, delay=args.delay)

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
        "availability": "phase_one_complete" if not any(detail_failures.values()) else "phase_one_partial",
        "detail_failures": detail_failures,
        "sources": {**urls, "district_roster": DISTRICT_8_ROSTER_SOURCE},
    }
    save_json(DATA_DIR / "monthly-summary.json", summary)
    save_json(BUILD_DATA_DIR / "distrito-8-summary.json", summary)
    print(f"Distrito {args.district}: {len(deputy_records)} diputadas y diputados guardados en {DATA_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Recolecta la primera fase del piloto Distrito 8.")
    parser.add_argument("--district", type=int, default=8)
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--delay", type=float, default=1.0, help="Pausa mínima entre solicitudes, en segundos.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra las fuentes sin realizar solicitudes.")
    collect(parser.parse_args())


if __name__ == "__main__":
    main()
