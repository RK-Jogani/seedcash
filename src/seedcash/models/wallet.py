from typing import Dict
from seedcash.models.bip44 import Bip44


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