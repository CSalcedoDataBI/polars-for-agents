# selectors: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## cs.string() silently skips Categorical columns

Applies to: `cs.string`, `cs.categorical`

`cs.string` matches only `String` columns by default. Categorical columns are not selected unless you pass `include_categorical=True`. Grouping by `cs.string()` on a frame with a categorical key therefore drops that key without any error, and the aggregates merge groups that should stay separate. Use `cs.string(include_categorical=True)`, or combine selectors with `cs.string() | cs.categorical()`.

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame(
    {"w": ["a", "a", "b"], "z": ["x", "y", "x"], "v": [1, 2, 4]}
).with_columns(pl.col("z").cast(pl.Categorical))

# WRONG: 'z' is not used as a key, so a/x and a/y collapse into one group
wrong = df.group_by(cs.string()).agg(cs.numeric().sum()).sort("w")
print(wrong.columns, wrong["v"].to_list())

# RIGHT: include categorical keys explicitly
right = (
    df.group_by(cs.string(include_categorical=True))
    .agg(cs.numeric().sum())
    .sort("v")
)
print(right.columns, right["v"].to_list())
```

Output:

```text
['w', 'v'] [3, 4]
['w', 'z', 'v'] [1, 2, 4]
```

## Use cs.matches for regex; contains/starts_with/ends_with are literal

Applies to: `cs.contains`, `cs.starts_with`, `cs.ends_with`, `cs.matches`

`cs.contains`, `cs.starts_with` and `cs.ends_with` match literal substrings, so `"."` means a real dot. `cs.matches` takes a regex and is not anchored: it selects any column whose name contains a match anywhere. A bare `cs.matches(".")` therefore selects every column. Add `^` and `$` (and escape metacharacters) when you want an exact pattern.

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame({"a.b": [1], "axb": [2], "total_a": [3]})

print(df.select(cs.contains(".")).columns)       # literal dot
print(df.select(cs.matches(".")).columns)        # regex: any char -> all
print(df.select(cs.matches("a")).columns)        # unanchored search
print(df.select(cs.matches("^a")).columns)       # anchored at start
print(df.select(cs.matches(r"^a\.b$")).columns)  # exact, escaped
```

Output:

```text
['a.b']
['a.b', 'axb', 'total_a']
['a.b', 'axb', 'total_a']
['a.b', 'axb']
['a.b']
```

## cs.alpha and cs.alphanumeric reject underscores and accept Unicode

Applies to: `cs.alpha`, `cs.alphanumeric`, `cs.digit`

`cs.alphanumeric` and `cs.alpha` require every character of the name to be a letter (or a digit, for alphanumeric). Snake_case names such as `user_id` are excluded. By default they also accept the full Unicode range, so `café` matches. Pass `ascii_only=True` to restrict to ASCII. For identifier-like names, use an explicit `cs.matches` pattern instead.

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame({"user_id": [1], "score": [2], "q1": [3], "café": [4]})

print(df.select(cs.alphanumeric()).columns)  # user_id excluded
print(df.select(cs.alphanumeric(ascii_only=True)).columns)
print(df.select(cs.alpha()).columns)
# Explicit ASCII identifier pattern, underscores allowed
print(df.select(cs.matches(r"^[A-Za-z0-9_]+$")).columns)
```

Output:

```text
['score', 'q1', 'café']
['score', 'q1']
['score', 'café']
['user_id', 'score', 'q1']
```

## cs.datetime(time_zone=None) means naive only, not any zone

Applies to: `cs.datetime`

The default `time_zone` of `cs.datetime` is `('*', None)`, which matches both tz-aware and naive columns. Passing `time_zone=None` does not mean "don't filter": it selects only columns without a timezone. `"*"` selects only tz-aware columns. `time_unit` is also a filter, so `cs.datetime("ms")` selects nothing when the columns use the default `us` unit.

```python
import polars as pl
import polars.selectors as cs
from datetime import datetime

df = pl.DataFrame({"naive": [datetime(2024, 1, 1)]}).with_columns(
    utc=pl.col("naive").dt.replace_time_zone("UTC")
)

print(df.select(cs.datetime()).columns)                 # both
print(df.select(cs.datetime(time_zone=None)).columns)   # naive only
print(df.select(cs.datetime(time_zone="*")).columns)    # tz-aware only
print(df.select(cs.datetime("ms")).columns)             # [] (columns are us)
```

Output:

```text
['naive', 'utc']
['naive']
['utc']
[]
```

## cs.first and cs.last pick columns, not rows

Applies to: `cs.first`, `cs.last`, `Expr.first`, `Expr.last`

`cs.first` and `cs.last` select the first or last column of the current scope. They do not return the first or last value of a column. For values, use `Expr.first` or `Expr.last` on an expression, for example `pl.all().first()`. Because the selection is positional, adding a column with `DataFrame.with_columns` changes what `cs.last()` refers to.

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame({"name": ["b", "a"], "v": [10, 20]})

print(df.select(cs.first()))         # whole 'name' column, 2 rows
print(df.select(pl.all().first()))   # first row of every column

print(df.select(cs.last()).columns)  # ['v']
df2 = df.with_columns(v2=pl.col("v") * 2)
print(df2.select(cs.last()).columns) # now ['v2']
```

Output:

```text
shape: (2, 1)
┌──────┐
│ name │
│ ---  │
│ str  │
╞══════╡
│ b    │
│ a    │
└──────┘
shape: (1, 2)
┌──────┬─────┐
│ name ┆ v   │
│ ---  ┆ --- │
│ str  ┆ i64 │
╞══════╪═════╡
│ b    ┆ 10  │
└──────┴─────┘
['v']
['v2']
```

## cs.by_name and cs.by_index raise on missing columns and reorder output

Applies to: `cs.by_name`, `cs.by_index`

`cs.by_name` and `cs.by_index` default to `require_all=True`. One missing name or out-of-bounds index raises an error instead of being skipped. Pass `require_all=False` to keep only the columns that exist. Both selectors return columns in the order you list them, not in schema order, so do not assume the output keeps the frame's column order.

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame({"a": [1], "b": [2], "c": [3]})

try:
    df.select(cs.by_name("c", "missing"))
except Exception as e:
    print(type(e))

print(df.select(cs.by_name("c", "missing", require_all=False)).columns)
# Order follows the selector, not the schema
print(df.select(cs.by_name("c", "a")).columns)
print(df.select(cs.by_index(-1, 0)).columns)
```

Output:

```text
<class 'polars.exceptions.ColumnNotFoundError'>
['c']
['c', 'a']
['c', 'a']
```

## cs.exclude silently ignores names that do not exist

Applies to: `cs.exclude`, `DataFrame.drop`

`cs.exclude` accepts names, dtypes and selectors. A name that matches no column is ignored without an error. A typo or a wrong-case name therefore leaves the column you meant to remove in the result. When the column must exist, use `DataFrame.drop`, which errors on unknown names by default.

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame({"id": [1, 2], "price": [9.5, 3.0], "qty": [2, 4]})

# WRONG: typo 'ID' is silently ignored, so 'id' is still there
print(df.select(cs.exclude("ID")).columns)

# RIGHT: DataFrame.drop fails loudly on the typo
try:
    df.drop("ID")
except Exception as e:
    print(type(e))
print(df.drop("id").columns)
```

Output:

```text
['id', 'price', 'qty']
<class 'polars.exceptions.ColumnNotFoundError'>
['price', 'qty']
```

## cs.expand_selector is strict and rejects plain expressions

Applies to: `cs.expand_selector`, `cs.is_selector`

`cs.expand_selector` defaults to `strict=True` and only expands genuine selectors. A plain column expression such as `pl.col(...)` is not a selector (`cs.is_selector` returns False), so in strict mode it fails. Pass `strict=False` to expand broader column expressions. Alternatively, build the selection from selectors only, for example with set difference (`cs.numeric() - cs.by_name("id")`).

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame({"id": [1], "x": [1.0], "s": ["a"]})

print(cs.is_selector(pl.col("id")), cs.is_selector(cs.numeric()))
print(cs.expand_selector(df, cs.numeric() - cs.by_name("id")))

try:
    cs.expand_selector(df, pl.col("id", "s"))
except Exception as e:
    print(type(e))

print(cs.expand_selector(df, pl.col("id", "s"), strict=False))
```

Output:

```text
False True
('x',)
<class 'TypeError'>
('id', 's')
```

## Python ints infer as Int64, so cs.unsigned_integer() can silently match nothing

Applies to: `cs.unsigned_integer`

`cs.unsigned_integer` selects by dtype, not by value. A column of non-negative Python ints is inferred as `pl.Int64`, so it is never selected. When nothing matches, `DataFrame.select` returns an empty frame instead of raising an error. If you want unsigned columns, declare them with `schema_overrides` (or cast them), and check what matched before you rely on it.

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
print(df.schema)
print(df.select(cs.unsigned_integer()).columns)

df2 = pl.DataFrame(
    {"a": [1, 2], "b": [3, 4]},
    schema_overrides={"a": pl.UInt32},
)
print(df2.select(cs.unsigned_integer()).columns)
```

Output:

```text
Schema({'a': Int64, 'b': Int64})
[]
['a']
```

## ~cs.unsigned_integer() means every other column, not the signed integers

Applies to: `cs.unsigned_integer`

`~cs.unsigned_integer()` takes the complement over all columns. The result includes strings, floats, dates and so on, not just signed integers. Code that then applies integer math to that selection can fail or touch the wrong columns. Use `cs.signed_integer()` for signed integers, or the set difference `cs.integer() - cs.unsigned_integer()`.

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame(
    {"foo": [-1, -2], "bar": [3, 4], "zap": ["ab", "cd"]},
    schema_overrides={"bar": pl.UInt32},
)
print(df.select(~cs.unsigned_integer()).columns)
print(df.select(cs.signed_integer()).columns)
print(df.select(cs.integer() - cs.unsigned_integer()).columns)
```

Output:

```text
['foo', 'zap']
['foo']
['foo']
```

## pl.col(pl.UInt32) matches one width; cs.unsigned_integer() matches all unsigned widths

Applies to: `cs.unsigned_integer`

Selecting by a single dtype, such as `pl.col(pl.UInt32)`, only picks columns of exactly that dtype. `UInt8`, `UInt16` and `UInt64` columns are silently left out. If you mean every unsigned integer column, use `cs.unsigned_integer()`, which covers all of these unsigned widths.

```python
import polars as pl
import polars.selectors as cs

df = pl.DataFrame(
    {"small": [1, 2], "bar": [3, 4], "baz": [5, 6]},
    schema_overrides={"small": pl.UInt8, "bar": pl.UInt32, "baz": pl.UInt64},
)
print(df.select(pl.col(pl.UInt32)).columns)
print(df.select(cs.unsigned_integer()).columns)
```

Output:

```text
['bar']
['small', 'bar', 'baz']
```
