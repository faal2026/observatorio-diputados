# Observatorio Parlamentario

Observatorio de transparencia pública de la Cámara de Diputadas y Diputados de Chile. La nómina y el mapa nacional se actualizan desde Datos Abiertos; el Distrito 8 es el primer detalle legislativo validado.

## Alcance inicial

- Identidad territorial, comisiones, actividad legislativa, asistencia y oficios.
- Transparencia mensual: dieta, gastos operacionales, asesorías externas, pasajes y personal de apoyo.
- Mapa horizontal de las 16 regiones, filtros nacionales y ficha por diputado o diputada.
- Tablero distrital y ficha detallada validada inicialmente para Distrito 8.

## Criterios de datos

- Todos los montos se almacenan en pesos chilenos enteros.
- Un dato no publicado se representa como `null`, nunca como cero.
- Totales, promedios y medianas indican siempre cuántos diputados tienen datos publicados.
- Cada registro conserva su URL de fuente y fecha de recolección.

El contrato del piloto está en `public/data/distrito-8/pilot-contract.json` y la estrategia de fuentes en `collector/README.md`.
