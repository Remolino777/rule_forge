# V6.8 — corrida automática k1b → k5 (programada el 17 oct 2026)

Este archivo es la especificación que siguen las corridas programadas. El estado vive en
`spaceplan/docs/plans/v68_autorun_state.json`. Cada corrida hace **un paso**, lo prueba, corre el piloto, documenta,
hace commit y push, y deja el estado listo para la siguiente.

## Protocolo de cada corrida

1. `cd` al repositorio `Remolino777/rule_forge`, rama `stacking/6.7a-s2.2` (`git fetch && git checkout
   stacking/6.7a-s2.2 && git pull`). Instalar si falta: `pip install -e spaceplan[dev] --break-system-packages`.
2. Leer el estado.
   - Si `halted` es true, o todos los pasos están `done`: no hacer nada más que reportar el estado y terminar.
   - Si un paso está `in_progress` con `started_at` de hace menos de `stale_hours`: otra corrida lo está haciendo;
     terminar sin tocar nada.
   - Si está `in_progress` y vencido: retomarlo desde lo que haya en la rama (revisar `git log` y el estado del
     código), no empezar de cero.
3. Tomar el primer paso `pending` (o el vencido), ponerlo `in_progress` con `started_at` (ISO, UTC), commit
   `"V6.8 autorun: <id> started"` y push (es el candado).
4. Leer: `spaceplan/HANDOFF_spaceplan.md` (sección 4ac en adelante y sección 10), este archivo, y el código que
   el paso toca. Línea base = el `pilot_summary.json` del último paso `done` (o `baseline_summary`).
5. Implementar el paso según su especificación de abajo. Reglas fijas del proyecto:
   - código en inglés; modular `main/` (flujo), `lib/` (funciones), `lib_aux/` (subfunciones);
   - **ningún número normativo en el código**: los valores van al registro de diseño
     (`spaceplan/data/design/*.json`, con `kind` hard/soft) o a las reglas (`spaceplan/data/rules/*.json`,
     subir versión) o al catálogo (`stacking_catalog.json`, subir versión y actualizar los tests de contrato que la
     fijan); el test de literales normativos debe pasar;
   - tests nuevos en `tests/stacking/test_stage_s22<letra>.py` (k1b → `test_stage_s22k1b.py`, etc.);
   - si cambia la salida del módulo, regenerar fixtures con `python tools/make_fixtures.py write`.
6. `python -m pytest -q -x` en `spaceplan/` hasta que **todo** pase (hoy son 1590 tests). No desactivar ni borrar
   tests existentes para que pasen; si un test viejo choca con una decisión nueva del cliente, actualizarlo y
   explicar por qué en el commit.
7. Piloto: `python tools/run_pilot.py /tmp/v68_<id> --jobs 2 --baseline <línea base>` (≈ 50 min) y
   `spaceplan quality --stack-plans /tmp/v68_<id>/stack_plan_*.json --out /tmp/v68_<id>/quality`.
   Medir además los indicadores propios del paso (abajo).
8. Resultados en `spaceplan/docs/results/v68_<id>_pilot/`: `README.md` en español (decisiones aplicadas, tabla de
   indicadores antes/después, casas por lote, lectura, pendientes para el cliente), `pilot_summary.json`,
   `quality.md`, `quality_summary.json` y 2–3 láminas PNG de plantas (las mejores y una fallida). Actualizar
   `HANDOFF_spaceplan.md` (nueva sección 4a<letra> y la sección 10). Si el Project de claude.ai está disponible,
   escribir también `claude/spaceplan_V6_8_<id>_resultados.md`.
9. Estado: `done`, `finished_at`, `commit`, `houses`, `notes` (una línea).
   **Freno:** si las casas del piloto quedan por debajo de `stop_houses_min`, o si no se logra que pasen todos los
   tests, poner el paso en `blocked`, `halted: true` y `halt_reason`, hacer commit de lo que haya (los tests deben
   pasar en lo que se commitea; si no, commitear solo el análisis en `docs/` y dejar el código en una rama
   `autorun/<id>-wip`), y avisar al usuario. Las siguientes corridas no avanzan hasta que el usuario decida.
10. Commit `"V6.8 <id>: <resumen>"` (con las líneas de atribución de la sesión) y push a
    `stacking/6.7a-s2.2`. Terminar con un mensaje corto al usuario: paso hecho, casas antes → después, lo más
    importante y el siguiente paso.

Las decisiones de abajo ya están tomadas por el cliente: **no preguntar**; donde una lectura no está confirmada se
toma la indicada y se reporta en el README como "por confirmar".

---

## k1b — U en la junta, escalera al fondo, planta alta sobre el garaje

Análisis previo (14 oct): la U en la junta nunca se espacia (0 de 238 intentos en S2.1). Causas medidas:
(1) el marco de S2 corta franjas sin mirar la escalera y la U (8.2 × 9.9 ft) queda a caballo de dos franjas — toca
2.0 unidades en promedio contra 1.25 de las rectas exitosas — y deja el foyer como anillo y muescas en las
vecinas ("cuts"); (2) en plantas altas angostas (front, compact, compact_bands) la U no deja zona privada;
(3) medio baño bajo una U no cabe (34 fallas); (4) arranque junto a la puerta garaje–casa (17); (5) en
over_garage el 94 % de las escaleras va al borde lateral: el fondo no se explora.

Decisiones del cliente (14 oct 12:47 y 17 oct 01:38):
1. **Arranque y llegada con espacio suficiente:** zona libre al pie y a la llegada de ancho ≥ ancho de la escalera
   y **4 ft de fondo** (registro, p. ej. `stair.arrival_clear.depth_ft = 4`, hard); ninguna hoja de puerta abate
   sobre ella; la zona entera dentro de una sola unidad de circulación (foyer o pasillo, hall o vestíbulo arriba).
   En la U girada a lo largo de la junta las dos zonas quedan del mismo lado.
2. **Núcleo primero en S2:** la escalera + sus zonas de arranque y llegada son un bloque; los bordes del bloque
   son líneas de corte del marco (`floor_frame`, `core_zoning`, `frame_positions`); la franja de circulación se
   dimensiona al fondo del bloque. Indicador: unidades que toca la escalera (meta: 1).
3. **Bajo la escalera:** medio baño **solo** si el espacio bajo la escalera sale al foyer o a un pasillo y el medio
   baño cabe; en cualquier otro caso es **despensa**. Se elimina la variante "por vestíbulo hacia la sala"
   (`stair_access.under_stair_use`, reglas K03/K04 → nueva versión de `client_stair_rules.json`). El medio baño
   nunca se pone al lado de la escalera; si no va bajo la escalera, va donde S2.1 lo ubique en la circulación como
   cualquier espacio.
4. **Escalera al fondo:** en over_garage (y rear) un ancla "junta de fondo" con la U a lo largo de la junta; el
   preselect reserva un cupo por borde de junta (lateral y fondo) y no solo por cercanía a la puerta.
5. **Planta alta sobre el garaje alargada al frente:** con 3 o más dormitorios arriba, la planta alta over_garage
   crece de lado sobre el frente de la casa (no hacia atrás); la junta de fondo se conserva. Pasillo desde la llegada
   hacia los dormitorios de fachada; baño sobre el núcleo húmedo de abajo.
6. **Planta baja:** línea puerta → arranque (el foyer puede volverse pasillo); garaje → mudroom → cocina junto a
   la escalera cuando la geometría lo permite (k2 la hace obligatoria).
7. **La L queda fuera** (K07 ya lo dice; no reabrir).

Indicadores: casas (total y por lote), U en la junta espaciadas, tipo de escalera de las casas, unidades que toca la
escalera, uso bajo la escalera (medio baño / despensa) y hacia qué sale, posición de la escalera (borde de junta y
fracción de fondo), área de la planta alta over_garage.

## k2 — Garaje → cocina sin cruzar sala ni comedor (obligatorio)

- S2: el garaje queda junto a la unidad de servicio o de cocina, y servicio junto a cocina (adyacencia dura en la
  zonificación de planta baja).
- S2.1: la puerta garaje–casa abre a mudroom, lavandería, cocina o pasillo de servicio (nunca a sala, comedor,
  dormitorio ni foyer principal si eso obliga a cruzar lo social); el grafo de puertas debe tener un camino
  garaje → cocina que no pase por living_room, dining_room, living_dining ni family_room (hard, registro). La
  longitud del camino se puntúa (soft) y se reporta.
- Indicadores: casas, casas con camino garaje–cocina válido (meta: todas las espaciadas), longitud mediana del
  camino (antes: 25 de 29 casas cruzaban sala o comedor, mediana 43 ft), espacio al que abre la puerta del garaje.

## k3 — Todos los espacios rectangulares (obligatorio)

- Lectura tomada (por confirmar con el cliente): todos los cuartos y espacios de servicio son rectángulos; **el
  pasillo y el foyer pueden ser compuestos** (unión de rectángulos), como dice el documento de observaciones V6.8.
- S2: las unidades en L se parten en rectángulos antes de S2.1.
- S2.1: cada espacio es su rectángulo; el sobrante se asigna a clóset, pasillo, porche, techo o muro (reusar la
  lógica de tiras de S2.2j); validación de rectangularidad hard en el registro.
- Indicadores: casas, % de espacios rectangulares por tipo (antes: sala 50 %, suite 46 % no rectangulares),
  sobrantes por destino.

## k4 — Clóset de pared por dormitorio en muro interior completo

- Todo dormitorio sin walk-in lleva un clóset de pared en el programa (2 ft de fondo, puerta corrediza, 3 ft libres
  al frente — ya en S2.2j).
- Va sobre un muro **interior**; un muro lateral exterior solo como respaldo extremo; nunca la fachada frontal ni
  la posterior. Ocupa **el muro completo**, nunca un pedazo (hard).
- Indicadores: dormitorios con clóset (antes: 34 de 60 sin clóset), clósets en muro interior (antes: 114 de 135 en
  muro exterior), clósets de muro completo, casas.

## k5 — Foyer como nodo

- KPIs y puntaje (soft) del foyer: forma, conexiones entrada → social → escalera, un cuadro libre de **5 × 5 ft**
  frente a la puerta principal (registro).
- El foyer conecta directo con la escalera (arranque) y con lo social; puntaje en la elección de S2.1.
- Indicadores: foyers con 5 × 5 libre, conexiones, área (antes: mediana 161 ft², nunca rectangular), casas.

## Después de k5

La corrida que encuentre todo `done` escribe un resumen final (`spaceplan/docs/results/v68_k_summary.md`: casas por
paso, indicadores clave, pendientes para el cliente) y avisa al usuario. S2.2l (reorganización, 1–25 nov) no se
corre en automático.
