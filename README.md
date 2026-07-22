# Observatorio Parlamentario

Observatorio de transparencia pública de la Cámara de Diputadas y Diputados de Chile. La nómina, la actividad legislativa y la asistencia cubren las 155 fichas nacionales; la transparencia se actualiza en una tarea nacional independiente, sin repetir la extracción legislativa.

## Alcance inicial

- Identidad territorial, comisiones, actividad legislativa, asistencia y oficios.
- Transparencia mensual: dieta, gastos operacionales, asesorías externas, pasajes y personal de apoyo.
- Mapa horizontal de las 16 regiones, filtros nacionales y ficha por diputado o diputada.
- Tablero nacional, mapa territorial interactivo y ficha detallada para las 155 diputadas y diputados.
- Transparencia mensual nacional para gastos operacionales, asesorías externas y pasajes; la tarea consulta sólo el mes publicado y muestra su cobertura.
- Personal de apoyo se mantiene separado: la fuente disponible describe remuneraciones de contratos vigentes y todavía no entrega una serie mensual nacional homogénea.
- Cuando una ficha o mes no está publicado se muestra como pendiente, nunca como $0.

## Criterios de datos

- Todos los montos se almacenan en pesos chilenos enteros.
- Un dato no publicado se representa como `null`, nunca como cero.
- Totales, promedios y medianas indican siempre cuántos diputados tienen datos publicados.
- Cada registro conserva su URL de fuente y fecha de recolección.

El contrato del piloto está en `public/data/distrito-8/pilot-contract.json` y la estrategia de fuentes en `collector/README.md`.

## Actualizaciones automáticas

- **Actualizar fichas nacionales** reúne actividad, asistencia y comisiones una vez al mes.
- **Actualizar transparencia nacional** consulta un solo mes para las 155 fichas y sus tres categorías de gasto. Puede ejecutarse manualmente indicando el mes `AAAA-MM`; por defecto propone `2026-03` para validar la primera publicación disponible.
