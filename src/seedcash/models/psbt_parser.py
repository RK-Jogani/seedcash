import logging
import struct
from enum import StrEnum
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field


from seedcash.models.bip44 import Bip44

logger = logging.getLogger(__name__)



# Data Classes Used for Display
@dataclass
class NFTData:
    capability: str
    commitment: str

# Enum for NFT Warnings
class NFTWarning(StrEnum):
    MINTING = "minting"
    BURNING = "burning"

@dataclass
class TokenData:
    category_id: str
    ft_amount: Optional[int] = None
    nft_data: Optional[NFTData] = None  # {'capability': 'none', 'commitment': b'...'}

@dataclass
class TxOutput:
    value_satoshis: int
    script_pubkey: bytes                       # CashToken prefix stripped
    full_script: bytes = field(repr=False, default=b"")  # exact on-chain script
    token: Optional[TokenData] = None
    address: Optional[str] = None

    @property
    def is_token_output(self) -> bool:
        return self.token is not None

@dataclass
class TxInput:
    prev_txid: bytes
    prev_index: int
    sequence: int
    script_sig: bytes = b""
    spent_output: Optional[TxOutput] = None

    @property
    def is_token_input(self) -> bool:
        return self.spent_output is not None and self.spent_output.token is not None

@dataclass
class Transaction:
    version: int
    locktime: int
    inputs: List[TxInput]
    outputs: List[TxOutput]
    input_maps: List[List[Tuple[bytes, bytes]]] = field(default_factory=list)
    output_maps: List[List[Tuple[bytes, bytes]]] = field(default_factory=list)
    raw_unsigned_tx: bytes = field(repr=False, default=b"")
    categories: Dict[str, List[str]] = field(default_factory=lambda: {"nft": [], "ft": []})  # [nft_categories, ft_categories]

    # ---- Total BCH (including token carriers) ----
    @property
    def total_input(self) -> int:
        return sum(inp.spent_output.value_satoshis for inp in self.inputs if inp.spent_output)

    @property
    def total_output(self) -> int:
        return sum(out.value_satoshis for out in self.outputs)

    @property
    def fee(self) -> int:
        return self.total_input - self.total_output


    def arrange_inputs_by_type_and_category(self) -> List[Dict[str, List[TxInput]]]: 
        st_dict: Dict[str, List[TxInput]] = {}
        ft_dict: Dict[str, List[TxInput]] = {}
        nft_dict: Dict[str, List[TxInput]] = {}

        for inp in self.inputs:
            if inp.is_token_input:
                if inp.spent_output.token.nft_data is not None:
                    category = inp.spent_output.token.category_id
                    if category not in nft_dict:
                        self.categories["nft"].append(category)
                        nft_dict[category] = []
                    nft_dict[category].append(inp)
                elif inp.spent_output.token.ft_amount is not None:
                    category = inp.spent_output.token.category_id
                    if category not in ft_dict:
                        self.categories["ft"].append(category)
                        ft_dict[category] = []
                    ft_dict[category].append(inp)
            else:
                if "bch" not in st_dict:
                    st_dict["bch"] = []
                st_dict["bch"].append(inp)

        return [nft_dict,ft_dict,st_dict]

    def arrange_outputs_by_type_and_category(self) -> List[Dict[str, List[TxOutput]]]:
        st_dict: Dict[str, List[TxOutput]] = {}
        ft_dict: Dict[str, List[TxOutput]] = {}
        nft_dict: Dict[str, List[TxOutput]] = {}

        for out in self.outputs:
            if out.is_token_output:
                if out.token.nft_data is not None:
                    category = out.token.category_id
                    if category not in nft_dict:
                        nft_dict[category] = []
                    nft_dict[category].append(out)
                elif out.token.ft_amount is not None:
                    category = out.token.category_id
                    if category not in ft_dict:
                        ft_dict[category] = []
                    ft_dict[category].append(out)
            else:
                if "bch" not in st_dict:
                    st_dict["bch"] = []
                st_dict["bch"].append(out)

        return [nft_dict, ft_dict, st_dict]
    
    def categories_type(self, type_name: str) -> List[str]:
        return self.categories.get(type_name, [])

def read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Read a Bitcoin-style varint (CompactSize uint) at ``pos``."""
    if pos >= len(buf):
        raise ValueError("pos out of range")
    b = buf[pos]
    if b < 0xFD:
        return b, pos + 1
    if b == 0xFD:
        return struct.unpack_from("<H", buf, pos + 1)[0], pos + 3
    if b == 0xFE:
        return struct.unpack_from("<I", buf, pos + 1)[0], pos + 5
    return struct.unpack_from("<Q", buf, pos + 1)[0], pos + 9

def parse_token_script(script: bytes) -> Optional[Dict[str, Any]]:
    """Decode a CashToken prefix (PREFIX_TOKEN = 0xef) from a locking script.

    Returns ``None`` if ``script`` has no token prefix. Otherwise returns
    ``{'prefix': <raw prefix bytes>, 'script_pubkey': <underlying spendable
    script>, 'data': <decoded token fields>}``.
    """
    if not script or script[0] != 0xEF:
        return None
    pos = 1
    if len(script) < pos + 32:
        return None
    category = script[pos:pos + 32]
    pos += 32
    if len(script) < pos + 1:
        return None
    bitfield = script[pos]
    pos += 1
    if bitfield & 0x80:
        return None

    has_commitment_length = bool(bitfield & 0x40)
    has_nft = bool(bitfield & 0x20)
    has_amount = bool(bitfield & 0x10)
    capability_bits = bitfield & 0x0F

    capability_map = {0: "none", 1: "mutable", 2: "minting"}
    capability = capability_map.get(capability_bits, str(capability_bits)) if has_nft else None

    nft_data = None
    if has_nft:
        if has_commitment_length:
            nft_len, pos = read_varint(script, pos)
            if len(script) < pos + nft_len:
                return None
            nft_bytes = script[pos:pos + nft_len]
            pos += nft_len
        else:
            nft_bytes = b""
        nft_data: NFTData = NFTData(capability=capability, commitment=nft_bytes.hex())

    ft_amount = None
    if has_amount:
        ft_amount, pos = read_varint(script, pos)

    token_data: TokenData = TokenData(
        category_id=category[::-1].hex(),
        ft_amount=ft_amount,
        nft_data=nft_data,
    )
    return {
        "prefix": script[:pos],
        "script_pubkey": script[pos:],
        "data": token_data,
    }

def parse_transaction(tx_bytes: bytes) -> Dict[str, Any]:
    """Parse a raw Bitcoin Cash transaction, with CashToken awareness.

    Each output dict carries both:
      - ``script``: the *full* raw locking script exactly as it appears on
        chain. This is what must be used verbatim when building a sighash
        preimage (the CashToken prefix, if any, is part of the committed
        scriptPubKey).
      - ``script_pubkey``: the underlying spendable script with any
        CashToken prefix stripped off, plus ``token_data`` with the decoded
        token fields. Use this for address extraction / OP_RETURN checks.
    """
    pos = 0
    version = tx_bytes[pos:pos + 4]
    pos += 4

    input_count, pos = read_varint(tx_bytes, pos)
    inputs = []
    for _ in range(input_count):
        prev_txid = tx_bytes[pos:pos + 32]
        pos += 32
        prev_index = tx_bytes[pos:pos + 4]
        pos += 4
        script_len, pos = read_varint(tx_bytes, pos)
        script_sig = tx_bytes[pos:pos + script_len]
        pos += script_len
        sequence = tx_bytes[pos:pos + 4]
        pos += 4
        inputs.append({
            "prev_txid": prev_txid,
            "prev_index": prev_index,
            "script_sig": script_sig,
            "sequence": sequence,
        })

    output_count, pos = read_varint(tx_bytes, pos)
    outputs = []
    for _ in range(output_count):
        value = tx_bytes[pos:pos + 8]
        pos += 8
        script_len, pos = read_varint(tx_bytes, pos)
        script = tx_bytes[pos:pos + script_len]
        pos += script_len

        token = parse_token_script(script)
        outputs.append({
            "value": value,
            "amount_int": int.from_bytes(value, "little"),
            "script": script,
            "token_prefix": token["prefix"] if token else None,
            "script_pubkey": token["script_pubkey"] if token else script,
            "token_data": token["data"] if token else None,
        })

    locktime = tx_bytes[pos:pos + 4]
    return {
        "version": version,
        "inputs": inputs,
        "outputs": outputs,
        "locktime": locktime,
    }

def parse_keypairs(buf: bytes, pos: int) -> Tuple[List[Tuple[bytes, bytes]], int]:
    """Parse one PSBT key-value map, returning ``[(key, value), ...]``."""
    pairs = []
    limit = len(buf)
    while pos < limit:
        key_len, pos = read_varint(buf, pos)
        if key_len == 0:
            return pairs, pos
        key = buf[pos:pos + key_len]
        pos += key_len
        val_len, pos = read_varint(buf, pos)
        value = buf[pos:pos + val_len]
        pos += val_len
        pairs.append((key, value))
    raise ValueError("unexpected end while parsing keypairs")

def parse_psbt(buf) -> Dict[str, Any]:
    """Parse a PSBT binary into global/input/output key-value maps.

    Key-value maps are lists of ``(key, value)`` tuples (in serialization
    order, duplicates preserved) rather than dicts, since PSBT allows
    repeated key *types* (e.g. multiple BIP32 derivations) that only differ
    by the data appended to the key type byte.
    """
    if isinstance(buf, (bytearray, memoryview)):
        buf = bytes(buf)
    if not isinstance(buf, bytes):
        raise TypeError(f"PSBT buffer must be bytes-like, got {type(buf).__name__}")
    if len(buf) < 5 or buf[:5] != b"psbt\xff":
        raise ValueError("invalid PSBT magic")
    pos = 5

    global_pairs, pos = parse_keypairs(buf, pos)

    unsigned_tx = None
    input_count = 0
    output_count = 0
    psbt_version = 0
    proprietary: List[Tuple[bytes, bytes]] = []
    for key, value in global_pairs:
        if key[0] == 0x00:  # PSBT_GLOBAL_UNSIGNED_TX
            unsigned_tx = value
        elif key[0] == 0x04:  # PSBT_GLOBAL_INPUT_COUNT (v2)
            input_count, _ = read_varint(value, 0)
        elif key[0] == 0x05:  # PSBT_GLOBAL_OUTPUT_COUNT (v2)
            output_count, _ = read_varint(value, 0)
        elif key[0] == 0xFB:  # PSBT_GLOBAL_VERSION
            psbt_version, _ = read_varint(value, 0)
        elif key[0] == 0xFC:  # PSBT_GLOBAL_PROPRIETARY
            proprietary.append((key, value))

    if unsigned_tx is None:
        raise ValueError("No unsigned transaction found in PSBT")

    parsed_tx = parse_transaction(unsigned_tx)
    if input_count == 0:
        input_count = len(parsed_tx["inputs"])
    if output_count == 0:
        output_count = len(parsed_tx["outputs"])

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
        "unsigned_tx": unsigned_tx,
        "parsed_tx": parsed_tx,
        "proprietary": proprietary,
    }

def resolve_spent_output(
    tx_input: Dict[str, Any], input_pairs: List[Tuple[bytes, bytes]]
) -> Optional[Dict[str, Any]]:
    """Resolve the UTXO an input spends, from PSBT_IN_NON_WITNESS_UTXO or
    PSBT_IN_WITNESS_UTXO, with CashToken decoding applied."""
    prev_index = int.from_bytes(tx_input["prev_index"], "little")
    for key, value in input_pairs:
        if key[0] == 0x00:  # PSBT_IN_NON_WITNESS_UTXO
            prev_tx = parse_transaction(value)
            if prev_index < len(prev_tx["outputs"]):
                return prev_tx["outputs"][prev_index]
            return None
        if key[0] == 0x01:  # PSBT_IN_WITNESS_UTXO
            out_value = value[:8]
            script_len, spos = read_varint(value, 8)
            script = value[spos:spos + script_len]
            token = parse_token_script(script)
            return {
                "value": out_value,
                "amount_int": int.from_bytes(out_value, "little"),
                "script": script,
                "token_prefix": token["prefix"] if token else None,
                "script_pubkey": token["script_pubkey"] if token else script,
                "token_data": token["data"] if token else None,
            }
    return None

class PSBTParser:

    def __init__(self, raw_psbt_bytes: bytearray, wallet_fingerprint: str):
        self.psbt_bytes: bytearray = raw_psbt_bytes
        self.wallet_fingerprint = wallet_fingerprint

        try:
            self.parsed = parse_psbt(self.psbt_bytes)
            self.tx = self._build_transaction()
            self._outputs = self.tx.arrange_outputs_by_type_and_category()
            self._inputs = self.tx.arrange_inputs_by_type_and_category()
        except Exception:
            logger.error(f"CRASHING PSBT BYTES HEX: {bytes(self.psbt_bytes).hex()}")
            raise

    @property
    def token_categories(self) -> List[str]:
        return sorted(self.tx.categories_type("ft")) if self.tx else []

    @property
    def ft_burning(self, category_id: str) -> bool:
        input_count = len(self.inputs[1].get(category_id, []))
        output_count = len(self.outputs[1].get(category_id, []))
        return input_count > 0 and output_count < input_count

    @property
    def nft_categories(self) -> List[str]:
        return sorted(self.tx.categories_type("nft")) if self.tx else []
    
    @property
    def input_amount(self) -> int:
        return self.tx.total_input if self.tx else 0

    @property
    def output_amount(self) -> int:
        return self.tx.total_output if self.tx else 0

    @property
    def fee_amount(self) -> int:
        return self.tx.fee if self.tx else 0

    @property
    def inputs(self) -> List[Dict[str, TxInput]]:
        return self._inputs

    @property
    def num_inputs(self) -> int:
        return len(self.tx.inputs) if self.tx else 0

    @property
    def outputs(self) -> List[Dict[str, TxOutput]]:
        return self._outputs
    def ft_output_amount(self, category_id: str) -> Optional[int]:
        total_ft_amount = 0
        for out in self.outputs[1].get(category_id, []):
            if out.token and out.token.ft_amount is not None:
                total_ft_amount += out.token.ft_amount
        return total_ft_amount if total_ft_amount > 0 else None

    @property
    def destination_addresses(self) -> List[str]:
        return [out.address for out in self.tx.outputs if out.address]

    
    @property
    def num_destinations(self) -> int:
        return len(self.destination_addresses)

    @property
    def op_return_data(self) -> Optional[bytes]:
        for out in self.tx.outputs:
            if out.script_pubkey.startswith(b"\x6a"):
                return out.script_pubkey[1:]  # strip OP_RETURN
        return None

    def token_destination_addresses(self, category_id: str) -> List[str]:
        return [out.address for out in self.outputs[1].get(category_id, []) if out.is_token_output and out.address]
        
    def output_at_index(self, index: int) -> Optional[TxOutput]:
        if self.tx and 0 <= index < len(self.tx.outputs):
            return self.tx.outputs[index]
        return None

    def get_warning(self, category_id: str) -> Optional[NFTWarning]:
        for out in self.outputs[0].get(category_id, []):
            if out.token.nft_data.capability == "minting":
                return NFTWarning.MINTING.value
            
        if len(self.inputs[0].get(category_id, [])) < len(self.outputs[0].get(category_id, [])):
            return NFTWarning.BURNING.value

        if len(self.inputs[0].get(category_id, [])) == len(self.outputs[0].get(category_id, [])):
            for i in range(len(self.inputs[0].get(category_id, []))):
                if ((self.inputs[0].get(category_id, [])[i].spent_output.token.nft_data.capability != self.outputs[0].get(category_id, [])[i].token.nft_data.capability) 
                    or self.inputs[0].get(category_id, [])[i].spent_output.token.nft_data.commitment != self.outputs[0].get(category_id, [])[i].token.nft_data.commitment):
                    return NFTWarning.BURNING.value
        return None

    @staticmethod
    def address_from_script(script_pubkey: bytes, is_token_tx: bool = False) -> Optional[str]:
        if script_pubkey.startswith(b"\x76\xa9\x14") and script_pubkey.endswith(b"\x88\xac"):
            hash160 = script_pubkey[3:23]
            addr = Bip44.hash160_to_cashaddr(hash160, version_byte=0x00).strip()
            if is_token_tx and addr.startswith("bitcoincash:q"):
                return addr.replace("q", "z", 1)
            return addr

        if script_pubkey.startswith(b"\xa9\x14") and script_pubkey.endswith(b"\x87"):
            hash160 = script_pubkey[2:22]
            addr = Bip44.hash160_to_cashaddr(hash160, version_byte=0x08).strip()
            if is_token_tx and addr.startswith("bitcoincash:p"):
                return addr.replace("p", "r", 1)
            return addr

        return None
    
    def _build_transaction(self) -> Transaction:
        raw_tx = self.parsed["parsed_tx"]

        inputs = []
        for i, raw_in in enumerate(raw_tx["inputs"]):
            input_pairs = self.parsed["inputs"][i]
            spent = resolve_spent_output(raw_in, input_pairs)
            spent_out = None
            if spent:
                spent_out = TxOutput(
                    value_satoshis=spent["amount_int"],
                    script_pubkey=spent["script_pubkey"],
                    full_script=spent["script"],
                    token=spent.get("token_data"),
                )
            inputs.append(TxInput(
                prev_txid=raw_in["prev_txid"],
                prev_index=int.from_bytes(raw_in["prev_index"], "little"),
                sequence=int.from_bytes(raw_in["sequence"], "little"),
                script_sig=raw_in["script_sig"],
                spent_output=spent_out,
            ))

        outputs = []
        for raw_out in raw_tx["outputs"]:
            outputs.append(TxOutput(
                value_satoshis=raw_out["amount_int"],
                script_pubkey=raw_out["script_pubkey"],
                full_script=raw_out["script"],
                token=raw_out.get("token_data"),
                address=self.address_from_script(raw_out["script_pubkey"], is_token_tx=raw_out.get("token_data") is not None)
            ))

        return Transaction(
            version=int.from_bytes(raw_tx["version"], "little"),
            locktime=int.from_bytes(raw_tx["locktime"], "little"),
            inputs=inputs,
            outputs=outputs,
            input_maps=self.parsed["inputs"],
            output_maps=self.parsed["outputs"],
            raw_unsigned_tx=self.parsed.get("unsigned_tx", b""),
        )
