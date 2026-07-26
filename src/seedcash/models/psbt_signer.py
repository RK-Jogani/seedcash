# signer.py
import hashlib
import ecdsa
from typing import List, Tuple

from src.seedcash.models.psbt_parser import parse_psbt, parse_transaction, read_varint
from src.seedcash.models.bip44 import Bip44

# ----------------------------------------------------------------------
# Low-level helpers (if not already in psbt_parser)
# ----------------------------------------------------------------------
def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def serialize_varint(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xFFFFFFFF:
        return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")

def parse_derivation_path(path: str) -> List[int]:
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

def parse_bip32_derivation_value(value: bytes) -> Tuple[bytes, List[int]]:
    if len(value) < 4:
        raise ValueError("invalid BIP32 derivation value")
    fingerprint = value[:4]
    path = [
        int.from_bytes(value[offset:offset + 4], "little")
        for offset in range(4, len(value), 4)
    ]
    return fingerprint, path

def _scan_psbt_map_end(buf: bytes, pos: int) -> int:
    while pos < len(buf):
        key_len, pos = read_varint(buf, pos)
        if key_len == 0:
            return pos
        pos += key_len
        val_len, pos = read_varint(buf, pos)
        pos += val_len
    raise ValueError("unexpected end while scanning PSBT map")

def _serialize_keypairs(pairs: List[Tuple[bytes, bytes]]) -> bytes:
    out = b""
    for key, value in pairs:
        out += serialize_varint(len(key)) + key + serialize_varint(len(value)) + value
    out += b"\x00"
    return out

def _replace_psbt_input_map(psbt_bytes: bytearray, input_index: int,
                            updated_pairs: List[Tuple[bytes, bytes]]) -> bytearray:
    parsed = parse_psbt(psbt_bytes)
    if input_index >= parsed["input_count"]:
        raise ValueError(f"Input index {input_index} out of range")
    pos = 5
    pos = _scan_psbt_map_end(psbt_bytes, pos)
    input_starts, input_ends = [], []
    for _ in range(parsed["input_count"]):
        input_starts.append(pos)
        pos = _scan_psbt_map_end(psbt_bytes, pos)
        input_ends.append(pos)
    replacement = _serialize_keypairs(updated_pairs)
    start, end = input_starts[input_index], input_ends[input_index]
    return psbt_bytes[:start] + replacement + psbt_bytes[end:]

# ----------------------------------------------------------------------
# Main signing class (uses Bip44 for derivation)
# ----------------------------------------------------------------------
class BitcoinCashSigner:
    def __init__(self, xpriv: str, account_path: str = "m/44'/145'/0'"):
        self.account_path = parse_derivation_path(account_path)
        decoded = self._decode_xpriv(xpriv)
        if decoded["depth"] != len(self.account_path):
            raise ValueError("xpriv depth does not match account_path")
        self.private_key = decoded["private_key"]
        self.chain_code = decoded["chain_code"]

    @staticmethod
    def _decode_xpriv(xpriv: str) -> dict:
        import base58
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
            "chain_code": payload[13:45],
            "private_key": key_data[1:],
        }

    def _derive_path(self, path: List[int]) -> Tuple[bytes, bytes]:
        """Derive private key and compressed public key from the given path."""
        priv, chain = self.private_key, self.chain_code
        # Skip the part that is already covered by the xpriv
        for idx in path[len(self.account_path):]:
            priv, chain = Bip44.derive_private_child_key(priv, chain, idx)
        pub = Bip44.private_to_public(priv)
        return priv, pub

    def _create_sighash(self, tx: bytes, input_index: int, script_code: bytes,
                        amount_sats: int, hash_type: int = 0x41) -> bytes:
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

        # Check jacobi symbol of R.y()
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

    def sign_input(self, tx: bytes, input_index: int, script_code: bytes,
                   amount_sats: int, derivation_path: List[int]) -> Tuple[bytes, bytes]:
        """Return (signature_with_sighash, public_key) for the given input."""
        priv, pub = self._derive_path(derivation_path)
        sighash = self._create_sighash(tx, input_index, script_code, amount_sats)
        sig = self._sign_schnorr(priv, sighash, pub) + b"\x41"  # SIGHASH_ALL | FORKID
        return sig, pub

# ----------------------------------------------------------------------
# Public API: sign all inputs in a PSBT
# ----------------------------------------------------------------------
def sign_psbt(psbt_bytes: bytearray, xpriv: str,
              account_path: str = "m/44'/145'/0'") -> bytearray:
    """
    Sign all inputs in the PSBT that have a BIP32 derivation path.
    Returns the updated PSBT as bytearray.
    """
    parsed = parse_psbt(psbt_bytes)
    tx_bytes = parsed.get("unsigned_tx")
    if tx_bytes is None:
        raise ValueError("No unsigned transaction in PSBT")
    signer = BitcoinCashSigner(xpriv, account_path)
    unsigned_tx = parse_transaction(tx_bytes)

    signed = bytearray(psbt_bytes)

    for i, input_pairs in enumerate(parsed["inputs"]):
        # Skip if already signed (has partial signature)
        if any(k[0] == 0x02 for k, _ in input_pairs):
            continue

        utxo_value = None
        utxo_script = None
        redeem_script = None
        witness_script = None
        derivation_path = None

        for k, v in input_pairs:
            if k[0] == 0x00:  # PSBT_IN_NON_WITNESS_UTXO
                prev_tx = parse_transaction(v)
                tx_in = unsigned_tx["inputs"][i]
                prev_idx = int.from_bytes(tx_in["prev_index"], "little")
                if prev_idx < len(prev_tx["outputs"]):
                    out = prev_tx["outputs"][prev_idx]
                    utxo_value = out["amount_int"]
                    utxo_script = out["script"]
            elif k[0] == 0x01:  # PSBT_IN_WITNESS_UTXO
                utxo_value = int.from_bytes(v[:8], "little")
                utxo_script = v[8:]
            elif k[0] == 0x04:  # PSBT_IN_REDEEM_SCRIPT
                redeem_script = v
            elif k[0] == 0x05:  # PSBT_IN_WITNESS_SCRIPT
                witness_script = v
            elif k[0] == 0x06:  # PSBT_IN_BIP32_DERIVATION
                _, derivation_path = parse_bip32_derivation_value(v)

        if derivation_path is None:
            continue   # not owned by this wallet

        if utxo_script is None:
            utxo_script = b""
            utxo_value = 0

        script_code = redeem_script or witness_script or utxo_script

        sig, pub = signer.sign_input(tx_bytes, i, script_code, utxo_value, derivation_path)
        partial_key = b"\x02" + pub
        updated_pairs = [p for p in input_pairs if p[0] != partial_key]
        updated_pairs.append((partial_key, sig))
        signed = _replace_psbt_input_map(signed, i, updated_pairs)

    return signed