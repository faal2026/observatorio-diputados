"use client";

import { useEffect, useMemo, useState } from "react";
import districtSummary from "../data/generated/distrito-8-summary.json";

type Metric = "gastos" | "asesorias" | "pasajes" | "personal" | "mociones" | "resoluciones" | "oficios";
type ActivityName = "motions" | "resolutions" | "offices";
type TransparencyName = "operational_expenses" | "external_advisories" | "flights" | "personnel_support";

const metricLabels: Record<Metric, { label: string; unit: string; activity?: ActivityName; transparency?: TransparencyName }> = {
  gastos: { label: "Gastos operacionales", unit: "CLP por mes", transparency: "operational_expenses" },
  asesorias: { label: "Asesorías externas", unit: "CLP por mes", transparency: "external_advisories" },
  pasajes: { label: "Pasajes aéreos", unit: "CLP por mes", transparency: "flights" },
  personal: { label: "Personal de apoyo", unit: "CLP por mes", transparency: "personnel_support" },
  mociones: { label: "Mociones", unit: "Número por mes", activity: "motions" },
  resoluciones: { label: "Resoluciones", unit: "Número por mes", activity: "resolutions" },
  oficios: { label: "Oficios enviados", unit: "Número por mes", activity: "offices" },
};

const sources = [
  "Datos Abiertos Legislativos: identidad, actividad legislativa y asistencia.",
  "Fichas oficiales vigentes: comisiones actuales de cada diputado(a).",
  "Fichas de transparencia: gastos, asesorías, pasajes y personal de apoyo.",
  "Transparencia Activa: dieta parlamentaria vigente.",
];

type MonthlyActivity = {
  by_month: Record<string, number>;
  total: number;
  months_with_records: number;
  average_per_deputy_per_month: number | null;
};

type MonthlyMoney = {
  by_month: Record<string, number>;
  latest_month: string | null;
  latest_amount: number | null;
  average_monthly: number | null;
  median_monthly: number | null;
  months_with_records: number;
  methodology?: string;
};

type DistrictSummary = {
  deputies_count: number;
  retrieved_at: string;
  deputies: { id: string; name: string }[];
  availability: string;
  activity?: { motions: MonthlyActivity; agreements: MonthlyActivity; resolutions: MonthlyActivity; offices: MonthlyActivity };
  attendance?: { average_percentage: number | null; deputies_with_classified_records: number };
  commissions?: { snapshot_retrieved_at?: string; snapshot_applied_to?: string[] };
  transparency?: Partial<Record<TransparencyName, MonthlyMoney>> & { personnel_support_metadata?: { availability: string; label?: string; methodology?: string; source_url?: string; snapshot_retrieved_at?: string; coverage?: string; reason?: string } };
  diet?: { monthly_gross_per_deputy_clp: number; monthly_gross_district_clp: number; valid_from: string; source_url: string; note: string };
};

type DeputyRecord = {
  profile: { id: string; name: string; district: string; region: string; period: string; commissions_source_url?: string };
  activity: {
    motions_by_month_and_state: Record<string, Record<string, number>>;
    agreements_by_month_and_state: Record<string, Record<string, number>>;
    resolutions_by_month_and_state: Record<string, Record<string, number>>;
    offices_by_month: Record<string, number>;
  };
  commissions?: string[];
  attendance?: { sessions_recorded: number; present: number; not_present: number; unclassified: number; percentage: number | null; by_type: Record<string, number> };
  transparency: { availability: string; personnel_support?: { by_month: Record<string, number>; contracts_count: number }; operational_expenses?: MonthlyMoney; external_advisories?: MonthlyMoney; flights?: MonthlyMoney; personnel_support_metadata?: { availability?: string; label?: string; methodology?: string; source_url?: string; snapshot_retrieved_at?: string; coverage?: string; reason?: string } };
};

const decimal = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 1 });
const currency = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });
const monthFormatter = new Intl.DateTimeFormat("es-CL", { month: "short", year: "numeric", timeZone: "UTC" });

function labelMonth(month: string) {
  const [year, number] = month.split("-").map(Number);
  return monthFormatter.format(new Date(Date.UTC(year, number - 1, 1))).replace(".", "");
}

function total(states: Record<string, number> | undefined) {
  return Object.values(states ?? {}).reduce((sum, value) => sum + value, 0);
}

function stateLabel(state: string) {
  if (state === "true") return "Admisible";
  if (state === "false") return "Inadmisible";
  return state;
}

function ActivityCell({ states }: { states: Record<string, number> | undefined }) {
  if (!states || total(states) === 0) return <>0</>;
  return <><strong>{total(states)}</strong><small className="activity-state">{Object.entries(states).map(([state, count]) => `${stateLabel(state)}: ${count}`).join(" · ")}</small></>;
}

function percentage(value: number | null | undefined) {
  return value == null ? "—" : `${decimal.format(value)}%`;
}

export default function Home() {
  const [metric, setMetric] = useState<Metric>("mociones");
  const [region, setRegion] = useState("");
  const [district, setDistrict] = useState("");
  const [deputy, setDeputy] = useState("");
  const [deputyRecord, setDeputyRecord] = useState<DeputyRecord | null>(null);
  const [profileMessage, setProfileMessage] = useState("");
  const summary = districtSummary as DistrictSummary;
  const selected = metricLabels[metric];
  const selectedDeputy = summary.deputies.find((item) => item.name === deputy);
  const activity = selected.activity ? summary.activity?.[selected.activity] : undefined;
  const money = selected.transparency ? summary.transparency?.[selected.transparency] : undefined;
  const series = Object.entries(activity?.by_month ?? money?.by_month ?? {});
  const maximum = Math.max(...series.map(([, value]) => value), 1);

  useEffect(() => {
    if (!selectedDeputy) {
      setDeputyRecord(null);
      setProfileMessage("");
      return;
    }

    let active = true;
    setDeputyRecord(null);
    setProfileMessage("Cargando actividad legislativa…");
    fetch(`data/distrito-8/deputies/${selectedDeputy.id}.json`)
      .then((response) => {
        if (!response.ok) throw new Error("La ficha no está disponible.");
        return response.json() as Promise<DeputyRecord>;
      })
      .then((record) => {
        if (active) {
          setDeputyRecord(record);
          setProfileMessage("");
        }
      })
      .catch(() => {
        if (active) setProfileMessage("No fue posible cargar esta ficha. Vuelve a intentarlo en unos segundos.");
      });

    return () => { active = false; };
  }, [selectedDeputy]);

  const detailMonths = useMemo(() => {
    if (!deputyRecord) return [];
    const months = new Set([
      ...Object.keys(deputyRecord.activity.motions_by_month_and_state),
      ...Object.keys(deputyRecord.activity.agreements_by_month_and_state),
      ...Object.keys(deputyRecord.activity.resolutions_by_month_and_state),
      ...Object.keys(deputyRecord.activity.offices_by_month),
      ...Object.keys(deputyRecord.transparency.personnel_support?.by_month ?? {}),
      ...Object.keys(deputyRecord.transparency.operational_expenses?.by_month ?? {}),
      ...Object.keys(deputyRecord.transparency.external_advisories?.by_month ?? {}),
      ...Object.keys(deputyRecord.transparency.flights?.by_month ?? {}),
    ]);
    return [...months].sort().reverse();
  }, [deputyRecord]);

  const averageMotions = summary.activity?.motions.average_per_deputy_per_month;
  const averageResolutions = summary.activity?.resolutions.average_per_deputy_per_month;
  const averageAttendance = summary.attendance?.average_percentage;
  const diet = summary.diet;
  const chartLabel = activity
    ? `${activity.total} registros legislativos en los meses publicados del piloto.`
    : money?.latest_amount != null
      ? `${money.methodology ?? "Monto mensual publicado."} Último mes: ${labelMonth(money.latest_month ?? "2026-01")}.`
      : `La serie de ${selected.label.toLocaleLowerCase("es-CL")} se incorporará al terminar la fase de transparencia.`;
  const personnelMetadata = summary.transparency?.personnel_support_metadata;

  return (
    <main>
      <header className="site-header">
        <p className="eyebrow">Piloto de datos públicos · Distrito 8</p>
        <h1>Observatorio Parlamentario</h1>
        <p className="intro">Un tablero para entender actividad legislativa, asistencia y transparencia parlamentaria con fuentes oficiales y metodología visible.</p>
      </header>

      <section className="status" aria-label="Estado del piloto">
        <span className="status-dot" aria-hidden="true" />
        <strong>{summary.availability === "phase_one_complete" ? "Actividad legislativa del Distrito 8 actualizada" : "Actividad legislativa actualizada parcialmente"}</strong>
        <span>Última recolección: {new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short" }).format(new Date(summary.retrieved_at))}. Los meses sin publicación se mostrarán como tales; nunca como $0.</span>
      </section>

      <section className="dashboard" aria-labelledby="dashboard-title">
        <div className="section-heading">
          <div><p className="eyebrow">Tablero general</p><h2 id="dashboard-title">Resumen mensual del distrito</h2></div>
          <label><span>Indicador de seguimiento</span><select value={metric} onChange={(event) => setMetric(event.target.value as Metric)}>{Object.entries(metricLabels).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}</select></label>
        </div>

        <div className="dashboard-grid">
          <div className="summary-grid">
            <MetricCard label="Diputados en cobertura" value={String(summary.deputies_count)} detail="Nómina vigente del Distrito 8" />
            <MetricCard label="Promedio de asistencia" value={percentage(averageAttendance)} detail={averageAttendance == null ? "Pendiente de la fuente oficial" : "Sesiones de sala con clasificación oficial"} />
            <MetricCard label="Promedio de mociones" value={averageMotions == null ? "—" : decimal.format(averageMotions)} detail="Por diputado(a) y mes con actividad" />
            <MetricCard label="Promedio de resoluciones" value={averageResolutions == null ? "—" : decimal.format(averageResolutions)} detail="Por diputado(a) y mes con actividad" />
            <MetricCard label={selected.label} value={activity ? String(activity.total) : money?.latest_amount != null ? currency.format(money.latest_amount) : "—"} detail={activity ? `Total del Distrito 8 · ${selected.unit}` : money?.latest_month ? `Último mes publicado: ${labelMonth(money.latest_month)}` : "Pendiente de publicación mensual"} />
            <MetricCard label="Dieta parlamentaria" value={diet ? currency.format(diet.monthly_gross_per_deputy_clp) : "—"} detail={diet ? "Bruta mensual vigente por diputado(a)" : "Monto bruto mensual vigente · pendiente"} />
          </div>

          <article className="chart-panel" aria-labelledby="chart-title">
            <div><p className="eyebrow">Seguimiento</p><h3 id="chart-title">{selected.label}</h3><p>{chartLabel}</p></div>
            {series.length ? (
              <div className="chart" role="img" aria-label={`Serie mensual de ${selected.label}`}>
                <div className="chart-lines" aria-hidden="true">{series.map(([month, value]) => <i key={month} style={{ height: `${Math.max(8, Math.round((value / maximum) * 100))}%` }} title={`${labelMonth(month)}: ${value}`} />)}</div>
                <div className="chart-axis">{series.map(([month, value]) => <span key={month}>{labelMonth(month)}<b>{value}</b></span>)}</div>
              </div>
            ) : <div className="chart-placeholder" role="img" aria-label="Serie pendiente de publicación"><span>Sin serie publicada aún</span></div>}
            {selected.transparency && personnelMetadata?.source_url ? <p className="source-note">{personnelMetadata.availability === "published_snapshot" ? "Respaldo de" : "Fuente:"} <a href={personnelMetadata.source_url} target="_blank" rel="noreferrer">directorio oficial de personal de apoyo</a>{personnelMetadata.snapshot_retrieved_at ? ` · corte ${personnelMetadata.snapshot_retrieved_at}` : ""}. {personnelMetadata.methodology}</p> : null}
          </article>
        </div>
      </section>

      <section className="district-view" aria-labelledby="district-title">
        <div><p className="eyebrow">Vista territorial</p><h2 id="district-title">Región Metropolitana · Distrito 8</h2><p>La versión completa incorporará el mapa nacional y permitirá fijar una región para revisar diputados, dieta y gastos mensuales agregados.</p></div>
        <dl className="territory-details"><div><dt>Región</dt><dd>Metropolitana de Santiago</dd></div><div><dt>Distrito</dt><dd>8</dd></div><div><dt>Comunas</dt><dd>Tiltil, Quilicura, Colina, Estación Central, Pudahuel, Lampa, Cerrillos y Maipú</dd></div><div><dt>Dieta bruta mensual</dt><dd>{diet ? currency.format(diet.monthly_gross_district_clp) : "Pendiente de publicación"}</dd></div></dl>
      </section>

      <section className="profile" aria-labelledby="profile-title">
        <div className="section-heading"><div><p className="eyebrow">Ficha individual</p><h2 id="profile-title">Detalle por diputado(a)</h2></div><span className="coverage-note">Actividad legislativa publicada durante 2026</span></div>
        <div className="filters">
          <label><span>Región</span><select value={region} onChange={(event) => setRegion(event.target.value)}><option value="">Seleccionar región</option><option>Región Metropolitana de Santiago</option></select></label>
          <label><span>Distrito</span><select value={district} onChange={(event) => setDistrict(event.target.value)} disabled={!region}><option value="">Seleccionar distrito</option><option>Distrito 8</option></select></label>
          <label><span>Diputado(a)</span><select value={deputy} onChange={(event) => setDeputy(event.target.value)} disabled={!district}><option value="">Seleccionar diputado(a)</option>{summary.deputies.map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
        </div>

        {deputyRecord ? <article className="profile-card"><div><p className="eyebrow">Ficha del piloto</p><h3>{deputyRecord.profile.name}</h3><p>{deputyRecord.profile.district} · {deputyRecord.profile.region} · {deputyRecord.profile.period}</p><h4>Asistencia a sala</h4><p>{percentage(deputyRecord.attendance?.percentage)} · {deputyRecord.attendance?.present ?? 0} presencias en {deputyRecord.attendance?.sessions_recorded ?? 0} registros de sesión.</p></div><div><h4>Comisiones actuales</h4>{deputyRecord.commissions?.length ? <><ul>{deputyRecord.commissions.map((commission) => <li key={commission}>{commission}</li>)}</ul><p className="source-note">Verificadas en <a href={deputyRecord.profile.commissions_source_url} target="_blank" rel="noreferrer">ficha oficial vigente</a>: {summary.commissions?.snapshot_retrieved_at ?? "fecha no indicada"}.</p></> : <p>La fuente oficial consultada aún no publica integrantes para esta actualización.</p>}<h4 className="profile-subheading">Cobertura de transparencia</h4>{deputyRecord.transparency.personnel_support?.by_month && Object.keys(deputyRecord.transparency.personnel_support.by_month).length ? <p>Personal de apoyo publicado para {deputyRecord.transparency.personnel_support_metadata?.coverage ?? "los meses disponibles"}. Son remuneraciones de contratos vigentes; no equivalen a gasto rendido. Gastos, asesorías y pasajes quedarán como “sin publicación” hasta que la Cámara libere esos meses.</p> : <p>La Cámara aún no publica transparencia mensual para esta nómina. El tablero conservará esos meses como pendientes, nunca como $0.</p>}</div></article> : <div className="empty-state">{profileMessage || "Elige región, distrito y diputado(a) para abrir su ficha."}</div>}

        <div className="table-wrap"><table><thead><tr><th>Mes</th><th>Mociones</th><th>Acuerdos</th><th>Resoluciones</th><th>Oficios</th><th>Asistencia total</th><th>Gastos</th><th>Asesorías</th><th>Pasajes</th><th>Personal</th></tr></thead><tbody>{detailMonths.length ? detailMonths.map((month) => <tr key={month}><td>{labelMonth(month)}</td><td><ActivityCell states={deputyRecord?.activity.motions_by_month_and_state[month]} /></td><td><ActivityCell states={deputyRecord?.activity.agreements_by_month_and_state[month]} /></td><td><ActivityCell states={deputyRecord?.activity.resolutions_by_month_and_state[month]} /></td><td>{deputyRecord?.activity.offices_by_month[month] ?? 0}</td><td>{percentage(deputyRecord?.attendance?.percentage)}</td><td>{MoneyCell(deputyRecord?.transparency.operational_expenses?.by_month[month])}</td><td>{MoneyCell(deputyRecord?.transparency.external_advisories?.by_month[month])}</td><td>{MoneyCell(deputyRecord?.transparency.flights?.by_month[month])}</td><td>{MoneyCell(deputyRecord?.transparency.personnel_support?.by_month[month])}</td></tr>) : <tr><td colSpan={10}>Elige un diputado(a) para ver los meses publicados.</td></tr>}</tbody></table></div>
      </section>

      <section className="methodology" aria-labelledby="methodology-title"><p className="eyebrow">Trazabilidad</p><h2 id="methodology-title">Cómo leer este tablero</h2><ul>{sources.map((source) => <li key={source}>{source}</li>)}</ul></section>
    </main>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <article className="metric-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function MoneyCell(value: number | undefined) {
  return value == null ? <span className="pending-cell">Pendiente</span> : currency.format(value);
}
