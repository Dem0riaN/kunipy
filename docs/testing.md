# Testing

The repository contains tests, but this document intentionally does not claim a
specific test count unless it has been verified against the current checkout.

## Recommended checks

```bash
python -m pytest
```

For a release, also verify:

- import/startup succeeds;
- configuration parsing succeeds;
- enabled integrations can initialize;
- memory storage is writable;
- external credentials are valid;
- metrics endpoints behave as expected;
- no secrets are present in tracked files.

The test suite and its coverage should be treated as a property of the current
revision, not as a permanent project claim.
