import logging
import time
from gettext import gettext as _
from seedcash.models.btc_functions import BitcoinFunctions as bf
from seedcash.gui.components import SeedCashIconsConstants
from seedcash.gui.screens import (
    RET_CODE__BACK_BUTTON,
    WarningScreen,
    load_seed_screens,
    SeedCashButtonListWithNav,
)
from seedcash.gui.screens.screen import ButtonOption
from seedcash.models.wallet import Wallet
from seedcash.views.view import (
    View,
    Destination,
    BackStackView,
    MainMenuView,
)

logger = logging.getLogger(__name__)


# Third Possible Load Seed View if the user enters the right mnemonic
class WalletFinalizeView(View):
    CONFIRM = ButtonOption("Confirm")
    PASSPHRASE = ButtonOption("Add Passphrase")

    def __init__(self, wallet: Wallet = None):
        super().__init__()

        # NTBC
        self.wallet = wallet or self.controller.storage._wallet
        self.fingerprint = self.wallet._fingerprint

    def run(self):
        button_data = [
            self.PASSPHRASE,
            self.CONFIRM,
        ]

        selected_menu_num = self.run_screen(
            load_seed_screens.SeedFinalizeScreen,
            fingerprint=self.fingerprint,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.CONFIRM:
            if self.controller.storage.wallet:
                self.controller.storage.discard_after_create_wallet()
                return Destination(WalletOptionsView)

            self.controller.storage.discard_mnemonic()
            return Destination(MainMenuView)
        elif button_data[selected_menu_num] == self.PASSPHRASE:
            return Destination(SeedAddPassphraseView, view_args={"wallet": self.wallet})

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
        wallet: Wallet = None,
    ):
        super().__init__()
        self.initial_keyboard = initial_keyboard
        self.wallet = wallet or self.controller.storage._wallet

    def run(self):
        ret_dict = self.run_screen(
            load_seed_screens.SeedAddPassphraseScreen,
            passphrase=self.controller.storage.passphrase,
            title="Enter Passphrase",
            initial_keyboard=self.initial_keyboard,
        )

        # The new passphrase will be the return value; it might be empty.
        self.controller.storage.set_passphrase(ret_dict["passphrase"])

        if "is_back_button" in ret_dict:
            if len(self.controller.storage.passphrase) > 0:
                return Destination(
                    SeedAddPassphraseExitDialogView, view_args={"wallet": self.wallet}
                )
            else:
                return Destination(BackStackView)

        elif len(self.controller.storage.passphrase) > 0:
            return Destination(
                SeedReviewPassphraseView, view_args={"wallet": self.wallet}
            )
        else:
            return Destination(
                SeedReviewPassphraseExitDialogView, view_args={"wallet": self.wallet}
            )


# Fifth Possible Load Seed View if the user wants to add a passphrase if BACK is pressed
class SeedAddPassphraseExitDialogView(View):
    EDIT = ButtonOption("Edit passphrase")
    DISCARD = ButtonOption("Discard passphrase", button_label_color="red")

    def __init__(self, wallet: Wallet = None):
        super().__init__()

        self.wallet = wallet or self.controller.storage._wallet

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
            return Destination(SeedAddPassphraseView, view_args={"wallet": self.wallet})

        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.storage.set_passphrase("")
            return Destination(
                SeedReviewPassphraseExitDialogView, view_args={"wallet": self.wallet}
            )


# Fifth Possible Load Seed View if the user wants to add a passphrase
class SeedReviewPassphraseView(View):
    """
    Display the completed passphrase back to the user.
    """

    EDIT = ButtonOption("Edit passphrase")
    DONE = ButtonOption("Confirm")

    def __init__(self, wallet: Wallet = None):
        super().__init__()
        self.wallet = wallet or self.controller.storage._wallet

    def run(self):

        button_data = [self.EDIT, self.DONE]

        # Because we have an explicit "Edit" button, we disable "BACK" to keep the
        # routing options sane.
        selected_menu_num = self.run_screen(
            load_seed_screens.SeedReviewPassphraseScreen,
            passphrase=self.controller.storage.passphrase,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(SeedAddPassphraseView, view_args={"wallet": self.wallet})

        elif button_data[selected_menu_num] == self.DONE:
            if self.controller.storage.wallet:
                self.controller.storage.create_wallet()
                self.controller.storage.discard_after_create_wallet()
                self.controller.storage.set_passphrase("")
                return Destination(SeedReviewPassphraseExitDialogView)
            wallet = self.controller.storage.get_seed_wallet()
            self.controller.storage.set_passphrase("")
            return Destination(
                SeedReviewPassphraseExitDialogView,
                view_args={"wallet": wallet},
            )


class SeedReviewPassphraseExitDialogView(View):
    CONFIRM = ButtonOption("Confirm")

    def __init__(self, wallet: Wallet = None):
        super().__init__()

        # NTBC
        self.wallet = wallet or self.controller.storage._wallet
        self.fingerprint = self.wallet._fingerprint

    def run(self):
        button_data = [
            self.CONFIRM,
        ]

        selected_menu_num = self.run_screen(
            load_seed_screens.SeedFinalizeScreen,
            fingerprint=self.fingerprint,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.CONFIRM:
            if self.controller.storage.wallet:
                return Destination(WalletOptionsView)

            self.controller.storage.discard_mnemonic()
            return Destination(MainMenuView)


# Final Possible Load Seed View
class WalletOptionsView(View):
    EXPORT_XPRIV = ButtonOption("Export Xpriv")
    EXPORT_XPUB = ButtonOption("Export Xpub")
    GENERATE_ADDRESS = ButtonOption("Generate Address")
    SIGN_TRANSACTION = ButtonOption("Sign Transaction")
    EXPEL_WALLET = ButtonOption("Expel Wallet")

    def __init__(self):
        super().__init__()

        self.wallet = self.controller.storage._wallet

    def run(self):

        button_data = [
            self.EXPORT_XPRIV,
            self.EXPORT_XPUB,
            self.GENERATE_ADDRESS,
            self.SIGN_TRANSACTION,
            self.EXPEL_WALLET,
        ]

        selected_menu_num = self.run_screen(
            load_seed_screens.SeedOptionsScreen,
            button_data=button_data,
            fingerprint=self.wallet._fingerprint,
        )

        if button_data[selected_menu_num] == self.EXPORT_XPRIV:
            return Destination(
                SeedCashQRView, view_args=dict(address=self.wallet._xpriv)
            )
        elif button_data[selected_menu_num] == self.EXPORT_XPUB:
            return Destination(
                SeedCashQRView, view_args=dict(address=self.wallet._xpub)
            )
        elif button_data[selected_menu_num] == self.GENERATE_ADDRESS:
            return Destination(SeedGenerateAddressView)
        elif button_data[selected_menu_num] == self.SIGN_TRANSACTION:
            return Destination(SeedSignTransactionView)
        elif button_data[selected_menu_num] == self.EXPEL_WALLET:
            return Destination(SeedDiscardView)


class SeedGenerateAddressView(View):
    def __init__(self):
        super().__init__()
        self.xpub = self.controller.storage._wallet._xpub

    def run(self):
        menu = self.run_screen(
            load_seed_screens.SeedGenerateAddressScreen,
        )

        if menu == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        addr_type, addr_index = menu

        if addr_type == "legacy":
            address = bf.xpub_to_legacy_address(self.xpub, addr_index)
            return Destination(SeedCashQRView, view_args=dict(address=address))
        elif addr_type == "cashaddr":
            address = bf.xpub_to_cashaddr_address(self.xpub, addr_index)
            return Destination(SeedCashQRView, view_args=dict(address=address))


class SeedCashQRView(View):
    def __init__(self, address: str = ""):
        super().__init__()
        self.address = address

        # Add delay to allow QR code to be displayed
        time.sleep(0.3)

    def run(self):

        self.selected_menu_num = self.run_screen(
            load_seed_screens.QRCodeScreen,
            qr_data=self.address,
        )

        if self.selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif self.selected_menu_num == "SWITCH":
            return Destination(
                SeedCashAddressView,
                view_args=dict(address=self.address),
                skip_current_view=True,
            )


class SeedCashAddressView(View):
    def __init__(self, address: str = ""):
        super().__init__()
        self.address = address

        # Add delay to allow address to be displayed
        time.sleep(0.3)

    def run(self):

        self.selected_menu_num = self.run_screen(
            load_seed_screens.AddressScreen,
            qr_data=self.address,
        )

        if self.selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif self.selected_menu_num == "SWITCH":
            return Destination(
                SeedCashQRView,
                view_args=dict(address=self.address),
                skip_current_view=True,
            )


class SeedSignTransactionView(View):
    SCAN_TX = ButtonOption("Scan TX", icon_name=SeedCashIconsConstants.SCAN_TX)
    READ_TX = ButtonOption("Read TX", icon_name=SeedCashIconsConstants.ATTACH_FILE)

    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.seed

    def run(self):
        button_data = [self.SCAN_TX, self.READ_TX]
        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            title="Sign Transaction",
            button_data=button_data,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if button_data[selected_menu_num] == self.SCAN_TX:
            return Destination(SeedSignTransactionScanView)
        elif button_data[selected_menu_num] == self.READ_TX:
            return Destination(SeedSignTransactionReadView)


class SeedSignTransactionScanView(View):
    """
    Camera preview View that displays the live camera feed.

    This view simply shows the camera output without any QR code processing.
    """

    instructions_text = _("Transaction Scan")

    def __init__(self):
        super().__init__()

    def run(self):
        from seedcash.gui.screens.scan_screens import ScanScreen

        # Start the live camera preview
        self.run_screen(
            ScanScreen,
            instructions_text=self.instructions_text,
        )

        return Destination(BackStackView)


class SeedSignTransactionReadView(View):
    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.seed

    def run(self):
        button_data = [
            ButtonOption("12:49 04/11/2025", icon_name=SeedCashIconsConstants.VIEW_TX),
            ButtonOption("12:48 04/11/2025", icon_name=SeedCashIconsConstants.VIEW_TX),
        ]

        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            button_data=button_data,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif selected_menu_num in [0, 1]:
            return Destination(LoadingPSBTView)


class LoadingPSBTView(View):
    def __init__(self):
        super().__init__()

        from seedcash.gui.screens.screen import LoadingScreenThread

        self.loading_screen = LoadingScreenThread(text=_("Parsing PSBT..."))
        self.loading_screen.start()
        try:
            # Simulate PSBT parsing delay
            time.sleep(10)  # Replace with actual PSBT parsing logic
        finally:
            self.loading_screen.stop()

    def run(self):
        btn_data = [ButtonOption("Done")]
        self.run_screen(
            SeedCashButtonListWithNav,
            button_data=btn_data,
        )


class SeedDiscardView(View):
    KEEP = ButtonOption("Keep Wallet")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def __init__(self):
        super().__init__()
        self.wallet = self.controller.storage._wallet

    def run(self):
        button_data = [self.KEEP, self.DISCARD]

        fingerprint = self.wallet._fingerprint
        # TRANSLATOR_NOTE: Inserts the wallet fingerprint
        text = _("Wipe wallet {} from the device?").format(fingerprint)
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Discard Wallet?"),
            status_headline=None,
            text=text,
            show_back_button=False,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.KEEP:
            # Use skip_current_view=True to prevent BACK from landing on this warning screen
            return Destination(
                WalletOptionsView,
                skip_current_view=True,
            )
        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.discard_wallet()
            return Destination(MainMenuView, clear_history=True)
