import hashlib
import hmac
import logging
from typing import Dict, List, Optional, Tuple

import ecdsa

from seedcash.models.bip44 import Bip44

logger = logging.getLogger(__name__)


class PSBTParser:
    def __init__(
        self,
        raw_psbt_bytes: bytearray,
    ):
        self.psbt_bytes: bytearray = raw_psbt_bytes

        self.spend_amount = 0
        self.fee_amount = 0
        self.input_amount = 0
        self.num_inputs = 0
        self.destination_addresses = []
        self.destination_amounts = []
        self.op_return_data: bytes = None

        self.parse()

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

            if not script_pubkey.startswith(b"\x6a"):
                self.spend_amount += value
                self.destination_amounts.append(value)
                self.destination_addresses.append(addr)

        self.fee_amount = self.input_amount - self.spend_amount
        return True

    def sign_with_wallet_xpriv(self, xpriv):
        """
        Signs the PSBT with the wallet's xpriv
        """
        try:
            signed_psbt = self.psbt_bytes
            for i in range(self.num_inputs):
                signed_psbt = sign_psbt_with_xpriv(
                    signed_psbt,
                    xpriv,
                    input_index=i,
                )
            self.psbt_bytes = signed_psbt
            return signed_psbt
        except Exception as e:
            logger.error(f"Error signing PSBT: {e}")
            return None


def read_varint(buf, pos):
    """Read Bitcoin-style varint (compact size uint)."""
    if pos >= len(buf):
        raise ValueError("pos out of range")
    b = buf[pos]
    if b < 0xFD:
        return b, pos + 1
    if b == 0xFD:
        v = int.from_bytes(buf[pos + 1 : pos + 3], "little")
        return v, pos + 3
    if b == 0xFE:
        v = int.from_bytes(buf[pos + 1 : pos + 5], "little")
        return v, pos + 5
    v = int.from_bytes(buf[pos + 1 : pos + 9], "little")
    return v, pos + 9


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


def parse_keypairs(buf, pos):
    """Parse a PSBT key-value section."""
    pairs = []
    limit = len(buf)
    while pos < limit:
        keylen, pos = read_varint(buf, pos)
        if keylen == 0:
            return pairs, pos
        key = bytes(buf[pos : pos + keylen])
        pos += keylen
        vlen, pos = read_varint(buf, pos)
        value = bytes(buf[pos : pos + vlen])
        pos += vlen
        pairs.append((key, value))
    raise ValueError("unexpected end while parsing keypairs")


def parse_psbt(buf):
    """Parse a PSBT binary into global/inputs/outputs sections."""
    if isinstance(buf, (bytearray, memoryview)):
        buf = bytes(buf)
    if not isinstance(buf, bytes):
        raise TypeError(f"PSBT buffer must be bytes-like, got {type(buf).__name__}")

    if len(buf) < 5 or buf[:5] != b"psbt\xff":
        raise ValueError("invalid PSBT magic")
    pos = 5

    global_pairs, pos = parse_keypairs(buf, pos)

    input_count = 0
    output_count = 0
    unsigned_tx = None
    psbt_version = 0
    for k, v in global_pairs:
        if k[0] == 0x00:
            unsigned_tx = v
        elif k[0] == 0x04:
            input_count, _ = read_varint(v, 0)
        elif k[0] == 0x05:
            output_count, _ = read_varint(v, 0)
        elif k[0] == 0xFB:
            psbt_version, _ = read_varint(v, 0)

    if (input_count == 0 or output_count == 0) and unsigned_tx is not None:
        tx = parse_unsigned_tx(unsigned_tx)
        input_count = len(tx["inputs"])
        output_count = len(tx["outputs"])

    inputs = []
    for _ in range(input_count):
        pairs, pos = parse_keypairs(buf, pos)
        inputs.append(pairs)

    outputs = []
    for _ in range(output_count):
        pairs, pos = parse_keypairs(buf, pos)
        outputs.append(pairs)

    return {
        "global": global_pairs,
        "inputs": inputs,
        "outputs": outputs,
        "input_count": input_count,
        "output_count": output_count,
        "psbt_version": psbt_version,
    }


def extract_tx_from_psbt(parsed):
    """Extract the unsigned transaction from PSBT global."""
    for k, v in parsed["global"]:
        if k[0] == 0x00:
            return v
    raise ValueError("No unsigned transaction found in PSBT")


def parse_unsigned_tx(tx_bytes: bytes) -> Dict[str, object]:
    """Parse a raw Bitcoin transaction into the fields used for BCH signing."""
    pos = 0
    version = tx_bytes[pos : pos + 4]
    pos += 4

    input_count, pos = read_varint(tx_bytes, pos)
    inputs = []
    for _ in range(input_count):
        prev_txid = tx_bytes[pos : pos + 32]
        pos += 32
        prev_index = tx_bytes[pos : pos + 4]
        pos += 4
        script_len, pos = read_varint(tx_bytes, pos)
        script_sig = tx_bytes[pos : pos + script_len]
        pos += script_len
        sequence = tx_bytes[pos : pos + 4]
        pos += 4
        inputs.append(
            {
                "prev_txid": prev_txid,
                "prev_index": prev_index,
                "script_sig": script_sig,
                "sequence": sequence,
            }
        )

    output_count, pos = read_varint(tx_bytes, pos)
    outputs = []
    for _ in range(output_count):
        value = tx_bytes[pos : pos + 8]
        pos += 8
        script_len, pos = read_varint(tx_bytes, pos)
        script_pubkey = tx_bytes[pos : pos + script_len]
        pos += script_len
        outputs.append({"value": value, "script_pubkey": script_pubkey})

    locktime = tx_bytes[pos : pos + 4]
    return {
        "version": version,
        "inputs": inputs,
        "outputs": outputs,
        "locktime": locktime,
    }


def parse_bip32_derivation_value(value: bytes) -> Tuple[bytes, List[int]]:
    """Parse a PSBT BIP32 derivation value into fingerprint and path."""
    if len(value) < 4:
        raise ValueError("invalid BIP32 derivation value")

    fingerprint = value[:4]
    derivation_path = []
    for offset in range(4, len(value), 4):
        derivation_path.append(int.from_bytes(value[offset : offset + 4], "little"))
    return fingerprint, derivation_path


def _scan_psbt_map_end(buf: bytes, pos: int) -> int:
    """Return the byte offset just after a PSBT key-value map terminator."""
    while pos < len(buf):
        keylen, pos = read_varint(buf, pos)
        if keylen == 0:
            return pos
        pos += keylen
        vlen, pos = read_varint(buf, pos)
        pos += vlen
    raise ValueError("unexpected end while scanning PSBT map")


def _serialize_keypairs(pairs):
    out = b""
    for key, value in pairs:
        out += serialize_varint(len(key)) + key + serialize_varint(len(value)) + value
    out += b"\x00"
    return out


def _replace_psbt_input_map(
    psbt_bytes: bytearray, input_index: int, updated_pairs
) -> bytearray:
    """Replace one input map in a PSBT without rewriting the rest of the file."""
    parsed = parse_psbt(psbt_bytes)
    if input_index >= parsed["input_count"]:
        raise ValueError(f"Input index {input_index} out of range")

    pos = 5
    pos = _scan_psbt_map_end(psbt_bytes, pos)

    input_starts = []
    input_ends = []
    for _ in range(parsed["input_count"]):
        input_starts.append(pos)
        pos = _scan_psbt_map_end(psbt_bytes, pos)
        input_ends.append(pos)

    replacement = _serialize_keypairs(updated_pairs)
    start = input_starts[input_index]
    end = input_ends[input_index]
    return psbt_bytes[:start] + replacement + psbt_bytes[end:]


class BitcoinCashSigner:
    def __init__(self, xpriv: str, account_path: str = "m/44'/145'/0'"):

        self.account_path = parse_derivation_path(account_path)
        self.is_extended_key = False
        self.account_private_key = None
        self.account_chain_code = None
        self.private_key = None
        self.public_key = None

        decoded = self._decode_xpriv(xpriv)
        if decoded["depth"] != len(self.account_path):
            raise ValueError(
                "xpriv depth does not match account_path; provide the wallet derivation prefix"
            )
        self.account_private_key = decoded["private_key"]
        self.account_chain_code = decoded["chain_code"]
        self.is_extended_key = True

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
            "version": payload[:4],
            "depth": payload[4],
            "parent_fingerprint": payload[5:9],
            "child_number": int.from_bytes(payload[9:13], "big"),
            "chain_code": payload[13:45],
            "private_key": key_data[1:],
        }

    def _private_to_public_key(self, private_key: bytes) -> bytes:
        """Derive compressed public key from private key."""
        sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        public_key = b"\x04" + vk.to_string()
        x = public_key[1:33]
        y = public_key[33:]
        if int.from_bytes(y[-1:], "big") % 2 == 0:
            prefix = b"\x02"
        else:
            prefix = b"\x03"
        return prefix + x

    def _derive_child_private_key(
        self, parent_private_key: bytes, parent_chain_code: bytes, index: int
    ) -> Tuple[bytes, bytes]:
        curve_order = ecdsa.SECP256k1.order
        if index >= 0x80000000:
            data = b"\x00" + parent_private_key + index.to_bytes(4, "big")
        else:
            data = self._private_to_public_key(parent_private_key) + index.to_bytes(
                4, "big"
            )

        I = hmac.new(parent_chain_code, data, hashlib.sha512).digest()
        IL, IR = I[:32], I[32:]
        child_int = (
            int.from_bytes(IL, "big") + int.from_bytes(parent_private_key, "big")
        ) % curve_order
        if int.from_bytes(IL, "big") >= curve_order or child_int == 0:
            raise ValueError("invalid child key derivation")
        return child_int.to_bytes(32, "big"), IR

    def _derive_private_key_from_path(
        self, derivation_path: List[int]
    ) -> Tuple[bytes, bytes]:
        if not self.is_extended_key:
            return self.private_key, self.public_key

        if derivation_path[: len(self.account_path)] != self.account_path:
            raise ValueError(
                "PSBT derivation path does not match the provided account_path"
            )

        private_key = self.account_private_key
        chain_code = self.account_chain_code
        for index in derivation_path[len(self.account_path) :]:
            private_key, chain_code = self._derive_child_private_key(
                private_key, chain_code, index
            )

        return private_key, self._private_to_public_key(private_key)

    def _get_script_code(self, locking_bytecode: bytes) -> bytes:
        """
        Get scriptCode for signature hash.
        For P2PKH: just the locking script.
        """
        return locking_bytecode

    def _serialize_tx_output(self, output: dict) -> bytes:
        return (
            output["value"]
            + serialize_varint(len(output["script_pubkey"]))
            + output["script_pubkey"]
        )

    def _create_sighash(
        self,
        tx: bytes,
        input_index: int,
        script_code: bytes,
        amount_sats: int,
        hash_type: int = 0x41,
    ) -> bytes:
        """Create a BCH fork-id sighash for SIGHASH_ALL|FORKID."""
        tx_data = parse_unsigned_tx(tx)
        anyone_can_pay = hash_type & 0x80
        sighash_mode = hash_type & 0x1F

        if input_index >= len(tx_data["inputs"]):
            raise ValueError("input_index out of range for unsigned transaction")

        if not anyone_can_pay:
            prevouts = b"".join(
                txin["prev_txid"] + txin["prev_index"] for txin in tx_data["inputs"]
            )
            hash_prevouts = double_sha256(prevouts)

            if sighash_mode in (0x01,):
                sequences = b"".join(txin["sequence"] for txin in tx_data["inputs"])
                hash_sequence = double_sha256(sequences)
            else:
                hash_sequence = b"\x00" * 32
        else:
            hash_prevouts = b"\x00" * 32
            hash_sequence = b"\x00" * 32

        if sighash_mode == 0x03 and input_index < len(tx_data["outputs"]):
            hash_outputs = double_sha256(
                self._serialize_tx_output(tx_data["outputs"][input_index])
            )
        elif sighash_mode == 0x02:
            hash_outputs = b"\x00" * 32
        else:
            hash_outputs = double_sha256(
                b"".join(
                    self._serialize_tx_output(output) for output in tx_data["outputs"]
                )
            )

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

    def _jacobi_symbol(self, a: int, p: int) -> int:
        """Compute the Jacobi symbol for odd prime p."""
        ls = pow(a % p, (p - 1) // 2, p)
        return -1 if ls == p - 1 else ls

    def sign_schnorr_bch(
        self, private_key: bytes, msg_hash: bytes, public_key: bytes
    ) -> bytes:
        """
        BCH Schnorr-style fixed-size signature (r || s), 64 bytes.
        """
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

        if self._jacobi_symbol(R.y(), field_prime) != 1:
            k = order - k
            R = k * G

        r_int = R.x()
        if r_int == 0:
            raise ValueError("invalid nonce: r is zero")

        r_bytes = r_int.to_bytes(32, "big")
        e = (
            int.from_bytes(
                hashlib.sha256(r_bytes + public_key + msg_hash).digest(), "big"
            )
            % order
        )

        s = (k + e * d) % order
        if s == 0:
            raise ValueError("invalid signature: s is zero")

        return r_bytes + s.to_bytes(32, "big")

    def sign_tx_input(
        self,
        tx: bytes,
        input_index: int,
        script_code: bytes,
        amount_sats: int,
        derivation_path: Optional[List[int]] = None,
        use_schnorr: bool = True,
    ) -> Tuple[bytes, bytes]:
        """Sign a transaction input."""
        if self.is_extended_key:
            if derivation_path is None:
                raise ValueError("xpriv signing requires a PSBT derivation path")
            signing_key, signing_pubkey = self._derive_private_key_from_path(
                derivation_path
            )
        else:
            signing_key = self.private_key
            signing_pubkey = self.public_key

        sighash = self._create_sighash(tx, input_index, script_code, amount_sats)

        if use_schnorr:
            signature = self.sign_schnorr_bch(signing_key, sighash, signing_pubkey) + bytes([
                0x41
            ])
        else:
            sk = ecdsa.SigningKey.from_string(signing_key, curve=ecdsa.SECP256k1)
            signature = sk.sign_digest_deterministic(
                sighash, hashfunc=hashlib.sha256, sigencode=ecdsa.util.sigencode_der_canonize
            ) + bytes([0x41])

        return signature, signing_pubkey


def sign_psbt_with_xpriv(
    psbt_bytes: bytearray,
    xpriv: str,
    input_index: int = 0,
    account_path: str = "m/44'/145'/0'",
):
    parsed = parse_psbt(psbt_bytes)
    tx_bytes = extract_tx_from_psbt(parsed)

    signer = BitcoinCashSigner(xpriv, account_path=account_path)
    unsigned_tx = parse_unsigned_tx(tx_bytes)

    if input_index >= len(parsed["inputs"]):
        raise ValueError(f"Input index {input_index} out of range")

    input_pairs = parsed["inputs"][input_index]

    utxo_value = None
    utxo_script = None
    redeem_script = None
    witness_script = None
    derivation_path = None

    for k, v in input_pairs:
        if k[0] == 0x00:
            prev_tx = parse_unsigned_tx(v)
            if input_index >= len(unsigned_tx["inputs"]):
                raise ValueError(
                    f"input_index {input_index} out of range for unsigned transaction inputs (len: {len(unsigned_tx['inputs'])})"
                )
            tx_input = unsigned_tx["inputs"][input_index]
            prevout_index = int.from_bytes(tx_input["prev_index"], "little")
            if prevout_index >= len(prev_tx["outputs"]):
                raise ValueError(
                    f"prev_index {prevout_index} out of range for input {input_index}"
                )
            prev_output = prev_tx["outputs"][prevout_index]
            utxo_value = int.from_bytes(prev_output["value"], "little")
            utxo_script = prev_output["script_pubkey"]
        if k[0] == 0x01:
            utxo_value = int.from_bytes(v[:8], "little")
            utxo_script = v[8:]
        if k[0] == 0x04:
            redeem_script = v
        if k[0] == 0x05:
            witness_script = v
        if k[0] == 0x06:
            _, derivation_path = parse_bip32_derivation_value(v)

    if utxo_script is None:
        utxo_script = b""
        utxo_value = 0

    script_code = redeem_script or witness_script or utxo_script

    signature, public_key = signer.sign_tx_input(
        tx_bytes,
        input_index,
        script_code,
        utxo_value,
        derivation_path=derivation_path,
        use_schnorr=True,
    )

    partial_sig_key = b"\x02" + public_key
    updated_pairs = [pair for pair in input_pairs if pair[0] != partial_sig_key]
    updated_pairs.append((partial_sig_key, signature))
    updated_psbt = _replace_psbt_input_map(psbt_bytes, input_index, updated_pairs)

    return bytearray(updated_psbt)
