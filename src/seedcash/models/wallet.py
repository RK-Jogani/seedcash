from seedcash.models.bip44 import Bip44
from seedcash.models.psbt_parser import PSBTParser
from seedcash.models.psbt_signer import BitcoinCashSigner


class Wallet:
    def __init__(self, private_master_key, private_master_code) -> None:
        self._xpriv, self._xpub, self._fingerprint = Bip44.get_wallet_data(
            private_master_key, private_master_code
        )

    @property
    def xpriv(self) -> bytearray:
        return self._xpriv

    @property
    def xpub(self) -> str:
        return self._xpub.decode('utf-8')

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def discard_wallet(self):
        if isinstance(self._xpriv, bytearray):
            self._xpriv[:] = b"\x00" * len(self._xpriv)
        self._xpriv = None
        self._xpub = ""
        self._fingerprint = ""
    
    def sign_psbt(self, parser: PSBTParser) -> bytearray:
        bchsigner = BitcoinCashSigner(self.xpriv, parser)
        return bchsigner.signed_psbt()