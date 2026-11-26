"""Focused tests for current SeedCash APIs; synthetic data only."""
from base58 import b58decode
from base58 import b58encode
from seedcash.models.bip44 import Bip44
from types import SimpleNamespace
from unittest.mock import Mock
import secrets
import pytest
from seedcash.models.seed import Seed
from seedcash.models.seed import InvalidSeedException
from seedcash.models.settings import Settings
from seedcash.models.storage import SeedStorage
from seedcash.views.view import View
from seedcash.views.generate_seed_views import ToolsCalcFinalWordCoinFlipsView
from seedcash.models.bip39 import Bip39
from seedcash.models.wallet import Wallet
from seedcash.views.view import Destination
from seedcash.views.wallet_views import SeedReviewPassphraseExitDialogView
from seedcash.views.wallet_views import WalletOptionsView

class TestBip44:

    @staticmethod
    def test_xpub_decode_rejects_invalid_checksum():
        xpub = Bip44.xpub_encode(b'\x00', b'\x00' * 4, b'\x00' * 4, b'\x11' * 32, b'\x02' + b'"' * 32)
        raw_xpub = bytearray(b58decode(xpub))
        raw_xpub[20] ^= 1
        try:
            Bip44.xpub_decode(b58encode(raw_xpub))
        except ValueError as error:
            assert str(error) == 'invalid xpub checksum'
        else:
            raise AssertionError('corrupted xpub was accepted')

class TestGenerationWorkflow:

    @staticmethod
    @pytest.fixture
    def storage(monkeypatch):
        monkeypatch.setattr(Settings.get_instance(), 'get_value', lambda key: 'BIP39')
        return SeedStorage()

    @staticmethod
    @pytest.mark.parametrize('count', [12, 15, 18, 21, 24])
    def test_final_word_confirm_derives_and_clears_fields(storage, count):
        storage.set_mnemonic(['abandon'] * (count - 1) + [None])
        coin_flips = '1' * (11 - count // 3)
        storage.calculate_final_word(coin_flips)
        (bits, checksum) = storage.calculate_last_word_fields
        assert bits == coin_flips
        final_index = storage.get_wordlist.index(storage.mnemonic[-1])
        assert format(final_index, '011b') == bits + checksum
        Seed(storage.mnemonic)
        expected = list(storage.mnemonic)
        storage.convert_mnemonic_to_seed()
        assert storage.seed.mnemonic == expected
        with pytest.raises(InvalidSeedException):
            _ = storage.calculate_last_word_fields
        storage.create_wallet()
        key = storage.wallet.xpriv
        storage.discard_wallet()
        assert not any(key)

    @staticmethod
    def test_coin_flips_not_in_destination_arguments(storage, monkeypatch):
        from seedcash.gui.screens.generate_seed_screens import ToolsCoinFlipEntryScreen
        storage.set_mnemonic(['abandon'] * 11 + [None])
        monkeypatch.setattr(ToolsCoinFlipEntryScreen, 'display', lambda self: '1010101')
        monkeypatch.setattr(ToolsCoinFlipEntryScreen, '__post_init__', lambda self: None)
        view = ToolsCalcFinalWordCoinFlipsView.__new__(ToolsCalcFinalWordCoinFlipsView)
        view.controller = SimpleNamespace(storage=storage)
        destination = view.run()
        assert not destination.view_args
        assert '1010101' not in repr(destination)

    @staticmethod
    def test_replacement_wipes_old_key_after_success():
        owner = Seed(['abandon'] * 11 + ['about'])
        owner.generate_wallet()
        old = owner.wallet
        key = old.xpriv
        owner.set_passphrase('synthetic-passphrase')
        owner.generate_wallet()
        assert owner.wallet is not old
        assert old.xpriv is None
        assert key == bytearray(len(key))

    @staticmethod
    def test_passphrase_length_limit_counts_spaces():
        seed = Seed(['abandon'] * 11 + ['about'])
        seed.set_passphrase('x' * 127 + ' ')
        assert len(seed.passphrase) == 128
        with pytest.raises(InvalidSeedException, match='at most 128 characters'):
            seed.set_passphrase('x' * 128 + ' ')

    @staticmethod
    @pytest.mark.parametrize('generated', [False, True])
    @pytest.mark.parametrize('passphrase', ['', 'synthetic-passphrase'])
    def test_passphrase_confirmation_finishes_without_back_route(storage, monkeypatch, generated, passphrase):
        from seedcash.views.wallet_views import (
            WalletFinalizeView, SeedAddPassphraseView, SeedReviewPassphraseView,
            SeedReviewPassphraseExitDialogView,
        )
        from seedcash.views.view import MainMenuView
        from seedcash.views.wallet_views import SeedFinalizeScreen
        from seedcash.gui.screens.load_seed_screens import SeedReviewPassphraseScreen
        storage._is_generate = generated
        words = ['abandon'] * 11 + ['about']
        storage.set_mnemonic(list(words))
        storage.convert_mnemonic_to_seed()
        storage.create_wallet()
        original = storage.wallet
        original_key = original.xpriv
        controller = SimpleNamespace(storage=storage)
        monkeypatch.setattr(View, '__init__', lambda self: setattr(self, 'controller', controller))

        finalize = WalletFinalizeView()
        finalize.run_screen = Mock(return_value=0)  # Add Passphrase.
        assert finalize.run().View_cls is SeedAddPassphraseView
        assert finalize.run_screen.call_args.args[0] is SeedFinalizeScreen
        assert not SeedFinalizeScreen.is_top_nav

        entry = SeedAddPassphraseView()
        entry.run_screen = Mock(return_value={'passphrase': passphrase})
        destination = entry.run()
        if passphrase:
            assert destination.View_cls is SeedReviewPassphraseView
            review = SeedReviewPassphraseView()
            review.run_screen = Mock(return_value=1)  # Confirm, not Edit.
            destination = review.run()
            assert review.run_screen.call_args.args[0] is SeedReviewPassphraseScreen
            assert not SeedReviewPassphraseScreen.is_top_nav
            assert storage.wallet is not original
            assert not any(original_key)
        else:
            assert storage.wallet is original
        assert destination.View_cls is SeedReviewPassphraseExitDialogView

        expected = Seed(words)
        expected.set_passphrase(passphrase)
        expected.generate_wallet()
        assert storage.wallet.xpub == expected.wallet.xpub
        confirmed_key = storage.wallet.xpriv
        finish = SeedReviewPassphraseExitDialogView()
        finish.run_screen = Mock(return_value=0)
        destination = finish.run()
        assert finish.run_screen.call_args.args[0] is SeedFinalizeScreen
        assert not SeedFinalizeScreen.is_top_nav
        assert [button.button_label for button in finish.run_screen.call_args.kwargs['button_data']] == ['Confirm']
        if generated:
            assert destination.View_cls is MainMenuView
            assert storage._seed is None
            assert not any(confirmed_key)
        else:
            assert destination.View_cls is WalletOptionsView
            assert destination.clear_history
            assert storage.wallet.xpub == expected.wallet.xpub

secret_lifecycle_WORDS = ['abandon'] * 11 + ['about']

def secret_lifecycle_create_seed_wallet(storage):
    storage.create_wallet()
    return storage.wallet

class TestSecretLifecycle:
    @staticmethod
    def test_bip39_nfkd_and_known_answer():
        expected = 'c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04'
        assert Bip39.generate_hexa_seed(secret_lifecycle_WORDS, 'TREZOR') == expected
        assert Bip39.generate_hexa_seed(secret_lifecycle_WORDS, 'é') == Bip39.generate_hexa_seed(secret_lifecycle_WORDS, 'é')

    @staticmethod
    def test_generated_wallet_assignment_and_passphrase_owner():
        storage = SeedStorage()
        storage._is_generate = False
        storage.set_mnemonic(list(secret_lifecycle_WORDS))
        storage.convert_mnemonic_to_seed()
        storage.set_passphrase('secret-passphrase')
        wallet = secret_lifecycle_create_seed_wallet(storage)
        assert storage.wallet is wallet
        assert storage.seed.wallet is wallet
        assert storage.seed.passphrase == 'secret-passphrase'
        assert storage.passphrase == 'secret-passphrase'
        view = SeedReviewPassphraseExitDialogView.__new__(SeedReviewPassphraseExitDialogView)
        view.controller = SimpleNamespace(storage=storage)
        view.fingerprint = wallet.fingerprint
        view.run_screen = Mock(return_value=0)
        assert view.run().View_cls is WalletOptionsView
        assert storage.seed is not None
        assert storage.wallet is wallet

    @staticmethod
    def test_discard_clears_shared_mnemonic_and_private_buffer():
        storage = SeedStorage()
        storage._is_generate = False
        source = list(secret_lifecycle_WORDS)
        storage.set_mnemonic(source)
        storage.convert_mnemonic_to_seed()
        assert source == [None] * 12
        seed_words = storage.seed.mnemonic
        secret_lifecycle_create_seed_wallet(storage)
        storage.set_passphrase('sensitive')
        storage.discard_wallet()
        assert seed_words == [None] * 12
        assert storage._seed is None
        assert storage._mnemonic == [None] * 12
        storage.discard_seed()
        wallet = Wallet.__new__(Wallet)
        secret = bytearray(b'secret')
        wallet._xpriv = secret
        wallet.discard_wallet()
        assert secret == bytearray(6)

    @staticmethod
    def test_secret_exceptions_and_logs_are_redacted(caplog):
        secret = 'this-word-is-sensitive'
        with pytest.raises(InvalidSeedException) as caught:
            Seed([secret] * 12)
        assert secret not in str(caught.value)
        storage = SeedStorage()
        storage._is_generate = False
        with caplog.at_level('INFO'):
            storage.set_mnemonic_length(12)
        assert secret not in caplog.text

    @staticmethod
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

    @staticmethod
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
                view.run_screen(Screen, mnemonic=secret_lifecycle_WORDS)
        else:
            assert view.run_screen(Screen, mnemonic=secret_lifecycle_WORDS) == 7
        assert view.screen is None
        assert view.controller.screensaver.last_screen is None

    @staticmethod
    def test_seed_derivation_failure_preserves_owner_and_previous_wallet(monkeypatch):
        seed = Seed(secret_lifecycle_WORDS)
        seed.generate_wallet()
        original = seed.wallet
        original_buffer = original.xpriv
        seed.set_passphrase('secret')
        monkeypatch.setattr(Bip39, 'bip39_protocol', Mock(side_effect=ValueError('failed')))
        with pytest.raises(ValueError):
            seed.generate_wallet()
        assert seed.passphrase == 'secret'
        assert seed.wallet is original
        assert any(original_buffer)

    @staticmethod
    def test_controller_discard_releases_history_psbt_and_snapshot():
        from seedcash.controller import Controller
        controller = Controller.__new__(Controller)
        controller._storage = SeedStorage()
        controller._storage._is_generate = False
        controller.back_stack = [Destination(View, {'mnemonic': secret_lifecycle_WORDS})]
        controller.screensaver = SimpleNamespace(last_screen='secret-pixels')
        raw = bytearray(b'sensitive-transaction')
        controller.psbt_bytes = raw
        controller.psbt_parser = object()
        controller.token_review = object()
        controller.token_review_parser = object()
        controller.token_review_acknowledged = {0}
        controller.discard_wallet()
        assert not controller.back_stack
        assert controller.screensaver.last_screen is None
        assert raw == bytearray(len(raw))
        assert controller.psbt_parser is controller.token_review is controller.token_review_parser is None
        assert not controller.token_review_acknowledged

    @staticmethod
    @pytest.mark.parametrize('generated', [False, True])
    def test_empty_passphrase_and_cancel_discard_keep_seed(generated):
        from seedcash.views.wallet_views import SeedAddPassphraseView, SeedAddPassphraseExitDialogView
        from seedcash.views.view import BackStackView
        storage = SeedStorage()
        storage._is_generate = False
        words = Bip39.mnemonic_from_bytes(secrets.token_bytes(16)) if generated else list(secret_lifecycle_WORDS)
        expected_words = list(words)
        storage.set_mnemonic(words)
        storage.convert_mnemonic_to_seed()
        wallet = secret_lifecycle_create_seed_wallet(storage)
        controller = SimpleNamespace(storage=storage)
        entry = SeedAddPassphraseView.__new__(SeedAddPassphraseView)
        (entry.controller, entry.wallet, entry.initial_keyboard) = (controller, wallet, '')
        entry.run_screen = Mock(return_value={'passphrase': ''})
        assert entry.run().View_cls is SeedReviewPassphraseExitDialogView
        entry.run_screen = Mock(return_value={'passphrase': '', 'is_back_button': True})
        assert entry.run().View_cls is BackStackView
        entry.run_screen = Mock(return_value={'passphrase': 'discard-me', 'is_back_button': True})
        assert entry.run().View_cls is SeedAddPassphraseExitDialogView
        dialog = SeedAddPassphraseExitDialogView.__new__(SeedAddPassphraseExitDialogView)
        (dialog.controller, dialog.wallet) = (controller, wallet)
        dialog.run_screen = Mock(return_value=1)
        assert dialog.run().View_cls is SeedReviewPassphraseExitDialogView
        assert storage.passphrase == ''
        assert storage.wallet is wallet
        assert storage.seed.mnemonic == expected_words

    @staticmethod
    def test_exception_handler_displays_unexpected_error_diagnostics():
        from seedcash.controller import Controller
        from seedcash.views.view import UnhandledExceptionView, MainMenuView
        controller = Controller.__new__(Controller)
        # Unexpected failures intentionally display diagnostics; expected seed
        # validation failures use their dedicated error views instead.
        message = 'Display initialization failed'
        try:
            raise RuntimeError(message)
        except RuntimeError as error:
            destination = controller.handle_exception(error)

        assert destination.View_cls is UnhandledExceptionView
        assert destination.clear_history
        error_type, location, error_message = destination.view_args['error']
        assert error_type == 'RuntimeError'
        assert 'test_wallet_workflow.py' in location
        assert error_message.strip() == message

        view = UnhandledExceptionView.__new__(UnhandledExceptionView)
        view.error = destination.view_args['error']
        view.run_screen = Mock(return_value=0)
        next_destination = view.run()
        screen_args = view.run_screen.call_args.kwargs
        assert screen_args['status_headline'] == 'RuntimeError'
        assert location in screen_args['text']
        assert message in screen_args['text']
        assert next_destination.View_cls is MainMenuView
        assert next_destination.clear_history

class TestSc08Discard:

    @staticmethod
    def test_discard_clears_storage_refs(monkeypatch):
        monkeypatch.setattr(Settings.get_instance(), 'get_value', lambda key: 'BIP39')
        storage = SeedStorage()
        storage.set_mnemonic(['abandon'] * 11 + ['about'])
        storage.convert_mnemonic_to_seed()
        storage.set_passphrase('synthetic')
        storage.create_wallet()
        seed = storage.seed
        (words, key) = (seed.mnemonic, storage.wallet.xpriv)
        storage.discard_wallet()
        assert storage._seed is None
        assert words == [None] * 12
        assert not seed.passphrase
        assert key == bytearray(len(key))
        storage.discard_wallet()

    @staticmethod
    def test_wallet_discard_clears_xpriv_attr():
        wallet = Wallet.__new__(Wallet)
        secret = bytearray(b'synthetic-key')
        wallet._xpriv = secret
        wallet.discard_wallet()
        assert wallet.xpriv is None
        assert secret == bytearray(len(secret))
