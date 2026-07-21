"use client";

import { useEffect, useMemo, useState } from "react";

type Metric = "gastos" | "asesorias" | "pasajes" | "personal" | "mociones" | "resoluciones";

const metricLabels: Record<Metric, { label: string; unit: string }> = {
  gastos: { label: "Gastos operacionales", unit: "CLP por mes" },
  asesorias: { label: "Asesorías externas", unit: "CLP por mes" },
  pasajes: { label: "Pasajes aéreos", unit: "CLP por mes" },
  personal: { label: "Personal de apoyo", unit: "CLP por mes" },
  mociones: { label: "Mociones", unit: "Número por mes" },
  resoluciones: { label: "Resoluciones", unit: "Número por mes" },
};

const pilotProfile = {
  name: "Pier Karlezi Hazleby",
  district: "Distrito 8",
  region: "Región Metropolitana de Santiago",
  period: "2026–2030",
  commissions: ["Hacienda", "Obras Públicas, Transportes y Telecomunicaciones"],
};

const sources = [
  "Datos Abiertos Legislativos: identidad, actividad legislativa y asistencia.",
  "Fichas de transparencia: gastos, asesorías, pasajes y personal de apoyo.",
  "Transparencia Activa: dieta parlamentaria vigente.",
];

type DistrictSummary = {
  deputies_count: number;
  retrieved_at: string;
};

export default function Home() {
  const [metric, setMetric] = useState<Metric>("gastos");
  const [region, setRegion] = useState("");
  const [district, setDistrict] = useState("");
  const [deputy, setDeputy] = useState("");
  const [summary, setSummary] = useState<DistrictSummary | null>(null);

  useEffect(() => {
    fetch("./data/distrito-8/monthly-summary.json")
      .then((response) => (response.ok ? response.json() : null))
      .then((data: DistrictSummary | null) => setSummary(data))
      .catch(() => setSummary(null));
  }, []);

  const selected = metricLabels[metric];
  const chartLabel = useMemo(
    () => `La serie de ${selected.label.toLocaleLowerCase("es-CL")} aparecerá cuando termine la primera recolección.`,
    [selected.label],
  );

  return (
    <main>
      <header className="site-header">
        <p className="eyebrow">Piloto de datos públicos · Distrito 8</p>
        <h1>Observatorio Parlamentario</h1>
        <p className="intro">
          Un tablero para entender actividad legislativa, asistencia y transparencia parlamentaria con fuentes oficiales y metodología visible.
        </p>
      </header>

      <section className="status" aria-label="Estado del piloto">
        <span className="status-dot" aria-hidden="true" />
        <strong>{summary ? "Datos del Distrito 8 actualizados" : "Preparando la primera recolección del Distrito 8"}</strong>
        <span>{summary ? `Nómina oficial descargada el ${new Intl.DateTimeFormat("es-CL", { dateStyle: "medium" }).format(new Date(summary.retrieved_at))}.` : "Los meses sin publicación se mostrarán como tales; nunca como $0."}</span>
      </section>

      <section className="dashboard" aria-labelledby="dashboard-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Tablero general</p>
            <h2 id="dashboard-title">Resumen mensual del distrito</h2>
          </div>
          <label>
            <span>Indicador de seguimiento</span>
            <select value={metric} onChange={(event) => setMetric(event.target.value as Metric)}>
              {Object.entries(metricLabels).map(([key, item]) => (
                <option key={key} value={key}>{item.label}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="dashboard-grid">
          <div className="summary-grid">
            <MetricCard label="Diputados en cobertura" value={summary ? String(summary.deputies_count) : "—"} detail={summary ? "Nómina vigente del Distrito 8" : "Se completará desde la nómina vigente"} />
            <MetricCard label="Promedio de asistencia" value="—" detail="Con desglose y metodología" />
            <MetricCard label="Promedio de mociones" value="—" detail="Por diputado y por mes" />
            <MetricCard label="Promedio de resoluciones" value="—" detail="Por diputado y por mes" />
            <MetricCard label={selected.label} value="—" detail={`Total · promedio · mediana · ${selected.unit}`} />
            <MetricCard label="Dieta parlamentaria" value="—" detail="Monto bruto mensual vigente" />
          </div>

          <article className="chart-panel" aria-labelledby="chart-title">
            <div>
              <p className="eyebrow">Seguimiento</p>
              <h3 id="chart-title">{selected.label}</h3>
              <p>{chartLabel}</p>
            </div>
            <div className="chart-placeholder" role="img" aria-label="Área reservada para la serie mensual del indicador seleccionado">
              <span>Últimos meses disponibles</span>
              <div className="chart-lines" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /></div>
            </div>
          </article>
        </div>
      </section>

      <section className="district-view" aria-labelledby="district-title">
        <div>
          <p className="eyebrow">Vista territorial</p>
          <h2 id="district-title">Región Metropolitana · Distrito 8</h2>
          <p>
            La versión completa incorporará el mapa nacional y permitirá fijar una región para revisar diputados, dieta y gastos mensuales agregados.
          </p>
        </div>
        <dl className="territory-details">
          <div><dt>Región</dt><dd>Metropolitana de Santiago</dd></div>
          <div><dt>Distrito</dt><dd>8</dd></div>
          <div><dt>Comunas</dt><dd>Tiltil, Quilicura, Colina, Estación Central, Pudahuel, Lampa, Cerrillos y Maipú</dd></div>
        </dl>
      </section>

      <section className="profile" aria-labelledby="profile-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Ficha individual</p>
            <h2 id="profile-title">Detalle por diputado(a)</h2>
          </div>
          <span className="coverage-note">La tabla mostrará 12 meses por defecto</span>
        </div>

        <div className="filters">
          <label><span>Región</span><select value={region} onChange={(event) => setRegion(event.target.value)}><option value="">Seleccionar región</option><option>Región Metropolitana de Santiago</option></select></label>
          <label><span>Distrito</span><select value={district} onChange={(event) => setDistrict(event.target.value)} disabled={!region}><option value="">Seleccionar distrito</option><option>Distrito 8</option></select></label>
          <label><span>Diputado(a)</span><select value={deputy} onChange={(event) => setDeputy(event.target.value)} disabled={!district}><option value="">Seleccionar diputado(a)</option><option>{pilotProfile.name}</option></select></label>
        </div>

        {deputy ? (
          <article className="profile-card">
            <div>
              <p className="eyebrow">Ficha de prueba</p>
              <h3>{pilotProfile.name}</h3>
              <p>{pilotProfile.district} · {pilotProfile.region} · {pilotProfile.period}</p>
            </div>
            <div>
              <h4>Comisiones actuales</h4>
              <ul>{pilotProfile.commissions.map((commission) => <li key={commission}>{commission}</li>)}</ul>
            </div>
          </article>
        ) : (
          <div className="empty-state">Elige región, distrito y diputado(a) para abrir su ficha.</div>
        )}

        <div className="table-wrap">
          <table>
            <thead><tr><th>Mes</th><th>Mociones</th><th>Resoluciones</th><th>Oficios</th><th>Asistencia</th><th>Gastos</th><th>Asesorías</th><th>Pasajes</th><th>Personal</th></tr></thead>
            <tbody><tr><td colSpan={9}>La primera corrida del piloto cargará aquí los últimos meses que estén publicados.</td></tr></tbody>
          </table>
        </div>
      </section>

      <section className="methodology" aria-labelledby="methodology-title">
        <p className="eyebrow">Trazabilidad</p>
        <h2 id="methodology-title">Cómo leer este tablero</h2>
        <ul>{sources.map((source) => <li key={source}>{source}</li>)}</ul>
      </section>
    </main>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <article className="metric-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}
