"""Secret lifetime and generated-wallet regression tests (no display/hardware required)."""
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seedcash.models.bip39 import Bip39
from seedcash.models.seed import Seed, InvalidSeedException
from seedcash.models.storage import SeedStorage
from seedcash.models.wallet import Wallet
from seedcash.views.view import Destination, View
from seedcash.gui.screens.slip_screens import SlipEntryScreen
from seedcash.views.wallet_views import SeedReviewPassphraseExitDialogView, WalletOptionsView

WORDS = ['abandon'] * 11 + ['about']


def test_bip39_nfkd_and_known_answer():
    expected = ('c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e5349553'
                '1f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04')
    assert Bip39.generate_hexa_seed(WORDS, 'TREZOR') == expected
    assert Bip39.generate_hexa_seed(WORDS, 'é') == Bip39.generate_hexa_seed(WORDS, 'e\u0301')


def test_generated_wallet_assignment_and_passphrase_owner():
    storage = SeedStorage()
    storage.set_mnemonic(list(WORDS))
    storage.convert_mnemonic_to_seed()
    storage.set_passphrase('secret-passphrase')
    wallet = storage.get_seed_wallet()
    assert storage.wallet is wallet
    assert storage.seed.wallet is wallet
    assert storage.seed.passphrase is None
    # Storage owns the sole retained passphrase, required by explicit backup screens.
    assert storage.passphrase == 'secret-passphrase'
    view = SeedReviewPassphraseExitDialogView.__new__(SeedReviewPassphraseExitDialogView)
    view.controller = SimpleNamespace(storage=storage)
    view.fingerprint = wallet._fingerprint
    view.run_screen = Mock(return_value=0)
    assert view.run().View_cls is WalletOptionsView
    assert storage.seed is not None
    assert storage.wallet is wallet


def test_discard_clears_shared_mnemonic_and_private_buffer():
    storage = SeedStorage()
    source = list(WORDS)
    storage.set_mnemonic(source)
    storage.convert_mnemonic_to_seed()
    assert source == [None] * 12
    seed_words = storage.seed.mnemonic
    storage.get_seed_wallet()
    storage.set_passphrase('sensitive')
    storage.discard_wallet()
    assert seed_words == [None] * 12
    assert storage.wallet is storage.seed is None
    assert not storage.passphrase
    storage.discard_seed()  # Repeat discard is safe.
    wallet = Wallet.__new__(Wallet)
    secret = bytearray(b'secret')
    wallet.xpriv = secret
    wallet.discard_wallet()
    assert secret == bytearray(6)


def test_secret_exceptions_and_logs_are_redacted(caplog):
    secret = 'this-word-is-sensitive'
    with pytest.raises(InvalidSeedException) as caught:
        Seed([secret] * 12)
    assert secret not in str(caught.value)
    storage = SeedStorage()
    bits = '10' * 64
    with caplog.at_level('INFO'):
        storage.set_scheme_params(bits)
    assert bits not in caplog.text


def test_destination_repr_and_executed_view_release():
    class Dummy:
        has_redirect = False
        def __init__(self, secret):
            self.secret = secret
        def run(self):
            return 123
    destination = Destination(Dummy, {'secret': 'known-mnemonic-secret'})
    assert 'known-mnemonic-secret' not in repr(destination)
    assert destination.run() == 123
    assert destination.view is None


@pytest.mark.parametrize('raises', [False, True])
def test_screen_released_on_return_and_exception(raises):
    class Screen:
        def __init__(self, **kwargs):
            self.secret = kwargs
        def display(self):
            if raises:
                raise ValueError('screen failed')
            return 7
    view = View.__new__(View)
    view.controller = SimpleNamespace(screensaver=SimpleNamespace(last_screen='secret-pixels'))
    if raises:
        with pytest.raises(ValueError):
            view.run_screen(Screen, mnemonic=WORDS)
    else:
        assert view.run_screen(Screen, mnemonic=WORDS) == 7
    assert view.screen is None
    assert view.controller.screensaver.last_screen is None


def test_dice_does_not_replace_manual_entropy(monkeypatch):
    generator = Mock(return_value='1' * 128)
    monkeypatch.setattr('seedcash.gui.screens.slip_screens.sp.get_random_bits_for_slip', generator)
    screen = SlipEntryScreen.__new__(SlipEntryScreen)
    screen.num_words = 20
    screen.current_bits = '00101'
    screen.cursor_position = 5
    screen._fill_random_entropy()
    assert screen.current_bits == '00101'
    generator.assert_not_called()
    screen.current_bits = ''
    screen._fill_random_entropy()
    assert screen.current_bits == '1' * 128
    assert screen.cursor_position == 128


def test_generated_seed_back_and_passphrase_retry_preserve_wallet():
    from seedcash.views.wallet_views import WalletFinalizeView, SeedAddPassphraseView, SeedReviewPassphraseView
    from seedcash.views.view import BackStackView
    from seedcash.gui.screens import RET_CODE__BACK_BUTTON
    storage = SeedStorage()
    storage.set_mnemonic(list(WORDS))
    storage.convert_mnemonic_to_seed()
    wallet = storage.get_seed_wallet()
    view = WalletFinalizeView.__new__(WalletFinalizeView)
    view.controller = SimpleNamespace(storage=storage)
    view.wallet = wallet
    view.fingerprint = wallet._fingerprint
    view.run_screen = Mock(return_value=RET_CODE__BACK_BUTTON)
    assert view.run().View_cls is BackStackView
    assert storage.wallet is wallet
    entry = SeedAddPassphraseView.__new__(SeedAddPassphraseView)
    entry.controller = view.controller
    entry.wallet = wallet
    entry.initial_keyboard = ''
    entry.run_screen = Mock(return_value={'passphrase': 'retry-passphrase'})
    assert entry.run().View_cls is SeedReviewPassphraseView
    assert storage.seed is not None
    assert storage.wallet is wallet


def test_seed_derivation_failure_clears_duplicate_passphrase(monkeypatch):
    seed = Seed(WORDS)
    seed.set_passphrase('secret')
    monkeypatch.setattr(Bip39, 'bip39_protocol', Mock(side_effect=ValueError('failed')))
    with pytest.raises(ValueError):
        seed.generate_wallet()
    assert seed.passphrase is None


def test_controller_discard_releases_history_psbt_and_snapshot():
    from seedcash.controller import Controller
    controller = Controller.__new__(Controller)
    controller._storage = SeedStorage()
    controller.back_stack = [Destination(View, {'mnemonic': WORDS})]
    controller.screensaver = SimpleNamespace(last_screen='secret-pixels')
    raw = bytearray(b'sensitive-transaction')
    controller.psbt_bytes = raw
    controller.psbt_parser = object()
    controller.token_review = object()
    controller.token_review_parser = object()
    controller.token_review_acknowledged = True
    controller.discard_wallet()
    assert not controller.back_stack
    assert controller.screensaver.last_screen is None
    assert raw == bytearray(len(raw))
    assert controller.psbt_parser is controller.token_review is controller.token_review_parser is None
    assert not controller.token_review_acknowledged


@pytest.mark.parametrize('generated', [False, True])
def test_empty_passphrase_and_cancel_discard_keep_seed(generated):
    from seedcash.views.wallet_views import SeedAddPassphraseView, SeedAddPassphraseExitDialogView
    from seedcash.views.view import BackStackView
    storage = SeedStorage()
    words = Bip39.generate_random_seed(12) if generated else list(WORDS)
    expected_words = list(words)
    storage.set_mnemonic(words)
    storage.convert_mnemonic_to_seed()
    wallet = storage.get_seed_wallet()
    controller = SimpleNamespace(storage=storage)
    entry = SeedAddPassphraseView.__new__(SeedAddPassphraseView)
    entry.controller, entry.wallet, entry.initial_keyboard = controller, wallet, ''
    entry.run_screen = Mock(return_value={'passphrase': ''})
    assert entry.run().View_cls is SeedReviewPassphraseExitDialogView
    entry.run_screen = Mock(return_value={'passphrase': '', 'is_back_button': True})
    assert entry.run().View_cls is BackStackView
    entry.run_screen = Mock(return_value={'passphrase': 'discard-me', 'is_back_button': True})
    assert entry.run().View_cls is SeedAddPassphraseExitDialogView
    dialog = SeedAddPassphraseExitDialogView.__new__(SeedAddPassphraseExitDialogView)
    dialog.controller, dialog.wallet = controller, wallet
    dialog.run_screen = Mock(return_value=1)
    assert dialog.run().View_cls is SeedReviewPassphraseExitDialogView
    assert storage.passphrase == ''
    assert storage.wallet is wallet
    assert storage.seed.mnemonic == expected_words


def test_exception_handler_never_displays_or_logs_secret(caplog):
    from seedcash.controller import Controller
    controller = Controller.__new__(Controller)
    secret = 'known-private-key-material'
    with caplog.at_level('ERROR'):
        destination = controller.handle_exception(ValueError(secret))
    assert secret not in caplog.text
    assert secret not in str(destination.view_args)


def test_compact_seed_qr_exception_log_is_redacted(monkeypatch, caplog):
    from seedcash.models.decode_qr import SeedQrDecoder, DecodeQRStatus
    secret = 'qr-secret-mnemonic-material'
    monkeypatch.setattr(Bip39, 'mnemonic_from_bytes', Mock(side_effect=ValueError(secret)))
    decoder = SeedQrDecoder()
    with caplog.at_level('WARNING'):
        assert decoder.add(b'\x01' * 16) == DecodeQRStatus.INVALID
    assert secret not in caplog.text
    assert not decoder.complete
    assert decoder.get_seed_phrase() == []
