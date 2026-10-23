# polars-for-agents — diseño inicial

*2026-10-23. Estado: borrador para la épica v0.1.*

## 1. Qué problema resuelve

Un agente que escribe Polars inventa métodos, mezcla la API de pandas con la de Polars y arrastra
nombres que cambiaron entre versiones (por ejemplo, métodos renombrados o deprecados en la 1.x).
`dax-for-agents`, `powerquery-m-for-agents` y `spark-for-agents` resolvieron lo mismo para su
lenguaje: el catálogo sale del motor, no de la memoria. Aquí se repite la receta con Polars.

## 2. Fuente de verdad

| Qué | Cómo se exporta |
|---|---|
| `pl.Expr` y sus namespaces `.str`, `.dt`, `.list`, `.arr`, `.struct`, `.cat`, `.name` | introspección del paquete `polars` instalado: miembros públicos, `inspect.signature` y docstring |
| `pl.DataFrame`, `pl.LazyFrame`, `pl.Series` | la misma introspección |
| Funciones de primer nivel (`polars.*`) y selectores (`polars.selectors`) | la misma introspección |
| Deprecado e inestable | marcas que deja Polars en el objeto y en el docstring (`.. deprecated::`, `.. warning:: This functionality is considered **unstable**`) |

La versión de `polars` queda fijada dentro del JSON. La exportación corre en local o en CI con un
`pip install polars==X.Y.Z`; un cambio de versión es un PR que regenera el JSON entero.

## 3. Antes de escribir nada (NORTE R2)

Hecho en el comentario de docker-lab#38. Lo que ya existe sobre Polars:

| Qué | Licencia | Qué cubre | ¿Catálogo del motor? |
|---|---|---|---|
| `K-Dense-AI/claude-scientific-skills` → `skills/polars` | MIT | guía escrita a mano de uso y rendimiento | no |
| `r-brink/polars-mcp` y otros MCP pequeños | MIT | ejecutar operaciones | no |

**Decisión:** la guía de K-Dense-AI **se enlaza, no se duplica**. Ejecutar código queda fuera (ya lo
hacen los MCP). El hueco real es el catálogo exportado del paquete, por versión, con marcas de
deprecado e inestable: nadie lo publica.

## 4. Piezas de la v0.1

1. Script de exportación + JSON del catálogo para una versión fijada de `polars`.
2. Check en `Validate` que falla si una nota o un ejemplo nombra algo que no está en el JSON.
3. Notas de trampas y ejemplos por grupo de funciones (`skills/`), validadas contra el JSON.
4. Skill `polars-reference` que lee el catálogo y las notas, y skill `polars-feedback`.
5. `.claude-plugin/` (plugin.json + marketplace.json) y `PRIVACY.md`.
6. Nodo de la capa `etl` (ADR 0023): `node.json`.

## 5. Salida de pre-release

Cuando las piezas 1–5 estén en `main` y una prueba de invención (como la de
`powerquery-m-for-agents`) muestre la mejora, se quita el aviso de pre-release y se propone a
Cristóbal enviarlo al directorio de plugins.
