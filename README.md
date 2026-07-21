# Observatorio Parlamentario

Piloto de transparencia pública para el Distrito 8 de la Cámara de Diputadas y Diputados de Chile.

## Alcance inicial

- Identidad territorial, comisiones, actividad legislativa, asistencia y oficios.
- Transparencia mensual: dieta, gastos operacionales, asesorías externas, pasajes y personal de apoyo.
- Tablero distrital y ficha por diputado o diputada.

## Criterios de datos

- Todos los montos se almacenan en pesos chilenos enteros.
- Un dato no publicado se representa como `null`, nunca como cero.
- Totales, promedios y medianas indican siempre cuántos diputados tienen datos publicados.
- Cada registro conserva su URL de fuente y fecha de recolección.

El contrato del piloto está en `data/distrito-8/pilot-contract.json` y la estrategia de fuentes en `collector/README.md`.
