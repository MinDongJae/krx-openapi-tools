# Contributing

Please describe a reproducible integration problem or a specific data-contract change.

For a new dataset, include a public KRX specification URL, its observed date, the exact wire fields, and an offline synthetic fixture. Separate provider facts from project interpretation. Confirm the production endpoint against its own developer specification before marking it verified.

Add tests for the failure that motivated the change. Preserve instrument codes and exact decimal values. Keep API keys and actual response datasets out of issues and commits; minimal synthetic examples are enough for most parsing problems.

Run `python -m unittest discover -s tests -v`. Keep changes focused on a real developer need. A contribution or release should accurately describe what was tested, including whether an approved live service was called.
