# Expr.list: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## Expr.list.get and Expr.list.gather raise on out-of-bounds indices by default

Applies to: `Expr.list.get`, `Expr.list.gather`, `Expr.list.first`, `Expr.list.last`

The `Expr.list.get` docstring prose says an out-of-bounds index returns `None`, but the default is `null_on_oob=False`, which raises an error. `Expr.list.gather` has the same default. A single empty or short sublist is enough to make the whole query fail. Pass `null_on_oob=True` when sublists can be shorter than the index. To take the first or last element, use `Expr.list.first` or `Expr.list.last`, which return null for empty lists.

```python
import polars as pl

df = pl.DataFrame({"a": [[3, 2, 1], [], [1, 2]]})
try:
    df.select(pl.col("a").list.get(0))
except Exception as e:
    print(getattr(type(e), "__name__"))
try:
    df.select(pl.col("a").list.gather([0, 2]))
except Exception as e:
    print(getattr(type(e), "__name__"))
out = df.select(
    get=pl.col("a").list.get(0, null_on_oob=True),
    first=pl.col("a").list.first(),
    last=pl.col("a").list.last(),
    taken=pl.col("a").list.gather([0, 2], null_on_oob=True),
)
print(out.to_dict(as_series=False))
```

Output:

```text
ComputeError
OutOfBoundsError
{'get': [3, None, 1], 'first': [3, None, 1], 'last': [1, None, 2], 'taken': [[3, 1], [None, None], [1, None]]}
```

## Expr.list.len counts null elements

Applies to: `Expr.list.len`, `Expr.list.drop_nulls`

`Expr.list.len` returns the number of elements in each sublist, and null elements count toward that total. If you expect a count of non-null values, the result is silently too high. To count only non-null elements, drop the nulls first with `Expr.list.drop_nulls` and then call `Expr.list.len`.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, 2, None], [None], [5]]})
out = df.with_columns(
    len_with_nulls=pl.col("a").list.len(),
    non_null=pl.col("a").list.drop_nulls().list.len(),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'a': [[1, 2, None], [None], [5]], 'len_with_nulls': [3, 1, 1], 'non_null': [2, 0, 1]}
```

## Expr.list.all is True and Expr.list.any is False for empty or all-null lists

Applies to: `Expr.list.all`, `Expr.list.any`

When a row has no non-null elements, `Expr.list.all` returns `True` and `Expr.list.any` returns `False`. This applies to both `[]` and `[null]`, while a null list gives null. A filter such as "every check passed" therefore keeps rows that ran no checks at all. If an empty or all-null list should not count as passing, also require at least one non-null element.

```python
import polars as pl

df = pl.DataFrame({"a": [[True], [False, True], [None], [], None]})
has_values = pl.col("a").list.drop_nulls().list.len() > 0
out = df.with_columns(
    naive_all=pl.col("a").list.all(),
    strict_all=pl.col("a").list.all() & has_values,
    any=pl.col("a").list.any(),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'a': [[True], [False, True], [None], [], None], 'naive_all': [True, False, True, True, None], 'strict_all': [True, False, False, False, None], 'any': [True, True, False, False, None]}
```

## Expr.list.join needs String elements and silently skips nulls

Applies to: `Expr.list.join`

`Expr.list.join` errors if the list's inner type is not `String`. Cast first, for example with `Expr.cast(pl.List(pl.String))`. The default `ignore_nulls=True` silently drops null elements, so `[1, null, 3]` becomes `"1-3"` with no trace of the missing value. Pass `ignore_nulls=False` if a sublist containing a null should produce a null string.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, None, 3], [4, 5]]})
try:
    df.select(pl.col("a").list.join("-"))
except Exception as e:
    print(getattr(type(e), "__name__"))
s = pl.col("a").cast(pl.List(pl.String))
out = df.select(
    skip_nulls=s.list.join("-"),
    propagate=s.list.join("-", ignore_nulls=False),
)
print(out.to_dict(as_series=False))
```

Output:

```text
InvalidOperationError
{'skip_nulls': ['1-3', '4-5'], 'propagate': [None, '4-5']}
```

## List set operations match nulls as values and do not sort the result

Applies to: `Expr.list.set_difference`, `Expr.list.set_intersection`, `Expr.list.set_symmetric_difference`, `Expr.list.set_union`

The list set operations treat null as an ordinary value. A null on both sides is removed by `Expr.list.set_difference` and kept by `Expr.list.set_intersection`. The output is not sorted, so `Expr.list.set_symmetric_difference` can return `[8, 5, 7]`. Do not compare results by position or against a sorted literal. Apply `Expr.list.sort` when order matters.

```python
import polars as pl

df = pl.DataFrame({"a": [[None, 3], [5, 6, 7]], "b": [[3, 4, None], [6, 8]]})
out = df.with_columns(
    diff=pl.col("a").list.set_difference("b"),
    inter=pl.col("a").list.set_intersection("b"),
    sdiff=pl.col("b").list.set_symmetric_difference("a"),
    sdiff_sorted=pl.col("b").list.set_symmetric_difference("a").list.sort(),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'a': [[None, 3], [5, 6, 7]], 'b': [[3, 4, None], [6, 8]], 'diff': [[], [5, 7]], 'inter': [[None, 3], [6]], 'sdiff': [[4], [8, 5, 7]], 'sdiff_sorted': [[4], [5, 7, 8]]}
```

## Use Expr.list.agg, not Expr.list.eval, to get a scalar per row

Applies to: `Expr.list.eval`, `Expr.list.agg`

`Expr.list.eval` does not automatically explode its result. An aggregation such as `pl.element().null_count()` inside it therefore returns a `List(UInt32)` column of one-element lists like `[[1], [0], [2]]` instead of a scalar column. Use `Expr.list.agg` when you want one scalar per row, because it automatically explodes the aggregated result and yields a plain `UInt32` column.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, None], [42, 13], [None, None]]})
out = df.with_columns(
    via_eval=pl.col("a").list.eval(pl.element().null_count()),
    via_agg=pl.col("a").list.agg(pl.element().null_count()),
)
print(out.to_dict(as_series=False))
print(out.schema)
```

Output:

```text
{'a': [[1, None], [42, 13], [None, None]], 'via_eval': [[1], [0], [2]], 'via_agg': [1, 0, 2]}
Schema({'a': List(Int64), 'via_eval': List(UInt32), 'via_agg': UInt32})
```

## Expr.list.explode turns empty and null lists into null rows

Applies to: `Expr.list.explode`

By default, `Expr.list.explode` uses `empty_as_null=True` and `keep_nulls=True`. An empty list and a null list each produce one null row instead of disappearing. Row counts and null counts after exploding are therefore higher than you might expect. Pass `empty_as_null=False` and `keep_nulls=False` to get only the actual elements.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, 2], [], None]})
default = df.select(pl.col("a").list.explode())
only_values = df.select(pl.col("a").list.explode(empty_as_null=False, keep_nulls=False))
print(default.to_dict(as_series=False))
print(default.height, only_values.height)
print(only_values.to_dict(as_series=False))
```

Output:

```text
{'a': [1, 2, None, None]}
4 2
{'a': [1, 2]}
```

## Expr.list.item errors unless every sublist has exactly one value

Applies to: `Expr.list.item`, `Expr.list.first`

`Expr.list.item` raises an error when any sublist does not have exactly one element. `allow_empty=True` only turns empty lists into null, and sublists with two or more elements still raise. Use `Expr.list.item` only when one element per list is a real invariant you want enforced. If you just want the leading value, use `Expr.list.first`.

```python
import polars as pl

df = pl.DataFrame({"a": [[3, 2], [1], []]})
try:
    df.select(pl.col("a").list.item(allow_empty=True))
except Exception as e:
    print(getattr(type(e), "__name__"))
ok = pl.DataFrame({"a": [[7], []]})
print(ok.select(pl.col("a").list.item(allow_empty=True)).to_dict(as_series=False))
print(df.select(first=pl.col("a").list.first()).to_dict(as_series=False))
```

Output:

```text
ComputeError
{'a': [7, None]}
{'first': [3, 1, None]}
```

## Set to_struct upper_bound from the real maximum list length or extra elements are silently dropped

Applies to: `Expr.list.to_struct`

Since 1.33.0, when `fields` is not a sequence of names, `upper_bound` is treated as ground truth for the number of struct fields. Elements beyond that width are dropped silently, with no error. Compute the widest list first, for example with `Expr.list.len` and `Expr.max`, and pass that as `upper_bound`. Alternatively, pass an explicit `fields=[...]` list. `n_field_strategy` is deprecated and ignored, so do not rely on `'max_width'` to size the struct.

```python
import polars as pl

df = pl.DataFrame({"n": [[0, 1], [0, 1, 2]]})

# Wrong: upper_bound too small, the trailing 2 is silently lost
truncated = df.select(s=pl.col("n").list.to_struct(upper_bound=2))
print(truncated.unnest("s").rows())

# Right: size the struct from the data
width = df.select(pl.col("n").list.len().max()).item()
full = df.select(s=pl.col("n").list.to_struct(upper_bound=width))
print(width, full.unnest("s").rows())

# Or name the fields explicitly
named = df.select(s=pl.col("n").list.to_struct(fields=["x", "y", "z"]))
print(named.unnest("s").columns)
```

Output:

```text
[(0, 1), (0, 1)]
3 [(0, 1, None), (0, 1, 2)]
['x', 'y', 'z']
```

## list.sort puts nulls first by default, even when descending

Applies to: `Expr.list.sort`

`Expr.list.sort` defaults to `nulls_last=False`, so nulls inside each list come first in both ascending and descending order. Code that sorts and then takes `Expr.list.first` to get the minimum gets null whenever a list contains a null. Pass `nulls_last=True`, or drop nulls first with `Expr.list.drop_nulls`.

```python
import polars as pl

df = pl.DataFrame({"a": [[3, None, 1], [2, 5, None]]})
out = df.select(
    default=pl.col("a").list.sort(),
    desc=pl.col("a").list.sort(descending=True),
    nulls_last=pl.col("a").list.sort(nulls_last=True),
    min_wrong=pl.col("a").list.sort().list.first(),
    min_right=pl.col("a").list.sort(nulls_last=True).list.first(),
)
for row in out.to_dicts():
    print(row)
```

Output:

```text
{'default': [None, 1, 3], 'desc': [None, 3, 1], 'nulls_last': [1, 3, None], 'min_wrong': None, 'min_right': 1}
{'default': [None, 2, 5], 'desc': [None, 5, 2], 'nulls_last': [2, 5, None], 'min_wrong': None, 'min_right': 2}
```

## Use list.tail for per-row slicing; Expr.tail takes the last rows of the column

Applies to: `Expr.list.tail`, `Expr.tail`

`pl.col("a").tail(2)` returns the last 2 rows of the column. It does not return the last 2 elements of each list, and its length no longer matches the frame. Use `Expr.list.tail` to slice inside every sublist. `n` may also be a string, which is read as a column name rather than a literal. That lets you supply a different `n` per row.

```python
import polars as pl

df = pl.DataFrame({"k": [1, 2, 3], "a": [[1, 2, 3], [4, 5], [6]]})

# Wrong: last two ROWS, height changes from 3 to 2
rows = df.select(pl.col("a").tail(2))
print(rows.height, rows.to_dicts())

# Right: last two elements of each list
print(df.with_columns(t=pl.col("a").list.tail(2)).to_dicts())

# A string n is a column name: per-row n taken from column k
print(df.with_columns(t=pl.col("a").list.tail("k")).to_dicts())
```

Output:

```text
2 [{'a': [4, 5]}, {'a': [6]}]
[{'k': 1, 'a': [1, 2, 3], 't': [2, 3]}, {'k': 2, 'a': [4, 5], 't': [4, 5]}, {'k': 3, 'a': [6], 't': [6]}]
[{'k': 1, 'a': [1, 2, 3], 't': [3]}, {'k': 2, 'a': [4, 5], 't': [4, 5]}, {'k': 3, 'a': [6], 't': [6]}]
```

## list.unique does not keep first-seen order unless maintain_order=True

Applies to: `Expr.list.unique`

pandas `unique` returns values in order of appearance. `Expr.list.unique` defaults to `maintain_order=False`, so the order of the distinct values is not guaranteed. Code that then takes `Expr.list.first` or compares lists across rows can give unstable results. Pass `maintain_order=True` for first-occurrence order, or chain `Expr.list.sort` for a canonical order.

```python
import polars as pl

df = pl.DataFrame({"a": [[3, 1, 3, 2, 1], [5, 5, 4]]})
out = df.select(
    first_seen=pl.col("a").list.unique(maintain_order=True),
    canonical=pl.col("a").list.unique().list.sort(),
)
for row in out.to_dicts():
    print(row)
```

Output:

```text
{'first_seen': [3, 1, 2], 'canonical': [1, 2, 3]}
{'first_seen': [5, 4], 'canonical': [4, 5]}
```

## list.sum returns 0, not null, for empty or all-null lists

Applies to: `Expr.list.sum`

SQL's `SUM` over no values gives NULL, but `Expr.list.sum` returns `0` when a row has no non-null elements. An empty list then looks the same as a list that really sums to zero, which skews downstream filters and averages. If you need SQL semantics, count the non-null elements with `Expr.list.drop_nulls` followed by `Expr.list.len`. Then null out the rows where that count is zero, for example with `Series.zip_with` (or `pl.when` inside an expression).

```python
import polars as pl

df = pl.DataFrame(
    {"v": [[1, 2], [], [None, None], [3, -3]]},
    schema={"v": pl.List(pl.Int64)},
)
out = df.select(
    naive=pl.col("v").list.sum(),
    has_vals=pl.col("v").list.drop_nulls().list.len() > 0,
)
naive = out.get_column("naive")
nulls = pl.Series([None] * out.height, dtype=naive.dtype)
sql_like = naive.zip_with(out.get_column("has_vals"), nulls)
# naive: 3, 0, 0, 0 -> cannot tell empty from a true zero
print(naive.to_list())
# sql_like: 3, None, None, 0
print(sql_like.to_list())
```

Output:

```text
[3, 0, 0, 0]
[3, None, None, 0]
```

## list.std and list.var default to sample statistics (ddof=1), not population

Applies to: `Expr.list.std`, `Expr.list.var`

`Expr.list.std` and `Expr.list.var` divide by `N - ddof` with `ddof=1` by default, which gives the sample estimate. NumPy's `std`/`var` default to `ddof=0`, so results ported from NumPy code will differ, especially for short lists. Pass `ddof=0` explicitly when you want the population statistic.

```python
import polars as pl

df = pl.DataFrame({"v": [[1, 2, 3, 4]]})
out = df.select(
    var_default=pl.col("v").list.var(),
    var_pop=pl.col("v").list.var(ddof=0),
    std_default=pl.col("v").list.std(),
    std_pop=pl.col("v").list.std(ddof=0),
)
# var_default = 5/3 (divides by N-1), var_pop = 1.25 (divides by N)
print(out.to_dicts())
```

Output:

```text
[{'var_default': 1.6666666666666667, 'var_pop': 1.25, 'std_default': 1.2909944487358056, 'std_pop': 1.118033988749895}]
```

## list.to_array needs an explicit width that every list matches; it does not pad or truncate

Applies to: `Expr.list.to_array`

`Expr.list.to_array` converts to a fixed-width `pl.Array`, and `width` is required rather than inferred. It does not truncate lists that are longer than `width`. In the example, a length-3 list with `width=2` raises a `ComputeError` at execution time instead of returning an Array. Normalise the lengths first, for example with `Expr.list.head`, or check `Expr.list.len` before converting.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, 2], [3, 4, 5]]})

try:
    df.select(pl.col("a").list.to_array(2))
except Exception as e:
    print(repr(e).split("(")[0])

fixed = df.select(pl.col("a").list.head(2).list.to_array(2))
print(fixed.schema)
print(fixed.rows())
```

Output:

```text
ComputeError
Schema({'a': Array(Int64, shape=(2,))})
[([1, 2],), ([3, 4],)]
```
