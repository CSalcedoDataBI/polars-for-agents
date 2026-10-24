# Expr.cat: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## Cast to String for string operations the cat namespace does not have

Applies to: `Expr.cat.starts_with`, `Expr.cat.ends_with`, `Expr.cat.slice`, `Expr.cat.len_bytes`, `Expr.cat.len_chars`, `Expr.cat.get_categories`

`Expr.cat` exposes only a few string helpers, such as `Expr.cat.starts_with`, `Expr.cat.ends_with`, `Expr.cat.slice`, `Expr.cat.len_bytes`, `Expr.cat.len_chars` and `Expr.cat.get_categories`. It has no `contains`, and calling `pl.col(c).cat.contains(...)` raises `AttributeError`. For other string operations, first cast with `Expr.cast` to `pl.String`, then use `Expr.str` methods such as `Expr.str.contains` or `Expr.str.to_lowercase`.

```python
import polars as pl

df = pl.DataFrame({"fruit": pl.Series(["apple", "Mango", None], dtype=pl.Categorical)})
try:
    df.select(pl.col("fruit").cat.contains("an"))
except AttributeError:
    print("AttributeError")
out = df.select(
    pl.col("fruit").cast(pl.String).str.contains("an").alias("has_an"),
    pl.col("fruit").cast(pl.String).str.to_lowercase().alias("lower"),
)
print(out["has_an"].to_list())
print(out["lower"].to_list())
```

Output:

```text
AttributeError
[False, True, None]
['apple', 'mango', None]
```

## Pass only literal strings to cat.starts_with and cat.ends_with

Applies to: `Expr.cat.starts_with`, `Expr.cat.ends_with`

`Expr.str.starts_with` and `Expr.str.ends_with` accept expressions. Their categorical counterparts, `Expr.cat.starts_with` and `Expr.cat.ends_with`, require a literal Python `str`. So a call like `pl.col("code").cat.starts_with(pl.col("region"))` raises a `TypeError`. For a per-row prefix or suffix, cast to `pl.String` and pass the column expression to `Expr.str.starts_with` or `Expr.str.ends_with`.

```python
import polars as pl

df = pl.DataFrame({
    "code": pl.Series(["US-1", "EU-2", "US-3"], dtype=pl.Categorical),
    "region": ["US", "EU", "EU"],
})
try:
    df.select(pl.col("code").cat.starts_with(pl.col("region")))
except TypeError:
    print("TypeError")
out = df.with_columns(
    pl.col("code").cast(pl.String).str.starts_with(pl.col("region")).alias("match")
)
print(out["match"].to_list())
```

Output:

```text
TypeError
[True, True, False]
```

## Expect cat.slice to return String, not Categorical

Applies to: `Expr.cat.slice`

`Expr.cat.slice` returns an expression of dtype `String`, so the categorical dtype is lost. Code further down that expects a categorical column will get a plain string column instead. If you need a categorical result, cast back explicitly with `Expr.cast` to `pl.Categorical`.

```python
import polars as pl

df = pl.DataFrame({"s": pl.Series(["pear", None, "papaya"], dtype=pl.Categorical)})
out = df.with_columns(
    pl.col("s").cat.slice(0, 2).alias("prefix_str"),
    pl.col("s").cat.slice(0, 2).cast(pl.Categorical).alias("prefix_cat"),
)
print(out.dtypes)
print(out["prefix_str"].to_list())
print(out["prefix_cat"].to_list())
```

Output:

```text
[Categorical, String, Categorical]
['pe', None, 'pa']
['pe', None, 'pa']
```

## Do not use get_categories to list the values present in a column

Applies to: `Expr.cat.get_categories`

`Expr.cat.get_categories` returns the categories stored in the data type, not the distinct values in the column. For a `pl.Enum`, that means every declared category, including ones that never occur in the data. To list only the values actually present, use `Expr.unique`. Pass `maintain_order=True` if order matters.

```python
import polars as pl

size = pl.Enum(["S", "M", "L", "XL"])
df = pl.DataFrame({"size": pl.Series(["M", "S", "M"], dtype=size)})
cats = df.select(pl.col("size").cat.get_categories()).to_series()
present = df.select(pl.col("size").unique(maintain_order=True)).to_series()
print(cats.to_list())
print(present.to_list())
```

Output:

```text
['S', 'M', 'L', 'XL']
['M', 'S']
```

## Use cat.len_chars, not cat.len_bytes, for character counts on non-ASCII text

Applies to: `Expr.cat.len_bytes`, `Expr.cat.len_chars`

`Expr.cat.len_bytes` counts UTF-8 bytes, not characters. For example, "Caf\u00e9" is 5 bytes but 4 characters, so a length filter written with it silently drops valid non-ASCII values. Use `Expr.cat.len_chars` when you mean characters. Keep `Expr.cat.len_bytes` for byte sizes or for data known to be ASCII. Both return `UInt32`, and null inputs give null.

```python
import polars as pl

city = ["Caf\u00e9", "\u6771\u4eac", "Oslo", None]
df = pl.DataFrame({"city": pl.Series(city, dtype=pl.Categorical)})
out = df.with_columns(
    pl.col("city").cat.len_bytes().alias("n_bytes"),
    pl.col("city").cat.len_chars().alias("n_chars"),
)
print(out["n_bytes"].to_list())
print(out["n_chars"].to_list())
print(df.filter(pl.col("city").cat.len_bytes() <= 4).height)
print(df.filter(pl.col("city").cat.len_chars() <= 4).height)
```

Output:

```text
[5, 6, 4, None]
[4, 2, 4, None]
1
3
```

## Fill nulls before negating cat.starts_with or cat.ends_with in a filter

Applies to: `Expr.cat.starts_with`, `Expr.cat.ends_with`

`Expr.cat.starts_with` and `Expr.cat.ends_with` return null for null values. Negating null with `~` still gives null, and `DataFrame.filter` drops rows whose condition is null. As a result, `~pl.col(c).cat.starts_with(p)` silently excludes the null rows. If nulls should count as "does not start with", add `Expr.fill_null(False)` before negating.

```python
import polars as pl

df = pl.DataFrame({"fruit": pl.Series(["apple", "mango", None], dtype=pl.Categorical)})
wrong = df.filter(~pl.col("fruit").cat.starts_with("app"))
right = df.filter(~pl.col("fruit").cat.starts_with("app").fill_null(False))
print(wrong["fruit"].to_list())
print(right["fruit"].to_list())
```

Output:

```text
['mango']
['mango', None]
```

## Replace pandas cat.codes and cat.categories with to_physical and get_categories

Applies to: `Expr.cat.get_categories`, `Expr.to_physical`

pandas users reach for `.cat.codes` or `.cat.categories`, but neither exists on `Expr.cat`, and accessing them raises `AttributeError`. Use `Expr.to_physical` to get the integer codes. Use `Expr.cat.get_categories` to get the categories; it is a method call, not an attribute.

```python
import polars as pl

lvl = pl.Enum(["lo", "mid", "hi"])
df = pl.DataFrame({"lvl": pl.Series(["hi", "lo", "mid", "hi"], dtype=lvl)})
for attr in ["codes", "categories"]:
    try:
        getattr(pl.col("lvl").cat, attr)
    except AttributeError:
        print(attr, "AttributeError")
print(df.select(pl.col("lvl").to_physical()).to_series().to_list())
print(df.select(pl.col("lvl").cat.get_categories()).to_series().to_list())
```

Output:

```text
codes AttributeError
categories AttributeError
[2, 0, 1, 2]
['lo', 'mid', 'hi']
```
