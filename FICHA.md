# Ficha — polars-for-agents

> Ficha de esta herramienta. La lee su experto (`.claude/agents/experto.md`) en cada PR.
> Se mantiene con las reglas internas del mantenedor: su norte es `FICHA.md` y el agente `experto` fusiona contra ella.
> Cambiarla exige una nueva aprobación de Cristóbal.

## Qué es

- **Qué construye y para quién:** la referencia de Polars para agentes de IA. Cada expresión,
  método, namespace y selector sale de la introspección del paquete `polars` instalado, fijado por
  versión, con su firma, su docstring y si está deprecado o es inestable, más las trampas que no
  cuenta la documentación. Es para quien escribe transformaciones con Polars ayudado por un agente.
- **Papel** (`repo-roles`): tool (plugin de skills)
- **Gemelo público/privado:** ninguno por ahora. Hermanos de familia: `dax-for-agents`,
  `powerquery-m-for-agents`, `spark-for-agents` y `pandas-for-agents`.

## Norte

- **Plan vigente:** [épica v0.1 — catálogo de Polars exportado del motor](https://github.com/CSalcedoDataBI/polars-for-agents/issues/2)
- **Lo que esta herramienta NO es:**
  - No ejecuta pipelines: es una referencia que un agente consulta.
  - No es pandas: eso es `pandas-for-agents`.
  - No es un tutorial de Polars: la guía escrita a mano ya existe
    (`K-Dense-AI/claude-scientific-skills`, skill `polars`, MIT) y se enlaza, no se duplica.

## Zonas protegidas

Lo que no se toca sin un paso del plan que lo nombre:

- El JSON del catálogo: solo lo escribe el script de exportación. Una entrada a mano rompe la
  promesa de «ningún nombre inventado».
- `LICENSE` (MIT) y la visibilidad pública del repo.

## Capa y feedback

- **Capa de nodo** (ADR 0023): `etl`
- **Skill de feedback:** `polars-for-agents:polars-feedback` (planeada en la v0.1)

## Check y experto

- **Check de CI requerido:** `Validate` (ruleset `main protegida` de `main`)
- **Suite de pruebas:** `python scripts/check_repo.py`
- **Runner:** GitHub (repo público)
- **Formato de tag:** `vX.Y.Z`, con release-please.
- **Experto:** `.claude/agents/experto.md`
- **¿Plugin del directorio?:** todavía no. Se envía cuando salga de pre-release; desde entonces,
  `stable` no se toca y publicar sigue R5.
- **Partes visibles que aprueba Cristóbal:** el README de cara al público y la salida de
  pre-release.

## Aprobación

Aprobada:
