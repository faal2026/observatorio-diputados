# Recolector externo de transparencia

Este Worker evita que GitHub Actions consulte las fichas individuales que la Cámara rechaza desde sus rangos de red. Guarda un corte mensual en Workers KV y expone una salida JSON pública de sólo lectura.

## Primera activación desde GitHub

No es necesario instalar nada en el computador. Antes de ejecutar el flujo de publicación, agrega dos secretos en **GitHub → Settings → Secrets and variables → Actions**:

1. `CLOUDFLARE_ACCOUNT_ID`: el identificador de tu cuenta de Cloudflare.
2. `CLOUDFLARE_API_TOKEN`: un token de Cloudflare con permiso **Edit Cloudflare Workers**, limitado a esta cuenta.

Luego abre **Actions → Publicar recolector de transparencia → Run workflow**. Cloudflare creará el espacio KV indicado en la configuración y publicará el Worker. Conserva la URL `workers.dev` que aparece al final del registro de la ejecución.

Para generar el primer corte, en Cloudflare abre **Workers & Pages → observatorio-transparencia → Settings → Triggers** y ejecuta el evento programado una vez. Ese corte queda disponible en `https://<tu-worker>.workers.dev/v1/transparency`.

## Qué publica

- `external_advisories`: asesorías externas del directorio mensual general de la Cámara, con total nacional, montos por diputado/a y filas que requieren revisión de nombre.
- Las demás categorías quedan explícitamente en espera hasta disponer de un directorio general equivalente o de una autorización de acceso automatizado. Nunca se publican como cero.

## Programación

El cron se ejecuta el día 12 de cada mes a las 17:20 UTC, cuando la Cámara ya debería haber publicado el período con desfase. Cloudflare documenta que los cron triggers se ejecutan en UTC y pueden tardar algunos minutos en propagarse.
