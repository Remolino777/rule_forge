# rule_forge — guía corta para trabajar en el repo

Capstone MS-AAI (University of San Diego), Municipal Permit Intelligence. 18 meses desde sept. 2026 (cierre feb. 2028).
El código vive en `spaceplan/` (paquete Python `spaceplan`). Detalle histórico completo: `spaceplan/HANDOFF_spaceplan.md`
(leer solo la sección que haga falta; el índice está en sus primeras líneas).

## Reglas del usuario (obligatorias)
1. Responder en **español**; **código, nombres y comentarios en inglés**.
2. Primero **análisis lógico y plan de acción en pasos**; **preguntar antes de empezar a programar** (salvo que el
   usuario ya haya aprobado un bloque, p. ej. "S1 y S2 aprobados").
3. Incluir siempre **posibilidades de innovación**.
4. Cada módulo: `main/` (workflow), `lib/` (dominio), `lib_aux/` (sin dominio). `lib_aux` no importa `lib`/`main`;
   `lib` no importa `main`; ningún `main` importa el `main` de otro módulo (compone `pipeline/`).
5. **Ningún número normativo en el código**: reglas en `spaceplan/spaceplan/data/rules/*.json` (con sección y
   `verified`), parámetros de diseño en catálogos (`data/catalog/`) con fuente y estado `provisional`/`verified`.
6. Costos solo como **índice relativo** (sin precios). El perfil cultural lo elige el cliente. F3 (RuleForge) no se recorta.
7. No cambiar resultados existentes sin decirlo: `python tools/golden_check.py check` debe pasar; si un cambio de
   resultados es intencional, explicarlo y regenerar con aprobación.

## Mapa (rutas relativas a `spaceplan/`)
- `spaceplan/core/lib/registry.py` — **registro único** de módulos, importaciones permitidas y contratos
  (productor, consumidores). Todas las listas se derivan de ahí.
- `spaceplan/modules/<m>/` — lotcap, site, household, cost, profiles, zoning, areas, stacking, viz.
- `spaceplan/contracts/schemas/<contrato>.schema.json` — contratos 0.2.0; `core/lib/contracts.py` (`make_contract`,
  `read_contract`). Cada módulo: `main/contract.py` con `to_contract` / `from_contract`.
- `spaceplan/pipeline/main/` — composición (`run_modules.py`) y CLI (`cli.py`).
- `docs/architecture/modules.md` — grafo y tablas **generados** (`python tools/module_graph.py write`).
- `tests/<m>/` con contratos fijos en `tests/<m>/fixtures/` (`python tools/make_fixtures.py write|check`).

## Flujo de desarrollo (rápido primero)
```bash
cd spaceplan && pip install -e ".[dev]"
python tools/dev_check.py quick <módulo>     # mientras se desarrolla: ~15 s (módulo + consumidores + guardas)
python tools/dev_check.py changed            # elige quick o full según lo tocado desde origin/spaceplan-modular
python tools/dev_check.py full               # al cerrar un paso: suite en paralelo + golden + fixtures + doc
python tools/new_module.py <m> --contract <c> --deps core,<...> --title "Step X.Y ..."   # módulo nuevo
```
- No correr la suite completa durante el desarrollo; CI (`.github/workflows/spaceplan.yml`) corre `full` en cada push.
- Para entender un módulo, leer su contrato (esquema) y su `main/run_<m>.py`, no el resto del repo.

## Ramas y commits
- `main` no se toca. Base: `spaceplan-modular`. Cada paso en su rama (`stacking/6.7a`, `dev/...`), creada desde la
  última rama del paso anterior. Push al terminar; el usuario decide los merges.

## Higiene de sesión (tokens y tiempo)
- Un chat por sub-paso (p. ej. S1, S2, 6.7b). Arrancar desde el documento de resultados del paso anterior en el
  proyecto de claude.ai (`claude/spaceplan_<paso>_*.md`) y esta guía, no desde el historial.
- Al cerrar un paso: documento corto de resultados en el proyecto + sección en el HANDOFF + push.

## Estado (9-oct-2026)
Pasos 1–6, 6.5a–d, 6.6, reestructuración modular y **6.7a etapa S0** hechos (rama `stacking/6.7a`).
Siguiente: 6.7a S1 (escalera, polígono por nivel con 131.0444, contención de la planta alta).
