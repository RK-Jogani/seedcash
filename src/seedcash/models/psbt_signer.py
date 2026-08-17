# seedcash/models/psbt_signer.py

import hashlib
import ecdsa
import base58
from typing import List, Tuple
from hmac import HMAC

from seedcash.models.psbt_parser import (
    PSBTParser,
    parse_transaction,
    parse_keypairs,
)
from seedcash.models.bip44 import Bip44


# ----------------------------------------------------------------------
# PSBT key constants (BIP‑174)
# ----------------------------------------------------------------------
PSBT_GLOBAL_UNSIGNED_TX      = 0x00
PSBT_GLOBAL_INPUT_COUNT      = 0x04
PSBT_GLOBAL_OUTPUT_COUNT     = 0x05
PSBT_GLOBAL_VERSION          = 0xFB
PSBT_GLOBAL_PROPRIETARY      = 0xFC

PSBT_IN_NON_WITNESS_UTXO     = 0x00
PSBT_IN_WITNESS_UTXO         = 0x01
PSBT_IN_PARTIAL_SIG          = 0x02
PSBT_IN_REDEEM_SCRIPT        = 0x04
PSBT_IN_WITNESS_SCRIPT       = 0x05
PSBT_IN_BIP32_DERIVATION     = 0x06

PSBT_OUT_AMOUNT              = 0x00
PSBT_OUT_SCRIPT              = 0x01
PSBT_OUT_BIP32_DERIVATION    = 0x02

# Bitcoin Cash sighash flags
SIGHASH_ALL                  = 0x01
SIGHASH_NONE                 = 0x02
SIGHASH_SINGLE               = 0x03
SIGHASH_ANYONECANPAY         = 0x80
SIGHASH_FORKID               = 0x40
SIGHASH_UTXOS                = 0x20

SIGHASH_BCH = SIGHASH_ALL | SIGHASH_FORKID  # 0x41


# ----------------------------------------------------------------------
# Serialization helpers
# ----------------------------------------------------------------------
def serialize_varint(n: int) -> bytes:
    if n < 0xfd:
        return n.to_bytes(1, "little")
    elif n <= 0xffff:
        return b"\xfd" + n.to_bytes(2, "little")
    elif n <= 0xffffffff:
        return b"\xfe" + n.to_bytes(4, "little")
    else:
        return b"\xff" + n.to_bytes(8, "little")


def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


# ----------------------------------------------------------------------
# BIP32 derivation helpers
# ----------------------------------------------------------------------
def derive_private_child_key(parent_priv: bytes, parent_chain: bytes, index: int) -> Tuple[bytes, bytes]:
    if index & 0x80000000:  # hardened
        data = b'\x00' + parent_priv + index.to_bytes(4, 'big')
    else:
        pub = Bip44.private_to_public(parent_priv)
        data = pub + index.to_bytes(4, 'big')

    hmac = HMAC(parent_chain, data, hashlib.sha512)
    il = hmac.digest()[:32]
    ir = hmac.digest()[32:]

    order = ecdsa.SECP256k1.order
    priv_int = (int.from_bytes(il, 'big') + int.from_bytes(parent_priv, 'big')) % order
    return priv_int.to_bytes(32, 'big'), ir


def parse_bip32_derivation_value(value: bytes) -> Tuple[bytes, List[int]]:
    if len(value) < 4 or (len(value) - 4) % 4 != 0:
        raise ValueError("Invalid BIP32 derivation value length")
    master_fingerprint = value[:4]
    path = [int.from_bytes(value[i:i+4], 'little') for i in range(4, len(value), 4)]
    return master_fingerprint, path


# ----------------------------------------------------------------------
# PSBT key‑value serialization
# ----------------------------------------------------------------------
def _serialize_keypairs(pairs: List[Tuple[bytes, bytes]]) -> bytes:
    out = b""
    for key, value in pairs:
        out += serialize_varint(len(key)) + key + serialize_varint(len(value)) + value
    out += b"\x00"   # map terminator
    return out


# ----------------------------------------------------------------------
# Main signer class – rebuilds the PSBT from parsed maps
# ----------------------------------------------------------------------
class BitcoinCashSigner:
    def __init__(self, xpriv: str, parser: PSBTParser):
        self.parser = parser
        self.account_path = self._parse_derivation_path("m/44'/145'/0'")
        decoded = self._decode_xpriv(xpriv)

        if decoded["depth"] != len(self.account_path):
            raise ValueError("xpriv depth does not match account_path (expected 3)")

        self.private_key = decoded["private_key"]
        self.chain_code = decoded["chain_code"]

    @staticmethod
    def _parse_derivation_path(path: str) -> List[int]:
        if not path:
            return []
        path = path.strip()
        if path in ("m", "M"):
            return []
        if path.startswith("m/") or path.startswith("M/"):
            path = path[2:]

        components = []
        for item in path.split("/"):
            item = item.strip()
            if not item:
                continue
            hardened = item[-1] in ("'", "h", "H")
            if hardened:
                item = item[:-1]
            index = int(item)
            if hardened:
                index |= 0x80000000
            components.append(index)
        return components

    @staticmethod
    def _decode_xpriv(xpriv: str) -> dict:
        decoded = base58.b58decode(xpriv)
        if len(decoded) != 82:
            raise ValueError("not an extended private key")

        payload = decoded[:-4]
        checksum = decoded[-4:]
        if double_sha256(payload)[:4] != checksum:
            raise ValueError("invalid xpriv checksum")

        key_data = payload[45:78]
        if key_data[0] != 0x00:
            raise ValueError("extended key is not private")

        return {
            "depth": payload[4],
            "fingerprint": payload[5:9],
            "child_number": int.from_bytes(payload[9:13], 'big'),
            "chain_code": payload[13:45],
            "private_key": key_data[1:],
        }

    def _derive_path(self, path: List[int]) -> Tuple[bytes, bytes]:
        priv, chain = self.private_key, self.chain_code
        for idx in path[len(self.account_path):]:
            priv, chain = derive_private_child_key(priv, chain, idx)
        pub = Bip44.private_to_public(priv)
        return priv, pub

    def _create_sighash(self, tx: bytes, input_index: int, script_code: bytes,
                        amount_sats: int, hash_type: int = SIGHASH_BCH) -> bytes:
        tx_data = parse_transaction(tx)
        anyone_can_pay = hash_type & 0x80
        mode = hash_type & 0x1F

        if input_index >= len(tx_data["inputs"]):
            raise ValueError("input_index out of range")

        if not anyone_can_pay:
            prevouts = b"".join(txin["prev_txid"] + txin["prev_index"] for txin in tx_data["inputs"])
            hash_prevouts = double_sha256(prevouts)
            if mode == 0x01:
                sequences = b"".join(txin["sequence"] for txin in tx_data["inputs"])
                hash_sequence = double_sha256(sequences)
            else:
                hash_sequence = b"\x00" * 32
        else:
            hash_prevouts = b"\x00" * 32
            hash_sequence = b"\x00" * 32

        if mode == 0x03 and input_index < len(tx_data["outputs"]):
            out = tx_data["outputs"][input_index]
            hash_outputs = double_sha256(
                out["value"] + serialize_varint(len(out["script"])) + out["script"]
            )
        elif mode == 0x02:
            hash_outputs = b"\x00" * 32
        else:
            out_bytes = b"".join(
                out["value"] + serialize_varint(len(out["script"])) + out["script"]
                for out in tx_data["outputs"]
            )
            hash_outputs = double_sha256(out_bytes)

        txin = tx_data["inputs"][input_index]

        preimage = (
            tx_data["version"]
            + hash_prevouts
            + hash_sequence
            + txin["prev_txid"]
            + txin["prev_index"]
            + serialize_varint(len(script_code))
            + script_code
            + amount_sats.to_bytes(8, "little")
            + txin["sequence"]
            + hash_outputs
            + tx_data["locktime"]
            + hash_type.to_bytes(4, "little")
        )
        return double_sha256(preimage)

    def _sign_schnorr(self, private_key: bytes, msg_hash: bytes, public_key: bytes) -> bytes:
        d = int.from_bytes(private_key, "big")
        order = ecdsa.SECP256k1.order
        field_prime = ecdsa.SECP256k1.curve.p()

        if d <= 0 or d >= order:
            raise ValueError("invalid private key scalar")
        if len(msg_hash) != 32:
            raise ValueError("msg_hash must be 32 bytes")
        if len(public_key) != 33:
            raise ValueError("public_key must be compressed (33 bytes)")

        k = ecdsa.rfc6979.generate_k(order, d, hashlib.sha256, msg_hash, extra_entropy=b"")
        G = ecdsa.SECP256k1.generator
        R = k * G

        if pow(R.y(), (field_prime - 1) // 2, field_prime) != 1:
            k = order - k
            R = k * G

        r_int = R.x()
        if r_int == 0:
            raise ValueError("invalid nonce: r is zero")

        r_bytes = r_int.to_bytes(32, "big")
        e = int.from_bytes(hashlib.sha256(r_bytes + public_key + msg_hash).digest(), "big") % order
        s = (k + e * d) % order
        if s == 0:
            raise ValueError("invalid signature: s is zero")

        return r_bytes + s.to_bytes(32, "big")

    # ------------------------------------------------------------------
    # Main signing method – rebuilds the PSBT from parsed maps
    # ------------------------------------------------------------------
    def signed_psbt(self) -> bytearray:
        parsed = self.parser.parsed
        tx_bytes = parsed["unsigned_tx"]
        if tx_bytes is None:
            raise ValueError("No unsigned transaction in PSBT")

        # 1. Copy the parsed maps
        global_pairs = parsed["global"].copy()
        input_maps = [pairs.copy() for pairs in parsed["inputs"]]
        output_maps = [pairs.copy() for pairs in parsed["outputs"]]

        print(f"Global pairs: {len(global_pairs)}")
        print(f"Input maps: {len(input_maps)}")
        print(f"Output maps: {len(output_maps)}")

        # 2. Sign each input that belongs to this wallet
        for idx, tx_input in enumerate(self.parser.tx.inputs):
            print(f"Processing input {idx}")
            if tx_input.spent_output is None:
                print("  spent_output is None, skipping")
                continue

            input_pairs = input_maps[idx]

            # Find derivation path
            derivation_path = None
            for key, value in input_pairs:
                if key[0] == PSBT_IN_BIP32_DERIVATION:
                    _, derivation_path = parse_bip32_derivation_value(value)
                    break
            if derivation_path is None:
                print("  derivation_path is None, skipping")
                continue
            print(f"  derivation_path: {derivation_path}")

            # Determine script_code (redeem script first)
            script_code = None
            for key, value in input_pairs:
                if key[0] == PSBT_IN_REDEEM_SCRIPT:
                    script_code = value
                    break
                elif key[0] == PSBT_IN_WITNESS_SCRIPT:
                    script_code = value
                    break
            if script_code is None:
                script_code = tx_input.spent_output.full_script
            print(f"  script_code length: {len(script_code)}")

            # Derive key
            priv, pub = self._derive_path(derivation_path)
            partial_key = bytes([PSBT_IN_PARTIAL_SIG]) + pub

            # Skip if already signed by this pubkey
            if any(k == partial_key for k, _ in input_pairs):
                print("  already signed by this pubkey, skipping")
                continue

            # Sign
            amount = tx_input.spent_output.value_satoshis
            sighash = self._create_sighash(tx_bytes, idx, script_code, amount, SIGHASH_BCH)
            sig = self._sign_schnorr(priv, sighash, pub) + bytes([SIGHASH_BCH])

            # Update the input map (keep all existing pairs, add partial signature)
            updated_pairs = input_pairs.copy()
            updated_pairs.append((partial_key, sig))
            input_maps[idx] = updated_pairs
            print(f"  signed input {idx}")

        # 3. Rebuild the PSBT
        psbt = bytearray(b"psbt\xff")
        psbt += _serialize_keypairs(global_pairs)
        print(f"After global: {len(psbt)} bytes")
        for i, pairs in enumerate(input_maps):
            psbt += _serialize_keypairs(pairs)
            print(f"After input {i}: {len(psbt)} bytes")
        for i, pairs in enumerate(output_maps):
            psbt += _serialize_keypairs(pairs)
            print(f"After output {i}: {len(psbt)} bytes")

        return psbt