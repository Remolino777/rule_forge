# S2.2f piloto: estructura de la planta alta, llegada de la escalera y puertas agrupadas (12 oct 2026)

Mismo piloto que `s22e_pilot` (10 lotes, 291 celdas, perfil base del registro 0.5.0).

## Decisiones del cliente aplicadas (12:31)

- Vigueta de **20 ft**.
- Ejes interiores como **regla obligatoria**.
- Voladizo de **3 ft**.
- Sala familiar arriba como **loft** (sin ser paso a los dormitorios).

## Resultados

| Indicador | S2.2e | S2.2f |
|---|---|---|
| Casas con planta completa | 32 | **25** |
| Plantas altas con luces de vigueta ≤ 20 ft entre líneas portantes | — (no medido) | **25 / 25** (mediana 15.5 ft, máx. 19 ft) |
| Muros de zona de arriba sobre muros de abajo (retícula, incluye la escalera) | — | mediana 39 %, máx. 92 % |
| Todos los muros de arriba sobre muros de abajo (retícula) | — | mediana 26 %, máx. 49 % |
| Muros interiores de arriba sobre muros de abajo (polígonos, sin la escalera) | mediana 4 %, p90 9 % | **mediana 9 %, p90 24 %**, máx. 35 % |
| Tramos sin muro debajo (vigas o tabiques sobre viguetas) / postes | — | 290 / 123 |
| Lado corto del espacio que recibe la escalera | mediana 7.5 ft, máx. **16 ft** (cajas de 13×13 a 16×16) | **mediana 5.5 ft, máx. 8 ft** |
| Área del espacio que recibe la escalera | mediana 114 ft², máx. 176 ft² | mediana 93 ft² |
| Plantas altas con un solo pasillo continuo | 31 / 32 | 22 / 25 |
| Llegada → puerta de dormitorio más lejana | mediana 12.6 ft | **mediana 9.7 ft** |
| Separación entre puertas de dormitorios (casas con ≥ 2) | mediana 9 ft (n 21) | mediana 12 ft (n 13) |
| Espacios N sin luz suficiente | 15.4 % | 13.7 % |
| Mobiliario que no cabe | 16.6 % | 14.9 % |
| Interferencias de puertas R3 (paso) | 75 | 47 |

## Lectura

- **Luces y vigas.** Toda planta alta tiene líneas portantes con luces de vigueta ≤ 20 ft, y cada viga entre apoyos
  de abajo mide ≤ 20 ft. Los muros exteriores de arriba que quedan sobre el interior de la planta baja llevan postes,
  que se cuentan.
- **Llegada compacta.** Desaparecieron las "cajas-vestíbulo": el nodo de llegada mide como máximo 8 ft de lado corto.
  El recorrido a los dormitorios bajó.
- **Alineación real de muros.** Los muros de arriba que caen sobre muros de abajo pasaron de 4 % a 9 % (mediana).
  Es una mejora, pero lejos de "compartir el eje". La exigencia de ≥ 50 % de cada muro portante sobre muros de abajo
  (`support_min_fraction` 0.5) dejó en el lote interior **1 casa de 36** (5 sin la regla). El valor por defecto
  quedó en 0.0: las líneas portantes son obligatorias sobre muros o vigas de abajo, y la alineación se premia y se
  imanta.
- **Causa.** S2 genera las zonas de cada planta con topologías distintas (bandas y columnas por área). La planta
  alta casi nunca comparte la retícula de la baja, y correr cortes ±2.5 ft no basta.
- **Propuesta (S2.2g).** Retícula estructural primero: elegir los ejes de la planta baja (crujías ≤ 20 ft) y zonificar
  la planta alta sobre esas mismas crujías (fusionar o subdividir bahías), en vez de buscarla libre y corregirla.

Archivos:
- `quality.md`, `quality_summary.json`, `quality_by_type.csv`, `quality_doors.csv`;
- `estructura_interior.png`, `estructura_hillside.png` (verde: muro de arriba sobre muro de abajo; rojo: sin muro
  debajo);
- láminas de espacios.
