# V6.8 k1b piloto: núcleo de escalera primero, zonas libres de 4 ft, bajo-escalera v2 y junta de fondo (17 oct 2026)

Corrida automática (protocolo `docs/plans/v68_autorun.md`). Mismo piloto de 10 lotes con entradas congeladas
(`tools/run_pilot.py`), perfil base del registro (586 parámetros). Línea base: piloto k1 (23 casas), vuelto a correr
con el código de k1 para medir los indicadores nuevos (`indicators.json`, clave `baseline_k1`; reproduce las 23 casas).

## Decisiones del cliente aplicadas (14 oct 12:47 y 17 oct 01:38)

1. **Arranque y llegada con espacio suficiente.** Zona libre al pie y a la llegada de ancho ≥ la escalera y **4 ft de
   fondo** (`stair.arrival_clear.depth_ft = 4`, hard; antes 3 ft al pie y 3 × 3.5 ft arriba). Ninguna hoja abate
   sobre ella (ya lo exigía `swing_forbidden_over`). La zona entera en una sola unidad (S2) y un solo espacio (S2.1)
   de circulación (`single_space`, `circulation_only`, hard).
2. **Núcleo primero en S2.** La unidad receptora se fija sobre el bloque escalera + zona (sus bordes son cortes de
   banda y columna); los bordes del bloque son ejes candidatos del marco; las unidades que toca la escalera se
   puntúan (meta 1, `stair.core.*`).
3. **Bajo la escalera (K13, `client_stair_rules` 0.8.0).** Medio baño solo si ese espacio sale al foyer o a un pasillo
   y cabe; en cualquier otro caso, despensa. Se eliminó la variante "por vestíbulo hacia la sala". El medio baño nunca
   al lado de la escalera, y el par medio baño + vestíbulo solo abre a foyer o pasillo (chequeo nuevo en S2.1).
4. **Escalera al fondo.** El preselect reserva un cupo por borde de junta (lateral y fondo), la U a lo largo primero
   (`stair.joint.*`).
5. **Planta alta sobre el garaje alargada al frente.** Ya ocurre por construcción (fondo = fondo del garaje, crece de
   lado); queda fijado con una prueba. Ninguna casa del piloto tiene 3+ dormitorios sobre el garaje.
6. **Planta baja.** Puerta → arranque y garaje → mudroom → cocina: se miden (abajo); la regla dura es k2.
7. La L sigue fuera.

## Indicadores

| Indicador | k1 | **k1b** |
|---|---|---|
| Casas | 23 | **28** |
| U en la junta espaciadas (zonificadas) | 0 (129) | **1 (72)** |
| Celdas zonificadas en S2 | 255 | 206 |
| Unidades S2 que toca la escalera, media abajo / arriba (todas las zonificadas) | 1.82 / 1.89 | **1.60 / 1.46** |
| Zonificadas con la escalera en 1 sola unidad, abajo / arriba | 35 % / 24 % | **50 % / 58 %** |
| Casas con la escalera en 1 sola unidad S2, abajo / arriba | 17 / 15 de 23 | 21 / 23 de 28 |
| Bajo la escalera en las casas: medio baño / despensa | 21 / 2 | 28 / 0 |
| El medio baño bajo la escalera sale a | foyer 19, cocina 1, mudroom 1 | **foyer 28** |
| Espacio que recibe el arranque / la llegada | foyer 23 / hall 21, family 2 | foyer 28 / **hall 28** |
| Junta de las casas B: lateral / de fondo (cruzada) | 14 / 6 | 18 / 7 |
| Escaleras B zonificadas sobre el garaje: lateral / fondo | 88 / 12 | 59 / 0 |
| Posición del centro (fracción del fondo, mediana) | 0.26 | 0.28 |
| Planta alta sobre el garaje (mediana de las casas) | 546 ft² | 546 ft² |
| Garaje → cocina sin cruzar sala ni comedor (casas) | 6 de 23 | 5 de 28 |
| Largo garaje → cocina (mediana, por centros de puertas) | 30.7 ft | 29.8 ft |

Tipos de escalera de las casas: B recta sobre garaje 13, B recta con descanso compacta 4, C U con vacío al frente 3,
B recta con descanso en voladizo 3, B recta compacta en bandas 2, **B U compacta 1 (la primera U en la junta)**,
B recta en voladizo 1, B recta compacta 1 (k1 tenía 2 casas A con U al frente; ya no salen, causa no medida).

Casas por lote:

| Lote | k1 | k1b |
|---|---|---|
| corner_55x100 | 3 | 5 |
| fan_reverse_80_40x100 | 4 | 3 |
| hillside_50x100 | 4 | 4 |
| interior_50x100 | 4 | 4 |
| narrow_40x125 | 4 | 4 |
| shallow_50x95 | 3 | 4 |
| trapezoid_asym_45_65x100 | 1 | 4 |
| fan_cul_de_sac, fan_curve, flag | 0 | 0 |

## Lectura

- **Más casas con reglas más duras (23 → 28).** Al fijar la unidad de circulación sobre todo el bloque, el foyer deja
  de rodear la escalera y las vecinas pierden muescas: la escalera toca una sola unidad en la mitad de las plantas
  bajas zonificadas y en el 58 % de las altas (antes 35 % y 24 %). Se zonifican menos celdas (255 → 206), pero más
  llegan a planta completa. Ganan corner y trapezoid; fan_reverse pierde una.
- **La U en la junta aparece por primera vez** (corner, early_childhood, planta compacta), pero sigue siendo rara:
  las U fallidas caen ahora en `cuts` de social, cocina y privada (espacios que no se pueden cortar en la unidad que
  queda) y en `structure:frame:posts`, no en el foyer.
- **Bajo la escalera:** todas las casas tienen el medio baño bajo la escalera saliendo al foyer; desaparecen los casos
  hacia cocina o mudroom.
- **La junta de fondo sobre el garaje no funciona con la U a lo largo.** La planta alta tiene el fondo del garaje,
  así que la escalera solo cabe en la parte que no está sobre el garaje (≤ 11 ft de ancho en corner); la U a lo
  largo con su zona de 4 ft pide 13.9 ft. El cupo de fondo solo encuentra la U cruzada, y con las zonas de 4 ft
  ninguna escalera de fondo sobre el garaje llega a zonificarse (k1: 12).
- **Garaje → cocina no mejora** (6 → 5 casas limpias): es el paso k2.

## Pendientes para el cliente (por confirmar)

1. **Solo circulación:** con `circulation_only` duro, los arranques B (desde la sala) y C (desde la cocina) quedan sin
   uso. Es la lectura tomada de "la zona entera dentro de una sola unidad de circulación".
2. **Escalera al fondo sobre el garaje:** para la U a lo largo hace falta que la planta alta pase el fondo del garaje
   (variante V2 hacia atrás) o aceptar la U cruzada en la junta de fondo. La decisión 5 (crecer solo hacia el frente)
   impide la primera.
3. Contrato: el esquema `stack_plan` no acepta `open_air.kind = "porch"` en planta baja (trapezoid); arreglar en S2.2l.

## Innovación (pasos futuros)

- Búsqueda local del núcleo: deslizar el bloque sobre la junta en pasos de 1 ft hasta alinear sus bordes con los ejes.
- Modelo sustituto entrenado con las ~180 celdas zonificadas que no llegan a planta completa, para ordenar candidatos.

## Archivos

- `pilot_summary.json` (casas y diferencia por lote contra k1), `indicators.json` (`tools/v68_indicators.py`, k1 y
  k1b), `quality.md`, `quality_summary.json`.
- `corner_55x100_espacios.png` (5 casas, con la U en la junta), `trapezoid_asym_45_65x100_espacios.png` (4 casas),
  `interior_50x100_U_junta_fallida_S2.png` (zonificación S2 de tres U en la junta sin planta completa).
