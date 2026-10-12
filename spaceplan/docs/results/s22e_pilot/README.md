# S2.2e piloto: topes de área y detector exacto de puertas (12 oct 2026)

Mismo piloto que `s22d_pilot/k12_roof` (10 lotes, 291 celdas, perfil base). `before/` es S2.2d medido con los
indicadores nuevos; `after/` es S2.2e.

| Indicador | S2.2d | S2.2e |
|---|---|---|
| casas con planta completa | 26 | **32** |
| dormitorio principal, mediana / máx (sq ft dibujados) | 302.6 / 385.0 | **255.4 / 274.5** |
| suite completa, mediana / máx | 423.7 / 525.0 | **377.4 / 460.8** |
| dormitorio principal / garage, mediana / máx | 0.65 / 1.12 | **0.53 / 0.95** |
| % de espacios sobre su máximo efectivo | 13.5 | **6.3** |
| % sobre la proporción preferida / máxima | 41.6 / 24.6 | 42.7 / 23.2 |
| % sin mobiliario de referencia | 17.4 | 16.6 |
| % de espacios N sin luz suficiente | 23.5 | 15.4 |
| interferencias de puertas (R1 / E1 / R1b / R2 / R3) | 0 / 0 / 0 / 0 / 68 | 0 / 0 / 0 / 2 / 75 |
| plantas con interferencias / plantas medidas | 39 / 52 | 48 / 64 |
| casas donde cabe el paquete dormitorio + baño (propuesta) | — | 25 de 32 (222 de 291 celdas) |

Hallazgos:

- **Área sin construir.** Los topes dejan sin construir una mediana de 47 sq ft brutos por casa (máximo 121).
- **Suite principal.** Queda en 250 sq ft porque la mínima del catálogo es 250; con la mínima en 150–180 bajaría a
  224–238. Es un cambio de programa; se puede hacer con `set_criteria` (`program_min_sqft`).
- **Interferencias de puertas (R3).** La más frecuente es la puerta del walk-in que barre la zona de paso del baño
  principal (18 casos). Le siguen la puerta del baño sobre el clóset del baño y la puerta garage→foyer frente al
  vano de la sala. La colocación conjunta de puertas (P3) es la siguiente palanca.
- **Giro fuera del ambiente (R2).** Son 2 casos de 0.09 sq ft que la aproximación por celdas no veía.
