# DataFrame: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## Comparisons against null yield null, so `filter` silently drops those rows

Applies to: `DataFrame.filter`

`DataFrame.filter` keeps only rows where the predicate is True. A comparison with a null value gives null, not True or False, so the row is discarded. Pandas users expect `col != 'ok'` to keep missing values, because NaN != 'ok' is True there; in Polars those rows vanish without any warning. Use `Expr.ne_missing` / `Expr.eq_missing`, or add an explicit `| pl.col(...).is_null()` when nulls should be kept.

```python
import polars as pl

df = pl.DataFrame({"id": [1, 2, 3], "status": ["ok", None, "bad"]})

# Habit: "everything that is not ok" -- the null row is silently dropped
wrong = df.filter(pl.col("status") != "ok")
print(wrong["id"].to_list())  # [3]

# Null-aware comparison keeps the missing status
right = df.filter(pl.col("status").ne_missing("ok"))
print(right["id"].to_list())  # [2, 3]

# Equivalent explicit form
also = df.filter((pl.col("status") != "ok") | pl.col("status").is_null())
print(also["id"].to_list())  # [2, 3]
```

Output:

```text
[3]
[2, 3]
[2, 3]
```

## NaN and null are different values: the null methods ignore NaN and the NaN methods ignore null

Applies to: `DataFrame.drop_nulls`, `DataFrame.drop_nans`, `DataFrame.fill_null`, `DataFrame.fill_nan`

In pandas, NaN is the missing-value marker, so `dropna`/`fillna` remove it. In Polars, missing data is null. NaN is an ordinary floating-point value. `DataFrame.drop_nulls` and `DataFrame.fill_null` leave NaN untouched, and `DataFrame.fill_nan` leaves nulls untouched. To handle both, convert NaN to null first with `fill_nan(None)`, then apply the null method.

```python
import polars as pl

df = pl.DataFrame({"x": [1.0, float("nan"), None]})

# drop_nulls keeps the NaN row
print(df.drop_nulls()["x"].to_list())  # [1.0, nan]

# fill_null does not touch NaN, and fill_nan does not touch null
print(df.fill_null(0.0)["x"].to_list())  # [1.0, nan, 0.0]
print(df.fill_nan(0.0)["x"].to_list())   # [1.0, 0.0, None]

# Treat both as missing: NaN -> null, then fill nulls
print(df.fill_nan(None).fill_null(0.0)["x"].to_list())  # [1.0, 0.0, 0.0]
```

Output:

```text
[1.0, nan]
[1.0, nan, 0.0]
[1.0, 0.0, None]
[1.0, 0.0, 0.0]
```

## `group_by` output order is not guaranteed unless you ask for it

Applies to: `DataFrame.group_by`

Pandas `groupby` sorts the group keys by default, but `DataFrame.group_by` does not guarantee any group order. Code that takes the first row or zips the result against another list can therefore silently misalign. Pass `maintain_order=True` to get groups in input (first-appearance) order, which is slower and blocks the streaming engine, or call `.sort(...)` on the result. The order of rows within each group is always preserved, regardless of `maintain_order`.

```python
import polars as pl

df = pl.DataFrame({"k": ["b", "a", "b", "c"], "v": [1, 2, 3, 4]})

# Default df.group_by("k") gives groups in arbitrary order -- do not rely on it

# Order of first appearance
ordered = df.group_by("k", maintain_order=True).agg(pl.col("v").sum())
print(ordered.rows())  # [('b', 4), ('a', 2), ('c', 4)]

# Pandas-like sorted keys: sort explicitly
sorted_out = df.group_by("k").agg(pl.col("v").sum()).sort("k")
print(sorted_out.rows())  # [('a', 2), ('b', 4), ('c', 4)]
```

Output:

```text
[('b', 4), ('a', 2), ('c', 4)]
[('a', 2), ('b', 4), ('c', 4)]
```

## Most methods return a new frame, but `extend` and `drop_in_place` mutate the original

Applies to: `DataFrame.drop`, `DataFrame.drop_in_place`, `DataFrame.extend`

`DataFrame.drop` returns a new frame, so calling it without reassigning the result has no effect. Some methods do mutate the frame. `DataFrame.drop_in_place` removes the column from the frame and returns it as a Series. `DataFrame.extend` appends to the frame's own memory and returns the frame only for convenience. To keep the original unchanged, call `extend` on a `DataFrame.clone()`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
df.drop("b")  # result discarded: df is unchanged
print(df.columns)  # ['a', 'b']

s = df.drop_in_place("b")  # mutates df and returns the Series
print(s.name, df.columns)  # b ['a']

df1 = pl.DataFrame({"a": [1, 2]})
df2 = pl.DataFrame({"a": [3]})
combined = df1.clone().extend(df2)  # df1 untouched
print(df1.height, combined.height)  # 2 3

df1.extend(df2)  # mutates df1 in place
print(df1.height)  # 3
```

Output:

```text
['a', 'b']
b ['a']
2 3
3
```

## `bottom_k` skips nulls and returns unordered rows; `sort().head()` puts nulls first

Applies to: `DataFrame.bottom_k`

`DataFrame.bottom_k` always prefers non-null values, even with `reverse=True`. Its output is not guaranteed to be in any order, so call `.sort(...)` afterwards if order matters. `sort(...).head(k)` is not equivalent, because an ascending sort puts nulls first by default, so the null rows come out as the "smallest". The old `descending` parameter was renamed `reverse` in 1.0.0.

```python
import polars as pl

df = pl.DataFrame({"name": ["a", "b", "c", "d"], "score": [3, None, 1, 2]})

# sort + head: the null row counts as the smallest
print(df.sort("score").head(2).rows())  # [('b', None), ('c', 1)]

# bottom_k ignores nulls; sort the result because its order is unspecified
print(df.bottom_k(2, by="score").sort("score").rows())  # [('c', 1), ('d', 2)]

# reverse=True (formerly descending) gives the largest values, still no nulls
print(df.bottom_k(2, by="score", reverse=True).sort("score").rows())  # [('d', 2), ('a', 3)]
```

Output:

```text
[('b', None), ('c', 1)]
[('c', 1), ('d', 2)]
[('d', 2), ('a', 3)]
```

## `cast` is strict by default, and `strict=False` silently turns bad values into nulls

Applies to: `DataFrame.cast`

`DataFrame.cast` defaults to `strict=True`, so a single unparsable string or out-of-range value makes the whole cast raise an error. With `strict=False`, the cast succeeds and every invalid value becomes null without any warning. This can quietly corrupt aggregates later. If you use `strict=False`, check `Series.null_count` afterwards to see how many values were lost.

```python
import polars as pl

df = pl.DataFrame({"x": ["1", "2", "oops"]})

try:
    df.cast({"x": pl.Int64})
except Exception as e:
    print(type(e))

lenient = df.cast({"x": pl.Int64}, strict=False)
print(lenient["x"].to_list())     # [1, 2, None]
print(lenient["x"].null_count())  # 1 value silently lost
```

Output:

```text
<class 'polars.exceptions.InvalidOperationError'>
[1, 2, None]
1
```

## `drop` raises on missing columns unless `strict=False`

Applies to: `DataFrame.drop`

By default, `DataFrame.drop` checks that every named column exists and raises an error if any is missing. Defensive cleanup code such as "drop these columns if present" therefore fails on frames that lack one of them. Pass `strict=False` to ignore names that are not in the schema.

```python
import polars as pl

df = pl.DataFrame({"a": [1], "b": [2]})

try:
    df.drop("b", "c")
except Exception as e:
    print(type(e))

print(df.drop("b", "c", strict=False).columns)  # ['a']
```

Output:

```text
<class 'polars.exceptions.ColumnNotFoundError'>
['a']
```

## `DataFrame.approx_n_unique` is deprecated and only approximate

Applies to: `DataFrame.approx_n_unique`

`DataFrame.approx_n_unique` has been deprecated since 0.20.11 and emits a deprecation warning. Replace it with `DataFrame.select` combined with `Expr.approx_n_unique`, for example `df.select(pl.all().approx_n_unique())`. That method uses HyperLogLog++, so its result is an estimate. When you need an exact distinct count per column, use `Expr.n_unique` instead.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 3, 4], "b": [1, 2, 1, 1]})

# Replacement for the deprecated df.approx_n_unique()
approx = df.select(pl.all().approx_n_unique())
print(approx.to_dicts())

# Exact distinct counts per column
exact = df.select(pl.all().n_unique())
print(exact.to_dicts())  # [{'a': 4, 'b': 2}]
```

Output:

```text
[{'a': 4, 'b': 2}]
[{'a': 4, 'b': 2}]
```

## DataFrame.insert_column mutates the frame in place while DataFrame.hstack does not

Applies to: `DataFrame.insert_column`, `DataFrame.hstack`

Most Polars methods return a new frame, and `DataFrame.hstack` follows that rule unless you pass `in_place=True`. `DataFrame.insert_column` breaks the rule: its docstring says *this operation is in place*. It changes the original `df` as well as returning it. Call `DataFrame.clone` first if the original must stay untouched.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
out = df.hstack([pl.Series("c", [5, 6])])
print(df.columns, out.columns)  # df unchanged

df.insert_column(1, pl.Series("z", [0, 0]))
print(df.columns)  # df itself was modified

orig = pl.DataFrame({"a": [1, 2]})
safe = orig.clone()
safe.insert_column(0, pl.Series("idx", [10, 11]))
print(orig.columns, safe.columns)
```

Output:

```text
['a', 'b'] ['a', 'b', 'c']
['a', 'z', 'b']
['a'] ['idx', 'a']
```

## Null join keys never match unless nulls_equal=True

Applies to: `DataFrame.join`

By default `DataFrame.join` uses `nulls_equal=False`, so a null key on the left does not match a null key on the right. Inner joins silently drop those rows, and left joins leave the right-hand columns null. Pass `nulls_equal=True` when null keys should pair up. The old parameter name `join_nulls` was renamed to `nulls_equal` in 1.24.

```python
import polars as pl

left = pl.DataFrame({"k": [1, None], "x": ["a", "b"]})
right = pl.DataFrame({"k": [1, None], "y": ["A", "B"]})

default = left.join(right, on="k", how="left").sort("x")
matched = left.join(right, on="k", how="left", nulls_equal=True).sort("x")
print(default["y"].to_list())  # ['A', None]
print(matched["y"].to_list())  # ['A', 'B']

print(left.join(right, on="k").height)  # 1
print(left.join(right, on="k", nulls_equal=True).height)  # 2
```

Output:

```text
['A', None]
['A', 'B']
1
2
```

## DataFrame.is_duplicated flags every copy and has no subset argument

Applies to: `DataFrame.is_duplicated`, `DataFrame.is_unique`

`DataFrame.is_duplicated` and `DataFrame.is_unique` take no arguments, so there is no `subset` or `keep` option. They compare whole rows and mark **all** copies of a duplicated row, not just the later ones. To check only some columns, pack them with `pl.struct` and call `Expr.is_duplicated`. To flag only the later copies, use the negation of `Expr.is_first_distinct`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 1], "b": ["x", "y", "x"], "c": [9, 8, 7]})
print(df.is_duplicated().to_list())  # whole rows: all False

sub = df.select(pl.struct("a", "b").is_duplicated()).to_series()
print(sub.to_list())  # [True, False, True] - every copy

later = df.select(~pl.struct("a", "b").is_first_distinct()).to_series()
print(later.to_list())  # [False, False, True] - pandas keep='first'
```

Output:

```text
[False, False, False]
[True, False, True]
[False, False, True]
```

## DataFrame.n_unique counts unique rows, not unique values per column

Applies to: `DataFrame.n_unique`

`DataFrame.n_unique` does not return one count per column. It returns a single `int`: the number of distinct rows, or distinct row-subsets when you pass `subset`. For per-column counts, use `df.select(pl.all().n_unique())`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 1, 2], "b": ["x", "y", "x"]})
print(df.n_unique())  # 3 distinct rows
print(df.n_unique(subset="a"))  # 2
print(df.select(pl.all().n_unique()).to_dicts())  # per column
```

Output:

```text
3
2
[{'a': 2, 'b': 2}]
```

## DataFrame.pivot raises on duplicates unless aggregate_function is given

Applies to: `DataFrame.pivot`

With the default `aggregate_function=None`, `DataFrame.pivot` does no aggregation. It raises an error when one output cell would receive several values. Pass an aggregate such as `'sum'`, `'mean'`, `'first'` or `'len'` when the `index`/`on` combinations are not unique. Use `on=` rather than the old `columns=` name, and pass `index=` and `values=` as keywords.

```python
import polars as pl

df = pl.DataFrame({"id": [1, 1, 2], "k": ["p", "p", "q"], "v": [10, 20, 30]})
try:
    df.pivot(on="k", index="id", values="v")
except Exception as e:
    print(type(e))

out = df.pivot(on="k", index="id", values="v", aggregate_function="sum")
print(out.columns)
print(out.sort("id").rows())
```

Output:

```text
<class 'polars.exceptions.ComputeError'>
['id', 'p', 'q']
[(1, 30, 0), (2, 0, 30)]
```

## partition_by(as_dict=True) keys are tuples even for one column

Applies to: `DataFrame.partition_by`

With `as_dict=True`, `DataFrame.partition_by` uses tuples of the group values as dictionary keys, even when you partition by a single column. Looking up `parts['a']` raises `KeyError`; use `parts[('a',)]` instead. The key columns are kept in each part by default. Pass `include_key=False` to drop them.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "b", "a"], "v": [1, 2, 3]})
parts = df.partition_by("g", as_dict=True)
print(list(parts.keys()))
print("a" in parts, ("a",) in parts)
print(parts[("a",)]["v"].to_list())
print(parts[("a",)].columns)

no_key = df.partition_by("g", as_dict=True, include_key=False)
print(no_key[("b",)].columns)
```

Output:

```text
[('a',), ('b',)]
False True
[1, 3]
['g', 'v']
['v']
```

## DataFrame.melt is deprecated: use DataFrame.unpivot with index and on

Applies to: `DataFrame.melt`, `DataFrame.unpivot`

`DataFrame.melt` has been deprecated since 1.0.0. The replacement is `DataFrame.unpivot`, and its parameters are renamed: `id_vars` becomes `index` and `value_vars` becomes `on`. Do not copy pandas-style `melt(id_vars=..., value_vars=...)` calls; write `DataFrame.unpivot` from the start. `variable_name` and `value_name` still name the two output columns.

```python
import polars as pl

df = pl.DataFrame({"id": [1, 2], "x": [3, 4], "y": [5, 6]})
long = df.unpivot(
    index="id", on=["x", "y"], variable_name="var", value_name="val"
)
print(long.columns)
print(long.sort("id", "var").rows())
```

Output:

```text
['id', 'var', 'val']
[(1, 'x', 3), (1, 'y', 5), (2, 'x', 4), (2, 'y', 6)]
```

## DataFrame.max has no axis: use the *_horizontal methods for row-wise results

Applies to: `DataFrame.max`, `DataFrame.min`, `DataFrame.mean`, `DataFrame.max_horizontal`, `DataFrame.min_horizontal`, `DataFrame.mean_horizontal`

`DataFrame.max`, `DataFrame.min` and `DataFrame.mean` take no `axis` argument. They always aggregate down each column into a one-row frame. For row-wise results, use `DataFrame.max_horizontal`, `DataFrame.min_horizontal` or `DataFrame.mean_horizontal`, which return a **Series** (named `max`/`min`/`mean`), not a frame. `DataFrame.mean_horizontal` ignores nulls by default; pass `ignore_nulls=False` to make any null produce a null result. To add a row-wise column, use `pl.max_horizontal` inside `DataFrame.with_columns`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, None], "b": [4.0, 6.0]})
print(df.max().rows())  # one row: column-wise

row_max = df.max_horizontal()
print(row_max.name, row_max.to_list())  # Series named 'max'
print(df.mean_horizontal().to_list())  # nulls ignored
print(df.mean_horizontal(ignore_nulls=False).to_list())
out = df.with_columns(pl.max_horizontal("a", "b").alias("row_max"))
print(out.columns, out["row_max"].to_list())
```

Output:

```text
[(1, 6.0)]
max [4.0, 6.0]
[2.5, 6.0]
[2.5, None]
['a', 'b', 'row_max'] [4.0, 6.0]
```

## DataFrame.remove keeps rows whose predicate is null, so it is not the mirror of filter

Applies to: `DataFrame.remove`, `DataFrame.filter`

`DataFrame.remove` drops only rows where the predicate is exactly True. Rows where it evaluates to `null` are **retained**, and any comparison with a null value yields `null`. So `df.remove(pred)` and `df.filter(~pred)` give different results when the column contains nulls. If you want null rows gone too, add `| pl.col(c).is_null()` to the predicate, or fill the nulls first.

```python
import polars as pl

df = pl.DataFrame({"id": [1, 2, 3], "bar": [5, None, 1]})

# remove() keeps id=2 because (null >= 5) is null, not True
print(df.remove(pl.col("bar") >= 5)["id"].to_list())  # [2, 3]

# filter(~pred) drops the null row instead
print(df.filter(~(pl.col("bar") >= 5))["id"].to_list())  # [3]

# handle nulls explicitly to get the intended result
fixed = df.remove((pl.col("bar") >= 5) | pl.col("bar").is_null())
print(fixed["id"].to_list())  # [3]
```

Output:

```text
[2, 3]
[3]
[3]
```

## DataFrame.sort puts nulls first by default and does not guarantee a stable order for ties

Applies to: `DataFrame.sort`

`DataFrame.sort` has `nulls_last=False` by default, so nulls come out at the **top**. pandas habits expect missing values at the end. Pass `nulls_last=True` (a bool, or one bool per sort column) when you want them at the end. Also, `maintain_order=False` is the default, so the original order of tied rows is not guaranteed. Pass `maintain_order=True` when a later step depends on stable ordering.

```python
import polars as pl

df = pl.DataFrame({"a": [2, None, 1]})
print(df.sort("a")["a"].to_list())  # [None, 1, 2]
print(df.sort("a", nulls_last=True)["a"].to_list())  # [1, 2, None]
print(df.sort("a", descending=True, nulls_last=True)["a"].to_list())  # [2, 1, None]

ties = pl.DataFrame({"k": [1, 0, 1, 0], "pos": [0, 1, 2, 3]})
# stable sort: tied rows keep their original relative order
print(ties.sort("k", maintain_order=True)["pos"].to_list())  # [1, 3, 0, 2]
```

Output:

```text
[None, 1, 2]
[1, 2, None]
[2, 1, None]
[1, 3, 0, 2]
```

## DataFrame.replace_column mutates the frame in place

Applies to: `DataFrame.replace_column`, `DataFrame.with_columns`

Almost every DataFrame method returns a new frame, but the docstring of `DataFrame.replace_column` states that it operates **in place**. The original `df` is changed even if you assign the result to a new variable. Any other reference to that frame, such as a cached input or a function argument, sees the change too. Prefer `DataFrame.with_columns` with a same-named Series or expression, which returns a new frame. Alternatively, call `DataFrame.clone` first if you really need positional replacement.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
backup = df.clone()

out = df.replace_column(0, pl.Series("z", [9, 9]))
print(df.columns)  # ['z', 'b']  original df was mutated
print(out.columns)  # ['z', 'b']

# non-mutating alternative: replace by name, get a new frame
safe = backup.with_columns(pl.Series("a", [9, 9]))
print(backup["a"].to_list())  # [1, 2]  untouched
print(safe["a"].to_list())  # [9, 9]
```

Output:

```text
['z', 'b']
['z', 'b']
[1, 2]
[9, 9]
```

## DataFrame.slice takes (offset, length), not (start, stop)

Applies to: `DataFrame.slice`, `DataFrame.tail`

`DataFrame.slice(offset, length)` uses a **length** as its second argument. Code translated from Python slicing or pandas `iloc[start:stop]` that passes a stop index returns too many rows. Compute `stop - start` for the length. Leaving `length=None` takes everything from the offset onward, and negative offsets count from the end. Also, `DataFrame.tail` with a negative `n` returns all rows *except* the first `abs(n)`, not the last `n`.

```python
import polars as pl

df = pl.DataFrame({"i": [0, 1, 2, 3, 4]})

print(df.slice(1, 3)["i"].to_list())  # [1, 2, 3]  3 rows, not rows 1..2

start, stop = 1, 3
print(df.slice(start, stop - start)["i"].to_list())  # [1, 2]

print(df.slice(-2)["i"].to_list())  # [3, 4]
print(df.tail(-3)["i"].to_list())  # [3, 4]  all except first 3
```

Output:

```text
[1, 2, 3]
[1, 2]
[3, 4]
[3, 4]
```

## DataFrame.rows_by_key with unique=True silently keeps only the last duplicate

Applies to: `DataFrame.rows_by_key`

By default `DataFrame.rows_by_key` groups rows into a list per key, and the key column is omitted from the values (`include_key=False`). Passing `unique=True` gives a 1:1 mapping. If the key is not actually unique, it **silently returns the last row** for that key instead of raising. Verify uniqueness first, for example by comparing `Series.n_unique` to `DataFrame.height`, before relying on `unique=True`.

```python
import polars as pl

df = pl.DataFrame({"x": ["a", "b", "b", "a"], "y": [1, 2, 3, 4]})

print(dict(df.rows_by_key("x")))  # lists of rows per key, key omitted
print(df.rows_by_key("x", unique=True))  # only the LAST row per key survives

print(df["x"].n_unique() == df.height)  # False -> unique=True would lose data
print(dict(df.rows_by_key("x", named=True, include_key=True)))
```

Output:

```text
{'a': [(1,), (4,)], 'b': [(2,), (3,)]}
{'a': (4,), 'b': (3,)}
False
{'a': [{'x': 'a', 'y': 1}, {'x': 'a', 'y': 4}], 'b': [{'x': 'b', 'y': 2}, {'x': 'b', 'y': 3}]}
```

## DataFrame.rolling windows are right-closed (t - period, t] and need a sorted index

Applies to: `DataFrame.rolling`

By default each `DataFrame.rolling` window is `(t - period, t]` because `closed='right'`. The value exactly `period` before `t` is **excluded**, which surprises anyone expecting an inclusive lookback. Pass `closed="both"` (or `"left"`/`"none"`) to choose explicitly. The `index_column` must be sorted ascending, or sorted within each group when `group_by` is used. The old `by` parameter was renamed to `group_by`.

```python
import polars as pl

df = pl.DataFrame({"t": [1, 2, 3, 4], "v": [1, 10, 100, 1000]})

right = df.rolling("t", period="2i").agg(pl.col("v").sum().alias("s"))
both = df.rolling("t", period="2i", closed="both").agg(
    pl.col("v").sum().alias("s")
)

print(right["s"].to_list())  # [1, 11, 110, 1100]  window (t-2, t]
print(both["s"].to_list())  # [1, 11, 111, 1110]  window [t-2, t]
```

Output:

```text
[1, 11, 110, 1100]
[1, 11, 111, 1110]
```

## DataFrame.sum_horizontal silently ignores nulls, unlike `a + b`

Applies to: `DataFrame.sum_horizontal`

`DataFrame.sum_horizontal` defaults to `ignore_nulls=True`, so a row containing a null still gets the sum of its remaining values. In contrast, `pl.col("a") + pl.col("b")` returns null for that row. Pass `ignore_nulls=False` if a missing input should make the total missing. The method returns a `Series` named `"sum"`, not a DataFrame, so attach it with `DataFrame.with_columns` under a proper name.

```python
import polars as pl

df = pl.DataFrame({"a": [1, None], "b": [10, 20]})

print(df.sum_horizontal().to_list())  # [11, 20]  null treated as absent
print(df.sum_horizontal(ignore_nulls=False).to_list())  # [11, None]
print(df.select((pl.col("a") + pl.col("b")).alias("t"))["t"].to_list())  # [11, None]

s = df.sum_horizontal()
print(isinstance(s, pl.Series), s.name)  # True sum
print(df.with_columns(total=df.sum_horizontal(ignore_nulls=False)).to_dicts())
```

Output:

```text
[11, 20]
[11, None]
[11, None]
True sum
[{'a': 1, 'b': 10, 'total': 11}, {'a': None, 'b': 20, 'total': None}]
```

## DataFrame.quantile defaults to 'nearest' interpolation, not linear

Applies to: `DataFrame.quantile`

`DataFrame.quantile` uses `interpolation='nearest'` by default, so it returns an existing data value instead of interpolating between neighbours. If you expect linear interpolation, a median computed with `DataFrame.quantile(0.5)` can differ from what you expect. Pass `interpolation="linear"` explicitly to interpolate. Non-numeric columns are not dropped: they come back as `null` in the result row.

```python
import polars as pl

df = pl.DataFrame({"x": [1, 2, 3, 4], "s": ["a", "b", "c", "d"]})

nearest = df.quantile(0.5)  # default interpolation='nearest'
linear = df.quantile(0.5, interpolation="linear")

print(nearest.to_dicts())  # x is an existing value, s is None
print(linear["x"].item())  # 2.5
print(nearest["x"].item() == linear["x"].item())  # False
```

Output:

```text
[{'x': 3.0, 's': None}]
2.5
False
```

## Expressions in one with_columns call cannot see each other, and nothing happens in place

Applies to: `DataFrame.with_columns`, `DataFrame.with_columns_seq`

All expressions passed to a single `DataFrame.with_columns` call are evaluated against the *input* frame, so a sibling expression that references a column created in the same call raises `ColumnNotFoundError`. `DataFrame.with_columns_seq` differs only in running the expressions sequentially instead of in parallel; use it when the work per expression is cheap, not as a way to reference sibling columns. Both methods return a new DataFrame, so calling them without reassigning silently does nothing. Chain a second `DataFrame.with_columns` call for dependent columns and always reassign the result.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 3]})
try:
    df.with_columns(b=pl.col("a") * 2, c=pl.col("b") + 1)
except Exception as e:
    print(type(e))

df.with_columns(b=pl.col("a") * 10)  # result discarded
print(df.columns)

out = df.with_columns(b=pl.col("a") * 2).with_columns(c=pl.col("b") + 1)
print(out.columns)
print(out.rows())
```

Output:

```text
<class 'polars.exceptions.ColumnNotFoundError'>
['a']
['a', 'b', 'c']
[(1, 2, 3), (2, 4, 5), (3, 6, 7)]
```

## update joins on row position by default and ignores nulls from the other frame

Applies to: `DataFrame.update`

`DataFrame.update` is unstable. With `on=None`, the default, it uses the implicit row index of each frame as the join key, not any key column. This can overwrite your key column with values from unrelated rows, so always pass `on=` (or `left_on`/`right_on`). With the default `include_nulls=False`, nulls in `other` are skipped rather than written. Pass `include_nulls=True` if a null is meant to clear the value.

```python
import polars as pl

df = pl.DataFrame({"A": [1, 2, 3, 4], "B": [400, 500, 600, 700]})
new = pl.DataFrame({"A": [3, 2], "B": [0, None]})

print(df.update(new).rows())  # positional: A in row 0 becomes 3
print(df.update(new, on="A")["B"].to_list())
print(df.update(new, on="A", include_nulls=True)["B"].to_list())
```

Output:

```text
[(3, 0), (2, 500), (3, 600), (4, 700)]
[400, 500, 0, 700]
[400, None, 0, 700]
```

## unique keeps an arbitrary duplicate and drops row order by default

Applies to: `DataFrame.unique`

`DataFrame.unique` defaults to `keep='any'` and `maintain_order=False`. Which duplicate survives is not guaranteed, and neither is the output row order. Pass `keep='first'` or `keep='last'` together with `maintain_order=True` when the surviving row or the row order matters. `keep='none'` removes every row that has a duplicate. The method fails if a `List` column is part of the rows or the `subset`.

```python
import polars as pl

df = pl.DataFrame({"k": ["b", "a", "b", "a"], "v": [1, 2, 3, 4]})

print(df.unique(subset="k").height)  # which v survives is not guaranteed
print(df.unique(subset="k", keep="first", maintain_order=True).rows())
print(df.unique(subset="k", keep="last", maintain_order=True).rows())
print(df.unique(subset="k", keep="none").height)
```

Output:

```text
2
[('b', 1), ('a', 2)]
[('b', 3), ('a', 4)]
0
```

## top_k output is unordered and uses reverse, not descending

Applies to: `DataFrame.top_k`, `DataFrame.bottom_k`

`DataFrame.top_k` returns the k largest rows in no particular order, so taking the first row as the maximum is a bug. Call `DataFrame.sort` on the result if order matters. The parameter for picking the smallest values is `reverse`; `descending` was renamed in 1.0.0. Non-null values are always preferred over nulls, whatever `reverse` is set to, so nulls are not selected while enough non-null values exist.

```python
import polars as pl

df = pl.DataFrame({"name": ["a", "b", "c", "d", "e"], "score": [3, None, 1, 5, 4]})

top = df.top_k(3, by="score")
print(sorted(top["score"].to_list()))
print(top.sort("score", descending=True).rows())

low = df.top_k(2, by="score", reverse=True).sort("score")
print(low["score"].to_list())  # nulls not picked as smallest
print(df.bottom_k(2, by="score").sort("score")["score"].to_list())
```

Output:

```text
[3, 4, 5]
[('d', 5), ('e', 4), ('a', 3)]
[1, 3]
[1, 3]
```

## unpivot uses on/index instead of value_vars/id_vars, and the first positional argument is on

Applies to: `DataFrame.unpivot`, `DataFrame.melt`

Coming from pandas `melt`, use `index` in place of `id_vars` and `on` in place of `value_vars`. The first positional argument of `DataFrame.unpivot` is `on`, so `df.unpivot("id")` unpivots the id column itself and drops everything else instead of keeping it as the identifier. Pass `on=` and `index=` by keyword. The resulting row order is unspecified, so sort the output if you depend on it.

```python
import polars as pl

df = pl.DataFrame({"id": ["x", "y"], "b": [1, 3], "c": [2, 4]})

wrong = df.unpivot("id")  # 'id' is treated as `on`
print(wrong.columns, wrong["variable"].unique().to_list())

right = df.unpivot(on=["b", "c"], index="id").sort("id", "variable")
print(right.columns)
print(right.rows())
```

Output:

```text
['variable', 'value'] ['id']
['id', 'variable', 'value']
[('x', 'b', 1), ('x', 'c', 2), ('y', 'b', 3), ('y', 'c', 4)]
```

## with_row_count is deprecated and its replacement uses a different default column name

Applies to: `DataFrame.with_row_count`, `DataFrame.with_row_index`

`DataFrame.with_row_count` is deprecated; use `DataFrame.with_row_index`. The default column name changed from `row_nr` to `index`. Code that later selects `pl.col("row_nr")` breaks unless you pass the name explicitly. The result is an ordinary `UInt32` column, not a pandas-style index, and `offset` cannot be negative.

```python
import polars as pl

df = pl.DataFrame({"a": [10, 20, 30]})

print(df.with_row_index().columns)  # default name is 'index'

legacy = df.with_row_index("row_nr", offset=1)
print(legacy.columns)
print(legacy.rows())
print(legacy.schema["row_nr"])
```

Output:

```text
['index', 'a']
['row_nr', 'a']
[(1, 10), (2, 20), (3, 30)]
UInt32
```

## upsample needs a sorted time column and leaves inserted rows null

Applies to: `DataFrame.upsample`

`DataFrame.upsample` only produces meaningful output if `time_column` is sorted, so sort it first. Inserted rows get nulls in every other column, including grouping columns, unless those columns are passed via `group_by` (formerly `by`). Fill the value columns afterwards, for example with `Expr.forward_fill`. With `group_by`, the result is sorted only within each group; pass `maintain_order=True` for a predictable order.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({
    "time": [datetime(2021, 1, 1), datetime(2021, 3, 1), datetime(2021, 4, 1)],
    "grp": ["A", "A", "A"],
    "v": [1, 2, 3],
}).sort("time")

up = df.upsample(time_column="time", every="1mo")
print(up["grp"].to_list(), up["v"].to_list())  # null in Feb

filled = df.upsample(
    time_column="time", every="1mo", group_by="grp", maintain_order=True
).with_columns(pl.col("v").forward_fill())
print(filled["grp"].to_list(), filled["v"].to_list())
```

Output:

```text
['A', None, 'A', 'A'] [1, None, 2, 3]
['A', 'A', 'A', 'A'] [1, 1, 2, 3]
```
