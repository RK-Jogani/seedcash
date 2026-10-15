# New
import hashlib
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
    full_script: bytes = field(repr=False, default=b"")
    token: Optional[Token] = None
    address: Optional[str] = None

    @property
    def script_pubkey(self) -> bytes:
        return self.token.script_pubkey if self.token else self.full_script

    @property
    def op_return_text(self) -> str:
        """Decode pushed UTF-8 strings; reject malformed scripts and binary payloads.

        Separate pushes with newlines so their boundaries remain visible. Callers
        should display the original script as hex when this raises ValueError.
        """
        if not self.full_script.startswith(b"\x6a"):
            raise ValueError("Expected OP_RETURN")
        offset = 1
        parts = []
        while offset < len(self.full_script):
            opcode = self.full_script[offset]
            offset += 1
            if opcode <= 0x4b:
                length = opcode
            elif opcode in (0x4c, 0x4d, 0x4e):
                width = {0x4c: 1, 0x4d: 2, 0x4e: 4}[opcode]
                if offset + width > len(self.full_script):
                    raise ValueError("Truncated pushdata length")
                length = int.from_bytes(self.full_script[offset:offset + width], "little")
                offset += width
            else:
                raise ValueError("Non-push opcode in OP_RETURN")
            if offset + length > len(self.full_script):
                raise ValueError("Truncated pushdata payload")
            part = self.full_script[offset:offset + length].decode("utf-8", errors="strict")
            if any(not char.isprintable() and char not in "\n\r\t" for char in part):
                raise ValueError("Non-printable OP_RETURN payload")
            parts.append(part)
            offset += length
        return "\n".join(parts)


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
class Category:
    category_id: str
    is_genesis: bool = False
    is_ft: bool = False

    inputs: List[TxInput] = field(default_factory=list)
    
    outputs: List[TxOutput] = field(default_factory=list)
    output_no: int = 0

    def add_input(self, tx_input: TxInput):
        self.inputs.append(tx_input)

    def add_output(self, tx_output: TxOutput):
        self.outputs.append(tx_output)

    @property
    def next_output(self) -> bool:
        if self.output_no < len(self.outputs)-1:
            self.output_no += 1
            return True
        return False

    @property
    def previous_output(self) -> bool:
        if self.output_no > 0:
            self.output_no -= 1
            return True
        return False

    @property
    def address(self) -> Optional[str]:
        if self.outputs:
            return self.outputs[self.output_no].address
        return None

    @property
    def is_last_output(self) -> bool:
        return self.output_no == len(self.outputs) - 1

    @property
    def inputs_count(self) -> int:
        return len(self.inputs)
    
    @property
    def outputs_count(self) -> int:
        return len(self.outputs)
    
    @property
    def ft_inputs_total_amount(self) -> int:
        total_amount = 0
        for tx_in in self.inputs:
            total_amount += tx_in.spent_output.token.ft_amount
        return total_amount

    @property
    def ft_output_amount(self) -> int:
        if self.outputs:
            return self.outputs[self.output_no].token.ft_amount
        return 0

    @property
    def ft_outputs_total_amount(self) -> int:
        total_amount = 0
        for tx_out in self.outputs:
            total_amount += tx_out.token.ft_amount
        return total_amount

    nft_detail_no: int = 0
    @property
    def next_nft_detail(self) -> bool:
        if self.nft_detail_no < len(self.outputs)-1:
            self.nft_detail_no += 1
            return True
        return False

    @property
    def previous_nft_detail(self) -> bool:
        if self.nft_detail_no > 0:
            self.nft_detail_no -= 1
            return True
        return False

    @property
    def nft_commitment(self) -> str:
        tx_out = self.outputs[self.nft_detail_no]
        if tx_out and tx_out.token and tx_out.token.nft_data:
            return tx_out.token.nft_data.commitment
        return ""

    @property
    def nft_capability(self) -> str:
        tx_out = self.outputs[self.nft_detail_no]
        if tx_out and tx_out.token and tx_out.token.nft_data:
            return tx_out.token.nft_data.capability
        return ""
    
    @property
    def is_nft_minted(self) -> bool:
        has_minting = False
        for tx_in in self.inputs:
            if tx_in.spent_output.token.nft_data.capability == "minting":
                has_minting = True
                break
        return has_minting


    
@dataclass
class TokenReview:
    ft_categories: List[Category] = field(default_factory=list)
    ft_category_num: int = 0

    nft_categories: List[Category] = field(default_factory=list)
    nft_category_num: int = 0

    current_category: Optional[Category] = None

    @property
    def initiate(self):
        if self.ft_categories:
            self.current_category = self.ft_categories[0]
        elif self.nft_categories:
            self.current_category = self.nft_categories[0]

    @property
    def next_category(self) -> Optional[Category]:
        if self.ft_category_num < len(self.ft_categories)-1:
            self.ft_category_num += 1
            self.current_category = self.ft_categories[self.ft_category_num]
            return self.current_category
        
        elif self.nft_category_num == 0 and self.current_category.is_ft:
            if not self.nft_categories:
                return None
            self.current_category = self.nft_categories[0]
            return self.current_category
        
        if self.nft_category_num < len(self.nft_categories)-1:
            self.nft_category_num += 1
            self.current_category = self.nft_categories[self.nft_category_num]
            return self.current_category
        return None

    @property
    def previous_category(self) -> Optional[Category]:
        if self.nft_category_num > 0:
            self.current_category = self.nft_categories[self.nft_category_num-1]
            self.nft_category_num -= 1
            return self.current_category
        
        if (self.current_category and not self.current_category.is_ft and self.ft_categories):
            self.current_category = self.ft_categories[self.ft_category_num]
            return self.current_category
        
        if self.ft_category_num > 0:
            self.current_category = self.ft_categories[self.ft_category_num-1]
            self.ft_category_num -= 1
            return self.current_category
        return None

    def add_category(self, is_ft: bool, category: Category):
        if is_ft:
            self.ft_categories.append(category)
        else:
            self.nft_categories.append(category)

def read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Read a Bitcoin-style varint (CompactSize uint) at ``pos``."""
    if pos >= len(buf):
        raise ValueError("pos out of range")
    b = buf[pos]
    if b < 0xFD:
        return b, pos + 1
    if b == 0xFD:
        if pos + 3 > len(buf):
            raise ValueError("truncated CompactSize uint16")
        value = struct.unpack_from("<H", buf, pos + 1)[0]
        if value < 0xFD:
            raise ValueError("non-minimal CompactSize encoding")
        return value, pos + 3
    if b == 0xFE:
        if pos + 5 > len(buf):
            raise ValueError("truncated CompactSize uint32")
        value = struct.unpack_from("<I", buf, pos + 1)[0]
        if value <= 0xFFFF:
            raise ValueError("non-minimal CompactSize encoding")
        return value, pos + 5
    if pos + 9 > len(buf):
        raise ValueError("truncated CompactSize uint64")
    value = struct.unpack_from("<Q", buf, pos + 1)[0]
    if value <= 0xFFFFFFFF:
        raise ValueError("non-minimal CompactSize encoding")
    return value, pos + 9

def read_token_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Read a minimally encoded CashTokens CompactSize value."""

    if pos >= len(buf):
        raise ValueError("missing CompactSize value")

    value, new_pos = read_varint(buf, pos)
    marker = buf[pos]

    if (
        (marker == 0xFD and value < 0xFD)
        or (marker == 0xFE and value <= 0xFFFF)
        or (marker == 0xFF and value <= 0xFFFFFFFF)
    ):
        raise ValueError("non-minimal CompactSize encoding")

    return value, new_pos

def parse_token_script(script: bytes) -> Optional[Token]:
    """Parse a CashTokens prefix and return the token + remaining locking bytecode."""

    if not script or script[0] != 0xEF:
        return None

    pos = 1

    # category_id
    if len(script) < pos + 32:
        return None

    category = script[pos:pos + 32]
    pos += 32

    # bitfield
    if len(script) <= pos:
        return None

    bitfield = script[pos]
    pos += 1

    # RESERVED_BIT
    if bitfield & 0x80:
        return None

    has_commitment_length = bool(bitfield & 0x40)
    has_nft = bool(bitfield & 0x20)
    has_amount = bool(bitfield & 0x10)
    capability_bits = bitfield & 0x0F

    if not has_nft and has_commitment_length:
        return None
    if not has_nft and capability_bits != 0:
        return None
    if has_nft and capability_bits > 2:
        return None
    if not has_nft and not has_amount:
        return None

    capability_map = { 0: "none", 1: "mutable", 2: "minting"}
    capability = (capability_map[capability_bits] if has_nft else None)

    nft_data = None
    if has_nft:
        if has_commitment_length:
            try:
                nft_len, pos = read_token_varint(script, pos)
            except (IndexError, struct.error, ValueError):
                return None
            if nft_len == 0 or nft_len > 40:
                return None
            if len(script) < pos + nft_len:
                return None
            nft_bytes = script[pos:pos + nft_len]
            pos += nft_len
        else:
            nft_bytes = b""
        nft_data: Token.NFTData = Token.NFTData(capability=capability,commitment=nft_bytes.hex())

    ft_amount = None
    if has_amount:
        try:
            ft_amount, pos = read_token_varint(script, pos)
        except (IndexError, struct.error, ValueError):
            return None
        if not 0 < ft_amount <= 0x7FFFFFFFFFFFFFFF:
            return None

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
    if len(tx_bytes) < 10:
        raise ValueError("truncated transaction")
    pos = 0
    version = tx_bytes[pos:pos + 4]
    pos += 4

    input_count, pos = read_varint(tx_bytes, pos)
    inputs: List[TxInput] = []
    for _ in range(input_count):
        if pos + 36 > len(tx_bytes):
            raise ValueError("truncated transaction input")
        prev_txid = tx_bytes[pos:pos + 32]
        pos += 32
        prev_index = tx_bytes[pos:pos + 4]
        pos += 4
        script_len, pos = read_varint(tx_bytes, pos)
        if pos + script_len + 4 > len(tx_bytes):
            raise ValueError("truncated transaction input script")
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
        if pos + 8 > len(tx_bytes):
            raise ValueError("truncated transaction output")
        value = tx_bytes[pos:pos + 8]
        pos += 8
        script_len, pos = read_varint(tx_bytes, pos)
        if pos + script_len > len(tx_bytes):
            raise ValueError("truncated transaction output script")
        script = tx_bytes[pos:pos + script_len]
        pos += script_len

        token: Optional[Token] = parse_token_script(script)
        if script.startswith(b"\xef") and token is None:
            raise ValueError("invalid token prefix")
        script_type, address = classify_script(token.script_pubkey if token else script, is_token_tx=bool(token))
        
        if script_type == ScriptType.UNKNOWN and not script.startswith(b"\xef"):
            raise ValueError("unknown script type")
        
        outputs.append(TxOutput(
            value_satoshis=int.from_bytes(value, "little"),
            index=vout,
            script_type=script_type,
            full_script=script,
            token=token,
            address=address,
        ))

    if pos + 4 != len(tx_bytes):
        raise ValueError("transaction has trailing or missing bytes")
    locktime = tx_bytes[pos:pos + 4]
    return ParseTransactionResult(
        version=version,
        inputs=inputs,
        outputs=outputs,
        locktime=locktime
    )

def resolve_spent_output(
        prev_index: int, 
        input_pairs: List[Tuple[bytes, bytes]],
        prev_txid: Optional[bytes] = None,) -> Optional[TxOutput]:
        """
        Resolve the UTXO an input spends, from PSBT_IN_NON_WITNESS_UTXO or
        PSBT_IN_WITNESS_UTXO, with CashToken decoding applied.
        """

        for key, value in input_pairs:
            if key[0] == 0x00:  # PSBT_IN_NON_WITNESS_UTXO
                expected_txid = hashlib.sha256(hashlib.sha256(value).digest()).digest()
                if prev_txid is not None and expected_txid != prev_txid:
                    raise ValueError("parent transaction hash mismatch")
                prev_tx = parse_transaction(value)
                if prev_index < len(prev_tx.outputs):
                    return prev_tx.outputs[prev_index]   # TxOutput
                return None
            if key[0] == 0x01:  # PSBT_IN_WITNESS_UTXO
                out_value = value[:8]
                script_len, spos = read_varint(value, 8)
                script = value[spos:spos + script_len]
                token = parse_token_script(script)
                if script.startswith(b"\xef") and token is None:
                    raise ValueError("invalid token prefix")
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

def parse_keypairs(buf: bytes, pos: int) -> Tuple[List[Tuple[bytes, bytes]], int]:
    """Parse one PSBT key-value map, returning ``[(key, value), ...]``."""
    pairs = []
    seen_keys = set()
    limit = len(buf)
    while pos < limit:
        key_len, pos = read_varint(buf, pos)
        if key_len == 0:
            return pairs, pos
        if pos + key_len > limit:
            raise ValueError("truncated PSBT key")
        key = buf[pos:pos + key_len]
        pos += key_len
        if key in seen_keys:
            raise ValueError("duplicate PSBT key")
        seen_keys.add(key)
        val_len, pos = read_varint(buf, pos)
        if pos + val_len > limit:
            raise ValueError("truncated PSBT value")
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

    known_global_types = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0xFB, 0xFC}
    known_input_types = {
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x0E, 0x0F, 0x10, 0xFC,
    }
    known_output_types = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0xFC, 0x36}

    def reject_unknown_types(pairs, allowed_types, scope):
        for key, _ in pairs:
            if not key:
                raise ValueError(f"empty PSBT {scope} key")
            if key[0] not in allowed_types:
                raise ValueError(f"unknown PSBT {scope} field 0x{key[0]:02x}")

    reject_unknown_types(global_pairs, known_global_types, "global")

    unsigned_tx = None
    input_count = 0
    output_count = 0
    psbt_version = 0
    proprietary: List[Tuple[bytes, bytes]] = []
    for key, value in global_pairs:
        if not key:
            raise ValueError("empty PSBT key")
        if key[0] == 0x00:  # PSBT_GLOBAL_UNSIGNED_TX
            unsigned_tx = value
        elif key[0] == 0x04:  # PSBT_GLOBAL_INPUT_COUNT (v2)
            input_count, count_pos = read_varint(value, 0)
            if count_pos != len(value):
                raise ValueError("invalid PSBT input count")
        elif key[0] == 0x05:  # PSBT_GLOBAL_OUTPUT_COUNT (v2)
            output_count, count_pos = read_varint(value, 0)
            if count_pos != len(value):
                raise ValueError("invalid PSBT output count")
        elif key[0] == 0xFB:  # PSBT_GLOBAL_VERSION
            # The version value is uint32 little-endian, not CompactSize.
            if key != b"\xfb" or len(value) != 4:
                raise ValueError("invalid PSBT version")
            psbt_version = int.from_bytes(value, "little")
            if psbt_version not in (0, 145):
                raise ValueError("unsupported PSBT version")
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
        reject_unknown_types(pairs, known_input_types, "input")
        inputs.append(pairs)
        if _ == input_count - 1:
            input_ends = pos

    # Paytaca v145 writes an additional separator after the input maps.
    # Keep input_ends before this byte: the signer preserves the original
    # suffix when rebuilding input maps, including this separator.
    if psbt_version == 145 and pos < len(buf) and buf[pos] == 0:
        pos += 1

    outputs = []
    for _ in range(output_count):
        pairs, pos = parse_keypairs(buf, pos)
        reject_unknown_types(pairs, known_output_types, "output")
        for key, value in pairs:
            if key == b"\x36" and parse_token_script(value) is None:
                raise ValueError("invalid token prefix")
        outputs.append(pairs)

    if pos != len(buf):
        raise ValueError("PSBT has trailing bytes")

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
        self.total_input_amount: int = 0
        self.total_output_amount: int = 0
        self.token_review: TokenReview = None

        # Build the transaction
        self.build_transaction()
        self.validate_no_token_burning()

    def validate_no_token_burning(self):
        """Reject token loss before a parsed PSBT can enter review."""
        if self.token_review is None:
            return
        for category in self.token_review.ft_categories:
            input_amount = sum(item.spent_output.token.ft_amount for item in category.inputs)
            output_amount = sum(item.token.ft_amount for item in category.outputs)
            if input_amount > output_amount:
                raise ValueError("PSBT burns fungible tokens")

        for category in self.token_review.nft_categories:
            # NFT categories contain only inputs/outputs with NFT data.
            # Check counts first without allocating intermediate lists.
            if len(category.outputs) < len(category.inputs):
                raise ValueError("PSBT burns non-fungible tokens")
            if not category.inputs:
                continue

            has_minting = any(
                item.spent_output.token.nft_data.capability == "minting"
                for item in category.inputs
            ) or any(
                item.token.nft_data.capability == "minting"
                for item in category.outputs
            )
            if not has_minting:
                continue

            # Minted replacements can hide a loss in the total NFT count.
            # Match each input's capability and commitment, including duplicates.
            output_nfts = {}
            for item in category.outputs:
                nft = item.token.nft_data
                key = (nft.capability, nft.commitment)
                output_nfts[key] = output_nfts.get(key, 0) + 1
            for item in category.inputs:
                nft = item.spent_output.token.nft_data
                key = (nft.capability, nft.commitment)
                if output_nfts.get(key, 0) == 0:
                    raise ValueError("PSBT burns non-fungible tokens")
                output_nfts[key] -= 1

    # BCH View
    @property
    def input_count(self) -> int:
        return len(self.tx.inputs)

    @property
    def output_count(self) -> int:
        return len(self.tx.outputs)

    @property
    def outputs(self) -> List[TxOutput]:
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
    def has_p2pk(self) -> bool:
        return any(tx_out.script_type == ScriptType.P2PK for tx_out in self.tx.outputs)
    
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


    # Build Transaction
    def build_transaction(self):
        ft_categories: Dict[str, Category] = {}
        nft_categories: Dict[str, Category] = {}

        # Candidate funding inputs for a genesis category (prev_index == 0)
        in_genesis_catId: Dict[str, List[str]] = {}

        # ---------------- INPUTS ----------------
        for i, tx_in in enumerate(self.tx.inputs):
            spent = resolve_spent_output(tx_in.prev_index, self.parsed["inputs"][i], prev_txid=tx_in.prev_txid)
            tx_in.spent_output = spent

            if spent is None:
                raise ValueError(f"input {i} has no UTXO in the PSBT; cannot verify what is being spent")

            self.total_input_amount += spent.value_satoshis

            if tx_in.prev_index == 0:
                category_id = tx_in.prev_txid[::-1].hex()
                in_genesis_catId.setdefault(category_id, []).append(tx_in)

            if spent.token:
                category = spent.token.category_id
                if spent.token.nft_data is not None:
                    if category not in nft_categories:
                        nft_categories.setdefault(
                            category, 
                            Category(category_id=category))
                    nft_categories[category].add_input(tx_in)
                if spent.token.ft_amount is not None:
                    if category not in ft_categories:
                        ft_categories.setdefault(
                            category, 
                            Category(category_id=category, is_ft=True))
                    ft_categories[category].add_input(tx_in)


        # ---------------- OUTPUTS ----------------
        for tx_out in self.tx.outputs:

            self.total_output_amount += tx_out.value_satoshis

            if not tx_out.token:
                continue

            category = tx_out.token.category_id
            
            is_new_nft = (tx_out.token.nft_data is not None and category not in nft_categories)
            is_new_ft  = (tx_out.token.ft_amount is not None and category not in ft_categories)

            if is_new_nft and category not in in_genesis_catId:
                raise ValueError(f"category {category} appears in outputs with no genesis input and no matching token input")
            if is_new_ft and category not in in_genesis_catId:
                raise ValueError(f"category {category} appears in outputs with no genesis input and no matching token input")

            if tx_out.token.nft_data is not None:
                if is_new_nft:
                    if category not in nft_categories:
                        nft_categories.setdefault(
                            category, 
                            Category(category_id=category, is_genesis=True))
                    nft_categories[category].add_output(tx_out)
                    if category in in_genesis_catId and category not in nft_categories:
                        for input in in_genesis_catId[category]:
                            nft_categories[category].add_input(input) 
                else:
                    nft_categories[category].add_output(tx_out)

            # --- FT side ---
            if tx_out.token.ft_amount is not None:
                if is_new_ft:
                    if category not in ft_categories:
                        ft_categories.setdefault(
                            category, 
                            Category(category_id=category, is_ft=True, is_genesis=True))
                    ft_categories[category].add_output(tx_out)
                    if category in in_genesis_catId and category not in ft_categories:
                        for input in in_genesis_catId[category]:
                            ft_categories[category].add_input(input)
                else:
                    ft_categories[category].add_output(tx_out)

        if ft_categories or nft_categories:
            self.token_review = TokenReview(
                ft_categories=list(ft_categories.values()),
                nft_categories=list(nft_categories.values())
            )
