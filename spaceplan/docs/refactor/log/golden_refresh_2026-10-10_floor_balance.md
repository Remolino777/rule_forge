# Golden snapshot refresh — reparto balanceado entre pisos (paso 9a, 2026-10-10)

Aprobado por el cliente el 10-oct-2026 ("Empieza el código del paso 9a").

## Paquetes de capacidad
Cambian solo por la versión y el hash del catálogo (0.12.0 → 0.13.0, `program_review/catalog_*` y `cost/sources`). La capacidad, el sitio, la zonificación y el costo no cambian.

## Tabla del análisis de áreas (`area_matrix_cells.csv`)
- Filas: 3373 → 3369. Columnas nuevas: `balanced_up` y `maximum_trimmed`.
- Mejores celdas: 976 → 1022; de dos pisos: 245 → 291.
- Estados: {'fits': 2691, 'exceeds_design_footprint': 570, 'exceeds_coverage': 11, 'fits_small_garden': 38, 'site_fails': 59} (antes {'fits': 2606, 'exceeds_design_footprint': 661, 'exceeds_coverage': 19, 'fits_small_garden': 34, 'site_fails': 53}).
- Máximos sin esquema viable: 64 → 18 (todos del lote fan-curve, por `site_fails` del pavimento del antejardín, 131.0447).

## Causas
1. Regla del cliente VB01 `ground_balance` (catálogo 0.13.0): family room, study, flex room y storage suben hasta que la planta baja cabe en la huella de diseño.
2. Máximo recortado a lo largo de la curva de expansión cuando ningún reparto cabe (`design_footprint_ground`).
