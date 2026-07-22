# Observatorio Parlamentario

Observatorio de transparencia pública de la Cámara de Diputadas y Diputados de Chile. La nómina, la actividad legislativa y la asistencia cubren las 155 fichas nacionales; el Distrito 8 conserva el primer piloto de transparencia validado.

## Alcance inicial

- Identidad territorial, comisiones, actividad legislativa, asistencia y oficios.
- Transparencia mensual: dieta, gastos operacionales, asesorías externas, pasajes y personal de apoyo.
- Mapa horizontal de las 16 regiones, filtros nacionales y ficha por diputado o diputada.
- Tablero nacional, mapa territorial interactivo y ficha detallada para las 155 diputadas y diputados.
- Transparencia mensual se incorpora sólo cuando la Cámara publica una serie comparable; mientras tanto se muestra como pendiente, nunca como $0.

## Criterios de datos

- Todos los montos se almacenan en pesos chilenos enteros.
- Un dato no publicado se representa como `null`, nunca como cero.
- Totales, promedios y medianas indican siempre cuántos diputados tienen datos publicados.
- Cada registro conserva su URL de fuente y fecha de recolección.

El contrato del piloto está en `public/data/distrito-8/pilot-contract.json` y la estrategia de fuentes en `collector/README.md`.
