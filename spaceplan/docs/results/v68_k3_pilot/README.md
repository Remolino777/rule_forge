# V6.8 k3 — Todos los espacios rectangulares (corrida automática, 17–18 oct 2026)

Piloto de 10 lotes (`tools/run_pilot.py`, entradas congeladas del 14 oct), línea base = k2
(`docs/results/v68_k2_pilot/pilot_summary.json`, 11 casas).

## Decisiones aplicadas

Registro `design_space_standards` 0.9.0, regla nueva **S00-RECTANGLES** (`space.rectangles.*`, 605 parámetros):

1. **Duro:** todo cuarto y espacio de servicio (incluidos clósets, walk-ins, despensa, mudroom) es **un rectángulo**
   (`enabled`, hard). Los espacios fijos de S1 (garaje, escalera, medio baño y vestíbulo bajo la escalera) quedan
   como los dibuja S1.
2. **Lectura tomada (por confirmar):** el **pasillo y el foyer pueden ser compuestos** (unión de rectángulos)
   (`composite_types` = hall, foyer), como dice el documento de observaciones V6.8.
3. **S2.1, unidades en L:** las líneas de las esquinas interiores de una unidad que no es rectángulo (la L que dejan
   el garaje, la escalera o el medio baño) son líneas de corte: los cortes de la guillotina se mueven a ellas a
   ≤ 3 ft (`split_l_units`, `split_reach_ft`). La parte de la regla "partir en S2" se implementó así, dentro de S2.1,
   sin cambiar las unidades ni el grafo de zonas de S2.
4. **S2.1, piso compuesto:** después de las tiras de S2.2j, cada espacio que no es rectángulo se queda con uno de sus
   rectángulos candidatos (el mayor primero) que conserve su área mínima y su lado mínimo; el sobrante, cortado en
   rectángulos, va en el orden `leftover_to`: **circulación** (pasillo o foyer vecino) → **vecino** que siga siendo
   rectángulo → **clóset** del espacio (tamaños de S2.2j) → **porche/techo** si está en fachada → **muro** (solo una
   astilla más angosta que un clóset). Se recolocan las puertas y se verifica `rect:<tipo>` (duro).
5. **Blando:** el puntaje de cada unidad premia la fracción de espacios ya rectangulares (`unit_weight` 0.2).

## Indicadores

| Indicador | k2 (antes) | k3 (después) |
|---|---|---|
| Casas (S2.1 espaciadas) | 11 | **11** |
| Celdas zonificadas en S2 | 149 | 149 |
| Cuartos y espacios de servicio no rectangulares | sala 50 %, dormitorio 50 %, suite 27 %, sala familiar 25 %, comedor 18 %, walk-in 14 %, mudroom 9 %, estudio 5 % | **0 % en todos los tipos** |
| Pasillos / foyers compuestos (permitido) | 56 % / 100 % | 50 % / 100 % |
| Celdas que fallan por `rect:` | — | 0 |
| Sobrante reasignado (ft², 11 casas) | — | circulación 174.5, vecino 54.9, clóset 28.0, muro 4.5, porche/techo 0 |
| Fracción de circulación (mediana por planta) | 0.172 | 0.199 |
| Dormitorio secundario arriba (mediana) | 185 ft² | 130 ft² |
| Walk-in que pasa a clóset (respaldo del programa) | 3 | 5 |
| Tiras de pasillo/foyer reportadas | 45.7 ft² | 82.4 ft² |
| Garaje → cocina limpio (k2) | 11 de 11, 6.2 ft | 11 de 11, 6.2 ft |

Casas por lote (sin cambios): corner 0, fan_cul_de_sac 0, fan_curve 0, fan_reverse 2, flag 0, hillside 1,
interior 1, narrow 2, shallow 1, trapezoid 4. Escaleras de las casas: C U con vacío al frente 4, B U compacta 3,
B recta compacta 2, B recta sobre garaje 1, B recta con descanso compacta 1. Primeras fallas de las celdas sin casa:
`unit:kitchen:cuts` 41, `unit:social:cuts` 32, `unit:private:cuts` 12 (como en k2; ninguna por la regla nueva).

Láminas: `trapezoid_asym_45_65x100_espacios.png` (4 casas), `narrow_40x125_espacios.png` y
`fan_reverse_80_40x100_espacios.png` (2 cada una), `corner_55x100_fallida_S2.png` (zonificaciones de corner que S2.1
sigue sin espaciar).

## Lectura

- **La regla se cumple en el 100 % de los cuartos sin perder casas (11 → 11).** Las muescas venían casi todas de
  objetos fijos (el garaje mordiendo el comedor o la sala familiar, el medio baño bajo la escalera mordiendo la
  sala) y de clósets o pasillos arriba; ahora se resuelven cortando en la línea de la esquina o moviendo el sobrante.
- **El costo va a la circulación:** el 67 % del sobrante (174 de 262 ft²) termina en pasillos y foyers, que suben
  de 17 % a 20 % del piso y siguen compuestos. Los dormitorios secundarios quedan más chicos (mediana 185 → 130 ft²)
  y dos walk-ins más bajan a clóset.
- El foyer sigue grande y nunca rectangular (k5 lo trata como nodo).

## Pendientes para el cliente

1. **Confirmar la lectura:** ¿pasillo y foyer pueden ser compuestos, o también deben ser rectángulos? (Con el foyer
   rectangular el sobrante tendría que ir a clósets o muros, y hoy es el destino de dos tercios.)
2. ¿Se acepta que el sobrante agrande la circulación (≈ +3 puntos) o se prefiere que vaya primero a clósets?
3. Pendientes de k2 siguen abiertos (servicio dentro de la unidad de cocina; lavandería de paso).
