# Expr.struct: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## Wrap plain columns in pl.struct before calling Expr.struct.json_encode

Applies to: `Expr.struct.json_encode`

`Expr.struct.json_encode` exists only in the `.struct` namespace and only works on a Struct column. There is no top-level `json_encode` on `Expr`, and calling `.struct.json_encode()` on a plain column raises an error. To serialise several columns per row (a pandas `to_json(orient='records')` habit), first combine them with `pl.struct`, then call `Expr.struct.json_encode`. Null field values are written as JSON `null` and the key is kept, so downstream consumers must not assume missing keys mean null.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2], "b": ["x", None]})

# Wrong: column 'a' is Int64, not a Struct
try:
    df.select(pl.col("a").struct.json_encode())
except Exception as e:
    print(type(e).__name__)

# Right: build a struct first, then encode it
out = df.select(pl.struct("a", "b").struct.json_encode().alias("json"))
print(out)
print(out["json"].to_list())
```

Output:

```text
shape: (2, 1)
┌──────────────────┐
│ json             │
│ ---              │
│ str              │
╞══════════════════╡
│ {"a":1,"b":"x"}  │
│ {"a":2,"b":null} │
└──────────────────┘
['{"a":1,"b":"x"}', '{"a":2,"b":null}']
```

## Inside struct.with_fields use pl.field for struct fields, not pl.col or bare strings

Applies to: `Expr.struct.with_fields`, `pl.field`, `pl.col`

Inside `Expr.struct.with_fields`, `pl.col(...)` refers to a **top-level DataFrame column**, not to a field of the struct; the docstring example itself uses `pl.col("multiply")` to pull in an outer column. Per the docstring, strings passed positionally are parsed as column names, not as struct fields. If the frame has a column with the same name as a struct field, `pl.col` silently computes on the outer column. Use `pl.field("name")` to reference the struct's own fields.

```python
import polars as pl

df = pl.DataFrame({"x": [100, 200], "s": [{"x": 1, "y": 10}, {"x": 3, "y": 20}]})

# Wrong: pl.col("x") is the outer column, not s.x
wrong = df.select(pl.col("s").struct.with_fields(x2=pl.col("x") * 2).struct.field("x2"))

# Right: pl.field("x") is the struct's own field
right = df.select(pl.col("s").struct.with_fields(x2=pl.field("x") * 2).struct.field("x2"))

print(wrong["x2"].to_list())  # [200, 400]
print(right["x2"].to_list())  # [2, 6]
```

Output:

```text
[200, 400]
[2, 6]
```

## struct.unnest inside with_columns silently overwrites same-named columns

Applies to: `Expr.struct.unnest`, `Expr.struct.field`, `DataFrame.with_columns`, `Expr.name.prefix_fields`

`Expr.struct.unnest` and `Expr.struct.field` name their output columns after the **field names**, not after the struct column. Inside `DataFrame.with_columns`, a field whose name matches an existing column replaces that column without any warning. The struct column itself is also kept. To avoid collisions, prefix the field names first with `Expr.name.prefix_fields`, or alias the result of `Expr.struct.field`.

```python
import polars as pl

df = pl.DataFrame({"a": ["keep", "keep"], "s": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]})

# Field 'a' silently replaces the top-level column 'a'
clobbered = df.with_columns(pl.col("s").struct.unnest())
print(clobbered.columns, clobbered["a"].to_list())

# Prefix the fields so nothing collides
safe = df.with_columns(pl.col("s").name.prefix_fields("s_").struct.unnest())
print(safe.columns, safe["a"].to_list())
```

Output:

```text
['a', 's', 'b'] [1, 3]
['a', 's', 's_a', 's_b'] ['keep', 'keep']
```

## rename_fields is positional, not a mapping

Applies to: `Expr.struct.rename_fields`, `Expr.name.map_fields`

`Expr.struct.rename_fields` takes a list of new names and applies them **in the order of the struct's existing fields**. It is not an `{old: new}` mapping. If you list the names in the wrong order, the labels land on the wrong data and no error is raised. To rename only some fields by name, use `Expr.name.map_fields` with a lookup function.

```python
import polars as pl

df = pl.DataFrame({"s": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]})

# Intent: rename name -> label. Names are applied by position, so this mislabels.
wrong = df.select(pl.col("s").struct.rename_fields(["label", "id"]))
print(wrong.unnest("s").to_dicts())  # 'label' now holds the ids

# Rename one field by name
mapping = {"name": "label"}
right = df.select(pl.col("s").name.map_fields(lambda n: mapping.get(n, n)))
print(right.unnest("s").to_dicts())
```

Output:

```text
[{'label': 1, 'id': 'a'}, {'label': 2, 'id': 'b'}]
[{'id': 1, 'label': 'a'}, {'id': 2, 'label': 'b'}]
```

## Same field from two structs collides in select; alias it

Applies to: `Expr.struct.field`, `DataFrame.select`

`Expr.struct.field("score")` produces a column named `score`, no matter which struct it came from. If you select the same field from two struct columns, the output names are duplicated and `DataFrame.select` raises an error. Give each result a unique name with `Expr.alias`.

```python
import polars as pl

df = pl.DataFrame({"home": [{"score": 1}], "away": [{"score": 2}]})

try:
    df.select(
        pl.col("home").struct.field("score"),
        pl.col("away").struct.field("score"),
    )
except Exception as e:
    print(str(type(e)).split(".")[-1][:-2])

ok = df.select(
    pl.col("home").struct.field("score").alias("home_score"),
    pl.col("away").struct.field("score").alias("away_score"),
)
print(ok.to_dicts())
```

Output:

```text
DuplicateError
[{'home_score': 1, 'away_score': 2}]
```

## No dotted paths in struct.field; chain calls for nested structs

Applies to: `Expr.struct.field`

`Expr.struct.field` looks up a field name at one level of nesting only. A dotted path like `"a.b"` (a JSON or SQL habit) is treated as a field literally named `a.b`. No such field exists, so the call fails. To reach a nested field, chain the calls: `.struct.field("a").struct.field("b")`.

```python
import polars as pl

df = pl.DataFrame({"s": [{"a": {"b": 1}}, {"a": {"b": 2}}]})

try:
    df.select(pl.col("s").struct.field("a.b"))
except Exception as e:
    print(str(type(e)).split(".")[-1][:-2])

out = df.select(pl.col("s").struct.field("a").struct.field("b"))
print(out.to_dicts())
```

Output:

```text
StructFieldNotFoundError
[{'b': 1}, {'b': 2}]
```
