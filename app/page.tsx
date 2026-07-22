"use client";

import { useEffect, useMemo, useState } from "react";
import districtSummary from "../data/generated/distrito-8-summary.json";
import nationalSummary from "../data/generated/chile-summary.json";
import nationalDetailsSummary from "../data/generated/chile-details-summary.json";

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

const nationalMetricLabels: Record<ActivityName, string> = {
  motions: "Mociones",
  resolutions: "Resoluciones",
  offices: "Oficios enviados",
};

const TRANSPARENCY_API_URL = "https://observatorio-transparencia.falcerrecalapostol.workers.dev/v1/transparency";

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
  coverage_by_month?: Record<string, number>;
  metadata?: {
    availability?: string;
    label?: string;
    source_url?: string;
    source_file?: string;
    source_files?: string[];
    imported_at?: string;
    last_imported_at?: string | null;
  };
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

type NationalRegion = {
  code: string;
  name: string;
  districts: number[];
  deputies_count: number | null;
  diet_monthly_clp?: number;
  activity_availability?: string;
  transparency_availability?: string;
};

type NationalDeputy = {
  id: string;
  name: string;
  district: number;
  district_label: string;
  region_code: string;
  region: string;
};

type NationalSummary = {
  retrieved_at: string | null;
  availability: string;
  deputies_count: number | null;
  diet_monthly_clp?: number;
  deputies: NationalDeputy[];
  regions: NationalRegion[];
};

type OfficialTransparencyImport = {
  category: TransparencyName;
  month: string;
  file: string;
  rows_read: number;
  deputies_matched: number;
  unmatched_names: string[];
};

type NationalTransparency = Partial<Record<TransparencyName, MonthlyMoney>> & {
  month_requested?: string;
  failures?: unknown[];
  official_imports?: OfficialTransparencyImport[];
  retrieved_at?: string;
};

type NationalDetailsSummary = {
  availability: string;
  deputies_with_details: number;
  activity?: Partial<Record<ActivityName, MonthlyActivity>>;
  attendance?: { average_percentage?: number | null; deputies_with_classified_records?: number };
  transparency?: NationalTransparency;
  districts?: Array<{
    district: number;
    region: string;
    deputies_count: number;
    activity?: Partial<Record<ActivityName, MonthlyActivity>>;
    attendance?: { average_percentage?: number | null };
    transparency?: Partial<Record<TransparencyName, MonthlyMoney>>;
  }>;
};

type WorkerTransparencyCategory = {
  availability?: string;
  reason?: string;
  by_deputy?: Record<string, number>;
  national_total_clp?: number;
  deputies_with_records?: number;
  methodology?: string;
};

type WorkerTransparencySnapshot = {
  month?: string;
  retrieved_at?: string;
  categories?: {
    external_advisories?: WorkerTransparencyCategory;
    personnel_support?: WorkerTransparencyCategory;
  };
};

const decimal = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 1 });
const currency = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });
const monthFormatter = new Intl.DateTimeFormat("es-CL", { month: "short", year: "numeric", timeZone: "UTC" });
const collectionDateFormatter = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" });

function clp(value: number) {
  return `${currency.format(value)} CLP`;
}

function labelMonth(month: string) {
  const [year, number] = month.split("-").map(Number);
  return monthFormatter.format(new Date(Date.UTC(year, number - 1, 1))).replace(".", "");
}

function latestPublished(byMonth: Record<string, number> | undefined) {
  const month = Object.keys(byMonth ?? {}).sort().at(-1);
  return month && byMonth ? { month, value: byMonth[month] } : null;
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
  return <><strong>{decimal.format(total(states))}</strong><small className="activity-state">{Object.entries(states).map(([state, count]) => `${stateLabel(state)}: ${decimal.format(count)}`).join(" · ")}</small></>;
}

function percentage(value: number | null | undefined) {
  return value == null ? "—" : `${decimal.format(value)}%`;
}

export default function Home() {
  const [metric, setMetric] = useState<Metric>("mociones");
  const [nationalMetric, setNationalMetric] = useState<ActivityName>("motions");
  const [region, setRegion] = useState("");
  const [hoverRegion, setHoverRegion] = useState("");
  const [district, setDistrict] = useState("");
  const [deputy, setDeputy] = useState("");
  const [deputyRecord, setDeputyRecord] = useState<DeputyRecord | null>(null);
  const [profileMessage, setProfileMessage] = useState("");
  const [workerTransparency, setWorkerTransparency] = useState<WorkerTransparencySnapshot | null>(null);
  const summary = districtSummary as DistrictSummary;
  const national = nationalSummary as NationalSummary;
  const nationalDetails = nationalDetailsSummary as NationalDetailsSummary;
  const selected = metricLabels[metric];
  const nationalRegions = national.regions;
  const nationalDeputies = useMemo(() => national.deputies.length ? national.deputies : summary.deputies.map((item) => ({
    id: item.id,
    name: item.name,
    district: 8,
    district_label: "Distrito 8",
    region_code: "metropolitana",
    region: "Metropolitana de Santiago",
  })), [national.deputies, summary.deputies]);
  const selectedRegion = nationalRegions.find((item) => item.code === region);
  const mapRegion = nationalRegions.find((item) => item.code === hoverRegion) ?? selectedRegion;
  const districtOptions = selectedRegion?.districts ?? [];
  const availableDeputies = nationalDeputies.filter((item) => item.region_code === region && item.district === Number(district));
  const selectedDeputy = availableDeputies.find((item) => item.name === deputy);
  const workerAdvisories = workerTransparency?.categories?.external_advisories;
  const workerPersonnel = workerTransparency?.categories?.personnel_support;
  const workerMonth = workerTransparency?.month;
  const workerDataMonth = workerMonth && (workerAdvisories?.national_total_clp != null || workerPersonnel?.national_total_clp != null) ? workerMonth : undefined;
  const workerDistrictTotal = (category: WorkerTransparencyCategory | undefined) => workerDataMonth && category?.national_total_clp != null
    ? nationalDeputies.filter((item) => item.district === 8).reduce((sum, item) => sum + (category.by_deputy?.[item.id] ?? 0), 0)
    : null;
  const workerDistrictAdvisories = workerDistrictTotal(workerAdvisories);
  const workerDistrictPersonnel = workerDistrictTotal(workerPersonnel);
  const activity = selected.activity ? summary.activity?.[selected.activity] : undefined;
  const workerMoney = selected.transparency === "external_advisories" && workerAdvisories?.national_total_clp != null ? workerAdvisories : selected.transparency === "personnel_support" && workerPersonnel?.national_total_clp != null ? workerPersonnel : undefined;
  const workerDistrictMoney = selected.transparency === "external_advisories" ? workerDistrictAdvisories : selected.transparency === "personnel_support" ? workerDistrictPersonnel : null;
  const money = selected.transparency && workerDataMonth && workerDistrictMoney != null && workerMoney
    ? { by_month: { [workerDataMonth]: workerDistrictMoney }, latest_month: workerDataMonth, latest_amount: workerDistrictMoney, average_monthly: null, median_monthly: null, months_with_records: 1, methodology: workerMoney.methodology, coverage_by_month: { [workerDataMonth]: workerMoney.deputies_with_records ?? 0 } }
    : selected.transparency ? summary.transparency?.[selected.transparency] : undefined;
  const series = Object.entries(activity?.by_month ?? money?.by_month ?? {});
  const maximum = Math.max(...series.map(([, value]) => value), 1);

  useEffect(() => {
    let active = true;
    fetch(TRANSPARENCY_API_URL)
      .then((response) => response.ok ? response.json() as Promise<WorkerTransparencySnapshot> : null)
      .then((snapshot) => { if (active && snapshot?.categories && (snapshot.categories.external_advisories || snapshot.categories.personnel_support)) setWorkerTransparency(snapshot); })
      .catch(() => { /* El sitio conserva la última cobertura estática si el Worker aún no tiene un corte. */ });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selectedDeputy) {
      setDeputyRecord(null);
      setProfileMessage("");
      return;
    }

    let active = true;
    setDeputyRecord(null);
    setProfileMessage("Cargando actividad legislativa…");
    const profileDataPath = selectedDeputy.district === 8
      ? `data/distrito-8/deputies/${selectedDeputy.id}.json`
      : `data/chile/deputies/${selectedDeputy.id}.json`;
    fetch(profileDataPath)
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
        if (active) setProfileMessage(`La ficha detallada de ${selectedDeputy.name} aún no se ha publicado. La nómina territorial sí está disponible.`);
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
      ...(workerDataMonth ? [workerDataMonth] : []),
    ]);
    return [...months].sort().reverse();
  }, [deputyRecord, workerDataMonth]);

  const averageMotions = summary.activity?.motions.average_per_deputy_per_month;
  const averageResolutions = summary.activity?.resolutions.average_per_deputy_per_month;
  const averageAttendance = summary.attendance?.average_percentage;
  const diet = summary.diet;
  const nationalDietTotal = (national.deputies_count ?? 0) * (national.diet_monthly_clp ?? 0);
  const nationalAverageAttendance = nationalDetails.attendance?.average_percentage;
  const nationalAverageMotions = nationalDetails.activity?.motions?.average_per_deputy_per_month;
  const nationalAverageResolutions = nationalDetails.activity?.resolutions?.average_per_deputy_per_month;
  const nationalTrend = nationalDetails.activity?.[nationalMetric];
  const nationalTrendSeries = Object.entries(nationalTrend?.by_month ?? {});
  const nationalTrendMaximum = Math.max(...nationalTrendSeries.map(([, value]) => value), 1);
  const nationalTransparency = nationalDetails.transparency;
  const transparencyCard = (name: TransparencyName) => {
   const workerCategory = name === "external_advisories" ? workerAdvisories : name === "personnel_support" ? workerPersonnel : undefined;
   if (workerDataMonth && workerCategory?.national_total_clp != null) {
     return {
        value: clp(workerCategory.national_total_clp),
        detail: `${labelMonth(workerDataMonth)} · ${workerCategory.deputies_with_records ?? 0} de 155 diputados(as) con registros`,
     };
    }
    const item = nationalTransparency?.[name];
    const coverage = item?.latest_month ? item.coverage_by_month?.[item.latest_month] : undefined;
    return {
      value: item?.latest_amount == null ? "—" : clp(item.latest_amount),
      detail: item?.latest_month
        ? `${labelMonth(item.latest_month)} · ${coverage ?? 0} de 155 diputados(as) con registros${item.metadata?.source_file || item.metadata?.source_files?.length ? " · exportación oficial" : ""}`
        : workerCategory?.reason ?? "Mes publicado pendiente de carga",
    };
  };
  const nationalOperational = transparencyCard("operational_expenses");
  const nationalAdvisories = transparencyCard("external_advisories");
  const nationalFlights = transparencyCard("flights");
  const nationalPersonnel = transparencyCard("personnel_support");
  const transparencyCoverage = [
    { key: "external_advisories" as TransparencyName, label: "Asesorías externas", card: nationalAdvisories },
    { key: "personnel_support" as TransparencyName, label: "Personal de apoyo", card: nationalPersonnel },
    { key: "operational_expenses" as TransparencyName, label: "Gastos operacionales", card: nationalOperational },
    { key: "flights" as TransparencyName, label: "Pasajes aéreos", card: nationalFlights },
  ];
  const regionalWorkerTotal = (category: WorkerTransparencyCategory | undefined) => mapRegion && workerDataMonth && category?.national_total_clp != null
    ? nationalDeputies.filter((item) => item.region_code === mapRegion.code).reduce((sum, item) => sum + (category.by_deputy?.[item.id] ?? 0), 0)
    : null;
  const regionalAdvisories = regionalWorkerTotal(workerAdvisories);
  const regionalPersonnel = regionalWorkerTotal(workerPersonnel);
  const selectedRegionDetails = (nationalDetails.districts ?? []).filter((item) => item.region === mapRegion?.name);
  const regionalImportedMoney = (name: TransparencyName) => {
    const items = selectedRegionDetails.map((item) => item.transparency?.[name]).filter((item): item is MonthlyMoney => item != null);
    const month = items.flatMap((item) => Object.keys(item.by_month ?? {})).sort().at(-1);
    if (!month) return null;
    const amounts = items.map((item) => item.by_month?.[month]).filter((amount): amount is number => amount != null);
    return amounts.length ? { month, amount: amounts.reduce((sum, amount) => sum + amount, 0) } : null;
  };
  const regionalAdvisoriesImported = regionalImportedMoney("external_advisories");
  const regionalPersonnelImported = regionalImportedMoney("personnel_support");
  const regionalAdvisoriesDisplay = regionalAdvisories == null ? regionalAdvisoriesImported : workerDataMonth ? { month: workerDataMonth, amount: regionalAdvisories } : null;
  const regionalPersonnelDisplay = regionalPersonnel == null ? regionalPersonnelImported : workerDataMonth ? { month: workerDataMonth, amount: regionalPersonnel } : null;
  const regionalDetailAvailable = mapRegion != null && selectedRegionDetails.length === mapRegion.districts.length;
  const regionalAttendanceRecords = selectedRegionDetails.filter((item) => item.attendance?.average_percentage != null);
  const regionalAttendanceWeight = regionalAttendanceRecords.reduce((sum, item) => sum + item.deputies_count, 0);
  const regionalAttendance = regionalAttendanceWeight ? regionalAttendanceRecords.reduce((sum, item) => sum + (item.attendance?.average_percentage ?? 0) * item.deputies_count, 0) / regionalAttendanceWeight : null;
  const regionalTotal = (activityName: ActivityName) => selectedRegionDetails.reduce((sum, item) => sum + (item.activity?.[activityName]?.total ?? 0), 0);
  const chartLabel = activity
    ? `${activity.total} registros legislativos en los meses publicados del piloto.`
    : money?.latest_amount != null
      ? `${money.methodology ?? "Monto mensual publicado."} Último mes disponible: ${labelMonth(money.latest_month ?? "2026-01")}. Los meses posteriores quedan pendientes hasta su publicación oficial.`
      : `La serie de ${selected.label.toLocaleLowerCase("es-CL")} se incorporará al terminar la fase de transparencia.`;
  const personnelMetadata = summary.transparency?.personnel_support_metadata;

  return (
    <main>
      <header className="site-header">
        <div><p className="eyebrow">Observatorio · Datos públicos</p><h1>Observatorio<br />Parlamentario</h1></div>
        <p className="intro">Una lectura nacional de la Cámara de Diputadas y Diputados. Reúne nómina, actividad legislativa, asistencia y dieta de los 155 representantes en ejercicio.</p>
      </header>

      <section className="status" aria-label="Estado del piloto">
        <span className="status-dot" aria-hidden="true" />
        <strong>{national.availability === "national_index_complete" ? `${decimal.format(national.deputies_count ?? 0)} diputados(as) en el índice nacional` : "Índice nacional preparado para su primera actualización"}</strong>
        <span>{nationalDetails.deputies_with_details === 155 ? "155 fichas legislativas consolidadas" : "Detalle legislativo en consolidación"} · última recolección del piloto: {collectionDateFormatter.format(new Date(summary.retrieved_at))}. Los meses sin publicación se mostrarán como tales; nunca como $0.</span>
      </section>

      <section className="national-summary" aria-labelledby="national-summary-title">
        <div className="section-heading">
          <div><p className="eyebrow">Panorama nacional</p><h2 id="national-summary-title">Chile en cifras</h2></div>
          <span className="coverage-note">Nómina, dieta, asistencia y actividad consolidadas</span>
        </div>
        <div className="national-summary-grid">
          <MetricCard label="Diputados(as) en ejercicio" value={national.deputies_count == null ? "—" : decimal.format(national.deputies_count)} detail={`${decimal.format(nationalRegions.length)} regiones · 28 distritos electorales`} />
          <MetricCard label="Promedio de asistencia" value={percentage(nationalAverageAttendance)} detail={nationalAverageAttendance == null ? "Fichas nacionales en carga" : "Sesiones de sala con clasificación oficial"} />
          <MetricCard label="Promedio de mociones" value={nationalAverageMotions == null ? "—" : decimal.format(nationalAverageMotions)} detail={nationalAverageMotions == null ? "Fichas nacionales en carga" : "Por diputado(a) y mes con actividad"} />
          <MetricCard label="Promedio de resoluciones" value={nationalAverageResolutions == null ? "—" : decimal.format(nationalAverageResolutions)} detail={nationalAverageResolutions == null ? "Fichas nacionales en carga" : "Por diputado(a) y mes con actividad"} />
          <MetricCard label="Dieta bruta nacional" value={national.deputies_count == null ? "—" : clp(nationalDietTotal)} detail="Total mensual de las 155 dietas brutas" />
          <MetricCard label="Dieta bruta por diputado(a)" value={national.diet_monthly_clp == null ? "—" : clp(national.diet_monthly_clp)} detail="Promedio y mediana mensual: mismo monto vigente" />
          <MetricCard label="Gastos operacionales" value={nationalOperational.value} detail={nationalOperational.detail} />
          <MetricCard label="Asesorías externas" value={nationalAdvisories.value} detail={nationalAdvisories.detail} />
          <MetricCard label="Pasajes aéreos" value={nationalFlights.value} detail={nationalFlights.detail} />
          <MetricCard label="Personal de apoyo" value={nationalPersonnel.value} detail={nationalPersonnel.detail} />
        </div>
        <p className="national-summary-note">Los totales de transparencia muestran sólo fichas y meses efectivamente publicados por la Cámara. La cobertura queda visible junto a cada cifra; una ficha sin publicación nunca se incorpora como $0. Personal de apoyo corresponde a la suma de sueldos vigentes informados en el corte, no a una rendición mensual.</p>
        <div className="transparency-coverage" aria-label="Cobertura de fuentes de transparencia">
          {transparencyCoverage.map((item) => {
            const metadata = nationalTransparency?.[item.key]?.metadata;
            const source = metadata?.source_url;
            return <article key={item.key}>
              <p>{item.label}</p>
              <strong>{item.card.value}</strong>
              <small>{item.card.detail}</small>
              {source ? <a href={source} target="_blank" rel="noreferrer">Ver fuente oficial</a> : <span>Esperando archivo nacional comparable</span>}
            </article>;
          })}
        </div>
      </section>

      <section className="national-trend" aria-labelledby="national-trend-title">
        <div className="section-heading">
          <div><p className="eyebrow">Seguimiento mensual</p><h2 id="national-trend-title">Actividad legislativa nacional</h2></div>
          <label><span>Indicador de seguimiento</span><select value={nationalMetric} onChange={(event) => setNationalMetric(event.target.value as ActivityName)}>{Object.entries(nationalMetricLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        </div>
        <article className="chart-panel national-chart" aria-labelledby="national-chart-title">
          <div><p className="eyebrow">Cámara de Diputadas y Diputados</p><h3 id="national-chart-title">{nationalMetricLabels[nationalMetric]}</h3><p>{nationalTrend ? `${decimal.format(nationalTrend.total)} registros en los meses publicados para las 155 fichas nacionales.` : "La serie se incorporará al terminar la carga nacional."}</p></div>
          {nationalTrendSeries.length ? <div className="chart" role="img" aria-label={`Serie mensual nacional de ${nationalMetricLabels[nationalMetric]}`}><div className="chart-lines" aria-hidden="true">{nationalTrendSeries.map(([month, value]) => <i key={month} style={{ height: `${Math.max(8, Math.round((value / nationalTrendMaximum) * 100))}%` }} title={`${labelMonth(month)}: ${value}`} />)}</div><div className="chart-axis">{nationalTrendSeries.map(([month, value]) => <span key={month}>{labelMonth(month)}<b>{decimal.format(value)}</b></span>)}</div></div> : <div className="chart-placeholder" role="img" aria-label="Serie nacional pendiente"><span>Sin serie publicada aún</span></div>}
        </article>
      </section>

      <section className="dashboard" aria-labelledby="dashboard-title">
        <div className="section-heading">
          <div><p className="eyebrow">Piloto validado · Distrito 8</p><h2 id="dashboard-title">Resumen mensual del distrito</h2></div>
          <label><span>Indicador de seguimiento</span><select value={metric} onChange={(event) => setMetric(event.target.value as Metric)}>{Object.entries(metricLabels).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}</select></label>
        </div>

        <div className="dashboard-grid">
          <div className="summary-grid">
            <MetricCard label="Diputados en cobertura" value={String(summary.deputies_count)} detail="Nómina vigente del Distrito 8" />
            <MetricCard label="Promedio de asistencia" value={percentage(averageAttendance)} detail={averageAttendance == null ? "Pendiente de la fuente oficial" : "Sesiones de sala con clasificación oficial"} />
            <MetricCard label="Promedio de mociones" value={averageMotions == null ? "—" : decimal.format(averageMotions)} detail="Por diputado(a) y mes con actividad" />
            <MetricCard label="Promedio de resoluciones" value={averageResolutions == null ? "—" : decimal.format(averageResolutions)} detail="Por diputado(a) y mes con actividad" />
            <MetricCard label={selected.label} value={activity ? decimal.format(activity.total) : money?.latest_amount != null ? clp(money.latest_amount) : "—"} detail={activity ? `Total del Distrito 8 · ${selected.unit}` : money?.latest_month ? `Último mes publicado: ${labelMonth(money.latest_month)}` : "Pendiente de publicación mensual"} />
            <MetricCard label="Dieta parlamentaria" value={diet ? clp(diet.monthly_gross_per_deputy_clp) : "—"} detail={diet ? "Bruta mensual vigente por diputado(a)" : "Monto bruto mensual vigente · pendiente"} />
          </div>

          <article className="chart-panel" aria-labelledby="chart-title">
            <div><p className="eyebrow">Seguimiento</p><h3 id="chart-title">{selected.label}</h3><p>{chartLabel}</p></div>
            {series.length ? (
              <div className="chart" role="img" aria-label={`Serie mensual de ${selected.label}`}>
                <div className="chart-lines" aria-hidden="true">{series.map(([month, value]) => <i key={month} style={{ height: `${Math.max(8, Math.round((value / maximum) * 100))}%` }} title={`${labelMonth(month)}: ${value}`} />)}</div>
                <div className="chart-axis">{series.map(([month, value]) => <span key={month}>{labelMonth(month)}<b>{selected.transparency ? <><span>{currency.format(value)}</span><em>CLP</em></> : decimal.format(value)}</b></span>)}</div>
              </div>
            ) : <div className="chart-placeholder" role="img" aria-label="Serie pendiente de publicación"><span>Sin serie publicada aún</span></div>}
            {selected.transparency && personnelMetadata?.source_url ? <p className="source-note">{personnelMetadata.availability === "published_snapshot" ? "Respaldo de" : "Fuente:"} <a href={personnelMetadata.source_url} target="_blank" rel="noreferrer">directorio oficial de personal de apoyo</a>{personnelMetadata.snapshot_retrieved_at ? ` · corte ${personnelMetadata.snapshot_retrieved_at}` : ""}. {personnelMetadata.methodology}</p> : null}
          </article>
        </div>
      </section>

      <section className="national-view" aria-labelledby="national-title">
        <div className="section-heading"><div><p className="eyebrow">Vista territorial</p><h2 id="national-title">Chile, región por región</h2></div><span className="coverage-note">Pasa sobre una región para ver su resumen; haz clic para preparar el filtro.</span></div>
        <div className="national-map-layout">
          <div className="national-map" role="list" aria-label="Mapa horizontal de regiones de Chile">
            {nationalRegions.map((item, index) => <button key={item.code} type="button" role="listitem" className={`region-tile ${region === item.code ? "is-selected" : ""} ${mapRegion?.code === item.code ? "is-previewed" : ""}`} onMouseEnter={() => setHoverRegion(item.code)} onMouseLeave={() => setHoverRegion("")} onFocus={() => setHoverRegion(item.code)} onBlur={() => setHoverRegion("")} onClick={() => { setRegion(item.code); setDistrict(""); setDeputy(""); }} title={`${item.name}: ${item.deputies_count == null ? "nómina en actualización" : `${item.deputies_count} diputados(as)`}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item.name}</strong><small>{item.deputies_count == null ? "Nómina en actualización" : `${decimal.format(item.deputies_count)} diputados(as)`}</small></button>)}
          </div>
          <aside className="region-panel" aria-live="polite">
            {mapRegion ? <><p className="eyebrow">{hoverRegion ? "Vista previa regional" : "Región seleccionada"}</p><h3>{mapRegion.name}</h3><dl><div><dt>Distritos</dt><dd>{mapRegion.districts.map((item) => `D${item}`).join(" · ")}</dd></div><div><dt>Diputados(as)</dt><dd>{mapRegion.deputies_count == null ? "Actualizando nómina" : decimal.format(mapRegion.deputies_count)}</dd></div><div><dt>Dieta bruta mensual</dt><dd>{mapRegion.diet_monthly_clp != null ? clp(mapRegion.diet_monthly_clp) : "Disponible al actualizar la nómina"}</dd></div><div><dt>Asistencia promedio</dt><dd>{regionalDetailAvailable ? percentage(regionalAttendance) : "Sin registros clasificados"}</dd></div><div><dt>Mociones del período</dt><dd>{regionalDetailAvailable ? decimal.format(regionalTotal("motions")) : "Sin serie publicada"}</dd></div><div><dt>Resoluciones del período</dt><dd>{regionalDetailAvailable ? decimal.format(regionalTotal("resolutions")) : "Sin serie publicada"}</dd></div><div><dt>Asesorías externas</dt><dd>{regionalAdvisoriesDisplay ? `${clp(regionalAdvisoriesDisplay.amount)} · ${labelMonth(regionalAdvisoriesDisplay.month)}` : "Corte mensual pendiente"}</dd></div><div><dt>Personal de apoyo</dt><dd>{regionalPersonnelDisplay ? `${clp(regionalPersonnelDisplay.amount)} · ${labelMonth(regionalPersonnelDisplay.month)}` : "Corte mensual pendiente"}</dd></div><div><dt>Gastos y pasajes</dt><dd>Sin publicación mensual comparable</dd></div></dl></> : <><p className="eyebrow">Cobertura nacional</p><h3>{national.deputies_count == null ? "Nómina en actualización" : `${decimal.format(national.deputies_count)} diputados(as)`}</h3><p>Pasa sobre una región para ver sus distritos, representantes, dieta mensual y actividad legislativa. Haz clic para cargarla en el filtro individual.</p></>}
          </aside>
        </div>
      </section>

      <section className="profile" aria-labelledby="profile-title">
        <div className="section-heading"><div><p className="eyebrow">Ficha individual</p><h2 id="profile-title">Detalle por diputado(a)</h2></div><span className="coverage-note">{nationalDetails.deputies_with_details === 155 ? "Fichas nacionales disponibles" : "Distrito 8 disponible · fichas nacionales en carga"}</span></div>
        <div className="filters">
          <label><span>Región</span><select value={region} onChange={(event) => { setRegion(event.target.value); setDistrict(""); setDeputy(""); }}><option value="">Seleccionar región</option>{nationalRegions.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
          <label><span>Distrito</span><select value={district} onChange={(event) => { setDistrict(event.target.value); setDeputy(""); }} disabled={!region}><option value="">Seleccionar distrito</option>{districtOptions.map((item) => <option key={item} value={item}>Distrito {item}</option>)}</select></label>
          <label><span>Diputado(a)</span><select value={deputy} onChange={(event) => setDeputy(event.target.value)} disabled={!district}><option value="">Seleccionar diputado(a)</option>{availableDeputies.map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
        </div>

        {deputyRecord ? <article className="profile-card"><div><p className="eyebrow">Ficha individual</p><h3>{deputyRecord.profile.name}</h3><p>{deputyRecord.profile.district} · {deputyRecord.profile.region} · {deputyRecord.profile.period}</p><h4>Asistencia a sala</h4><p>{percentage(deputyRecord.attendance?.percentage)} · {deputyRecord.attendance?.present ?? 0} presencias en {deputyRecord.attendance?.sessions_recorded ?? 0} registros de sesión.</p></div><div><h4>Comisiones actuales</h4>{deputyRecord.commissions?.length ? <><ul>{deputyRecord.commissions.map((commission) => <li key={commission}>{commission}</li>)}</ul><p className="source-note">Comisiones incorporadas desde la fuente oficial. Puedes contrastarlas en la <a href={deputyRecord.profile.commissions_source_url} target="_blank" rel="noreferrer">ficha vigente de la Cámara</a>.</p></> : <p>El servicio de Datos Abiertos no devolvió aún integrantes para esta ficha. No significa que no participe en comisiones: consulta la <a href={deputyRecord.profile.commissions_source_url} target="_blank" rel="noreferrer">ficha vigente de la Cámara</a>.</p>}<h4 className="profile-subheading">Cobertura de transparencia</h4>{workerDataMonth && (workerAdvisories?.national_total_clp != null || workerPersonnel?.national_total_clp != null) ? <p>{workerAdvisories?.national_total_clp != null ? `Asesorías externas: corte de ${labelMonth(workerDataMonth)} desde el directorio mensual nacional. ` : ""}{workerPersonnel?.national_total_clp != null ? `Personal de apoyo: suma de sueldos vigentes del corte ${labelMonth(workerDataMonth)}, no gasto rendido. ` : ""}Los montos publicados aparecen en la tabla; categorías sin registros no se convierten en $0.</p> : deputyRecord.transparency.availability === "published_partial" ? <p>Esta ficha ya tiene meses de transparencia publicados. Los meses posteriores o categorías sin registro se mantienen como pendientes, sin imputar $0. Personal de apoyo se publica por ahora sólo donde existe una fuente mensual comparable.</p> : deputyRecord.transparency.personnel_support?.by_month && Object.keys(deputyRecord.transparency.personnel_support.by_month).length ? <p>Personal de apoyo publicado para {deputyRecord.transparency.personnel_support_metadata?.coverage ?? "los meses disponibles"}. Son remuneraciones de contratos vigentes; no equivalen a gasto rendido.</p> : <p>La Cámara aún no publica transparencia mensual para esta ficha. El tablero conservará esos meses como pendientes, nunca como $0.</p>}</div></article> : <div className="empty-state">{profileMessage || "Elige región, distrito y diputado(a) para abrir su ficha."}</div>}

        {deputyRecord ? <div className="table-wrap"><table><thead><tr><th>Mes</th><th>Mociones</th><th>Acuerdos</th><th>Resoluciones</th><th>Oficios</th><th>Asistencia total</th><th>Gastos</th><th>Asesorías</th><th>Pasajes</th><th>Personal</th></tr></thead><tbody>{detailMonths.map((month) => <tr key={month}><td>{labelMonth(month)}</td><td><ActivityCell states={deputyRecord.activity.motions_by_month_and_state[month]} /></td><td><ActivityCell states={deputyRecord.activity.agreements_by_month_and_state[month]} /></td><td><ActivityCell states={deputyRecord.activity.resolutions_by_month_and_state[month]} /></td><td>{decimal.format(deputyRecord.activity.offices_by_month[month] ?? 0)}</td><td>{percentage(deputyRecord.attendance?.percentage)}</td><td>{MoneyCell(deputyRecord.transparency.operational_expenses?.by_month[month], deputyRecord.transparency.operational_expenses?.by_month)}</td><td>{month === workerDataMonth && workerAdvisories?.national_total_clp != null ? workerAdvisories.by_deputy?.[deputyRecord.profile.id] == null ? <span className="pending-cell">Sin registros</span> : clp(workerAdvisories.by_deputy[deputyRecord.profile.id]) : MoneyCell(deputyRecord.transparency.external_advisories?.by_month[month], deputyRecord.transparency.external_advisories?.by_month)}</td><td>{MoneyCell(deputyRecord.transparency.flights?.by_month[month], deputyRecord.transparency.flights?.by_month)}</td><td>{month === workerDataMonth && workerPersonnel?.national_total_clp != null ? workerPersonnel.by_deputy?.[deputyRecord.profile.id] == null ? <span className="pending-cell">Sin registros</span> : clp(workerPersonnel.by_deputy[deputyRecord.profile.id]) : MoneyCell(deputyRecord.transparency.personnel_support?.by_month[month], deputyRecord.transparency.personnel_support?.by_month)}</td></tr>)}</tbody></table></div> : null}
      </section>

      <section className="methodology" aria-labelledby="methodology-title"><p className="eyebrow">Trazabilidad</p><h2 id="methodology-title">Cómo leer este tablero</h2><ul>{sources.map((source) => <li key={source}>{source}</li>)}</ul></section>
    </main>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <article className="metric-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function MoneyCell(value: number | undefined, byMonth?: Record<string, number>) {
  if (value != null) return clp(value);
  const latest = latestPublished(byMonth);
  return latest ? <span className="pending-cell"><small>Último: {labelMonth(latest.month)}</small>{clp(latest.value)}</span> : <span className="pending-cell">Pendiente</span>;
}
