const ADVISORIES_URL = "https://www.camara.cl/transparencia/asesoriasexternasgral.aspx";
const ROSTER_URL = "https://faal2026.github.io/observatorio-diputados/data/chile/index.json";
const ALLOWED_ORIGINS = new Set([
  "https://faal2026.github.io",
  "https://diputados.felipealcerreca.lat",
]);

const browserHeaders = {
  "User-Agent": "Mozilla/5.0 (compatible; ObservatorioParlamentario/1.0; +https://faal2026.github.io/observatorio-diputados/)",
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "Accept-Language": "es-CL,es;q=0.9",
  Referer: "https://www.camara.cl/",
};

function clean(value) {
  return value.replace(/<[^>]*>/g, " ").replace(/&nbsp;/gi, " ").replace(/&amp;/gi, "&").replace(/&#(?:x[0-9a-f]+|\d+);/gi, " ").replace(/\s+/g, " ").trim();
}

function normalized(value) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
}

function formValue(attributes, name) {
  const expression = new RegExp(`${name}\\s*=\\s*["']([^"']*)["']`, "i");
  return attributes.match(expression)?.[1] ?? "";
}

function hiddenFields(html) {
  const result = new URLSearchParams();
  for (const match of html.matchAll(/<input\b([^>]*)>/gi)) {
    const attributes = match[1];
    if (formValue(attributes, "type").toLowerCase() === "hidden") {
      const name = formValue(attributes, "name");
      if (name) result.set(name, formValue(attributes, "value"));
    }
  }
  return result;
}

function selectName(html, idSuffix) {
  const expression = new RegExp(`<select\\b([^>]*id=["'][^"']*${idSuffix}["'][^>]*)>`, "i");
  const attributes = html.match(expression)?.[1];
  return attributes ? formValue(attributes, "name") : null;
}

function parseAmount(value) {
  const compact = value.replace(/[$.\s]/g, "").replace(/,/g, "");
  return /^\d+$/.test(compact) ? Number(compact) : null;
}

function rowsFromAdvisories(html) {
  const table = [...html.matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/gi)].find((item) => /Folio[\s\S]{0,500}Asesor[\s\S]{0,500}Monto/i.test(item[1]));
  if (!table) return [];
  return [...table[1].matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)].map((row) => {
    const cells = [...row[1].matchAll(/<t[dh]\b[^>]*>([\s\S]*?)<\/t[dh]>/gi)].map((cell) => clean(cell[1]));
    return { folio: cells[0], advisor: cells[1], amount: parseAmount(cells[2] ?? ""), deputy: cells[3] };
  }).filter((row) => row.amount != null && row.deputy);
}

function deputyId(sourceName, deputies) {
  const name = normalized(sourceName);
  const [surnamePart, givenPart = ""] = name.split(",");
  const surname = surnamePart.split(" ")[0];
  const given = givenPart.trim().split(" ")[0];
  const matches = deputies.filter((deputy) => {
    const candidate = normalized(deputy.name);
    return surname && given && candidate.includes(surname) && candidate.includes(given);
  });
  return matches.length === 1 ? String(matches[0].id) : null;
}

async function publishedAdvisories(monthKey) {
  const [year, month] = monthKey.split("-").map(Number);
  const initial = await fetch(ADVISORIES_URL, { headers: browserHeaders });
  if (!initial.ok) throw new Error(`La Cámara respondió ${initial.status} al directorio general de asesorías.`);
  const html = await initial.text();
  const monthName = selectName(html, "ddlMes");
  const yearName = selectName(html, "ddlAno");
  if (!monthName || !yearName) throw new Error("El directorio general no entregó sus selectores mensuales.");
  const fields = hiddenFields(html);
  fields.set(monthName, String(month));
  fields.set(yearName, String(year));
  fields.set("__EVENTTARGET", monthName);
  fields.set("__EVENTARGUMENT", "");
  const response = await fetch(ADVISORIES_URL, {
    method: "POST",
    headers: { ...browserHeaders, "Content-Type": "application/x-www-form-urlencoded" },
    body: fields.toString(),
  });
  if (!response.ok) throw new Error(`La Cámara respondió ${response.status} al consultar ${monthKey}.`);
  return rowsFromAdvisories(await response.text());
}

async function refresh(env, monthKey) {
  const [rows, rosterResponse] = await Promise.all([
    publishedAdvisories(monthKey),
    fetch(ROSTER_URL, { headers: { Accept: "application/json" } }),
  ]);
  if (!rosterResponse.ok) throw new Error("No fue posible cargar la nómina nacional publicada.");
  const roster = await rosterResponse.json();
  const totals = {};
  const unmatched = [];
  for (const row of rows) {
    const id = deputyId(row.deputy, roster.deputies ?? []);
    if (!id) {
      unmatched.push({ deputy: row.deputy, folio: row.folio });
      continue;
    }
    totals[id] = (totals[id] ?? 0) + row.amount;
  }
  const nationalTotal = Object.values(totals).reduce((sum, amount) => sum + amount, 0);
  const snapshot = {
    schema_version: 1,
    retrieved_at: new Date().toISOString(),
    source: ADVISORIES_URL,
    month: monthKey,
    categories: {
      external_advisories: {
        by_deputy: totals,
        national_total_clp: nationalTotal,
        deputies_with_records: Object.keys(totals).length,
        unmatched_rows: unmatched,
        methodology: "Suma de filas del directorio general de asesorías externas de la Cámara para el mes publicado. Cada fila está asociada a un diputado o diputada por la fuente oficial.",
      },
      operational_expenses: { availability: "pending_source" },
      flights: { availability: "pending_source" },
      personnel_support: { availability: "pending_source" },
    },
  };
  await env.TRANSPARENCY.put("latest", JSON.stringify(snapshot));
  return snapshot;
}

function cors(request) {
  const origin = request.headers.get("Origin");
  return {
    "Access-Control-Allow-Origin": origin && ALLOWED_ORIGINS.has(origin) ? origin : "https://faal2026.github.io",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "public, max-age=300",
  };
}

function monthTwoMonthsAgo() {
  const date = new Date();
  date.setUTCMonth(date.getUTCMonth() - 2, 1);
  return date.toISOString().slice(0, 7);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { headers: cors(request) });
    if (url.pathname !== "/v1/transparency" || request.method !== "GET") return new Response("Not found", { status: 404 });
    const value = await env.TRANSPARENCY.get("latest");
    if (value) return new Response(value, { headers: cors(request) });

    const retryAt = await env.TRANSPARENCY.get("initialization_retry_at");
    if (retryAt && Number(retryAt) > Date.now()) {
      return new Response(JSON.stringify({ availability: "pending_first_refresh" }), { status: 503, headers: cors(request) });
    }

    try {
      const snapshot = await refresh(env, monthTwoMonthsAgo());
      return new Response(JSON.stringify(snapshot), { headers: cors(request) });
    } catch {
      await env.TRANSPARENCY.put("initialization_retry_at", String(Date.now() + 60 * 60 * 1000), { expirationTtl: 60 * 60 });
      return new Response(JSON.stringify({ availability: "pending_first_refresh" }), { status: 503, headers: cors(request) });
    }
  },

  async scheduled(_controller, env) {
    await refresh(env, monthTwoMonthsAgo());
  },
};
