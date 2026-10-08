# Paso 6.6 — Análisis de áreas por lote (programa × esquema vertical × estrategia)

Módulo `spaceplan` · Municipal Permit Intelligence · Capstone MS-AAI, University of San Diego · octubre 2026.
Todos los valores de diseño son hipótesis `provisional`; el índice de costo es comparativo, nunca una cotización.
Reproducir: `spaceplan areas --zone-top 2 --sheets examples/area_matrix/figures --tables examples/area_matrix`
(≈ 2.5 min; sin E2 ≈ 40 s).

## 1. Qué se evalúa

| Dimensión | Valores |
|---|---|
| Lotes del piloto (10) | interior 50×100, esquina 55×100, **poco profundo 50×95**, **angosto 40×125**, **ladera 50×100**, abanico cul-de-sac, abanico en curva, abanico inverso, trapecio, **bandera 70×80 + acceso 20 ft** (nuevos en negrita) |
| Hogares (21) | 7 arquetipos × 3 perfiles culturales (sin perfil, latino, anglosajón) |
| Programas (5) | mínimo, óptimo, máximo, accesible, por etapas (estado final) — de 6.5d, con el FAR del lote como techo |
| Esquemas verticales (6) | V0 un piso · V1 privada arriba · V2 suite principal abajo · V3 dos generaciones por piso · V4 planta alta parcial · V5 social arriba (solo con vista o ladera) |
| Estrategias (4) | A rectángulo · B2 / B3 escalonado · P poligonal (colapsan a A cuando todas sostienen la misma huella) |

Resultado: **3,148 celdas** (programa × esquema), cada una con su veredicto por estrategia.

## 2. Índices de construcción y de ocupación

Familia de reglas de razón en el DSL (`Z15-BUILDING-INDICES`): cada índice declara numerador, denominador y la regla
que lo limita; otra jurisdicción (p. ej. un POT colombiano) se declara solo en datos.

| Índice | Definición | Límite en RS-1-7 |
|---|---|---|
| **IC** (construcción) | área construida total / área del lote | FAR de la Tabla 131-04J sobre el área base (0.60 hasta 5,000 sq ft; 0.59 hasta 6,000) |
| **IO** (ocupación) | huella de planta baja / área del lote | solo en ladera: 50 % si más de la mitad del lote es ladera pronunciada (131.0445(a)); en lotes planos no hay razón límite |
| IC por piso | área de cada piso / área del lote | desglose, sin límite |

**Garaje en el IC (pendiente de verificar SDMC 113.0234).** Se evalúan dos lecturas: garaje incluido (por defecto,
conservadora) y garaje excluido (sensibilidad). Resultado: **ninguna celda cambia de veredicto** (0 de 3,148),
porque los programas de 6.5d ya se cortan en el FAR con el garaje incluido. Lo que cambia es la holgura: excluir el
garaje baja el IC de los máximos en **0.05–0.10 (media 0.084)**, es decir, habilitaría ≈ 250–500 sq ft más de
vivienda por lote. Es una ambigüedad normativa con consecuencia medible: prioridad para RuleForge.

**Escalera y FAR.** Dos pisos suman la escalera en cada piso (2 × 60 sq ft): el IC sube ≈ 0.024 en un lote de
5,000 sq ft. Un máximo de un piso que llega al FAR no cabe en dos pisos; el máximo de dos pisos se recalcula con el
techo FAR − escalera (programa ≈ 120 sq ft menor).

## 3. Esquemas verticales y el criterio de cada hogar

Un esquema asigna grupos de espacios a pisos (`vertical_schemes` del catálogo). Reglas duras: lo que tiene
`floor_preference` 0 (movilidad, garaje) queda abajo y **la suite se mueve completa** (nunca se parte entre pisos);
los espacios alojados siguen a su anfitrión; la lavandería sigue el aspecto cultural (anglosajón: cerca de los
dormitorios; latino: con la cocina y el patio de servicio). Un esquema que queda sin nada habitable arriba se
reporta como no aplicable; dos esquemas que producen la misma distribución se reportan como equivalentes (`=V1`).

El hogar **pondera, no excluye** (`scoring.multipliers`): VS01 movilidad prevista o reducida de la pareja principal
(independencia de la escalera ×3), VS02 niños de 0–5 (supervisión ×2), VS03 adolescentes o adultos no emparentados
(separación ×2), VS04 niños o patio de juego (área libre ×1.25), VS05 residentes temporales. La trayectoria cuenta:
una regla se activa si vale hoy o en la etapa siguiente. El cliente puede fijar un esquema (`--scheme Vx`) y se
evalúa aunque su condición no se cumpla.

Métricas en [0, 1]: área libre (lote − huella − pavimento − deck, complemento del IO), independencia de la escalera
(área de uso diario fuera del piso de entrada), supervisión, separación, eficiencia de la planta alta (≥ 300 sq ft
útiles), holgura de frente, costo (1 − índice). Es un **indicador provisional** hasta el puntaje común de 6.8.

## 4. Evaluación escalonada

| Etapa | Qué mide | Costo |
|---|---|---|
| E0 | IC, IO (dos variantes de garaje), contención de la planta alta, huella vs capacidad de cada estrategia, frente duro (garaje + entrada) y blando (+ ancla de la sala) | aritmética |
| E1 | acceso, pavimento del antejardín (131.0447), deck, jardín y área libre medidos por la capa de sitio, por estrategia | ≈ 5 ms por huella, con caché |
| E2 | zonificación completa de un piso para las 2 mejores celdas de un piso por lote (arquetipos distintos) | 1–14 s por celda |

Estados, en el orden que nombra la restricción que manda: excede IC → excede IO → planta alta mayor que la baja →
excede la huella de la estrategia → frente insuficiente → sitio no cumple; si no, cabe (o cabe con jardín bajo
el umbral indicativo de 20 % del lote).

## 5. Resultados del piloto

### 5.1 Qué restricción manda en cada lote

| Lote | IC máx. | IO máx. | Capacidad 1 piso (A / B2 / B3 / P) | Celdas que no cumplen | Restricción que manda |
|---|---|---|---|---|---|
| interior 50×100 | 0.60 | — | 3,024 (iguales) | 0 | ninguna (jardín en máximos) |
| esquina 55×100 | 0.59 | — | 3,312 (iguales) | 0 | ninguna |
| poco profundo 50×95 | 0.60 | — | 2,961 (iguales) | 0 | jardín (25 celdas bajo el umbral) |
| angosto 40×125 | 0.60 | — | 3,259 (iguales) | 0 | ninguna; frente útil 33.6 ft |
| ladera 50×100 | 0.60 | **0.50** | 3,024 (iguales) | **19 por IO** | **IO**: los máximos de un piso (y V4) superan el 50 % |
| abanico cul-de-sac | 0.59 | — | 2,416 / 3,077 / 3,299 / 3,744 | 31 | **pavimento del antejardín** con B (69 % > 60 %) |
| abanico en curva | 0.59 | — | 2,416 / 2,999 / 3,193 / 3,582 | 69 | **pavimento**: ningún máximo es factible (18 grupos) |
| abanico inverso | 0.59 | — | 2,667 / 3,185 / 3,358 / 3,704 | 0 | jardín (36 celdas bajo el umbral) |
| trapecio | 0.59 | — | 2,874 / 3,134 / 3,220 / 3,393 | 0 | ninguna |
| bandera (provisional) | 0.59 | — | 3,534 (iguales) | 0 | ninguna; FAR sobre el cuerpo (lectura de lote completo: 3,712 sq ft) |

Hallazgos:
1. **En RS-1-7 el FAR casi nunca obliga a construir dos pisos**; lo que decide es el área libre, la escalera y la
   convivencia del hogar.
2. **En los abanicos manda el pavimento del antejardín (131.0447), no el frente**: con la estrategia A el frente
   útil deja 8–12 ft de holgura; con B la huella llega a la línea de retiro y el antejardín angosto supera el 60 %.
   El retroceso por columna de 6.8 es la corrección natural.
3. **La ladera es el único lote donde el IO es normativo**, y ahí dos pisos dejan de ser una mejora y pasan a ser la
   condición para cumplir en los programas grandes.
4. La estrategia simple (A) basta en 1,025 de 1,032 mejores celdas; B2 solo se usa 7 veces (abanicos, máximos).

### 5.2 Cuándo ganan los dos pisos

Participación de dos pisos entre los mejores esquemas, según el IC del programa en un piso:

| IC del programa | 0.2–0.3 | 0.3–0.4 | 0.4–0.5 | ≥ 0.5 |
|---|---|---|---|---|
| Celdas | 360 | 481 | 106 | 82 |
| Gana un esquema de 2 pisos | 19 % | 59 % | 80 % | 100 % |

**El cruce está en IC ≈ 0.35** (≈ 1,750 sq ft en un lote de 5,000). Por perfil: mínimo 29 %, accesible 31 %,
óptimo 41 %, por etapas 69 %, máximo 84 %. Con el mismo programa óptimo, pasar de V0 a V1 libera ≈ 520 sq ft de
área libre (+14 % a +19 %) y baja el IO ≈ 0.10 en todos los lotes.

### 5.3 Qué esquema gana por hogar

Ver `figures/pilot_best_schemes.png`. Resumen (participación de 2 pisos entre los mejores esquemas):

| Arquetipo | 2 pisos | Esquema que suele ganar y por qué |
|---|---|---|
| Familia con adolescentes | 100 % | **V2** (padres abajo, adolescentes arriba): separación |
| Adultos que comparten | 100 % | **V1**: separación de lo común |
| Trabajo remoto | 52 % | **V2** (estudio arriba) en óptimo y máximo: área libre |
| Multigeneracional | 45 % | V0 en el óptimo; **V1 / V3** en el máximo (abuelos abajo por regla dura, familia arriba) |
| Pareja joven | 39 % | V0 en el óptimo; **V2** en el máximo |
| Crianza temprana | 16 % | V0; V1 en el máximo (todos los dormitorios en el mismo piso: supervisión) |
| **Nido vacío** | 0 % | **V0**, pero con opciones: en el máximo compiten V1 ≡ V2 (suite abajo por H16) y V4 (huéspedes arriba); en el óptimo no hay nada que subir |

Métrica decisiva entre el primero y el segundo: independencia de la escalera (330), separación (306), área libre
(180), único factible (87), eficiencia de la planta alta (85), supervisión (27), costo (12), frente (5).

### 5.4 Zonificación completa (E2)

7 de 20 celdas zonifican en un piso (esquina ×2, cul-de-sac, curva, interior, poco profundo, ladera). Novedad: el
**nido vacío zonifica en un piso en el cul-de-sac y en la curva**, que con el programa de 2,212 sq ft de los pasos
5–6 no lo hacían: con un programa a la medida del hogar el abanico deja de ser infactible. Las demás fallan en el
nivel de espacios (limitación conocida de la zonificación de un piso, sección 6.5a).

## 6. Figuras (examples/area_matrix/figures)

- `<lote>_decision_map.png`: hogares × (perfil, esquema); color = estado, número = rango del esquema, borde negro =
  mejor; `=V1` marca esquemas equivalentes.
- `<lote>_area_budget.png`: uso del suelo (planta baja, pavimento y deck, área libre = lote) y área construida por
  piso contra el IC máximo, para cuatro hogares de referencia (óptimo y máximo).
- `<lote>_ic_io.png`: cada celda como punto (IC, IO); la diagonal es un piso, las líneas rojas son los límites.
- `pilot_best_schemes.png`: mejor esquema por hogar y lote (óptimo y máximo) con la métrica decisiva.
- `<lote>_E2_<hogar>_<perfil>.png`: láminas de revisión de la zonificación completa.

Tablas: `area_matrix_cells.csv` (una fila por celda) y `area_matrix_best.csv` (mejor esquema por hogar y perfil).
`--tables` también escribe `area_matrix.json` con el detalle por estrategia (≈ 10 MB, no versionado).

## 7. Limitaciones

1. El puntaje de esquemas es un indicador provisional; los pesos (escalera 0.5, área libre de referencia 70 % del
   lote) deciden cruces cercanos. Se reemplaza por el puntaje común de 6.8 y se calibra con planos del piloto.
2. Dos pisos se evalúan a nivel de áreas: no hay planta alta dibujada, ni escalera ubicada, ni plano envolvente
   (131.0444) aplicado. Eso es 6.7.
3. El "jardín" que mide la capa de sitio es el área detrás de la huella; en abanicos no cuenta las cuñas laterales
   y no es monótono con la huella. Por eso el puntaje usa el área libre.
4. Lote bandera: lectura provisional (cuerpo como lote, acceso como pavimento, FAR sobre el cuerpo); la
   conformidad reporta la profundidad del cuerpo (80 ft < 95 ft).
5. El nivel de espacios sigue sin zonificar la mayoría de los mínimos y varios óptimos en un piso (sección 6.5a).
6. Las láminas E2 rotulan el ancho mayor del lote como "frente" en el abanico cul-de-sac (heredado de 6.5d).

## 8. Posibilidades de innovación

- Curva IO–IC del piloto como figura central del informe: dónde manda cada índice según forma y pendiente.
- Umbral de cruce un piso / dos pisos (IC ≈ 0.35) como regla explicable al cliente y como hipótesis a contrastar
  con planos aprobados de Clairemont (mayoritariamente de un piso).
- Transferencia a Colombia: IO e IC de un POT declarados en `Z15` sin código nuevo.
- Valor del segundo piso en sq ft de área libre por unidad de índice (≈ 520 sq ft por +0.024 de IC).
- Sensibilidad de la definición de área construida (garaje) como riesgo normativo cuantificado para RuleForge.
- Barrido paramétrico de lotes con planogen (ancho, fondo, ángulo de abanico, pendiente) para superficies de
  decisión en lugar de 10 puntos.
