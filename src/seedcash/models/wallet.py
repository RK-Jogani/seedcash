from typing import List
from seedcash.models.bip44 import Bip44

from seedcash.models.psbt_parser import PSBTParser


class Wallet:
    def __init__(self, private_master_key, private_master_code) -> None:
        self.transaction: List[PSBTParser] = None
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
