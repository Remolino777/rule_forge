# S2.2g piloto: marco estructural primero, posiciones por optimización y techos en varios planos (12 oct 2026)

Mismo piloto que `s22e_pilot` y `s22f_pilot`: 10 lotes, 291 celdas, perfil base del registro (526 parámetros).

## Decisiones del cliente aplicadas (18:45–18:51)

- Enfoque **C + E**: primero el soporte estructural (Habraken/SAR), con las posiciones por optimización (MILP en
  HiGHS). La verificación de S2.2f queda al final.
- Planta alta de 30–40 ft de lado corto: **pasillo central con 2 ejes**.
- Sobrante de la planta baja: **porche o huella más chica**, según la fachada.
- El eje del núcleo de la escalera es **un candidato más**.
- **Techos en varios planos**.

## Resultados

| Indicador | S2.2e | S2.2f | **S2.2g** |
|---|---|---|---|
| Casas con planta completa | 32 | 25 | **39** |
| Plantas con bandas en la misma dirección | 6 / 32 | 10 / 25 | **39 / 39** |
| Patrón del marco (una crujía / dos crujías / pasillo central) | — | — | 5 / 25 / 9 |
| Ejes compartidos con muro o viga debajo | — | — | **43 ejes, 100 %** |
| Largo de los ejes con muro debajo (el resto es viga sobre el eje) | — | — | mediana **67 %** |
| Postes bajo vigas de eje (máx. 1 por eje) | — | — | 20 |
| Luces de vigueta ≤ 20 ft | — | 25 / 25 | **39 / 39** (mediana 15.5 ft) |
| Muros de zona de arriba sobre muros de abajo (retícula) | — | mediana 39 % | **mediana 48 %** |
| Todos los muros de arriba sobre muros de abajo (retícula) | — | mediana 26 % | mediana 26 % |
| Muros interiores de arriba sobre muros de abajo (polígonos) | mediana 4 %, p90 9 % | mediana 9 %, p90 24 % | mediana 10 %, **p90 29 %**, máx. 43 % |
| Lado corto del espacio de llegada | mediana 7.5, máx. 16 ft | mediana 5.5, máx. 8 ft | mediana 6.5, máx. 8 ft |
| Un solo pasillo continuo arriba | 31 / 32 | 22 / 25 | 35 / 39 |
| Llegada → puerta de dormitorio más lejana | mediana 12.6 ft | mediana 9.7 ft | mediana 9.8 ft |
| Espacios sobre la proporción preferida / máxima | — | 40.5 % / 21.4 % | **37.0 % / 18.3 %** |
| Mobiliario que no cabe | 16.6 % | 14.9 % | 16.5 % |
| Espacios N sin luz suficiente | 15.4 % | 13.7 % | 14.0 % |
| Interferencias de puertas R3 (paso) | 75 | 47 | 95 |
| Sobrante al aire libre | — | — | porche 2 111 ft², huella menor 605 ft², techo de crujía arriba 1 305 ft² |
| Planos de techo por casa | 1 | 1 | **mediana 5** (2–9): alto, bajos, garage, porche |

Casas por lote (S2.2f → S2.2g):

| Lote | S2.2f | S2.2g |
|---|---|---|
| corner | 1 | 7 |
| fan_cul_de_sac | 1 | 2 |
| fan_curve | 1 | 1 |
| fan_reverse | 2 | 4 |
| flag | 3 | 4 |
| hillside | 5 | 5 |
| interior | 4 | 5 |
| narrow | 4 | 5 |
| shallow | 1 | 3 |
| trapezoid | 3 | 3 |

## Lectura

- **El orden era la causa.** Con el marco primero, las dos plantas comparten dirección y ejes en todas las casas.
  La cobertura sube de 25 a 39 casas: S2 encuentra más zonificaciones válidas (lote interior: 34 de 36 en S2,
  antes 26), porque las crujías ya traen el ancho correcto.
- **Ejes.** Cada eje tiene muro o viga debajo. En dos tercios de su largo es muro; el resto es viga sobre el eje
  (sala abierta), con un poste como máximo por eje.
- **Alineación de tabiques.** Los muros de zona se alinean más (48 %). Los tabiques entre cuartos siguen en 26 %
  (retícula) y 10 % (polígonos, mediana; p90 29 %). La meta de > 40 % de todos los muros **no se alcanzó**: los
  cuartos (S2.1) aún se cortan por área dentro de cada crujía. El MILP de S2 alinea muros de zona, pero arriba hay
  pocos (las zonas son 2–4 por planta).
- **Pasillo junto a la escalera.** El primer piloto dejó franjas de pasillo más angostas que el pasillo mínimo
  junto a la escalera y bajó la cobertura en los lotes 50×100. Ahora la franja de circulación que contiene la
  escalera deja al lado un pasillo de ancho mínimo, dentro del nodo compacto.
- **Techos.** Las partes de un piso se cortan por las líneas de la planta alta: una pieza por lado y las esquinas.
  Cada pieza es un techo de una caída (3:12) que baja desde el muro de la planta alta. El porche y el garage son
  piezas propias.
- **Costo.** Más interferencias R3 (95) y un poco más de mobiliario que no cabe, por 14 casas más y pasillos más
  largos.

## Archivos

- `quality.md`, `quality_summary.json` (bloques `frame` y `roofs`), `quality_by_type.csv`, `quality_doors.csv`,
  `quality_spaces.csv`.
- `interior_50x100_espacios.png` y `corner_55x100_espacios.png`: ejes estructurales en línea punto-raya, porche
  rayado, techo bajo y huella menor punteada.
- `techos_corner.png`: piezas de techo con su caída y su altura máxima.
