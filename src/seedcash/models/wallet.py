from typing import Dict
from seedcash.models.bip44 import Bip44


class Wallet:
    def __init__(self, private_master_key, private_master_code) -> None:
        self.transaction: Dict[str, bytearray] = {}
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
    def _transaction(self) -> Dict[str, bytearray]:
        return self.transaction

    def add_transaction(self, tx_data: bytearray):
        from datetime import datetime

        now = datetime.now()
        dt_string = now.strftime("%H:%M %d/%m/%Y")
        self.transaction[dt_string] = tx_data

    def remove_transaction(self, tx_data: bytearray):
        for key, value in list(self.transaction.items()):
            if value == tx_data:
                del self.transaction[key]
                break