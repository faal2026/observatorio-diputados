# Publicación del piloto

## Primera publicación

1. En GitHub, abre **Settings → Pages**.
2. En **Build and deployment**, selecciona **GitHub Actions** como fuente.
3. Abre la pestaña **Actions**, ejecuta **Publicar sitio** y espera a que termine.
4. La dirección inicial será `https://faal2026.github.io/observatorio-diputados/`.

## Primera recopilación real

1. En la pestaña **Actions**, abre **Actualizar datos Distrito 8**.
2. Selecciona **Run workflow → Run workflow**.
3. Espera el resultado y revisa el enlace de publicación que mostrará GitHub.

## Subdominio propio

Cuando `diputados.felipealcerreca.lat` esté listo:

1. Crea un registro DNS de tipo `CNAME`: `diputados` hacia `faal2026.github.io`.
2. En **Settings → Pages**, ingresa `diputados.felipealcerreca.lat` como dominio personalizado y activa HTTPS cuando esté disponible.
3. En **Settings → Secrets and variables → Actions → Variables**, crea la variable `PAGES_BASE_PATH` con el valor `.`.
4. Ejecuta nuevamente **Publicar sitio**.

La variable del paso 3 hace que la web funcione en la raíz del subdominio, sin agregar `/observatorio-diputados` a las direcciones.
