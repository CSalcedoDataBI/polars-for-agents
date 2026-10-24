# Contributing

Thanks for helping. This repository is in pre-release, so expect things to move.

## Report a problem

Open an [issue](https://github.com/CSalcedoDataBI/polars-for-agents/issues) when:

- an entry in `catalog/` is wrong, missing, or flagged deprecated or unstable when it is not (or
  the other way round): say which Polars version and which name;
- a trap note in `skills/polars-reference/notes/` is wrong or misleading: link the note and say
  what Polars really does, ideally with a short script and its output.

## Change something

Everything enters through a pull request, and the required `Validate` check must pass before it
can merge. `Validate` runs `python scripts/check_repo.py` and regenerates the catalogue from the
pinned `polars` version to prove it was not edited by hand.

## The one rule

**No Polars name outside the exported catalogue.** Every expression, method, namespace function
or selector named in anything an agent reads must exist in `catalog/polars-<version>.json`, which
only `scripts/export_catalog.py` writes. The check in `Validate` fails a PR that names anything
else. To support a new Polars version, regenerate the catalogue with that version installed; do
not add names by hand.

## License

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE).
