#!/usr/bin/env python3
import hashlib
import hmac
import ecdsa
from typing import Dict, List, Tuple, Optional
from ecdsa.rfc6979 import generate_k
from ecdsa.util import sigencode_der_canonize

def read_varint(buf, pos):
    """Read Bitcoin-style varint (compact size uint)"""
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
    """Parse a PSBT key-value section"""
    pairs = []
    limit = len(buf)
    while pos < limit:
        keylen, pos = read_varint(buf, pos)
        if keylen == 0:
            return pairs, pos  # trailing 0x00 has already been consumed
        key = bytes(buf[pos : pos + keylen])
        pos += keylen
        vlen, pos = read_varint(buf, pos)
        value = bytes(buf[pos : pos + vlen])
        pos += vlen
        pairs.append((key, value))
    raise ValueError("unexpected end while parsing keypairs")

def parse_psbt(buf):
    """Parse a PSBT binary into global/inputs/outputs sections"""
    assert buf[:5] == b"psbt\xff", "not a PSBT binary"
    pos = 5

    global_pairs, pos = parse_keypairs(buf, pos)

    # Get input/output counts from global
    input_count = 0
    output_count = 0
    for k, v in global_pairs:
        if k[0] == 0x04:  # PSBT_GLOBAL_INPUT_COUNT
            input_count, _ = read_varint(v, 0)
        if k[0] == 0x05:  # PSBT_GLOBAL_OUTPUT_COUNT
            output_count, _ = read_varint(v, 0)

    # Parse inputs
    inputs = []
    for _ in range(input_count):
        pairs, pos = parse_keypairs(buf, pos)
        inputs.append(pairs)

    # Parse outputs
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
    }

def extract_tx_from_psbt(parsed):
    """Extract the unsigned transaction from PSBT global"""
    for k, v in parsed["global"]:
        if k[0] == 0x00:  # PSBT_GLOBAL_UNSIGNED_TX
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

def _serialize_keypairs(pairs: List[Tuple[bytes, bytes]]) -> bytes:
    out = b""
    for key, value in pairs:
        out += serialize_varint(len(key)) + key + serialize_varint(len(value)) + value
    out += b"\x00"
    return out

def _replace_psbt_input_map(
    psbt_bytes: bytes, input_index: int, updated_pairs: List[Tuple[bytes, bytes]]
) -> bytes:
    """Replace one input map in a PSBT without rewriting the rest of the file."""
    parsed = parse_psbt(psbt_bytes)
    if input_index >= parsed["input_count"]:
        raise ValueError(f"Input index {input_index} out of range")

    pos = 5  # skip magic
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

def compute_fee(parsed_psbt: dict, tx_bytes: bytes) -> int:
    """Compute transaction fee in satoshis from parsed PSBT."""
    # Parse the unsigned transaction
    tx = parse_unsigned_tx(tx_bytes)
    
    # Total outputs
    total_output = sum(int.from_bytes(out["value"], "little") for out in tx["outputs"])
    
    total_input = 0
    # Iterate over inputs using their index
    for idx, inp_pairs in enumerate(parsed_psbt["inputs"]):
        utxo_value = None
        
        # Look for PSBT_IN_WITNESS_UTXO (0x01) first
        for k, v in inp_pairs:
            if k[0] == 0x01:
                utxo_value = int.from_bytes(v[:8], "little")
                break
        
        # If not found, look for PSBT_IN_NON_WITNESS_UTXO (0x00)
        if utxo_value is None:
            for k, v in inp_pairs:
                if k[0] == 0x00:
                    # Parse the previous transaction
                    prev_tx = parse_unsigned_tx(v)
                    # Get the output index being spent from the unsigned tx input
                    prev_index = int.from_bytes(tx["inputs"][idx]["prev_index"], "little")
                    if prev_index >= len(prev_tx["outputs"]):
                        raise ValueError(f"Invalid prev_index {prev_index} for input {idx}")
                    utxo_value = int.from_bytes(prev_tx["outputs"][prev_index]["value"], "little")
                    break
        
        if utxo_value is None:
            raise ValueError(f"Cannot determine input amount for input {idx}")
        
        total_input += utxo_value
    
    return total_input - total_output
    
# ============ Bitcoin Cash Signing ============
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
        """Derive compressed public key from private key"""
        sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        public_key = b"\x04" + vk.to_string()
        # Compressed format
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
        Get scriptCode for signature hash
        For P2PKH: just the locking script
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

        k = generate_k(order, d, hashlib.sha256, msg_hash, extra_entropy=b"")
        G = ecdsa.SECP256k1.generator
        R = k * G

        # BCH Schnorr normalizes R to jacobi(y)=1 to make signatures unique.
        if self._jacobi_symbol(R.y(), field_prime) != 1:
            k = order - k
            R = k * G

        r_int = R.x()
        if r_int == 0:
            raise ValueError("invalid nonce: r is zero")

        r_bytes = r_int.to_bytes(32, "big")
        e = int.from_bytes(
            hashlib.sha256(r_bytes + public_key + msg_hash).digest(), "big"
        ) % order

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
            signature = (
                self.sign_schnorr_bch(signing_key, sighash, signing_pubkey)
                + bytes([0x41])
            )
        else:
            sk = ecdsa.SigningKey.from_string(signing_key, curve=ecdsa.SECP256k1)
            signature = sk.sign_digest_deterministic(
                sighash, hashfunc=hashlib.sha256, sigencode=sigencode_der_canonize
            ) + bytes([0x41])

        return signature, signing_pubkey  # SIGHASH_ALL | SIGHASH_FORKID


def add_signature_to_psbt(
    psbt_bytes: bytes,
    xpriv: str,
    input_index: int = 0,
    account_path: str = "m/44'/145'/0'",
):
    parsed = parse_psbt(psbt_bytes)
    tx_bytes = extract_tx_from_psbt(parsed)
    
    # Compute fee
    fee = compute_fee(parsed, tx_bytes)
    print(f"Computed fee: {fee} satoshis")

    signer = BitcoinCashSigner(xpriv, account_path=account_path)
    unsigned_tx = parse_unsigned_tx(tx_bytes)

    if input_index >= len(parsed["inputs"]):
        raise ValueError(f"Input index {input_index} out of range")

    input_pairs = parsed["inputs"][input_index]

    # Find the UTXO info (look for PSBT_IN_NON_WITNESS_UTXO or PSBT_IN_WITNESS_UTXO)
    utxo_value = None
    utxo_script = None
    redeem_script = None
    witness_script = None
    derivation_path = None

    for k, v in input_pairs:
        if k[0] == 0x00:  # PSBT_IN_NON_WITNESS_UTXO
            prev_tx = parse_unsigned_tx(v)
            prevout_index = int.from_bytes(
                unsigned_tx["inputs"][input_index]["prev_index"], "little"
            )
            prev_output = prev_tx["outputs"][prevout_index]
            utxo_value = int.from_bytes(prev_output["value"], "little")
            utxo_script = prev_output["script_pubkey"]
        if k[0] == 0x01:  # PSBT_IN_WITNESS_UTXO
            # This contains value (8 bytes) + script
            utxo_value = int.from_bytes(v[:8], "little")
            utxo_script = v[8:]
        if k[0] == 0x04:  # PSBT_IN_REDEEM_SCRIPT
            redeem_script = v
        if k[0] == 0x05:  # PSBT_IN_WITNESS_SCRIPT
            witness_script = v
        if k[0] == 0x06:  # PSBT_IN_BIP32_DERIVATION
            _, derivation_path = parse_bip32_derivation_value(v)

    if utxo_script is None:
        print(
            "Warning: Could not find UTXO info. Using default script from transaction."
        )
        # Fallback: extract from transaction outputs
        # This requires parsing the full transaction
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

    # Add PSBT_IN_PARTIAL_SIG (key type 0x02)
    partial_sig_key = b"\x02" + public_key
    updated_pairs = [pair for pair in input_pairs if pair[0] != partial_sig_key]
    updated_pairs.append((partial_sig_key, signature))
    updated_psbt = _replace_psbt_input_map(psbt_bytes, input_index, updated_pairs)

    print(f"Signature created for input {input_index}")
    print(f"Public key: {public_key.hex()}")
    print(f"Signature: {signature.hex()[:64]}...")

    return updated_psbt


# ============ Main Execution ============
def main():
    # Your PSBT bytes
    PSBT_BYTES = b'psbt\xff\x01\x00u\x02\x00\x00\x00\x01\x15Cq.$\xa4L\xb0N\xcb0(|\xf8}\xef[\xc8\xbc\xf1@\xfcE/\xd7\xe0\\\xba\xed\xa1\x8f\x80\x01\x00\x00\x00\x00\xff\xff\xff\xff\x02\xe8\x03\x00\x00\x00\x00\x00\x00\x19v\xa9\x148z@\x93\xb13\x91o\xc17\xdf\xcdJ\xad\xab:\xdd\xee\x87\xb4\x88\xac\xf4\xb8\x02\x00\x00\x00\x00\x00\x17\xa9\x14DFk\xea?/\x84\xfb\x83\xc2\x1e\x0f\xdd\xca!<N|w\x92\x87\x00\x00\x00\x00O\x01\x04\x88\xb2\x1e\x03+r\xf5\xb7\x80\x00\x00\x00\xaa\x1e\xfb\xd54\x06dP\xc3~8=\x18\xdd?\xc1\xb9\x91\xd04\x0f\x9d\xd5\xe0S\xdc\xae\x86u\xf8\xd7C\x03\xf5\xd6\xedM\x10\xe9\xf9\xdf\xd2k\xd8y\x9eIQ\xe3\'\xd4\xa8\xd9\xa3np\xfeq\xfe\x0c\xc5\x965E\xd5\x10s\xc5\xda\n,\x00\x00\x80\x91\x00\x00\x80\x00\x00\x00\x80O\x01\x04\x88\xb2\x1e\x03\xebo>\xe9\x80\x00\x00\x00\x13\xf4\x1e-\x91\x96A\xc1(\xda\x8c\x11\x9f[\x8b,\x7fh\xb7I0\xbd+\xa5Y|\xc2\xb6W(S\xba\x03\x81\xe8d\xc7)h\xdak\xb4?l\x1f\xe9\xbd|\xe5\x13ewB\x06\xd2\xae\t\xecd&*\xa1\xc8\xe9\x19\x10b\r\x1c:,\x00\x00\x80\x91\x00\x00\x80\x00\x00\x00\x80\x01\x02\x04\x02\x00\x00\x00\x01\x03\x04\x00\x00\x00\x00\x01\x04\x01\x01\x01\x05\x01\x02\x01\xfb\x04\x91\x00\x00\x00\x10\xfc\x07paytaca\x01origin\x0epaytaca-wallet\x11\xfc\x07paytaca\x04creatorB02aa3cdae6fedea5f8432e6fd2bccb4a6e54311d5913752f01962cd80557e6160d\x11\xfc\x07paytaca\x02purpose\x08Send BCH\x11\xfc\x07paytaca\x03network\x07mainnet\x11\xfc\x08metadata\x01origin\x0epaytaca-wallet\x12\xfc\x08metadata\x04creatorB02aa3cdae6fedea5f8432e6fd2bccb4a6e54311d5913752f01962cd80557e6160d\x12\xfc\x08metadata\x02purpose\x08Send BCH\x12\xfc\x08metadata\x03network\x07mainnet\x00\x01\x10\x04\x00\x00\x00\x00\x01\x00\xfdB\x01\x02\x00\x00\x00\x01\x88zy!}O\xfdK\x1f\xc4\xbcm\t \xeaM\x1b\xa0@+\x9a\xc6\x8d\x1e\x9d\xcf\xdf\xb1\x90\xe9P\xec\x01\x00\x00\x00\xcdSA\xb9n\xcc\xcd%M.\xd6\xccAyv\x91\xb8iJ\x8a\x8e\x08DS&\xf8\x97\x06/\xba\xc0\x96\xcb\xb0\x9b\xd9"\x99\xbd\xf1>\xe2\x10\x06\x85\xe8\xf3-\xad\xf2\x19D}I\xcfG\x93xq\x0e\xd9\xa5\xc7H\xd8 7AAw\x81h$W\xde\xd1\xd6\x0cK}\x02\x1d\x8d/\xbb1\xc0=R\x80Tz\x89\xfa\x80\xa8V\xd6\x8f\xa9\xb7I\xd3j\xda\xbe\xcf_\xd3\xc2\x83\x02\xa9P\x89\x05\xc0r\x9dK\x0e\xeb\xf6P\x05>o\x1d\xb8\xfa\x99\xfb5AGR!\x02\x18\xef\x99\x80\x8d\x18\xc4\rU\\iE\x14R\xe8\xf3\x80FKd\xefK l\x14U\xb2\x8f9\x8b6\xf8!\x02\xbb\xe7\xdb\xcd\xf8\xb2&\x150\xa8g\xdfq\x80\xb1z\x90\xb4\x82\xf7O\'6\xb8\xa3\r?unB\xe2\x17R\xae\xff\xff\xff\xff\x02\xa0\x86\x01\x00\x00\x00\x00\x00\x19v\xa9\x148z@\x93\xb13\x91o\xc17\xdf\xcdJ\xad\xab:\xdd\xee\x87\xb4\x88\xac\xbf\xbe\x02\x00\x00\x00\x00\x00\x17\xa9\x14\n\xf4p\x8d\x1a\x07\xd4\\\x8c\xe7\x82\xf2J\x8f\xadaWoA\xfd\x87\x00\x00\x00\x00"\x02\x03\xcf\x18\xa2\xf0\xaa\x80\xc1\xf1\xf2>\xb0J\x15\x0f\x1eXo#\xf1q}\xb2\xd6\xc9\x8cq\xc9^\xdb\x0br\xa2A\xa3\x0c\xf2\xdeb\xcc<\xc1C\xf4\xeasV\xa9\x11\xa4\x8c\xc6\x8c\x7fc\xdc&\xd0\x0eU\x7fIY1\xab\xbd\xfa\x9a^\xf7\x86\xe1I\tI\x81\xe6f\xe0\xbc\xf5\xccd\xbd)u\xc0\x0c\xa3Y\x07Zt\xd0V,\x1f8A\x01\x04GR!\x03\xc2.lQ\x8c\xa3\xf0\x06\xa7\xcbC\xbb\xc6\x8fc\x88\'y%\xd7Q\xba\xf1\xd2,6\xdb \x17\x00\xc9\x01!\x03\xcf\x18\xa2\xf0\xaa\x80\xc1\xf1\xf2>\xb0J\x15\x0f\x1eXo#\xf1q}\xb2\xd6\xc9\x8cq\xc9^\xdb\x0br\xa2R\xae"\x06\x03\xc2.lQ\x8c\xa3\xf0\x06\xa7\xcbC\xbb\xc6\x8fc\x88\'y%\xd7Q\xba\xf1\xd2,6\xdb \x17\x00\xc9\x01\x18s\xc5\xda\n,\x00\x00\x80\x91\x00\x00\x80\x00\x00\x00\x80\x01\x00\x00\x00\x01\x00\x00\x00"\x06\x03\xcf\x18\xa2\xf0\xaa\x80\xc1\xf1\xf2>\xb0J\x15\x0f\x1eXo#\xf1q}\xb2\xd6\xc9\x8cq\xc9^\xdb\x0br\xa2\x18b\r\x1c:,\x00\x00\x80\x91\x00\x00\x80\x00\x00\x00\x80\x01\x00\x00\x00\x01\x00\x00\x00\x01\x07\x00\x01\x0e \x80\x8f\xa1\xed\xba\\\xe0\xd7/E\xfc@\xf1\xbc\xc8[\xef}\xf8|(0\xcbN\xb0L\xa4$.qC\x15\x01\x0f\x04\x01\x00\x00\x00\x00\x00\x01\x03\x08\xe8\x03\x00\x00\x00\x00\x00\x00\x01\x04\x19v\xa9\x148z@\x93\xb13\x91o\xc17\xdf\xcdJ\xad\xab:\xdd\xee\x87\xb4\x88\xac\x00"\x02\x02\x0b\x90\x1b\x859z\xda\xb5\x1eoT\x9b\xe1\xaf\x8ew\x1dJ\x05\xd16\xdait\x06\xdb\x16\xa6\xb67\xdf\xda\x18b\r\x1c:,\x00\x00\x80\x91\x00\x00\x80\x00\x00\x00\x80\x01\x00\x00\x00\x03\x00\x00\x00"\x02\x03\xf2\x1a\xc0\x96\xd8\xf3\xe4d\xdd\xcbZ\xac\x97z\xcd\xf4\xca\x16\x8e\xbc\xdb\xfe\x83y\xb1\xc4C\xd1\xb9\xe5\t7\x18s\xc5\xda\n,\x00\x00\x80\x91\x00\x00\x80\x00\x00\x00\x80\x01\x00\x00\x00\x03\x00\x00\x00\x01\x03\x08\xf4\xb8\x02\x00\x00\x00\x00\x00\x01\x04\x17\xa9\x14DFk\xea?/\x84\xfb\x83\xc2\x1e\x0f\xdd\xca!<N|w\x92\x87\x11\xfc\x07paytaca\x02purpose\x12sats-self-internal\x00'
    xpriv = "xprv9xywTsqYa9uDLdJs8QpXf7xwRWgPw4rq5FtkcShsDoZTqfNQjVQ3dDCdyedXX3FqB18U8e8PfVMeFqkhzPGseKVMDjGe5rPdiUXMxy7BQNJ"
    derivation_path = "m/44'/145'/0'"    
    input_index = 0

    
    print("=" * 60)
    print("PSBT Transaction Signer for Bitcoin Cash")
    print("=" * 60)

    # Parse the PSBT
    print("\n1. Parsing PSBT...")
    parsed = parse_psbt(PSBT_BYTES)
    print(f"   - Inputs: {parsed['input_count']}")
    print(f"   - Outputs: {parsed['output_count']}")

    # Extract transaction details
    print("\n2. Transaction Details:")
    tx_bytes = extract_tx_from_psbt(parsed)
    tx_hex = tx_bytes.hex()
    print(f"   - Raw tx hex: {tx_hex[:100]}...")

    # Parse outputs from the transaction
    # The transaction structure: version(4) + inputs_count + inputs + outputs_count + outputs + locktime
    pos = 4  # skip version
    input_count, pos = read_varint(tx_bytes, pos)
    print(f"   - Input count in tx: {input_count}")

    # Skip inputs to get to outputs
    for i in range(input_count):
        # Skip prev_tx_hash (32) + prev_out (4) + script_len + script + sequence (4)
        pos += 32 + 4
        script_len, pos = read_varint(tx_bytes, pos)
        pos += script_len
        pos += 4

    output_count, pos = read_varint(tx_bytes, pos)
    print(f"   - Output count in tx: {output_count}")

    outputs = []
    for i in range(output_count):
        value = int.from_bytes(tx_bytes[pos : pos + 8], "little")
        pos += 8
        script_len, pos = read_varint(tx_bytes, pos)
        script = tx_bytes[pos : pos + script_len]
        pos += script_len
        outputs.append({"value": value, "script": script.hex()})
        print(f"   - Output {i}: {value} satoshis, script: {script.hex()[:40]}...")

    print("\n3. Signing Information:")
    print("   This transaction needs to be signed with the private key")
    print("   corresponding to the input UTXO.")

    # To actually sign, you need the private key for the address
    # The address from your JSON has locking bytecode: a914520250639aa1427d96098ed876297d0278937485??
    # That's a P2SH address

    signed_psbt = add_signature_to_psbt(
        PSBT_BYTES,
        xpriv,
        input_index=input_index,
        account_path=derivation_path,
    )

if __name__ == "__main__":
    main()
