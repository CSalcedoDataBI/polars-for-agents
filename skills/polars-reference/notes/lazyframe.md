# LazyFrame: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## Filter drops rows whose predicate evaluates to null

Applies to: `LazyFrame.filter`, `Expr.ne_missing`, `Expr.is_null`

`LazyFrame.filter` keeps only rows where the predicate evaluates to True. Rows where it evaluates to `null` are discarded too. In Polars any comparison involving a null gives `null`, not boolean True or False, so `pl.col("a") != 1` silently drops the null rows as well. Use `Expr.ne_missing`, or add an explicit `| pl.col("a").is_null()`, when nulls must survive the filter.

```python
import polars as pl

lf = pl.LazyFrame({"a": [1, 2, None], "b": ["x", "y", "z"]})

# Wrong: the null row is dropped because null != 1 evaluates to null
wrong = lf.filter(pl.col("a") != 1).collect()
print(wrong["b"].to_list())

# Right: null-aware comparison keeps the null row
right = lf.filter(pl.col("a").ne_missing(1)).collect()
print(right["b"].to_list())

# Equivalent explicit form
also_right = lf.filter((pl.col("a") != 1) | pl.col("a").is_null()).collect()
print(also_right["b"].to_list())
```

Output:

```text
['y']
['y', 'z']
['y', 'z']
```

## NaN and null are different: drop_nulls/fill_null ignore NaN

Applies to: `LazyFrame.drop_nulls`, `LazyFrame.drop_nans`, `LazyFrame.fill_null`, `LazyFrame.fill_nan`

In pandas, NaN is the missing-value marker. In Polars, a floating-point NaN is a real value and is distinct from `null`. `LazyFrame.drop_nulls` and `LazyFrame.fill_null` leave NaN untouched. `LazyFrame.drop_nans` and `LazyFrame.fill_nan` only act on NaN. To treat both as missing, chain the two calls, or convert NaN to null first with `fill_nan(None)`.

```python
import polars as pl

lf = pl.LazyFrame({"x": [1.0, float("nan"), None]})

# drop_nulls keeps the NaN row
print(lf.drop_nulls().collect()["x"].to_list())
# Chain both to drop every kind of missing value
print(lf.drop_nulls().drop_nans().collect()["x"].to_list())

# fill_null does not touch NaN
print(lf.fill_null(0.0).collect()["x"].to_list())
# Convert NaN to null first, then fill everything
print(lf.fill_nan(None).fill_null(0.0).collect()["x"].to_list())
```

Output:

```text
[1.0, nan]
[1.0]
[1.0, nan, 0.0]
[1.0, 0.0, 0.0]
```

## LazyFrame.count counts non-null values per column, not rows

Applies to: `LazyFrame.count`, `pl.len`

`LazyFrame.count` returns a one-row frame holding the number of non-null elements in each column. It is not the number of rows: a column containing nulls reports fewer than the frame height. To get the row count, use `lf.select(pl.len())`.

```python
import polars as pl

lf = pl.LazyFrame({"a": [1, None, 3], "b": [None, None, 6]})

# Per-column non-null counts, NOT the row count
print(lf.count().collect().row(0))

# Actual number of rows
print(lf.select(pl.len()).collect().item())
```

Output:

```text
(2, 1)
3
```

## LazyFrame.describe collects eagerly and returns a DataFrame

Applies to: `LazyFrame.describe`, `LazyFrame.select`

Unlike most LazyFrame methods, `LazyFrame.describe` does not stay lazy. It runs the whole query and returns a `DataFrame`, which can be expensive on a large scan. Do not chain further lazy operations after it. Its output is also documented as not stable across versions, so do not parse it programmatically. For statistics you rely on in code, build explicit aggregations with `LazyFrame.select`.

```python
import polars as pl

lf = pl.LazyFrame({"a": [1, 2, 3], "b": [4.0, None, 6.0]})

summary = lf.describe()  # executes the query immediately
print(isinstance(summary, pl.DataFrame))

# Stable, lazy, programmatic statistics instead
stats = lf.select(
    pl.col("a").mean().alias("a_mean"),
    pl.col("b").null_count().alias("b_nulls"),
).collect()
print(stats.row(0))
```

Output:

```text
True
(2.0, 1)
```

## group_by does not preserve group order unless maintain_order=True

Applies to: `LazyFrame.group_by`

With the default `maintain_order=False`, `LazyFrame.group_by` does not guarantee that groups come out in any particular order, so tests and `head()` calls that assume an order can break. Pass `maintain_order=True` to keep the order consistent with the input (first appearance), or call `sort` on the result explicitly. Per the docstring, `maintain_order=True` is slower and blocks the possibility of running on the streaming engine.

```python
import polars as pl

lf = pl.LazyFrame({"k": ["b", "a", "b", "c"], "v": [1, 2, 3, 4]})

# Order of first appearance in the input
ordered = lf.group_by("k", maintain_order=True).agg(pl.col("v").sum()).collect()
print(ordered["k"].to_list())

# Or sort explicitly after an unordered group_by
sorted_out = lf.group_by("k").agg(pl.col("v").sum()).sort("k").collect()
print(sorted_out["k"].to_list(), sorted_out["v"].to_list())
```

Output:

```text
['b', 'a', 'c']
['a', 'b', 'c'] [2, 4, 4]
```

## join never matches null keys by default and does not guarantee row order

Applies to: `LazyFrame.join`

`LazyFrame.join` uses `nulls_equal=False` by default, so null keys never match each other. Rows keyed on null disappear from an inner join; pandas `merge` does match NaN keys. Set `nulls_equal=True` if nulls should match; this parameter was called `join_nulls` before 1.24. The default `maintain_order=None` does not promise any output order, so `sort` the result if order matters.

```python
import polars as pl

left = pl.LazyFrame({"k": [1, None], "l": ["x", "y"]})
right = pl.LazyFrame({"k": [1, None], "r": ["p", "q"]})

# Default: the null keys do not match
default = left.join(right, on="k").sort("l").collect()
print(default.height, default["r"].to_list())

# Opt in to matching nulls
matched = left.join(right, on="k", nulls_equal=True).sort("l").collect()
print(matched.height, matched["r"].to_list())
```

Output:

```text
1 ['p']
2 ['p', 'q']
```

## bottom_k output is unordered and the direction flag is reverse, not descending

Applies to: `LazyFrame.bottom_k`, `LazyFrame.top_k`, `LazyFrame.sort`

`LazyFrame.bottom_k` and `LazyFrame.top_k` return the selected rows in no guaranteed order. Call `LazyFrame.sort` afterwards if you need them ranked. To flip the direction, pass `reverse=True`. These methods have no `descending` keyword. Non-null values are always preferred over nulls, whatever the value of `reverse`.

```python
import polars as pl

lf = pl.LazyFrame({"name": ["a", "b", "c", "d"], "score": [5, None, 3, 2]})

# Sort explicitly to get a ranked result
low = lf.bottom_k(2, by="score").sort("score").collect()
print(low["name"].to_list())

# reverse=True picks the largest; the null score is never chosen
high = lf.bottom_k(2, by="score", reverse=True).sort("score", descending=True).collect()
print(high["name"].to_list())
```

Output:

```text
['d', 'c']
['a', 'c']
```

## fetch and approx_n_unique on LazyFrame are deprecated

Applies to: `LazyFrame.fetch`, `LazyFrame.approx_n_unique`, `LazyFrame.head`, `LazyFrame.collect`, `Expr.approx_n_unique`

`LazyFrame.fetch` is deprecated. Use `LazyFrame.head` followed by `LazyFrame.collect` instead, but note the two are not equivalent. `fetch` limited the rows read by every scan, so filters and joins could return fewer rows or none. `head` limits the final result. `LazyFrame.approx_n_unique` is also deprecated; use `lf.select(pl.all().approx_n_unique())` with `Expr.approx_n_unique`.

```python
import polars as pl

lf = pl.LazyFrame({"a": [1, 2, 2, 3], "b": [1, 1, 1, 1]})

# Replacement for lf.fetch(2): limit the final output, then collect
print(lf.head(2).collect().rows())

# Replacement for lf.approx_n_unique()
print(lf.select(pl.all().approx_n_unique()).collect().row(0))
```

Output:

```text
[(1, 1), (2, 1)]
(3, 1)
```

## LazyFrame.rolling windows are right-closed (t - period, t] by default

Applies to: `LazyFrame.rolling`

By default `LazyFrame.rolling` uses `closed='right'`, so each window is `(t - period, t]`. The left edge is excluded, which means `period="2i"` covers 2 index values, not 3. Pass `closed='both'` (or adjust `period`/`offset`) if you need both edges included. The `index_column` must be sorted ascending (within each group when `group_by` is set). The method returns a group-by object, so you must call `.agg(...)` on it.

```python
import polars as pl

lf = pl.LazyFrame({"t": [1, 2, 3, 4], "v": [1, 1, 1, 1]})

right = lf.rolling("t", period="2i").agg(pl.col("v").sum().alias("s"))
both = lf.rolling("t", period="2i", closed="both").agg(
    pl.col("v").sum().alias("s")
)

print(right.collect().sort("t")["s"].to_list())  # [1, 2, 2, 2]
print(both.collect().sort("t")["s"].to_list())   # [1, 2, 3, 3]
```

Output:

```text
[1, 2, 2, 2]
[1, 2, 3, 3]
```

## LazyFrame.quantile defaults to nearest interpolation, not linear

Applies to: `LazyFrame.quantile`

`LazyFrame.quantile` uses `interpolation='nearest'` by default, so it returns an actual data value rather than an interpolated one. For example, `quantile(0.7)` on `[1, 2, 3, 4]` gives `3.0`, while `interpolation='linear'` gives `3.1`. Code ported from tools that interpolate linearly by default, such as pandas, silently returns a different number. Pass `interpolation='linear'` explicitly when you expect linear quantiles.

```python
import polars as pl

lf = pl.LazyFrame({"a": [1, 2, 3, 4]})

nearest = lf.quantile(0.7).collect().item()
linear = lf.quantile(0.7, interpolation="linear").collect().item()

print(nearest)  # 3.0 (default: nearest)
print(round(linear, 6))  # 3.1 (pandas-style linear)
```

Output:

```text
3.0
3.1
```

## LazyFrame.remove keeps rows where the predicate is null

Applies to: `LazyFrame.remove`

`LazyFrame.remove` drops only rows where the predicate is exactly True. Rows where it evaluates to `null`, for example a comparison against a null value, are **retained**. This means `remove(cond)` is not the same as `LazyFrame.filter(~cond)`: the filter drops the null row and the remove keeps it. If null rows should also be discarded, add the null case explicitly, e.g. `cond | pl.col(c).is_null()`.

```python
import polars as pl

lf = pl.LazyFrame({"id": [1, 2, 3], "bar": [7, None, 1]})
cond = pl.col("bar") >= 5

# null comparison -> null -> row is kept by remove (ids 2 and 3)
print(lf.remove(cond).collect().get_column("id").to_list())

# filter on the negation drops the null row (only id 3)
print(lf.filter(~cond).collect().get_column("id").to_list())

# handle nulls explicitly to remove them too (only id 3)
print(lf.remove(cond | pl.col("bar").is_null()).collect().get_column("id").to_list())
```

Output:

```text
[2, 3]
[3]
[3]
```

## Declare the output schema and disable pushdown when a map_batches UDF changes columns or aggregates

Applies to: `LazyFrame.map_batches`

With `schema=None`, `LazyFrame.map_batches` assumes the function returns the same schema as its input. A UDF that adds columns therefore fails the default `validate_output_schema=True` check. `predicate_pushdown` defaults to True, so a later filter may be pushed past the UDF. The docstring warns that this changes the results of any aggregation done inside the UDF. Pass the real `schema=` and set `predicate_pushdown=False` when the function aggregates.

```python
import polars as pl

lf = pl.LazyFrame({"a": [1, 2, 3]})

def add_total(df):
    return df.with_columns(pl.col("a").sum().alias("total"))

try:
    lf.map_batches(add_total).collect()  # schema assumed unchanged
except Exception as e:
    print(type(e))

ok = lf.map_batches(
    add_total,
    schema={"a": pl.Int64, "total": pl.Int64},
    predicate_pushdown=False,
).filter(pl.col("a") > 1)
out = ok.collect()
# total is 6 on every remaining row
print(out.get_column("a").to_list(), out.get_column("total").to_list())
```

Output:

```text
<class 'polars.exceptions.ComputeError'>
[2, 3] [6, 6]
```

## merge_sorted does not sort: both inputs must already be ascending by the key

Applies to: `LazyFrame.merge_sorted`

`LazyFrame.merge_sorted` is a merge step, not a sort-and-concat. The caller must make sure both frames are sorted **ascending** by `key`; otherwise the docstring says the output will not make sense. The schemas of both frames must be equal, and row order among equal keys is not guaranteed. Call `.sort(key)` on both sides first, or use `pl.concat` followed by a sort.

```python
import polars as pl

a = pl.LazyFrame({"k": [3, 1], "v": ["a3", "a1"]})
b = pl.LazyFrame({"k": [2], "v": ["b2"]})

try:
    bad = a.merge_sorted(b, key="k").collect()  # inputs not sorted
    print(bad.get_column("k").to_list(), bad.get_column("k").is_sorted())
except Exception as e:
    print(type(e))

good = a.sort("k").merge_sorted(b.sort("k"), key="k").collect()
print(good.get_column("k").to_list(), good.get_column("k").is_sorted())
```

Output:

```text
[2, 3, 1] False
[1, 2, 3] True
```

## LazyFrame.pivot requires on_columns up front

Applies to: `LazyFrame.pivot`

`LazyFrame.pivot` has a required parameter `on_columns` that lists the values of `on` to turn into output columns. Eager-style calls that pass only `on`, `index` and `values` raise `TypeError`. With `aggregate_function=None`, a duplicate `index`/`on` combination raises an error. Because `maintain_order=False` is the default, the output row order is not guaranteed, so sort explicitly.

```python
import polars as pl

lf = pl.LazyFrame(
    {"name": ["a", "a", "b"], "subject": ["x", "y", "x"], "score": [1, 2, 3]}
)

try:
    lf.pivot(on="subject", index="name", values="score")
except TypeError:
    print("TypeError")

out = lf.pivot(on="subject", on_columns=["x", "y"], index="name", values="score")
print(out.collect().sort("name").to_dicts())
```

Output:

```text
TypeError
[{'name': 'a', 'x': 1, 'y': 2}, {'name': 'b', 'x': 3, 'y': None}]
```

## LazyFrame.melt is deprecated: use unpivot with index and on

Applies to: `LazyFrame.melt`, `LazyFrame.unpivot`

`LazyFrame.melt` is the pandas-style name and has been deprecated since 1.0.0; it emits a `DeprecationWarning`. Use `LazyFrame.unpivot` instead. The parameters are renamed: `id_vars` becomes `index` and `value_vars` becomes `on`. Passing the old keyword names to `LazyFrame.unpivot` will not work.

```python
import polars as pl
import warnings

lf = pl.LazyFrame({"id": [1, 2], "x": [10, 20], "y": [30, 40]})

with warnings.catch_warnings():
    warnings.simplefilter("error")
    try:
        lf.melt(id_vars="id", value_vars=["x", "y"])
    except DeprecationWarning:
        print("DeprecationWarning")

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    old = lf.melt(id_vars="id", value_vars=["x", "y"])

new = lf.unpivot(on=["x", "y"], index="id")
print(new.collect().to_dicts())
print(old.collect().equals(new.collect()))
```

Output:

```text
DeprecationWarning
[{'id': 1, 'variable': 'x', 'value': 10}, {'id': 2, 'variable': 'x', 'value': 20}, {'id': 1, 'variable': 'y', 'value': 30}, {'id': 2, 'variable': 'y', 'value': 40}]
True
```

## LazyFrame.serialize returns binary bytes by default, not JSON

Applies to: `LazyFrame.serialize`, `LazyFrame.deserialize`

The docstring summary mentions JSON, but the default is `format='binary'`, which returns `bytes`. The `'json'` format is deprecated. Read the result back with `LazyFrame.deserialize` wrapped in `io.BytesIO`. Serialized plans are not stable across Polars versions, so do not use them as a long-term storage format.

```python
import polars as pl
import io

lf = pl.LazyFrame({"a": [1, 2, 3]}).sum()

data = lf.serialize()
print(isinstance(data, bytes), isinstance(data, str))  # True False

restored = pl.LazyFrame.deserialize(io.BytesIO(data))
print(restored.collect().to_dicts())
```

Output:

```text
True False
[{'a': 6}]
```

## LazyFrame.update without `on` aligns rows by position and skips nulls

Applies to: `LazyFrame.update`

If `on` is omitted, `LazyFrame.update` joins on the *implicit row index*. Row 0 of `other` overwrites row 0 of the frame, key columns included, so an update meant to go by key is silently applied to the wrong rows. Nulls in `other` are also ignored by default (`include_nulls=False`), so you cannot clear a value unless you pass `include_nulls=True`. Always pass `on=` (or `left_on`/`right_on`). The API is marked unstable.

```python
import polars as pl

lf = pl.LazyFrame({"A": [1, 2, 3], "B": [10, 20, 30]})
new = pl.LazyFrame({"A": [2, 3], "B": [None, 99]})

# Wrong: no `on`, so rows are matched by position and column A is overwritten too
print(lf.update(new).collect().to_dicts())

# Right: match on the key; the null in `new` is ignored by default
print(lf.update(new, on="A").collect().to_dicts())

# To write the null through, opt in explicitly
print(lf.update(new, on="A", include_nulls=True).collect().to_dicts())
```

Output:

```text
[{'A': 2, 'B': 10}, {'A': 3, 'B': 99}, {'A': 3, 'B': 30}]
[{'A': 1, 'B': 10}, {'A': 2, 'B': 20}, {'A': 3, 'B': 99}]
[{'A': 1, 'B': 10}, {'A': 2, 'B': None}, {'A': 3, 'B': 99}]
```

## LazyFrame.unique keeps an arbitrary duplicate in arbitrary order by default

Applies to: `LazyFrame.unique`

pandas `drop_duplicates` keeps the first row and preserves order. `LazyFrame.unique` defaults to `keep='any'` and `maintain_order=False`, which guarantee neither which duplicate survives nor the output order. Pass `keep='first'` (or `'last'`) and `maintain_order=True` when either matters. pandas `keep=False` corresponds to `keep='none'`, which drops every duplicated row.

```python
import polars as pl

lf = pl.LazyFrame({"id": [1, 2, 1], "v": ["a", "b", "c"]})

# Default: only the row count is guaranteed, not which `v` is kept for id=1
print(lf.unique(subset="id").collect().height)

# pandas-like: keep the first occurrence, in original order
print(lf.unique(subset="id", keep="first", maintain_order=True).collect().to_dicts())

# pandas keep=False equivalent: drop every duplicated key
print(lf.unique(subset="id", keep="none").collect().to_dicts())
```

Output:

```text
2
[{'id': 1, 'v': 'a'}, {'id': 2, 'v': 'b'}]
[{'id': 2, 'v': 'b'}]
```

## LazyFrame.sort puts nulls first and is not stable by default

Applies to: `LazyFrame.sort`

`LazyFrame.sort` defaults to `nulls_last=False`, so nulls come *first*, even when `descending=True`. pandas habits expect missing values at the end. Ties are also not guaranteed to keep their input order unless `maintain_order=True`. Pass `nulls_last=True` and/or `maintain_order=True` explicitly when the order of nulls or ties matters.

```python
import polars as pl

lf = pl.LazyFrame({"a": [2, None, 1]})
print(lf.sort("a").collect().get_column("a").to_list())
print(lf.sort("a", descending=True).collect().get_column("a").to_list())
print(lf.sort("a", nulls_last=True).collect().get_column("a").to_list())

ties = pl.LazyFrame({"k": [1, 1, 0], "v": ["first", "second", "third"]})
# Stable sort: tied rows keep their input order
print(ties.sort("k", maintain_order=True).collect().get_column("v").to_list())
```

Output:

```text
[None, 1, 2]
[None, 2, 1]
[1, 2, None]
['third', 'first', 'second']
```

## LazyFrame.top_k output is unordered and uses `reverse`, not `descending`

Applies to: `LazyFrame.top_k`

`LazyFrame.top_k` returns the k largest rows in no particular order. Do not assume row 0 is the maximum; chain `LazyFrame.sort` if order matters. Since 1.0.0 the direction flag is `reverse` (renamed from `descending`), and `reverse=True` selects the k *smallest* rows. Non-null values are always preferred over nulls, whichever direction you use.

```python
import polars as pl

lf = pl.LazyFrame({"name": ["a", "b", "c", "d"], "score": [3, None, 5, 1]})

# Largest two, then sorted explicitly because top_k does not order its output
print(lf.top_k(2, by="score").sort("score", descending=True).collect().to_dicts())

# Smallest two: reverse=True; the null is still not picked
print(lf.top_k(2, by="score", reverse=True).sort("score").collect().to_dicts())
```

Output:

```text
[{'name': 'c', 'score': 5}, {'name': 'a', 'score': 3}]
[{'name': 'd', 'score': 1}, {'name': 'a', 'score': 3}]
```

## Replace deprecated LazyFrame.with_context with a horizontal pl.concat

Applies to: `LazyFrame.with_context`, `pl.concat`

`LazyFrame.with_context` is deprecated since 1.0.0. Use `pl.concat([...], how='horizontal')` to bring another frame's columns into scope. Rename the other frame's columns first (for example with `Expr.name.suffix`) so they do not collide with yours. Then compute aggregates such as `Expr.median` on the borrowed columns.

```python
import polars as pl

train = pl.LazyFrame({"x": [-1.0, 0.0, 1.0]})
test = pl.LazyFrame({"x": [-1.0, None, 5.0]})

both = pl.concat(
    [test, train.select(pl.all().name.suffix("_train"))], how="horizontal"
)
out = both.select(pl.col("x").fill_null(pl.col("x_train").median()))
print(out.collect().to_dicts())
```

Output:

```text
[{'x': -1.0}, {'x': 0.0}, {'x': 5.0}]
```

## LazyFrame.std and var default to sample statistics (ddof=1), unlike numpy

Applies to: `LazyFrame.std`, `LazyFrame.var`

`LazyFrame.std` and `LazyFrame.var` divide by N - 1 by default (`ddof=1`). That matches pandas but not numpy, whose default is population statistics (`ddof=0`). Porting numpy code without passing `ddof=0` silently changes the numbers. The results come back as `Float64`.

```python
import polars as pl

lf = pl.LazyFrame({"a": [1, 2, 3, 4]})
print(lf.std().collect().to_dicts())        # sample std, ddof=1
print(lf.std(ddof=0).collect().to_dicts())  # population std, numpy-style
print(lf.var().collect().to_dicts())
print(lf.var(ddof=0).collect().to_dicts())
```

Output:

```text
[{'a': 1.2909944487358056}]
[{'a': 1.118033988749895}]
[{'a': 1.6666666666666667}]
[{'a': 1.25}]
```

## with_row_count is deprecated and its column name changed to 'index'

Applies to: `LazyFrame.with_row_count`, `LazyFrame.with_row_index`

`LazyFrame.with_row_count` is deprecated; use `LazyFrame.with_row_index` instead. The default column name is now `index`, not `row_nr`, so downstream code that selects `row_nr` breaks unless you pass `name='row_nr'`. The `offset` cannot be negative and raises a `ValueError`. Adding a row index can block predicate pushdown, so add it as late in the query as possible.

```python
import polars as pl

lf = pl.LazyFrame({"a": [1, 3, 5]})
out = lf.with_row_index().collect()
print(out.columns)

# Keep old downstream code working by naming the column explicitly
print(lf.with_row_index("row_nr", offset=1).collect().to_dicts())

try:
    lf.with_row_index(offset=-1).collect()
except ValueError:
    print("negative offset rejected: ValueError")
```

Output:

```text
['index', 'a']
[{'row_nr': 1, 'a': 1}, {'row_nr': 2, 'a': 3}, {'row_nr': 3, 'a': 5}]
negative offset rejected: ValueError
```

## LazyFrame.unpivot uses `index`/`on`, not pandas `id_vars`/`value_vars`

Applies to: `LazyFrame.unpivot`

`LazyFrame.unpivot` does not take pandas-style `id_vars=` or `value_vars=` keywords. Pass the identifier columns as `index=` and the columns to unpivot as `on=`. If `on` is omitted (`None`, the default), every column not in `index` is unpivoted; an explicitly empty `on` unpivots no columns. The output columns are named `variable` and `value` unless you set `variable_name` and `value_name`.

```python
import polars as pl

lf = pl.LazyFrame({"id": ["x", "y"], "b": [1, 3], "c": [2, 4]})

# pandas id_vars -> index, value_vars -> on
out = lf.unpivot(on=["b", "c"], index="id").sort("id", "variable").collect()
print(out.to_dicts())

# Omitting on unpivots every non-index column
all_cols = lf.unpivot(index="id", variable_name="col", value_name="val")
print(all_cols.sort("id", "col").collect().to_dicts())
```

Output:

```text
[{'id': 'x', 'variable': 'b', 'value': 1}, {'id': 'x', 'variable': 'c', 'value': 2}, {'id': 'y', 'variable': 'b', 'value': 3}, {'id': 'y', 'variable': 'c', 'value': 4}]
[{'id': 'x', 'col': 'b', 'val': 1}, {'id': 'x', 'col': 'c', 'val': 2}, {'id': 'y', 'col': 'b', 'val': 3}, {'id': 'y', 'col': 'c', 'val': 4}]
```
