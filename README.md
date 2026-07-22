# Observatorio Parlamentario

Observatorio de transparencia pública de la Cámara de Diputadas y Diputados de Chile. La nómina, la actividad legislativa y la asistencia cubren las 155 fichas nacionales; la transparencia se actualiza en una tarea nacional independiente, sin repetir la extracción legislativa.

## Alcance inicial

- Identidad territorial, comisiones, actividad legislativa, asistencia y oficios.
- Transparencia mensual: dieta, gastos operacionales, asesorías externas, pasajes y personal de apoyo.
- Mapa horizontal de las 16 regiones, filtros nacionales y ficha por diputado o diputada.
- Tablero nacional, mapa territorial interactivo y ficha detallada para las 155 diputadas y diputados.
- Transparencia nacional: asesorías externas y personal de apoyo se incorporan desde directorios generales de la Cámara; gastos operacionales y pasajes se muestran como pendientes hasta contar con un directorio nacional equivalente o una fuente autorizada.
- Personal de apoyo se mantiene separado: la fuente disponible describe remuneraciones de contratos vigentes, no gasto rendido.
- Cuando una ficha o mes no está publicado se muestra como pendiente, nunca como $0.

## Criterios de datos

- Todos los montos se almacenan en pesos chilenos enteros.
- Un dato no publicado se representa como `null`, nunca como cero.
- Totales, promedios y medianas indican siempre cuántos diputados tienen datos publicados.
- Cada registro conserva su URL de fuente y fecha de recolección.

El contrato del piloto está en `public/data/distrito-8/pilot-contract.json` y la estrategia de fuentes en `collector/README.md`.

## Actualizaciones automáticas

- **Actualizar fichas nacionales** reúne actividad, asistencia y comisiones una vez al mes.
- **Actualizar transparencia nacional** mantiene el mecanismo anterior de verificación para las fuentes de la Cámara. Si ésta rechaza las consultas automatizadas, no publica ceros.
- **Publicar recolector de transparencia** instala en Cloudflare el recolector mensual independiente. Sus instrucciones están en `worker/observatorio-transparencia/README.md`; las credenciales de Cloudflare quedan guardadas como secretos de GitHub, nunca dentro del repositorio.
