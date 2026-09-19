# src/tests/test_sc08_discard.py
import gc
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

# Adjust imports to your real classes
from seedcash.models.storage import SeedStorage
# from seedcash.models.seed import Seed
# from seedcash.models.wallet import Wallet

class TestSC08Discard:

    def test_discard_clears_storage_refs(self):
        """
        After discard_wallet / discard_seed, storage must not keep
        live seed/wallet/passphrase attributes pointing at secrets.
        """
        storage = SeedStorage()
        # Minimal setup — adapt to your API:
        # storage.set_mnemonic(["abandon"] * 11 + ["about"])
        # storage.create_wallet() or equivalent
        #
        # storage.discard_wallet()  # or controller path

        # Assertions (adapt names):
        # assert storage.wallet is None
        # assert storage.seed is None or storage.seed.mnemonic is None
        # assert not storage.passphrase

        pytest.skip("Wire to your SeedStorage.discard_* API")

    def test_wallet_discard_clears_xpriv_attr(self):
        """Wallet.discard_wallet should drop xpriv attribute or set None."""
        pytest.skip("Wire Wallet instance + discard_wallet()")
        # w = Wallet(...)
        # w.discard_wallet()
        # assert not hasattr(w, "xpriv") or w.xpriv in (None, b"", bytearray())