import struct
from typing import Dict, Any, List, Tuple, Optional

# ----------------------------------------------------------------------
# 1. Copy of your parser's helpers (must match exactly)
# ----------------------------------------------------------------------
def read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
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

def serialize_varint(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b'\xfd' + n.to_bytes(2, 'little')
    if n <= 0xFFFFFFFF:
        return b'\xfe' + n.to_bytes(4, 'little')
    return b'\xff' + n.to_bytes(8, 'little')

# ----------------------------------------------------------------------
# 2. Token script builder (your existing one)
# ----------------------------------------------------------------------
def build_token_script(underlying: bytes, token_data: Dict[str, Any]) -> bytes:
    bitfield = 0
    commitment = b''
    if 'nft' in token_data:
        bitfield |= 0x20
        cap_map = {'none': 0, 'mutable': 1, 'minting': 2}
        cap = token_data['nft'].get('capability', 'none')
        bitfield |= cap_map.get(cap, 0)
        commitment = token_data['nft'].get('commitment', b'')
        if commitment:
            bitfield |= 0x40
    if 'amount' in token_data and token_data['amount'] != "0":
        bitfield |= 0x10

    script = b'\xef' + token_data['category'] + bytes([bitfield])
    if bitfield & 0x40:
        script += serialize_varint(len(commitment)) + commitment
    if bitfield & 0x10:
        amount = int(token_data['amount'])
        script += serialize_varint(amount)
    script += underlying
    return script

# ----------------------------------------------------------------------
# 3. Serialization function (your existing one)
# ----------------------------------------------------------------------
def serialize_transaction(tx_json: Dict[str, Any]) -> bytes:
    out = b''
    out += struct.pack('<I', tx_json['version'])
    inputs = tx_json['inputs']
    out += serialize_varint(len(inputs))
    for inp in inputs:
        txid_hex = inp['outpointTransactionHash'].replace('0x', '').replace('<Uint8Array: ', '').replace('>', '').strip()
        prev_txid = bytes.fromhex(txid_hex)
        if len(prev_txid) != 32:
            raise ValueError(f"Invalid txid length: {len(prev_txid)}")
        out += prev_txid
        out += struct.pack('<I', inp['outpointIndex'])
        out += b'\x00'  # scriptSig length 0
        out += struct.pack('<I', inp['sequenceNumber'])
    outputs = tx_json['outputs']
    out += serialize_varint(len(outputs))
    for out_json in outputs:
        out += struct.pack('<Q', int(out_json['valueSatoshis']))
        lb_hex = out_json['lockingBytecode'].replace('0x', '').replace('<Uint8Array: ', '').replace('>', '').strip()
        underlying = bytes.fromhex(lb_hex)
        token = out_json.get('token')
        if token:
            category_hex = token['category'].replace('0x', '').replace('<Uint8Array: ', '').replace('>', '').strip()
            category = bytes.fromhex(category_hex)
            token_data = {'category': category}
            if 'amount' in token:
                token_data['amount'] = token['amount']
            if 'nft' in token:
                nft = token['nft']
                comm_hex = nft.get('commitment', '').replace('0x', '').replace('<Uint8Array: ', '').replace('>', '').strip()
                commitment = bytes.fromhex(comm_hex) if comm_hex else b''
                token_data['nft'] = {'capability': nft['capability'], 'commitment': commitment}
            script = build_token_script(underlying, token_data)
        else:
            script = underlying
        out += serialize_varint(len(script))
        out += script
    out += struct.pack('<I', tx_json['locktime'])
    return out

# ----------------------------------------------------------------------
# 4. Copy of your parse_transaction (from psbt_parser.py)
# ----------------------------------------------------------------------
def parse_token_script(script: bytes) -> Optional[Dict[str, Any]]:
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
        nft_data = {'capability': capability, 'commitment': nft_bytes}

    ft_amount = None
    if has_amount:
        ft_amount, pos = read_varint(script, pos)

    token_data = {
        'category_id': category[::-1].hex(),
        'ft_amount': ft_amount,
        'nft_data': nft_data,
    }
    return {
        'prefix': script[:pos],
        'script_pubkey': script[pos:],
        'data': token_data,
    }

def parse_transaction(tx_bytes: bytes) -> Dict[str, Any]:
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

# ----------------------------------------------------------------------
# 5. Test data (mixed NFT + FT)
# ----------------------------------------------------------------------
tx_data = {
  "version": 2,
  "locktime": 0,
  "inputs": [
    {
      "outpointIndex": 0,
      "outpointTransactionHash": "39924013508b6d4e5cd26db6b10b7a4dda6c62926460bd93cf19fddac57fefab",
      "sequenceNumber": 4294967295,
      "unlockingBytecode": ""
    },
    {
      "outpointIndex": 1,
      "outpointTransactionHash": "d3a9bc6045cfd251f057f9a0526c1ae41ec64dc10a837a4613d3a99e62faeb2c",
      "sequenceNumber": 4294967295,
      "unlockingBytecode": ""
    },
    {
      "outpointIndex": 0,
      "outpointTransactionHash": "36c291849d37c6098743e16f67cf89218f6281b56ffa65eb170de2e8fdea6023",
      "sequenceNumber": 4294967295,
      "unlockingBytecode": ""
    }
  ],
  "outputs": [
    {
      "lockingBytecode": "a91413ad973500bf8bb053969ba0a4965f9411d82a2587",
      "token": {
        "amount": "0",
        "category": "2ae0caa50077424b34725ed7250a0b1ff3bed7669119db96f0b9f56487fb701c",
        "nft": {
          "capability": "mutable",
          "commitment": ""
        }
      },
      "valueSatoshis": "981"
    },
    {
      "lockingBytecode": "a91413ad973500bf8bb053969ba0a4965f9411d82a2587",
      "token": {
        "amount": "100",
        "category": "2469acc5afa4b10cb5b5c04afb89c3a3ffd61c5da9c01e26d00951cae2a02544"
      },
      "valueSatoshis": "984"
    },
    {
      "lockingBytecode": "a914d3ddb1fab74803226d71ca5501fa3e7e704de1b687",
      "token": {
        "amount": "13",
        "category": "2469acc5afa4b10cb5b5c04afb89c3a3ffd61c5da9c01e26d00951cae2a02544"
      },
      "valueSatoshis": "984"
    }
  ]
}

def create_psbt_from_raw(raw_tx: bytes) -> bytes:
    """
    Wrap a raw transaction into a minimal PSBT.
    Input and output maps are empty (no UTXO info, no derivation paths).
    This is sufficient for parsing and displaying the transaction.
    """
    tx = parse_transaction(raw_tx)   # parse to get input/output counts
    input_count = len(tx["inputs"])
    output_count = len(tx["outputs"])

    out = b'psbt\xff'  # magic header

    # Global map: key 0x00 = unsigned_tx
    key = b'\x00'
    value = raw_tx
    out += serialize_varint(len(key)) + key + serialize_varint(len(value)) + value

    # Global map terminator
    out += b'\x00'

    # Input maps (empty)
    for _ in range(input_count):
        out += b'\x00'   # just the terminator

    # Output maps (empty)
    for _ in range(output_count):
        out += b'\x00'

    return out

# ----------------------------------------------------------------------
# 6. Round-trip test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    raw = serialize_transaction(tx_data)
    psbt = create_psbt_from_raw(raw)              
    print("PSBT hex:", psbt)
    print("Length:", len(raw))

    parsed = parse_transaction(raw)

    print("\n=== Parsed result ===")
    print(f"Version: {int.from_bytes(parsed['version'], 'little')}")
    print(f"Inputs: {len(parsed['inputs'])}")
    print(f"Outputs: {len(parsed['outputs'])}")
    print(f"Locktime: {int.from_bytes(parsed['locktime'], 'little')}")

    # Compare each output
    for i, (orig, parsed_out) in enumerate(zip(tx_data['outputs'], parsed['outputs'])):
        print(f"\nOutput {i}:")
        print(f"  Original value: {orig['valueSatoshis']}, parsed value: {parsed_out['amount_int']}")
        if parsed_out['amount_int'] != int(orig['valueSatoshis']):
            print(f"  ❌ VALUE MISMATCH!")

        orig_token = orig.get('token')
        parsed_token = parsed_out.get('token_data')
        if orig_token and parsed_token:
            print(f"  Token category (parsed): {parsed_token.get('category_id')}")
            if 'nft' in orig_token:
                print(f"  NFT capability: {parsed_token['nft_data']['capability']}, commitment: {parsed_token['nft_data']['commitment'].hex()}")
            if 'amount' in orig_token and orig_token['amount'] != "0":
                print(f"  FT amount: {parsed_token.get('ft_amount')}")
        elif not orig_token and not parsed_token:
            print("  No token")
        else:
            print("  ❌ TOKEN MISMATCH!")