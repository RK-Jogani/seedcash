# src/tests/test_sc07_cashaddr.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seedcash.models.bip44 import Bip44
from seedcash.models.psbt_parser import classify_script, ScriptType

H160 = bytes.fromhex("f5bf48b397dac9") + bytes(13)  # pad to 20 if needed
# Use a real 20-byte hash:
H160 = bytes.fromhex("f5bf48b397dac918a1fe95962deb1a885b7834f9")  # example length check

class TestSC07CashAddr:

    def test_plain_p2pkh_is_q(self):
        addr = Bip44.hash160_to_cashaddr(H160, version_byte=0x00)
        assert ":q" in addr or addr.split(":")[1].startswith("q")

    def test_token_p2pkh_is_z(self):
        addr = Bip44.hash160_to_cashaddr(H160, version_byte=0x10)
        assert addr.split(":")[1].startswith("z")

    def test_plain_p2sh20_is_p(self):
        addr = Bip44.hash160_to_cashaddr(H160, version_byte=0x08)
        assert addr.split(":")[1].startswith("p")

    def test_token_p2sh_version(self):
        # 0x18 → r… for token P2SH20 (per audit)
        addr = Bip44.hash160_to_cashaddr(H160, version_byte=0x18)
        assert addr.split(":")[1].startswith("r")

    def test_classify_token_p2pkh_uses_token_version(self):
        script = b"\x76\xa9\x14" + H160 + b"\x88\xac"
        stype, addr = classify_script(script, is_token_tx=True)
        assert stype == ScriptType.P2PKH
        assert addr is not None
        assert addr.split(":")[1].startswith("z")  # not p

    def test_classify_plain_p2pkh_is_q(self):
        script = b"\x76\xa9\x14" + H160 + b"\x88\xac"
        stype, addr = classify_script(script, is_token_tx=False)
        assert stype == ScriptType.P2PKH
        assert addr.split(":")[1].startswith("q")