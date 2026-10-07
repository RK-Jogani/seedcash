# SeedCash focused tests

The suite has three self-contained test files. There is no umbrella loader,
child-module directory, or test helper package.

| File | Coverage |
| --- | --- |
| `test_wallet_workflow.py` | BIP39 known answers and normalization, final-word generation, SLIP39 recovery/navigation, passphrase consistency, replacement key wiping, disposal, and redaction |
| `test_transactions.py` | PSBT fixtures and parsing boundaries, CashTokens, CashAddr, sighash restrictions, redeem-script validation, and independently constructed signing digests/signatures |
| `test_qr_transport.py` | QR shell isolation, UR framing/round trips, fragment identity, Bytewords corruption, CRC against Python's standard library, and PSBT receiving |

Run from the repository root:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest src/tests/test_wallet_workflow.py -q
.venv/bin/python -m pytest src/tests/test_wallet_workflow.py::TestGenerationWorkflow -q
```

All mnemonic/key data is synthetic. QR tests mock the actual subprocess entry
point before submitting adversarial strings; tests never execute those strings.
Fountain round trips use bounded retries so a decoder defect cannot hang pytest.

## Review decisions

Removed tests for absent components, placeholders, source-text inspection,
duplicated negative fixtures, constant-only checks, and impossible Back routes.
Malformed token prefixes accept either the current parser's `None` rejection or
`ValueError`; they must never produce an accepted token. Redeem-script matching
is tested at `validate_redeem_script`, while BIP143 digest construction is tested
separately against independently assembled bytes. Generic UR transport is not
required to validate application-specific CBOR. QR tests assert shell isolation
and color validation without dictating a particular temporary-directory design.

Preserved security regressions for existing code, even when they fail. Failures
are not skipped or reclassified merely to make the suite green. Some PSBT format
and signing contracts still require review against intended protocol behavior.
Production code was not changed by this test consolidation.
