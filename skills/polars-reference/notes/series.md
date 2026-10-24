# Series: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## backward_fill does not fill NaN, only null

Applies to: `Series.backward_fill`

In pandas, `bfill` treats NaN as missing. In Polars, `Series.backward_fill` (an alias of `fill_null(strategy="backward")`) fills only nulls, and NaN counts as a valid float value. A null that comes just before a NaN gets filled *with* the NaN, and the NaN itself stays. Convert NaN to null first with `Series.fill_nan(None)`, then call `Series.backward_fill`.

```python
import polars as pl

s = pl.Series("x", [None, float("nan"), 1.0])

# pandas habit: NaN is treated as missing (it is not in Polars)
print(s.backward_fill().to_list())

# Right: turn NaN into null, then fill
print(s.fill_nan(None).backward_fill().to_list())
```

Output:

```text
[nan, nan, 1.0]
[1.0, 1.0, 1.0]
```

## cum_sum and cum_prod upcast only small integer dtypes

Applies to: `Series.cum_sum`, `Series.cum_prod`

`Series.cum_sum` and `Series.cum_prod` cast Int8, UInt8, Int16 and UInt16 to Int64 before accumulating. So the result dtype differs from the input dtype. Other integer dtypes such as Int32 are not listed for this upcast and keep their own dtype. Do not assume the output dtype matches the input. If you need a fixed dtype, or headroom for large products, `Series.cast` explicitly first.

```python
import polars as pl

s8 = pl.Series("a", [1, 2, 3], dtype=pl.Int8)
s32 = pl.Series("b", [1, 2, 3], dtype=pl.Int32)

print(s8.cum_sum().dtype)   # upcast to Int64
print(s32.cum_sum().dtype)  # not upcast

# Right: choose the accumulation dtype explicitly
print(s32.cast(pl.Int64).cum_prod().dtype)
```

Output:

```text
Int64
Int32
Int64
```

## clip leaves nulls as null and None bounds mean unbounded

Applies to: `Series.clip`

`Series.clip` does not touch nulls: a null stays null in the output and is not clamped to a bound. Passing `None` as a bound means "no bound on that side", not a null bound. The method only works for numeric and temporal data. For other dtypes, write a `pl.when` expression instead. If nulls should become a bound value, chain `Series.fill_null` explicitly.

```python
import polars as pl

s = pl.Series("v", [-50, 5, 50, None])

print(s.clip(1, 10).to_list())                # null survives
print(s.clip(upper_bound=10).to_list())       # no lower bound applied
print(s.clip(1, 10).fill_null(1).to_list())   # fill explicitly if wanted
```

Output:

```text
[1, 5, 10, None]
[-50, 5, 10, None]
[1, 5, 10, 1]
```

## cumulative_eval is unstable, O(n^2), and uses min_samples not min_periods

Applies to: `Series.cumulative_eval`

`Series.cumulative_eval` is marked unstable, so its behaviour may change without a breaking-change notice. It re-evaluates the expression over an ever-growing window, which can cost `O(n^2)`. For plain running aggregates, prefer `Series.cum_sum`, `Series.cum_max` and similar. Since 1.21.0 the threshold parameter is `min_samples`; the old pandas-style `min_periods` name was renamed. Windows with fewer valid values than `min_samples` produce null.

```python
import polars as pl

s = pl.Series("values", [1, 2, 3, 4, 5])

# Expensive general form; early windows are null below min_samples
print(s.cumulative_eval(pl.element().sum(), min_samples=3).to_list())

# Right for simple running sums: the dedicated cumulative method
print(s.cum_sum().to_list())
```

Output:

```text
[None, None, 6, 10, 15]
[1, 3, 6, 10, 15]
```

## Series.append mutates the Series in place

Applies to: `Series.append`

Unlike pandas habits where appending returns a new object, `Series.append` modifies the calling Series in place. It returns that same object only for convenience. Code like `c = a.append(b)` therefore also changes `a`, and the result is left with several chunks. Use `pl.concat([a, b])` to get a new Series and leave the original unchanged.

```python
import polars as pl

a = pl.Series("a", [1, 2, 3])
b = pl.Series("a", [4, 5])
result = a.append(b)
print(a.to_list())  # a itself was mutated: [1, 2, 3, 4, 5]
print(result is a)  # True
print(a.n_chunks())  # 2

a2 = pl.Series("a", [1, 2, 3])
combined = pl.concat([a2, b])
print(a2.to_list())  # unchanged: [1, 2, 3]
print(combined.to_list())  # [1, 2, 3, 4, 5]
```

Output:

```text
[1, 2, 3, 4, 5]
True
2
[1, 2, 3]
[1, 2, 3, 4, 5]
```

## all/any skip nulls by default, so an all-null column reports True for all

Applies to: `Series.all`, `Series.any`

By default, `Series.all` and `Series.any` use `ignore_nulls=True` and drop nulls before deciding. A column of only nulls then gives `True` from `Series.all` and `False` from `Series.any`, which can hide missing data. Pass `ignore_nulls=False` to get Kleene logic: the answer becomes `None` when nulls make the result unknown. Both methods only work on Boolean data, so build a mask first, for example `s > 0`.

```python
import polars as pl

s = pl.Series([None, True], dtype=pl.Boolean)
print(s.all())  # True: the null is ignored
print(s.all(ignore_nulls=False))  # None: unknown

nulls = pl.Series([None, None], dtype=pl.Boolean)
print(nulls.all(), nulls.any())  # True False
print(nulls.all(ignore_nulls=False), nulls.any(ignore_nulls=False))  # None None

f = pl.Series([None, False], dtype=pl.Boolean)
print(f.any(), f.any(ignore_nulls=False))  # False None
```

Output:

```text
True
None
True False
None None
False None
```

## arg_sort puts nulls first by default

Applies to: `Series.arg_sort`

`Series.arg_sort` defaults to `nulls_last=False`, so the positions of nulls come first in the result. Code that takes `s.arg_sort()[0]` as the position of the smallest value gets the null instead. Pass `nulls_last=True` when you want nulls at the end. Use `Series.arg_min` if you only need the position of the minimum.

```python
import polars as pl

s = pl.Series("a", [3, None, 1, 2])
print(s.arg_sort().to_list())  # [1, 2, 3, 0] -> null position first
print(s.arg_sort()[0])  # 1: the null, not the minimum
idx = s.arg_sort(nulls_last=True)
print(idx.to_list())  # [2, 3, 0, 1]
print(s.gather(idx).to_list())  # [1, 2, 3, None]
print(s.arg_min())  # 2
```

Output:

```text
[1, 2, 3, 0]
1
[2, 3, 0, 1]
[1, 2, 3, None]
2
```

## arg_max/arg_min return a position or None, not an index label

Applies to: `Series.arg_max`, `Series.arg_min`

Polars has no index, so `Series.arg_max` and `Series.arg_min` return a 0-based integer position. This is not a pandas-style `idxmax` label. Nulls are skipped, and the return type is `int | None`. A Series with no non-null values gives `None`, so check for `None` before passing the result on to indexing or `Series.gather`.

```python
import polars as pl

s = pl.Series("a", [1, None, 3, 2])
print(s.arg_max(), s.arg_min())  # 2 0 -> positions, nulls skipped

empty = pl.Series("a", [None, None], dtype=pl.Int64)
pos = empty.arg_max()
print(pos)  # None
if pos is not None:
    print(empty[pos])
else:
    print("no non-null values")
```

Output:

```text
2 0
None
no non-null values
```

## bottom_k output is unordered and only includes nulls when it has to

Applies to: `Series.bottom_k`, `Series.bottom_k_by`

`Series.bottom_k` and `Series.bottom_k_by` do not promise any order in their output. Call `sort` afterwards if order matters, and do not treat the first element as the minimum. Non-null elements are always chosen ahead of nulls, regardless of `reverse`. Nulls only appear when `k` is larger than the number of non-null values.

```python
import polars as pl

s = pl.Series("a", [2, None, 5, 1, None])
print(s.bottom_k(3).sort().to_list())  # [1, 2, 5]: nulls are not 'smallest'
print(s.bottom_k(4).sort(nulls_last=True).to_list())  # [1, 2, 5, None]
```

Output:

```text
[1, 2, 5]
[1, 2, 5, None]
```

## Out-of-domain trig results are NaN or inf, not null

Applies to: `Series.arccosh`, `Series.arctanh`, `Series.arccos`, `Series.arcsin`

Out-of-domain inputs return NaN, not null. `Series.arccosh` gives NaN below 1, and `Series.arctanh` gives NaN when the absolute value is above 1, `inf` at 1 and `-inf` at -1. `Series.null_count` reports 0 for these NaNs and `Series.drop_nulls` keeps them, so check with `is_nan()` or `is_finite()` instead. Use `fill_nan(None)` to turn NaN into nulls, or `drop_nans()` to remove them.

```python
import polars as pl

s = pl.Series("a", [5.0, 1.0, 0.0, -1.0]).arccosh()
print(s.null_count())  # 0
print(s.drop_nulls().len())  # 4: NaNs survive
print(s.is_nan().sum())  # 2
print(s.fill_nan(None).null_count())  # 2
print(s.drop_nans().to_list())

t = pl.Series("b", [1.0, 0.5]).arctanh()
print(t.to_list(), t.is_finite().to_list())  # [inf, ...] [False, True]
```

Output:

```text
0
4
2
2
[2.2924316695611777, 0.0]
[inf, 0.5493061443340549] [False, True]
```

## ceil returns floats, not integers

Applies to: `Series.ceil`

`Series.ceil` rounds up but keeps the floating-point dtype. The result is `2.0`, not `2`, and it is documented to work only on floating-point Series. If later code needs integers, for example for `Series.gather` or for a join key, cast explicitly with `.cast(pl.Int64)`.

```python
import polars as pl

s = pl.Series("a", [1.2, 2.5, -1.5])
c = s.ceil()
print(c.dtype)  # Float64
print(c.to_list())  # [2.0, 3.0, -1.0]
ci = c.cast(pl.Int64)
print(ci.dtype, ci.to_list())  # Int64 [2, 3, -1]
```

Output:

```text
Float64
[2.0, 3.0, -1.0]
Int64 [2, 3, -1]
```

## cast is strict by default; strict=False silently turns failures into nulls

Applies to: `Series.cast`

`Series.cast` defaults to `strict=True`, so a single unparsable string or out-of-range number makes the whole cast raise. Setting `strict=False` does not fix the data: it turns every invalid value into null without any warning, so check `Series.null_count` afterwards. For numeric overflow, `wrap_numerical=True` wraps the value around instead of failing or producing null. Choose that option deliberately, because it returns a different number rather than flagging the problem.

```python
import polars as pl

s = pl.Series(["1", "2", "x"])
try:
    s.cast(pl.Int64)
except Exception:
    print("strict string cast raised")
lenient = s.cast(pl.Int64, strict=False)
print(lenient.to_list(), lenient.null_count())  # [1, 2, None] 1

big = pl.Series([1, 300])
try:
    big.cast(pl.UInt8)
except Exception:
    print("strict overflow cast raised")
print(big.cast(pl.UInt8, strict=False).to_list())  # [1, None]
print(big.cast(pl.UInt8, wrap_numerical=True).to_list())  # [1, 44]
```

Output:

```text
strict string cast raised
[1, 2, None] 1
strict overflow cast raised
[1, None]
[1, 44]
```

## Series.explode turns empty lists into nulls by default

Applies to: `Series.explode`

`Series.explode` defaults to `empty_as_null=True` and `keep_nulls=True`. An empty list therefore produces a `null` row instead of disappearing, and a `null` list also produces a `null` row. Counts and lengths taken after exploding include these extra nulls. Pass `empty_as_null=False` to drop empty lists. Pass `keep_nulls=False` to drop null lists.

```python
import polars as pl

s = pl.Series("a", [[1, 2], [], None])
print(s.explode().to_list())
print(s.explode(empty_as_null=False).to_list())
print(s.explode(empty_as_null=False, keep_nulls=False).to_list())
```

Output:

```text
[1, 2, None, None]
[1, 2, None]
[1, 2]
```

## Series.first and Series.last return None when the edge value is null

Applies to: `Series.first`, `Series.last`

`Series.first` and `Series.last` default to `ignore_nulls=False`. They return the literal first or last element, so a leading or trailing null gives `None` even when the Series has real values. If you want the first or last non-null value, pass `ignore_nulls=True`.

```python
import polars as pl

s = pl.Series("a", [None, 2, 3, None])
print(s.first(), s.last())
print(s.first(ignore_nulls=True), s.last(ignore_nulls=True))
```

Output:

```text
None None
2 3
```

## Series.kurtosis is biased Fisher kurtosis by default

Applies to: `Series.kurtosis`

`Series.kurtosis` defaults to `fisher=True, bias=True`. It returns excess kurtosis (normal distribution gives 0.0) computed from biased moment estimators. Code ported from tools that report a bias-corrected sample kurtosis will silently get different numbers. Pass `bias=False` for the bias-corrected estimate. Pass `fisher=False` for Pearson kurtosis (normal distribution gives 3.0).

```python
import polars as pl

s = pl.Series("grades", [66, 79, 54, 97, 96, 70, 69, 85, 93, 75])
print(s.kurtosis())
print(s.kurtosis(bias=False))
print(s.kurtosis(fisher=False))
```

Output:

```text
-1.0522623626787952
-0.8959638197357283
1.9477376373212048
```

## Series.is_close has no absolute tolerance by default, so comparisons with 0 fail

Applies to: `Series.is_close`

`Series.is_close` mirrors Python's `math.isclose`, not `numpy.isclose`. The defaults are `rel_tol=1e-09` and `abs_tol=0.0`. With these defaults, a tiny value such as 1e-12 is never close to 0.0, because the relative tolerance scales with the operands. Set `abs_tol` explicitly when comparing near zero. Also, NaN is not close to NaN unless you pass `nans_equal=True`.

```python
import polars as pl

s = pl.Series("s", [1e-12, float("nan")])
print(s.is_close(0.0).to_list())
print(s.is_close(0.0, abs_tol=1e-9).to_list())
n = pl.Series("n", [float("nan")])
print(n.is_close(float("nan")).to_list())
print(n.is_close(float("nan"), nans_equal=True).to_list())
```

Output:

```text
[False, False]
[True, False]
[False]
[True]
```

## Use min_samples, not min_periods, in Series.ewm_mean, Series.ewm_std and Series.ewm_var

Applies to: `Series.ewm_mean`, `Series.ewm_std`, `Series.ewm_var`

Since 1.21.0 the warm-up parameter of the EWM methods is `min_samples`; the old `min_periods` name was renamed. Write `min_samples` in new code. Positions with fewer observations than `min_samples` are null. `adjust=True` is the default and uses decaying weights. `adjust=False` uses the recursive formula and gives different early values, so choose it deliberately.

```python
import polars as pl

s = pl.Series("x", [1.0, 2.0, 3.0])
print(s.ewm_mean(alpha=0.5, min_samples=2).to_list())
print(s.ewm_mean(alpha=0.5).to_list())
print(s.ewm_mean(alpha=0.5, adjust=False).to_list())
```

Output:

```text
[None, 1.6666666666666665, 2.4285714285714284]
[1.0, 1.6666666666666665, 2.4285714285714284]
[1.0, 1.5, 2.25]
```

## Do not persist Series.hash values: they are only stable within one Polars version

Applies to: `Series.hash`

`Series.hash` is deterministic for a given seed only within a single Polars version. The docstring explicitly does not guarantee stable results across versions. Do not store these hashes as keys in files or databases, or compare them with hashes computed by another Polars install. Use them only for in-process work such as bucketing or deduplication. Different seeds also give different hashes, so keep the seed fixed when comparing.

```python
import polars as pl

s = pl.Series("a", [1, 2, 3])
h1 = s.hash(seed=0)
h2 = s.hash(seed=0)
h3 = s.hash(seed=1)
print(h1.dtype)
print(h1.to_list() == h2.to_list())
print(h1.to_list() == h3.to_list())
```

Output:

```text
UInt64
True
False
```

## Series.count counts NaN as a valid value; only nulls are excluded

Applies to: `Series.count`, `Series.len`, `Series.fill_nan`

`Series.count` returns the number of non-null elements. A floating-point NaN is not null in Polars, so it is counted. pandas users expect `count()` to skip NaN, so they get a larger number than they expect. Use `Series.len` for the total length. To count only real numbers, first convert NaN to null with `Series.fill_nan(None)`, then call `Series.count`.

```python
import polars as pl

s = pl.Series("a", [1.0, None, float("nan")])
print("len:", s.len())
print("count (NaN counted):", s.count())
print("count excluding NaN:", s.fill_nan(None).count())
```

Output:

```text
len: 3
count (NaN counted): 2
count excluding NaN: 1
```

## drop_nulls keeps NaN and drop_nans keeps null

Applies to: `Series.drop_nulls`, `Series.drop_nans`

In Polars, null (missing) and NaN (a float value) are different things. `Series.drop_nulls` leaves NaN in place, and `Series.drop_nans` leaves nulls in place. pandas `dropna` removes both, so translating it to one of these methods leaves bad values behind. Chain both calls when you want to remove both kinds.

```python
import polars as pl

s = pl.Series("a", [1.0, None, 3.0, float("nan")])
print("drop_nulls:", s.drop_nulls().to_list())
print("drop_nans:", s.drop_nans().to_list())
print("both:", s.drop_nulls().drop_nans().to_list())
```

Output:

```text
drop_nulls: [1.0, 3.0, nan]
drop_nans: [1.0, None, 3.0]
both: [1.0, 3.0]
```

## Use eq_missing when null should compare equal to null

Applies to: `Series.eq`, `Series.eq_missing`

`Series.eq` (and `==`) propagates nulls. Comparing null with null gives null, not `True`. If you use that mask as a filter, the null rows are silently dropped. Use `Series.eq_missing` when two missing values should count as a match. It always returns a non-null boolean.

```python
import polars as pl

s1 = pl.Series("a", [333, 200, None])
s2 = pl.Series("a", [100, 200, None])
print("eq:", s1.eq(s2).to_list())
print("eq_missing:", s1.eq_missing(s2).to_list())
print("matches via eq:", s1.filter(s1.eq(s2)).len())
print("matches via eq_missing:", s1.filter(s1.eq_missing(s2)).len())
```

Output:

```text
eq: [False, True, None]
eq_missing: [False, True, True]
matches via eq: 1
matches via eq_missing: 2
```

## Series.equals ignores names and dtypes by default

Applies to: `Series.equals`

`Series.equals` defaults to `check_dtypes=False`, `check_names=False` and `null_equal=True`. Two Series with different names and different integer dtypes can therefore compare as equal. If you use it as a strict test, pass `check_dtypes=True` and `check_names=True`. Note that the old `strict` parameter was renamed `check_dtypes`. Pass `null_equal=False` if nulls should make the comparison fail.

```python
import polars as pl

a = pl.Series("a", [1, 2, None])
b = pl.Series("b", [1, 2, None], dtype=pl.Int32)
print("default:", a.equals(b))
print("strict:", a.equals(b, check_dtypes=True, check_names=True))
print("null_equal=False:", a.equals(b, null_equal=False))
```

Output:

```text
default: True
strict: False
null_equal=False: False
```

## Series.extend mutates the original Series in place

Applies to: `Series.extend`, `Series.clone`

`Series.extend` appends the other Series' data into this Series' own memory. It modifies the Series in place and returns it only for convenience. Writing `b = a.extend(other)` therefore also changes `a`, which breaks the pandas habit that methods return new objects. Call `Series.clone` first, or use `pl.concat`, if `a` must stay unchanged.

```python
import polars as pl

a = pl.Series("a", [1, 2, 3])
b = a.extend(pl.Series("b", [4, 5]))
print("a after extend:", a.to_list())
print("b is a:", b is a)

c = pl.Series("c", [1, 2, 3])
d = c.clone().extend(pl.Series("x", [4, 5]))
print("c untouched:", c.to_list(), "d:", d.to_list())
e = pl.concat([c, pl.Series("c", [9])])
print("c untouched:", c.to_list(), "e:", e.to_list())
```

Output:

```text
a after extend: [1, 2, 3, 4, 5]
b is a: True
c untouched: [1, 2, 3] d: [1, 2, 3, 4, 5]
c untouched: [1, 2, 3] e: [1, 2, 3, 9]
```

## Series.cut bins are right-closed by default and labels need len(breaks)+1 entries

Applies to: `Series.cut`

`Series.cut` (unstable) uses right-closed intervals by default, so a value exactly equal to a break falls into the lower bin. Pass `left_closed=True` to make bins left-closed. `labels` must have exactly one more entry than `breaks`; a mismatch raises an error. The result is `Categorical`, or a `Struct` if `include_breaks=True`, not a string column.

```python
import polars as pl

s = pl.Series("x", [-1, 0, 1, 2])
print(s.cut([0, 1]).cast(pl.String).to_list())
print(s.cut([0, 1], left_closed=True).cast(pl.String).to_list())
print(s.cut([0, 1]).dtype)
try:
    s.cut([0, 1], labels=["lo", "hi"])
except Exception as e:
    print(type(e))
print(s.cut([0, 1], labels=["lo", "mid", "hi"]).cast(pl.String).to_list())
```

Output:

```text
['(-inf, 0]', '(-inf, 0]', '(0, 1]', '(1, inf]']
['[-inf, 0)', '[0, 1)', '[1, inf)', '[1, inf)']
Categorical
<class 'polars.exceptions.ShapeError'>
['lo', 'lo', 'mid', 'hi']
```

## Series.cum_count counts non-null values; it is not a row number

Applies to: `Series.cum_count`, `DataFrame.with_row_index`

`Series.cum_count` returns the running count of non-null values, starting at 1. When it hits a null, the count stays flat. Do not use it as a 0-based row index that counts every row. For row positions, use `DataFrame.with_row_index`.

```python
import polars as pl

s = pl.Series("s", ["x", "k", None, "d"])
print("cum_count:", s.cum_count().to_list())
row = s.to_frame().with_row_index("row").get_column("row")
print("row index:", row.to_list())
```

Output:

```text
cum_count: [1, 2, 2, 3]
row index: [0, 1, 2, 3]
```

## Series.describe uses nearest-rank percentiles by default, not linear interpolation

Applies to: `Series.describe`

`Series.describe` defaults to `interpolation='nearest'`, so its 25%/50%/75% rows are picked from actual data points. If you expect linearly interpolated percentiles, the numbers can differ. Pass `interpolation="linear"` to get interpolated percentiles. The output is a two-column DataFrame (`statistic`, `value`), not an indexed Series.

```python
import polars as pl

s = pl.Series("a", [1, 2, 3, 4])
pct = pl.col("statistic").str.ends_with("%")
print(s.describe().columns)
print("nearest:", s.describe().filter(pct).rows())
print("linear:", s.describe(interpolation="linear").filter(pct).rows())
```

Output:

```text
['statistic', 'value']
nearest: [('25%', 2.0), ('50%', 3.0), ('75%', 3.0)]
linear: [('25%', 1.75), ('50%', 2.5), ('75%', 3.25)]
```

## pct_change returns a fraction and gives inf after a zero, not null

Applies to: `Series.pct_change`

`Series.pct_change` returns the change as a fraction (0.5 means +50%), not a percentage, so multiply by 100 yourself if you need percent. When the earlier value is 0, the result is `inf`, not null or an error, and that `inf` silently poisons later means and sums. Guard zero denominators explicitly, for example with `pl.when` on the shifted value, before you aggregate.

```python
import polars as pl

s = pl.Series("price", [0.0, 2.0, 3.0, 3.0])
print(s.pct_change().to_list())
print(s.pct_change().mean())

safe = s.to_frame().select(
    pl.when(pl.col("price").shift() == 0)
    .then(None)
    .otherwise(pl.col("price").pct_change() * 100)
    .alias("pct")
)
print(safe["pct"].to_list())
print(safe["pct"].mean())
```

Output:

```text
[None, inf, 0.5, 0.0]
inf
[None, None, 50.0, 0.0]
25.0
```

## Integer pow keeps the integer dtype; use a float exponent for roots and negative powers

Applies to: `Series.pow`

`Series.pow` follows the dtype of the base unless the exponent is a float. An integer Series raised to an integer exponent stays integer. To raise integers to a negative power, the docstring says to cast the base or the exponent to float, for example pass `-1.0` instead of `-1`. A float exponent makes the result follow the exponent's float dtype.

```python
import polars as pl

s = pl.Series("x", [1, 2, 3, 4])
sq = s.pow(2)
print(sq.dtype, sq.to_list())

root = s.pow(0.5)
print(root.dtype, root.to_list())

inv = s.pow(-1.0)
print(inv.dtype, inv.to_list())
```

Output:

```text
Int64 [1, 4, 9, 16]
Float64 [1.0, 1.4142135623730951, 1.7320508075688772, 2.0]
Float64 [1.0, 0.5, 0.3333333333333333, 0.25]
```

## Rolling skew, kurtosis and map default min_samples to the full window

Applies to: `Series.rolling_map`, `Series.rolling_skew`, `Series.rolling_kurtosis`

For `Series.rolling_map`, `Series.rolling_skew` and `Series.rolling_kurtosis`, `min_samples=None` means `min_samples = window_size`. The first `window_size - 1` results are therefore null. Pass `min_samples` explicitly if you want partial windows. In `Series.rolling_map` the old `min_periods` parameter was renamed to `min_samples` in 1.21.0, so use the new name. These three methods are also marked unstable.

```python
import polars as pl

s = pl.Series("v", [1.0, 2.0, 3.0, 4.0])
print(s.rolling_map(lambda w: w.sum(), window_size=3).to_list())
print(s.rolling_map(lambda w: w.sum(), window_size=3, min_samples=1).to_list())
```

Output:

```text
[None, None, 6.0, 9.0]
[1.0, 3.0, 6.0, 9.0]
```

## Series.std defaults to the sample standard deviation (ddof=1), unlike NumPy

Applies to: `Series.std`

`Series.std` divides by N - 1 by default (`ddof=1`). This matches pandas, but code ported from NumPy (`np.std` uses ddof=0) will get different numbers. Pass `ddof=0` when you need the population standard deviation.

```python
import polars as pl

s = pl.Series("a", [1, 2, 3])
print(s.std())
print(s.std(ddof=0))
```

Output:

```text
1.0
0.816496580927726
```

## rle_id numbers runs of consecutive values, not distinct values

Applies to: `Series.rle_id`, `Series.rle`

`Series.rle_id` starts a new ID every time the value changes. A value that reappears later gets a new ID, so it is not a distinct-value ID or a categorical code. A null also forms its own run. `Series.rle` likewise returns one row per run, not one row per unique value. Use these methods to group consecutive streaks; to count distinct values, use `Series.n_unique` or `Series.value_counts`.

```python
import polars as pl

s = pl.Series("state", ["a", "a", "b", "a", None, "a"])
print(s.rle_id().to_list())
print(s.rle_id().max() + 1, s.n_unique())
print(s.rle().struct.unnest())
```

Output:

```text
[0, 0, 1, 2, 3, 4]
5 3
shape: (5, 2)
┌─────┬───────┐
│ len ┆ value │
│ --- ┆ ---   │
│ u32 ┆ str   │
╞═════╪═══════╡
│ 2   ┆ a     │
│ 1   ┆ b     │
│ 1   ┆ a     │
│ 1   ┆ null  │
│ 1   ┆ a     │
└─────┴───────┘
```

## Series.set takes a boolean mask, Series.scatter takes positions; both are anti-patterns

Applies to: `Series.set`, `Series.scatter`

pandas users reach for `.loc` or `.iloc` style assignment. In Polars, `Series.set` expects a boolean mask the same length as the Series, while `Series.scatter` expects integer index positions; mixing them up gives wrong rows or an error. The docstrings call both an anti-pattern that can block optimization such as predicate pushdown. Prefer `pl.when(predicate).then(value).otherwise(...)` inside `DataFrame.select` or `DataFrame.with_columns`.

```python
import polars as pl

s1 = pl.Series("a", [1, 2, 3])
print(s1.set(s1 == 2, 10).to_list())

s2 = pl.Series("a", [1, 2, 3])
print(s2.scatter([0], [99]).to_list())

out = pl.Series("a", [1, 2, 3]).to_frame().select(
    pl.when(pl.col("a") == 2).then(10).otherwise(pl.col("a")).alias("a")
)
print(out["a"].to_list())
```

Output:

```text
[1, 10, 3]
[99, 2, 3]
[1, 10, 3]
```

## is_duplicated flags every copy, not just the repeats after the first

Applies to: `Series.is_duplicated`, `Series.is_first_distinct`, `Series.is_last_distinct`

Pandas `duplicated()` defaults to `keep='first'`, so it flags only the later copies. `Series.is_duplicated` flags **every** occurrence of a value that appears more than once, including the first. Filtering with `~s.is_duplicated()` therefore drops all copies of a repeated value; it does not deduplicate. To match pandas `keep='first'`, use `~Series.is_first_distinct()`. To match `keep='last'`, use `~Series.is_last_distinct()`.

```python
import polars as pl

s = pl.Series("a", [1, 2, 2, 3, 2])

# Wrong: flags the first 2 as well
print(s.is_duplicated().to_list())
# Wrong dedup: every copy of 2 disappears
print(s.filter(~s.is_duplicated()).to_list())

# Right: pandas keep='first' semantics
print((~s.is_first_distinct()).to_list())
# Right dedup that keeps the first occurrence
print(s.filter(s.is_first_distinct()).to_list())
```

Output:

```text
[False, True, True, False, True]
[1, 3]
[False, False, True, False, True]
[1, 2, 3]
```

## NaN and null are different: fill_null and is_null ignore NaN

Applies to: `Series.fill_null`, `Series.fill_nan`, `Series.is_null`, `Series.is_nan`, `Series.is_not_null`, `Series.is_not_nan`

Unlike pandas, Polars keeps the missing value (null) separate from the float NaN. `Series.fill_null` leaves NaN untouched, and `Series.fill_nan` leaves nulls untouched. `Series.is_null` returns `False` for NaN, and `Series.is_nan` returns null (not `False`) for a null element. To clean both, convert NaN to null first with `s.fill_nan(None)`, then call `Series.fill_null`.

```python
import polars as pl

s = pl.Series("x", [1.0, None, float("nan")])

print(s.fill_null(0.0).to_list())  # NaN survives
print(s.fill_nan(0.0).to_list())   # null survives
print(s.is_null().to_list())       # NaN not flagged
print(s.is_nan().to_list())

# Right: turn NaN into null, then fill all missing values at once
print(s.fill_nan(None).fill_null(0.0).to_list())
```

Output:

```text
[1.0, 0.0, nan]
[1.0, None, 0.0]
[False, True, False]
[False, None, True]
[1.0, 0.0, 0.0]
```

## is_in returns null for null inputs unless nulls_equal=True

Applies to: `Series.is_in`, `Series.filter`

With the default `nulls_equal=False`, `Series.is_in` returns null (not `False`) for null elements. Negating the mask leaves that null in place, and `Series.filter` discards null mask positions. So a null row vanishes from both the "in" result and the "not in" result. Pass `nulls_equal=True` to treat null as an ordinary value. A null that is not in `other` then yields `False`.

```python
import polars as pl

s = pl.Series("b", [2, 4, None])

m = s.is_in([1, 2, 3])
print(m.to_list())                 # [True, False, None]
print(s.filter(~m).to_list())      # null row silently lost

m2 = s.is_in([1, 2, 3], nulls_equal=True)
print(m2.to_list())                # [True, False, False]
print(s.filter(~m2).to_list())     # null row kept in the complement
```

Output:

```text
[True, False, None]
[4]
[True, False, False]
[4, None]
```

## filter drops rows where the mask is null, so mask and ~mask do not partition the data

Applies to: `Series.filter`, `Series.gt`, `Series.ge`

`Series.filter` keeps only positions where the predicate is `True`. Positions where it is null are discarded. A comparison such as `Series.gt` on data containing nulls returns null at those positions. That means `s.filter(mask)` and `s.filter(~mask)` together lose the null rows. Decide explicitly where nulls belong by calling `fill_null(True)` or `fill_null(False)` on the mask.

```python
import polars as pl

s = pl.Series("a", [10, None, 30])
mask = s.gt(15)
print(mask.to_list())                       # [False, None, True]

print(s.filter(mask).to_list())             # [30]
print(s.filter(~mask).to_list())            # [10]  -> null row in neither

# Right: decide where nulls go
print(s.filter(mask.fill_null(False)).to_list())
print(s.filter((~mask).fill_null(True)).to_list())
```

Output:

```text
[False, None, True]
[30]
[10]
[30]
[10, None]
```

## is_between includes both bounds by default and never swaps reversed bounds

Applies to: `Series.is_between`

`Series.is_between` defaults to `closed='both'`, like SQL `BETWEEN`. If you build adjacent buckets with it, values that sit exactly on a shared edge are counted in two buckets. Use `closed='left'` or `closed='right'` for half-open bins. If `lower_bound` is greater than `upper_bound`, the bounds are not swapped and the result is all `False`.

```python
import polars as pl

s = pl.Series("num", [1, 2, 3, 4, 5])

# Wrong: 3 lands in both buckets
print(s.is_between(1, 3).sum(), s.is_between(3, 5).sum())  # 3 3 -> 6 of 5 values

# Right: half-open buckets
print(s.is_between(1, 3, closed="left").sum(), s.is_between(3, 5).sum())

# Reversed bounds give all False
print(s.is_between(4, 2).to_list())
```

Output:

```text
3 3
2 3
[False, False, False, False, False]
```

## interpolate leaves edge nulls and changes integers to Float64

Applies to: `Series.interpolate`, `Series.interpolate_by`, `Series.forward_fill`

`Series.interpolate` and `Series.interpolate_by` only fill nulls that lie between two known values. Leading and trailing nulls remain null, so do not assume the result is null-free. Linear interpolation of an integer Series returns `Float64`, as the docstring example shows. Handle the edges explicitly, for example with `Series.forward_fill` and `backward_fill`, and cast back if you need integers.

```python
import polars as pl

s = pl.Series("a", [None, 1, None, 3, None])
r = s.interpolate()
print(r.dtype)
print(r.to_list())                     # edges are still null
print(r.null_count())

filled = r.forward_fill().backward_fill()
print(filled.to_list())
print(filled.cast(pl.Int64).to_list())
```

Output:

```text
Float64
[None, 1.0, 2.0, 3.0, None]
2
[1.0, 1.0, 2.0, 3.0, 3.0]
[1, 1, 2, 3, 3]
```

## index_of returns None when not found, and index 0 is falsy

Applies to: `Series.index_of`

`Series.index_of` returns the position of the first match, or `None` when the value is absent. It does not return `-1` and it does not raise like pandas `get_loc`. A truthiness check such as `if s.index_of(v):` therefore reports "not found" for a match at index 0. Always compare with `is not None`. Passing `None` searches for the first null.

```python
import polars as pl

s = pl.Series("a", [17, None, 5])

idx = s.index_of(17)
print(idx)                              # 0
print("truthy check:", bool(idx))       # False -> wrongly 'not found'
print("correct check:", idx is not None)

print(s.index_of(55))                   # None, not -1
print(s.index_of(None))                 # 1, position of the null
```

Output:

```text
0
truthy check: False
correct check: True
None
1
```

## has_validity is deprecated; has_nulls replaces it and ignores NaN

Applies to: `Series.has_validity`, `Series.has_nulls`, `Series.is_nan`

`Series.has_validity` has been deprecated since 0.20.30. Use `Series.has_nulls` instead. `Series.has_nulls` only reports null values, so a float Series full of NaN still returns `False`. To detect NaN, use `Series.is_nan` combined with `any()`.

```python
import polars as pl

f = pl.Series("x", [1.0, float("nan")])
print(f.has_nulls())          # False, despite the NaN
print(f.is_nan().any())       # True

g = pl.Series("y", [1.0, None])
print(g.has_nulls())          # True
print(g.null_count())
```

Output:

```text
False
True
True
1
```

## Series.to_dummies adds a null indicator column unless drop_nulls=True

Applies to: `Series.to_dummies`

If the Series contains nulls, `Series.to_dummies` creates an extra indicator column for the null values by default. A model matrix built this way gets an unexpected feature column. Pass `drop_nulls=True` to skip that column, so null rows become all-zero vectors. `drop_first=True` drops the first category, not the null column. The indicator columns are `UInt8`, not boolean.

```python
import polars as pl

s = pl.Series("a", [1, 2, None, 3])

default = s.to_dummies()
print(default.columns)

clean = s.to_dummies(drop_nulls=True)
print(clean.columns)
print(clean.dtypes)
print(clean.row(2))
```

Output:

```text
['a_1', 'a_2', 'a_3', 'a_null']
['a_1', 'a_2', 'a_3']
[UInt8, UInt8, UInt8]
(0, 0, 0)
```

## Series.upper_bound returns the dtype's limit, not the data maximum

Applies to: `Series.upper_bound`

`Series.upper_bound` ignores the values in the Series. It returns the largest value representable by the Series' dtype as a one-element Series. For example, it gives 127 for `Int8` and `inf` for `Float64`, not the largest finite float. Use `Series.max` for the largest value actually present. When you use `Series.upper_bound` as a sentinel, remember that it is infinite for float dtypes.

```python
import polars as pl

s_int = pl.Series("s", [-1, 0, 1], dtype=pl.Int8)
print(s_int.max(), s_int.upper_bound().item())

s_float = pl.Series("s", [1.0, 2.5, 3.0], dtype=pl.Float64)
print(s_float.max(), s_float.upper_bound().item())
```

Output:

```text
1 127
3.0 inf
```

## Use ne_missing when nulls must compare as values; ne, lt and le return null for null inputs

Applies to: `Series.ne`, `Series.ne_missing`, `Series.lt`, `Series.le`

`Series.ne` and `Series.lt` propagate nulls: a comparison that involves a null gives null, not `True` or `False`. When that mask is passed to `Series.filter`, the null rows are dropped without any warning, so a null-vs-value mismatch is silently missed. Use `Series.ne_missing` when two nulls should count as equal and a null against a value should count as different, or handle nulls explicitly with `Series.fill_null`.

```python
import polars as pl

s1 = pl.Series("a", [333, 200, None, 5])
s2 = pl.Series("a", [100, 200, None, None])

print(s1.ne(s2).to_list())          # [True, False, None, None]
print(s1.ne_missing(s2).to_list())  # [True, False, False, True]

# Row 3 (5 vs null) silently disappears with ne
print(s1.filter(s1.ne(s2)).to_list())
print(s1.filter(s1.ne_missing(s2)).to_list())

print(s1.lt(250).to_list())  # null stays null
```

Output:

```text
[True, False, None, None]
[True, False, False, True]
[333]
[333, 5]
[False, True, None, True]
```

## Series.len counts nulls; do not divide by it to get a mean

Applies to: `Series.len`, `Series.null_count`, `Series.mean`

`Series.len` returns the total number of elements, and null values count towards that total. Aggregations such as `Series.mean` skip nulls. So a hand-rolled `s.sum() / s.len()` gives a different, wrong answer whenever nulls are present. For the number of non-null values use `Series.count` or `s.len() - s.null_count()`, or simply call `Series.mean`.

```python
import polars as pl

s = pl.Series("a", [1, 2, None])

print(s.len())         # 3 (null counted)
print(s.count())       # 2 (non-null)
print(s.null_count())  # 1

print(s.sum() / s.len())    # 1.0  -- wrong
print(s.mean())             # 1.5  -- nulls ignored
print(s.sum() / s.count())  # 1.5
```

Output:

```text
3
2
1
1.0
1.5
1.5
```

## Series.max and Series.min ignore NaN; use nan_max or nan_min to propagate it

Applies to: `Series.max`, `Series.min`, `Series.nan_max`, `Series.nan_min`

By default, Polars ignores NaN values when computing `Series.max` and `Series.min`. A float column containing NaN can therefore report a clean-looking extreme value. NumPy users expect the opposite, because `np.max` propagates NaN. If NaN should poison the result, use `Series.nan_max` or `Series.nan_min`. Otherwise, check `Series.is_nan` explicitly before trusting the extreme.

```python
import polars as pl

s = pl.Series("a", [1.0, float("nan"), 4.0])

print(s.max())      # 4.0 -- NaN ignored
print(s.min())      # 1.0
print(s.nan_max())  # nan -- NaN propagates
print(s.nan_min())  # nan
print(s.is_nan().any())  # True
```

Output:

```text
4.0
1.0
nan
nan
True
```

## Series.log is the natural log; log(0) gives -inf and negatives give NaN, not null

Applies to: `Series.log`, `Series.log10`, `Series.log1p`

The default base of `Series.log` is e, not 10, so code expecting a base-10 result gets silently wrong numbers. Use `Series.log10`, or pass the base explicitly as in `s.log(10)`. Invalid inputs also do not become null. In this example, zero gives `-inf` and a negative value gives NaN, so `Series.is_null` misses them; check with `Series.is_nan` and `Series.is_infinite` instead.

```python
import polars as pl

s = pl.Series([100.0, 1.0, 0.0, -1.0])

print(s.log().to_list())    # natural log, not base 10
print(s.log10().to_list())  # [2.0, 0.0, -inf, nan]
print(s.log(10).to_list())

r = s.log10()
print(r.is_null().sum())      # 0 -- nothing flagged as null
print(r.is_nan().sum())       # 1
print(r.is_infinite().sum())  # 1
```

Output:

```text
[4.605170185988092, 0.0, -inf, nan]
[2.0, 0.0, -inf, nan]
[2.0, 0.0, -inf, nan]
0
1
1
```

## Series.is_sorted expects nulls first by default

Applies to: `Series.is_sorted`

`Series.is_sorted` defaults to `nulls_last=False`, which means it expects nulls at the start of the Series. An otherwise ascending Series with a trailing null, which is the pandas habit of putting NaN last, reports `False`. Pass `nulls_last=True` when nulls are at the end. Pass `descending=True` to check for descending order, because the default only checks ascending.

```python
import polars as pl

s = pl.Series([1, 2, None])
print(s.is_sorted())                # False -- null expected first
print(s.is_sorted(nulls_last=True)) # True

print(s.sort().to_list())  # [None, 1, 2] -- default puts nulls first
print(s.sort().is_sorted())         # True

t = pl.Series([3, 2, 1])
print(t.is_sorted())                # False
print(t.is_sorted(descending=True)) # True
```

Output:

```text
False
True
[None, 1, 2]
True
False
True
```

## Series.is_unique is a method returning a Boolean mask, not the pandas bool property

Applies to: `Series.is_unique`, `Series.n_unique`

In pandas, `s.is_unique` is a property that returns a single bool. In Polars, `Series.is_unique` is a method that returns a Boolean Series with one value per element. Writing `if s.is_unique:` tests a bound method, which is always truthy, so the check silently passes. Writing `if s.is_unique():` raises instead, because a Series has no single truth value. To get one bool, use `s.is_unique().all()` or `s.n_unique() == s.len()`.

```python
import polars as pl

s = pl.Series("a", [1, 2, 2, 3])

print(bool(s.is_unique))  # True -- a bound method, not a check!

try:
    if s.is_unique():
        pass
except TypeError:
    print("TypeError")

print(s.is_unique().to_list())  # [True, False, False, True]
print(s.is_unique().all())      # False
print(s.n_unique() == s.len())  # False
```

Output:

```text
True
TypeError
[True, False, False, True]
False
False
```

## Series.item() without an index raises unless the Series has exactly one element

Applies to: `Series.item`

`Series.item` called without an argument is not "give me the first value". It checks that the Series has length 1 and raises otherwise. Code like `s.filter(mask).item()` therefore breaks as soon as the filter matches zero rows or several rows. Pass an index, as in `s.item(0)` or `s.item(-1)`, when you want a specific position. Keep the no-argument form for cases where exactly one value is guaranteed.

```python
import polars as pl

s = pl.Series("a", [3, 1, 2])

try:
    s.item()
except ValueError:
    print("ValueError")

print(s.item(0))    # 3
print(s.item(-1))   # 2
print(s.filter(s > 2).item())  # 3 -- exactly one match

try:
    s.filter(s > 1).item()  # two matches
except ValueError:
    print("ValueError")
```

Output:

```text
ValueError
3
2
3
ValueError
```

## Series.mode can return several values in unspecified order

Applies to: `Series.mode`

`Series.mode` returns a Series, not a scalar, and it contains every value that ties for most frequent. The default is `maintain_order=False`, so the order of those values is not guaranteed. Taking `s.mode()[0]` or `s.mode().item()` as "the" mode is therefore either non-deterministic or an error. Pass `maintain_order=True`, or sort the result, before picking an element, and handle the multi-value case explicitly.

```python
import polars as pl

s = pl.Series("a", [3, 1, 3, 1, 2])

m = s.mode()
print(m.len())               # 2 -- a tie, not one value
print(m.sort().to_list())    # [1, 3] -- deterministic
print(s.mode(maintain_order=True).to_list())

try:
    m.item()
except ValueError:
    print("ValueError")
```

Output:

```text
2
[1, 3]
[3, 1]
ValueError
```

## rank keeps nulls as null and defaults to average ranks

Applies to: `Series.rank`

SQL users often expect nulls to be ranked last. `Series.rank` only ranks non-null values and leaves nulls as null. The default `method='average'` gives fractional Float64 ranks for ties. Pass `method='dense'` or `'ordinal'` to get integer ranks. If nulls need a rank, fill them with `Series.fill_null` before ranking.

```python
import polars as pl

s = pl.Series([3, None, 1, 1])

# default 'average': float ranks, null stays null
print(s.rank().dtype, s.rank().to_list())

# integer ranks
print(s.rank("dense").to_list())
print(s.rank("ordinal").to_list())

# rank nulls as the largest value by filling them first
filled = s.fill_null(s.max() + 1)
print(filled.rank("dense").to_list())
```

Output:

```text
Float64 [3.0, None, 1.5, 1.5]
[2, None, 1, 1]
[3, None, 1, 2]
[2, 3, 1, 1]
```

## Fixed-size rolling windows need min_samples to tolerate nulls

Applies to: `Series.rolling_mean`, `Series.rolling_sum`, `Series.rolling_min`, `Series.rolling_max`, `Series.rolling_std`, `Series.rolling_median`

For the fixed-size `rolling_*` methods, `min_samples=None` means `min_samples = window_size`. The first `window_size - 1` rows are null, and so is every window that contains a null. The window trails: it is the row itself plus the previous `window_size - 1` rows, unless you pass `center=True`. The parameter was renamed from `min_periods` to `min_samples` in 1.21.0, so pass `min_samples`.

```python
import polars as pl

s = pl.Series([1.0, None, 3.0, 4.0, 5.0])

# default: a single null nulls out every window that contains it
print(s.rolling_mean(window_size=2).to_list())

# require only 1 non-null value per window
print(s.rolling_mean(window_size=2, min_samples=1).to_list())

# centered window instead of trailing
print(s.rolling_sum(window_size=3, min_samples=1, center=True).to_list())
```

Output:

```text
[None, None, None, 3.5, 4.5]
[1.0, 1.0, 3.0, 3.5, 4.5]
[1.0, 4.0, 7.0, 12.0, 9.0]
```

## rolling_*_by windows are right-closed and use min_samples=1 by default

Applies to: `Series.rolling_sum_by`, `Series.rolling_mean_by`, `Series.rolling_max_by`, `Series.rolling_min_by`, `Series.rolling_median_by`, `Series.rolling_std_by`, `Series.rolling_quantile_by`, `Series.rolling_rank_by`

The temporal `rolling_*_by` methods default to `closed='right'`, so the window is `(t - window_size, t]`. A `"2d"` window therefore excludes the value exactly two days earlier. Unlike the fixed-size `rolling_*` methods, `min_samples` defaults to `1`, so the first rows are not null. Pass `closed='both'` for an inclusive start. Integer `by` columns need an `'i'` window such as `"2i"`. These methods are marked unstable.

```python
import polars as pl
from datetime import date

d = pl.Series("d", [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)])
v = pl.Series("v", [1, 2, 3])

# default closed='right': (t - 2d, t]
print(v.rolling_sum_by(d, "2d").to_list())

# inclusive on both ends: [t - 2d, t]
print(v.rolling_sum_by(d, "2d", closed="both").to_list())
```

Output:

```text
[1, 3, 5]
[1, 3, 6]
```

## quantile defaults to nearest interpolation, not linear

Applies to: `Series.quantile`, `Series.rolling_quantile`

`Series.quantile` defaults to `interpolation='nearest'`, while pandas and numpy default to linear. Results can therefore silently differ from pandas/numpy or from `Series.median`. Pass `interpolation='linear'` to match them. `Series.rolling_quantile` also defaults to `'nearest'`, and its `window_size` defaults to `2`, so always pass `window_size` explicitly.

```python
import polars as pl

s = pl.Series([1.0, 2.0, 3.0, 4.0])

print(s.quantile(0.5))                          # nearest (default)
print(s.quantile(0.5, interpolation="linear"))  # 2.5, like pandas
print(s.median())

# rolling_quantile: window_size silently defaults to 2
print(s.rolling_quantile(0.5).to_list())
print(s.rolling_quantile(0.5, interpolation="linear", window_size=3).to_list())
```

Output:

```text
3.0
2.5
2.5
[None, 2.0, 3.0, 4.0]
[None, None, 2.0, 3.0]
```

## product of an empty or all-null Series is 1, not None

Applies to: `Series.product`

`Series.product` returns `1` when there are no non-null values, so missing data can silently look like a real product. If an empty product should be `None`, guard it with `Series.count`, as the docstring suggests: `s.product() if s.count() else None`.

```python
import polars as pl

s = pl.Series("a", [None, None], dtype=pl.Int64)

print(s.product())                         # 1
print(s.product() if s.count() else None)  # None
```

Output:

```text
1
None
```

## Use replace_strict, not replace, when you need a default or a new dtype

Applies to: `Series.replace`, `Series.replace_strict`

`Series.replace` leaves unmatched values unchanged and keeps the original data type. Its `default` and `return_dtype` parameters are deprecated. To send unmatched values to a default, or to change the dtype, use `Series.replace_strict`. Without `default`, `Series.replace_strict` raises `InvalidOperationError` if any non-null value is not matched, so pass `default=None` to get nulls instead.

```python
import polars as pl

s = pl.Series([1, 2, 3])
mapping = {1: 10, 2: 20}

# replace keeps unmatched values as they are
print(s.replace(mapping).to_list())

# replace_strict raises on unmatched values when no default is given
try:
    s.replace_strict(mapping)
except Exception as e:
    print(type(e))

# explicit default: unmatched values become null
print(s.replace_strict(mapping, default=None).to_list())

# replace_strict can change the dtype
labels = s.replace_strict({1: "one", 2: "two"}, default="other")
print(labels.dtype, labels.to_list())
```

Output:

```text
[10, 20, 3]
<class 'polars.exceptions.InvalidOperationError'>
[10, 20, None]
String ['one', 'two', 'other']
```

## qcut raises DuplicateError on repeated breakpoints and is right-closed

Applies to: `Series.qcut`

`Series.qcut` raises `DuplicateError` when quantiles land on the same value, which is common with skewed or discrete data, even if the probabilities are unique. Pass `allow_duplicates=True` to drop the duplicate breakpoints. Intervals are right-closed by default; use `left_closed=True` for left-closed intervals. `labels` must have exactly one more entry than the number of cut points. The result is `Categorical`, or `Struct` with `include_breaks=True`, and the API is unstable.

```python
import polars as pl

s = pl.Series("x", [1, 1, 1, 1, 2])

try:
    s.qcut([0.25, 0.5])
except Exception as e:
    print(type(e))

binned = s.qcut([0.25, 0.5], allow_duplicates=True)
print(binned.dtype, binned.to_list())

t = pl.Series("t", [-2, -1, 0, 1, 2])
print(t.qcut(2, labels=["low", "high"]).to_list())
print(t.qcut(2, labels=["low", "high"], left_closed=True).to_list())
```

Output:

```text
<class 'polars.exceptions.DuplicateError'>
Categorical ['(-inf, 1]', '(-inf, 1]', '(-inf, 1]', '(-inf, 1]', '(1, inf]']
['low', 'low', 'low', 'high', 'high']
['low', 'low', 'high', 'high', 'high']
```

## Series.round uses bankers' rounding by default, not half-up

Applies to: `Series.round`

`Series.round` defaults to `mode='half_to_even'`, so a value exactly halfway between two candidates goes to the even one: 0.5 becomes 0.0 and 2.5 becomes 2.0. SQL `ROUND` and spreadsheet users usually expect half away from zero, so totals and labels can silently differ. Pass `mode='half_away_from_zero'` when you need that behaviour.

```python
import polars as pl

s = pl.Series("x", [0.5, 1.5, 2.5, -2.5])

# Default: half_to_even (bankers' rounding)
print(s.round().to_list())  # [0.0, 2.0, 2.0, -2.0]

# SQL-style rounding
print(s.round(mode="half_away_from_zero").to_list())  # [1.0, 2.0, 3.0, -3.0]
```

Output:

```text
[0.0, 2.0, 2.0, -2.0]
[1.0, 2.0, 3.0, -3.0]
```

## Series.sum returns 0, not None, when there are no non-null values

Applies to: `Series.sum`

`Series.sum` on an empty or all-null Series returns `0`, not `None` or null. Code that checks `if total is None` to detect missing data will never fire. If an empty sum should be `None`, use `s.sum() if s.count() else None` as the docstring suggests. Note also that Int8/UInt8/Int16/UInt16 are cast to Int64 before summing, so the result does not overflow the small dtype.

```python
import polars as pl

all_null = pl.Series("x", [None, None], dtype=pl.Int64)
print(all_null.sum())  # 0, not None

# Explicitly treat 'no data' as None
print(all_null.sum() if all_null.count() else None)  # None

# Small ints are widened before summing, so no overflow
small = pl.Series("y", [100, 100], dtype=pl.Int8)
print(small.sum())  # 200
```

Output:

```text
0
None
200
```

## Series.sort puts nulls first and returns a new Series

Applies to: `Series.sort`

`Series.sort` defaults to `nulls_last=False`, so nulls come first. This also applies with `descending=True`. pandas users expect nulls at the end (`na_position='last'`), so taking the first element after a sort may give you a null. Pass `nulls_last=True` explicitly. The call also returns a new Series (`in_place=False`), so calling `s.sort()` without assigning the result leaves `s` unchanged.

```python
import polars as pl

s = pl.Series("x", [3, None, 1])

print(s.sort().to_list())                 # [None, 1, 3]
print(s.sort(descending=True).to_list())  # [None, 3, 1]
print(s.sort(nulls_last=True).to_list())  # [1, 3, None]

s.sort()  # result discarded
print(s.to_list())  # [3, None, 1] -- unchanged

s = s.sort(nulls_last=True)
print(s.to_list())  # [1, 3, None]
```

Output:

```text
[None, 1, 3]
[None, 3, 1]
[1, 3, None]
[3, None, 1]
[1, 3, None]
```

## Series.skew is biased by default, unlike pandas

Applies to: `Series.skew`

`Series.skew` defaults to `bias=True` and returns the plain Fisher-Pearson coefficient g1. pandas `skew()` returns the bias-adjusted G1, so porting code gives a different number on small samples. Pass `bias=False` to get the adjusted coefficient.

```python
import polars as pl

s = pl.Series([1, 2, 2, 4, 5])

biased = s.skew()               # default bias=True -> g1
adjusted = s.skew(bias=False)   # adjusted G1 (pandas-style)

print(round(biased, 6))    # 0.347767
print(round(adjusted, 6))  # larger value
print(biased == adjusted)  # False
```

Output:

```text
0.347767
0.518421
False
```

## Series.slice takes a length, not a stop index

Applies to: `Series.slice`, `Series.tail`

`Series.slice(offset, length)` takes a start and a number of elements. It is not Python's `[start:stop]`. Calling `s.slice(1, 3)` returns three elements starting at index 1, not indices 1 and 2. Compute `length = stop - start` when translating slicing code. With `Series.tail`, a negative `n` returns everything except the first `abs(n)` elements; it does not count back from the end.

```python
import polars as pl

s = pl.Series("a", [10, 20, 30, 40, 50])

print(s.slice(1, 3).to_list())      # [20, 30, 40] -- 3 elements, not stop=3

start, stop = 1, 3
print(s.slice(start, stop - start).to_list())  # [20, 30] == python s[1:3]

print(s.slice(-2).to_list())        # [40, 50]
print(s.tail(-2).to_list())         # [30, 40, 50] -- all except first 2
```

Output:

```text
[20, 30, 40]
[20, 30]
[40, 50]
[30, 40, 50]
```

## Series.set_sorted on unsorted data silently gives wrong answers

Applies to: `Series.set_sorted`

`Series.set_sorted` does not sort or check anything. It only sets a flag that later operations trust for fast paths. If the data is not actually sorted, aggregations such as `Series.max` can return wrong values with no error. Use `Series.sort` unless you are certain the data is already ordered.

```python
import polars as pl

s = pl.Series("a", [3, 1, 2])

flagged = s.set_sorted()  # lies: data is not sorted
print(flagged.max())      # may be wrong (fast path returns the last value)

print(s.max())            # 3 -- correct
print(s.sort().max())     # 3 -- sort for real instead of flagging
```

Output:

```text
2
3
3
```

## Series.rolling_var returns null for any window containing a null

Applies to: `Series.rolling_var`, `Series.rolling_var_by`

For `Series.rolling_var`, `min_samples=None` means it is set to `window_size`. As a result, a single null inside a window makes that row's result null, not just the first `window_size - 1` rows. Lower `min_samples` to compute variance over the available values. The parameter was renamed from `min_periods` in 1.21.0, so use `min_samples`. By contrast, the unstable `Series.rolling_var_by` defaults to `min_samples=1`, and its windows default to `closed='right'`. Both use `ddof=1`.

```python
import polars as pl

s = pl.Series("a", [1.0, None, 3.0, 4.0, 5.0])

# Default min_samples == window_size: one null kills 3 windows
print(s.rolling_var(3).round(6).to_list())
# [None, None, None, None, 1.0]

# Allow windows with at least 2 non-null values
print(s.rolling_var(3, min_samples=2).round(6).to_list())
# [None, None, 2.0, 0.5, 1.0]
```

Output:

```text
[None, None, None, None, 1.0]
[None, None, 2.0, 0.5, 1.0]
```

## Pass side explicitly to Series.search_sorted when there are duplicates

Applies to: `Series.search_sorted`

`Series.search_sorted` defaults to `side='any'`, which returns the first suitable location the search finds. With duplicate values, that is not documented to be the leftmost one. Use `side='left'` or `side='right'` when you need `bisect_left` or `bisect_right` semantics. The Series must already be sorted; pass `descending=True` if it is sorted descending. The return type depends on the input: a scalar returns a Python `int`, and a list returns a `Series`.

```python
import polars as pl

s = pl.Series("vals", [1, 2, 3, 4, 4, 5, 6, 7])

print(s.search_sorted(4, side="left"))   # 3 (bisect_left)
print(s.search_sorted(4, side="right"))  # 5 (bisect_right)

scalar = s.search_sorted(4, side="left")
many = s.search_sorted([1, 4, 5], side="left")
print(isinstance(scalar, int))        # True
print(isinstance(many, pl.Series))    # True
print(many.to_list())                 # [0, 3, 5]
```

Output:

```text
3
5
True
True
[0, 3, 5]
```

## Pass maintain_order=True when the order of unique values matters

Applies to: `Series.unique`

`Series.unique` defaults to `maintain_order=False`, so the order of the result is not guaranteed. Code that takes the first unique value, or that zips the result with something else, can silently change between runs. Pass `maintain_order=True` to keep first-appearance order, or call `Series.sort` on the result if you want sorted order.

```python
import polars as pl

s = pl.Series('a', [3, 1, 3, 2])

# Default: order is not guaranteed, so sort explicitly if you need a stable result
print(s.unique().sort().to_list())

# First-appearance order, like pandas unique()
print(s.unique(maintain_order=True).to_list())
```

Output:

```text
[1, 2, 3]
[3, 1, 2]
```

## Sort the result of top_k yourself and expect nulls to be skipped

Applies to: `Series.top_k`, `Series.top_k_by`

`Series.top_k` and `Series.top_k_by` do not return elements in any particular order. Do not assume the first element is the largest; call `Series.sort` on the result. Non-null elements are always preferred over nulls, and for `Series.top_k_by` this holds regardless of `reverse`. So a 'smallest k' query with `reverse=True` picks non-null values before any nulls rather than treating null as the minimum.

```python
import polars as pl

s = pl.Series('a', [2, None, 5, 1, 4])

# Unordered output: sort explicitly
print(s.top_k(3).sort(descending=True).to_list())

# reverse=True gives the smallest values, and nulls are still skipped
print(s.top_k_by('a', 2, reverse=True).sort().to_list())
```

Output:

```text
[5, 4, 2]
[1, 2]
```

## Series.var uses the sample variance (ddof=1) by default

Applies to: `Series.var`

`Series.var` divides by `N - ddof` with `ddof=1` by default, which gives the sample variance. Code ported from NumPy, where the default is population variance (`ddof=0`), will get different numbers. Pass `ddof=0` explicitly when you want the population variance.

```python
import polars as pl

s = pl.Series('a', [1, 2, 3])
print(s.var())        # sample variance, ddof=1
print(s.var(ddof=0))  # population variance
```

Output:

```text
1.0
0.6666666666666666
```

## to_physical output depends on dtype details and is not a stable encoding

Applies to: `Series.to_physical`

`Series.to_physical` exposes the internal representation. For example, `Datetime` becomes `Int64` counted in the column's own time unit, so the same instant gives different integers for `ms` and `us`. `Categorical` becomes `UInt32` codes. The docs warn that physical representations are an implementation detail and not guaranteed to be stable, so do not persist or compare these integers across datasets. For epoch values with an explicit unit, use `Expr.dt.epoch`.

```python
import polars as pl

df = pl.select(
    ms=pl.datetime(2024, 1, 1, time_unit='ms'),
    us=pl.datetime(2024, 1, 1, time_unit='us'),
)
print(df['ms'].to_physical().to_list())
print(df['us'].to_physical().to_list())

# Explicit unit: identical regardless of storage unit
print(df.select(pl.col('ms', 'us').dt.epoch('s')).row(0))
```

Output:

```text
[1704067200000]
[1704067200000000]
(1704067200, 1704067200)
```

## Pair unique_counts with unique(maintain_order=True), not the default unique

Applies to: `Series.unique_counts`, `Series.unique`

`Series.unique_counts` returns only the counts, in order of first appearance, and not the values. The default `Series.unique()` does not guarantee order, so zipping the two can attach counts to the wrong values. Pair it with `Series.unique(maintain_order=True)`, or use `Series.value_counts` to get values and counts together.

```python
import polars as pl

s = pl.Series('id', ['b', 'a', 'b', 'c', 'b'])
keys = s.unique(maintain_order=True)
counts = s.unique_counts()
print(list(zip(keys.to_list(), counts.to_list())))

vc = s.value_counts()
print(sorted(vc.rows()))
```

Output:

```text
[('b', 3), ('a', 1), ('c', 1)]
[('a', 1), ('b', 3), ('c', 1)]
```

## value_counts returns an unsorted DataFrame with a 'count' column

Applies to: `Series.value_counts`

`Series.value_counts` returns a `DataFrame` with one column of values and one column of counts. It does not return a Series indexed by value. The counts column is named `count`, or `proportion` when `normalize=True`. The default is `sort=False`, which leaves the row order non-deterministic, so `.head(1)` is not reliably the most frequent value. Pass `sort=True` for descending counts, and use `name=` to choose the count column name.

```python
import polars as pl

s = pl.Series('color', ['red', 'blue', 'red', 'green', 'blue', 'blue'])
vc = s.value_counts(sort=True)
print(isinstance(vc, pl.DataFrame), vc.columns)
print(vc.rows())
print(s.value_counts(sort=True, normalize=True).columns)
print(s.value_counts(sort=True, name='n').columns)
```

Output:

```text
True ['color', 'count']
[('blue', 3), ('red', 2), ('green', 1)]
['color', 'proportion']
['color', 'n']
```

## zip_with keeps self where the mask is True and takes a Series for other

Applies to: `Series.zip_with`

`Series.zip_with(mask, other)` takes values from `self` where `mask` is true and from `other` where it is false. The calling Series is the 'true' branch, so swapping `self` and `other` silently inverts the selection. `other` is documented as a Series of the same type, so pass a Series rather than a scalar. For conditional logic inside a frame, prefer `pl.when`.

```python
import polars as pl

s1 = pl.Series('a', [1, 2, 3])
s2 = pl.Series('b', [10, 20, 30])
mask = pl.Series([True, False, True])
print(s1.zip_with(mask, s2).to_list())  # self where True
print(s2.zip_with(mask, s1).to_list())  # swapped: inverted selection
```

Output:

```text
[1, 20, 3]
[10, 2, 30]
```

## to_numpy may return a read-only array, and zero_copy_only is deprecated

Applies to: `Series.to_numpy`

When the conversion is zero-copy (numeric dtype, no nulls, single chunk), `Series.to_numpy` returns an array that is not writable, and in-place assignment on it raises an error. Pass `writable=True` to force a copy you can mutate. The `zero_copy_only` parameter is deprecated in favour of `allow_copy=False`, which is its inverse, and `use_pyarrow` is deprecated as well. With `allow_copy=False`, any conversion that needs a copy fails, for example a Series with nulls.

```python
import polars as pl

s = pl.Series('a', [1, 2, 3], dtype=pl.Int8)
arr = s.to_numpy()
try:
    arr[0] = 10
except Exception as e:
    print(repr(e).split('(')[0])

w = s.to_numpy(writable=True)
w[0] = 10
print(pl.Series(w).to_list(), s.to_list())

try:
    pl.Series('b', [1, None]).to_numpy(allow_copy=False)
except Exception as e:
    print(repr(e).split('(')[0])
```

Output:

```text
ValueError
[10, 2, 3] [1, 2, 3]
RuntimeError
```
