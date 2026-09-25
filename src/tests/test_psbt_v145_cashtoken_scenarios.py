import hashlib
import json
from pathlib import Path

import pytest

from seedcash.models.psbt_parser import PSBTParser
from seedcash.models.psbt_signer import (
    PSBT_OUT_AMOUNT,
    PSBT_OUT_BIP32_DERIVATION,
    PSBT_OUT_CASHTOKEN,
    PSBT_OUT_SCRIPT,
)


FIXTURE_PATH = Path(__file__).with_name("psbtV145CashTokenScenarios.json")


def load_fixture():
    return json.loads(FIXTURE_PATH.read_text())


def test_materialized_fixtures_match_declared_transaction_contract():
    fixture = load_fixture()

    assert len(fixture["materializedFixtures"]) == fixture["materializedFixtureCount"]

    for materialized in fixture["materializedFixtures"]:
        for parent in materialized["sourceTransactions"]:
            digest = hashlib.sha256(hashlib.sha256(bytes.fromhex(parent["hex"])).digest()).digest()
            assert digest[::-1].hex() == parent["txid"]

        parser = PSBTParser(bytearray.fromhex(materialized["psbtHex"]))
        assert parser.parsed["unsigned_tx"].hex() == materialized["unsignedTransactionHex"]
        assert parser.input_count == len(materialized["inputs"])
        assert parser.output_count == len(materialized["outputs"])
        assert parser.input_amount == sum(
            int(parent_output["satoshis"])
            for parent in materialized["sourceTransactions"]
            for parent_output in parent["outputs"]
            if any(
                tx_input["txid"] == parent["txid"]
                and tx_input["vout"] == parent["outputs"].index(parent_output)
                for tx_input in materialized["inputs"]
            )
        )
        assert parser.output_amount == sum(
            int(output["satoshis"]) for output in materialized["outputs"]
        )


def test_v145_uses_psbt_v2_output_field_mapping():
    assert PSBT_OUT_AMOUNT == 0x03
    assert PSBT_OUT_SCRIPT == 0x04
    assert PSBT_OUT_BIP32_DERIVATION == 0x02
    assert PSBT_OUT_CASHTOKEN == 0x36


@pytest.mark.parametrize("vector", load_fixture()["materializedNegativeVectors"])
def test_materialized_negative_vectors_are_rejected(vector):
    with pytest.raises(ValueError):
        PSBTParser(bytearray.fromhex(vector["psbtHex"]))