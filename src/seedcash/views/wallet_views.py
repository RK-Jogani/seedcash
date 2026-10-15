import logging
from seedcash.models.settings_definition import SettingsConstants
from seedcash.models.bip44 import Bip44
from seedcash.gui.screens import (
    RET_CODE__BACK_BUTTON,
    WarningScreen,
    ButtonOption,
    SeedCashButtonListWithNav
)

from seedcash.gui.screens.wallet_screens import (
    SeedFinalizeScreen,
    GenerateAddressScreen,
    AddressScreen,
    WalletOptionsScreen,
    TranscribeSeedQRWholeQRScreen,
    TranscribeSeedQRZoomedInScreen,
)

from seedcash.gui.screens.load_seed_screens import (
    SeedAddPassphraseScreen,
    SeedReviewPassphraseScreen,
)

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
            SeedFinalizeScreen,
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
        initial_keyboard: str = SeedAddPassphraseScreen.KEYBOARD__LOWERCASE_BUTTON_TEXT
    ):
        super().__init__()
        self.initial_keyboard = initial_keyboard
        self.wallet = self.controller.storage.wallet

    def run(self):
        ret_dict = self.run_screen(
            SeedAddPassphraseScreen,
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
            title="Discard passphrase?",
            status_headline=None,
            text="Your current passphrase entry will be erased",
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
            SeedReviewPassphraseScreen,
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
            SeedFinalizeScreen,
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
            WalletOptionsScreen,
            button_data=button_data,
            fingerprint=self.wallet.fingerprint,
        )
        

        if button_data[selected_menu_num] == self.VIEW_SEED:
            return Destination(ViewSeedView)

        elif button_data[selected_menu_num] == self.EXPORT_XPUB:
            return Destination(AddressEntryView, view_args={"address": self.wallet.xpub, "title": "Export Xpub"})
        elif button_data[selected_menu_num] == self.GENERATE_ADDRESS:
            return Destination(GenerateAddressView)
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
                WarningScreen,
                show_back_button=True,
                title="",
                text="Exposing your Seed gives full control of your funds")
            
            if result == RET_CODE__BACK_BUTTON:
                return Destination(BackStackView)
        
        if self.controller.storage.passphrase:
            result = self.run_screen(
                SeedReviewPassphraseScreen,
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

class GenerateAddressView(View):
    def __init__(self):
        super().__init__()

    def run(self):
        menu = self.run_screen(
            GenerateAddressScreen,
        )

        if menu == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        addr_type, addr_index = menu

        if addr_type == "cashtoken":
            address = Bip44.xpub_to_cashaddr_address(self.controller.storage.wallet.xpub, addr_index, version_byte=0x10)
            return Destination(AddressEntryView, view_args=dict(address=address, title="CashToken Address"))
        elif addr_type == "standard":
            address = Bip44.xpub_to_cashaddr_address(self.controller.storage.wallet.xpub, addr_index, version_byte=0x00)
            return Destination(AddressEntryView, view_args=dict(address=address, title="Standard Address"))

class AddressEntryView(View):
    EXPORT_QR = ButtonOption("QR")
    EXPORT_ADDR = ButtonOption("Text")

    def __init__(self, address: str = None, title: str = None):
        super().__init__()
        self.address = address
        self.title = title

    def run(self):

        button_data = [self.EXPORT_QR, self.EXPORT_ADDR]

        self.selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            title=self.title,
            button_data=button_data,
            show_back_button=True,
        )

        if self.selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif button_data[self.selected_menu_num] == self.EXPORT_QR:
            return Destination(QRAddressView, view_args=dict(address=self.address))
        elif button_data[self.selected_menu_num] == self.EXPORT_ADDR:
            return Destination(ViewAddressView, view_args=dict(address=self.address, title=self.title))

class ViewAddressView(View):
    def __init__(self, address: str = None, title: str = None):
        super().__init__()
        self.address = address
        self.title = title

    def run(self):
        self.selected_menu_num = self.run_screen(
            AddressScreen,
            title=self.title,
            address=self.address,
        )

        if self.selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        return Destination(AddressEntryView, view_args=dict(address=self.address))

class QRAddressView(View):
    def __init__(self, address: str = None):
        self.address = address
        super().__init__()
        
    def run(self):
        from seedcash.models.encode_qr import GenericStaticQrEncoder
        from seedcash.models.threads import ThreadsafeCounter
        from seedcash.models.settings_definition import SettingsConstants

        qr_encoder = GenericStaticQrEncoder(data=self.address)

        current_brightness = self.controller.settings.get_value(
            SettingsConstants.SETTING__QR_BRIGHTNESS
        )
        if current_brightness is None:
            current_brightness = 255

        brightness_counter = ThreadsafeCounter(initial_value=int(current_brightness))

        from seedcash.gui.screens import QRDisplayScreen
        self.run_screen(
            QRDisplayScreen, qr_encoder=qr_encoder, qr_brightness=brightness_counter
        )

        # Save any brightness adjustments made by the user
        self.controller.settings.set_value(
            SettingsConstants.SETTING__QR_BRIGHTNESS, brightness_counter.cur_count
        )

        return Destination(BackStackView)

class SeedDiscardView(View):
    KEEP = ButtonOption("Keep Wallet")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def __init__(self):
        super().__init__()
        self.wallet = self.controller.storage.wallet

    def run(self):
        
        button_data = [self.KEEP, self.DISCARD]

        text = f"Wipe wallet {self.wallet.fingerprint} from the device?"
        selected_menu_num = self.run_screen(
            WarningScreen,
            title="Discard Wallet?",
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

class TranscribeSeedQRWholeQRView(View):
    def __init__(self):
        super().__init__()
        self.is_screensaver_allowed = False
    
    def run(self):
        ret = self.run_screen(
            TranscribeSeedQRWholeQRScreen,
            button_data=[ButtonOption("View Zoomed")],
            qr_data=self.controller.storage.seed.get_encoded(),
        )

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif ret == 0:
            return Destination(TranscribeSeedQRZoomedInView)
    
class TranscribeSeedQRZoomedInView(View):
    """
    intial_zone_x, initial_zone_y: Used by the screenshot generator to shift the view
    to a more interesting part of the QR code template.
    """
    def __init__(self, initial_zone_x: int = 0, initial_zone_y: int = 0):
        super().__init__()
        self.initial_zone_x = initial_zone_x
        self.initial_zone_y = initial_zone_y
        self.is_screensaver_allowed = False


    def run(self):
        self.run_screen(
            TranscribeSeedQRZoomedInScreen,
            qr_data=self.controller.storage.seed.get_encoded(),
            num_modules=21,
            initial_zone_x=self.initial_zone_x,
            initial_zone_y=self.initial_zone_y,
        )

        return Destination(WalletOptionsView, clear_history=True)
