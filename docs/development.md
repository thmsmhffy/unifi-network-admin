# Development

## Set up

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Check the project

```bash
ruff check .
pytest
```

The test suite validates the Skill front matter and UI metadata. Maintainers with Codex's `skill-creator` installed should also run its `quick_validate.py` against `skill/unifi-network-admin` before a release.

The normal test suite uses mocked HTTP transports. It sends no network traffic and reads no real keyring entry.

The opt-in live test only calls read endpoints:

```bash
UNIFI_TEST_URL='https://console.example' \
UNIFI_TEST_API_KEY='...' \
pytest -m integration
```

Use a test controller and a dedicated API key. The live test still exercises a real inventory and should not run in public CI.

## Contribution rules

- Use documented official endpoints. Link the versioned Ubiquiti page or OpenAPI operation in the pull request.
- Keep every API call in the shared client. CLI and MCP code format or expose shared models; they do not duplicate transport logic.
- Add a mocked test for pagination, errors, or normalization affected by the change.
- Do not add a raw HTTP interface or undocumented `/api/s/...` fallback.
- A write proposal follows [`change-management.md`](change-management.md) and needs separate review.
