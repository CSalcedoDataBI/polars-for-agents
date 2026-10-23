# Expr.name: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## Renaming inside with_columns adds columns instead of renaming them

Applies to: `Expr.name.to_lowercase`, `Expr.name.to_uppercase`, `Expr.name.prefix`, `Expr.name.suffix`, `Expr.name.map`

A pandas user expects `df.rename(columns=str.lower)` behaviour. `Expr.name.to_lowercase`, `Expr.name.prefix` and the other `Expr.name.*` methods only set the output name of an expression. Inside `DataFrame.with_columns` the originals stay and the renamed copies are appended, which doubles the data. Use `DataFrame.select` to replace the columns, or `DataFrame.rename` (it accepts a callable) for a pure rename.

```python
import polars as pl

df = pl.DataFrame({"ColX": [1, 2], "ColY": ["x", "y"]})

# Trap: originals kept, copies appended
added = df.with_columns(pl.all().name.to_lowercase())
print(added.columns)

# Right: select replaces, rename renames
print(df.select(pl.all().name.to_lowercase()).columns)
print(df.rename(str.lower).columns)
```

Output:

```text
['ColX', 'ColY', 'colx', 'coly']
['colx', 'coly']
['colx', 'coly']
```

## name.keep discards your alias and overwrites the source column in with_columns

Applies to: `Expr.name.keep`, `Expr.alias`

`Expr.name.keep` restores the root column name, so an earlier `Expr.alias` is undone. Inside `DataFrame.with_columns` the result then silently replaces the original column instead of creating a new one. Only use `Expr.name.keep` when overwriting in place is what you want. Otherwise keep the `Expr.alias` as the last name operation.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})

# Trap: alias 'c' is discarded and 'a' is overwritten
out = df.with_columns((pl.col("a") * 9).alias("c").name.keep())
print(out.columns, out["a"].to_list())

# Right: alias last keeps 'a' intact and adds 'c'
good = df.with_columns((pl.col("a") * 9).alias("c"))
print(good.columns, good["a"].to_list())
```

Output:

```text
['a', 'b'] [9, 18]
['a', 'b', 'c'] [1, 2]
```

## name.replace treats the pattern as a regex by default

Applies to: `Expr.name.replace`

`Expr.name.replace` interprets `pattern` as a regular expression unless `literal=True` is passed. A pattern like `"."` therefore matches every character, and the docstring example shows that every match in the name is replaced. In `value`, `$` refers to a capture group, so a literal dollar sign must be written as `$$` (or use `literal=True`). Pass `literal=True` for plain substring renames.

```python
import polars as pl

df = pl.DataFrame({"price.usd": [1], "qty": [2]})

# Trap: '.' is a regex that matches every character
print(df.select(pl.all().name.replace(".", "_")).columns)

# Right: literal substring replacement
print(df.select(pl.all().name.replace(".", "_", literal=True)).columns)
```

Output:

```text
['_________', '___']
['price_usd', 'qty']
```

## Generated names can collide: silent overwrite in with_columns, DuplicateError in select

Applies to: `Expr.name.to_lowercase`, `Expr.name.to_uppercase`, `Expr.name.map`, `Expr.name.replace`

`Expr.name.*` methods do not check whether the new name already exists. In `DataFrame.with_columns`, a generated name that matches an existing column replaces that column without any warning. In `DataFrame.select`, two outputs that map to the same name raise an error. Check the resulting names for collisions before you apply a bulk rename. For example, columns `ColX` and `colx` collide under `Expr.name.to_lowercase`.

```python
import polars as pl

df = pl.DataFrame({"ColX": [1, 2], "colx": [10, 20]})

# Trap 1: existing 'colx' is silently overwritten with ColX's values
out = df.with_columns(pl.col("ColX").name.to_lowercase())
print(out.columns, out["colx"].to_list())

# Trap 2: two outputs named 'colx' in one select
try:
    df.select(pl.all().name.to_lowercase())
except Exception as e:
    print(type(e))
```

Output:

```text
['ColX', 'colx'] [1, 2]
<class 'polars.exceptions.DuplicateError'>
```

## prefix renames the struct column, prefix_fields renames its fields

Applies to: `Expr.name.prefix`, `Expr.name.suffix`, `Expr.name.prefix_fields`, `Expr.name.suffix_fields`, `Expr.name.map_fields`, `DataFrame.unnest`

`Expr.name.prefix` and `Expr.name.suffix` change only the column name. They leave the struct's inner field names alone, so unnesting two structs that share field names still collides. To rename the fields, use `Expr.name.prefix_fields`, `Expr.name.suffix_fields` or `Expr.name.map_fields`, which only take effect for struct columns. Apply them before `DataFrame.unnest` to get distinct column names.

```python
import polars as pl

df = pl.DataFrame({"s1": [{"a": 1}], "s2": [{"a": 2}]})

# prefix touches the column name only; fields are still 'a'
print(df.select(pl.col("s1").name.prefix("p_")).schema)

try:
    df.unnest("s1", "s2")
except Exception as e:
    print(type(e))

fixed = df.select(
    pl.col("s1").name.prefix_fields("s1_"),
    pl.col("s2").name.map_fields(lambda f: "s2_" + f),
).unnest("s1", "s2")
print(fixed.columns)
```

Output:

```text
Schema({'p_s1': Struct({'a': Int64})})
<class 'polars.exceptions.DuplicateError'>
['s1_a', 's2_a']
```
