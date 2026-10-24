# Expr.arr: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## Use Expr.arr.agg to reduce each array and Expr.arr.eval to keep its shape

Applies to: `Expr.arr.agg`, `Expr.arr.eval`

`Expr.arr.agg` explodes the result automatically. An aggregation such as `pl.element().null_count()` gives one scalar per row, and a non-aggregation such as `drop_nulls()` gives a `list` column. `Expr.arr.eval` does not explode, so `pl.element().rank()` returns an `array` of the same width. If the expression can return a different number of elements per row, pass `as_list=True` to `Expr.arr.eval`; otherwise the result cannot fit the fixed-width array type.

```python
import polars as pl

df = pl.Series("a", [[1, None], [42, 13]], pl.Array(pl.Int64, 2)).to_frame()

# agg: aggregation gives a scalar per row
print(df.select(pl.col("a").arr.agg(pl.element().null_count()).alias("nc")).schema)
# eval: keeps the array shape
print(df.select(pl.col("a").arr.eval(pl.element().rank()).alias("rk")).schema)

# variable-length output without as_list
try:
    print(df.select(pl.col("a").arr.eval(pl.element().drop_nulls()).alias("x")))
except Exception as e:
    print(type(e).__name__)

# right: collect as list
print(df.select(pl.col("a").arr.eval(pl.element().drop_nulls(), as_list=True).alias("x")))
```

Output:

```text
Schema({'nc': UInt32})
Schema({'rk': Array(Float64, shape=(2,))})
InvalidOperationError
shape: (2, 1)
┌───────────┐
│ x         │
│ ---       │
│ list[i64] │
╞═══════════╡
│ [1]       │
│ [42, 13]  │
└───────────┘
```

## Expr.arr.shift moves values inside each array, Expr.shift moves whole rows

Applies to: `Expr.arr.shift`

`Expr.shift` on an Array column shifts the rows, so the first row becomes null. `Expr.arr.shift` shifts the elements inside every array. It does not rotate them: vacated slots are filled with null and the array width stays the same. A negative `n` shifts toward the front, like SQL `LEAD`.

```python
import polars as pl

df = pl.DataFrame(
    {"a": [[1, 2, 3], [4, 5, 6]]}, schema={"a": pl.Array(pl.Int64, 3)}
)
out = df.with_columns(
    row_shift=pl.col("a").shift(),
    elem_shift=pl.col("a").arr.shift(),
    elem_lead=pl.col("a").arr.shift(-2),
)
print(out.rows())
```

Output:

```text
[([1, 2, 3], None, [None, 1, 2], [3, None, None]), ([4, 5, 6], [1, 2, 3], [None, 4, 5], [6, None, None])]
```

## Convert with Expr.arr.to_list before using list-only operations

Applies to: `Expr.arr.to_list`

The `Expr.arr` namespace is smaller than `Expr.list`. It has no `drop_nulls`, `filter`, `gather` or set operations such as `Expr.list.set_union`. Do not assume that calling `Expr.list` methods on an `Array` column will work. Convert explicitly with `Expr.arr.to_list`, which keeps the inner dtype, and then use the `Expr.list` method.

```python
import polars as pl

df = pl.DataFrame(
    {"a": [[1, None], [3, 4]]}, schema={"a": pl.Array(pl.Int64, 2)}
)
try:
    print(df.select(pl.col("a").list.drop_nulls()))
except Exception as e:
    print(type(e).__name__)

out = df.select(pl.col("a").arr.to_list().list.drop_nulls())
print(out.schema)
print(out["a"].to_list())
```

Output:

```text
InvalidOperationError
Schema({'a': List(Int64)})
[[1], [3, 4]]
```

## Expr.arr.explode keeps a null row for null arrays by default

Applies to: `Expr.arr.explode`

With the default `keep_nulls=True`, a null array becomes a single null row rather than disappearing. Counts and joins on the exploded column then include a spurious null. Pass `keep_nulls=False` to drop those rows. `empty_as_null` likewise defaults to True.

```python
import polars as pl

df = pl.DataFrame(
    {"a": [[1, 2], None]}, schema={"a": pl.Array(pl.Int64, 2)}
)
default = df.select(pl.col("a").arr.explode())
dropped = df.select(pl.col("a").arr.explode(keep_nulls=False))
print(default["a"].to_list())
print(dropped["a"].to_list())
```

Output:

```text
[1, 2, None]
[1, 2]
```

## Expr.arr.sort puts nulls first unless nulls_last=True

Applies to: `Expr.arr.sort`

`Expr.arr.sort` defaults to `nulls_last=False`, so null elements come first in every sorted array. This applies to both ascending and descending order. Code that then takes the first element as the minimum (or as the maximum after `descending=True`) gets null. Pass `nulls_last=True` when nulls should sink to the end.

```python
import polars as pl

df = pl.DataFrame(
    {"a": [[3, None, 1]]}, schema={"a": pl.Array(pl.Int64, 3)}
)
out = df.select(
    default=pl.col("a").arr.sort(),
    desc=pl.col("a").arr.sort(descending=True),
    fixed=pl.col("a").arr.sort(descending=True, nulls_last=True),
)
print(out.rows(named=True))
print(out.select(pl.col("desc").arr.first(), pl.col("fixed").arr.first()).rows())
```

Output:

```text
[{'default': [None, 1, 3], 'desc': [None, 3, 1], 'fixed': [3, 1, None]}]
[(None, 3)]
```

## Build a real Array column before calling Expr.arr methods

Applies to: `Expr.arr.sum`, `Expr.arr.max`, `Expr.arr.get`

`pl.DataFrame` infers nested Python lists as `pl.List`, not `pl.Array`, as the printed schema `List(Int64)` shows. Calling `Expr.arr.sum` on such a column raises an error, because the `.arr` namespace expects a fixed-width `pl.Array` column. Declare the column as `pl.Array(inner, width)` in `schema=`, or convert an existing list column with `Expr.list.to_array`. For data whose length genuinely varies, use the `Expr.list` namespace instead.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, 2], [3, 4]]})
print(df.schema)  # inferred as List, not Array
try:
    df.select(pl.col("a").arr.sum())
    print("no error")
except Exception:
    print("raised: .arr needs an Array column")

# Fix 1: convert the list column to a fixed-width array
fixed = df.with_columns(pl.col("a").list.to_array(2))
print(fixed.schema)
print(fixed.select(pl.col("a").arr.sum()).to_dicts())

# Fix 2: declare the Array dtype up front
df2 = pl.DataFrame({"a": [[1, 2], [3, 4]]}, schema={"a": pl.Array(pl.Int64, 2)})
print(df2.select(pl.col("a").arr.sum()).to_dicts())
```

Output:

```text
Schema({'a': List(Int64)})
raised: .arr needs an Array column
Schema({'a': Array(Int64, shape=(2,))})
[{'a': 3}, {'a': 7}]
[{'a': 3}, {'a': 7}]
```

## Expr.arr.get raises on out-of-bounds unless null_on_oob=True

Applies to: `Expr.arr.get`

Part of the `Expr.arr.get` docstring prose says an out-of-bounds index returns `None`. However, with the default `null_on_oob=False` it raises an error instead. If you expect a null for a missing position, pass `null_on_oob=True` explicitly. Negative indices count from the end, so `-1` gives the last element; `Expr.arr.last` expresses that more clearly.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, 2], [3, 4]]}, schema={"a": pl.Array(pl.Int64, 2)})

try:
    df.select(pl.col("a").arr.get(2))
    print("no error")
except Exception:
    print("raised: index out of bounds")

print(df.select(pl.col("a").arr.get(2, null_on_oob=True)).to_dicts())
print(df.select(pl.col("a").arr.get(-1)).to_dicts())
print(df.select(pl.col("a").arr.last()).to_dicts())
```

Output:

```text
raised: index out of bounds
[{'a': None}, {'a': None}]
[{'a': 2}, {'a': 4}]
[{'a': 2}, {'a': 4}]
```

## Expr.arr.head, tail and slice return List by default, not Array

Applies to: `Expr.arr.head`, `Expr.arr.tail`, `Expr.arr.slice`

By default, `Expr.arr.head`, `Expr.arr.tail` and `Expr.arr.slice` return a `pl.List` column, even though the input is a fixed-width `pl.Array`. Chaining another `.arr` method onto that result then fails because the dtype is no longer Array. Pass `as_array=True` to keep a fixed-width Array; this requires constant `n`, `offset` and `length` values. Alternatively, continue with the `Expr.list` namespace.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, 2, 3], [4, 5, 6]]}, schema={"a": pl.Array(pl.Int64, 3)})

print(df.select(pl.col("a").arr.head(2)).schema)  # List
try:
    df.select(pl.col("a").arr.head(2).arr.sum())
    print("no error")
except Exception:
    print("raised: result is List, not Array")

print(df.select(pl.col("a").arr.head(2, as_array=True)).schema)  # Array
print(df.select(pl.col("a").arr.head(2, as_array=True).arr.sum()).to_dicts())
print(df.select(pl.col("a").arr.slice(1, 2, as_array=True)).to_dicts())
print(df.select(pl.col("a").arr.head(2).list.sum()).to_dicts())
```

Output:

```text
Schema({'a': List(Int64)})
raised: result is List, not Array
Schema({'a': Array(Int64, shape=(2,))})
[{'a': 3}, {'a': 9}]
[{'a': [2, 3]}, {'a': [5, 6]}]
[{'a': 3}, {'a': 9}]
```

## Expr.arr.all and Expr.arr.any ignore null elements

Applies to: `Expr.arr.all`, `Expr.arr.any`

`Expr.arr.all` and `Expr.arr.any` ignore null elements inside a sub-array rather than treating them as unknown. As a result, an all-null array gives `true` for `Expr.arr.all` and `false` for `Expr.arr.any`. Only a null array row itself produces null. If a null element should count against the result, count nulls with `Expr.arr.agg(pl.element().null_count())` and combine that check with `Expr.and_`.

```python
import polars as pl

df = pl.DataFrame(
    {"a": [[True, True], [None, None], [False, None], None]},
    schema={"a": pl.Array(pl.Boolean, 2)},
)
nulls = pl.col("a").arr.agg(pl.element().null_count())
out = df.with_columns(
    all=pl.col("a").arr.all(),
    any=pl.col("a").arr.any(),
    nulls=nulls,
    all_no_nulls=pl.col("a").arr.all().and_(nulls.eq(0)),
)
print(out.columns)
for row in out.rows():
    print(row)
```

Output:

```text
['a', 'all', 'any', 'nulls', 'all_no_nulls']
([True, True], True, True, 0, True)
([None, None], True, False, 2, False)
([False, None], False, False, 1, False)
(None, None, None, None, None)
```

## Expr.arr.join silently drops nulls by default

Applies to: `Expr.arr.join`

`Expr.arr.join` defaults to `ignore_nulls=True`, so null elements vanish from the joined string. For example, `["a", null]` becomes `"a"` with no hint that a value was missing. Pass `ignore_nulls=False` to make the whole result null whenever a sub-array contains a null. The method also errors if the inner dtype is not `pl.String`, so cast first with `Expr.cast`.

```python
import polars as pl

df = pl.DataFrame(
    {"s": [["a", None], ["x", "y"]]},
    schema={"s": pl.Array(pl.String, 2)},
)
out = df.select(
    default=pl.col("s").arr.join("-"),
    strict=pl.col("s").arr.join("-", ignore_nulls=False),
)
print(out.to_dicts())
```

Output:

```text
[{'default': 'a', 'strict': None}, {'default': 'x-y', 'strict': 'x-y'}]
```

## Expr.arr.std and Expr.arr.var default to ddof=1 (sample statistics)

Applies to: `Expr.arr.std`, `Expr.arr.var`

`Expr.arr.std` and `Expr.arr.var` default to `ddof=1`, which gives the sample estimator rather than the population statistic. Code that assumes `ddof=0` silently gets different numbers: for `[1, 2]` the default std is `0.7071` while `ddof=0` gives `0.5`. Pass `ddof=0` explicitly when you want the population statistic.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, 2], [4, 3]]}, schema={"a": pl.Array(pl.Int64, 2)})
out = df.select(
    std_default=pl.col("a").arr.std(),
    std_pop=pl.col("a").arr.std(ddof=0),
    var_default=pl.col("a").arr.var(),
    var_pop=pl.col("a").arr.var(ddof=0),
)
print(out.to_dicts())
```

Output:

```text
[{'std_default': 0.7071067811865476, 'std_pop': 0.5, 'var_default': 0.5, 'var_pop': 0.25}, {'std_default': 0.7071067811865476, 'std_pop': 0.5, 'var_default': 0.5, 'var_pop': 0.25}]
```

## Expr.arr.unique returns an unordered List

Applies to: `Expr.arr.unique`

`Expr.arr.unique` defaults to `maintain_order=False`, so the order of the distinct values is not guaranteed. Code that takes the "first unique" value can therefore give wrong results. The output is also a `pl.List`, not an Array, because the number of distinct values varies per row. Pass `maintain_order=True` for first-occurrence order, or sort explicitly, and use `Expr.list` methods on the result.

```python
import polars as pl

df = pl.DataFrame({"a": [[3, 1, 3, 2]]}, schema={"a": pl.Array(pl.Int64, 4)})

ordered = df.select(pl.col("a").arr.unique(maintain_order=True))
print(ordered.schema)  # List, not Array
print(ordered.to_dicts())

sorted_unique = df.select(pl.col("a").arr.unique().list.sort())
print(sorted_unique.to_dicts())
print(ordered.select(pl.col("a").list.first()).to_dicts())
```

Output:

```text
Schema({'a': List(Int64)})
[{'a': [3, 1, 2]}]
[{'a': [1, 2, 3]}]
[{'a': 3}]
```
