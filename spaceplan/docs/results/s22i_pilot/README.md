# S2.2i piloto: planta alta — dormitorio principal, puertas sin choques, baños laterales, puertas cerca de la escalera y vano de escalera (13 oct 2026)

Mismo piloto que S2.2h: 10 lotes, 291 celdas, perfil base del registro (546 parámetros).

## Decisiones del cliente (17:06)

1. **Dormitorio principal:** también cuando la suite está abajo. El dormitorio mayor (o el llamado "primary") lleva
   walk-in y un poco más de área.
2. **Puertas que chocan:** la puerta se corre, como en los ejemplos del vestíbulo.
3. **Baños:** preferentemente contra los muros laterales.
4. **Puertas de dormitorios:** sin máximo; lo más cerca posible del núcleo de la escalera.
5. **Escalera:** la planta alta abre solo lo que pide la altura libre. Los primeros peldaños quedan cubiertos.

## Resultados

| Indicador | S2.2h | **S2.2i** |
|---|---|---|
| Casas con planta completa | 39 | **42** |
| Casas con ≥ 2 dormitorios arriba y walk-in arriba | 6 de 23 | **21 de 21** |
| Dormitorios de arriba del mismo tamaño (±10 %) | 15 | **5** |
| Conflictos de puertas R3 (una hoja en el paso de otra puerta) | 94 (arriba 44, abajo 50) | **45 (arriba 27, abajo 18)** |
| Baños de arriba con muro exterior | 55.7 % | **79.7 %** |
| Distancia del descanso a la puerta de dormitorio | mediana 6.8 ft (máx. 17.5) | **mediana 3.5 ft** (mín. 3.0) |
| Huella de escalera cubierta arriba | 0 | **mediana 7.5 ft²** por casa; 39 clósets sobre el arranque |
| Fracción de circulación | 18.2 % | 18.2 % |
| Proporciones sobre la preferida / máxima | 37.8 % / 19.2 % | 37.4 % / 20.4 % |
| Mobiliario que no cabe | 16.9 % | 20.6 % |
| Espacios N sin luz suficiente | 13.2 % | 11.5 % |
| Separación entre puertas de dormitorios | mediana 5.9 ft | mediana 9.4 ft |

## Lectura

- **Principal.** En todas las casas con dos o más dormitorios arriba hay uno con walk-in. El área sale de los otros
  dormitorios (hasta su mínimo); el walk-in es programa nuevo que S2 acomoda en la planta. El piso no crece y S1 no
  cambia.
- **Puertas.** Los conflictos bajan a la mitad. Al colocar cada puerta se revisa el paso de las demás, y la puerta
  prueba la otra esquina y luego se corre por su muro (`door.conflicts.off_corner`, como en el vestíbulo; su hoja
  abierta ya no descansa contra un muro). Las corredizas de clóset se corren también. Quedan 27 conflictos arriba:
  baño junto al baño de su clóset, en espacios donde ninguna posición queda libre.
- **Baños y puertas.** Los baños con muro exterior pasan de 56 a 80 %. Las puertas de los dormitorios quedan en el
  borde del vestíbulo (3–3.5 ft de la llegada).
- **Escalera.** Con 120 in entre pisos, entrepiso de 12 in y altura libre de 80 in, se cubren los tres primeros
  peldaños (2.5 ft). Ese tramo se suma al cuarto vecino si queda rectangular; si no, se vuelve un clóset del espacio
  que toca (39 casas).

## Pendiente

- **El principal se dibuja a veces más chico que el otro dormitorio** (por ejemplo, 100 ft² + walk-in 57 ft² frente
  a 130 ft²). S2.1 reparte el área de la zona privada por forma. Falta una regla en S2.1: el principal es el
  dormitorio mayor.
- El mobiliario que no cabe sube de 16.9 a 20.6 %, en parte por los dormitorios que ceden área al principal.
- Los conflictos dentro del baño (puerta del baño contra su clóset).

## Archivos

- `quality.md`, `quality_summary.json` (bloque `upper_rooms`), `quality_doors.csv`, `quality_by_type.csv`,
  `quality_spaces.csv`.
- `corner_55x100_espacios.png`, `interior_50x100_espacios.png`.
