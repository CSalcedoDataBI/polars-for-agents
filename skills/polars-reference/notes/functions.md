# functions: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## pl.concat_list returns null for the whole row if any input is null, and upcasts to a supertype

Applies to: `pl.concat_list`

`pl.concat_list` propagates nulls. If any input list in a row is null, the whole concatenated list for that row is null, not the other lists joined together. The output dtype is also the supertype of all inputs, so mixing an integer list with a string literal turns every element into a string. Handle null inputs explicitly, for example with `pl.when` on `Expr.is_null`, and cast inputs to a common dtype yourself.

```python
import polars as pl

df = pl.DataFrame({"a": [[1, 2], [3]], "b": [[4], None]})
out = df.with_columns(
    naive=pl.concat_list("a", "b"),
    safe=pl.when(pl.col("b").is_null())
    .then(pl.col("a"))
    .otherwise(pl.concat_list("a", "b")),
)
print(out)
print(df.select(pl.concat_list("a", pl.lit("x"))).dtypes)
```

Output:

```text
shape: (2, 4)
┌───────────┬───────────┬───────────┬───────────┐
│ a         ┆ b         ┆ naive     ┆ safe      │
│ ---       ┆ ---       ┆ ---       ┆ ---       │
│ list[i64] ┆ list[i64] ┆ list[i64] ┆ list[i64] │
╞═══════════╪═══════════╪═══════════╪═══════════╡
│ [1, 2]    ┆ [4]       ┆ [1, 2, 4] ┆ [1, 2, 4] │
│ [3]       ┆ null      ┆ null      ┆ [3]       │
└───────────┴───────────┴───────────┴───────────┘
[List(String)]
```

## pl.cum_count counts non-null values, not rows

Applies to: `pl.cum_count`

pandas `cumcount` numbers rows, but `pl.cum_count` is the cumulative count of non-null values. On a null the counter does not advance, so it repeats the previous number. To get a running row number, use `pl.int_range` over `pl.len()` instead.

```python
import polars as pl

df = pl.DataFrame({"a": [1, None, 3, None]})
out = df.with_columns(
    cc=pl.cum_count("a"),
    row_no=pl.int_range(1, pl.len() + 1),
)
print(out)
```

Output:

```text
shape: (4, 3)
┌──────┬─────┬────────┐
│ a    ┆ cc  ┆ row_no │
│ ---  ┆ --- ┆ ---    │
│ i64  ┆ u32 ┆ i64    │
╞══════╪═════╪════════╡
│ 1    ┆ 1   ┆ 1      │
│ null ┆ 1   ┆ 2      │
│ 3    ┆ 2   ┆ 3      │
│ null ┆ 2   ┆ 4      │
└──────┴─────┴────────┘
```

## String arguments to pl.format are column names, not literal text

Applies to: `pl.format`

In `pl.format`, each positional argument after the template fills a `{}` placeholder, and plain strings are parsed as column names. Passing a word you meant as literal text fails because no column has that name. Wrap literal text in `pl.lit`, or put it directly into the template string.

```python
import polars as pl

df = pl.DataFrame({"a": ["x", "y"], "b": [1, 2]})
try:
    df.select(pl.format("{}-{}", "a", "units"))
except Exception as e:
    print(type(e).__name__)
print(df.select(pl.format("{}-{}", "a", pl.lit("units")).alias("fmt")))
print(df.select(pl.format("{}_{}", "a", "b").alias("fmt")))
```

Output:

```text
ColumnNotFoundError
shape: (2, 1)
┌─────────┐
│ fmt     │
│ ---     │
│ str     │
╞═════════╡
│ x-units │
│ y-units │
└─────────┘
shape: (2, 1)
┌─────┐
│ fmt │
│ --- │
│ str │
╞═════╡
│ x_1 │
│ y_2 │
└─────┘
```

## pl.fold result dtype follows the accumulator, so pl.lit(0) gives Int32

Applies to: `pl.fold`, `pl.cum_fold`

When `return_dtype` is not set, `pl.fold` and `pl.cum_fold` infer the output dtype from the accumulator. A bare `pl.lit(0)` or `pl.lit(1)` is Int32, so a horizontal sum of Int64 columns comes back as Int32. Give the accumulator an explicit dtype with `pl.lit(0, dtype=pl.Int64)`, or pass `return_dtype`. For plain horizontal sums, prefer `pl.sum_horizontal`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
out = df.select(
    i32=pl.fold(acc=pl.lit(0), function=lambda acc, x: acc + x, exprs=pl.all()),
    i64=pl.fold(
        acc=pl.lit(0, dtype=pl.Int64), function=lambda acc, x: acc + x, exprs=pl.all()
    ),
    builtin=pl.sum_horizontal("a", "b"),
)
print(out.schema)
print(out)
```

Output:

```text
Schema({'i32': Int32, 'i64': Int64, 'builtin': Int64})
shape: (2, 3)
┌─────┬─────┬─────────┐
│ i32 ┆ i64 ┆ builtin │
│ --- ┆ --- ┆ ---     │
│ i32 ┆ i64 ┆ i64     │
╞═════╪═════╪═════════╡
│ 4   ┆ 4   ┆ 4       │
│ 6   ┆ 6   ┆ 6       │
└─────┴─────┴─────────┘
```

## pl.from_dict is strict by default; strict=False turns uncastable values into null

Applies to: `pl.from_dict`

With the default `strict=True`, `pl.from_dict` raises if any value does not exactly match the given or inferred column dtype. Setting `strict=False` does not keep the odd values. They are cast to the column dtype, or silently set to null when casting is impossible. If you use `strict=False`, check `DataFrame.null_count` afterwards so lost data does not go unnoticed.

```python
import polars as pl

data = {"a": [1, "x", 3]}
try:
    pl.from_dict(data, schema={"a": pl.Int64})
except Exception as e:
    print(type(e).__name__)
df = pl.from_dict(data, schema={"a": pl.Int64}, strict=False)
print(df)
print(df.null_count())
```

Output:

```text
TypeError
shape: (3, 1)
┌──────┐
│ a    │
│ ---  │
│ i64  │
╞══════╡
│ 1    │
│ null │
│ 3    │
└──────┘
shape: (1, 1)
┌─────┐
│ a   │
│ --- │
│ u32 │
╞═════╡
│ 1   │
└─────┘
```

## pl.arctan2d is deprecated; use pl.arctan2 then Expr.degrees

Applies to: `pl.arctan2d`, `pl.arctan2`

`pl.arctan2d` has been deprecated since 1.0.0 and emits a deprecation warning. `pl.arctan2` returns radians, so do not mix the two up. For degrees, chain `pl.arctan2(...)` with `Expr.degrees`. Note that the argument order is `(y, x)`.

```python
import polars as pl

c = (2**0.5) / 2
df = pl.DataFrame({"y": [c, -c], "x": [c, -c]})
out = df.select(
    radians=pl.arctan2("y", "x"),
    degrees=pl.arctan2("y", "x").degrees(),
)
print(out)
```

Output:

```text
shape: (2, 2)
┌───────────┬─────────┐
│ radians   ┆ degrees │
│ ---       ┆ ---     │
│ f64       ┆ f64     │
╞═══════════╪═════════╡
│ 0.785398  ┆ 45.0    │
│ -2.356194 ┆ -135.0  │
└───────────┴─────────┘
```

## pl.concat_str returns null for the whole row if any input is null

Applies to: `pl.concat_str`

By default `pl.concat_str` uses `ignore_nulls=False`, so a single null in any input column makes the entire concatenated string null. This is not how Python string joining behaves. Pass `ignore_nulls=True` to skip null parts.

```python
import polars as pl

df = pl.DataFrame({"first": ["Ann", "Bob"], "middle": [None, "J"], "last": ["Lee", "Kim"]})
out = df.select(
    default=pl.concat_str("first", "middle", "last", separator=" "),
    skip_nulls=pl.concat_str("first", "middle", "last", separator=" ", ignore_nulls=True),
)
print(out["default"].to_list())
print(out["skip_nulls"].to_list())
```

Output:

```text
[None, 'Bob J Kim']
['Ann Lee', 'Bob J Kim']
```

## pl.count counts non-null values, not rows; use pl.len for row counts

Applies to: `pl.count`, `pl.len`

`pl.count("a")` is sugar for `pl.col("a").count()` and returns the number of **non-null** values, not the number of rows. Calling `pl.count()` with no arguments to get a row count is deprecated. Use `pl.len()` when you mean the number of rows, the equivalent of SQL `COUNT(*)`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, None, 3]})
out = df.select(non_null=pl.count("a"), rows=pl.len())
print(out.columns, out.rows())
```

Output:

```text
['non_null', 'rows'] [(2, 3)]
```

## pl.all with column names aggregates instead of selecting, and skips nulls by default

Applies to: `pl.all`, `pl.any`

`pl.all()` with no arguments selects every column. `pl.all("a")` does **not** select column `a`. It is sugar for `pl.col("a").all()` and collapses the column to a single boolean. `pl.all` and `pl.any` also default to `ignore_nulls=True`, so an all-null column gives `True` for `pl.all` and `False` for `pl.any`. To select a column use `pl.col`, and pass `ignore_nulls=False` to get Kleene (null-propagating) logic.

```python
import polars as pl

df = pl.DataFrame(
    {"a": [True, None], "b": [None, None]},
    schema={"a": pl.Boolean, "b": pl.Boolean},
)
print(df.select(pl.all()).shape)  # all columns, 2 rows
print(df.select(pl.all("a")).shape)  # aggregated, 1 row
print(df.select(pl.all("b")).item())  # all-null column -> True
print(df.select(pl.any("b")).item())  # all-null column -> False
print(df.select(pl.all("a", "b", ignore_nulls=False)).rows())  # Kleene -> None
```

Output:

```text
(2, 2)
(1, 1)
True
False
[(None, None)]
```

## Null results from pl.all_horizontal/pl.any_horizontal make rows vanish from filters

Applies to: `pl.all_horizontal`, `pl.any_horizontal`

`pl.all_horizontal` and `pl.any_horizontal` use Kleene logic, so a row whose result is undetermined (`True AND null`, `False OR null`) becomes null rather than `False`. A filter drops null rows, and negating null is still null. Such rows therefore disappear from both `DataFrame.filter(cond)` and `DataFrame.filter(~cond)`. Call `Expr.fill_null(False)` (or `True`) on the condition if every row must land on one side.

```python
import polars as pl

df = pl.DataFrame({"id": [1, 2, 3], "x": [True, True, False], "y": [True, None, True]})
cond = pl.all_horizontal("x", "y")
print(df.select(cond).to_series().to_list())
print(df.filter(cond).height, df.filter(~cond).height)  # 1 + 1, row 2 lost
safe = cond.fill_null(False)
print(df.filter(safe).height, df.filter(~safe).height)  # 1 + 2
```

Output:

```text
[True, None, False]
1 1
1 2
```

## pl.coalesce skips nulls but keeps NaN, and literals can change the dtype

Applies to: `pl.coalesce`

`pl.coalesce` keeps the first **non-null** value. In Polars, `NaN` is a valid float value, not a missing one, so a `NaN` wins over a later fallback. Convert NaN to null first with `Expr.fill_nan(None)`. Also, the output dtype is the supertype of all inputs, so a float fallback literal such as `0.0` turns an integer column into `Float64`.

```python
import polars as pl

df = pl.DataFrame({"a": [float("nan"), None, 1.0], "b": [10.0, 20.0, 30.0]})
out = df.with_columns(
    naive=pl.coalesce("a", "b"),
    fixed=pl.coalesce(pl.col("a").fill_nan(None), "b"),
)
print(out["naive"].to_list())
print(out["fixed"].to_list())
ints = pl.DataFrame({"i": [None, 2]})
print(ints.select(pl.coalesce("i", 0.0)).dtypes)
```

Output:

```text
[nan, 20.0, 1.0]
[10.0, 20.0, 1.0]
[Float64]
```

## Range functions return expressions by default, and endpoint inclusion differs

Applies to: `pl.arange`, `pl.date_range`, `pl.date_ranges`

`pl.arange` and `pl.date_range` return an `Expr` unless you pass `eager=True`, so code expecting a `Series` gets an expression instead. Endpoints are also inconsistent between them. `pl.arange` (an alias of `pl.int_range`) excludes `end`. `pl.date_range` and `pl.date_ranges` default to `closed="both"` and include `end`; pass `closed="left"` for a half-open date range.

```python
import polars as pl
from datetime import date

print(isinstance(pl.arange(0, 3), pl.Expr))  # True: Expr, not Series
print(pl.arange(0, 3, eager=True).to_list())  # end excluded
print(pl.date_range(date(2024, 1, 1), date(2024, 1, 3), eager=True).to_list())  # end included
print(
    pl.date_range(date(2024, 1, 1), date(2024, 1, 3), closed="left", eager=True).to_list()
)
```

Output:

```text
True
[0, 1, 2]
[datetime.date(2024, 1, 1), datetime.date(2024, 1, 2), datetime.date(2024, 1, 3)]
[datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)]
```

## pl.concat defaults to strict vertical stacking with no column alignment or type coercion

Applies to: `pl.concat`

With the default `how="vertical"`, `pl.concat` needs the frames to have the same columns with the same dtypes. It does not fill missing columns with nulls or upcast mismatched types; it raises instead. Use `how="vertical_relaxed"` to coerce to a common supertype. Use `how="diagonal"` (or `"diagonal_relaxed"`) to take the union of columns and fill the gaps with null.

```python
import polars as pl

a = pl.DataFrame({"x": [1, 2]})
b = pl.DataFrame({"x": [0.5]})
c = pl.DataFrame({"x": [3], "y": ["new"]})
for other in (b, c):
    try:
        pl.concat([a, other])
        print("no error")
    except Exception as e:
        print(type(e))
relaxed = pl.concat([a, b], how="vertical_relaxed")
print(relaxed.schema, relaxed.rows())
diag = pl.concat([a, c], how="diagonal")
print(diag.columns, diag.rows())
```

Output:

```text
<class 'polars.exceptions.SchemaError'>
<class 'polars.exceptions.ShapeError'>
Schema({'x': Float64}) [(1.0,), (2.0,), (0.5,)]
['x', 'y'] [(1, None), (2, None), (3, 'new')]
```

## pl.business_day_count excludes the end date and is unstable

Applies to: `pl.business_day_count`

`pl.business_day_count` counts business days from `start` up to but **not including** `end`, so a Monday-to-Friday span returns 4, not 5. To count inclusively, shift `end` forward by one day, for example with `Expr.dt.offset_by`. Dates listed in `holidays` are also excluded from the count. The function is marked unstable and may change without notice.

```python
import polars as pl
from datetime import date

df = pl.DataFrame({"start": [date(2024, 1, 1)], "end": [date(2024, 1, 5)]})  # Mon..Fri
out = df.select(
    exclusive=pl.business_day_count("start", "end"),
    inclusive=pl.business_day_count("start", pl.col("end").dt.offset_by("1d")),
    with_holiday=pl.business_day_count("start", "end", holidays=[date(2024, 1, 2)]),
)
print(out.columns, out.rows())
```

Output:

```text
['exclusive', 'inclusive', 'with_holiday'] [(4, 5, 3)]
```

## from_dicts only infers the schema from the first 100 dicts

Applies to: `pl.from_dicts`

`pl.from_dicts` scans at most `infer_schema_length=100` rows to infer the schema. A key that first appears after that window is not part of the inferred schema, so its column can silently go missing. A value whose type does not match the inferred dtype raises under the default `strict=True`. For heterogeneous records, pass `infer_schema_length=None` (a full scan) or declare an explicit `schema`.

```python
import polars as pl

rows = [{"a": i} for i in range(100)] + [{"a": 100, "b": "late"}]

df = pl.from_dicts(rows)
print(df.columns)

full = pl.from_dicts(rows, infer_schema_length=None)
print(full.columns)
print(full.tail(1))
```

Output:

```text
['a']
['a', 'b']
shape: (1, 2)
┌─────┬──────┐
│ a   ┆ b    │
│ --- ┆ ---  │
│ i64 ┆ str  │
╞═════╪══════╡
│ 100 ┆ late │
└─────┴──────┘
```

## from_records treats square data as columns unless orient is given

Applies to: `pl.from_records`

When `orient=None`, `pl.from_records` guesses the orientation by matching the schema length against the data dimensions. If the guess is inconclusive, as with square data, it falls back to column orientation. A list of rows like `[[1, 2], [3, 4]]` with two column names is therefore silently transposed. Always pass `orient="row"` when your inner sequences are rows.

```python
import polars as pl

data = [[1, 2], [3, 4]]

wrong = pl.from_records(data, schema=["a", "b"])
print(wrong)

right = pl.from_records(data, schema=["a", "b"], orient="row")
print(right)
```

Output:

```text
shape: (2, 2)
┌─────┬─────┐
│ a   ┆ b   │
│ --- ┆ --- │
│ i64 ┆ i64 │
╞═════╪═════╡
│ 1   ┆ 3   │
│ 2   ┆ 4   │
└─────┴─────┘
shape: (2, 2)
┌─────┬─────┐
│ a   ┆ b   │
│ --- ┆ --- │
│ i64 ┆ i64 │
╞═════╪═════╡
│ 1   ┆ 2   │
│ 3   ┆ 4   │
└─────┴─────┘
```

## pl.repeat infers Int32 for integers and pl.ones defaults to Float64

Applies to: `pl.repeat`, `pl.ones`

With `dtype=None`, `pl.repeat` infers `Int32` for integer values unless `Int64` is needed to fit the value. It does not use the `Int64` you get from Python ints in a DataFrame. `pl.ones` defaults to `Float64` even though it holds whole numbers. These dtypes can cause schema mismatches when concatenating or comparing with `Int64` columns, so pass `dtype=` explicitly.

```python
import polars as pl

print(pl.repeat(1, 3, eager=True).dtype)
print(pl.ones(3, eager=True).dtype)

df = pl.DataFrame({"x": [10, 20, 30]})
print(df.schema)

out = df.with_columns(
    pl.repeat(1, pl.len(), dtype=pl.Int64).alias("one"),
    pl.ones(pl.len(), dtype=pl.Int64).alias("one_b"),
)
print(out.schema)
```

Output:

```text
Int32
Float64
Schema({'x': Int64})
Schema({'x': Int64, 'one': Int64, 'one_b': Int64})
```

## pl.mean over several columns is per column, not a row-wise mean

Applies to: `pl.mean`

`pl.mean("a", "b")` is sugar for `pl.col("a", "b").mean()`. It reduces each column vertically and returns one row with one mean per column. It does not average across columns like pandas `df.mean(axis=1)`. For a per-row mean, use `pl.mean_horizontal`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2], "b": [3, 6]})

# per-column means, one row
print(df.select(pl.mean("a", "b")))

# row-wise mean
print(df.with_columns(pl.mean_horizontal("a", "b").alias("row_mean")))
```

Output:

```text
shape: (1, 2)
┌─────┬─────┐
│ a   ┆ b   │
│ --- ┆ --- │
│ f64 ┆ f64 │
╞═════╪═════╡
│ 1.5 ┆ 4.5 │
└─────┴─────┘
shape: (2, 3)
┌─────┬─────┬──────────┐
│ a   ┆ b   ┆ row_mean │
│ --- ┆ --- ┆ ---      │
│ i64 ┆ i64 ┆ f64      │
╞═════╪═════╪══════════╡
│ 1   ┆ 3   ┆ 2.0      │
│ 2   ┆ 6   ┆ 4.0      │
└─────┴─────┴──────────┘
```

## pl.nth selects columns by position, not rows, and is strict

Applies to: `pl.nth`

Unlike pandas `groupby(...).nth(n)`, which picks rows, `pl.nth` selects the n-th column(s) of the context. By default (`strict=True`) an out-of-bounds index raises. Pass `strict=False` to ignore indices that do not exist. To pick the n-th row of a column, use `Expr.get` (or `Expr.gather`) instead.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 8, 3], "b": [4, 5, 2]})

print(df.select(pl.nth(1)))  # column 'b', not row 1

try:
    df.select(pl.nth(0, 5))
except Exception as e:
    print(type(e).__name__)

print(df.select(pl.nth(0, 5, strict=False)))

# row at position 1 of column 'a'
print(df.select(pl.col("a").get(1)))
```

Output:

```text
shape: (3, 1)
┌─────┐
│ b   │
│ --- │
│ i64 │
╞═════╡
│ 4   │
│ 5   │
│ 2   │
└─────┘
ColumnNotFoundError
shape: (3, 1)
┌─────┐
│ a   │
│ --- │
│ i64 │
╞═════╡
│ 1   │
│ 8   │
│ 3   │
└─────┘
shape: (1, 1)
┌─────┐
│ a   │
│ --- │
│ i64 │
╞═════╡
│ 8   │
└─────┘
```

## pl.map_batches passes ONE list of Series to the function

Applies to: `pl.map_batches`

The callable given to `pl.map_batches` receives a single argument: a sequence of Series, one per entry in `exprs`. It does not receive one positional argument per column, so `lambda a, b: a + b` fails. Index into the list instead, and set `return_dtype` so Polars does not need to infer it. Prefer native expressions such as `pl.sum_horizontal` when they exist.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2], "b": [10, 20]})

try:
    df.select(pl.map_batches(["a", "b"], lambda a, b: a + b, return_dtype=pl.Int64))
except Exception as e:
    print(type(e).__name__)

out = df.select(
    pl.map_batches(["a", "b"], lambda s: s[0] + s[1], return_dtype=pl.Int64).alias("a_plus_b")
)
print(out)

print(df.select(pl.sum_horizontal("a", "b").alias("native")))
```

Output:

```text
TypeError
shape: (2, 1)
┌──────────┐
│ a_plus_b │
│ ---      │
│ i64      │
╞══════════╡
│ 11       │
│ 22       │
└──────────┘
shape: (2, 1)
┌────────┐
│ native │
│ ---    │
│ i64    │
╞════════╡
│ 11     │
│ 22     │
└────────┘
```

## json_normalize turns dicts past max_level into JSON strings

Applies to: `pl.json_normalize`

`pl.json_normalize` is unstable. Unlike pandas, it encodes any dictionary it does not unnest as JSON string data, never as objects. With `max_level` set, deeper dicts become `String` columns holding JSON text rather than nested values. Leave `max_level=None` to flatten every level, or decode the strings afterwards with `Expr.str.json_decode`.

```python
import polars as pl

data = [
    {"id": 1, "fitness": {"height": 180, "stats": {"bmi": 26}}},
    {"id": 2, "fitness": {"height": 155, "stats": {"bmi": 24}}},
]

shallow = pl.json_normalize(data, max_level=1)
print(shallow.schema)
print(shallow)

full = pl.json_normalize(data)
print(full.schema)
```

Output:

```text
Schema({'id': Int64, 'fitness.height': Int64, 'fitness.stats': String})
shape: (2, 3)
┌─────┬────────────────┬───────────────┐
│ id  ┆ fitness.height ┆ fitness.stats │
│ --- ┆ ---            ┆ ---           │
│ i64 ┆ i64            ┆ str           │
╞═════╪════════════════╪═══════════════╡
│ 1   ┆ 180            ┆ {"bmi": 26}   │
│ 2   ┆ 155            ┆ {"bmi": 24}   │
└─────┴────────────────┴───────────────┘
Schema({'id': Int64, 'fitness.height': Int64, 'fitness.stats.bmi': Int64})
```

## pl.from_epoch assumes seconds by default, so millisecond timestamps give wrong dates

Applies to: `pl.from_epoch`

`pl.from_epoch` defaults to `time_unit="s"`. JavaScript, Java and many APIs emit epoch values in milliseconds. Polars then reads those values as seconds, which gives dates tens of thousands of years in the future and raises no error. Always pass `time_unit` (`"ms"`, `"us"`, `"ns"` or `"d"`) to match your data. The unit also changes the output dtype: `"d"` returns `pl.Date`, and `"ms"` returns `Datetime("ms")`.

```python
import polars as pl

df = pl.DataFrame({"ts_ms": [1666683077000, 1666683099000]})

# Wrong: default time_unit="s" treats milliseconds as seconds
wrong = df.select(pl.from_epoch("ts_ms").dt.year().alias("year_with_default_s"))
print(wrong.to_series().to_list())

# Right: state the unit explicitly
right = df.select(pl.from_epoch("ts_ms", time_unit="ms").alias("ts"))
print(right.to_series().to_list())
print(right.schema)
```

Output:

```text
[54785, 54785]
[datetime.datetime(2022, 10, 25, 7, 31, 17), datetime.datetime(2022, 10, 25, 7, 31, 39)]
Schema({'ts': Datetime(time_unit='ms', time_zone=None)})
```

## int_range excludes its end but datetime_range includes it, and both return an Expr by default

Applies to: `pl.int_range`, `pl.datetime_range`

`pl.int_range` works like Python `range`, so `end` is exclusive. `pl.datetime_range` defaults to `closed="both"`, so `end` is included. Mixing the two leads to off-by-one row counts, so pass `closed="left"` to `pl.datetime_range` when you want a half-open range. Both functions default to `eager=False` and return a `pl.Expr`, not a `pl.Series`. Pass `eager=True` when you need a concrete `Series` outside a frame context.

```python
import polars as pl
from datetime import datetime

print(isinstance(pl.int_range(0, 3), pl.Expr))  # True: Expr, not Series
print(pl.int_range(0, 3, eager=True).to_list())  # end excluded: [0, 1, 2]

start, end = datetime(2024, 1, 1), datetime(2024, 1, 3)
both = pl.datetime_range(start, end, "1d", eager=True)
left = pl.datetime_range(start, end, "1d", closed="left", eager=True)
print(both.len(), left.len())  # 3 (end included) vs 2
```

Output:

```text
True
[0, 1, 2]
3 2
```

## pl.first and pl.last mean first column without arguments and first value with arguments

Applies to: `pl.first`, `pl.last`

Called with no arguments, `pl.first()` and `pl.last()` select the first or last *column* of the context and keep every row. Called with column names, they return the first or last *value* of those columns, which is a single row. Adding or dropping an argument therefore changes the shape of the result completely. Write `pl.col(name).first()` when you want a value. Use `pl.first()` with no argument only when you mean positional column selection.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 8, 3], "b": [4, 5, 2]})

print(df.select(pl.first()).to_dict(as_series=False))      # first COLUMN 'a', 3 rows
print(df.select(pl.first("b")).to_dict(as_series=False))   # first VALUE of 'b', 1 row
print(df.select(pl.col("b").first()).to_dict(as_series=False))  # explicit equivalent
print(df.select(pl.last()).to_dict(as_series=False))       # last COLUMN 'b', 3 rows
print(df.select(pl.last("a")).to_dict(as_series=False))    # last VALUE of 'a' -> 3
```

Output:

```text
{'a': [1, 8, 3]}
{'b': [4]}
{'b': [4]}
{'b': [4, 5, 2]}
{'a': [3]}
```

## pl.duration is a fixed length with no months; use Expr.dt.offset_by for calendar shifts

Applies to: `pl.duration`

`pl.duration` only accepts fixed units from `weeks` down to `nanoseconds`, so `days=1` means exactly 24 hours. It has no `months` or `years` parameter. Faking a month as `days=30` silently gives wrong dates. For calendar arithmetic such as months or years, use `Expr.dt.offset_by` with a duration string such as `"1mo"`.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({"dt": [datetime(2024, 1, 31), datetime(2024, 2, 29)]})

out = df.with_columns(
    plus_30d=pl.col("dt") + pl.duration(days=30),  # fixed: 2024-03-01, 2024-03-30
    plus_1mo=pl.col("dt").dt.offset_by("1mo"),     # calendar: 2024-02-29, 2024-03-29
)
for row in out.rows():
    print(row)
```

Output:

```text
(datetime.datetime(2024, 1, 31, 0, 0), datetime.datetime(2024, 3, 1, 0, 0), datetime.datetime(2024, 2, 29, 0, 0))
(datetime.datetime(2024, 2, 29, 0, 0), datetime.datetime(2024, 3, 30, 0, 0), datetime.datetime(2024, 3, 29, 0, 0))
```

## pl.len counts rows including nulls, unlike a column count

Applies to: `pl.len`

`pl.len()` is the equivalent of SQL `COUNT(*)`: it counts the rows in the context, nulls included. `Expr.count` on a column counts only its non-null values. Swapping one for the other in a `DataFrame.group_by` aggregation silently gives wrong group sizes whenever nulls are present. Use `pl.len()` for row counts and `pl.col(...).count()` for non-null counts.

```python
import polars as pl

df = pl.DataFrame({"g": ["x", "x", "y"], "v": [1, None, None]})

print(df.select(pl.len(), pl.col("v").count().alias("v_non_null")).to_dicts())
print(
    df.group_by("g", maintain_order=True)
    .agg(pl.len(), pl.col("v").count().alias("v_non_null"))
    .to_dicts()
)
```

Output:

```text
[{'len': 3, 'v_non_null': 1}]
[{'g': 'x', 'len': 2, 'v_non_null': 1}, {'g': 'y', 'len': 1, 'v_non_null': 0}]
```

## pl.groups is deprecated; collect row indices with with_row_index and group_by

Applies to: `pl.groups`

`pl.groups` (sugar for `Expr.agg_groups`) is deprecated and slated for removal. Code that relies on it to get the row positions in each group will break when it is removed. The replacement is `DataFrame.with_row_index` followed by `DataFrame.group_by(...).agg(pl.col("index"))`. Pass `maintain_order=True` if you need the groups in first-appearance order.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "b", "a"], "v": [10, 20, 30]})

# Replacement for the deprecated pl.groups("g")
out = (
    df.with_row_index()
    .group_by("g", maintain_order=True)
    .agg(pl.col("index"))
)
print(out.to_dicts())
```

Output:

```text
[{'g': 'a', 'index': [0, 2]}, {'g': 'b', 'index': [1]}]
```

## Use datetime_ranges, not datetime_range, for per-row ranges from columns

Applies to: `pl.datetime_range`, `pl.datetime_ranges`, `pl.int_ranges`

`pl.datetime_range` builds one range, so its `start` and `end` must each resolve to a single value. Passing multi-row columns raises an error. For one range per row, use `pl.datetime_ranges` (or `pl.int_ranges` for integers). These return a `List` column, not flat values. Call `DataFrame.explode` afterwards if you want one row per generated timestamp.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({
    "id": [1, 2],
    "start": [datetime(2024, 1, 1), datetime(2024, 1, 5)],
    "end": [datetime(2024, 1, 2), datetime(2024, 1, 6)],
})

try:
    df.select(pl.datetime_range("start", "end", "1d"))
except Exception as e:
    print(repr(e).split("(")[0])

out = df.with_columns(day=pl.datetime_ranges("start", "end", "1d"))
print(out.schema["day"])  # List(Datetime)
for row in out.explode("day").select("id", "day").rows():
    print(row)
```

Output:

```text
ShapeError
List(Datetime(time_unit='us', time_zone=None))
(1, datetime.datetime(2024, 1, 1, 0, 0))
(1, datetime.datetime(2024, 1, 2, 0, 0))
(2, datetime.datetime(2024, 1, 5, 0, 0))
(2, datetime.datetime(2024, 1, 6, 0, 0))
```

## pl.row_index restarts at 0 inside each group

Applies to: `pl.row_index`

`pl.row_index` numbers rows within the current evaluation context. Inside `DataFrame.group_by(...).agg(...)` it restarts at 0 for each group, so it does not give the original row positions. If you need the original positions, call `DataFrame.with_row_index` before grouping and aggregate that column. The dtype is the index type (`u32` by default), not `i64`. The function is also marked unstable.

```python
import polars as pl

df = pl.DataFrame({"x": ["A", "B", "A", "B", "B"]})

# Trap: positions are per group, not the original row numbers
print(df.group_by("x", maintain_order=True).agg(pl.row_index()))

# Right: materialise the original row index before grouping
print(
    df.with_row_index("idx")
    .group_by("x", maintain_order=True)
    .agg(pl.col("idx"))
)

print(df.select(pl.row_index()).schema)
```

Output:

```text
shape: (2, 2)
┌─────┬───────────┐
│ x   ┆ index     │
│ --- ┆ ---       │
│ str ┆ list[u32] │
╞═════╪═══════════╡
│ A   ┆ [0, 1]    │
│ B   ┆ [0, 1, 2] │
└─────┴───────────┘
shape: (2, 2)
┌─────┬───────────┐
│ x   ┆ idx       │
│ --- ┆ ---       │
│ str ┆ list[u32] │
╞═════╪═══════════╡
│ A   ┆ [0, 2]    │
│ B   ┆ [1, 3, 4] │
└─────┴───────────┘
Schema({'index': UInt32})
```

## pl.time_range includes both endpoints and defaults end to the end of the day

Applies to: `pl.time_range`, `pl.time_ranges`

`pl.time_range` and `pl.time_ranges` default to `closed='both'`, so the `end` value is included. This differs from Python's `range` and pandas-style half-open slicing. Pass `closed='left'` for a half-open range. If you omit `end`, it defaults to `time(23,59,59,999999)`, so the range silently runs to midnight.

```python
import polars as pl
from datetime import time

both = pl.time_range(time(9), time(12), "1h", eager=True)
left = pl.time_range(time(9), time(12), "1h", closed="left", eager=True)
no_end = pl.time_range(time(22), interval="1h", eager=True)

print(both.to_list())    # includes 12:00
print(left.to_list())    # stops at 11:00
print(no_end.to_list())  # runs to the end of the day
```

Output:

```text
[datetime.time(9, 0), datetime.time(10, 0), datetime.time(11, 0), datetime.time(12, 0)]
[datetime.time(9, 0), datetime.time(10, 0), datetime.time(11, 0)]
[datetime.time(22, 0), datetime.time(23, 0)]
```

## pl.union does not preserve row order; use pl.concat when order matters

Applies to: `pl.union`

`pl.union` looks like `pl.concat` and takes the same `how` strategies. However, it explicitly does not guarantee any ordering of rows in the result. Code that assumes the rows of the first frame come first, or relies on positional alignment afterwards, can silently get wrong results. Use `pl.concat` when you need predictable order, or sort the union result explicitly.

```python
import polars as pl

a = pl.DataFrame({"id": [1, 2]})
b = pl.DataFrame({"id": [3, 4]})

u = pl.union([a, b])
# Only rely on the union's content, not its order: sort explicitly
print(u.sort("id")["id"].to_list())

# pl.concat guarantees a's rows followed by b's rows
print(pl.concat([a, b])["id"].to_list())
```

Output:

```text
[1, 2, 3, 4]
[1, 2, 3, 4]
```

## pl.scan_parquet raises on missing columns by default; allow_missing_columns is deprecated

Applies to: `pl.scan_parquet`

When scanning several parquet sources whose schemas differ, `pl.scan_parquet` uses `missing_columns='raise'` by default. A later file that lacks a column from the first file therefore errors. The old `allow_missing_columns=True` flag is deprecated since 1.30.0. Pass `missing_columns='insert'` instead to fill the absent columns with nulls.

```python
import io
import polars as pl

def pq(df):
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()

srcs = [pq(pl.DataFrame({"a": [1], "b": ["x"]})), pq(pl.DataFrame({"a": [2]}))]

try:
    pl.scan_parquet(srcs).collect()
except Exception as e:
    print(type(e).__name__)

print(pl.scan_parquet(srcs, missing_columns="insert").collect())
```

Output:

```text
ColumnNotFoundError
shape: (2, 2)
┌─────┬──────┐
│ a   ┆ b    │
│ --- ┆ ---  │
│ i64 ┆ str  │
╞═════╪══════╡
│ 1   ┆ x    │
│ 2   ┆ null │
└─────┴──────┘
```

## pl.lit of a Python list is one List value, not a column

Applies to: `pl.lit`

The `pl.lit` docstring states that `pl.lit([1, 2, 3])` produces a `List<i64>` literal. Writing `with_columns(x=pl.lit([10, 20, 30]))` the pandas way therefore gives a list-typed column, not one element per row. To add a column of values, pass a `pl.Series` instead. Likewise `pl.lit(None)` has dtype `Null`, so give `dtype=` when you need a typed null column.

```python
import polars as pl

df = pl.DataFrame({"id": [1, 2, 3]})

wrong = df.with_columns(x=pl.lit([10, 20, 30]))
right = df.with_columns(x=pl.Series([10, 20, 30]))
print(wrong.schema["x"], wrong["x"].to_list())
print(right.schema["x"], right["x"].to_list())

untyped = df.with_columns(n=pl.lit(None))
typed = df.with_columns(n=pl.lit(None, dtype=pl.Int64))
print(untyped.schema["n"], typed.schema["n"])
```

Output:

```text
List(Int64) [[10, 20, 30], [10, 20, 30], [10, 20, 30]]
Int64 [10, 20, 30]
Null Int64
```

## pl.linear_space includes both endpoints and turns Date into Datetime

Applies to: `pl.linear_space`, `pl.linear_spaces`

`pl.linear_space` defaults to `closed='both'`, so `end` is part of the output. `pl.int_range` is half-open and excludes `end`, so the two are not interchangeable. Integer bounds yield Float64 points. `Date` bounds yield `Datetime` values, not `Date`: the docstring says millisecond precision, but 1.38.1 printed `time_unit='us'`. Use `closed="left"` for a half-open grid and `Expr.dt.date` to get dates back; both functions are experimental and may change without notice.

```python
import polars as pl
from datetime import date

both = pl.linear_space(0, 10, 5, eager=True)
left = pl.linear_space(0, 10, 5, closed="left", eager=True)
ints = pl.int_range(0, 10, 2, eager=True)
print(both.to_list(), both.dtype)
print(left.to_list())
print(ints.to_list(), ints.dtype)

d = pl.linear_space(date(2024, 1, 1), date(2024, 1, 3), 3, eager=True)
print(d.dtype)
print(d.dt.date().to_list())
```

Output:

```text
[0.0, 2.5, 5.0, 7.5, 10.0] Float64
[0.0, 2.0, 4.0, 6.0, 8.0]
[0, 2, 4, 6, 8] Int64
Datetime(time_unit='us', time_zone=None)
[datetime.date(2024, 1, 1), datetime.date(2024, 1, 2), datetime.date(2024, 1, 3)]
```

## pl.max and pl.min aggregate down a column; they are not row-wise GREATEST/LEAST

Applies to: `pl.max`, `pl.min`, `pl.max_horizontal`, `pl.min_horizontal`

`pl.max("a", "b")` is shorthand for `pl.col("a", "b").max()`. It returns one row with the maximum of each column, not the larger of `a` and `b` on each row. Python's built-in `max(x, y)` and SQL `GREATEST(a, b)` lead people to expect the row-wise version. For a per-row maximum or minimum, use `pl.max_horizontal` or `pl.min_horizontal`. Note that `pl.max` and `pl.min` accept only column-name strings.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 8, 3], "b": [4, 5, 2]})

# Per-column aggregation: collapses to a single row
wrong = df.select(pl.max("a", "b"))

# Row-wise maximum/minimum across columns: one value per row
right = df.with_columns(
    row_max=pl.max_horizontal("a", "b"),
    row_min=pl.min_horizontal("a", "b"),
)
print(wrong.to_dicts())
print(right.to_dicts())
```

Output:

```text
[{'a': 8, 'b': 5}]
[{'a': 1, 'b': 4, 'row_max': 4, 'row_min': 1}, {'a': 8, 'b': 5, 'row_max': 8, 'row_min': 5}, {'a': 3, 'b': 2, 'row_max': 3, 'row_min': 2}]
```

## Horizontal mean, max and min silently skip nulls

Applies to: `pl.mean_horizontal`, `pl.max_horizontal`, `pl.min_horizontal`

`pl.mean_horizontal` defaults to `ignore_nulls=True`. A row with a missing value is averaged over fewer columns instead of becoming null. Plain arithmetic like `(a + b) / 2` gives null for that row instead, so swapping one for the other quietly changes results. `pl.max_horizontal` and `pl.min_horizontal` also return the non-null value, as their docstring examples show. Pass `ignore_nulls=False` to `pl.mean_horizontal` when a missing input should make the result missing.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 8, 3], "b": [4, 5, None]})
out = df.with_columns(
    skip_nulls=pl.mean_horizontal("a", "b"),
    strict=pl.mean_horizontal("a", "b", ignore_nulls=False),
    arith=(pl.col("a") + pl.col("b")) / 2,
    row_max=pl.max_horizontal("a", "b"),
)
# Row 3: skip_nulls=3.0, row_max=3, but strict and arith are None
for row in out.to_dicts():
    print(row)
```

Output:

```text
{'a': 1, 'b': 4, 'skip_nulls': 2.5, 'strict': 2.5, 'arith': 2.5, 'row_max': 4}
{'a': 8, 'b': 5, 'skip_nulls': 6.5, 'strict': 6.5, 'arith': 6.5, 'row_max': 8}
{'a': 3, 'b': None, 'skip_nulls': 3.0, 'strict': None, 'arith': None, 'row_max': 3}
```

## pl.quantile defaults to 'nearest' interpolation, not pandas' 'linear'

Applies to: `pl.quantile`, `pl.median`

`pl.quantile` uses `interpolation='nearest'` by default, so it returns an existing data point rather than interpolating. pandas and NumPy default to linear interpolation. Porting `quantile(0.5)` from pandas therefore silently gives a different number, and the result can differ from `pl.median` on even-length data. Pass `interpolation="linear"` when you need pandas-compatible results.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 3, 10]})
out = df.select(
    default_nearest=pl.quantile("a", 0.5),
    linear=pl.quantile("a", 0.5, interpolation="linear"),
    median=pl.median("a"),
)
# default_nearest is an actual data point; linear and median are 2.5
print(out.to_dicts())
```

Output:

```text
[{'default_nearest': 3.0, 'linear': 2.5, 'median': 2.5}]
```

## pl.n_unique counts null as a distinct value

Applies to: `pl.n_unique`

`pl.n_unique` is sugar for `Expr.n_unique`, which treats null as one more unique value. pandas `nunique()` drops missing values by default, so a ported distinct count comes out one higher whenever the column contains nulls. Use `pl.col(...).drop_nulls().n_unique()` (`Expr.drop_nulls` then `Expr.n_unique`) to match pandas or SQL `COUNT(DISTINCT ...)`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, None, 1, None], "b": ["x", "y", None, "x"]})

# Null counted as a value
print(df.select(pl.n_unique("a", "b")).to_dicts())

# Exclude nulls (pandas nunique / SQL COUNT(DISTINCT) semantics)
print(df.select(pl.col("a", "b").drop_nulls().n_unique()).to_dicts())
```

Output:

```text
[{'a': 2, 'b': 3}]
[{'a': 1, 'b': 2}]
```

## pl.read_csv infers dtypes from only the first 100 rows

Applies to: `pl.read_csv`

`pl.read_csv` defaults to `infer_schema_length=100`, so dtypes are guessed from the first 100 rows only. If a column looks integer early on but holds `1.5` further down, the read fails instead of widening to float. Pass `infer_schema_length=None` to scan everything, or pin dtypes with `schema_overrides`. The old `dtypes=` parameter was renamed to `schema_overrides` in 0.20.31.

```python
import polars as pl

data = ("v\n" + "1\n" * 150 + "1.5\n").encode()

try:
    pl.read_csv(data)
except Exception as e:
    print(repr(e).split("(")[0])

full = pl.read_csv(data, infer_schema_length=None)
pinned = pl.read_csv(data, schema_overrides={"v": pl.Float64})
print(full.schema, full.height)
print(pinned.schema, pinned["v"].tail(2).to_list())
```

Output:

```text
ComputeError
Schema({'v': Float64}) 151
Schema({'v': Float64}) [1.0, 1.5]
```

## pl.read_csv_batched is deprecated; stream with scan_csv().collect_batches()

Applies to: `pl.read_csv_batched`

`pl.read_csv_batched` has been deprecated since 1.37.0, and its `BatchedCsvReader` / `next_batches` loop should not be used in new code. The deprecation message names the replacement: build a lazy scan with `pl.scan_csv` and iterate `LazyFrame.collect_batches()`, which yields DataFrames.

```python
import polars as pl
import io

data = b"a,b\n1,x\n2,y\n3,z\n"

total = 0
for batch in pl.scan_csv(io.BytesIO(data)).collect_batches():
    total += batch.height
print(total)

print(pl.scan_csv(io.BytesIO(data)).collect().to_dicts())
```

Output:

```text
3
[{'a': 1, 'b': 'x'}, {'a': 2, 'b': 'y'}, {'a': 3, 'b': 'z'}]
```

## Bare strings in concat_str and coalesce are column names, not values

Applies to: `pl.concat_str`, `pl.coalesce`, `pl.lit`

`pl.concat_str` and `pl.coalesce` treat a bare string argument as a **column name**, not a string literal. `pl.concat_str("first", " ", "last")` looks for a column named `" "`, and `pl.coalesce("last", "unknown")` looks for a column named `unknown`. Both fail with a column-not-found error, or silently use a column that happens to have that name. Wrap literal strings in `pl.lit`.

```python
import polars as pl

df = pl.DataFrame({"first": ["Ann", "Bo"], "last": ["Lee", None]})
try:
    df.select(pl.concat_str("first", " ", "last"))
except Exception as e:
    print(type(e))
try:
    df.select(pl.coalesce("last", "unknown"))
except Exception as e:
    print(type(e))

out = df.select(
    full=pl.concat_str("first", pl.lit(" "), "last"),
    last=pl.coalesce("last", pl.lit("unknown")),
)
print(out.to_dict(as_series=False))
```

Output:

```text
<class 'polars.exceptions.ColumnNotFoundError'>
<class 'polars.exceptions.ColumnNotFoundError'>
{'full': ['Ann Lee', None], 'last': ['Lee', 'unknown']}
```

## sum_horizontal skips nulls by default while + propagates them

Applies to: `pl.sum_horizontal`

`pl.sum_horizontal` defaults to `ignore_nulls=True`, so a null in one column is skipped and the row still gets a total. Plain `pl.col("a") + pl.col("b")` returns null for that row instead. Choose on purpose: if a missing input should make the total missing, pass `ignore_nulls=False` to `pl.sum_horizontal`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 8, 3], "b": [4, 5, None]})
out = df.with_columns(
    plus=pl.col("a") + pl.col("b"),
    horiz=pl.sum_horizontal("a", "b"),
    horiz_strict=pl.sum_horizontal("a", "b", ignore_nulls=False),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'a': [1, 8, 3], 'b': [4, 5, None], 'plus': [5, 13, None], 'horiz': [5, 13, 3], 'horiz_strict': [5, 13, None]}
```

## Sum of an all-null column or group is 0, not null

Applies to: `pl.sum`

`pl.sum` returns `0` when there are no non-null values, so an all-null group (like `b` here) looks like a real zero. If an all-null group should give null instead, check that `Expr.count` > 0 before keeping the sum. The docstring recommends `pl.when(pl.col(name).count() > 0).then(pl.sum(name))` instead of `pl.sum(name)`.

```python
import polars as pl

df = pl.DataFrame({"g": ["a", "a", "b"], "v": [1, 2, None]})
out = (
    df.group_by("g")
    .agg(pl.sum("v").alias("v_sum"), pl.col("v").count().alias("n"))
    .sort("g")
)
print(out.rows())

sql_like = out.get_column("v_sum").set(out.get_column("n") == 0, None)
print(sql_like.to_list())
```

Output:

```text
[('a', 3, 2), ('b', 0, 0)]
[3, None]
```

## pl.std and pl.var take one column; the second positional argument is ddof

Applies to: `pl.std`, `pl.var`, `pl.sum`

`pl.sum` accepts several column names, but `pl.std(column, ddof=1)` and `pl.var(column, ddof=1)` accept exactly one. A second positional argument is read as `ddof`, so `pl.std("a", "b")` fails. For several columns, use `pl.col("a", "b").std()`. `ddof` defaults to 1 (the sample statistic); pass `ddof=0` for the population value.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 8, 3], "b": [4, 5, 2]})
try:
    df.select(pl.std("a", "b"))
except Exception as e:
    print(type(e))

print(df.select(pl.col("a", "b").std()).rows())
print(
    df.select(
        pl.std("a", ddof=0).alias("a_pop_std"),
        pl.var("a", ddof=0).alias("a_pop_var"),
    ).rows()
)
```

Output:

```text
<class 'TypeError'>
[(3.605551275463989, 1.5275252316519465)]
[(2.943920288775949, 8.666666666666666)]
```

## rolling_corr/rolling_cov need a full window by default; the parameter is min_samples

Applies to: `pl.rolling_corr`, `pl.rolling_cov`

In `pl.rolling_corr` and `pl.rolling_cov`, `min_samples=None` means it is set equal to `window_size`. The first `window_size - 1` rows are therefore null. Lower `min_samples` to get results from partial windows earlier. The old name `min_periods` was renamed to `min_samples` in 1.21.0, so write `min_samples`.

```python
import polars as pl

df = pl.DataFrame({
    "x": [1.0, 2.0, 4.0, 3.0, 5.0],
    "y": [2.0, 1.0, 5.0, 3.0, 6.0],
})
out = df.select(
    corr_default=pl.rolling_corr("x", "y", window_size=3),
    corr_min2=pl.rolling_corr("x", "y", window_size=3, min_samples=2),
    cov_default=pl.rolling_cov("x", "y", window_size=3),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'corr_default': [None, None, 0.8386278693775346, 1.0000000000000009, 0.9819805060619665], 'corr_min2': [None, -1.0, 0.8386278693775346, 1.0000000000000009, 0.9819805060619665], 'cov_default': [None, None, 2.6666666666666665, 2.000000000000001, 1.5]}
```

## pl.sql returns a LazyFrame by default, unlike pl.select

Applies to: `pl.sql`, `pl.select`

`pl.sql` defaults to `eager=False` and returns a `LazyFrame`, which you must materialise with `LazyFrame.collect`. `pl.select` defaults to `eager=True` and returns a `DataFrame`. Code that treats the `pl.sql` result as a finished table (for example, using `DataFrame.height` or printing rows) breaks or shows only a query plan. Call `LazyFrame.collect` or pass `eager=True`.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 3]})

res = pl.sql("SELECT a FROM df WHERE a > 1")
print(isinstance(res, pl.LazyFrame))
print(res.collect().rows())

print(isinstance(pl.sql("SELECT a FROM df", eager=True), pl.DataFrame))
print(isinstance(pl.select(pl.lit(1)), pl.DataFrame))
```

Output:

```text
True
[(2,), (3,)]
True
True
```

## scan_csv infers types from only the first 100 rows

Applies to: `pl.scan_csv`

`pl.scan_csv` defaults to `infer_schema_length=100`. A column that looks like integers in its first rows but holds a float later therefore fails when you collect. Pass `infer_schema_length=None` to scan every row (slower), or declare the type with `schema_overrides`. The old `dtypes` parameter was renamed to `schema_overrides` in 0.20.31.

```python
import polars as pl

data = ("v\n" + "1\n" * 200 + "1.5\n").encode()
try:
    pl.scan_csv(data).collect()
except Exception as e:
    print(type(e))

full = pl.scan_csv(data, infer_schema_length=None).collect()
print(full.get_column("v").tail(2).to_list())
over = pl.scan_csv(data, schema_overrides={"v": pl.Float64}).collect()
print(over.get_column("v").tail(2).to_list())
```

Output:

```text
<class 'polars.exceptions.ComputeError'>
[1.0, 1.5]
[1.0, 1.5]
```

## pl.zeros defaults to Float64, not an integer dtype

Applies to: `pl.zeros`

Habits from `[0] * n` or integer-typed code lead people to expect integer zeros. `pl.zeros` defaults to `dtype=Float64`, so you get `0.0` values, not integers. If you need integer zeros, pass the dtype explicitly, for example `pl.zeros(n, pl.Int32)`.

```python
import polars as pl

s = pl.zeros(3, eager=True)
print(s.dtype, s.to_list())

s_int = pl.zeros(3, pl.Int32, eager=True)
print(s_int.dtype, s_int.to_list())
```

Output:

```text
Float64 [0.0, 0.0, 0.0]
Int32 [0, 0, 0]
```

## Adding pl.zeros to an integer column silently turns it into Float64

Applies to: `pl.zeros`

Because `pl.zeros` produces Float64 by default, an expression like `pl.col("a") + pl.zeros(n)` promotes an integer column to Float64. No error is raised, but the schema changes for everything downstream, including joins, comparisons and writes. Pass a `dtype` that matches the column you combine it with.

```python
import polars as pl

df = pl.DataFrame({"a": [1, 2, 3]})

bad = df.with_columns(pl.col("a") + pl.zeros(3))
good = df.with_columns(pl.col("a") + pl.zeros(3, pl.Int64))

print(bad.schema["a"])
print(good.schema["a"])
```

Output:

```text
Float64
Int64
```

## pl.zeros returns an Expr unless eager=True

Applies to: `pl.zeros`

The default is `eager=False`, so `pl.zeros(3)` returns a lazy `pl.Expr`, not data. Calling `Series` methods such as `Series.to_list` on it fails. Pass `eager=True` to get a `pl.Series`, or evaluate the expression with `pl.select`.

```python
import polars as pl

z = pl.zeros(3)
print(isinstance(z, pl.Expr), isinstance(z, pl.Series))
try:
    z.to_list()
except AttributeError:
    print("AttributeError")

s = pl.zeros(3, eager=True)
print(isinstance(s, pl.Series), s.to_list())

print(pl.select(pl.zeros(3)).to_series().to_list())
```

Output:

```text
True False
AttributeError
True [0.0, 0.0, 0.0]
[0.0, 0.0, 0.0]
```
