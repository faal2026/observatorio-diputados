# Recolectores del Observatorio Parlamentario

El piloto combinará dos fuentes oficiales:

1. Datos Abiertos Legislativos para nómina, territorios, comisiones, actividad legislativa y asistencia.
2. Fichas de Transparencia para gastos operacionales, asesorías externas, pasajes, personal de apoyo y oficios personales.

Cada registro mensual debe incluir `source_url`, `retrieved_at`, `availability` y `published_deputies_count`. Los valores no publicados se almacenan como `null`, nunca como cero.

`collect_national_index.py` es la entrada nacional ligera. Consulta una sola vez el servicio oficial `retornarDiputadosPeriodoActual`, que entrega la nómina vigente y su distrito, y genera el índice de las 16 regiones. No descarga todavía fichas individuales, por lo que puede correr junto con cada actualización sin aumentar significativamente el tiempo.

```text
public/data/chile/index.json
data/generated/chile-summary.json
```

La primera fase detallada está implementada en `collect_district.py`. Cruza los identificadores de Datos Abiertos con la nómina oficial del Distrito 8 publicada por la Biblioteca del Congreso Nacional y genera las métricas anuales disponibles para mociones, acuerdos y resoluciones. Se puede revisar sin consultar las fuentes:

```text
python3 collector/collect_district.py --dry-run
```

La segunda fase añadirá los postbacks mensuales de transparencia y el detalle de asistencia/oficios. Esto evita confundir un mes no publicado con un monto cero.

La primera corrida completa producirá un archivo por diputado y un agregado distrital:

```text
public/data/distrito-8/deputies/<id>.json
public/data/distrito-8/monthly-summary.json
```
