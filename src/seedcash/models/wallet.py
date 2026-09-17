from seedcash.models.bip44 import Bip44
from seedcash.models.psbt_parser import PSBTParser
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
        # convert xpub bytearray to string
        return self.xpub.decode('utf-8')

    @property
    def _fingerprint(self) -> str:
        return self.fingerprint

    def discard_wallet(self):
        self.xpriv = None
        self.xpub = ""
        self.fingerprint = ""
    
    def sign_psbt(self, parser: PSBTParser) -> bytearray:
        bchsigner = BitcoinCashSigner(self._xpriv, parser)
        return bchsigner.signed_psbt()