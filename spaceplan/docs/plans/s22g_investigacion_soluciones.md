# S2.2g — Investigación: soluciones existentes para muros estructurales compartidos entre plantas

*12 oct 2026 · investigación en línea, sin código*

## Familias de soluciones

| # | Familia | Ejemplo | Cómo alinea las plantas | A favor | En contra | Encaje con spaceplan |
|---|---|---|---|---|---|---|
| A | **Estructura después del plano** | Patente "Techniques for automatically designing structural systems for residential buildings" (bloques por luz de vigueta, muros de borde portantes, el resto tabiques); auto-framing de CAD (Chief Architect, StruCalc) | No alinea: deduce muros portantes, vigas y viguetas del plano ya hecho | Siempre factible; no toca el generador | Muchas vigas y postes; no hay ejes compartidos | **Es lo que hace hoy S2.2f.** Queda como verificación. |
| B | **Optimización conjunta de las plantas** | Merrell, Schkufza y Koltun (SIGGRAPH Asia 2010): red bayesiana + Metropolis; costo por área sin apoyo; muros "snapped" a los de la planta vecina | Penaliza en el costo y atrae muros | Probada en casas de 2 y 3 pisos | Estocástica y costosa; falla ~1 de cada 20 casas de 2 pisos; alinea "por atracción", sin garantía | Nuestro snap es una versión débil de esto: por eso no basta. |
| C | **Soporte e infill / zonas y márgenes** | Habraken y SAR (1965–): un soporte fijo (estructura, núcleos) y una retícula de zonas y márgenes donde el relleno varía | Por construcción: el soporte es el mismo en todos los pisos | Variedad dentro de una estructura fija; claro para el cliente | Necesita un catálogo de soportes y que el programa quepa en las crujías | **Coincide con tus 3 conceptos** (ejes, núcleo de escalera, sobrante a techo). |
| D | **Gramáticas de formas** | Gramática de las casas de Siza en Malagueira (Duarte): parte de la parcela y la estructura y subdivide con reglas | Las reglas parten de la estructura | Coherencia arquitectónica, explicable | Escribir la gramática es costoso y poco general | Útil como idea de "catálogo de marcos". |
| E | **Programación matemática** | MIQP de Wu, Fan, Liu y Wonka (2018); MILP multiplanta (*mixed integer programming formulation for multi-floor layout*); CP + algoritmo genético (ESSEC) | Igualdad de coordenadas de muro entre plantas como restricción | Restricciones exactas y objetivo explícito; rápido si la topología está fija | Con topología libre explota la combinatoria | **Ideal para posicionar** cortes y ejes una vez elegida la topología (pocas variables). |
| F | **Aprendizaje** (GAN, difusión, datasets como MSD) | BuildingGAN, HouseDiffusion, MSD | Aprendido de ejemplos | Variedad realista | No garantiza reglas duras; necesita datos | Más adelante, para ranking o sugerencias. |

## Lectura técnica de la industria

- **WoodWorks:** alinear montantes y viguetas entre plantas es más difícil de construir, pero simplifica la ruta
  de cargas y las bajantes de plomería. Cuando no alinean, hacen falta vigas de borde o vigas cargadoras.
- **Guías de entramado de dos pisos:** alinear los muros portantes con vigas, postes y cuartos pesados arriba;
  mantener las líneas portantes rectas y continuas; planear la escalera temprano con cabezales y dobles viguetas.

## Recomendación: híbrido C + E (con A como verificación)

1. **Soporte primero (C).** Por cada casa, un marco con 0–2 ejes interiores y la vigueta de 20 ft como crujía
   máxima. Ejes candidatos: el muro largo del núcleo de la escalera, la junta de la planta alta y los muros del
   garage. Es el mismo eje en ambas plantas. Se generan 2–3 variantes de marco.
2. **Topología por bandas.** El motor actual de bandas y columnas, con las bandas obligadas a ser crujías del marco
   y la misma dirección en las dos plantas.
3. **Posiciones por optimización (E).** Para cada par de topologías (baja, alta), un MILP o LP pequeño fija las
   posiciones de ejes y cortes:
   - variables: coordenadas de ejes y cortes, y la holgura de techo por crujía;
   - restricciones: eje alto = eje bajo (igualdad), crujía ≤ 20 ft, anchos mínimos, el núcleo de la escalera
     dentro de su crujía, la franja K12;
   - objetivo: desvío de área mínimo; el área sobrante va al techo (arriba) o al porche (abajo).
   - Es un problema de decenas de variables que se resuelve en milisegundos con `scipy.optimize.milp` (HiGHS),
     ya instalado.
4. **Cuartos (S2.1):** por área dentro de cada crujía; los tabiques perpendiculares quedan libres. Se puede
   conservar el snap blando (B) solo para tabiques.
5. **Verificación (A):** la que ya existe en S2.2f, ahora con los ejes declarados; muro o viga sobre el eje = 100 %.

**Por qué no solo B o F:** no garantizan la regla. **Por qué no solo E:** sin topología fija la combinatoria es
inmanejable. **Por qué no solo D:** escribir y mantener una gramática completa es caro.

## Innovación

- **Catálogo de marcos** (crujía simple, doble, columna vertebral, núcleo central) como "gramática" ligera que un
  LLM elige y explica.
- **Aprendizaje:** priorizar marcos y topologías con datos de los pilotos.
- **Prefabricación:** crujías en módulos de 2 ft.

## Fuentes

- Merrell, Schkufza, Koltun (2010) — https://www.cs.princeton.edu/courses/archive/spring11/cos598A/pdfs/Merrell10a.pdf
- Computer-Aided Layout Generation for Building Design: A Review (2025) — https://arxiv.org/pdf/2504.09694
- Techniques for automatically designing structural systems for residential buildings (patente) — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12282713
- WoodWorks, alineación de montantes y viguetas — https://www.woodworks.org/resources/structural-design-considerations-for-bearing-wall-top-plates-that-support-concentrated-loads/
- Two-story framing — https://architecturecourses.org/build/two-story-framing
- Wu, Fan, Liu, Wonka (2018) MIQP layout — https://diglib.eg.org/items/4bcbcb26-b92e-4646-a486-e4f74f7208f8/full
- MILP multi-floor layout — https://www.researchgate.net/publication/299195156_A_mixed_integer_programming_formulation_for_multi-floor_layout
- CP + GA floor plans (ESSEC) — https://metalab.essec.edu/floor-plan-generation-through-a-mixed-constraint-programming-genetic-optimization-approach/
- Habraken / SAR — https://habraken.com/html/on_sar.htm
- Gramática de Siza (Malagueira) — https://dspace.mit.edu/handle/1721.1/8189
