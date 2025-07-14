import logging
import random
from binascii import hexlify
from gettext import gettext as _
from seedcash.models import btc_functions as bf
from seedcash.gui.components import SeedCashIconsConstants
from seedcash.gui.screens import (
    RET_CODE__BACK_BUTTON,
    WarningScreen,
    DireWarningScreen,
    load_seed_screens,
)
from seedcash.gui.screens.screen import ButtonOption
from seedcash.models.seed import Seed
from seedcash.models.settings import Settings, SettingsConstants
from seedcash.views.view import (
    View,
    Destination,
    BackStackView,
    MainMenuView,
)


logger = logging.getLogger(__name__)


"""**************************************************
Seed Cash Updated Code
**************************************************"""


# First Load Seed View
class SeedCashLoadSeedView(View):
    BACK = ButtonOption("BACK", SeedCashIconsConstants.BACK)
    NEXT = ButtonOption("NEXT", SeedCashIconsConstants.NEXT)
    label_text: str = (
        "Enter your mnemonic seed word by word and passphrase.\n Remember that Seedcash only supports 12 seed words."
    )

    def run(self):
        from seedcash.gui.screens.load_seed_screens import SeedCashLoadSeedScreen

        button_data = [self.NEXT, self.BACK]

        selected_menu_num = self.run_screen(
            SeedCashLoadSeedScreen,
        )

        if button_data[selected_menu_num] == self.BACK:
            return Destination(BackStackView)

        if button_data[selected_menu_num] == self.NEXT:
            from seedcash.views.load_seed_views import SeedMnemonicEntryView

            return Destination(SeedMnemonicEntryView)

        return Destination(BackStackView)


# Second Load Seed View for input
class SeedMnemonicEntryView(View):
    def __init__(self, cur_word_index: int = 0, is_calc_final_word: bool = False):
        super().__init__()
        # counter
        self.cur_word_index = cur_word_index
        # getting the index
        self.cur_word = self.controller.storage.get_mnemonic_word(cur_word_index)
        # for the generation of seed
        self.is_calc_final_word = is_calc_final_word

    def run(self):
        ret = self.run_screen(
            load_seed_screens.SeedMnemonicEntryScreen,
            # TRANSLATOR_NOTE: Inserts the word number (e.g. "Seed Word #6")
            title=_("Seed Word #{}").format(
                self.cur_word_index + 1
            ),  # Human-readable 1-indexing!
            initial_letters=list(self.cur_word) if self.cur_word else ["a"],
            wordlist=Seed.get_wordlist(),
        )

        if ret == RET_CODE__BACK_BUTTON:
            if self.cur_word_index > 0:
                return Destination(BackStackView)
            else:
                self.controller.storage.discard_mnemonic()
                return Destination(MainMenuView)

        # ret will be our new mnemonic word
        self.controller.storage.update_mnemonic(ret, self.cur_word_index)

        if (
            self.is_calc_final_word
            and self.cur_word_index == self.controller.storage.mnemonic_length - 2
        ):
            # Time to calculate the last word. User must decide how they want to specify
            # the last bits of entropy for the final word.
            from seedcash.views.generate_seed_view import (
                ToolsCalcFinalWordCoinFlipsView,
            )

            return Destination(ToolsCalcFinalWordCoinFlipsView)

        if (
            self.is_calc_final_word
            and self.cur_word_index == self.controller.storage.mnemonic_length - 1
        ):
            # Time to calculate the last word. User must either select a final word to
            # contribute entropy to the checksum word OR we assume 0 ("abandon").
            from seedcash.views.generate_seed_view import (
                ToolsCalcFinalWordShowFinalWordView,
            )

            return Destination(ToolsCalcFinalWordShowFinalWordView)

        if self.cur_word_index < (self.controller.storage.mnemonic_length - 1):
            return Destination(
                SeedMnemonicEntryView,
                view_args={
                    "cur_word_index": self.cur_word_index + 1,
                    "is_calc_final_word": self.is_calc_final_word,
                },
            )
        else:
            # Display the seed words for confirmation
            from seedcash.gui.screens.load_seed_screens import SeedCashSeedWordsScreen

            confirm = self.run_screen(
                SeedCashSeedWordsScreen,
                seed_words=self.controller.storage._mnemonic,
            )

            if confirm == "CONFIRM":
                # User confirmed the seed words
                try:
                    self.controller.storage.convert_mnemonic_to_seed()

                except Exception as e:
                    logger.error(
                        f"SeedMnemonicEntryView: Error converting pending mnemonic to pending seed: {e}"
                    )
                    return Destination(SeedMnemonicInvalidView)

                return Destination(SeedFinalizeView)


# Third Possible Load Seed View if the user enters the wrong mnemonic
class SeedMnemonicInvalidView(View):
    EDIT = ButtonOption("Review & Edit")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def __init__(self):
        super().__init__()
        self.mnemonic: list[str] = self.controller.storage._mnemonic

    def run(self):
        button_data = [self.EDIT, self.DISCARD]
        selected_menu_num = self.run_screen(
            DireWarningScreen,
            title=_("Invalid Mnemonic!"),
            status_icon_name=SeedCashIconsConstants.ERROR,
            status_headline=None,
            text=_("Checksum failure; not a valid seed phrase."),
            show_back_button=False,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(SeedMnemonicEntryView, view_args={"cur_word_index": 0})

        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.storage.discard_mnemonic()
            return Destination(MainMenuView)


# Third Possible Load Seed View if the user enters the right mnemonic
class SeedFinalizeView(View):
    CONFIRM = ButtonOption("Confirm")
    PASSPHRASE = ButtonOption("Add Passphrase")

    def __init__(self):
        super().__init__()

        # NTBC
        self.seed = self.controller.storage.get_seed()

        passphrase = self.seed.passphrase
        self.seed.set_passphrase("")

        # generate a fingerprint for the seed
        self.seed.generate_seed()

        self.fingerprint = self.seed.get_fingerprint()
        self.seed.set_passphrase(passphrase)
        logger.debug(
            f"SeedFinalizeView: fingerprint={self.fingerprint} (with passphrase set to {passphrase})"
        )

    def run(self):
        button_data = [
            self.CONFIRM,
            self.PASSPHRASE,
        ]

        selected_menu_num = self.run_screen(
            load_seed_screens.SeedFinalizeScreen,
            fingerprint=self.fingerprint,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.CONFIRM:
            return Destination(SeedOptionsView)

        elif button_data[selected_menu_num] == self.PASSPHRASE:
            return Destination(SeedAddPassphraseView)

        elif selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)


# Fourth Possible Load Seed View if the user wants to add a passphrase
class SeedAddPassphraseView(View):
    """
    initial_keyboard: used by the screenshot generator to render each different keyboard layout.
    """

    def __init__(
        self,
        initial_keyboard: str = load_seed_screens.SeedAddPassphraseScreen.KEYBOARD__LOWERCASE_BUTTON_TEXT,
    ):
        super().__init__()
        self.initial_keyboard = initial_keyboard
        self.seed = self.controller.storage.get_seed()

    def run(self):
        ret_dict = self.run_screen(
            load_seed_screens.SeedAddPassphraseScreen,
            passphrase=self.seed.passphrase,
            title="Enter Passphrase",
            initial_keyboard=self.initial_keyboard,
        )

        # The new passphrase will be the return value; it might be empty.
        self.seed.set_passphrase(ret_dict["passphrase"])

        if "is_back_button" in ret_dict:
            if len(self.seed.passphrase) > 0:
                return Destination(SeedAddPassphraseExitDialogView)
            else:
                return Destination(BackStackView)

        elif len(self.seed.passphrase) > 0:
            return Destination(SeedReviewPassphraseView)

        else:
            return Destination(SeedFinalizeView)


# Fifth Possible Load Seed View if the user wants to add a passphrase if BACK is pressed
class SeedAddPassphraseExitDialogView(View):
    EDIT = ButtonOption("Edit passphrase")
    DISCARD = ButtonOption("Discard passphrase", button_label_color="red")

    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.get_seed()

    def run(self):
        button_data = [self.EDIT, self.DISCARD]

        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Discard passphrase?"),
            status_headline=None,
            text=_("Your current passphrase entry will be erased"),
            show_back_button=False,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(SeedAddPassphraseView)

        elif button_data[selected_menu_num] == self.DISCARD:
            self.seed.set_passphrase("")
            return Destination(SeedFinalizeView)


# Fifth Possible Load Seed View if the user wants to add a passphrase
class SeedReviewPassphraseView(View):
    """
    Display the completed passphrase back to the user.
    """

    EDIT = ButtonOption("Edit passphrase")
    DONE = ButtonOption("Done")

    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.get_seed()

    def run(self):
        # Get the before/after fingerprints
        fingerprint_without = self.seed.get_fingerprint()

        passphrase = self.seed.passphrase
        self.seed.set_passphrase(passphrase)
        self.seed.generate_seed()  # Ensure the seed is generated with the passphrase
        fingerprint_with = self.seed.get_fingerprint()

        button_data = [self.EDIT, self.DONE]

        # Because we have an explicit "Edit" button, we disable "BACK" to keep the
        # routing options sane.
        selected_menu_num = self.run_screen(
            load_seed_screens.SeedReviewPassphraseScreen,
            fingerprint_without=fingerprint_without,
            fingerprint_with=fingerprint_with,
            passphrase=self.seed.passphrase,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(SeedAddPassphraseView)

        elif button_data[selected_menu_num] == self.DONE:
            return Destination(SeedOptionsView)


# Final Possible Load Seed View
class SeedOptionsView(View):
    EXPORT_XPRIV = ButtonOption("Export Xpriv")
    EXPORT_XPUB = ButtonOption("Export Xpub")
    GENERATE_ADDRESS = ButtonOption("Generate Address")
    SIGN_TRANSACTION = ButtonOption("Sign Transaction")
    EXPEL_SEED = ButtonOption("Expel Seed")

    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.seed

    def run(self):

        button_data = [
            self.EXPORT_XPRIV,
            self.EXPORT_XPUB,
            self.GENERATE_ADDRESS,
            self.SIGN_TRANSACTION,
            self.EXPEL_SEED,
        ]

        selected_menu_num = self.run_screen(
            load_seed_screens.SeedOptionsScreen,
            button_data=button_data,
            fingerprint=self.seed.get_fingerprint(),
        )

        if button_data[selected_menu_num] == self.EXPORT_XPRIV:
            return Destination(SeedExportXprivView)
        elif button_data[selected_menu_num] == self.EXPORT_XPUB:
            return Destination(SeedExportXpubView)
        elif button_data[selected_menu_num] == self.GENERATE_ADDRESS:
            return Destination(SeedGenerateAddressView)
        elif button_data[selected_menu_num] == self.SIGN_TRANSACTION:
            return Destination(SeedSignTransactionView)
        elif button_data[selected_menu_num] == self.EXPEL_SEED:
            return Destination(SeedDiscardView)


class SeedExportXprivView(View):
    def __init__(self):
        super().__init__()
        self.xpriv = self.controller.storage.seed.xpriv

    def run(self):
        from seedcash.gui.screens.load_seed_screens import (
            QRCodeScreen,
        )

        selected_menu_num = self.run_screen(QRCodeScreen, qr_data=self.xpriv)

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)


class SeedExportXpubView(View):
    def __init__(self):
        super().__init__()
        self.xpub = self.controller.storage.seed.xpub

    def run(self):
        from seedcash.gui.screens.load_seed_screens import (
            QRCodeScreen,
        )

        selected_menu_num = self.run_screen(QRCodeScreen, qr_data=self.xpub)

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)


class SeedGenerateAddressView(View):
    def __init__(self):
        super().__init__()
        self.xpub = self.controller.storage.seed.xpub

    def run(self):
        menu = self.run_screen(
            load_seed_screens.SeedGenerateAddressScreen,
        )

        if menu == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        addr_type, addr_index = menu

        if addr_type == "legacy":
            address = bf.xpub_to_legacy_address(self.xpub, addr_index)
            return Destination(SeedGenerateLegacyView, view_args=dict(address=address))
        elif addr_type == "cashaddr":
            address = bf.xpub_to_cashaddr_address(self.xpub, addr_index)
            return Destination(
                SeedGenerateCashAddrView, view_args=dict(address=address)
            )


class SeedGenerateCashAddrView(View):
    def __init__(self, address: str = ""):
        super().__init__()
        self.address = address

    def run(self):
        from seedcash.gui.screens.load_seed_screens import (
            QRCodeScreen,
        )

        selected_menu_num = self.run_screen(QRCodeScreen, qr_data=self.address)

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)


class SeedGenerateLegacyView(View):
    def __init__(self, address: str = ""):
        super().__init__()
        self.address = address

    def run(self):
        from seedcash.gui.screens.load_seed_screens import (
            QRCodeScreen,
        )

        selected_menu_num = self.run_screen(QRCodeScreen, qr_data=self.address)

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)


class SeedSignTransactionView(View):
    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.seed

    def run(self):
        # Implement the logic for signing a transaction
        pass


class SeedDiscardView(View):
    KEEP = ButtonOption("Keep Seed")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.get_seed()

    def run(self):
        button_data = [self.KEEP, self.DISCARD]

        fingerprint = self.seed.get_fingerprint()
        # TRANSLATOR_NOTE: Inserts the seed fingerprint
        text = _("Wipe seed {} from the device?").format(fingerprint)
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Discard Seed?"),
            status_headline=None,
            text=text,
            show_back_button=False,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.KEEP:
            # Use skip_current_view=True to prevent BACK from landing on this warning screen
            return Destination(
                SeedOptionsView,
                skip_current_view=True,
            )
        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.discard_seed()
            return Destination(MainMenuView, clear_history=True)
