# Golden snapshot refresh — área lógica de diseño (2026-10-09)

Aprobado por el cliente el 9-oct-2026 (FOS de diseño, FOT editable, un piso primero, escalera corregida).

## Paquetes de capacidad
Cambian solo por la escalera del catálogo 0.12.0 (60 → 44 sq ft por piso) en la opción de dos pisos del costo y por la versión del catálogo; la capacidad, el sitio y la zonificación no cambian.

- `package_apt_2br_corner.json`: program_review/catalog_sha256, program_review/catalog_version
- `package_apt_2br_interior.json`: program_review/catalog_sha256, program_review/catalog_version
- `package_corner_55x100.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version
- `package_fan_cul_de_sac_35_80x100.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version
- `package_fan_curve_35_80x100.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version
- `package_fan_reverse_80_40x100.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version
- `package_flag_70x80_pole20.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version
- `package_hillside_50x100.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version
- `package_interior_50x100.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version
- `package_interior_50x100_multigen.json`: cost/budget, cost/options, cost/sources, program_review/catalog_sha256, program_review/catalog_version
- `package_interior_50x100_multigen_anglo.json`: cost/budget, cost/options, cost/sources, program_review/catalog_sha256, program_review/catalog_version
- `package_interior_50x100_multigen_latino.json`: cost/budget, cost/options, cost/sources, program_review/catalog_sha256, program_review/catalog_version
- `package_narrow_40x125.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version
- `package_shallow_50x95.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version
- `package_trapezoid_asym_45_65x100.json`: cost/budget, cost/options, cost/sources, cost/tornado, program_review/catalog_sha256, program_review/catalog_version

## Tabla del análisis de áreas (`area_matrix_cells.csv`)
- Filas: 3148 → 3373.
- Mejores celdas: 1032 → 976; de dos pisos: 519 → 245.
- Estados nuevos: {'fits': 2606, 'exceeds_design_footprint': 661, 'exceeds_coverage': 19, 'fits_small_garden': 34, 'site_fails': 53} (antes {'fits': 2883, 'fits_small_garden': 146, 'exceeds_coverage': 19, 'site_fails': 100}).
- Mejores por perfil y pisos (nuevo): {('accessible', '1'): 124, ('accessible', '2'): 81, ('maximum', '1'): 6, ('maximum', '2'): 140, ('minimum', '1'): 210, ('optimum', '1'): 205, ('staged_final', '1'): 186, ('staged_final', '2'): 24}.

## Causas
1. Variables de diseño del cliente (`client_design_variables.json`): FOS 0.60 sobre la envolvente (estado `exceeds_design_footprint`), FOT del SDMC.
2. Política `one_floor_first`: los dos pisos solo se clasifican si un piso no cabe.
3. Óptimo `footprint`: el mayor programa de la curva que cabe en un piso dentro de la huella; máximo al FOT efectivo menos la escalera en dos pisos.
4. Escalera 44 sq ft por piso (catálogo 0.12.0).

La lógica anterior se reproduce con `--legacy-areas` (salvo el valor de la escalera).
