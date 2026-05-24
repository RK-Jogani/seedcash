from typing import List, Tuple

class PSBT:
    magic: bytes = b"psbt\xff"
    global_map: List[Tuple[bytes, bytes]]
    inputs: List[List[Tuple[bytes, bytes]]]   # each input is a list of key-value pairs
    outputs: List[List[Tuple[bytes, bytes]]]
    
    # Derived fields (optional)
    unsigned_tx: bytes
    total_in: int
    total_out: int
    fee: int