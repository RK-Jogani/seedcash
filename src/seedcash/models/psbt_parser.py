# New
import struct
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from seedcash.models.bip44 import Bip44


# Data Classes
@dataclass
class Token:
    @dataclass
    class NFTData:
        capability: str
        commitment: str

    class Warning(Enum):
        MINTING = "minting"
        BURNING = "burning"

    prefix: bytes
    script_pubkey: bytes
    category_id: str
    ft_amount: Optional[int] = None
    nft_data: Optional[NFTData] = None

class ScriptType(Enum):
    P2PKH = "p2pkh"
    P2SH20 = "p2sh20"
    P2SH32 = "p2sh32"
    OP_RETURN = "op_return"
    P2PK = "p2pk"
    UNKNOWN = "unknown"

@dataclass
class TxOutput:
    value_satoshis: int
    index: int = -1
    script_type: ScriptType = ScriptType.UNKNOWN
    full_script: bytes = field(repr=False, default=b"")  # exact on-chain script
    token: Optional[Token] = None
    address: Optional[str] = None

    @property
    def script_pubkey(self) -> bytes:
        return self.token.script_pubkey if self.token else self.full_script
    
@dataclass
class TxInput:
    prev_txid: bytes
    prev_index: int
    sequence: int
    script_sig: bytes = b""
    spent_output: Optional[TxOutput] = None

@dataclass
class ParseTransactionResult:
    version: bytes
    inputs: List[TxInput]
    outputs: List[TxOutput]
    locktime: bytes

@dataclass
class Inputs:
    ft: Dict[str, List[TxInput]] = field(default_factory=dict)
    nft: Dict[str, List[TxInput]] = field(default_factory=dict)

    
    # FT functions
    @property
    def get_ft_category_ids(self) -> List[str]:
            return list(self.ft.keys())
    
    def get_ft(self, category_id: str) -> List[TxInput]:
        return self.ft.get(category_id, [])

    def get_ft_count(self, category_id: str) -> int:
        return len(self.ft.get(category_id, []))

    def get_ft_total_amount(self, category_id: str) -> int:
        total_amount = 0
        for tx_in in self.ft.get(category_id, []):
            total_amount += tx_in.spent_output.token.ft_amount
        return total_amount

    
    # NFT functions
    @property
    def get_nft_category_ids(self) -> List[str]:
            return list(self.nft.keys())
    
    def get_nft(self, category_id: str) -> List[TxInput]:
            return self.nft.get(category_id, [])

    def get_nft_count(self, category_id: str) -> int:
        return len(self.nft.get(category_id, []))

    def has_minting_nft(self, category_id: str) -> bool:
        has_minting = False
        for tx_in in self.nft.get(category_id, []):
            if tx_in.spent_output.token.nft_data.capability == "minting":
                has_minting = True
                break
        return has_minting
  
@dataclass
class Outputs:
    ft: Dict[str, List[TxOutput]] = field(default_factory=dict)
    nft: Dict[str, List[TxOutput]] = field(default_factory=dict)

    def get_ft(self, category_id: str) -> List[TxOutput]:
        return self.ft.get(category_id, [])

    def get_ft_total_amount(self, category_id: str) -> int:
        total_amount = 0
        for tx_out in self.ft.get(category_id, []):
            if tx_out.token and tx_out.token.ft_amount is not None:
                total_amount += tx_out.token.ft_amount
        return total_amount
      
    # NFT functions
    def get_nft(self, category_id: str) -> List[TxOutput]:
        return self.nft.get(category_id, [])
    
    def get_nft_count(self, category_id: str) -> int:
        return len(self.nft.get(category_id, []))

@dataclass
class Genesis:
    categories: Dict[str, List[str]] = field(default_factory=lambda: {"nft": [], "ft": []})
    inputs: Inputs = field(default_factory=Inputs)
    outputs: Outputs = field(default_factory=Outputs)


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

def parse_token_script(script: bytes) -> Optional[Token]:

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
        nft_data: Token.NFTData = Token.NFTData(capability=capability, commitment=nft_bytes.hex())

    ft_amount = None
    if has_amount:
        ft_amount, pos = read_varint(script, pos)

    return Token(
        prefix=script[:pos],
        script_pubkey=script[pos:],
        category_id=category[::-1].hex(),
        ft_amount=ft_amount,
        nft_data=nft_data)

def classify_script(script_pubkey: bytes, is_token_tx: bool = False) -> Tuple[ScriptType, Optional[str]]:
    if not script_pubkey:
        return ScriptType.UNKNOWN, None

    # Standard P2PKH
    if (len(script_pubkey) == 25
            and script_pubkey.startswith(b"\x76\xa9\x14")
            and script_pubkey.endswith(b"\x88\xac")):
        vb = 0x10 if is_token_tx else 0x00
        addr = Bip44.hash160_to_cashaddr(script_pubkey[3:23], vb)
        return ScriptType.P2PKH, addr

    # Standard P2SH20
    if (len(script_pubkey) == 23
            and script_pubkey.startswith(b"\xa9\x14")
            and script_pubkey.endswith(b"\x87")):
        vb = 0x18 if is_token_tx else 0x08
        addr = Bip44.hash160_to_cashaddr(script_pubkey[2:22], vb)
        return ScriptType.P2SH20, addr

    # Standard P2SH32
    if (len(script_pubkey) == 35
            and script_pubkey.startswith(b"\xaa\x20")
            and script_pubkey.endswith(b"\x87")):
        vb = 0x1B if is_token_tx else 0x0B
        addr = Bip44.hash256_to_cashaddr(script_pubkey[2:34], vb)
        return ScriptType.P2SH32, addr

    if script_pubkey[0] == 0x6a:
        return ScriptType.OP_RETURN, None

    if (len(script_pubkey) in (35, 67)     # compressed / uncompressed
            and script_pubkey[-1] == 0xac):  # OP_CHECKSIG
        return ScriptType.P2PK, None

    return ScriptType.UNKNOWN, None

def parse_transaction(tx_bytes: bytes) -> ParseTransactionResult:
    """
    Parse the raw transaction bytes into a structured dictionary with inputs and outputs, 
    including token information if present.
    """
    pos = 0
    version = tx_bytes[pos:pos + 4]
    pos += 4

    input_count, pos = read_varint(tx_bytes, pos)
    inputs: List[TxInput] = []
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
        inputs.append(TxInput(
            prev_txid=prev_txid,
            prev_index=int.from_bytes(prev_index, "little"),
            sequence=int.from_bytes(sequence, "little"),
            script_sig=script_sig
        ))

    output_count, pos = read_varint(tx_bytes, pos)
    outputs: List[TxOutput] = []
    for vout in range(output_count):
        value = tx_bytes[pos:pos + 8]
        pos += 8
        script_len, pos = read_varint(tx_bytes, pos)
        script = tx_bytes[pos:pos + script_len]
        pos += script_len

        token: Optional[Token] = parse_token_script(script)
        script_type, address = classify_script(token.script_pubkey if token else script, is_token_tx=bool(token))
        outputs.append(TxOutput(
            value_satoshis=int.from_bytes(value, "little"),
            index=vout,
            script_type=script_type,
            full_script=script,
            token=token,
            address=address,
        ))

    locktime = tx_bytes[pos:pos + 4]
    return ParseTransactionResult(
        version=version,
        inputs=inputs,
        outputs=outputs,
        locktime=locktime
    )

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

    input_starts: int = 0
    input_ends: int = 0
    inputs = []
    for _ in range(input_count):
        if _ == 0:
            input_starts = pos
        pairs, pos = parse_keypairs(buf, pos)
        inputs.append(pairs)
        if _ == input_count - 1:
            input_ends = pos

    outputs = []
    for _ in range(output_count):
        pairs, pos = parse_keypairs(buf, pos)
        outputs.append(pairs)

    return {
        "global": global_pairs,
        "input_starts": input_starts,
        "input_ends": input_ends,
        "inputs": inputs,
        "outputs": outputs,
        "input_count": input_count,
        "output_count": output_count,
        "psbt_version": psbt_version,
        "unsigned_tx": unsigned_tx,
        "proprietary": proprietary,
    }

class PSBTParser:
    def __init__(self,raw_psbt_bytes: bytearray):
        self.psbt_bytes: bytearray = raw_psbt_bytes
        self.parsed = parse_psbt(raw_psbt_bytes)
        self.tx: ParseTransactionResult = parse_transaction(self.parsed["unsigned_tx"])
        self.inputs: Inputs
        self.outputs: Outputs
        self.categories: Dict[str, List[str]] = {"nft": [], "ft": []}
        self.genesis: Optional[Genesis] = None
        self.total_input_amount: int = 0
        self.total_output_amount: int = 0

        # Build the transaction
        self.build_transaction()

    # BCH View
    # Overview
    @property
    def input_count(self) -> int:
        return len(self.tx.inputs)


    @property
    def output_count(self) -> int:
        return len(self.tx.outputs)

    
    @property
    def bch_outputs(self) -> List[TxOutput]:
        return [tx_out for tx_out in self.tx.outputs if tx_out.address]

    @property
    def has_op_return(self) -> bool:
        return any(tx_out.script_type == ScriptType.OP_RETURN for tx_out in self.tx.outputs)
    
    @property
    def op_return_outputs(self) -> List[TxOutput]:
        return [tx_out for tx_out in self.tx.outputs if tx_out.script_type == ScriptType.OP_RETURN]

    @property
    def p2pk_outputs(self) -> List[TxOutput]:
        return [tx_out for tx_out in self.tx.outputs if tx_out.script_type == ScriptType.P2PK]

    @property
    def unknown_outputs(self) -> List[TxOutput]:
        return [tx_out for tx_out in self.tx.outputs if tx_out.script_type == ScriptType.UNKNOWN]
    
    # Math
    @property
    def input_amount(self) -> int:
        return self.total_input_amount

    @property
    def output_amount(self) -> int:
        return self.total_output_amount

    @property
    def fee_amount(self) -> int:
        return self.total_input_amount - self.total_output_amount

    # Token View
    # GENESIS
    @property
    def is_genesis(self) -> bool:
        return self.genesis is not None

    @property
    def genesis_categories(self) -> Dict[str, List[str]]:
        if self.genesis:
            return self.genesis.categories

    # NON GENESIS
    # FT functions
    def is_ft_burning(self, category_id: str) -> bool:
        return self.inputs.get_ft_total_amount(category_id) > self.outputs.get_ft_total_amount(category_id)

    # NFT functions
    def get_nft_warnings(self, category_id: str) -> List[str]:
        warnings = []
        if self.inputs.has_minting_nft(category_id):
            warnings.append(Token.Warning.MINTING.value)
        if self._nft_burned(category_id):
            warnings.append(Token.Warning.BURNING.value)
        return warnings

    def _nft_burned(self, category_id: str) -> bool:
        def bag(items, get_token):
            result = {}
            for item in items:
                nft = get_token(item).nft_data
                if nft:
                    key = (nft.capability, nft.commitment)
                    result[key] = result.get(key, 0) + 1
            return result

        inputs = bag(self.inputs.get_nft(category_id), lambda item: item.spent_output.token)
        outputs = bag(self.outputs.get_nft(category_id), lambda item: item.token)
        if self.genesis:
            for key, count in bag(self.genesis.outputs.nft.get(category_id, []), lambda item: item.token).items():
                outputs[key] = outputs.get(key, 0) + count

        return any(outputs.get(key, 0) < count for key, count in inputs.items())

    def resolve_spent_output(
        self,
        prev_index: int, 
        input_pairs: List[Tuple[bytes, bytes]],) -> Optional[TxOutput]:
        """
        Resolve the UTXO an input spends, from PSBT_IN_NON_WITNESS_UTXO or
        PSBT_IN_WITNESS_UTXO, with CashToken decoding applied.
        """

        for key, value in input_pairs:
            if key[0] == 0x00:  # PSBT_IN_NON_WITNESS_UTXO
                prev_tx = parse_transaction(value)
                if prev_index < len(prev_tx.outputs):
                    return prev_tx.outputs[prev_index]   # TxOutput
                return None
            if key[0] == 0x01:  # PSBT_IN_WITNESS_UTXO
                out_value = value[:8]
                script_len, spos = read_varint(value, 8)
                script = value[spos:spos + script_len]
                token = parse_token_script(script)
                script_type, address = classify_script(token.script_pubkey if token else script, is_token_tx=bool(token))
                return TxOutput(
                    value_satoshis=int.from_bytes(out_value, "little"),
                    index=prev_index,
                    script_type=script_type,
                    full_script=script,
                    token=token,
                    address=address,
                )
        return None

    def build_transaction(self):
        is_genesis_tx: bool = False
        genesis_categories: Dict[str, List[str]] = {"nft": [], "ft": []}

        # Non-genesis buckets (category-id → list)
        inputs: Dict[str, Dict[str, List[TxInput]]] = {"nft": {}, "ft": {}}
        outputs: Dict[str, Dict[str, List[TxOutput]]] = {"nft": {}, "ft": {}}

        # Genesis buckets — outer key is "nft"/"ft", inner key is category-id
        in_genesis_dict: Dict[str, Dict[str, List[TxInput]]] = {"nft": {}, "ft": {}}
        out_genesis_dict: Dict[str, Dict[str, List[TxOutput]]] = {"nft": {}, "ft": {}}

        # Candidate funding inputs for a genesis category (non-token, prev_index == 0)
        in_genesis_catId: Dict[str, List[str]] = {}

        # ---------------- INPUTS ----------------
        for i, tx_in in enumerate(self.tx.inputs):
            spent = self.resolve_spent_output(tx_in.prev_index, self.parsed["inputs"][i])
            tx_in.spent_output = spent

            if spent is None:
                raise ValueError(f"input {i} has no UTXO in the PSBT; cannot verify what is being spent")

            self.total_input_amount += spent.value_satoshis

            if spent.token:
                category = spent.token.category_id
                if spent.token.nft_data is not None:
                    if category not in self.categories["nft"]:
                        self.categories["nft"].append(category)
                    inputs["nft"].setdefault(category, []).append(tx_in)
                if spent.token.ft_amount is not None:
                    if category not in self.categories["ft"]:
                        self.categories["ft"].append(category)
                    inputs["ft"].setdefault(category, []).append(tx_in)
            else:
                if tx_in.prev_index == 0:
                    category_id = tx_in.prev_txid[::-1].hex()
                    in_genesis_catId.setdefault(category_id, []).append(tx_in)

        # ---------------- OUTPUTS ----------------
        for tx_out in self.tx.outputs:

            self.total_output_amount += tx_out.value_satoshis

            if not tx_out.token:
                continue

            category = tx_out.token.category_id
            
            is_new_nft = (tx_out.token.nft_data is not None and category not in self.categories["nft"])
            is_new_ft  = (tx_out.token.ft_amount is not None and category not in self.categories["ft"])

            if is_new_nft and category not in in_genesis_catId:
                raise ValueError(f"category {category} appears in outputs with no genesis input and no matching token input")
            if is_new_ft and category not in in_genesis_catId:
                raise ValueError(f"category {category} appears in outputs with no genesis input and no matching token input")

            if tx_out.token.nft_data is not None:
                if is_new_nft:
                    is_genesis_tx = True
                    if category not in genesis_categories["nft"]:
                        genesis_categories["nft"].append(category) 
                    out_genesis_dict["nft"].setdefault(category, []).append(tx_out)
                    if category in in_genesis_catId and category not in in_genesis_dict["nft"]:
                        in_genesis_dict["nft"].setdefault(category, []).extend(in_genesis_catId[category])
                else:
                    outputs["nft"].setdefault(category, []).append(tx_out)

            # --- FT side ---
            if tx_out.token.ft_amount is not None:
                if is_new_ft:
                    is_genesis_tx = True
                    if category not in genesis_categories["ft"]:
                        genesis_categories["ft"].append(category)
                    out_genesis_dict["ft"].setdefault(category, []).append(tx_out)
                    if category in in_genesis_catId and category not in in_genesis_dict["ft"]:
                        in_genesis_dict["ft"].setdefault(category, []).extend(in_genesis_catId[category])
                else:
                    outputs["ft"].setdefault(category, []).append(tx_out)

        
        self.inputs=Inputs(
            nft=inputs["nft"],
            ft=inputs["ft"]
        )

        self.outputs=Outputs(
            nft=outputs["nft"],
            ft=outputs["ft"],
        )

        self.genesis=Genesis(
            categories=genesis_categories,
            inputs=Inputs(
                nft=in_genesis_dict["nft"] if "nft" in in_genesis_dict else {},
                ft=in_genesis_dict["ft"] if "ft" in in_genesis_dict else {},
            ),
            outputs=Outputs(
                nft=out_genesis_dict["nft"] if "nft" in out_genesis_dict else {},
                ft=out_genesis_dict["ft"] if "ft" in out_genesis_dict else {}
            )
        ) if is_genesis_tx else None