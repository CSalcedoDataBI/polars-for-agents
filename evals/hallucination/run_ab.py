#!/usr/bin/env python3
"""Measure the one thing this library exists for: does the reference stop invented names?

Same design as powerquery-m-for-agents and dax-for-agents (their evals/hallucination/run_ab.py),
ported to Polars. Every question is asked twice, of the same model:

    arm A   the question alone
    arm B   the question, plus the catalogue rows of its category

Arm B is deliberately NOT the card that holds the answer. Handing over the answer would measure
obedience, not invention. The rows are names and one-line summaries -- the first hop an agent
makes (find the function, then open it) -- so arm B knows what exists and still has to choose.

## The metric is mechanical

No model judges another. Every name an answer writes in code (```python blocks and inline spans)
is looked up against the exported catalogue with the repo's OWN checker, scripts/catalog_names.py
-- the exact same authority CI enforces on skills/. A `pl.<x>`, `cs.<x>`, `<expr>.<method>` or
`DataFrame.<method>` the catalogue does not have is an invention. Parameter and parse errors the
checker also reports are NOT counted here: the metric is invented names only.

    python evals/hallucination/run_ab.py --limit 3          # a few questions
    python evals/hallucination/run_ab.py --out run.json     # the whole bank
    python evals/hallucination/run_ab.py --replay run.json  # re-count, no API calls
    python evals/hallucination/run_ab.py --out run.json --resume   # finish an interrupted run

The provider is read from the model's name, and each has its own key variable: ANTHROPIC_API_KEY
for `claude-*`, DEEPSEEK_API_KEY for `deepseek-*`. A key is read from the environment and nowhere
else: never passed on the command line, never printed, never written into the output file.
"""
import argparse
import json
import os
import sys

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed (pip install pyyaml)")
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import catalog_names as cn  # noqa: E402

QUESTIONS = os.path.join(HERE, "questions.yaml")


# --- the catalogue: valid names, and the per-category rows arm B is given --------------------

def catalog_rows():
    """`name: summary` rows of every catalogue group, keyed by the group name (the category a
    question names). These are what arm B is handed."""
    data = json.loads(cn.catalog_path().read_text(encoding="utf-8"))
    rows = {}
    for group, entries in data["groups"].items():
        rows[group] = [f"- {e['name']}: {e.get('summary') or ''}".rstrip(": ")
                       for e in entries]
    return rows


# Real Polars methods the repo checker does not know, because they live on the When/Then
# conditional builders -- classes that are not among the catalogue's member groups (Expr,
# DataFrame, LazyFrame, Series, the accessors). The skills avoid the blind spot by writing
# `pl.when(...).then(...)` only in prose, where the inline regex does not match the chain; a
# model answers in a ```python block, where check_code's AST walk flags `.then`/`.otherwise`.
# Allowlisting them here keeps a valid idiom from being miscounted as a hallucination, without
# changing the CI checker. A name that is genuinely invented is still flagged.
KNOWN_VALID_UNCHECKED = frozenset({"then", "otherwise"})


def invented(text):
    """Invented Polars names in an answer's RUNNABLE CODE (```python blocks), minus parameter and
    parse errors (not name inventions) and the known builder methods the checker misses.

    Only fenced code is scanned, not inline prose: a model naming a dead or wrong API in a
    sentence to contrast it ("not `with_column`, use `with_columns`") is not inventing it. A name
    the model commits to in code it means to run is the hallucination this measures."""
    out = []
    for block in cn.CODE_BLOCK.findall(text or ""):
        for e in cn.check_code(block):
            if "does not parse" in e or "takes `" in e:
                continue
            # Match the EXACT reported attribute (the checker backticks it, `.then`), not a
            # substring of the message: a substring would also swallow an invented `.then_fill`.
            if any(f"`.{n}`" in e for n in KNOWN_VALID_UNCHECKED):
                continue
            out.append(e)
    return out


# --- asking a model (provider by name; standard library only) --------------------------------

MAX_TOKENS = 4000

SYSTEM = ("You are a Polars developer answering a colleague. Be brief: name the Polars "
          "functions and expression methods involved and show a short snippet. Do not hedge "
          "with lists of alternatives you are unsure about.")


def _user(question, reference):
    if not reference:
        return question
    return (f"{question}\n\n---\nPolars names available in this category, from the API "
            f"reference:\n\n{reference}")


def _anthropic_request(model, question, reference, system, max_tokens):
    return {"model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": _user(question, reference)}]}


def _anthropic_read(out):
    usage = dict(out.get("usage", {}))
    usage["stop_reason"] = out.get("stop_reason")
    text = "".join(b.get("text", "") for b in out.get("content", []))
    return text, usage


def _openai_request(model, question, reference, system, max_tokens):
    return {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": _user(question, reference)}]}


def _openai_read(out):
    choice = (out.get("choices") or [{}])[0]
    raw = out.get("usage", {}) or {}
    usage = {"input_tokens": raw.get("prompt_tokens", 0),
             "output_tokens": raw.get("completion_tokens", 0),
             "stop_reason": choice.get("finish_reason")}
    return (choice.get("message") or {}).get("content") or "", usage


PROVIDERS = {
    "anthropic": {
        "prefixes": ("claude-",),
        "url": "https://api.anthropic.com/v1/messages",
        "key_env": "ANTHROPIC_API_KEY",
        "headers": lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01",
                                "content-type": "application/json"},
        "request": _anthropic_request,
        "read": _anthropic_read,
    },
    "deepseek": {
        "prefixes": ("deepseek-",),
        "url": "https://api.deepseek.com/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "headers": lambda key: {"Authorization": f"Bearer {key}",
                                "content-type": "application/json"},
        "request": _openai_request,
        "read": _openai_read,
    },
}


def provider_for(model):
    for name, spec in PROVIDERS.items():
        if model.startswith(spec["prefixes"]):
            return name, spec
    raise SystemExit(f"ERROR: no provider is configured for '{model}'. Known prefixes: "
                     + ", ".join(p for s in PROVIDERS.values() for p in s["prefixes"]))


def ask(model, key, question, reference=None, timeout=180):
    import urllib.request
    _, spec = provider_for(model)
    body = json.dumps(spec["request"](model, question, reference, SYSTEM, MAX_TOKENS)).encode()
    req = urllib.request.Request(spec["url"], data=body, headers=spec["headers"](key))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.load(r)
    return spec["read"](out)


def describe(exc):
    import urllib.error
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
            message = (body.get("error") or {}).get("message") or json.dumps(body)[:200]
        except Exception:  # noqa: BLE001
            message = exc.reason
        return f"HTTP {exc.code}: {message}"
    return f"{type(exc).__name__}: {exc}"


# --- counting and reporting ------------------------------------------------------------------

def answered(rec):
    """Both arms said something and neither was a refusal. Only these are compared: an empty or
    refused arm scores zero inventions for not answering, which would flatter it."""
    return all((rec[arm].get("text") or "").strip()
               and rec[arm].get("stop_reason") != "refusal" for arm in ("A", "B"))


def summarise(records):
    by_regime = {}
    for rec in records:
        slot = by_regime.setdefault(rec["regime"], {"n": 0, "A": 0, "B": 0,
                                                    "A_q": 0, "B_q": 0, "dropped": 0})
        if not answered(rec):
            slot["dropped"] += 1
            continue
        slot["n"] += 1
        for arm in ("A", "B"):
            bad = invented(rec[arm]["text"])
            slot[arm] += len(bad)
            slot[arm + "_q"] += 1 if bad else 0
    return by_regime


def refusals(records):
    return [f"{r['id']} {arm}" for r in records for arm in ("A", "B")
            if r[arm].get("stop_reason") == "refusal"]


def report(records):
    print()
    print(f"{'question':<28} {'regime':<6} {'invented A':>11} {'invented B':>11}")
    print("-" * 60)
    for rec in records:
        a = invented(rec["A"]["text"])
        b = invented(rec["B"]["text"])
        print(f"{rec['id']:<28} {rec['regime']:<6} {len(a):>11} {len(b):>11}")
        if a:
            print(f"{'':<28} A invented: {', '.join(a)}")
        if b:
            print(f"{'':<28} B invented: {', '.join(b)}")
    print()
    by_regime = summarise(records)
    print(f"{'regime':<10} {'questions':>9} {'A invented':>11} {'B invented':>11} "
          f"{'A q. with':>10} {'B q. with':>10} {'dropped':>8}")
    print("-" * 77)
    for regime in sorted(by_regime):
        s = by_regime[regime]
        print(f"{regime:<10} {s['n']:>9} {s['A']:>11} {s['B']:>11} "
              f"{s['A_q']:>10} {s['B_q']:>10} {s['dropped']:>8}")
    total_a = sum(s["A"] for s in by_regime.values())
    total_b = sum(s["B"] for s in by_regime.values())
    compared = sum(s["n"] for s in by_regime.values())
    dropped = sum(s["dropped"] for s in by_regime.values())
    print("-" * 77)
    print(f"{'TOTAL':<10} {compared:>9} {total_a:>11} {total_b:>11} {'':>10} {'':>10} {dropped:>8}")

    refused = refusals(records)
    if refused:
        print(f"\nREFUSED by the model ({len(refused)} answer(s)): {', '.join(refused)}")
    if dropped:
        print(f"\n{dropped} question(s) dropped: a question is compared only when both arms "
              f"answered.")
    return total_a, total_b


# --- run files -------------------------------------------------------------------------------

def save(path, model, provider, records):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"model": model, "provider": provider, "records": records}, f,
                  ensure_ascii=False, indent=2)


def already_answered(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return {}

    def finished(arm):
        return arm is not None and ((arm.get("text") or "").strip() or arm.get("stop_reason"))
    return {r["id"]: r for r in saved.get("records", [])
            if finished(r.get("A")) and finished(r.get("B"))}


def other_model(path, model):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f).get("model")
    except (OSError, ValueError):
        return None
    return saved if saved and saved != model else None


def load_questions(path=QUESTIONS):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["questions"]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="ask only the first N questions")
    ap.add_argument("--regime", help="core | deep")
    ap.add_argument("--model", default=os.environ.get("EVAL_MODEL", "claude-haiku-5-5"))
    ap.add_argument("--out", help="write every answer to this JSON file")
    ap.add_argument("--replay", help="re-count a saved run, making no API calls")
    ap.add_argument("--resume", action="store_true",
                    help="keep the answers already in --out and ask only what is missing")
    args = ap.parse_args(argv)

    if args.replay:
        with open(args.replay, encoding="utf-8") as f:
            saved = json.load(f)
        print(f"replaying {len(saved['records'])} question(s) from {args.replay} "
              f"(model {saved.get('model', '?')}) - no API calls.")
        report(saved["records"])
        return 0

    if args.resume and (args.limit or args.regime) and args.out and os.path.exists(args.out):
        print("ERROR: --resume rewrites the whole run file; it cannot be combined with --limit "
              "or --regime. Resume the full bank, or write to another --out.")
        return 2
    other = other_model(args.out, args.model) if args.resume else None
    if other:
        print(f"ERROR: {args.out} holds answers from {other}, not {args.model}. Resume it with "
              f"--model {other}, or write to another --out.")
        return 2

    rows = catalog_rows()
    questions = load_questions()
    if args.regime:
        questions = [q for q in questions if q["regime"] == args.regime]
    if args.limit:
        questions = questions[:args.limit]
    if not questions:
        print("no questions selected.")
        return 2

    provider, spec = provider_for(args.model)
    key = os.environ.get(spec["key_env"])
    if not key:
        print(f"ERROR: {spec['key_env']} is not set in the environment "
              f"({args.model} is served by {provider}).")
        return 2

    print(f"model {args.model} ({provider}) - {len(questions)} question(s) - 2 arms each "
          f"= {len(questions) * 2} calls")
    done = already_answered(args.out) if args.resume else {}
    if done:
        print(f"  resuming: {len(done)} question(s) already answered in {args.out}")
    records = [done[q["id"]] for q in questions if q["id"] in done]
    consecutive = 0
    tokens_in = tokens_out = 0
    for q in questions:
        if q["id"] in done:
            continue
        if q["category"] not in rows:
            raise SystemExit(f"{q['id']}: category '{q['category']}' is not a catalogue group")
        reference = "\n".join(rows[q["category"]])
        rec = {"id": q["id"], "regime": q["regime"], "category": q["category"],
               "question": q["question"]}
        for arm, ref in (("A", None), ("B", reference)):
            try:
                text, usage = ask(args.model, key, q["question"], ref)
                consecutive = 0
            except Exception as exc:  # noqa: BLE001
                consecutive += 1
                print(f"  {q['id']} arm {arm}: FAILED - {describe(exc)}")
                text, usage = "", {}
            rec[arm] = {"text": text, "stop_reason": usage.get("stop_reason")}
            tokens_in += usage.get("input_tokens", 0)
            tokens_out += usage.get("output_tokens", 0)
        if consecutive >= 4:
            print(f"\n{consecutive} calls failed in a row. Stopping: a run of empty answers is "
                  f"not a measurement.")
            if args.out and records:
                save(args.out, args.model, provider, records)
            return 2
        records.append(rec)
        if args.out:
            save(args.out, args.model, provider, records)
        print(f"  {q['id']:<28} A={len(invented(rec['A']['text']))} "
              f"B={len(invented(rec['B']['text']))}", flush=True)

    report(records)
    print(f"\ntokens: {tokens_in} in, {tokens_out} out")
    if args.out:
        save(args.out, args.model, provider, records)
        print(f"answers written to {args.out} - re-count with --replay")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
