# S2.2j piloto: dormitorios — baño por el walk-in, la cama no se cruza, hojas sobre muro, sin tiras, ducha lejos del clóset y cuarto de huéspedes (14 oct 2026)

Mismo piloto que S2.2i: 10 lotes, perfil base del registro (577 parámetros). Comparación contra el piloto oficial de
S2.2i (42 casas).

## Decisiones del cliente (13 oct 23:21–23:30, 14 oct 00:11)

1. **R1:** el baño propio de la suite y del dormitorio principal se alcanza por su walk-in (obligatorio). Si la
   secuencia no cabe, el walk-in pasa a clóset de pared.
2. **R3:** el paso dentro del cuarto nunca cruza la cama (obligatorio). Cama con 36 in a los lados y al pie: queen en
   los dormitorios, king en el principal (12.5 × 10 ft).
3. **R2:** walk-in, clóset y baño junto a la puerta de entrada del cuarto, también en los secundarios.
4. **R4:** el principal es el dormitorio mayor.
5. **Puertas:** la hoja abatible siempre abre contra un muro (sin puertas de bolsillo); baños y walk-ins pueden usar
   puerta de 2'-8" (unos 80 cm).
6. **Tiras:** ninguna parte de un cuarto o pasillo de menos de 3 ft; de un clóset, de menos de 2 ft; clóset mínimo
   2 × 3 ft.
7. **Baños:** el clóset del baño nunca del lado de la ducha.
8. **Huéspedes:** el cuarto de huéspedes solo si comparte baño con otro dormitorio; si no, estudio (sala familiar si
   llega a 220 ft²).

## Resultados

| Indicador | S2.2i | **S2.2j** |
|---|---|---|
| Casas con planta completa | 42 | **30** |
| Baño propio por el walk-in (cuartos con walk-in) | 30 de 45 (15 por el dormitorio) | **17 de 17** |
| El principal es el dormitorio mayor | 4 de 15 | **8 de 8** |
| Cama con holguras sin que el paso la cruce (arriba: suite / principal / secundarios) | 16/16 · 0/15 · 1/21 | **12/12 · 8/8 · 16/16** (abajo 24/24) |
| Parte del cuarto que es paso (mediana arriba: principal / secundarios) | 42 % · 43 % | **23 % · 30 %** |
| Puerta interna en el muro opuesto a la entrada (secundarios arriba) | 76 % | 63 % |
| Hojas de puerta al aire | 105 de 389 | **0 de 246** |
| Puertas de 2'-8" en baños y walk-ins | 0 | 5 |
| Conflictos R3 (hoja en el paso de otra puerta) | 45 | 87 |
| Baños con aparatos dibujados; clóset del lado de la ducha | — | **74; 0** |
| Tiras resueltas (clóset, porche/techo, muro, vecino) | — | 64 |
| Tiras que quedan (solo en pasillos y foyers, reportadas) | — | 199 ft² |
| Cuartos de huéspedes con baño compartido / pasados a estudio | — | 8 / 14 |
| Respaldos usados: walk-in → clóset / huésped → estudio / ambos | — | 9 / 4 / 4 |
| Casas con ≥ 2 dormitorios arriba y walk-in arriba | 21 de 21 | 4 de 16 |
| Mobiliario que no cabe | 20.6 % | **11.8 %** |
| Baños de arriba con muro exterior | 79.7 % | 98.0 % |
| Fracción de circulación | 18.2 % | 16.8 % |

Casas por lote:

| Lote | S2.2i | S2.2j |
|---|---|---|
| corner_55x100 | 7 | 7 |
| narrow_40x125 | 5 | 5 |
| trapezoid_asym_45_65x100 | 2 | 2 |
| fan_curve_35_80x100 | 1 | 1 |
| fan_reverse_80_40x100 | 5 | 4 |
| flag_70x80_pole20 | 4 | 3 |
| fan_cul_de_sac_35_80x100 | 2 | 1 |
| shallow_50x95 | 4 | 2 |
| hillside_50x100 | 6 | 3 |
| interior_50x100 | 6 | 2 |

## Lectura

- **Las reglas se cumplen en todas las casas dibujadas.** Ninguna hoja queda en el aire, ningún paso cruza la cama,
  ningún clóset de baño toca la ducha, el principal es siempre el mayor y su baño se alcanza por el walk-in.
- **Se pierden 12 casas (−29 %), sobre todo en los lotes de 50 ft** (interior, ladera, poco fondo). Medido por partes
  (corridas de ablación):
  - la cama con 36 in a ambos lados: la zona privada de la planta alta mide 15–16 ft de ancho y no cabe un dormitorio
    de 10–11 ft más una columna de baños con un walk-in de paso de 6 ft;
  - la hoja siempre sobre muro: ya en S2.2i costaba 5 casas (42 → 37);
  - las tiras: la primera versión eliminaba casi todo; se corrigió (un escalón de muro de menos de 2 ft no es tira;
    una tira en fachada sale como porche o techo; una astilla que nadie toma pasa a muro; una tira de pasillo o
    foyer se reporta, porque viene de la escalera de S1).
- **El walk-in arriba bajó de 21 a 4 casas:** en 13 casas la secuencia dormitorio → walk-in → baño no cupo y el
  walk-in pasó a clóset (respaldo aprobado).
- **Los conflictos R3 suben de 45 a 87:** sin correr la puerta fuera de su esquina, el choque solo se resuelve con la
  otra esquina, otro muro o la hoja de 2'-8".
- **R2** mejora la parte del cuarto que es paso (43 → 30 % en secundarios), pero en el principal la puerta del
  walk-in sigue en el muro opuesto a la entrada en la única distribución que queda.

## Pendiente para el cliente

- Si las 12 casas perdidas pesan más que la holgura de 36 in: 30 in a los lados (mínimo NKBA) podría devolver parte
  de ellas (no está medido); el registro ya permite cambiarlo.
- Las tiras de pasillo y foyer (199 ft²): se resuelven en la fase 2 (circulación dimensionada en S2).

## Archivos

- `quality.md`, `quality_summary.json` (bloque `rooms`), `quality_by_type.csv`, `quality_doors.csv`,
  `quality_spaces.csv`.
- `corner_55x100_espacios.png`, `narrow_40x125_espacios.png`, `interior_50x100_espacios.png` (aparatos del baño
  en azul: la ducha o tina más oscura).
