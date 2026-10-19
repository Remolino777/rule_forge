# V6.8 k4 — Clóset de pared por dormitorio en muro interior completo (corrida automática, 19 oct 2026)

Piloto de 10 lotes (`tools/run_pilot.py`, entradas congeladas del 14 oct), línea base = k3
(`docs/results/v68_k3_pilot/pilot_summary.json`, 11 casas).

**Resultado: FRENO.** El piloto deja **9 casas** (k3: 11), por debajo de `stop_houses_min` = 10. El paso queda
`blocked` y la corrida automática se detiene (`halted`) hasta que el cliente decida. Todos los tests pasan con el
código commiteado; la regla se puede volver blanda o apagar desde el registro sin tocar código.

## Decisiones aplicadas

Registro `design_space_standards` 0.10.0, regla nueva **S00-WALL-CLOSETS** (`space.wall_closets.*`, 613 parámetros):

1. **Duro:** todo dormitorio y suite **sin walk-in** tiene un clóset de pared de 2 ft de fondo (puerta corrediza —
   los clósets ya son `sliding_space_types` —, 3 ft libres al frente) que ocupa **el muro completo**, nunca un pedazo
   (`enabled`, `full_wall`, `depth_ft`, `front_clear_ft`, todos hard).
2. **Muro:** orden `walls` = interior → lateral exterior (solo respaldo); **nunca** fachada frontal ni posterior
   (frente = −y del marco local, hacia la calle).
3. **S2.1, programa (`in_room_program`):** el clóset del programa de un dormitorio sin walk-in se suma al cuarto
   (área objetivo y tope) y el chequeo duro de mobiliario exige cama + clóset (11 × 10 ft de cama con holguras más
   2 ft a un lado). Así el cuarto nace con el fondo del clóset.
4. **S2.1, piso compuesto** (después de los rectángulos de k3, `lib/wall_closets`): un cuarto cuyo clóset ya cubre
   un muro completo permitido lo conserva; si no, sus clósets parciales vuelven al cuarto cuando la unión sigue
   siendo rectángulo (`merge_partial`, lectura del diseñador) y una franja de 2 ft a lo largo del **muro válido más
   corto** pasa a ser su clóset, si el cuarto conserva lado y área mínimos, el frente libre, la cama y el contacto
   que piden sus puertas con cada vecino. Se recolocan puertas (si fallan, cuarto por cuarto) y se verifica
   `wall_closet:<tipo>:<estado>` (duro).

## Indicadores

| Indicador | k3 (antes) | k4 (después) |
|---|---|---|
| Casas (S2.1 espaciadas) | 11 | **9** |
| Dormitorios sin walk-in con clóset | 6 de 7 (trapezoid, medido con la geometría) ; especificación: 26 de 60 | **8 de 8** |
| Dormitorios sin clóset | 1 de 7 (trapezoid); especificación: 34 de 60 | **0** |
| Clósets de dormitorio que cubren un muro completo | 2 de 6 (trapezoid) | **8 de 8** (+ 2 clósets parciales de sobrante que quedan, ver pendientes) |
| Muro del clóset de pared (reporte del pase) | — | interior 6, lateral exterior 2, frente 0, fondo 0 |
| Clósets en muro exterior | especificación: 114 de 135 | 2 de 10 (los dos laterales de respaldo; la medida geométrica de fondo sobre el contorno cuenta 1) |
| Estado antes del pase (11 dormitorios) | — | ya bien 5, parcial 2, sin clóset 1, con walk-in 3 → tallados 3 |
| Cuartos no rectangulares (k3) | 0 % | 0 % |
| Garaje → cocina limpio (k2) | 11 de 11, 6.2 ft | 9 de 9, 5.6 ft |
| Fracción de circulación (mediana) | 0.199 | 0.208 |
| Mobiliario que no cabe | 10.6 % | 9.6 % |
| Clósets por rol (clóset / blancos / baño) | 35 / 9 / 9 | 30 / 6 / 7 |

La columna "antes" de clósets se midió con `tools/v68_indicators.py` sobre una corrida de k3 del lote trapezoid
(4 casas, `k3_trapezoid_closets_baseline.json`); el piloto completo de k3 no guardó los planos. Las cifras de la
especificación (34 de 60, 114 de 135) vienen del análisis de observaciones V6.8.

Casas por lote: corner 0, fan_cul_de_sac 0, fan_curve 0, fan_reverse 2, flag 0, hillside 1, interior 1, narrow 2,
shallow 1, **trapezoid 4 → 2**. Escaleras: B U compacta 3, C U con vacío al frente 2, B recta compacta 2, B recta
sobre garaje 1, B recta con descanso 1.

Láminas: `trapezoid_asym_45_65x100_espacios.png`, `narrow_40x125_espacios.png`, `fan_reverse_80_40x100_espacios.png`
(casas con su clóset de pared) y `trapezoid_teens_fallida_S21.png` (zonificaciones de teens_family que S2.1 ya no
espacia).

## Lectura

- **La regla se cumple en todos los dormitorios espaciados**: 8 de 8 sin walk-in tienen un clóset de muro completo,
  6 en muro interior y 2 en muro lateral exterior; ninguno en fachada frontal ni posterior.
- **Se pierden las dos casas teens_family del trapecio** (escalera C, U con vacío al frente). Diagnóstico (contando
  por qué falla cada muro en ≈ 2 400 distribuciones de la planta alta):
  1. **Dormitorios de 11 × 10 ft**: la cama con holguras llena el cuarto y no queda fondo para el clóset (≈ 70 %).
     Con el clóset dentro del programa y el chequeo cama + clóset en S2.1, la búsqueda ya no los produce, pero la
     unidad privada no encuentra otro reparto.
  2. **Dormitorios de 11 × 13.5 ft**: el único muro interior que deja la cama es el del pasillo, que lleva la
     puerta; los muros largos dejarían 9 ft de ancho (la cama pide 10) y el otro lado es fachada frontal.
  Se probó además un filtro en S2.1 (cada dormitorio debe tener un muro válido que no sea el de su única puerta al
  pasillo): el trapecio sigue en 2 casas, así que no se dejó en el código.
- El costo de área es moderado: la circulación sube 0.9 puntos y el mobiliario que no cabe baja.

## Pendientes para el cliente (decidir antes de seguir con k5)

1. **¿Cómo seguir con 9 casas?** Opciones:
   a. Aceptar el clóset **en el muro de la puerta** (muro completo menos el vano de la puerta y su abatimiento) —
      es la solución típica del dormitorio secundario; hoy lo prohíbe "nunca un pedazo".
   b. Permitir la **fachada frontal o posterior** como último respaldo (`walls` += front/rear).
   c. Volver la regla **blanda** (`space.wall_closets.enabled` → soft): se puntúa y se reporta, sin descartar casas.
   d. Bajar `stop_houses_min` a 9 y seguir.
2. Clósets parciales de sobrante (de k3 o S2.2j) que no pueden volver a su cuarto: quedan como clóset extra (2 en el
   piloto). ¿Se convierten en muro/vecino o se aceptan como guardado adicional?
3. Lectura del diseñador, por confirmar: un clóset parcial se une al cuarto y se talla de nuevo (`merge_partial`).
