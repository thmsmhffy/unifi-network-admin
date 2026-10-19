# Contributing

Open an issue before a large change. For a focused fix, send a pull request with the test that would have caught the problem.

Run these checks before submitting:

```bash
ruff check .
pytest
```

API additions need a link to the current official Ubiquiti operation. Do not add legacy undocumented endpoints, plaintext credential storage, raw-request tools, or live writes under a configuration flag.
