# Importaciones oficiales de transparencia

Este directorio guarda los archivos mensuales descargados manualmente desde la
Transparencia Activa de la Cámara. No son datos estimados: cada archivo es el
respaldo reutilizable de los montos mostrados en el Observatorio.

## Cómo incorporar un mes

1. Abrir los directorios nacionales de la Cámara:
   - [Asesorías externas](https://www.camara.cl/transparencia/asesoriasexternasgral.aspx)
   - [Personal de apoyo](https://www.camara.cl/transparencia/personalapoyogral.aspx)
2. Elegir el mes y año que efectivamente tenga filas publicadas.
3. Usar el botón de exportación de cada directorio.
4. Subir el archivo a este directorio con uno de estos nombres exactos:

```text
asesorias-2026-05.xls
personal-apoyo-2026-05.xls
```

También se aceptan `.xlsx`, `.csv` y `.html`. Si un `.xls` no puede ser leído,
abrirlo con Excel y usar **Guardar como → Libro de Excel (.xlsx)**.

Al subir un archivo a `main`, GitHub ejecuta la importación, cruza los nombres
con la nómina oficial de 155 diputados(as), genera la cobertura y vuelve a
publicar el sitio. Los nombres que no logren cruzarse se conservan en el
reporte de importación: nunca se asignan a otra persona ni se convierten en $0.

## Alcance actual

- `asesorias-*`: monto mensual publicado por asesoría externa.
- `personal-apoyo-*`: suma de sueldos publicados para contratos vigentes; es
  una fotografía del directorio, no una rendición mensual.
- Gastos operacionales y pasajes aún requieren un archivo nacional entregado
  por la Cámara o una solicitud de información formal.
