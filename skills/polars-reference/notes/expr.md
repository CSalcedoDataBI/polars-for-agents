# Expr: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## diff(null_behavior="drop") shortens the column and breaks with_columns

Applies to: `Expr.diff`

By default `Expr.diff` keeps the input length and puts `null` in the first `n` rows, like pandas. With `null_behavior="drop"` those rows are removed, so the result has `n` fewer rows. That shorter expression cannot be added next to the original columns with `DataFrame.with_columns`, which raises an error. Keep the default `"ignore"` when adding a column. Use `"drop"` only in a `DataFrame.select` where every output has the same shortened length.

```python
import polars as pl

df = pl.DataFrame({"x": [20, 10, 30, 25, 35]})

try:
    df.with_columns(d=pl.col("x").diff(null_behavior="drop"))
except Exception as e:
    print(type(e).__name__)

# Right: keep the length (first row is null) when adding a column
print(df.with_columns(d=pl.col("x").diff()))

# "drop" is fine when the output stands alone
print(df.select(pl.col("x").diff(null_behavior="drop")))
```

Output:

```text
ShapeError
shape: (5, 2)
┌─────┬──────┐
│ x   ┆ d    │
│ --- ┆ ---  │
│ i64 ┆ i64  │
╞═════╪══════╡
│ 20  ┆ null │
│ 10  ┆ -10  │
│ 30  ┆ 20   │
│ 25  ┆ -5   │
│ 35  ┆ 10   │
└─────┴──────┘
shape: (4, 1)
┌─────┐
│ x   │
│ --- │
│ i64 │
╞═════╡
│ -10 │
│ 20  │
│ -5  │
│ 10  │
└─────┘
```

## bitwise_and/or/xor are aggregations, not element-wise operators

Applies to: `Expr.bitwise_and`, `Expr.bitwise_or`, `Expr.bitwise_xor`, `Expr.and_`, `Expr.or_`, `Expr.xor`

`Expr.bitwise_and`, `Expr.bitwise_or` and `Expr.bitwise_xor` take no argument. Each one reduces a whole column (or each group) to a single value. Code like `pl.col("a").bitwise_and(pl.col("b"))` fails. Using it as a row-wise combine of two columns is wrong. For element-wise bit operations between two integer columns, use `Expr.and_`, `Expr.or_` and `Expr.xor`, or the operators `&`, `|` and `^`.

```python
import polars as pl

df = pl.DataFrame({"a": [12, 10], "b": [10, 6]})

try:
    df.select(pl.col("a").bitwise_and(pl.col("b")))
except Exception as e:
    print(type(e).__name__)

# bitwise_and reduces the column to ONE value: 12 & 10 = 8
print(df.select(pl.col("a").bitwise_and()))

# Element-wise: row by row a & b -> [8, 2]
print(df.select(pl.col("a").and_(pl.col("b")).alias("elementwise")))
```

Output:

```text
TypeError
shape: (1, 1)
┌─────┐
│ a   │
│ --- │
│ i64 │
╞═════╡
│ 8   │
└─────┘
shape: (2, 1)
┌─────────────┐
│ elementwise │
│ ---         │
│ i64         │
╞═════════════╡
│ 8           │
│ 2           │
└─────────────┘
```

## Out-of-domain trig results are NaN/inf, not null

Applies to: `Expr.arccos`, `Expr.arcsin`, `Expr.arctanh`, `Expr.arccosh`, `Expr.is_nan`, `Expr.fill_nan`

The inverse trig functions always return Float64 and never raise for bad inputs. `Expr.arctanh` of 1.0 gives `inf`, and `Expr.arccos` of 2.0 gives NaN. Polars treats NaN as a float value, not as missing, so `Expr.is_null` and `Expr.fill_null` will not catch these results. Detect them with `Expr.is_nan` or `Expr.is_finite`. Convert them with `Expr.fill_nan(None)` if you want them to behave as nulls.

```python
import polars as pl

df = pl.DataFrame({"a": [0.5, 2.0, 1.0]})
res = df.with_columns(
    pl.col("a").arccos().alias("acos"),
    pl.col("a").arctanh().alias("atanh"),
)
print(res)
print(res.select(
    pl.col("acos").is_null().alias("acos_is_null"),
    pl.col("acos").is_nan().alias("acos_is_nan"),
    pl.col("atanh").is_finite().alias("atanh_finite"),
))
# Turn NaN into a real null so null handling applies
print(res.select(pl.col("acos").fill_nan(None).is_null()))
```

Output:

```text
shape: (3, 3)
┌─────┬──────────┬──────────┐
│ a   ┆ acos     ┆ atanh    │
│ --- ┆ ---      ┆ ---      │
│ f64 ┆ f64      ┆ f64      │
╞═════╪══════════╪══════════╡
│ 0.5 ┆ 1.047198 ┆ 0.549306 │
│ 2.0 ┆ NaN      ┆ NaN      │
│ 1.0 ┆ 0.0      ┆ inf      │
└─────┴──────────┴──────────┘
shape: (3, 3)
┌──────────────┬─────────────┬──────────────┐
│ acos_is_null ┆ acos_is_nan ┆ atanh_finite │
│ ---          ┆ ---         ┆ ---          │
│ bool         ┆ bool        ┆ bool         │
╞══════════════╪═════════════╪══════════════╡
│ false        ┆ false       ┆ true         │
│ false        ┆ true        ┆ false        │
│ false        ┆ false       ┆ false        │
└──────────────┴─────────────┴──────────────┘
shape: (3, 1)
┌───────┐
│ acos  │
│ ---   │
│ bool  │
╞═══════╡
│ false │
│ true  │
│ false │
└───────┘
```

## cum_sum leaves null rows null and widens small ints to Int64

Applies to: `Expr.cum_sum`, `Expr.cum_prod`, `Expr.cum_max`, `Expr.cum_min`

`Expr.cum_sum` and the other cumulative functions skip nulls, but the output is still `null` at those positions. It does not carry the running total forward, as a SQL running SUM would. If every row needs the total so far, chain `.fill_null(strategy="forward")`. `Expr.cum_sum` and `Expr.cum_prod` also cast Int8, UInt8, Int16 and UInt16 input to Int64. The output schema therefore differs from the input schema.

```python
import polars as pl

df = pl.DataFrame({"v": [None, 10, None, 8]}, schema={"v": pl.Int8})
out = df.with_columns(
    pl.col("v").cum_sum().alias("cs"),
    pl.col("v").cum_sum().fill_null(strategy="forward").alias("cs_filled"),
)
print(out)
print(out.schema)
```

Output:

```text
shape: (4, 3)
┌──────┬──────┬───────────┐
│ v    ┆ cs   ┆ cs_filled │
│ ---  ┆ ---  ┆ ---       │
│ i8   ┆ i64  ┆ i64       │
╞══════╪══════╪═══════════╡
│ null ┆ null ┆ null      │
│ 10   ┆ 10   ┆ 10        │
│ null ┆ null ┆ 10        │
│ 8    ┆ 18   ┆ 18        │
└──────┴──────┴───────────┘
Schema({'v': Int8, 'cs': Int64, 'cs_filled': Int64})
```

## `Expr.cast` raises by default; `strict=False` silently turns bad values into nulls

Applies to: `Expr.cast`

`Expr.cast` defaults to `strict=True`, so one unparsable string or one out-of-range integer makes the whole query raise. Passing `strict=False` turns every invalid value into null without any warning, so bad data can disappear quietly. Check `Expr.null_count` after a non-strict cast. Integer overflow counts as invalid by default; pass `wrap_numerical=True` only if you really want overflowing values to wrap around.

```python
import polars as pl

df = pl.DataFrame({"s": ["1", "2", "x"], "n": [10, 200, 300]})
try:
    df.select(pl.col("s").cast(pl.Int64))
except Exception as e:
    print(type(e))
loose = df.select(pl.col("s").cast(pl.Int64, strict=False))
print(loose.to_dict(as_series=False))
print(loose.select(pl.col("s").null_count()).item())
try:
    df.select(pl.col("n").cast(pl.UInt8))
except Exception as e:
    print(type(e))
wrapped = df.select(pl.col("n").cast(pl.UInt8, wrap_numerical=True))
print(wrapped.to_dict(as_series=False))
```

Output:

```text
<class 'polars.exceptions.InvalidOperationError'>
{'s': [1, 2, None]}
1
<class 'polars.exceptions.InvalidOperationError'>
{'n': [10, 200, 44]}
```

## `Expr.all` and `Expr.any` ignore nulls unless `ignore_nulls=False`

Applies to: `Expr.all`, `Expr.any`

By default (`ignore_nulls=True`), nulls are skipped. A Boolean column like `[null, true]` reports `Expr.all` as `true`, and `[null, false]` reports `Expr.any` as `false`. A column with no non-null values gives `true` for `Expr.all` and `false` for `Expr.any`. If a null should mean "unknown", pass `ignore_nulls=False` to get Kleene logic, which returns null in those cases. Do not confuse `Expr.all` with `pl.all`, which selects every column.

```python
import polars as pl

df = pl.DataFrame({"c": [None, True], "d": [None, False]})
out = df.select(
    all_default=pl.col("c").all(),
    all_kleene=pl.col("c").all(ignore_nulls=False),
    any_default=pl.col("d").any(),
    any_kleene=pl.col("d").any(ignore_nulls=False),
)
print(out.to_dicts())
```

Output:

```text
[{'all_default': True, 'all_kleene': None, 'any_default': False, 'any_kleene': None}]
```

## Combine conditions with `&` or `Expr.and_`, never Python `and`, and remember integers go bitwise

Applies to: `Expr.and_`

Python's `and` keyword asks for the truth value of an expression, and that raises a `TypeError`. Combine predicates with `&` or with `Expr.and_`, and wrap each comparison in parentheses. On integer columns, `&` and `Expr.and_` do a bitwise AND rather than a logical one; for example, `5` AND `-9` is `5`. Make sure both operands are Boolean comparisons when you mean a logical test.

```python
import polars as pl

df = pl.DataFrame({"x": [5, 6, 7], "z": [-9, 2, 7]})
try:
    df.filter(pl.col("x") > 5 and pl.col("z") > 0)
except Exception as e:
    print(type(e))
print(df.filter((pl.col("x") > 5) & (pl.col("z") > 0)).rows())
print(df.filter((pl.col("x") > 5).and_(pl.col("z") > 0)).rows())
print(df.select(bitwise=pl.col("x").and_(pl.col("z"))).to_dict(as_series=False))
```

Output:

```text
<class 'TypeError'>
[(6, 2), (7, 7)]
[(6, 2), (7, 7)]
{'bitwise': [5, 2, 7]}
```

## `Expr.arg_sort` puts nulls first by default

Applies to: `Expr.arg_sort`

`Expr.arg_sort` defaults to `nulls_last=False`, so the positions of null values come before everything else, even when `descending=True`. Code that assumes the first position points at the smallest (or largest) value will pick a null row instead. Pass `nulls_last=True` when you use `Expr.arg_sort` with `Expr.gather` to reorder or select rows.

```python
import polars as pl

df = pl.DataFrame({"v": [3, None, 1], "name": ["a", "b", "c"]})
print(df.select(pl.col("v").arg_sort()).to_dict(as_series=False))
print(df.select(pl.col("v").arg_sort(nulls_last=True)).to_dict(as_series=False))
first = df.select(pl.col("name").gather(pl.col("v").arg_sort(descending=True)))
print(first.to_dict(as_series=False))
fixed = df.select(
    pl.col("name").gather(pl.col("v").arg_sort(descending=True, nulls_last=True))
)
print(fixed.to_dict(as_series=False))
```

Output:

```text
{'v': [1, 2, 0]}
{'v': [2, 0, 1]}
{'name': ['b', 'a', 'c']}
{'name': ['a', 'c', 'b']}
```

## `Expr.arg_max` and `Expr.arg_min` return a 0-based position, not an index label

Applies to: `Expr.arg_max`, `Expr.arg_min`

Polars has no index, so `Expr.arg_max` and `Expr.arg_min` return an integer row position, not a label. Inside `DataFrame.group_by` aggregations, the position is counted within each group, not across the whole frame. To fetch the matching value from another column, pass the position to `Expr.gather`.

```python
import polars as pl

df = pl.DataFrame({"city": ["A", "B", "C"], "temp": [20, 30, 10]})
pos = df.select(pl.col("temp").arg_max(), argmin=pl.col("temp").arg_min())
print(pos.to_dict(as_series=False))
names = df.select(
    hottest=pl.col("city").gather(pl.col("temp").arg_max()),
    coldest=pl.col("city").gather(pl.col("temp").arg_min()),
)
print(names.to_dict(as_series=False))
g = pl.DataFrame({"k": ["x", "x", "y", "y"], "v": [1, 5, 7, 2]})
per_group = g.group_by("k", maintain_order=True).agg(pl.col("v").arg_max())
print(per_group.to_dict(as_series=False))
```

Output:

```text
{'temp': [1], 'argmin': [2]}
{'hottest': ['B'], 'coldest': ['C']}
{'k': ['x', 'y'], 'v': [1, 0]}
```

## `Expr.bottom_k` output is unordered and never prefers nulls

Applies to: `Expr.bottom_k`, `Expr.bottom_k_by`

`Expr.bottom_k` and `Expr.bottom_k_by` (like `Expr.top_k`) do not guarantee any order in their output, so chain `Expr.sort` if you need the result ordered. They always prefer non-null elements over nulls. `Expr.sort` followed by `Expr.head` behaves differently: it puts nulls first by default, so the two approaches can return different values.

```python
import polars as pl

df = pl.DataFrame({"value": [1, 98, None, 2, 3, 99, 4]})
print(df.select(pl.col("value").bottom_k(3).sort()).to_dict(as_series=False))
print(df.select(pl.col("value").sort().head(3)).to_dict(as_series=False))
top = df.select(pl.col("value").top_k(3).sort(descending=True))
print(top.to_dict(as_series=False))
df2 = pl.DataFrame({"a": [3, 1, 2], "b": ["x", "y", "z"]})
print(df2.select(pl.col("b").bottom_k_by("a", 2).sort()).to_dict(as_series=False))
```

Output:

```text
{'value': [1, 2, 3]}
{'value': [None, 1, 2]}
{'value': [99, 98, 4]}
{'b': ['y', 'z']}
```

## `Expr.arg_true` changes the row count and cannot be added as a column

Applies to: `Expr.arg_true`

`Expr.arg_true` returns only the positions where the condition is true, so its length usually differs from the frame's height. Putting it in `DataFrame.with_columns`, or next to other full-length expressions, raises an error. Use it on its own in `DataFrame.select`. To keep row positions alongside the data, use `DataFrame.with_row_index` followed by `DataFrame.filter`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 1, 2, 1]})
try:
    df.with_columns(idx=(pl.col("a") == 1).arg_true())
except Exception as e:
    print(type(e))
out = df.select((pl.col("a") == 1).arg_true().alias("idx"))
print(out.to_dict(as_series=False))
kept = df.with_row_index().filter(pl.col("a") == 1)
print(kept.to_dict(as_series=False))
```

Output:

```text
<class 'polars.exceptions.ShapeError'>
{'idx': [0, 1, 3]}
{'index': [0, 1, 3], 'a': [1, 1, 1]}
```

## `Expr.agg_groups` is deprecated: aggregate a row index instead

Applies to: `Expr.agg_groups`

`Expr.agg_groups` is deprecated since 1.35, will be removed in Polars 2.0, and should only be used in an aggregation context. The documented replacement is `df.with_row_index().group_by(...).agg(pl.col("index"))`, which produces the same per-group lists of row positions. Call `DataFrame.with_row_index` before any filtering if you want the original row numbers. The docstring's recommended form passes `maintain_order=True` to `DataFrame.group_by`; do the same if the order of the groups matters.

```python
import polars as pl

df = pl.DataFrame(
    {"group": ["one", "two", "one", "two"], "value": [94, 97, 95, 99]}
)
out = (
    df.with_row_index()
    .group_by("group", maintain_order=True)
    .agg(pl.col("index"))
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'group': ['one', 'two'], 'index': [[0, 2], [1, 3]]}
```

## Float floordiv does not match Python's // operator

Applies to: `Expr.floordiv`

`Expr.floordiv` (and `//` on expressions) first does the float division and then floors the result. Python's `//` floors the exact quotient instead. So `6.0 // 0.1` is `59.0` in Python but `60.0` in Polars. Do not port Python or NumPy floor-division results and expect identical values on floats. If you need the exact-quotient semantics, compute it outside Polars or use integer-scaled data.

```python
import polars as pl

print('python:', 6.0 // 0.1)
df = pl.DataFrame({"x": [6.0, 6.03]})
out = df.with_columns(
    pl.col("x").floordiv(0.1).alias("floordiv"),
    (pl.col("x") // 0.1).alias("op"),
)
print(out)
```

Output:

```text
python: 59.0
shape: (2, 3)
┌──────┬──────────┬──────┐
│ x    ┆ floordiv ┆ op   │
│ ---  ┆ ---      ┆ ---  │
│ f64  ┆ f64      ┆ f64  │
╞══════╪══════════╪══════╡
│ 6.0  ┆ 60.0     ┆ 60.0 │
│ 6.03 ┆ 60.0     ┆ 60.0 │
└──────┴──────────┴──────┘
```

## forward_fill fills nulls only, not NaN

Applies to: `Expr.forward_fill`

`Expr.forward_fill` is an alias of `.fill_null(strategy="forward")`, so it only fills nulls. A NaN is a real value, not a missing one. Unlike pandas `ffill`, NaN is never filled, and it gets propagated into the nulls that follow it. Convert NaN to null first with `Expr.fill_nan(None)` if both should count as missing.

```python
import polars as pl

df = pl.DataFrame({"v": [1.0, None, float("nan"), None]})
out = df.select(
    pl.col("v").forward_fill().alias("ffill"),
    pl.col("v").fill_nan(None).forward_fill().alias("fixed"),
)
print(out)
```

Output:

```text
shape: (4, 2)
┌───────┬───────┐
│ ffill ┆ fixed │
│ ---   ┆ ---   │
│ f64   ┆ f64   │
╞═══════╪═══════╡
│ 1.0   ┆ 1.0   │
│ 1.0   ┆ 1.0   │
│ NaN   ┆ 1.0   │
│ NaN   ┆ 1.0   │
└───────┴───────┘
```

## Expr.get raises on out-of-bounds indices unless null_on_oob=True

Applies to: `Expr.get`

By default `Expr.get` raises an error when the index is out of bounds (`null_on_oob=False`). In a `DataFrame.group_by` aggregation, a single short group makes the whole query fail. Pass `null_on_oob=True` to get null for groups that are too short.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "a", "b"], "v": [1, 2, 3]})
try:
    df.group_by("g", maintain_order=True).agg(pl.col("v").get(1))
except Exception as e:
    print(type(e).__name__)
out = df.group_by("g", maintain_order=True).agg(
    pl.col("v").get(1, null_on_oob=True)
)
print(out)
```

Output:

```text
shape: (2, 2)
┌─────┬──────┐
│ g   ┆ v    │
│ --- ┆ ---  │
│ str ┆ i64  │
╞═════╪══════╡
│ a   ┆ 2    │
│ b   ┆ null │
└─────┴──────┘
```

## Expr.item errors unless there is exactly one value

Applies to: `Expr.item`

`Expr.item` is not "first value". It raises a `ComputeError` if the expression yields more than one value, and also if it yields zero values. Aggregate first (for example with `Expr.max` or `Expr.first`) or filter down to one row. Pass `allow_empty=True` if an empty input should give null instead of an error.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 3]})
try:
    df.select(pl.col("a").item())
except Exception as e:
    print(type(e).__name__)
print(df.select(pl.col("a").max().item()))
empty = df.filter(pl.col("a") > 5)
print(empty.select(pl.col("a").item(allow_empty=True)))
```

Output:

```text
ComputeError
shape: (1, 1)
┌─────┐
│ a   │
│ --- │
│ i64 │
╞═════╡
│ 3   │
└─────┘
shape: (1, 1)
┌──────┐
│ a    │
│ ---  │
│ i64  │
╞══════╡
│ null │
└──────┘
```

## Expr.index_of returns null when the value is missing, and can match null

Applies to: `Expr.index_of`

`Expr.index_of` does not raise like Python's `list.index`, and it does not return `-1`. When the value is not found it returns null, so check the result with `Expr.is_null`. It also matches null itself: `index_of(None)` returns the position of the first null.

```python
import polars as pl

df = pl.DataFrame({"a": [1, None, 17]})
out = df.select(
    pl.col("a").index_of(17).alias("seventeen"),
    pl.col("a").index_of(None).alias("null"),
    pl.col("a").index_of(55).alias("missing"),
    pl.col("a").index_of(55).is_null().alias("not_found"),
)
print(out)
```

Output:

```text
shape: (1, 4)
┌───────────┬──────┬─────────┬───────────┐
│ seventeen ┆ null ┆ missing ┆ not_found │
│ ---       ┆ ---  ┆ ---     ┆ ---       │
│ u32       ┆ u32  ┆ u32     ┆ bool      │
╞═══════════╪══════╪═════════╪═══════════╡
│ 2         ┆ 1    ┆ null    ┆ true      │
└───────────┴──────┴─────────┴───────────┘
```

## is_close has abs_tol=0.0 by default, so values near zero are never close

Applies to: `Expr.is_close`

`Expr.is_close` mirrors `math.isclose`, not `numpy.isclose`. The defaults are `rel_tol=1e-09` and `abs_tol=0.0`. Comparing against `0.0` is therefore false for any nonzero value, however tiny. Set `abs_tol` explicitly when values can be near zero.

```python
import polars as pl

df = pl.DataFrame({"x": [1e-12, 0.5]})
out = df.with_columns(
    pl.col("x").is_close(0.0).alias("default"),
    pl.col("x").is_close(0.0, abs_tol=1e-9).alias("with_abs_tol"),
)
print(out)
```

Output:

```text
shape: (2, 3)
┌────────────┬─────────┬──────────────┐
│ x          ┆ default ┆ with_abs_tol │
│ ---        ┆ ---     ┆ ---          │
│ f64        ┆ bool    ┆ bool         │
╞════════════╪═════════╪══════════════╡
│ 1.0000e-12 ┆ false   ┆ true         │
│ 0.5        ┆ false   ┆ false        │
└────────────┴─────────┴──────────────┘
```

## Expr.exclude treats a pattern as a regex only when anchored with ^ and $

Applies to: `Expr.exclude`

`Expr.exclude` accepts regular expressions only if they start with `^` and end with `$`. A pattern like `"a.*"` is taken as a literal column name, so it silently excludes nothing. `Expr.exclude` also only works after a wildcard or regex selection, and you cannot mix names and dtypes in one call. Anchor your regex, or use selectors.

```python
import polars as pl

df = pl.DataFrame({"ab": [1], "ac": [2], "b": [3]})
print(df.select(pl.all().exclude("a.*")).columns)
print(df.select(pl.all().exclude("^a.*$")).columns)
```

Output:

```text
['ab', 'ac', 'b']
['b']
```

## Expr.hist silently drops values outside the given bins

Applies to: `Expr.hist`

`Expr.hist` is unstable. With explicit `bins` edges, values outside the edges are not counted at all, so the counts can sum to less than the row count. In the catalogue example, the first bin is closed on both sides (`[1.0, 2.0]`) and later bins are left-open (`(2.0, 3.0]`). Check that the counts sum to the height. Alternatively, use `bin_count` to get edges that encompass all the data.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 3, 8, 8, 2, 1, 3]})
out = df.select(pl.col("a").hist(bins=[1, 2, 3]))
print(out)
print(out.get_column("a").sum(), df.height)
```

Output:

```text
shape: (2, 1)
┌─────┐
│ a   │
│ --- │
│ u32 │
╞═════╡
│ 3   │
│ 2   │
└─────┘
5 7
```

## NaN and null are different values, and each method only handles one of them

Applies to: `Expr.drop_nans`, `Expr.drop_nulls`, `Expr.fill_nan`

In pandas, NaN *is* the missing value, so `dropna`/`fillna` remove both. In Polars, a missing value is `null`, while `NaN` is an ordinary float value. `Expr.drop_nulls` keeps `NaN`, `Expr.drop_nans` keeps `null`, and `Expr.fill_nan` leaves `null` untouched. To clean both, first convert one into the other (for example `Expr.fill_nan(None)`), then use the null tools such as `Expr.drop_nulls` or `Expr.fill_null`.

```python
import polars as pl

df = pl.DataFrame({"a": [1.0, None, 3.0, float("nan")]})

# Wrong: each call removes or fills only one kind of missing value
print(df.select(pl.col("a").drop_nulls()).to_series().to_list())  # NaN survives
print(df.select(pl.col("a").drop_nans()).to_series().to_list())  # null survives
print(df.select(pl.col("a").fill_nan(0.0)).to_series().to_list())  # null survives

# Right: turn NaN into null, then handle nulls once
print(df.select(pl.col("a").fill_nan(None).drop_nulls()).to_series().to_list())
print(df.select(pl.col("a").fill_nan(None).fill_null(0.0)).to_series().to_list())
```

Output:

```text
[1.0, 3.0, nan]
[1.0, None, 3.0]
[1.0, None, 3.0, 0.0]
[1.0, 3.0]
[1.0, 0.0, 3.0, 0.0]
```

## Use eq_missing for null-safe equality; plain eq propagates null and treats NaN == NaN as true

Applies to: `Expr.eq`, `Expr.eq_missing`

`Expr.eq` (and `==`) returns `null` whenever either side is null, the same as SQL. A filter on that result therefore silently drops rows where both sides are null. Polars also returns `true` for `NaN == NaN`, which differs from IEEE and NumPy. If two nulls should count as equal (for example when comparing old and new versions of a column), use `Expr.eq_missing`, which always returns `true`/`false`.

```python
import polars as pl

df = pl.DataFrame({
    "x": [1.0, float("nan"), None, None],
    "y": [1.0, float("nan"), 5.0, None],
})
out = df.select(
    eq=pl.col("x").eq(pl.col("y")),
    eq_missing=pl.col("x").eq_missing(pl.col("y")),
)
print(out.to_dict(as_series=False))

# Filtering with eq drops the null/null row; eq_missing keeps it
print(df.filter(pl.col("x").eq(pl.col("y"))).height)  # 2
print(df.filter(pl.col("x").eq_missing(pl.col("y"))).height)  # 3
```

Output:

```text
{'eq': [True, True, None, None], 'eq_missing': [True, True, False, True]}
2
3
```

## count and cum_count skip nulls, so they are not row counts or row numbers

Applies to: `Expr.count`, `Expr.cum_count`

`Expr.count` returns the number of non-null values, unlike SQL `COUNT(*)`; use `Expr.len` or `pl.len` for the row count. `Expr.cum_count` is a cumulative count of the non-null values, so it does not advance at null rows. It is not pandas `groupby().cumcount()` (a 0-based row number). For a per-group row number, use `pl.int_range(pl.len()).over(...)`.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "a", "a", "b"], "v": [1, None, 3, 4]})

print(df.select(
    count=pl.col("v").count(),  # 3: nulls skipped
    length=pl.col("v").len(),  # 4: all rows
    rows=pl.len(),
).to_dict(as_series=False))

out = df.select(
    cum_count=pl.col("v").cum_count().over("g"),  # 1, 1, 2, 1
    row_nr=pl.int_range(pl.len()).over("g"),  # 0, 1, 2, 0
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'count': [3], 'length': [4], 'rows': [4]}
{'cum_count': [1, 1, 2, 1], 'row_nr': [0, 1, 2, 0]}
```

## cut takes interior break points and needs len(breaks) + 1 labels, not pandas-style bin edges

Applies to: `Expr.cut`

`Expr.cut` treats `breaks` as cut points; the outer bins run to -inf and +inf automatically. Passing pandas-style edges with one label per bin therefore gives the wrong number of labels and raises an error. Intervals are right-closed by default (`(a, b]`); pass `left_closed=True` for `[a, b)`. The result is `Categorical` (or `Struct` with `include_breaks=True`), not a string or integer. The API is marked unstable.

```python
import polars as pl

df = pl.DataFrame({"x": [-2, -1, 0, 1, 2]})

# Wrong: two breaks define three bins, so two labels is an error
try:
    df.select(pl.col("x").cut([-1, 1], labels=["low", "high"]))
except Exception:
    print("raises an error")

# Right: len(breaks) + 1 labels; boundary values move with left_closed
out = df.with_columns(
    right=pl.col("x").cut([-1, 1], labels=["a", "b", "c"]),
    left=pl.col("x").cut([-1, 1], labels=["a", "b", "c"], left_closed=True),
)
print(out.rows())
print(out.schema["right"])
```

Output:

```text
raises an error
[(-2, 'a', 'a'), (-1, 'a', 'b'), (0, 'b', 'b'), (1, 'b', 'c'), (2, 'c', 'c')]
Categorical
```

## String bounds in clip are column names, not literal values

Applies to: `Expr.clip`

`Expr.clip` parses string arguments as column names. Writing `clip(lower_bound="2024-01-01")` on a date column therefore treats the string as a column name and raises an error. Pass a typed Python value instead, such as `date(2024, 1, 1)` or a number. `Expr.clip` only works on numeric and temporal columns, and null values stay null.

```python
import polars as pl
from datetime import date

df = pl.DataFrame({
    "d": [date(2023, 12, 1), date(2024, 6, 1), None],
    "v": [-5, 50, None],
})

# Wrong: the string is treated as a column name
try:
    df.select(pl.col("d").clip(lower_bound="2024-01-01"))
except Exception:
    print("raises an error")

# Right: pass typed literals; nulls stay null
out = df.select(
    pl.col("d").clip(lower_bound=date(2024, 1, 1)),
    pl.col("v").clip(0, 10),
)
print(out.to_dict(as_series=False))
```

Output:

```text
raises an error
{'d': [datetime.date(2024, 1, 1), datetime.date(2024, 6, 1), None], 'v': [0, 10, None]}
```

## EWM functions use min_samples (not min_periods), and the default adjust=True is not the recursive formula

Applies to: `Expr.ewm_mean`, `Expr.ewm_std`, `Expr.ewm_var`, `Expr.cumulative_eval`

Since 1.21.0 the `min_periods` parameter of `Expr.ewm_mean`, `Expr.ewm_std`, `Expr.ewm_var` and `Expr.cumulative_eval` is named `min_samples`, so code copied from older Polars or pandas should be updated. Also, the default `adjust=True` computes a weighted average with weights `(1 - alpha)^i`. If you expect the textbook recursion `y_t = (1 - alpha) * y_{t-1} + alpha * x_t`, pass `adjust=False`, or your numbers will differ.

```python
import polars as pl

df = pl.DataFrame({"v": [1.0, 2.0, 3.0, 4.0]})

out = df.select(
    adjusted=pl.col("v").ewm_mean(alpha=0.5),  # default adjust=True
    recursive=pl.col("v").ewm_mean(alpha=0.5, adjust=False),
    recursive_min2=pl.col("v").ewm_mean(alpha=0.5, adjust=False, min_samples=2),
)
for name, values in out.to_dict(as_series=False).items():
    print(name, values)
```

Output:

```text
adjusted [1.0, 1.6666666666666665, 2.4285714285714284, 3.2666666666666666]
recursive [1.0, 1.5, 2.25, 3.125]
recursive_min2 [None, 1.5, 2.25, 3.125]
```

## explode turns empty lists into null rows by default

Applies to: `Expr.explode`

With the defaults `empty_as_null=True` and `keep_nulls=True`, `Expr.explode` emits a `null` row for every empty list and every null list. The output length is therefore not the sum of the list lengths, and nulls appear that were never inside a list. Pass `empty_as_null=False` to drop empty lists and `keep_nulls=False` to drop null lists.

```python
import polars as pl

df = pl.DataFrame({"v": [[1, 2], [], None]})

# Default: empty list and null list both become null rows
print(df.select(pl.col("v").explode()).to_series().to_list())  # [1, 2, None, None]

# Drop empty lists, then also drop null lists
print(df.select(pl.col("v").explode(empty_as_null=False)).to_series().to_list())
print(df.select(pl.col("v").explode(empty_as_null=False, keep_nulls=False)).to_series().to_list())
```

Output:

```text
[1, 2, None, None]
[1, 2, None]
[1, 2]
```

## Expr.mode can return several rows and its order is not guaranteed

Applies to: `Expr.mode`

Unlike a scalar aggregation, `Expr.mode` returns *every* value tied for most frequent, so the result can have more than one row. Inside `DataFrame.group_by` it produces a list, not a scalar. With the default `maintain_order=False`, the order of the tied values is not defined, so `mode().first()` can pick a different value from run to run. Sort the result first, or pass `maintain_order=True`, before reducing it to one value.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "a", "a", "a"], "x": [1, 1, 2, 2]})

# Two values tie, so mode returns two rows
modes = df.select(pl.col("x").mode().sort())
print(modes)
print(modes.height)

# Deterministic single value per group: sort before taking first
print(df.group_by("g").agg(pl.col("x").mode().sort().first()))
```

Output:

```text
shape: (2, 1)
┌─────┐
│ x   │
│ --- │
│ i64 │
╞═════╡
│ 1   │
│ 2   │
└─────┘
2
shape: (1, 2)
┌─────┬─────┐
│ g   ┆ x   │
│ --- ┆ --- │
│ str ┆ i64 │
╞═════╪═════╡
│ a   ┆ 1   │
└─────┴─────┘
```

## Expr.shift ignores groups unless you add .over

Applies to: `Expr.shift`, `Expr.over`

pandas users expect a lag to restart in each group. `Expr.shift` works on the whole column, so values leak from the previous group into the first row of the next one. Wrap it as `pl.col(...).shift().over("group")` to get a per-group LAG.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "a", "b", "b"], "v": [1, 2, 10, 20]})
out = df.with_columns(
    wrong=pl.col("v").shift(),
    right=pl.col("v").shift().over("g"),
)
# 'wrong' row 3 holds 2 from group a; 'right' is null there
print(out)
```

Output:

```text
shape: (4, 4)
┌─────┬─────┬───────┬───────┐
│ g   ┆ v   ┆ wrong ┆ right │
│ --- ┆ --- ┆ ---   ┆ ---   │
│ str ┆ i64 ┆ i64   ┆ i64   │
╞═════╪═════╪═══════╪═══════╡
│ a   ┆ 1   ┆ null  ┆ null  │
│ a   ┆ 2   ┆ 1     ┆ 1     │
│ b   ┆ 10  ┆ 2     ┆ null  │
│ b   ┆ 20  ┆ 10    ┆ 10    │
└─────┴─────┴───────┴───────┘
```

## Order-dependent window expressions follow frame order unless order_by is given

Applies to: `Expr.over`, `Expr.cum_sum`

In `Expr.over`, order-dependent expressions such as `Expr.cum_sum` run in the current row order of the frame, not in time order. SQL users expect an ORDER BY inside the window. On unsorted data the running totals are silently wrong. Pass `order_by=` to `Expr.over`; the results still map back to the original row positions.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "a", "a"], "t": [3, 1, 2], "v": [30, 10, 20]})
out = df.with_columns(
    frame_order=pl.col("v").cum_sum().over("g"),
    by_time=pl.col("v").cum_sum().over("g", order_by="t"),
)
# by_time: t=1 -> 10, t=2 -> 30, t=3 -> 60
print(out)
```

Output:

```text
shape: (3, 5)
┌─────┬─────┬─────┬─────────────┬─────────┐
│ g   ┆ t   ┆ v   ┆ frame_order ┆ by_time │
│ --- ┆ --- ┆ --- ┆ ---         ┆ ---     │
│ str ┆ i64 ┆ i64 ┆ i64         ┆ i64     │
╞═════╪═════╪═════╪═════════════╪═════════╡
│ a   ┆ 3   ┆ 30  ┆ 30          ┆ 60      │
│ a   ┆ 1   ┆ 10  ┆ 40          ┆ 10      │
│ a   ┆ 2   ┆ 20  ┆ 60          ┆ 30      │
└─────┴─────┴─────┴─────────────┴─────────┘
```

## Expr.set_sorted on unsorted data can give wrong answers

Applies to: `Expr.set_sorted`

`Expr.set_sorted` does not sort anything and does not check the data. It only sets a flag that lets later operations such as `Expr.max` take sorted fast paths. If the data is not actually sorted, those operations can silently return incorrect results. Use `Expr.sort` when you need sorted data, and use `Expr.set_sorted` only when you know the order is already correct.

```python
import polars as pl

df = pl.DataFrame({"v": [3, 1, 2]})
out = df.select(
    flagged=pl.col("v").set_sorted().max(),
    honest=pl.col("v").max(),
    sorted_then_flag=pl.col("v").sort().set_sorted().max(),
)
# 'flagged' may not equal the true max of 3
print(out)
```

Output:

```text
shape: (1, 3)
┌─────────┬────────┬──────────────────┐
│ flagged ┆ honest ┆ sorted_then_flag │
│ ---     ┆ ---    ┆ ---              │
│ i64     ┆ i64    ┆ i64              │
╞═════════╪════════╪══════════════════╡
│ 2       ┆ 3      ┆ 3                │
└─────────┴────────┴──────────────────┘
```

## Expr.shuffle shuffles one column independently and breaks rows

Applies to: `Expr.shuffle`, `DataFrame.sample`

`Expr.shuffle` reorders only the expression it is applied to. Using it inside `DataFrame.with_columns` scrambles the pairing between that column and the others, which silently corrupts records. To shuffle whole rows, use `DataFrame.sample(fraction=1.0, shuffle=True, seed=...)`.

```python
import polars as pl

df = pl.DataFrame({"id": [1, 2, 3], "name": ["x", "y", "z"]})

# Wrong: ids no longer match their names
print(df.with_columns(pl.col("id").shuffle(seed=1)))

# Right: rows stay intact, only their order changes
print(df.sample(fraction=1.0, shuffle=True, seed=1))
```

Output:

```text
shape: (3, 2)
┌─────┬──────┐
│ id  ┆ name │
│ --- ┆ ---  │
│ i64 ┆ str  │
╞═════╪══════╡
│ 2   ┆ x    │
│ 3   ┆ y    │
│ 1   ┆ z    │
└─────┴──────┘
shape: (3, 2)
┌─────┬──────┐
│ id  ┆ name │
│ --- ┆ ---  │
│ i64 ┆ str  │
╞═════╪══════╡
│ 2   ┆ y    │
│ 3   ┆ z    │
│ 1   ┆ x    │
└─────┴──────┘
```

## Null and NaN are different missing values

Applies to: `Expr.fill_null`, `Expr.is_null`, `Expr.is_not_null`, `Expr.is_nan`, `Expr.is_not_nan`, `Expr.interpolate`

pandas treats `NaN` as missing data. Polars does not: `null` is missing, while `NaN` is an ordinary float value. `Expr.is_null` returns false for `NaN`, and `Expr.fill_null` leaves `NaN` untouched. `Expr.interpolate` also leaves `NaN` in place, as its docstring example shows. To clean float columns, first convert `NaN` to null with `Expr.fill_nan(None)` and then call `Expr.fill_null`, or test for `NaN` with `Expr.is_nan`.

```python
import polars as pl

df = pl.DataFrame({"b": [1.0, float("nan"), None]})
out = df.select(
    pl.col("b").is_null().alias("is_null"),
    pl.col("b").is_nan().alias("is_nan"),
    pl.col("b").fill_null(0.0).alias("fill_null_only"),
    pl.col("b").fill_nan(None).fill_null(0.0).alias("nan_and_null_filled"),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'is_null': [False, False, True], 'is_nan': [False, True, None], 'fill_null_only': [1.0, nan, 0.0], 'nan_and_null_filled': [1.0, 0.0, 0.0]}
```

## NaN compares equal to NaN in Polars comparisons

Applies to: `Expr.ge`, `Expr.gt`

Under IEEE/NumPy/pandas rules, every comparison with `NaN` is false. Polars treats NaNs as equal, so `Expr.ge` evaluates `NaN >= NaN` to true. `Expr.gt` gives false for that pair. A filter such as `x >= y` can therefore silently keep NaN rows. If NaN rows must not pass, exclude them explicitly with `Expr.is_not_nan`.

```python
import polars as pl

df = pl.DataFrame({"x": [float("nan"), 1.0], "y": [float("nan"), 2.0]})
out = df.with_columns(
    pl.col("x").ge(pl.col("y")).alias("x_ge_y"),
    pl.col("x").gt(pl.col("y")).alias("x_gt_y"),
    (pl.col("x").ge(pl.col("y")) & pl.col("x").is_not_nan()).alias("x_ge_y_no_nan"),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'x': [nan, 1.0], 'y': [nan, 2.0], 'x_ge_y': [True, False], 'x_gt_y': [False, False], 'x_ge_y_no_nan': [False, False]}
```

## is_between parses string bounds as column names and is inclusive on both ends

Applies to: `Expr.is_between`

`Expr.is_between` treats string bounds as **column names**, not literals. So `pl.col("s").is_between("b", "d")` looks for columns `b` and `d` and fails. Wrap string bounds in `pl.lit` instead. The default `closed="both"` includes both endpoints, so pass `closed="left"`, `"right"` or `"none"` when you need half-open ranges such as date buckets.

```python
import polars as pl

df = pl.DataFrame({"num": [1, 2, 4, 5], "s": ["a", "b", "d", "e"]})
out = df.select(
    pl.col("num").is_between(2, 4).alias("both"),
    pl.col("num").is_between(2, 4, closed="left").alias("left"),
)
print(out.to_dict(as_series=False))
try:
    df.select(pl.col("s").is_between("b", "d"))
except Exception as e:
    print(type(e))
ok = df.select(pl.col("s").is_between(pl.lit("b"), pl.lit("d")))
print(ok.to_dict(as_series=False))
```

Output:

```text
{'both': [False, True, True, False], 'left': [False, True, False, False]}
<class 'polars.exceptions.ColumnNotFoundError'>
{'s': [False, True, True, False]}
```

## Expr.flatten is deprecated since 1.38

Applies to: `Expr.flatten`

`Expr.flatten` is deprecated in 1.38 and will be removed in 2.0, so do not write new code with it. The deprecation message names `Expr.list.explode(keep_nulls=False, empty_as_null=False)` as the replacement and describes it as the behaviour you likely expect. Use that form, including in `group_by().agg`, where `flatten` was commonly used to merge lists per group.

```python
import polars as pl

df = pl.DataFrame({"group": ["a", "b", "b"], "values": [[1, 2], [2, 3], [4]]})
out = df.group_by("group", maintain_order=True).agg(
    pl.col("values").list.explode(keep_nulls=False, empty_as_null=False)
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'group': ['a', 'b'], 'values': [[1, 2], [2, 3, 4]]}
```

## is_in propagates nulls unless nulls_equal=True

Applies to: `Expr.is_in`

With the default `nulls_equal=False`, a null input to `Expr.is_in` does not produce False, and putting `None` in the lookup list does not make it match. The null propagates instead, so a filter on that mask silently drops the null rows. Pass `nulls_equal=True` to treat null as a matchable value.

```python
import polars as pl

df = pl.DataFrame({"a": [1, None, 3]})
out = df.with_columns(
    pl.col("a").is_in([1, None]).alias("default"),
    pl.col("a").is_in([1, None], nulls_equal=True).alias("nulls_equal"),
)
print(out.to_dict(as_series=False))
print(df.filter(pl.col("a").is_in([1, None])).height)
print(df.filter(pl.col("a").is_in([1, None], nulls_equal=True)).height)
```

Output:

```text
{'a': [1, None, 3], 'default': [True, None, False], 'nulls_equal': [True, True, False]}
1
2
```

## first() returns null if the first value is null

Applies to: `Expr.first`

pandas `groupby().first()` skips missing values. Polars `Expr.first` defaults to `ignore_nulls=False` and returns the literal first element, even when that element is null. To get the first non-null value per group, pass `ignore_nulls=True`.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "a", "b"], "v": [None, 1, 2]})
out = df.group_by("g", maintain_order=True).agg(
    pl.col("v").first().alias("first"),
    pl.col("v").first(ignore_nulls=True).alias("first_non_null"),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'g': ['a', 'b'], 'first': [None, 2], 'first_non_null': [1, 2]}
```

## is_duplicated marks every occurrence, unlike pandas duplicated

Applies to: `Expr.is_duplicated`, `Expr.is_unique`, `Expr.is_first_distinct`, `Expr.is_last_distinct`

`Expr.is_duplicated` is true for **all** occurrences of a repeated value, including the first one. pandas `duplicated()` with keep='first' flags only the later copies. Filtering out `is_duplicated()` rows therefore drops every copy, not just the extras. `Expr.is_unique` is its exact complement. For pandas-style dedup masks, use `Expr.is_first_distinct().not_()` to keep the first copy or `Expr.is_last_distinct().not_()` to keep the last.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 1, 2, 1]})
out = df.with_columns(
    pl.col("a").is_duplicated().alias("is_duplicated"),
    pl.col("a").is_unique().alias("is_unique"),
    pl.col("a").is_first_distinct().not_().alias("dup_keep_first"),
    pl.col("a").is_last_distinct().not_().alias("dup_keep_last"),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'a': [1, 1, 2, 1], 'is_duplicated': [True, True, False, True], 'is_unique': [False, False, True, False], 'dup_keep_first': [False, True, False, True], 'dup_keep_last': [True, True, False, False]}
```

## Division by zero yields inf/NaN, not null or an error

Applies to: `Expr.truediv`

`Expr.truediv` (and the `/` operator) follows IEEE-754. `n/0` gives `±inf` and `0/0` gives `NaN`. It does not return null as SQL `NULLIF` code expects, and it does not raise. Because `NaN` is not null, a later `Expr.fill_null` or `Expr.is_null` misses these rows, and they silently poison sums and means. Integer inputs also come back as `Float64`. Guard the denominator explicitly with `pl.when(...).then(None).otherwise(...)`, or clean up afterwards with `Expr.fill_nan` and `Expr.is_infinite`.

```python
import polars as pl

df = pl.DataFrame({"x": [1, 0, 4], "y": [0, 0, 2]})
out = df.with_columns(
    naive=pl.col("x").truediv(pl.col("y")),
    safe=pl.when(pl.col("y") == 0)
    .then(None)
    .otherwise(pl.col("x").truediv(pl.col("y"))),
)
print(out)
print(out.select(
    pl.col("naive").is_null().sum().alias("naive_nulls"),
    pl.col("naive").fill_null(0).sum().alias("naive_sum_after_fill_null"),
    pl.col("safe").is_null().sum().alias("safe_nulls"),
    pl.col("safe").fill_null(0).sum().alias("safe_sum"),
))
```

Output:

```text
shape: (3, 4)
┌─────┬─────┬───────┬──────┐
│ x   ┆ y   ┆ naive ┆ safe │
│ --- ┆ --- ┆ ---   ┆ ---  │
│ i64 ┆ i64 ┆ f64   ┆ f64  │
╞═════╪═════╪═══════╪══════╡
│ 1   ┆ 0   ┆ inf   ┆ null │
│ 0   ┆ 0   ┆ NaN   ┆ null │
│ 4   ┆ 2   ┆ 2.0   ┆ 2.0  │
└─────┴─────┴───────┴──────┘
shape: (1, 4)
┌─────────────┬───────────────────────────┬────────────┬──────────┐
│ naive_nulls ┆ naive_sum_after_fill_null ┆ safe_nulls ┆ safe_sum │
│ ---         ┆ ---                       ┆ ---        ┆ ---      │
│ u32         ┆ f64                       ┆ u32        ┆ f64      │
╞═════════════╪═══════════════════════════╪════════════╪══════════╡
│ 0           ┆ NaN                       ┆ 2          ┆ 2.0      │
└─────────────┴───────────────────────────┴────────────┴──────────┘
```

## Expr.slice takes (offset, length), not (start, end)

Applies to: `Expr.slice`

`Expr.slice(offset, length)` uses a length as its second argument, not an exclusive end index like Python `[1:3]` or pandas `iloc[1:3]`. Writing `slice(1, 3)` while expecting rows 1 and 2 returns three rows instead. If you think in start/end terms, pass `end - start` as the length. Leaving `length=None` takes everything from `offset` onward.

```python
import polars as pl

df = pl.DataFrame({"a": [10, 20, 30, 40, 50]})
# Python-style intent: rows [1:3] -> 20, 30
wrong = df.select(pl.col("a").slice(1, 3))
start, end = 1, 3
right = df.select(pl.col("a").slice(start, end - start))
print(wrong["a"].to_list())
print(right["a"].to_list())
```

Output:

```text
[20, 30, 40]
[20, 30]
```

## Expr.std defaults to sample std (ddof=1), not population std

Applies to: `Expr.std`

`Expr.std` divides by `N - ddof` with `ddof=1` by default, which gives the sample standard deviation. Code ported from NumPy (where `np.std` defaults to population, ddof=0), or written with a population formula in mind, will silently get a larger value. Pass `ddof=0` explicitly when you need the population standard deviation.

```python
import polars as pl

df = pl.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
print(df.select(
    pl.col("a").std().alias("default_ddof1"),
    pl.col("a").std(ddof=0).alias("population_ddof0"),
))
```

Output:

```text
shape: (1, 2)
┌───────────────┬──────────────────┐
│ default_ddof1 ┆ population_ddof0 │
│ ---           ┆ ---              │
│ f64           ┆ f64              │
╞═══════════════╪══════════════════╡
│ 1.290994      ┆ 1.118034         │
└───────────────┴──────────────────┘
```

## Expr.max and Expr.min silently skip NaN; use Expr.nan_max / Expr.nan_min to propagate it

Applies to: `Expr.max`, `Expr.min`, `Expr.nan_max`, `Expr.nan_min`

Coming from numpy, you may expect `max` or `min` to return NaN when the data contains NaN. In Polars, `Expr.max` and `Expr.min` ignore NaN, so `[-1.0, NaN, 1.0]` gives `1.0` and `-1.0`, and a bad value can pass through unnoticed. Use `Expr.nan_max` or `Expr.nan_min` when a NaN should poison the result. You can also check explicitly with `Expr.is_nan`. NaN is not null, so these rules are separate from null handling.

```python
import polars as pl

df = pl.DataFrame({"a": [-1.0, float("nan"), 1.0]})

# NaN ignored: looks like clean data
out1 = df.select(mx=pl.col("a").max(), mn=pl.col("a").min())
print(out1.to_dict(as_series=False))

# NaN propagated
out2 = df.select(mx=pl.col("a").nan_max(), mn=pl.col("a").nan_min())
print(out2.to_dict(as_series=False))

# Explicit check
out3 = df.select(has_nan=pl.col("a").is_nan().any())
print(out3.to_dict(as_series=False))
```

Output:

```text
{'mx': [1.0], 'mn': [-1.0]}
{'mx': [nan], 'mn': [nan]}
{'has_nan': [True]}
```

## NaN compares equal to NaN, so the x != x NaN check does not work

Applies to: `Expr.ne`, `Expr.lt`, `Expr.le`

In IEEE floats, numpy and pandas, `NaN != NaN` is True, and `x != x` is a common way to find NaN. Polars treats NaN as equal to itself. `Expr.ne` returns `false` for NaN vs NaN, `Expr.le` returns `true` and `Expr.lt` returns `false`. Code that relies on IEEE semantics will silently miss every NaN. Use `Expr.is_nan` to detect NaN.

```python
import polars as pl

df = pl.DataFrame({"x": [1.0, float("nan")], "y": [2.0, float("nan")]})

out = df.with_columns(
    ne=pl.col("x").ne(pl.col("y")),
    lt=pl.col("x").lt(pl.col("y")),
    le=pl.col("x").le(pl.col("y")),
    # numpy idiom for NaN detection: finds nothing here
    self_ne=pl.col("x").ne(pl.col("x")),
    # correct NaN detection
    is_nan=pl.col("x").is_nan(),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'x': [1.0, nan], 'y': [2.0, nan], 'ne': [True, False], 'lt': [True, False], 'le': [True, True], 'self_ne': [False, False], 'is_nan': [False, True]}
```

## Expr.ne propagates null, so filtering with != silently drops null rows

Applies to: `Expr.ne`, `Expr.ne_missing`

`Expr.ne` (the `!=` operator) returns null when either side is null. `DataFrame.filter` keeps only rows where the predicate is true, so `filter(pl.col("status") != "done")` also removes rows whose status is null. pandas users expect those rows to be kept, because `NaN != 'done'` is True in pandas. Use `Expr.ne_missing` when null should count as "not equal". `Expr.ne_missing` also treats null vs null as equal (`false`).

```python
import polars as pl

df = pl.DataFrame({"status": ["done", None, "open"]})

# null row silently dropped
print(df.filter(pl.col("status").ne("done")).to_dict(as_series=False))

# null row kept
print(df.filter(pl.col("status").ne_missing("done")).to_dict(as_series=False))

out = df.with_columns(
    ne=pl.col("status").ne("done"),
    ne_missing=pl.col("status").ne_missing("done"),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'status': ['open']}
{'status': [None, 'open']}
{'status': ['done', None, 'open'], 'ne': [False, None, True], 'ne_missing': [False, True, True]}
```

## Expr.n_unique and Expr.len count nulls, unlike pandas nunique

Applies to: `Expr.n_unique`, `Expr.len`, `Expr.null_count`

`Expr.n_unique` counts null as one distinct value. pandas `nunique()` drops missing values by default, so the Polars result can be one higher than expected. `Expr.len` counts every row including nulls. Use `Expr.count` for the non-null count and `Expr.null_count` for the number of nulls. To count distinct values without null, apply `Expr.drop_nulls` before `Expr.n_unique`.

```python
import polars as pl

df = pl.DataFrame({"y": [1, 1, None, None]})

out = df.select(
    n_unique=pl.col("y").n_unique(),
    n_unique_non_null=pl.col("y").drop_nulls().n_unique(),
    len=pl.col("y").len(),
    count=pl.col("y").count(),
    nulls=pl.col("y").null_count(),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'n_unique': [2], 'n_unique_non_null': [1], 'len': [4], 'count': [2], 'nulls': [2]}
```

## Expr.last returns a trailing null unless ignore_nulls=True

Applies to: `Expr.last`

pandas `groupby(...).last()` returns the last non-missing value of each group. Polars `Expr.last` defaults to `ignore_nulls=False` and returns whatever is in the final row, null included. Pass `ignore_nulls=True` to get the last non-null value. The result also depends on row order, so sort the frame first if order matters.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "a", "b", "b"], "v": [1, None, 2, 3]})

out = df.group_by("g", maintain_order=True).agg(
    pl.col("v").last().alias("v_last"),
    pl.col("v").last(ignore_nulls=True).alias("v_last_non_null"),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'g': ['a', 'b'], 'v_last': [None, 3], 'v_last_non_null': [1, 3]}
```

## Expr.not_ and ~ are bitwise on integers, not logical

Applies to: `Expr.not_`, `Expr.or_`

`Expr.not_` (the `~` operator) negates Boolean columns but operates bitwise on integer columns. A 0/1 integer flag therefore becomes -1/-2 instead of 1/0, and no error is raised. `Expr.or_` is likewise a bitwise OR on integers. Cast integer flags to `pl.Boolean` before negating or combining them as logical conditions.

```python
import polars as pl

df = pl.DataFrame({"flag": [1, 0, None]})

out = df.with_columns(
    bitwise=pl.col("flag").not_(),
    tilde=~pl.col("flag"),
    logical=pl.col("flag").cast(pl.Boolean).not_(),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'flag': [1, 0, None], 'bitwise': [-2, -1, None], 'tilde': [-2, -1, None], 'logical': [False, True, None]}
```

## Expr.kurtosis defaults to the biased estimator, so results differ from pandas

Applies to: `Expr.kurtosis`

`Expr.kurtosis` defaults to `fisher=True, bias=True`, which is the biased Fisher (excess) kurtosis, as in scipy's default. pandas `kurt()` returns the bias-corrected value, so porting code gives a different number with no error. Pass `bias=False` to apply the k-statistics correction. Pass `fisher=False` if you want Pearson kurtosis, where a normal distribution gives 3.0.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 3, 2, 1]})

out = df.select(
    default_biased=pl.col("a").kurtosis(),
    unbiased=pl.col("a").kurtosis(bias=False),
    pearson=pl.col("a").kurtosis(fisher=False),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'default_biased': [-1.1530612244897964], 'unbiased': [-0.6122448979591852], 'pearson': [1.8469387755102036]}
```

## Expr.map_elements never calls the function on nulls by default

Applies to: `Expr.map_elements`

`Expr.map_elements` defaults to `skip_nulls=True`, so a UDF written to handle `None` is never called for null rows, which stay null. Pass `skip_nulls=False` if the function must see nulls. Better still, use native expressions such as `Expr.fill_null`, which are much faster than a Python UDF. Always set `return_dtype` so Polars does not have to infer the output type.

```python
import polars as pl

df = pl.DataFrame({"a": [1, None, 3]})


def f(x):
    return 0 if x is None else x * 10


out = df.with_columns(
    skipped=pl.col("a").map_elements(f, return_dtype=pl.Int64),
    seen=pl.col("a").map_elements(f, return_dtype=pl.Int64, skip_nulls=False),
    native=(pl.col("a") * 10).fill_null(0),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'a': [1, None, 3], 'skipped': [10, None, 30], 'seen': [10, 0, 30], 'native': [10, 0, 30]}
```

## Expr.quantile defaults to 'nearest', not pandas' 'linear' interpolation

Applies to: `Expr.quantile`, `Expr.rolling_quantile`, `Expr.rolling_quantile_by`

`Expr.quantile`, `Expr.rolling_quantile` and `Expr.rolling_quantile_by` all default to `interpolation='nearest'`. pandas and numpy default to linear interpolation, so ported code can silently return a different number. For example, `quantile(0.3)` on `[0..5]` with `'nearest'` returns one of the actual elements, while linear interpolation gives `1.5`. Pass `interpolation='linear'` explicitly when you need pandas-compatible results.

```python
import polars as pl

df = pl.DataFrame({"a": [0, 1, 2, 3, 4, 5]})
out = df.select(
    default=pl.col("a").quantile(0.3),
    linear=pl.col("a").quantile(0.3, interpolation="linear"),
)
print(out.to_dict(as_series=False))
roll = df.select(
    default=pl.col("a").rolling_quantile(0.3, window_size=4),
    linear=pl.col("a").rolling_quantile(0.3, interpolation="linear", window_size=4),
)
print(roll.to_dict(as_series=False))
```

Output:

```text
{'default': [2.0], 'linear': [1.5]}
{'default': [None, None, None, 1.0, 2.0, 3.0], 'linear': [None, None, None, 0.8999999999999999, 1.9, 2.9]}
```

## Use replace_strict, not replace, to map values to a new dtype or set a default

Applies to: `Expr.replace`, `Expr.replace_strict`

`Expr.replace` replaces values with values of the same data type, and it keeps every unmatched value unchanged. Its `default` and `return_dtype` parameters have been deprecated since 1.0.0. To map codes to labels, use `Expr.replace_strict`. `Expr.replace_strict` raises `InvalidOperationError` if any non-null value is not covered by the mapping and no `default` is given, so pass `default=` (and `return_dtype=` if needed) to handle unmatched values.

```python
import polars as pl

df = pl.DataFrame({"code": [1, 2, 3]})
mapping = {1: "one", 2: "two"}
try:
    df.select(pl.col("code").replace_strict(mapping))
except Exception as e:
    print(repr(e).split("(")[0])
out = df.with_columns(
    kept=pl.col("code").replace({1: 10}),
    label=pl.col("code").replace_strict(mapping, default="other"),
)
print(out.to_dict(as_series=False))
```

Output:

```text
InvalidOperationError
{'code': [1, 2, 3], 'kept': [10, 2, 3], 'label': ['one', 'two', 'other']}
```

## Expr.rank leaves nulls null and averages ties into floats by default

Applies to: `Expr.rank`

Unlike SQL window ranking, `Expr.rank` does not rank null values last. It only ranks the non-null values and keeps the nulls as null. The default `method='average'` produces Float64 ranks such as `2.5` for ties, while methods like `'dense'` or `'ordinal'` give UInt32 integer ranks. Use `descending=True` for top-is-1 ranking. If you need nulls ranked last, fill them explicitly afterwards with `Expr.fill_null`.

```python
import polars as pl

df = pl.DataFrame({"score": [30, None, 10, 30]})
r = pl.col("score").rank("dense", descending=True)
out = df.with_columns(
    avg=pl.col("score").rank(),
    dense_desc=r,
    nulls_last=r.fill_null(r.max() + 1),
)
print(out.to_dict(as_series=False))
print(out.schema)
```

Output:

```text
{'score': [30, None, 10, 30], 'avg': [2.5, None, 1.0, 2.5], 'dense_desc': [1, None, 2, 1], 'nulls_last': [1, 3, 2, 1]}
Schema({'score': Int64, 'avg': Float64, 'dense_desc': UInt32, 'nulls_last': UInt32})
```

## A single null in a fixed rolling window nulls the result unless min_samples is lowered

Applies to: `Expr.rolling_mean`, `Expr.rolling_max`, `Expr.rolling_min`, `Expr.rolling_median`, `Expr.rolling_quantile`

For the count-based rolling functions, `min_samples` defaults to `window_size`. Every window that contains a null, and every leading row, therefore yields null. Set `min_samples=1` (or another lower value) to compute over the non-null values that are present. The old `min_periods` parameter was renamed to `min_samples` in 1.21.0, so always use the new name. Windows are trailing (the row itself plus the `window_size - 1` rows before it) unless `center=True`.

```python
import polars as pl

df = pl.DataFrame({"x": [1.0, None, 3.0, 4.0]})
out = df.with_columns(
    mean_default=pl.col("x").rolling_mean(2),
    mean_min1=pl.col("x").rolling_mean(2, min_samples=1),
    max_default=pl.col("x").rolling_max(2),
    max_min1=pl.col("x").rolling_max(2, min_samples=1),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'x': [1.0, None, 3.0, 4.0], 'mean_default': [None, None, None, 3.5], 'mean_min1': [1.0, 1.0, 3.0, 3.5], 'max_default': [None, None, None, 4.0], 'max_min1': [1.0, 1.0, 3.0, 4.0]}
```

## rolling_*_by windows are right-closed (t - window, t] with min_samples=1 by default

Applies to: `Expr.rolling_mean_by`, `Expr.rolling_max_by`, `Expr.rolling_min_by`, `Expr.rolling_median_by`, `Expr.rolling_quantile_by`, `Expr.rolling_rank_by`

The `_by` rolling functions default to `closed='right'`, so a `'2d'` window at day t covers (t-2d, t] and excludes the row exactly 2 days earlier. Pass `closed='both'` if you want both endpoints included. Unlike `Expr.rolling_mean`, their `min_samples` defaults to `1`, so the first rows are not null. When `by` is an integer column, `window_size` must use the `'i'` unit, such as `'2i'`. These functions are marked unstable.

```python
import polars as pl
from datetime import date

df = pl.DataFrame({
    "d": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
    "i": [0, 1, 2],
    "v": [1.0, 2.0, 3.0],
})
out = df.with_columns(
    right=pl.col("v").rolling_mean_by("d", window_size="2d"),
    both=pl.col("v").rolling_mean_by("d", window_size="2d", closed="both"),
    by_int=pl.col("v").rolling_max_by("i", window_size="2i"),
)
print(out.select("right", "both", "by_int").to_dict(as_series=False))
```

Output:

```text
{'right': [1.0, 1.5, 2.5], 'both': [1.0, 1.5, 2.0], 'by_int': [1.0, 2.0, 3.0]}
```

## Expr.pct_change does not forward-fill nulls the way old pandas did

Applies to: `Expr.pct_change`

`Expr.pct_change` preserves nulls, which matches pandas `fill_method=None`. In the documented example, the null row and the row right after it both come out null. Code ported from older pandas, where padding was the default, will therefore get extra nulls. If you want the padded behaviour, call `Expr.forward_fill` before `Expr.pct_change`. The first `n` rows are always null.

```python
import polars as pl

df = pl.DataFrame({"a": [10, 11, 12, None, 12]})
out = df.with_columns(
    pct=pl.col("a").pct_change(),
    pct_ffill=pl.col("a").forward_fill().pct_change(),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'a': [10, 11, 12, None, 12], 'pct': [None, 0.1, 0.09090909090909091, None, None], 'pct_ffill': [None, 0.1, 0.09090909090909091, 0.0, 0.0]}
```

## Expr.product of an empty or all-null group returns 1, not null

Applies to: `Expr.product`

When there are no non-null values, `Expr.product` returns `1`. In a `DataFrame.group_by` aggregation, a group whose values are all missing therefore reports a product of 1 instead of null, which is a silently wrong result. Aggregate `Expr.count` alongside the product and treat groups with a count of 0 as missing, for example by guarding with `pl.when` or by masking afterwards with `Series.zip_with`.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "a", "b"], "v": [2, 3, None]})
out = df.group_by("g", maintain_order=True).agg(
    pl.col("v").product().alias("naive"),
    pl.col("v").count().alias("n"),
)
print(out.to_dict(as_series=False))
nulls = pl.Series("safe", [None] * out.height, dtype=pl.Int64)
safe = out.get_column("naive").zip_with(out.get_column("n") > 0, nulls)
print(safe.to_list())
```

Output:

```text
{'g': ['a', 'b'], 'naive': [6, 1], 'n': [2, 0]}
[6, None]
```

## Integer base with integer exponent stays integer in Expr.pow

Applies to: `Expr.pow`

`Expr.pow` follows the dtype of the base unless the exponent is a float, in which case the result follows the float exponent. `pl.col("x").pow(2)` on an Int64 column stays Int64. For negative or fractional powers, do not pass an integer exponent. Pass a float exponent such as `-1.0`, or cast the base to `pl.Float64` first, as the docstring recommends.

```python
import polars as pl

df = pl.DataFrame({"x": [1, 2, 4]})
out = df.with_columns(
    sq=pl.col("x").pow(2),
    inv=pl.col("x").pow(-1.0),
    inv_cast=pl.col("x").cast(pl.Float64).pow(-1),
    root=pl.col("x").pow(0.5),
)
print(out.schema)
print(out.to_dict(as_series=False))
```

Output:

```text
Schema({'x': Int64, 'sq': Int64, 'inv': Float64, 'inv_cast': Float64, 'root': Float64})
{'x': [1, 2, 4], 'sq': [1, 4, 16], 'inv': [1.0, 0.5, 0.25], 'inv_cast': [1.0, 0.5, 0.25], 'root': [1.0, 1.4142135623730951, 2.0]}
```

## Expr.shrink_dtype is a deprecated no-op

Applies to: `Expr.shrink_dtype`

Since 1.33.0, `Expr.shrink_dtype` is deprecated and does nothing. Calling it emits a deprecation warning and leaves the dtype unchanged, so any memory saving you expected never happens. Use `Series.shrink_dtype` on materialized data instead, for example via `DataFrame.get_column`.

```python
import polars as pl
import warnings

df = pl.DataFrame({"a": [1, 2, 3]})
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    via_expr = df.select(pl.col("a").shrink_dtype())
print(via_expr.dtypes)  # [Int64] - unchanged
via_series = df.get_column("a").shrink_dtype()
print(via_series.dtype)  # Int8
```

Output:

```text
[Int64]
Int8
```

## Sum of an all-null or empty column is 0, not null

Applies to: `Expr.sum`

`Expr.sum` returns `0` when there are no non-null values, unlike SQL `SUM`, which returns NULL. In a `DataFrame.group_by` aggregation, a group whose values are all missing silently reports a total of 0, which looks the same as a real zero. Aggregate `Expr.count` next to the sum so empty groups can be detected. If an empty sum should be null, null it out when the count is 0; the `Expr.sum` docstring suggests a `pl.when` guard on the count.

```python
import polars as pl

df = pl.DataFrame(
    {"g": ["a", "a", "b"], "x": [None, None, 5]},
    schema={"g": pl.String, "x": pl.Int64},
)
out = df.group_by("g", maintain_order=True).agg(
    pl.col("x").sum().alias("naive"),
    pl.col("x").count().alias("n"),
    # max is null when a group has no non-null values, so this nulls empty sums
    (pl.col("x").sum() + pl.col("x").max() * 0).alias("safe"),
)
# group a: naive=0 (misleading), n=0, safe=None
print(out.to_dicts())
```

Output:

```text
[{'g': 'a', 'naive': 0, 'n': 0, 'safe': None}, {'g': 'b', 'naive': 5, 'n': 1, 'safe': 5}]
```

## Fixed-window rolling stats need a full non-null window by default

Applies to: `Expr.rolling_sum`, `Expr.rolling_std`, `Expr.rolling_var`, `Expr.rolling_skew`

For `Expr.rolling_sum`, `Expr.rolling_std`, `Expr.rolling_var` and `Expr.rolling_skew`, `min_samples=None` means `min_samples = window_size`. The first `window_size - 1` rows are therefore null. A single null inside the data also nulls out every window that contains it, not just its own row. The docstrings of `Expr.rolling_sum`, `Expr.rolling_std` and `Expr.rolling_var` note that `min_periods` was renamed `min_samples` in 1.21.0. Pass `min_samples=1` (or another threshold) when partial windows should still produce a value.

```python
import polars as pl

df = pl.DataFrame({"x": [1.0, None, 3.0, 4.0, 5.0]})
out = df.with_columns(
    pl.col("x").rolling_sum(2).alias("default"),
    pl.col("x").rolling_sum(2, min_samples=1).alias("lenient"),
)
# default: None, None, None, 7.0, 9.0
# lenient: 1.0, 1.0, 3.0, 7.0, 9.0
print(out.to_dict(as_series=False))
```

Output:

```text
{'x': [1.0, None, 3.0, 4.0, 5.0], 'default': [None, None, None, 7.0, 9.0], 'lenient': [1.0, 1.0, 3.0, 7.0, 9.0]}
```

## Rolling-by windows are right-closed and exclude the left edge

Applies to: `Expr.rolling_sum_by`, `Expr.rolling_std_by`, `Expr.rolling_var_by`

`Expr.rolling_sum_by`, `Expr.rolling_std_by` and `Expr.rolling_var_by` default to `closed='right'`. The window at `t` is therefore `(t - window_size, t]`, so a "2d" window over daily data covers today and yesterday, not three days. Pass `closed='both'` if the left boundary must be included. Unlike the fixed-size variants, these default to `min_samples=1`, and an integer `by` column needs an `'i'` window such as `"2i"`. These methods are marked unstable.

```python
import polars as pl
from datetime import date

df = pl.DataFrame(
    {
        "d": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        "x": [1, 2, 3, 4],
    }
)
out = df.with_columns(
    pl.col("x").rolling_sum_by("d", "2d").alias("right"),
    pl.col("x").rolling_sum_by("d", "2d", closed="both").alias("both"),
)
# right: 1, 3, 5, 7   both: 1, 3, 6, 9
print(out.select("right", "both").to_dict(as_series=False))
```

Output:

```text
{'right': [1, 3, 5, 7], 'both': [1, 3, 6, 9]}
```

## skew defaults to the biased estimator

Applies to: `Expr.skew`, `Expr.rolling_skew`

`Expr.skew` and `Expr.rolling_skew` default to `bias=True`, which gives the biased Fisher-Pearson coefficient g1. pandas `skew` and spreadsheet `SKEW` report the bias-adjusted G1, so ported code silently produces smaller-magnitude numbers. Pass `bias=False` to get the adjusted coefficient.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 3, 2, 1]})
out = df.select(
    pl.col("a").skew().alias("biased"),
    pl.col("a").skew(bias=False).alias("adjusted"),
)
# biased ~0.343622, adjusted ~0.512241
print(out.to_dicts())
```

Output:

```text
[{'biased': 0.3436215967445454, 'adjusted': 0.5122408325718827}]
```

## round uses bankers' rounding by default

Applies to: `Expr.round`

`Expr.round` defaults to `mode='half_to_even'`, so 0.5 rounds to 0.0 and 2.5 rounds to 2.0. People coming from SQL `ROUND` or spreadsheets expect ties to round away from zero, and that habit gives off-by-one results on exact halves. Pass `mode='half_away_from_zero'` for that behaviour.

```python
import polars as pl

df = pl.DataFrame({"a": [0.5, 1.5, 2.5, -2.5]})
out = df.select(
    pl.col("a").round(0).alias("default"),
    pl.col("a").round(0, mode="half_away_from_zero").alias("away"),
)
# default: 0.0, 2.0, 2.0, -2.0
# away:    1.0, 2.0, 3.0, -3.0
print(out.to_dict(as_series=False))
```

Output:

```text
{'default': [0.0, 2.0, 2.0, -2.0], 'away': [1.0, 2.0, 3.0, -3.0]}
```

## Nulls sort first, even when descending

Applies to: `Expr.sort`, `Expr.sort_by`

`Expr.sort` and `Expr.sort_by` default to `nulls_last=False`, so nulls come first in both ascending and descending order. pandas places missing values last, so a "sort descending then take the first" pattern returns a null instead of the maximum. Pass `nulls_last=True`. `Expr.sort_by` also defaults to `maintain_order=False`, so ties are not guaranteed to keep their original order unless you set it.

```python
import polars as pl

df = pl.DataFrame({"name": ["x", "y", "z"], "score": [None, 5, 7]})
wrong = df.select(
    pl.col("name").sort_by("score", descending=True).first().alias("best"),
    pl.col("score").sort(descending=True).first().alias("top"),
)
right = df.select(
    pl.col("name").sort_by("score", descending=True, nulls_last=True).first().alias("best"),
    pl.col("score").sort(descending=True, nulls_last=True).first().alias("top"),
)
print(wrong.to_dicts())  # best=x, top=None
print(right.to_dicts())  # best=z, top=7
```

Output:

```text
[{'best': 'x', 'top': None}]
[{'best': 'z', 'top': 7}]
```

## top_k output is unordered, and top_k_by uses reverse rather than descending

Applies to: `Expr.top_k`, `Expr.top_k_by`

`Expr.top_k` and `Expr.top_k_by` return the k elements in no guaranteed order, so sort afterwards if you need them ranked. In 1.0.0 the `descending` parameter of `Expr.top_k_by` was renamed `reverse`, so use `reverse=True` to get the k smallest. Non-null values are always preferred over nulls, even with `reverse=True`.

```python
import polars as pl

df = pl.DataFrame({"name": ["a", "b", "c", "d"], "score": [10, 40, None, 30]})
top = df.select(pl.all().top_k_by("score", 2)).sort("score", descending=True)
low = df.select(pl.all().top_k_by("score", 2, reverse=True)).sort("score")
print(top.to_dicts())  # b 40, d 30
print(low.to_dicts())  # a 10, d 30 (null row c is not chosen)
```

Output:

```text
[{'name': 'b', 'score': 40}, {'name': 'd', 'score': 30}]
[{'name': 'a', 'score': 10}, {'name': 'd', 'score': 30}]
```

## Expr.unique does not keep first-appearance order by default

Applies to: `Expr.unique`

`Expr.unique` defaults to `maintain_order=False`, so the order of the unique values is not guaranteed. This differs from pandas `unique()`, which keeps order of appearance. Code that pairs the result with another ordered list, or takes the 'first' unique value, can silently give wrong results. Pass `maintain_order=True` when order matters, or sort the result explicitly.

```python
import polars as pl

df = pl.DataFrame({"a": [3, 1, 3, 2, 1]})

# Default order is not guaranteed; do not rely on it.
# Keep first-appearance order:
ordered = df.select(pl.col("a").unique(maintain_order=True))
print(ordered["a"].to_list())  # [3, 1, 2]

# Or impose an explicit order:
sorted_u = df.select(pl.col("a").unique().sort())
print(sorted_u["a"].to_list())  # [1, 2, 3]
```

Output:

```text
[3, 1, 2]
[1, 2, 3]
```

## Expr.value_counts returns one Struct column in unspecified order

Applies to: `Expr.value_counts`

`Expr.value_counts` returns a single `Struct` column that pairs each value with its count, not two separate columns. Unnest it with `DataFrame.unnest` to get two columns. The default `sort=False` gives a non-deterministic row order, not most-frequent-first. The count field is named `count`, or `proportion` when `normalize=True`, unless you pass `name`. Use `sort=True` and `DataFrame.unnest` on the result.

```python
import polars as pl

df = pl.DataFrame({"color": ["red", "blue", "red", "green", "blue", "blue"]})

vc = df.select(pl.col("color").value_counts(sort=True))
print(vc.schema)  # a single Struct column, not two columns

flat = vc.unnest("color")
print(flat.columns)  # ['color', 'count']
print(flat.rows())  # [('blue', 3), ('red', 2), ('green', 1)]

props = df.select(
    pl.col("color").value_counts(sort=True, normalize=True)
).unnest("color")
print(props.columns)  # ['color', 'proportion']
```

Output:

```text
Schema({'color': Struct({'color': String, 'count': UInt32})})
['color', 'count']
[('blue', 3), ('red', 2), ('green', 1)]
['color', 'proportion']
```

## Expr.where is a deprecated alias of filter, not a length-preserving mask

Applies to: `Expr.where`, `Expr.filter`, `pl.when`

`Expr.where` is deprecated since 0.20.4 and is only an alias for `Expr.filter`. It drops the rows that fail the predicate, so the result is shorter. pandas' where method instead keeps the length and masks the failing values. To filter, call `Expr.filter`. To mask while keeping every row, use `pl.when`, which yields null where the condition is false unless you supply an otherwise value, or use `Series.zip_with` on a Series.

```python
import polars as pl

df = pl.DataFrame({"b": [1, 2, 3]})

# where behaves exactly like filter: rows are dropped
w = df.select(pl.col("b").where(pl.col("b") >= 2))["b"].to_list()
f = df.select(pl.col("b").filter(pl.col("b") >= 2))["b"].to_list()
print(w, f)  # [2, 3] [2, 3]

# masking keeps the original length
s = df["b"]
masked = s.zip_with(s >= 2, pl.Series([None, None, None], dtype=pl.Int64))
print(masked.to_list())  # [None, 2, 3]
```

Output:

```text
[2, 3] [2, 3]
[None, 2, 3]
```

## Expr.var defaults to sample variance with ddof=1

Applies to: `Expr.var`

`Expr.var` divides by `N - ddof`, and `ddof` defaults to 1, which gives the sample variance. NumPy's default is the population variance (`ddof=0`). Code ported from NumPy therefore returns different numbers without any error. Pass `ddof=0` explicitly when you want the population variance.

```python
import polars as pl

df = pl.DataFrame({"a": [-1, 0, 1]})

out = df.select(
    pl.col("a").var().alias("sample_ddof1"),
    pl.col("a").var(ddof=0).alias("population_ddof0"),
)
print(out.columns)
print(out.row(0))  # (1.0, 0.6666666666666666)
```

Output:

```text
['sample_ddof1', 'population_ddof0']
(1.0, 0.6666666666666666)
```

## The ^ operator is bitwise xor on integers, not exponentiation

Applies to: `Expr.xor`, `Expr.pow`

`expr ^ other` maps to `Expr.xor`, and on integer columns it is a bitwise exclusive-or. It is logical only on booleans. Writing `pl.col("x") ^ 2` to square a column, as in Excel or R, silently returns wrong numbers. Use `Expr.pow` or `**` for powers.

```python
import polars as pl

df = pl.DataFrame({"x": [2, 3, 10]})

out = df.select(
    (pl.col("x") ^ 2).alias("xor_wrong"),
    pl.col("x").pow(2).alias("pow"),
    (pl.col("x") ** 2).alias("pow_op"),
)
print(out.to_dict(as_series=False))
# xor_wrong: [0, 1, 8]; pow: [4, 9, 100]

b = pl.DataFrame({"p": [True, False], "q": [True, True]})
print(b.select(pl.col("p").xor(pl.col("q")))["p"].to_list())  # [False, True]
```

Output:

```text
{'xor_wrong': [0, 1, 8], 'pow': [4, 9, 100], 'pow_op': [4, 9, 100]}
[False, True]
```

## Expr.unique_counts gives counts only, aligned to first appearance

Applies to: `Expr.unique_counts`, `Expr.unique`

`Expr.unique_counts` returns only the counts, without the values, ordered by first appearance. If you pair it with the default `Expr.unique()` (order not guaranteed), the counts can be attached to the wrong values. Pair it with `Expr.unique(maintain_order=True)`, or use `Expr.value_counts` when you need values and counts together.

```python
import polars as pl

df = pl.DataFrame({"id": ["c", "a", "c", "b", "c", "a"]})

out = df.select(
    pl.col("id").unique(maintain_order=True),
    pl.col("id").unique_counts().alias("n"),
)
print(out.rows())  # [('c', 3), ('a', 2), ('b', 1)]
```

Output:

```text
[('c', 3), ('a', 2), ('b', 1)]
```

## Expr.upper_bound is the dtype maximum, not the data maximum

Applies to: `Expr.upper_bound`

`Expr.upper_bound` returns the highest value the column's dtype can represent, as a unit result. It does not compute the largest value in the data. Using it as a data maximum, for example to normalise or set an upper clip limit, gives wildly wrong numbers. Use `Expr.max` for the data maximum. The result of `Expr.upper_bound` also depends on the dtype.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 3]})

out = df.select(
    pl.col("a").max().alias("data_max"),
    pl.col("a").upper_bound().alias("i64_bound"),
    pl.col("a").cast(pl.Int8).upper_bound().alias("i8_bound"),
)
print(out.columns)
print(out.row(0))  # (3, 9223372036854775807, 127)
```

Output:

```text
['data_max', 'i64_bound', 'i8_bound']
(3, 9223372036854775807, 127)
```
