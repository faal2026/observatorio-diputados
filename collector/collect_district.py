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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    "commissions": ("WSComision.asmx/retornarComisionesVigentes", {}),
    "sessions": ("WSSala.asmx/retornarSesionesXAnno", {"prmAnno": "{year}"}),
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

SESSION_ATTENDANCE_METHOD = "WSSala.asmx/retornarSesionAsistencia"
COMMISSION_DETAIL_METHOD = "WSComision.asmx/retornarComision"

# La dieta no es una asignación rendida por cada diputado/a: es una
# remuneración bruta mensual fijada para el cargo. Se mantiene separada de
# gastos operacionales, asesorías, pasajes y personal de apoyo.
DIET_2026 = {
    "monthly_gross_per_deputy_clp": 8_239_091,
    "valid_from": "2026-03-11",
    "source_url": "https://www.camara.cl/transparencia/doc/dieta_actualizada.pdf",
    "note": "Monto bruto mensual vigente para diputadas y diputados sin funciones de presidencia o vicepresidencia.",
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


def session_attendance_url(session_id: str) -> str:
    """Devuelve el detalle de asistencia de una sesión de Sala."""
    return f"{OPEN_DATA}/{SESSION_ATTENDANCE_METHOD}?{urlencode({'prmSesionId': session_id})}"


def commission_detail_url(commission_id: str) -> str:
    return f"{OPEN_DATA}/{COMMISSION_DETAIL_METHOD}?{urlencode({'prmComisionId': commission_id})}"


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


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


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
    workers: int,
    author_cache: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Completa autores y reutiliza los ya obtenidos en ejecuciones anteriores."""
    hydrated: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    pending: list[dict[str, Any]] = []

    for project in projects:
        project_id = str(project.get("id") or "")
        if not project_id:
            continue
        cached = author_cache.get(project_id)
        if cached:
            hydrated.append({**project, "author_ids": cached.get("author_ids", []), "authors_text": cached.get("authors_text", "")})
            continue
        pending.append(project)

    def fetch_project(project: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
        detail_url = project_detail_url(source_name, project)
        try:
            detail = parse_projects(request_text(detail_url, delay=delay), element_name)
        except RuntimeError as error:
            return None, {"id": str(project["id"]), "url": detail_url, "reason": str(error)}
        if not detail:
            return None, {"id": str(project["id"]), "url": detail_url, "reason": "El detalle no entregó un proyecto."}
        detailed_project = detail[0]
        merged = {**project, "author_ids": detailed_project["author_ids"], "authors_text": detailed_project["authors_text"]}
        return merged, None

    if pending:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(fetch_project, project) for project in pending]
            for future in as_completed(futures):
                hydrated_project, failure = future.result()
                if failure:
                    unavailable.append(failure)
                    continue
                if hydrated_project:
                    project_id = str(hydrated_project["id"])
                    author_cache[project_id] = {
                        "author_ids": hydrated_project["author_ids"],
                        "authors_text": hydrated_project["authors_text"],
                    }
                    hydrated.append(hydrated_project)

    return hydrated, sorted(unavailable, key=lambda item: item["id"])


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


def parse_commissions(xml_text: str) -> dict[str, list[str]]:
    """Obtiene las comisiones vigentes de cada diputado/a desde la nómina oficial."""
    result: dict[str, list[str]] = defaultdict(list)
    root = parse_xml(xml_text)
    for commission in root.iter():
        if local_name(commission.tag) != "Comision":
            continue
        commission_name = child_text(commission, "NombreWeb") or child_text(commission, "Nombre")
        members = next((child for child in commission if local_name(child.tag) == "Integrantes"), None)
        if not commission_name or members is None:
            continue
        for membership in members:
            if local_name(membership.tag) != "DiputadoIntegrante":
                continue
            deputy = next((child for child in membership if local_name(child.tag) == "Diputado"), None)
            deputy_id = child_text(deputy, "Id") if deputy is not None else None
            if deputy_id and commission_name not in result[deputy_id]:
                result[deputy_id].append(commission_name)
    return {deputy_id: sorted(names) for deputy_id, names in result.items()}


def parse_commission_ids(xml_text: str) -> list[str]:
    root = parse_xml(xml_text)
    return list(dict.fromkeys(child_text(commission, "Id") for commission in root.iter() if local_name(commission.tag) == "Comision" and child_text(commission, "Id")))


def hydrate_commissions(xml_text: str, *, delay: float, workers: int) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    """La consulta resumida no expande integrantes; se obtienen desde cada comisión."""
    combined: dict[str, list[str]] = defaultdict(list)
    for deputy_id, names in parse_commissions(xml_text).items():
        combined[deputy_id].extend(names)
    failures: list[dict[str, str]] = []

    def fetch_commission(commission_id: str) -> tuple[dict[str, list[str]] | None, dict[str, str] | None]:
        url = commission_detail_url(commission_id)
        try:
            return parse_commissions(request_text(url, delay=delay)), None
        except RuntimeError as error:
            return None, {"id": commission_id, "url": url, "reason": str(error)}

    commission_ids = parse_commission_ids(xml_text)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_commission, commission_id) for commission_id in commission_ids]
        for future in as_completed(futures):
            memberships, failure = future.result()
            if failure:
                failures.append(failure)
                continue
            for deputy_id, names in (memberships or {}).items():
                for name in names:
                    if name not in combined[deputy_id]:
                        combined[deputy_id].append(name)
    return {deputy_id: sorted(names) for deputy_id, names in combined.items()}, sorted(failures, key=lambda item: item["id"])


def parse_session_ids(xml_text: str) -> list[str]:
    """Extrae los ids del listado anual; la asistencia viene en otra operación."""
    root = parse_xml(xml_text)
    session_ids: list[str] = []
    for session in root.iter():
        if local_name(session.tag) not in {"Sesion", "SesionSala"}:
            continue
        session_id = child_text(session, "Id")
        if session_id and session_id not in session_ids:
            session_ids.append(session_id)
    return session_ids


def attendance_kind(value: str | None) -> str:
    """Clasifica la etiqueta oficial sin asumir que una ausencia es asistencia."""
    label = normalized(value or "")
    if "presente" in label or "asiste" in label:
        return "present"
    if any(word in label for word in ("ausente", "justific", "permiso", "licencia", "pareo")):
        return "not_present"
    return "unclassified"


def parse_attendance(xml_text: str) -> dict[str, dict[str, Any]]:
    """Resume asistencia de sala; conserva los tipos para que el cálculo sea auditable."""
    records: dict[str, dict[str, Any]] = defaultdict(lambda: {"sessions_recorded": 0, "present": 0, "not_present": 0, "unclassified": 0, "by_type": Counter()})
    root = parse_xml(xml_text)
    for session in root.iter():
        if local_name(session.tag) not in {"Sesion", "SesionSala"}:
            continue
        attendance_list = next((child for child in session if local_name(child.tag) == "ListadoAsistencia"), None)
        if attendance_list is None:
            continue
        session_deputies: set[str] = set()
        for attendance in attendance_list:
            if local_name(attendance.tag) != "Asistencia":
                continue
            deputy = next((child for child in attendance if local_name(child.tag) == "Diputado"), None)
            deputy_id = child_text(deputy, "Id") if deputy is not None else None
            if not deputy_id or deputy_id in session_deputies:
                continue
            session_deputies.add(deputy_id)
            attendance_type_node = next((child for child in attendance if local_name(child.tag) == "TipoAsistencia"), None)
            attendance_type = flatten(attendance_type_node) if attendance_type_node is not None else None
            attendance_type = attendance_type or "Sin tipo publicado"
            kind = attendance_kind(attendance_type)
            record = records[deputy_id]
            record["sessions_recorded"] += 1
            record[kind] += 1
            record["by_type"][attendance_type] += 1

    result: dict[str, dict[str, Any]] = {}
    for deputy_id, record in records.items():
        denominator = record["sessions_recorded"] - record["unclassified"]
        result[deputy_id] = {
            "sessions_recorded": record["sessions_recorded"],
            "present": record["present"],
            "not_present": record["not_present"],
            "unclassified": record["unclassified"],
            "percentage": round(record["present"] * 100 / denominator, 1) if denominator else None,
            "by_type": dict(sorted(record["by_type"].items())),
        }
    return result


def hydrate_attendance(session_ids: list[str], *, delay: float, workers: int) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Consulta el detalle de cada sesión sin bloquear la publicación por fallas aisladas."""
    combined: dict[str, dict[str, Any]] = {}
    unavailable: list[dict[str, str]] = []
    def fetch_session(session_id: str) -> tuple[dict[str, dict[str, Any]] | None, dict[str, str] | None]:
        detail_url = session_attendance_url(session_id)
        try:
            return parse_attendance(request_text(detail_url, delay=delay)), None
        except RuntimeError as error:
            return None, {"id": session_id, "url": detail_url, "reason": str(error)}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_session, session_id) for session_id in session_ids]
        for future in as_completed(futures):
            session_records, failure = future.result()
            if failure:
                unavailable.append(failure)
                continue
            for deputy_id, record in (session_records or {}).items():
                target = combined.setdefault(
                    deputy_id,
                    {"sessions_recorded": 0, "present": 0, "not_present": 0, "unclassified": 0, "by_type": Counter()},
                )
                for field in ("sessions_recorded", "present", "not_present", "unclassified"):
                    target[field] += record[field]
                target["by_type"].update(record["by_type"])

    result: dict[str, dict[str, Any]] = {}
    for deputy_id, record in combined.items():
        denominator = record["sessions_recorded"] - record["unclassified"]
        result[deputy_id] = {
            "sessions_recorded": record["sessions_recorded"],
            "present": record["present"],
            "not_present": record["not_present"],
            "unclassified": record["unclassified"],
            "percentage": round(record["present"] * 100 / denominator, 1) if denominator else None,
            "by_type": dict(sorted(record["by_type"].items())),
        }
    return result, sorted(unavailable, key=lambda item: item["id"])


def summarize_district_activity(deputy_records: list[dict[str, Any]], activity_key: str) -> dict[str, Any]:
    """Agrega una actividad mensual sin convertir ausencias de datos en gastos o actividad ficticia."""
    by_month: Counter[str] = Counter()
    for record in deputy_records:
        for month, states in record["activity"][activity_key].items():
            by_month[month] += sum(states.values())

    series = dict(sorted(by_month.items()))
    total = sum(series.values())
    months_with_records = len(series)
    average = total / (len(deputy_records) * months_with_records) if deputy_records and months_with_records else None
    return {
        "by_month": series,
        "total": total,
        "months_with_records": months_with_records,
        "average_per_deputy_per_month": average,
    }


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
    author_cache_path = RAW_DIR / f"author-cache-{args.year}.json"
    author_cache_payload = load_json(author_cache_path, {"schema_version": 1, "sources": {}})
    if not isinstance(author_cache_payload, dict):
        author_cache_payload = {"schema_version": 1, "sources": {}}
    author_cache_sources = author_cache_payload.setdefault("sources", {})
    workers = max(1, min(args.workers, 6))
    for name, element_name in (("motions", "ProyectoLey"), ("agreements", "ProyectoAcuerdo"), ("resolutions", "ProyectoResolucion")):
        payload = request_text(urls[name], delay=args.delay)
        annual_projects = parse_projects(payload, element_name)
        source_cache = author_cache_sources.setdefault(name, {})
        open_data[name], detail_failures[name] = hydrate_authors(
            name,
            annual_projects,
            element_name,
            delay=args.delay,
            workers=workers,
            author_cache=source_cache,
        )
    save_json(author_cache_path, author_cache_payload)

    commissions_xml = request_text(urls["commissions"], delay=args.delay)
    commissions_by_deputy, commission_failures = hydrate_commissions(commissions_xml, delay=args.delay, workers=workers)
    annual_sessions = request_text(urls["sessions"], delay=args.delay)
    attendance_by_deputy, attendance_failures = hydrate_attendance(parse_session_ids(annual_sessions), delay=args.delay, workers=workers)

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
                "commissions": commissions_by_deputy.get(deputy_id, []),
                "attendance": attendance_by_deputy.get(
                    deputy_id,
                    {"sessions_recorded": 0, "present": 0, "not_present": 0, "unclassified": 0, "percentage": None, "by_type": {}},
                ),
                "transparency": {"availability": "pending_second_phase", "reason": "monthly_postback_collection_not_run"},
                "retrieved_at": retrieved_at,
            }
        )

    for record in deputy_records:
        save_json(DATA_DIR / "deputies" / f"{record['profile']['id']}.json", record)

    attendance_percentages = [record["attendance"]["percentage"] for record in deputy_records if record["attendance"]["percentage"] is not None]
    summary = {
        "district": args.district,
        "year": args.year,
        "retrieved_at": retrieved_at,
        "deputies_count": len(deputy_records),
        "deputies": [{"id": item["profile"]["id"], "name": item["profile"]["name"]} for item in deputy_records],
        "activity": {
            "motions": summarize_district_activity(deputy_records, "motions_by_month_and_state"),
            "agreements": summarize_district_activity(deputy_records, "agreements_by_month_and_state"),
            "resolutions": summarize_district_activity(deputy_records, "resolutions_by_month_and_state"),
        },
        "attendance": {
            "average_percentage": round(sum(attendance_percentages) / len(attendance_percentages), 1) if attendance_percentages else None,
            "deputies_with_classified_records": len(attendance_percentages),
            "session_detail_failures": attendance_failures,
        },
        "commissions": {"detail_failures": commission_failures},
        "diet": {
            **DIET_2026,
            "monthly_gross_district_clp": DIET_2026["monthly_gross_per_deputy_clp"] * len(deputy_records),
            "deputies_counted": len(deputy_records),
        },
        "availability": "phase_one_complete" if not any(detail_failures.values()) and not commission_failures else "phase_one_partial",
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
    parser.add_argument("--workers", type=int, default=4, help="Consultas oficiales simultáneas (máximo seguro: 6).")
    parser.add_argument("--dry-run", action="store_true", help="Muestra las fuentes sin realizar solicitudes.")
    collect(parser.parse_args())


if __name__ == "__main__":
    main()
