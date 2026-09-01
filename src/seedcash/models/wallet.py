from seedcash.models.bip44 import Bip44
from seedcash.models.psbt_parser import PSBTParser
from typing import Optional
from seedcash.models.psbt_signer import BitcoinCashSigner


class Wallet:
    def __init__(self, private_master_key, private_master_code) -> None:
        self.xpriv, self.xpub, self.fingerprint = Bip44.get_wallet_data(
            private_master_key, private_master_code
        )

    @property
    def _xpriv(self) -> str:
        return self.xpriv

    @property
    def _xpub(self) -> str:
        return self.xpub

    @property
    def _fingerprint(self) -> str:
        return self.fingerprint

    @property
    def _seed_bits(self) -> Optional[str]:
        return self.seed_bits

    def set_seed_bits(self, seed_bits: str) -> None:
        self.seed_bits = seed_bits
        
    def sign_psbt(self, parser: PSBTParser) -> bytearray:
        bchsigner = BitcoinCashSigner(self._xpriv, parser)
        return bchsigner.signed_psbt()