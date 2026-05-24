import logging

from seedcash.models.settings_definition import SettingsConstants
from seedcash.models.bip44 import Bip44
from seedcash.models.bch_signer import (
    parse_psbt,
    extract_tx_from_psbt,
    parse_unsigned_tx,
    parse_bip32_derivation_value,
)

logger = logging.getLogger(__name__)


class PSBTParser:
    def __init__(
        self,
        raw_psbt_bytes: bytes,
    ):
        self.psbt_bytes: bytes = raw_psbt_bytes

        self.spend_amount = 0
        self.change_amount = 0
        self.change_data = []
        self.fee_amount = 0
        self.input_amount = 0
        self.num_inputs = 0
        self.destination_addresses = []
        self.destination_amounts = []
        self.op_return_data: bytes = None

        self.parse()

    def get_change_data(self, change_num: int) -> dict:
        if change_num < len(self.change_data):
            return self.change_data[change_num]
        return {}

    @property
    def num_change_outputs(self):
        return len(self.change_data)

    @property
    def is_multisig(self):
        return False

    @property
    def num_destinations(self):
        return len(self.destination_addresses)

    def parse(self):
        if self.psbt_bytes is None:
            logger.info("self.psbt_bytes is None!!")
            return False

        try:
            parsed_psbt = parse_psbt(self.psbt_bytes)
        except Exception as e:
            logger.error(f"CRASHING PSBT BYTES HEX: {self.psbt_bytes}")
            raise

        tx_bytes = extract_tx_from_psbt(parsed_psbt)
        unsigned_tx = parse_unsigned_tx(tx_bytes)

        self.num_inputs = parsed_psbt["input_count"]

        self.input_amount = 0
        for i, input_map in enumerate(parsed_psbt["inputs"]):
            for k, v in input_map:
                if k[0] == 0x00:  # PSBT_IN_NON_WITNESS_UTXO
                    prev_tx = parse_unsigned_tx(v)
                    prev_index = int.from_bytes(
                        unsigned_tx["inputs"][i]["prev_index"], "little"
                    )
                    if prev_index < len(prev_tx["outputs"]):
                        self.input_amount += int.from_bytes(
                            prev_tx["outputs"][prev_index]["value"], "little"
                        )
                elif k[0] == 0x01:  # PSBT_IN_WITNESS_UTXO
                    utxo_value = int.from_bytes(v[:8], "little")
                    self.input_amount += utxo_value

        for i, out_map in enumerate(parsed_psbt["outputs"]):
            tx_output = unsigned_tx["outputs"][i]
            value = int.from_bytes(tx_output["value"], "little")
            script_pubkey = tx_output["script_pubkey"]

            is_change = False
            fingerprints = []
            derivation_paths = []

            for k, v in out_map:
                if k[0] == 0x02:  # PSBT_OUT_BIP32_DERIVATION
                    fingerprint, path = parse_bip32_derivation_value(v)
                    fingerprint_hex = fingerprint.hex()
                    fingerprints.append(fingerprint_hex)
                    derivation_paths.append(
                        "m/"
                        + "/".join(
                            str(p & 0x7FFFFFFF) + ("'" if p & 0x80000000 else "")
                            for p in path
                        )
                    )

            addr = "Unknown"
            if script_pubkey.startswith(b"\x76\xa9\x14") and script_pubkey.endswith(
                b"\x88\xac"
            ):
                hash160 = script_pubkey[3:23]
                addr = Bip44.hash160_to_cashaddr(hash160)
            elif script_pubkey.startswith(b"\xa9\x14") and script_pubkey.endswith(
                b"\x87"
            ):
                hash160 = script_pubkey[2:22]
                addr = Bip44.hash160_to_cashaddr(hash160)
            elif script_pubkey.startswith(b"\x6a"):
                self.op_return_data = script_pubkey[2:]

            if is_change:
                self.change_amount += value
                self.change_data.append(
                    {
                        "output_index": i,
                        "address": addr,
                        "amount": value,
                        "fingerprint": fingerprints,
                        "derivation_path": derivation_paths,
                    }
                )
            elif not script_pubkey.startswith(b"\x6a"):
                self.spend_amount += value
                self.destination_amounts.append(value)
                self.destination_addresses.append(addr)

        self.fee_amount = self.input_amount - self.spend_amount - self.change_amount
        return True

    def sign_with_wallet_xpriv(self, xpriv) -> int:
        """
        Signs the PSBT with the wallet's xpriv
        """
        from seedcash.models.bch_signer import sign_psbt_with_xpriv

        try:
            signed_psbt = sign_psbt_with_xpriv(self.psbt_bytes, xpriv)
            return signed_psbt
        except Exception as e:
            logger.error(f"Error signing PSBT: {e}")
            return None
