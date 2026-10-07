import logging
import time
from gettext import gettext as _
from seedcash.gui.screens import screen
from seedcash.models.bip44 import Bip44
from seedcash.gui.screens import (
    RET_CODE__BACK_BUTTON,
    WarningScreen,
    load_seed_screens
)
from seedcash.gui.screens.screen import ButtonOption
from seedcash.models.seed import Seed
from seedcash.models.settings_definition import SettingsConstants
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

    def __init__(self):
        super().__init__()

        # NTBC
        
        self.wallet = self.controller.storage.wallet
        self.fingerprint = self.wallet.fingerprint

    def run(self):
        button_data = [
            self.PASSPHRASE,
            self.CONFIRM
        ]

        selected_menu_num = self.run_screen(
            load_seed_screens.SeedFinalizeScreen,
            fingerprint=self.fingerprint,
            button_data=button_data,
            selected_button=1
        )
        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        
        if button_data[selected_menu_num] == self.CONFIRM:
            if self.controller.storage.wallet and not self.controller.storage.is_generate:
                return Destination(WalletOptionsView, clear_history=True)

            self.controller.storage.discard_wallet()
            return Destination(MainMenuView)
        elif button_data[selected_menu_num] == self.PASSPHRASE:
            return Destination(SeedAddPassphraseView)

# Fourth Possible Load Seed View if the user wants to add a passphrase
class SeedAddPassphraseView(View):
    """
    initial_keyboard: used by the screenshot generator to render each different keyboard layout.
    """

    def __init__(
        self,
        initial_keyboard: str = load_seed_screens.SeedAddPassphraseScreen.KEYBOARD__LOWERCASE_BUTTON_TEXT
    ):
        super().__init__()
        self.initial_keyboard = initial_keyboard
        self.wallet = self.controller.storage.wallet

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
                return Destination(SeedAddPassphraseExitDialogView)
            else:
                return Destination(BackStackView)

        elif len(self.controller.storage.passphrase) > 0:
            return Destination(SeedReviewPassphraseView)
        else:
            return Destination(SeedReviewPassphraseExitDialogView)

# Fifth Possible Load Seed View if the user wants to add a passphrase if BACK is pressed
class SeedAddPassphraseExitDialogView(View):
    EDIT = ButtonOption("Edit passphrase")
    DISCARD = ButtonOption("Discard passphrase", button_label_color="red")

    def __init__(self):
        super().__init__()

        self.wallet = self.controller.storage.wallet

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
            self.controller.storage.set_passphrase("")
            return Destination(SeedReviewPassphraseExitDialogView)

# Fifth Possible Load Seed View if the user wants to add a passphrase
class SeedReviewPassphraseView(View):
    """
    Display the completed passphrase back to the user.
    """

    EDIT = ButtonOption("Edit passphrase")
    CONFIRM = ButtonOption("Confirm")

    def __init__(self):
        super().__init__()
        self.wallet = self.controller.storage.wallet

    def run(self):

        button_data = [self.EDIT, self.CONFIRM]

        # Because we have an explicit "Edit" button, we disable "BACK" to keep the
        # routing options sane.
        selected_menu_num = self.run_screen(
            load_seed_screens.SeedReviewPassphraseScreen,
            passphrase=self.controller.storage.passphrase,
            button_data=button_data,
            selected_button=1,  # Default to "Confirm"
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(SeedAddPassphraseView)

        elif button_data[selected_menu_num] == self.CONFIRM:
            self.controller.storage.create_wallet()
            return Destination(SeedReviewPassphraseExitDialogView)
            

class SeedReviewPassphraseExitDialogView(View):
    CONFIRM = ButtonOption("Confirm")

    def __init__(self):
        super().__init__()

        # NTBC
        self.wallet = self.controller.storage.wallet
        self.fingerprint = self.wallet.fingerprint

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
            if self.controller.storage.wallet and not self.controller.storage.is_generate:
                return Destination(WalletOptionsView, clear_history=True)

            self.controller.storage.discard_wallet()
            return Destination(MainMenuView)

# Final Possible Load Seed View
class WalletOptionsView(View):
    VIEW_SEED = ButtonOption("View Seed")
    EXPORT_XPUB = ButtonOption("Export Xpub")
    GENERATE_ADDRESS = ButtonOption("Generate Address")
    SIGN_TRANSACTION = ButtonOption("Sign Transaction")
    EXPEL_WALLET = ButtonOption("Expel Wallet")

    def __init__(self):
        super().__init__()

        self.wallet = self.controller.storage.wallet

    def run(self):

        button_data = [
            self.VIEW_SEED,
            self.EXPORT_XPUB,
            self.GENERATE_ADDRESS,
            self.SIGN_TRANSACTION,
            self.EXPEL_WALLET,
        ]

        selected_menu_num = self.run_screen(
            load_seed_screens.SeedOptionsScreen,
            button_data=button_data,
            fingerprint=self.wallet.fingerprint,
        )
        

        if button_data[selected_menu_num] == self.VIEW_SEED:
            return Destination(ViewSeedView)

        elif button_data[selected_menu_num] == self.EXPORT_XPUB:
            return Destination(
                SeedCashQRView, view_args=dict(address=self.wallet.xpub)
            )
        elif button_data[selected_menu_num] == self.GENERATE_ADDRESS:
            return Destination(SeedGenerateAddressView)
        elif button_data[selected_menu_num] == self.SIGN_TRANSACTION:
            from seedcash.views.scan_view import ScanPSBTView
            return Destination(ScanPSBTView)
        elif button_data[selected_menu_num] == self.EXPEL_WALLET:
            return Destination(SeedDiscardView)

class ViewSeedView(View):
    
    def __init__(self, index: int = 0):
        super().__init__()
        self.is_slip = (SettingsConstants.SEED_PROTOCOL__SLIP39 == 
                        self.controller.settings.get_instance().get_value(
                            SettingsConstants.SETTING__SEED_PROTOCOL))
        self.index = index
    def run(self):
        
        if self.index == 0:
            result = self.run_screen(
                screen.WarningScreen,
                show_back_button=True,
                title="",
                text=_("Exposing your Seed gives full control of your funds"))
            
            if result == RET_CODE__BACK_BUTTON:
                return Destination(BackStackView)
        
        if self.controller.storage.passphrase:
            result = self.run_screen(
                load_seed_screens.SeedReviewPassphraseScreen,
                passphrase=self.controller.storage.passphrase,
                button_data=[ButtonOption("Back"), ButtonOption("Confirm")],
                selected_button=1,
            )

            if result == 0:
                return Destination(ViewSeedView, view_args={"index": 0}, skip_current_view=True)


        if self.is_slip:
            from seedcash.views.load_slip_views import Slip39SeedViewView
            return Destination(Slip39SeedViewView, skip_current_view=True)
        else:
            from seedcash.views.load_seed_views import Bip39SeedViewView
            return Destination(Bip39SeedViewView, skip_current_view=True)

class SeedGenerateAddressView(View):
    def __init__(self):
        super().__init__()

    def run(self):
        menu = self.run_screen(
            load_seed_screens.SeedGenerateAddressScreen,
        )

        if menu == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        addr_type, addr_index = menu

        if addr_type == "cashtoken":
            address = Bip44.xpub_to_cashaddr_address(self.controller.storage.wallet.xpub, addr_index, version_byte=0x10)
            return Destination(SeedCashQRView, view_args=dict(address=address))
        elif addr_type == "standard":
            address = Bip44.xpub_to_cashaddr_address(self.controller.storage.wallet.xpub, addr_index, version_byte=0x00)
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

class SeedDiscardView(View):
    KEEP = ButtonOption("Keep Wallet")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def __init__(self):
        super().__init__()
        self.wallet = self.controller.storage.wallet

    def run(self):
        button_data = [self.KEEP, self.DISCARD]

        fingerprint = self.wallet.fingerprint
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
            return Destination(WalletOptionsView, skip_current_view=True)
        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.discard_wallet()
            return Destination(MainMenuView, clear_history=True)

class SeedTranscribeSeedQRWholeQRView(View):
    def __init__(self):
        super().__init__()
    
    def run(self):
        from seedcash.gui.screens.load_seed_screens import SeedTranscribeSeedQRWholeQRScreen
        ret = self.run_screen(
            SeedTranscribeSeedQRWholeQRScreen,
            button_data=[ButtonOption("View Zoomed")],
            qr_data=self.controller.storage.seed.get_encoded(),
        )

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif ret == 0:
            return Destination(SeedTranscribeSeedQRZoomedInView)
    
class SeedTranscribeSeedQRZoomedInView(View):
    """
    intial_zone_x, initial_zone_y: Used by the screenshot generator to shift the view
    to a more interesting part of the QR code template.
    """
    def __init__(self, initial_zone_x: int = 0, initial_zone_y: int = 0):
        super().__init__()
        self.seed: Seed = self.controller.storage.seed
        self.initial_zone_x = initial_zone_x
        self.initial_zone_y = initial_zone_y
        self.is_screensaver_allowed = False


    def run(self):
        self.run_screen(
            load_seed_screens.SeedTranscribeSeedQRZoomedInScreen,
            qr_data=self.seed.get_encoded(),
            num_modules=21,
            initial_zone_x=self.initial_zone_x,
            initial_zone_y=self.initial_zone_y,
        )

        return Destination(WalletOptionsView, clear_history=True)
