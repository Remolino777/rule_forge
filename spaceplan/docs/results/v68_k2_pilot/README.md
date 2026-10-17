# V6.8 k2 — Garaje → cocina sin cruzar sala ni comedor (corrida automática, 17 oct 2026)

Piloto de 10 lotes (`tools/run_pilot.py`, entradas congeladas del 14 oct), línea base = k1b
(`docs/results/v68_k1b_pilot/pilot_summary.json`, 28 casas).

## Decisiones aplicadas

Registro `design_circulation_doors` 0.8.0, regla nueva **P16-GARAGE-ROUTE** (`circulation.garage_route.*`):

1. **S2 (duro):** el garaje queda contra una unidad de `zone_opens_to` = servicio o cocina (ya no basta el foyer), y la
   unidad de servicio contra la de cocina (`service_kitchen_adjacent`).
2. **S2 (lectura tomada, por confirmar):** `service_with_kitchen` — en planta baja la zona de servicio se zonifica
   **dentro** de la unidad de cocina (mudroom, lavandería y cocina se acomodan juntos en S2.1). Es la forma más
   directa de "servicio junto a cocina" y la que deja que S2.1 ponga el mudroom entre garaje y cocina.
3. **S2 (consistencia):** los pares D duros de espacios pasables (comedor–cocina, sala–comedor) exigen que sus unidades
   se toquen; antes S2 los daba por buenos si ambos abrían al mismo foyer y S2.1 siempre fallaba en
   `matrix:D:dining-kitchen` (164–206 combinaciones fallidas en corner).
4. **S2.1 (duro):** la puerta garaje–casa abre a mudroom, cocina, lavandería, pasillo o foyer (`door_to_types`); nunca a
   sala, comedor, sala familiar ni dormitorio. La colocación de puertas elige el destino cuyo camino a la cocina no
   cruza `avoid_space_types` (living_room, dining_room, living_dining, family_room) y agrega los vanos que ese camino
   necesita entre espacios pasables. Después se verifica en el grafo de puertas (`route:garage_kitchen`, duro).
5. **S2.1 (blando):** largo del camino por centros de puertas, puntaje 1 hasta 15 ft y cae con escala 15 ft
   (peso 0.15 en la planta baja); destino no preferido (foyer, pasillo) recarga 10 ft; dentro de la unidad contra el
   garaje se premia el mudroom o la cocina sobre el muro del garaje y seguido de la cocina (`unit_weight` 0.3).

La lavandería no es pasable en el catálogo: si la puerta del garaje abre a ella, el camino no sigue a la cocina (haría
falta una segunda puerta). En el piloto ninguna casa la usó; queda **por confirmar** si la lavandería puede ser de paso.

## Indicadores

| Indicador | k1b (antes) | k2 (después) |
|---|---|---|
| Casas (S2.1 espaciadas) | 28 | **11** |
| Celdas zonificadas en S2 | 206 | 149 |
| Garaje → cocina sin cruzar sala/comedor (casas) | 5 de 28 | **11 de 11** |
| Largo garaje → cocina (mediana, centros de puertas) | 29.8 ft | **6.2 ft** |
| La puerta del garaje abre a | foyer (9 de 9 medidas en corner y shallow) | mudroom 9, cocina 2 |
| Medio baño bajo la escalera | 28 de 28 | 11 de 11 |
| Escalera en una sola unidad S2 (casas, abajo / arriba) | 21 / 23 de 28 | 8 / 2 de 11 |

Casas por lote:

| Lote | k1b | k2 |
|---|---|---|
| corner_55x100 | 5 | 0 |
| fan_cul_de_sac_35_80x100 | 0 | 0 |
| fan_curve_35_80x100 | 0 | 0 |
| fan_reverse_80_40x100 | 3 | 2 |
| flag_70x80_pole20 | 0 | 0 |
| hillside_50x100 | 4 | 1 |
| interior_50x100 | 4 | 1 |
| narrow_40x125 | 4 | 2 |
| shallow_50x95 | 4 | 1 |
| trapezoid_asym_45_65x100 | 4 | 4 |

Escaleras de las casas: C U con vacío al frente 5, B U compacta 3, B recta sobre garaje 1, B recta compacta 1,
B recta con descanso compacta 1. Primeras fallas de las celdas sin casa: `unit:social:cuts` 36, `unit:kitchen:cuts` 33,
`unit:circulation:furniture` 12, `unit:private:cuts` 12; ninguna celda falla por `route:garage_kitchen` (la regla se
cumple siempre que S2 deja el garaje contra servicio/cocina).

Láminas: `trapezoid_asym_45_65x100_espacios.png` y `narrow_40x125_espacios.png` (garaje → mudroom → cocina en todas),
`corner_55x100_fallida_S2.png` (zonificaciones de corner que S2.1 no logra espaciar).

## Lectura

- **La regla se cumple en el 100 % de las casas** y el recorrido baja de ~30 ft cruzando el comedor a ~6 ft
  (garaje → mudroom → cocina).
- **El costo es grande: 28 → 11 casas** (por encima del freno de 10). Las casas de k1b tenían casi todas el garaje
  contra el foyer y la cocina al fondo, junto al comedor; con la cocina obligada contra el garaje (al frente) quedan
  menos zonificaciones válidas en S2 (206 → 149 celdas) y las que quedan fallan en S2.1 por cortes de unidades
  (`cuts` de social y cocina), sobre todo en corner (5 → 0).
- Probado en corner + shallow: sin la regla de S2 (solo el camino en S2.1) salen 3 casas de 9; con más alternativas de
  S2 (6 en vez de 3) no mejora. El cuello de botella es la geometría cocina-al-frente + comedor contiguo, no la búsqueda.
- La escalera toca más unidades arriba (23 → 2 de las casas en una sola unidad): las casas que sobreviven son otras
  (más U con vacío al frente).

## Pendientes para el cliente

1. **Lectura de S2:** ¿el garaje puede quedar contra el foyer si el foyer da directo a la cocina (garaje → foyer →
   cocina sin cruzar lo social)? Ver la comparación de la lectura B abajo.
2. **Servicio dentro de la unidad de cocina** (`service_with_kitchen`): lectura tomada, por confirmar.
3. **Lavandería de paso:** ¿puede la puerta del garaje abrir a la lavandería con una segunda puerta a la cocina?
4. Recuperar casas: el siguiente cuello son los cortes de unidades con la cocina al frente (k3 rectángulos lo tocará).

## Lectura B (comparación, no aplicada)

Mismo código con `zone_opens_to` = servicio, cocina **o circulación** (el garaje puede quedar contra el foyer; el
camino sin cruzar lo social se sigue exigiendo en S2.1). Piloto completo de 10 lotes:

| Indicador | k2 aplicada | Lectura B |
|---|---|---|
| Celdas zonificadas en S2 | 149 | 202 |
| Casas | **11** | 9 |
| Camino limpio garaje → cocina | 11 de 11 | 9 de 9 |
| Largo mediano | 6.2 ft | 6.7 ft |
| Puerta del garaje a | mudroom 9, cocina 2 | mudroom 7, cocina 1, foyer 1 |

Relajar S2 devuelve zonificaciones (149 → 202) pero no casas: en S2.1 casi todas cruzan el comedor y se rechazan. La
restricción que manda es el camino en S2.1, no la adyacencia de S2; la lectura literal (aplicada) rinde más.
