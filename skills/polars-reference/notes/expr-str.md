# Expr.str: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## Expr.str.contains treats the pattern as a regex unless literal=True

Applies to: `Expr.str.contains`

`Expr.str.contains` compiles `pattern` as a regex by default, like pandas `str.contains(regex=True)`. Metacharacters in a plain search term change its meaning. For example, `"1.2"` also matches `"112"` and `"1+2"` because `.` matches any character. A pattern that is not a valid regex, such as `"1+("`, raises an error with the default `strict=True` and turns every row into null with `strict=False`. When you mean a plain substring, pass `literal=True`.

```python
import polars as pl

df = pl.DataFrame({"ver": ["1.2", "112", "1+2"]})
out = df.select(
    regex=pl.col("ver").str.contains("1.2"),
    literal=pl.col("ver").str.contains("1.2", literal=True),
)
print(out.to_dict(as_series=False))

try:
    df.select(pl.col("ver").str.contains("1+("))
    print("no error")
except Exception:
    print("invalid regex raised an error")

lenient = df.select(pl.col("ver").str.contains("1+(", strict=False))
print(lenient.to_series().to_list())
plain = df.select(pl.col("ver").str.contains("1+(", literal=True))
print(plain.to_series().to_list())
```

Output:

```text
{'regex': [True, True, True], 'literal': [True, False, False]}
invalid regex raised an error
[None, None, None]
[False, False, False]
```

## Expr.str.replace changes only the first match, unlike pandas

Applies to: `Expr.str.replace`, `Expr.str.replace_all`

pandas `str.replace` replaces every occurrence. `Expr.str.replace` defaults to `n=1` and replaces only the first match, so the other occurrences are silently left in place. Use `Expr.str.replace_all` to replace every match. Both methods treat `pattern` as a regex unless `literal=True`.

```python
import polars as pl

df = pl.DataFrame({"d": ["2024-01-15", "1999-12-31"]})
out = df.select(
    first_only=pl.col("d").str.replace("-", "/"),
    every=pl.col("d").str.replace_all("-", "/"),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'first_only': ['2024/01-15', '1999/12-31'], 'every': ['2024/01/15', '1999/12/31']}
```

## Use Expr.str.join instead of the deprecated Expr.str.concat, and note its empty default delimiter

Applies to: `Expr.str.concat`, `Expr.str.join`

`Expr.str.concat` is deprecated; use `Expr.str.join` instead. The default `delimiter` changed from a hyphen to an empty string, so a straight rename glues the values together. Both methods collapse the whole column into a single value. With the default `ignore_nulls=True`, they also silently drop nulls. Pass `ignore_nulls=False` if a null anywhere should make the result null.

```python
import polars as pl

df = pl.DataFrame({"tag": ["a", None, "c"]})
print(df.select(pl.col("tag").str.join()).to_series().to_list())
print(df.select(pl.col("tag").str.join("-")).to_series().to_list())
out = df.select(pl.col("tag").str.join("-", ignore_nulls=False))
print(out.to_series().to_list())
```

Output:

```text
['ac']
['a-c']
[None]
```

## Expr.str.len_bytes counts bytes, not characters

Applies to: `Expr.str.len_bytes`, `Expr.str.len_chars`

pandas `str.len` counts characters; in Polars that is `Expr.str.len_chars`. `Expr.str.len_bytes` is faster, but it returns the UTF-8 byte length. That length differs as soon as the text contains non-ASCII characters, so length filters built on it silently keep the wrong rows. Use `Expr.str.len_bytes` only when the data is known to be ASCII.

```python
import polars as pl

df = pl.DataFrame({"name": ["Zo\u00eb", "Bob", "\u6771\u4eac"]})
out = df.select(
    n_bytes=pl.col("name").str.len_bytes(),
    n_chars=pl.col("name").str.len_chars(),
)
print(out.to_dict(as_series=False))
by_bytes = df.filter(pl.col("name").str.len_bytes() == 3)
by_chars = df.filter(pl.col("name").str.len_chars() == 3)
print(ascii(by_bytes.to_series().to_list()))
print(ascii(by_chars.to_series().to_list()))
```

Output:

```text
{'n_bytes': [4, 3, 6], 'n_chars': [3, 3, 2]}
['Bob']
['Zo\xeb', 'Bob']
```

## Expr.str.find returns a byte offset, or null when not found

Applies to: `Expr.str.find`, `Expr.str.slice`

`Expr.str.find` returns the byte offset of the first match, and null when there is no match. It does not return a character index or -1 as pandas does. `Expr.str.slice` counts characters, so feeding it the result of `Expr.str.find` gives off-by-N substrings on non-ASCII text. `Expr.str.find` also treats the pattern as a regex unless `literal=True`. To cut at a delimiter, use `Expr.str.extract` or a split instead of combining find and slice.

```python
import polars as pl

df = pl.DataFrame({"s": ["caf\u00e9: 5", "cafe: 5", "none"]})
pos = pl.col("s").str.find(":", literal=True)
out = df.select(
    pos=pos,
    wrong_key=pl.col("s").str.slice(0, pos),
    right_key=pl.col("s").str.extract(r"^([^:]*):", 1),
)
print(ascii(out.to_dict(as_series=False)))
```

Output:

```text
{'pos': [5, 4, None], 'wrong_key': ['caf\xe9:', 'cafe', 'none'], 'right_key': ['caf\xe9', 'cafe', None]}
```

## Expr.str.strip_chars strips a set of characters, not a prefix or suffix

Applies to: `Expr.str.strip_chars`, `Expr.str.strip_chars_end`, `Expr.str.strip_suffix`

`Expr.str.strip_chars` and `Expr.str.strip_chars_end` treat `characters` as an unordered set of characters. Every leading or trailing character in that set is removed, so stripping `".csv"` can eat into the file name itself. To remove an exact string, use `Expr.str.strip_suffix` or `Expr.str.strip_prefix`. Also, once you pass `characters`, whitespace is no longer stripped unless you include it in the set.

```python
import polars as pl

df = pl.DataFrame({"f": ["report.csv", "docs.csv", "vcs.csv", "data.csv "]})
out = df.select(
    as_set=pl.col("f").str.strip_chars_end(".csv"),
    as_suffix=pl.col("f").str.strip_suffix(".csv"),
)
print(out.to_dict(as_series=False))
```

Output:

```text
{'as_set': ['report', 'do', '', 'data.csv '], 'as_suffix': ['report', 'docs', 'vcs', 'data.csv ']}
```

## Expr.str.split_exact and Expr.str.splitn return structs and use n differently

Applies to: `Expr.str.split_exact`, `Expr.str.splitn`, `Expr.str.split`

Both methods return a `Struct`, not a list; use `Expr.str.split` if you want a list. In `Expr.str.split_exact`, `n` is the number of splits, giving n+1 fields, and anything after the n-th split is not kept in any field. In `Expr.str.splitn`, `n` is the maximum number of items, and the last field holds the remainder. pandas `str.split(n=1)` therefore corresponds to `Expr.str.splitn(by, 2)`.

```python
import polars as pl

df = pl.DataFrame({"s": ["a_b_c", "d"]})
exact = df.select(pl.col("s").str.split_exact("_", 1)).unnest("s")
print(exact.to_dict(as_series=False))
n1 = df.select(pl.col("s").str.splitn("_", 1)).unnest("s")
print(n1.to_dict(as_series=False))
n2 = df.select(pl.col("s").str.splitn("_", 2)).unnest("s")
print(n2.to_dict(as_series=False))
print(df.select(pl.col("s").str.split("_")).to_series().to_list())
```

Output:

```text
{'field_0': ['a', 'd'], 'field_1': ['b', None]}
{'field_0': ['a_b_c', 'd']}
{'field_0': ['a', 'd'], 'field_1': ['b_c', None]}
[['a', 'b', 'c'], ['d']]
```

## Datetime time unit is inferred from the format string

Applies to: `Expr.str.to_datetime`, `Expr.str.strptime`

When you give a format, `Expr.str.to_datetime` and `Expr.str.strptime` infer the time unit from it. `%.3f` yields `Datetime("ms")`; with no fractional seconds the default is `"us"`. Columns parsed with different formats can therefore end up with different `Datetime` dtypes. Pass `time_unit=` to `Expr.str.to_datetime` to pin the unit, for example `time_unit="ns"`.

```python
import polars as pl

df = pl.DataFrame({"s": ["2024-01-01 00:00:00.123"]})
fmt = "%Y-%m-%d %H:%M:%S%.3f"
inferred = df.select(pl.col("s").str.to_datetime(fmt))
pinned = df.select(pl.col("s").str.to_datetime(fmt, time_unit="ns"))
print(inferred.schema)
print(pinned.schema)
```

Output:

```text
Schema({'s': Datetime(time_unit='ms', time_zone=None)})
Schema({'s': Datetime(time_unit='ns', time_zone=None)})
```

## strip_chars_start strips a character set, not a prefix

Applies to: `Expr.str.strip_chars_start`, `Expr.str.strip_prefix`, `Expr.str.strip_suffix`

`Expr.str.strip_chars_start` treats its argument as a **set** of characters and strips any leading combination of them. So `"fo"` turns `"foofoobar"` into `"bar"` and `"ooze"` into `"ze"`. Once you pass `characters`, leading whitespace is no longer stripped. To remove an exact prefix once, use `Expr.str.strip_prefix`, or `Expr.str.strip_suffix` for the end. If the whole string equals the prefix or suffix, the result is an empty string, not null.

```python
import polars as pl

df = pl.DataFrame({"a": ["foofoobar", "ooze", " foo", "foo", "bar"]})
out = df.with_columns(
    chars=pl.col("a").str.strip_chars_start("fo"),
    prefix=pl.col("a").str.strip_prefix("foo"),
    suffix=pl.col("a").str.strip_suffix("bar"),
)
print(out["a"].to_list())
print(out["chars"].to_list())
print(out["prefix"].to_list())
print(out["suffix"].to_list())
```

Output:

```text
['foofoobar', 'ooze', ' foo', 'foo', 'bar']
['bar', 'ze', ' foo', '', 'bar']
['foobar', 'ooze', ' foo', '', 'bar']
['foofoo', 'ooze', ' foo', 'foo', '']
```

## to_integer raises on bad input unless strict=False

Applies to: `Expr.str.to_integer`

`Expr.str.to_integer` defaults to `strict=True`, so one unparsable string makes the whole query raise. Pass `strict=False` to turn failures into null instead. Use `base=` for binary or hex input. Use `dtype=` to choose the integer type; the default is `Int64`.

```python
import polars as pl

df = pl.DataFrame({"s": ["12", "abc", None]})
try:
    df.select(pl.col("s").str.to_integer())
except Exception as e:
    print("raised:", type(e))
out = df.select(pl.col("s").str.to_integer(strict=False))
print(out["s"].to_list())
hexdf = pl.DataFrame({"h": ["ff", "10"]})
hx = hexdf.select(pl.col("h").str.to_integer(base=16, dtype=pl.Int32))
print(hx["h"].to_list())
print(hx.schema)
```

Output:

```text
raised: <class 'polars.exceptions.ComputeError'>
[12, None, None]
[255, 16]
Schema({'h': Int32})
```

## Date parsing is strict and exact by default

Applies to: `Expr.str.to_date`, `Expr.str.strptime`, `Expr.str.to_datetime`

`Expr.str.to_date`, `Expr.str.to_datetime` and `Expr.str.strptime` default to `strict=True`. One invalid value, such as `2024-02-30`, raises instead of becoming null. They also default to `exact=True`, so any text around the date makes parsing fail. Use `strict=False` to get nulls for bad rows. Use `exact=False` to match the format anywhere in the string, at a performance cost.

```python
import polars as pl

df = pl.DataFrame({"s": ["2024-01-05", "2024-02-30", "due 2024-03-01"]})
try:
    df.select(pl.col("s").str.to_date("%Y-%m-%d"))
except Exception as e:
    print("raised:", type(e))
out = df.select(
    lenient=pl.col("s").str.to_date("%Y-%m-%d", strict=False),
    anywhere=pl.col("s").str.to_date("%Y-%m-%d", strict=False, exact=False),
)
print(out["lenient"].to_list())
print(out["anywhere"].to_list())
```

Output:

```text
raised: <class 'polars.exceptions.InvalidOperationError'>
[datetime.date(2024, 1, 5), None, None]
[datetime.date(2024, 1, 5), None, datetime.date(2024, 3, 1)]
```

## time_zone replaces naive times but converts offset-aware ones

Applies to: `Expr.str.to_datetime`

In `Expr.str.to_datetime`, the `time_zone` argument behaves differently depending on the input. For tz-naive strings it **replaces** the zone, so 12:00 stays 12:00 local time. For strings with an offset it **converts**, so 12:00+0000 becomes 17:30 in Asia/Kolkata. Offset-aware input without `time_zone` comes back in UTC. Check whether your strings carry an offset before assuming which behaviour you get.

```python
import polars as pl

naive = pl.DataFrame({"s": ["2024-01-01 12:00"]})
aware = pl.DataFrame({"s": ["2024-01-01 12:00+0000"]})
replaced = naive.select(
    pl.col("s").str.to_datetime("%Y-%m-%d %H:%M", time_zone="Asia/Kolkata")
).item()
converted = aware.select(
    pl.col("s").str.to_datetime("%Y-%m-%d %H:%M%z", time_zone="Asia/Kolkata")
).item()
print(replaced)
print(converted)
print(aware.select(pl.col("s").str.to_datetime("%Y-%m-%d %H:%M%z")).schema)
```

Output:

```text
2024-01-01 12:00:00+05:30
2024-01-01 17:30:00+05:30
Schema({'s': Datetime(time_unit='us', time_zone='UTC')})
```

## to_decimal is unstable and requires scale

Applies to: `Expr.str.to_decimal`

`Expr.str.to_decimal` is marked unstable and may change without notice. Since 1.33.0, `inference_length` has been removed and the keyword-only `scale` is mandatory. Older code that calls it with no arguments now fails with a `TypeError`. Always pass `scale=`. Values with fewer decimals are padded, so `143.9` becomes `143.90` at scale 2.

```python
import polars as pl

df = pl.DataFrame({"x": ["40.12", "143.9"]})
try:
    df.select(pl.col("x").str.to_decimal())
except Exception as e:
    print("raised:", type(e))
out = df.select(pl.col("x").str.to_decimal(scale=2))
print(out["x"].to_list())
print(out.schema)
```

Output:

```text
raised: <class 'TypeError'>
[Decimal('40.12'), Decimal('143.90')]
Schema({'x': Decimal(precision=38, scale=2)})
```

## Use zfill, not pad_start, for signed numbers

Applies to: `Expr.str.zfill`, `Expr.str.pad_start`

`Expr.str.zfill` inserts zeros **after** a leading `-`, giving `-001`. `Expr.str.pad_start` with `"0"` puts the zeros before the sign, giving the wrong `00-1`. Both are string methods, so cast numeric columns to `pl.String` first. `Expr.str.zfill` is intended for numeric strings; for non-ASCII text the docs recommend `Expr.str.pad_start`.

```python
import polars as pl

df = pl.DataFrame({"a": [-1, 123, None]})
s = pl.col("a").cast(pl.String)
out = df.with_columns(zfill=s.str.zfill(4), pad=s.str.pad_start(4, "0"))
print(out["zfill"].to_list())
print(out["pad"].to_list())
```

Output:

```text
['-001', '0123', None]
['00-1', '0123', None]
```

## Negative n in str.tail drops leading characters

Applies to: `Expr.str.tail`

`Expr.str.tail(-3)` does not mean the same as Python's `s[-3:]`. It returns everything **except the first 3** characters, like `s[3:]`. Use a positive `n` to get the last n characters. `n` counts characters, not bytes. Strings shorter than `n` come back whole, and nulls stay null.

```python
import polars as pl

df = pl.DataFrame({"s": ["dragonfruit", "kiwi", "h\u00e9llo", None]})
out = df.with_columns(
    last3=pl.col("s").str.tail(3),
    neg3=pl.col("s").str.tail(-3),
    last4=pl.col("s").str.tail(4),
)
print(ascii(out["last3"].to_list()))
print(ascii(out["neg3"].to_list()))
print(ascii(out["last4"].to_list()))
```

Output:

```text
['uit', 'iwi', 'llo', None]
['gonfruit', 'i', 'lo', None]
['ruit', 'kiwi', '\xe9llo', None]
```

## Use to_lowercase, to_uppercase and to_titlecase instead of the pandas names lower, upper and title

Applies to: `Expr.str.to_lowercase`, `Expr.str.to_uppercase`, `Expr.str.to_titlecase`, `Expr.str.starts_with`, `Expr.str.ends_with`

pandas habits such as `.str.lower()`, `.str.upper()`, `.str.title()` and `.str.startswith()` do not exist in Polars. They raise `AttributeError` as soon as the attribute is accessed. Use `Expr.str.to_lowercase`, `Expr.str.to_uppercase`, `Expr.str.to_titlecase`, `Expr.str.starts_with` and `Expr.str.ends_with`. A null input gives a null output in all of these; it is not coerced to `False`.

```python
import polars as pl

df = pl.DataFrame({"a": ["hello world", "CAT", None]})
try:
    df.select(pl.col("a").str.lower())
except AttributeError as e:
    print(type(e).__name__)
print(
    df.select(
        lower=pl.col("a").str.to_lowercase(),
        title=pl.col("a").str.to_titlecase(),
        starts=pl.col("a").str.starts_with("he"),
    )
)
```

Output:

```text
AttributeError
shape: (3, 3)
┌─────────────┬─────────────┬────────┐
│ lower       ┆ title       ┆ starts │
│ ---         ┆ ---         ┆ ---    │
│ str         ┆ str         ┆ bool   │
╞═════════════╪═════════════╪════════╡
│ hello world ┆ Hello World ┆ true   │
│ cat         ┆ Cat         ┆ false  │
│ null        ┆ null        ┆ null   │
└─────────────┴─────────────┴────────┘
```

## count_matches treats the pattern as a regex unless literal=True

Applies to: `Expr.str.count_matches`

`Expr.str.count_matches` interprets `pattern` as a regular expression by default. Counting `"."` therefore counts every character, not the dots. Pass `literal=True` to count a plain substring. A null input gives null, not 0.

```python
import polars as pl

df = pl.DataFrame({"s": ["a.b.c", "abc", None]})
print(
    df.with_columns(
        regex=pl.col("s").str.count_matches("."),
        literal=pl.col("s").str.count_matches(".", literal=True),
    )
)
```

Output:

```text
shape: (3, 3)
┌───────┬───────┬─────────┐
│ s     ┆ regex ┆ literal │
│ ---   ┆ ---   ┆ ---     │
│ str   ┆ u32   ┆ u32     │
╞═══════╪═══════╪═════════╡
│ a.b.c ┆ 5     ┆ 2       │
│ abc   ┆ 3     ┆ 0       │
│ null  ┆ null  ┆ null    │
└───────┴───────┴─────────┘
```

## contains_any, replace_many and extract_many match literal strings, never regex

Applies to: `Expr.str.contains_any`, `Expr.str.replace_many`, `Expr.str.extract_many`, `Expr.str.find_many`

The Aho-Corasick methods `Expr.str.contains_any`, `Expr.str.replace_many`, `Expr.str.extract_many` and `Expr.str.find_many` only match string literals. A pattern like `r"\d"` searches for a backslash followed by `d`, not for a digit. These calls raise no error, so the result is silently wrong. Use `Expr.str.contains`, `Expr.str.extract_all` or `Expr.str.replace_all` when you need regex semantics.

```python
import polars as pl

df = pl.DataFrame({"s": ["a1", "b\\d"]})
print(
    df.with_columns(
        any_literal=pl.col("s").str.contains_any([r"\d"]),
        regex=pl.col("s").str.contains(r"\d"),
    )
)
```

Output:

```text
shape: (2, 3)
┌─────┬─────────────┬───────┐
│ s   ┆ any_literal ┆ regex │
│ --- ┆ ---         ┆ ---   │
│ str ┆ bool        ┆ bool  │
╞═════╪═════════════╪═══════╡
│ a1  ┆ false       ┆ true  │
│ b\d ┆ true        ┆ false │
└─────┴─────────────┴───────┘
```

## find_many returns byte offsets, not character positions

Applies to: `Expr.str.find_many`

`Expr.str.find_many` returns a `List<UInt32>` of byte offsets for each match start. With non-ASCII text these offsets are larger than the character index. Do not feed them into character-based slicing such as `Expr.str.slice` and expect the right substring. Compare `Expr.str.len_bytes` with `Expr.str.len_chars` to see the difference.

```python
import polars as pl

df = pl.DataFrame({"s": ["cafe bar", "café bar"]})
print(
    df.with_columns(
        offset=pl.col("s").str.find_many(["bar"]),
        n_bytes=pl.col("s").str.len_bytes(),
        n_chars=pl.col("s").str.len_chars(),
    )
)
```

Output:

```text
shape: (2, 4)
┌──────────┬───────────┬─────────┬─────────┐
│ s        ┆ offset    ┆ n_bytes ┆ n_chars │
│ ---      ┆ ---       ┆ ---     ┆ ---     │
│ str      ┆ list[u32] ┆ u32     ┆ u32     │
╞══════════╪═══════════╪═════════╪═════════╡
│ cafe bar ┆ [5]       ┆ 8       ┆ 8       │
│ café bar ┆ [6]       ┆ 9       ┆ 8       │
└──────────┴───────────┴─────────┴─────────┘
```

## json_decode requires an explicit dtype in 1.38

Applies to: `Expr.str.json_decode`

Since 1.33.0 the `dtype` argument of `Expr.str.json_decode` is mandatory. Older code that calls `.str.json_decode()` and relies on schema inference fails with `TypeError`. The `infer_schema_length` argument is deprecated and ignored. Pass the target type, for example a `pl.Struct` of `pl.Field`s. Invalid JSON raises an error.

```python
import polars as pl

df = pl.DataFrame({"j": ['{"a":1,"b":true}', '{"a":2,"b":false}']})
try:
    df.select(pl.col("j").str.json_decode())
except Exception as e:
    print(type(e).__name__)
dtype = pl.Struct([pl.Field("a", pl.Int64), pl.Field("b", pl.Boolean)])
print(df.select(pl.col("j").str.json_decode(dtype)).unnest("j"))
```

Output:

```text
TypeError
shape: (2, 2)
┌─────┬───────┐
│ a   ┆ b     │
│ --- ┆ ---   │
│ i64 ┆ bool  │
╞═════╪═══════╡
│ 1   ┆ true  │
│ 2   ┆ false │
└─────┴───────┘
```

## json_path_match always returns String, even for numbers and booleans

Applies to: `Expr.str.json_path_match`

`Expr.str.json_path_match` casts every extracted value to `String`, whatever its JSON type. Doing arithmetic or numeric comparisons on the result is wrong: comparisons are lexical, and math fails. Cast explicitly with `Expr.cast`. If you need typed fields, use `Expr.str.json_decode` with a dtype. A missing path or a null input gives null.

```python
import polars as pl

df = pl.DataFrame({"j": ['{"a":10}', '{"a":9}', None]})
m = df.select(a=pl.col("j").str.json_path_match("$.a"))
print(m.schema)
print(m.select(pl.col("a").max()))
print(m.select(pl.col("a").cast(pl.Int64).max()))
```

Output:

```text
Schema({'a': String})
shape: (1, 1)
┌─────┐
│ a   │
│ --- │
│ str │
╞═════╡
│ 9   │
└─────┘
shape: (1, 1)
┌─────┐
│ a   │
│ --- │
│ i64 │
╞═════╡
│ 10  │
└─────┘
```

## extract_groups names unnamed groups "1", "2", ... as strings

Applies to: `Expr.str.extract_groups`, `Expr.str.extract`

`Expr.str.extract_groups` returns a `Struct` whose fields are all `String`. Unnamed capture groups get their position as a string name (`"1"`, `"2"`). Access them with `Expr.struct.field("1")` or use named groups such as `(?<key>...)`. Rows where the pattern does not match give null fields, and `Expr.str.extract` likewise returns null rather than an empty string.

```python
import polars as pl

df = pl.DataFrame({"s": ["k=1", "no match"]})
out = df.select(g=pl.col("s").str.extract_groups(r"(\w)=(\d)"))
print(out.unnest("g").columns)
print(out.select(pl.col("g").struct.field("2")))
named = df.select(g=pl.col("s").str.extract_groups(r"(?<key>\w)=(?<val>\d)"))
print(named.unnest("g"))
```

Output:

```text
['1', '2']
shape: (2, 1)
┌──────┐
│ 2    │
│ ---  │
│ str  │
╞══════╡
│ 1    │
│ null │
└──────┘
shape: (2, 2)
┌──────┬──────┐
│ key  ┆ val  │
│ ---  ┆ ---  │
│ str  ┆ str  │
╞══════╪══════╡
│ k    ┆ 1    │
│ null ┆ null │
└──────┴──────┘
```

## Replace deprecated str.explode with str.split("").explode(), noting that empty strings become null

Applies to: `Expr.str.explode`

`Expr.str.explode` is deprecated since 0.20.31. The replacement is `Expr.str.split` with `""` followed by `Expr.explode`. The behaviour differs: an empty string now yields a null row instead of being preserved. If you need the old behaviour, handle empty lists with `pl.when` before exploding.

```python
import polars as pl

df = pl.DataFrame({"a": ["ab", ""]})
out = df.select(pl.col("a").str.split("").explode())
print(out)
print(out.null_count())
```

Output:

```text
shape: (3, 1)
┌──────┐
│ a    │
│ ---  │
│ str  │
╞══════╡
│ a    │
│ b    │
│ null │
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

## decode raises on invalid input unless strict=False

Applies to: `Expr.str.decode`

`Expr.str.decode` defaults to `strict=True`, so one malformed hex or base64 value fails the whole query. Pass `strict=False` to turn undecodable values into null. The result dtype is `Binary`, not `String`.

```python
import polars as pl

df = pl.DataFrame({"h": ["ff00", "zz"]})
try:
    df.select(pl.col("h").str.decode("hex"))
except Exception as e:
    print(type(e).__name__)
print(df.select(pl.col("h").str.decode("hex", strict=False)))
```

Output:

```text
ComputeError
shape: (2, 1)
┌─────────────┐
│ h           │
│ ---         │
│ binary      │
╞═════════════╡
│ b"\xff\x00" │
│ null        │
└─────────────┘
```
