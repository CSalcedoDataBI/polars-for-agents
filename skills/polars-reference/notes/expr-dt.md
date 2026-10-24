# Expr.dt: traps

Drafted with Claude and checked by machine against polars 1.38.1: every name below is in
`catalog/polars-1.38.1.json`, and every example was run on that version. The output
under each example is what it printed.

## to_string defaults to ISO with a space; use iso:strict for the T separator

Applies to: `Expr.dt.to_string`, `Expr.dt.strftime`

Calling `Expr.dt.to_string()` with no format on a Datetime gives ISO date and time parts separated by a space, not by `T`. APIs that expect strict ISO 8601 may reject that output. Pass `'iso:strict'` to get the `T` separator, or give an explicit chrono format. `Expr.dt.strftime` is an alias of `Expr.dt.to_string` but requires a format. Duration columns cannot use strftime patterns at all; only `'iso'` and `'polars'` are supported for them.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({"ts": [datetime(2024, 5, 1, 8, 30)]})
print(df.select(
    default_iso=pl.col("ts").dt.to_string(),
    iso_strict=pl.col("ts").dt.to_string("iso:strict"),
    custom=pl.col("ts").dt.strftime("%Y-%m-%dT%H:%M"),
).rows())
```

Output:

```text
[('2024-05-01 08:30:00.000000', '2024-05-01T08:30:00.000000', '2024-05-01T08:30')]
```

## replace_time_zone relabels the wall clock, convert_time_zone keeps the instant

Applies to: `Expr.dt.replace_time_zone`, `Expr.dt.convert_time_zone`

`Expr.dt.replace_time_zone` keeps the wall-clock reading, attaches a new zone and ignores the original zone, so the underlying timestamp changes. `Expr.dt.convert_time_zone` keeps the same instant and only changes how it is displayed. Calling `Expr.dt.convert_time_zone` on a naive column treats the values as UTC, whatever your system zone is. To declare which zone naive data is in, call `Expr.dt.replace_time_zone` first, then `Expr.dt.convert_time_zone`.

```python
import polars as pl
from datetime import datetime

fmt = "%Y-%m-%d %H:%M %z"
df = pl.DataFrame({"ts": [datetime(2024, 7, 1, 12, 0)]})
utc = df.with_columns(pl.col("ts").dt.replace_time_zone("UTC"))
out = utc.select(
    converted=pl.col("ts").dt.convert_time_zone("Europe/Amsterdam"),
    replaced=pl.col("ts").dt.replace_time_zone("Europe/Amsterdam"),
)
print(out.select(pl.all().dt.to_string(fmt)).rows())
# Different instants: epoch seconds differ by 7200
print(out.select(
    conv_s=pl.col("converted").dt.epoch("s"),
    repl_s=pl.col("replaced").dt.epoch("s"),
).rows())
# Naive input to convert_time_zone is treated as UTC (14:00 +0200)
naive_conv = pl.col("ts").dt.convert_time_zone("Europe/Amsterdam")
print(df.select(naive_conv.dt.to_string(fmt)).rows())
# Correct way to say naive data is local Amsterdam time (12:00 +0200)
local = pl.col("ts").dt.replace_time_zone("Europe/Amsterdam")
print(df.select(local.dt.to_string(fmt)).rows())
```

Output:

```text
[('2024-07-01 14:00 +0200', '2024-07-01 12:00 +0200')]
[(1719835200, 1719828000)]
[('2024-07-01 14:00 +0200',)]
[('2024-07-01 12:00 +0200',)]
```

## Use replace_time_zone(None) instead of the deprecated dt.datetime

Applies to: `Expr.dt.datetime`, `Expr.dt.replace_time_zone`

`Expr.dt.datetime` has been deprecated since 0.20.4 and emits a deprecation warning. Its job was to drop the time zone from a Datetime column, and `Expr.dt.replace_time_zone(None)` does the same thing. It keeps the wall-clock values and removes the zone, so use it in new code.

```python
import polars as pl
import warnings
from datetime import datetime

df = pl.DataFrame(
    {"ts": [datetime(2024, 1, 1, 9, 30)]},
    schema={"ts": pl.Datetime(time_zone="UTC")},
)
with warnings.catch_warnings():
    warnings.simplefilter("error")
    try:
        df.select(pl.col("ts").dt.datetime())
    except Exception as e:
        print(str(type(e)).split("'")[1].split(".")[-1])

out = df.with_columns(naive=pl.col("ts").dt.replace_time_zone(None))
print(out.schema)
print(out.to_dicts())
```

Output:

```text
DeprecationWarning
Schema({'ts': Datetime(time_unit='us', time_zone='UTC'), 'naive': Datetime(time_unit='us', time_zone=None)})
[{'ts': datetime.datetime(2024, 1, 1, 9, 30, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'naive': datetime.datetime(2024, 1, 1, 9, 30)}]
```

## epoch and timestamp default to microseconds, not Unix seconds

Applies to: `Expr.dt.epoch`, `Expr.dt.timestamp`

`Expr.dt.epoch()` and `Expr.dt.timestamp()` both default to `time_unit='us'`. Code that expects Unix seconds or nanoseconds will be off by a large factor. For Unix seconds, pass `Expr.dt.epoch(time_unit='s')`. `Expr.dt.timestamp` only accepts `'ns'`, `'us'` and `'ms'`, so use `Expr.dt.epoch` when you need seconds or days.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({"ts": [datetime(2001, 1, 1)]})
out = df.select(
    epoch_default_us=pl.col("ts").dt.epoch(),
    timestamp_default_us=pl.col("ts").dt.timestamp(),
    unix_seconds=pl.col("ts").dt.epoch(time_unit="s"),
    unix_days=pl.col("ts").dt.epoch(time_unit="d"),
    unix_ms=pl.col("ts").dt.timestamp("ms"),
)
print(out.to_dicts())
```

Output:

```text
[{'epoch_default_us': 978307200000000, 'timestamp_default_us': 978307200000000, 'unix_seconds': 978307200, 'unix_days': 11323, 'unix_ms': 978307200000}]
```

## second() drops fractions and the sub-second fields are not additive

Applies to: `Expr.dt.second`, `Expr.dt.millisecond`, `Expr.dt.microsecond`, `Expr.dt.nanosecond`

`Expr.dt.second` returns an integer (Int8) by default, so 14.5 seconds comes back as 14. Pass `fractional=True` to get a Float64. `Expr.dt.millisecond`, `Expr.dt.microsecond` and `Expr.dt.nanosecond` each return the whole fractional part of the second in a different unit, so .5 s gives 500, 500000 and 500000000. Never add them together; pick the one unit you need.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({"ts": [datetime(2024, 1, 1, 0, 0, 14, 500_000)]})
out = df.select(
    sec=pl.col("ts").dt.second(),
    sec_frac=pl.col("ts").dt.second(fractional=True),
    ms=pl.col("ts").dt.millisecond(),
    us=pl.col("ts").dt.microsecond(),
    ns=pl.col("ts").dt.nanosecond(),
    wrong_total_us=pl.col("ts").dt.millisecond() * 1000
    + pl.col("ts").dt.microsecond(),
)
print(out.schema)
print(out.to_dicts())
```

Output:

```text
Schema({'sec': Int8, 'sec_frac': Float64, 'ms': Int32, 'us': Int32, 'ns': Int32, 'wrong_total_us': Int32})
[{'sec': 14, 'sec_frac': 14.5, 'ms': 500, 'us': 500000, 'ns': 500000000, 'wrong_total_us': 1000000}]
```

## Use offset_by for calendar months and years, and remember 1m means minute

Applies to: `Expr.dt.offset_by`

Adding a `timedelta` adds a fixed span of time, so adding 30 or 365 days drifts away from "one month later" or "one year later", especially across leap years. `Expr.dt.offset_by` understands calendar months and years. In its offset language `'1m'` means one minute and `'1mo'` means one calendar month, so writing `'1m'` for a month gives silently wrong results. A negative offset uses a single leading minus sign, for example `'-1y2mo'`.

```python
import polars as pl
from datetime import datetime, timedelta

df = pl.DataFrame({"d": [datetime(2024, 1, 15), datetime(2023, 3, 1)]})
out = df.with_columns(
    plus_30d=pl.col("d") + timedelta(days=30),
    plus_1mo=pl.col("d").dt.offset_by("1mo"),
    plus_365d=pl.col("d") + timedelta(days=365),
    plus_1y=pl.col("d").dt.offset_by("1y"),
    oops_1m_is_minute=pl.col("d").dt.offset_by("1m"),
    minus_1y2mo=pl.col("d").dt.offset_by("-1y2mo"),
)
for row in out.select(pl.all().dt.to_string("%Y-%m-%d %H:%M")).to_dicts():
    print(row)
```

Output:

```text
{'d': '2024-01-15 00:00', 'plus_30d': '2024-02-14 00:00', 'plus_1mo': '2024-02-15 00:00', 'plus_365d': '2025-01-14 00:00', 'plus_1y': '2025-01-15 00:00', 'oops_1m_is_minute': '2024-01-15 00:01', 'minus_1y2mo': '2022-11-15 00:00'}
{'d': '2023-03-01 00:00', 'plus_30d': '2023-03-31 00:00', 'plus_1mo': '2023-04-01 00:00', 'plus_365d': '2024-02-29 00:00', 'plus_1y': '2024-03-01 00:00', 'oops_1m_is_minute': '2023-03-01 00:01', 'minus_1y2mo': '2022-01-01 00:00'}
```

## dt.round goes to the nearest bucket boundary; use dt.truncate to floor

Applies to: `Expr.dt.round`, `Expr.dt.truncate`

`Expr.dt.round` maps values in the first half of an interval to the start of the bucket and values in the second half to the end of the bucket, so 01:40 rounded to `'1h'` becomes 02:00. If you want every value floored to the start of its bucket (for example for hourly grouping keys), use `Expr.dt.truncate` instead. Also remember that `'1m'` is minutes and `'1mo'` is months in `every`.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({"ts": [
    datetime(2024, 1, 1, 1, 20),
    datetime(2024, 1, 1, 1, 40),
]})
out = df.with_columns(
    rounded=pl.col("ts").dt.round("1h"),
    truncated=pl.col("ts").dt.truncate("1h"),
)
print(out.columns)
print(out.select(pl.all().dt.to_string("%H:%M")).rows())
```

Output:

```text
['ts', 'rounded', 'truncated']
[('01:20', '01:00', '01:00'), ('01:40', '02:00', '01:00')]
```

## add_business_days raises on weekend start dates unless you set roll

Applies to: `Expr.dt.add_business_days`, `Expr.dt.is_business_day`

`Expr.dt.add_business_days` defaults to `roll='raise'`, so the whole query fails if any start date falls on a non-business day. Pass `roll='forward'` or `roll='backward'` to say how such dates should move before counting. Use `Expr.dt.is_business_day` to find the offending rows first. Both `Expr.dt.add_business_days` and `Expr.dt.is_business_day` are marked unstable and may change without notice.

```python
import polars as pl
from datetime import date

# 2020-01-04 is a Saturday, 2020-01-06 is a Monday
df = pl.DataFrame({"start": [date(2020, 1, 4), date(2020, 1, 6)]})
try:
    df.select(pl.col("start").dt.add_business_days(1))
except Exception as e:
    print(str(type(e)).split("'")[1].split(".")[-1])

out = df.with_columns(
    is_bday=pl.col("start").dt.is_business_day(),
    fwd=pl.col("start").dt.add_business_days(1, roll="forward"),
    back=pl.col("start").dt.add_business_days(1, roll="backward"),
)
for row in out.to_dicts():
    print(row)
```

Output:

```text
ComputeError
{'start': datetime.date(2020, 1, 4), 'is_bday': False, 'fwd': datetime.date(2020, 1, 7), 'back': datetime.date(2020, 1, 6)}
{'start': datetime.date(2020, 1, 6), 'is_bday': True, 'fwd': datetime.date(2020, 1, 7), 'back': datetime.date(2020, 1, 7)}
```

## total_* duration accessors truncate to whole units by default

Applies to: `Expr.dt.total_days`, `Expr.dt.total_hours`, `Expr.dt.total_minutes`, `Expr.dt.total_seconds`, `Expr.dt.total_milliseconds`, `Expr.dt.total_microseconds`

pandas `Timedelta.total_seconds()` returns a float. The Polars `Expr.dt.total_*` methods default to `fractional=False` and return `Int64`, so the partial unit is dropped. A 90-minute duration gives `1` from `Expr.dt.total_hours`, and 59 seconds gives `0` from `Expr.dt.total_minutes`. Pass `fractional=True` to get a `Float64` that keeps the fractional part.

```python
import polars as pl
from datetime import timedelta

df = pl.DataFrame({"d": [timedelta(minutes=90), timedelta(seconds=59)]})
out = df.select(
    hours_int=pl.col("d").dt.total_hours(),
    hours_frac=pl.col("d").dt.total_hours(fractional=True),
    minutes_int=pl.col("d").dt.total_minutes(),
    minutes_frac=pl.col("d").dt.total_minutes(fractional=True),
)
for row in out.to_dicts():
    print(row)
print(out.schema)
```

Output:

```text
{'hours_int': 1, 'hours_frac': 1.5, 'minutes_int': 90, 'minutes_frac': 90.0}
{'hours_int': 0, 'hours_frac': 0.016388888888888887, 'minutes_int': 0, 'minutes_frac': 0.9833333333333334}
Schema({'hours_int': Int64, 'hours_frac': Float64, 'minutes_int': Int64, 'minutes_frac': Float64})
```

## weekday is ISO: Monday is 1 and Sunday is 7, not 0 to 6

Applies to: `Expr.dt.weekday`

pandas `dayofweek` numbers Monday as 0 and Sunday as 6. `Expr.dt.weekday` returns the ISO weekday instead, with Monday = 1 and Sunday = 7. A ported weekend filter such as `weekday >= 5` silently tags Fridays as weekend days. In Polars, test for weekends with `>= 6`.

```python
import polars as pl
from datetime import date

df = pl.DataFrame(
    {"date": pl.date_range(date(2024, 1, 5), date(2024, 1, 8), eager=True)}
)  # Fri, Sat, Sun, Mon
out = df.with_columns(wd=pl.col("date").dt.weekday()).with_columns(
    pandas_habit_weekend=pl.col("wd") >= 5,
    correct_weekend=pl.col("wd") >= 6,
)
print(out.columns)
for row in out.rows():
    print(row)
```

Output:

```text
['date', 'wd', 'pandas_habit_weekend', 'correct_weekend']
(datetime.date(2024, 1, 5), 5, True, False)
(datetime.date(2024, 1, 6), 6, True, True)
(datetime.date(2024, 1, 7), 7, True, True)
(datetime.date(2024, 1, 8), 1, False, False)
```

## Pair ISO week with iso_year, not year

Applies to: `Expr.dt.week`, `Expr.dt.year`, `Expr.dt.iso_year`

`Expr.dt.week` returns the ISO week number, from 1 to 53. Dates in early January can belong to week 52 or 53 of the previous ISO year, and late-December dates can belong to week 1 of the next one. `Expr.dt.year` returns the calendar year, so grouping by (`year`, `week`) mixes days from different weeks into one bucket. Group by `Expr.dt.iso_year` together with `Expr.dt.week` instead.

```python
import polars as pl
from datetime import date

df = pl.DataFrame({"date": [date(2021, 1, 1), date(2021, 1, 4), date(2024, 12, 30)]})
out = df.with_columns(
    year=pl.col("date").dt.year(),
    iso_year=pl.col("date").dt.iso_year(),
    week=pl.col("date").dt.week(),
)
print(out.columns)
for row in out.rows():
    print(row)
```

Output:

```text
['date', 'year', 'iso_year', 'week']
(datetime.date(2021, 1, 1), 2021, 2020, 53)
(datetime.date(2021, 1, 4), 2021, 2021, 1)
(datetime.date(2024, 12, 30), 2024, 2025, 1)
```

## truncate('7d') is not truncate('1w'): non-weekly buckets start at the Unix epoch

Applies to: `Expr.dt.truncate`

With `Expr.dt.truncate`, weekly buckets (`'1w'`) start on Monday, but all other buckets start on the Unix epoch, 1970-01-01, which was a Thursday. As a result, `truncate('7d')` produces Thursday-aligned buckets, not Monday ones. Use `'1w'` when you want calendar weeks, and remember that multi-day buckets such as `'2d'` are aligned to the epoch, not to your data.

```python
import polars as pl
from datetime import date

df = pl.DataFrame({"d": [date(2024, 1, 10)]})  # a Wednesday
out = df.with_columns(
    by_1w=pl.col("d").dt.truncate("1w"),
    by_7d=pl.col("d").dt.truncate("7d"),
).with_columns(
    by_1w_weekday=pl.col("by_1w").dt.weekday(),
    by_7d_weekday=pl.col("by_7d").dt.weekday(),
)
for row in out.to_dicts():
    print(row)
```

Output:

```text
{'d': datetime.date(2024, 1, 10), 'by_1w': datetime.date(2024, 1, 8), 'by_7d': datetime.date(2024, 1, 4), 'by_1w_weekday': 1, 'by_7d_weekday': 4}
```

## with_time_unit is deprecated and reinterprets rather than converts

Applies to: `Expr.dt.with_time_unit`

`Expr.dt.with_time_unit` has been deprecated since 0.20.5. It does not modify the underlying integers; it only relabels the unit, so an `ns` column relabelled as `us` jumps tens of thousands of years. If you really need to fix a wrongly labelled unit, cast to `Int64` and then cast to the desired `pl.Datetime`/`pl.Duration`. If you want the same instant in another unit, use `Expr.dt.cast_time_unit`.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({"ts": [datetime(2001, 1, 1)]}).with_columns(
    pl.col("ts").cast(pl.Datetime("ns"))
)
out = df.select(
    pl.col("ts"),
    relabel=pl.col("ts").cast(pl.Int64).cast(pl.Datetime("us")),
    convert=pl.col("ts").dt.cast_time_unit("us"),
)
print(out.schema)
print(out.select(pl.all().cast(pl.String)).rows())
```

Output:

```text
Schema({'ts': Datetime(time_unit='ns', time_zone=None), 'relabel': Datetime(time_unit='us', time_zone=None), 'convert': Datetime(time_unit='us', time_zone=None)})
[('2001-01-01 00:00:00.000000000', '+32971-04-28 00:00:00.000000', '2001-01-01 00:00:00.000000')]
```

## total_* requires a Duration column, not a Datetime

Applies to: `Expr.dt.total_days`, `Expr.dt.total_seconds`

The `Expr.dt.total_*` methods extract totals from a `Duration` type. Calling them directly on a `Datetime` column raises an error instead of returning time since the epoch. First build a duration, by subtracting two datetimes or with `Expr.diff`; note that `Expr.diff` yields `null` on the first row. Also pass `fractional=True` if partial days matter.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame(
    {"start": [datetime(2024, 1, 1)], "end": [datetime(2024, 1, 3, 12)]}
)
try:
    df.select(pl.col("end").dt.total_days())
except Exception as e:
    print(repr(e).split("(")[0])

dur = pl.col("end") - pl.col("start")
out = df.select(
    days=dur.dt.total_days(),
    days_frac=dur.dt.total_days(fractional=True),
)
print(out.to_dicts())
```

Output:

```text
SchemaError
[{'days': 2, 'days_frac': 2.5}]
```

## `Expr.dt.century` and `Expr.dt.millennium` use calendar counting, not `year // 100`

Applies to: `Expr.dt.century`, `Expr.dt.millennium`

`Expr.dt.century` returns the ordinal century, so 2000 is century 20 and 2001 is century 21. `Expr.dt.millennium` works the same way, so 2000 is millennium 2. If you want buckets such as "the 1900s" or "the 2000s", these results will be off by one at the boundary years. For decade or century buckets, use integer division on `Expr.dt.year` instead.

```python
import polars as pl
from datetime import date

df = pl.DataFrame({"d": [date(1999, 6, 1), date(2000, 1, 1), date(2001, 1, 1)]})
out = df.with_columns(
    century=pl.col("d").dt.century(),
    hundreds_bucket=pl.col("d").dt.year() // 100,
    millennium=pl.col("d").dt.millennium(),
    thousands_bucket=pl.col("d").dt.year() // 1000,
)
print(out)
```

Output:

```text
shape: (3, 5)
┌────────────┬─────────┬─────────────────┬────────────┬──────────────────┐
│ d          ┆ century ┆ hundreds_bucket ┆ millennium ┆ thousands_bucket │
│ ---        ┆ ---     ┆ ---             ┆ ---        ┆ ---              │
│ date       ┆ i32     ┆ i32             ┆ i32        ┆ i32              │
╞════════════╪═════════╪═════════════════╪════════════╪══════════════════╡
│ 1999-06-01 ┆ 20      ┆ 19              ┆ 2          ┆ 1                │
│ 2000-01-01 ┆ 20      ┆ 20              ┆ 2          ┆ 2                │
│ 2001-01-01 ┆ 21      ┆ 20              ┆ 3          ┆ 2                │
└────────────┴─────────┴─────────────────┴────────────┴──────────────────┘
```

## `Expr.dt.month_end` keeps the time of day, so it is not an end-of-month cutoff

Applies to: `Expr.dt.month_end`, `Expr.dt.month_start`

For Datetime columns, `Expr.dt.month_end` and `Expr.dt.month_start` move only the date and keep the original time of day. A value at 02:00 rolls forward to the last day of the month at 02:00, not to the end of that day. Using the result as an inclusive upper bound therefore silently drops later events on the last day. Compare at Date granularity with `Expr.dt.date` instead, or build an explicit exclusive bound.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({"ts": [datetime(2000, 1, 15, 2), datetime(2000, 1, 31, 18), datetime(2000, 2, 1, 1)]})
cutoff = pl.col("ts").min().dt.month_end()
print(df.select(cutoff.alias("cutoff")))
wrong = df.filter(pl.col("ts") <= cutoff)
right = df.filter(pl.col("ts").dt.date() <= cutoff.dt.date())
print("wrong rows:", wrong.height)
print("right rows:", right.height)
```

Output:

```text
shape: (1, 1)
┌─────────────────────┐
│ cutoff              │
│ ---                 │
│ datetime[μs]        │
╞═════════════════════╡
│ 2000-01-31 02:00:00 │
└─────────────────────┘
wrong rows: 1
right rows: 2
```

## `Expr.dt.time` fails on Date columns

Applies to: `Expr.dt.time`

`Expr.dt.time` works only on Datetime columns and raises an error on a Date column. If a column might be Date, for example after parsing with `Expr.str.to_date`, cast it to `pl.Datetime` first. Alternatively, use `Expr.dt.combine` to attach a time explicitly.

```python
import polars as pl
from datetime import date

df = pl.DataFrame({"d": [date(2024, 1, 1), date(2024, 6, 30)]})
try:
    df.select(pl.col("d").dt.time())
except Exception as e:
    print(type(e).__name__)
print(df.select(pl.col("d").cast(pl.Datetime).dt.time().alias("t")))
```

Output:

```text
ComputeError
shape: (2, 1)
┌──────────┐
│ t        │
│ ---      │
│ time     │
╞══════════╡
│ 00:00:00 │
│ 00:00:00 │
└──────────┘
```

## `Expr.dt.cast_time_unit` to a coarser unit loses precision

Applies to: `Expr.dt.cast_time_unit`

`Expr.dt.cast_time_unit` changes the stored unit of a Datetime, and casting to a coarser unit (for example 'us' to 'ms') discards the sub-unit part. Casting back to the finer unit does not restore the lost digits. Downcast only when you are sure the extra precision is not needed, for example when matching a join key from another source.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({"ts": [datetime(2024, 1, 1, 0, 0, 0, 123456)]})
out = df.select(
    original_us=pl.col("ts").dt.microsecond(),
    via_ms=pl.col("ts").dt.cast_time_unit("ms").dt.cast_time_unit("us").dt.microsecond(),
)
print(out)
```

Output:

```text
shape: (1, 2)
┌─────────────┬────────┐
│ original_us ┆ via_ms │
│ ---         ┆ ---    │
│ i32         ┆ i32    │
╞═════════════╪════════╡
│ 123456      ┆ 123000 │
└─────────────┴────────┘
```

## `Expr.dt.base_utc_offset` alone is not the UTC offset during DST

Applies to: `Expr.dt.base_utc_offset`, `Expr.dt.dst_offset`

`Expr.dt.base_utc_offset` returns only the zone's base offset, and `Expr.dt.dst_offset` returns the additional daylight-saving offset. The actual offset from UTC in effect at that moment is the sum of the two. Using the base offset alone is silently wrong by an hour throughout summer time.

```python
import polars as pl
from datetime import datetime

df = pl.DataFrame({"ts": [datetime(2020, 7, 1), datetime(2020, 12, 1)]})
df = df.with_columns(pl.col("ts").dt.replace_time_zone("Europe/London"))
out = df.with_columns(
    base=pl.col("ts").dt.base_utc_offset(),
    dst=pl.col("ts").dt.dst_offset(),
    total=pl.col("ts").dt.base_utc_offset() + pl.col("ts").dt.dst_offset(),
)
print(out)
```

Output:

```text
shape: (2, 4)
┌─────────────────────────────┬──────────────┬──────────────┬──────────────┐
│ ts                          ┆ base         ┆ dst          ┆ total        │
│ ---                         ┆ ---          ┆ ---          ┆ ---          │
│ datetime[μs, Europe/London] ┆ duration[ms] ┆ duration[ms] ┆ duration[ms] │
╞═════════════════════════════╪══════════════╪══════════════╪══════════════╡
│ 2020-07-01 00:00:00 BST     ┆ 0ms          ┆ 1h           ┆ 1h           │
│ 2020-12-01 00:00:00 GMT     ┆ 0ms          ┆ 0ms          ┆ 0ms          │
└─────────────────────────────┴──────────────┴──────────────┴──────────────┘
```
