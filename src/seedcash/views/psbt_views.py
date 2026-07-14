import time
from gettext import gettext as _
from seedcash.gui.components import SeedCashIconsConstants
from seedcash.gui.screens import RET_CODE__BACK_BUTTON
from seedcash.gui.screens.screen import (
    ButtonOption,
    QRDisplayScreen,
    SeedCashButtonListWithNav,
    WarningScreen,
)
from seedcash.models.psbt_parser import PSBTParser
from seedcash.views.view import (
    MainMenuView,
    View,
    Destination,
    BackStackView,
)
from seedcash.gui.screens.psbt_screens import PSBTOverviewScreen
from seedcash.views.wallet_views import WalletOptionsView

class PSBTOverviewView(View):
    def __init__(self):
        super().__init__()

        self.loading_screen = None

        # The PSBTParser takes a while to read the PSBT. Run the loading screen while
        # we wait.
        from seedcash.gui.screens.screen import LoadingScreenThread

        self.loading_screen = LoadingScreenThread(text=_("Parsing PSBT..."))
        self.loading_screen.start()

        try:
            time.sleep(2)  # Give loading screen time to start
        except Exception as e:
            self.loading_screen.stop()
            raise e

    def run(self):
        psbt_parser = self.controller.psbt_parser
        if not psbt_parser:
            return Destination(MainMenuView)

        num_self_transfer_outputs = 0

        # Everything is set. Stop the loading screen
        if self.loading_screen:
            self.loading_screen.stop()

        # Run the overview screen
        selected_menu_num = self.run_screen(
            PSBTOverviewScreen,
            spend_amount=psbt_parser.spend_amount,
            fee_amount=psbt_parser.fee_amount,
            num_inputs=psbt_parser.num_inputs,
            num_self_transfer_outputs=num_self_transfer_outputs,
            destination_addresses=psbt_parser.destination_addresses,
            has_op_return=psbt_parser.op_return_data is not None,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(PSBTDiscardWarningView)

        return Destination(PSBTMathView)

# discard PSBT warning view
class PSBTDiscardWarningView(View):
    DISCARD_PSBT = ButtonOption("Discard PSBT")

    def run(self):
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Discard PSBT"),
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Are you sure?"),
            text=_(
                "Discarding this PSBT will remove it from memory and cannot be undone."
            ),
            button_data=[self.DISCARD_PSBT],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if selected_menu_num == 0:
            self.controller.discard_psbt()
            return Destination(MainMenuView, clear_history=True)

class PSBTMathView(View):
    """
    Follows the Overview pictogram. Shows:
    + total input value
    - recipients' value
    - fees
    """

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTMathScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser
        if not psbt_parser:
            # Should not be able to get here
            return Destination(MainMenuView)

        selected_menu_num = self.run_screen(
            PSBTMathScreen,
            input_amount=psbt_parser.input_amount,
            num_inputs=psbt_parser.num_inputs,
            spend_amount=psbt_parser.spend_amount,
            num_outputs=psbt_parser.num_destinations,
            fee_amount=psbt_parser.fee_amount,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if len(psbt_parser.destination_addresses) > 0:
            return Destination(PSBTAddressDetailsView, view_args={"address_num": 0})

class PSBTAddressDetailsView(View):
    """
    Shows the recipient's address and amount they will receive
    """

    def __init__(self, address_num):
        super().__init__()
        self.address_num = address_num

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTAddressDetailsScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser

        if not psbt_parser:
            # Should not be able to get here
            raise Exception("Routing error")

        # TRANSLATOR_NOTE: Future-tense used to indicate that this transaction will send this amount, as opposed to "Send" on its own which could be misread as an instant command (e.g. "Send Now").
        title = _("Will Send")
        if psbt_parser.num_destinations > 1:
            title += f" (#{self.address_num + 1})"

        button_data = []
        if self.address_num < psbt_parser.num_destinations - 1:
            button_data.append(ButtonOption("Next Recipient"))
        else:
            # TRANSLATOR_NOTE: Short for "Next step"
            button_data.append(ButtonOption("Next"))

        selected_menu_num = self.run_screen(
            PSBTAddressDetailsScreen,
            title=title,
            button_data=button_data,
            address=psbt_parser.destination_addresses[self.address_num],
            amount=psbt_parser.destination_amounts[self.address_num],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if self.address_num < len(psbt_parser.destination_addresses) - 1:
            # Show the next receive addr
            return Destination(
                PSBTAddressDetailsView, view_args={"address_num": self.address_num + 1}
            )

        elif psbt_parser.op_return_data:
            return Destination(PSBTOpReturnView)

        else:
            # Move on to sign the PSBT.
            if psbt_parser.is_signed:
                return Destination(PSBTFinalizeView)
            return Destination(PSBTConfirmationView)
class PSBTOpReturnView(View):
    """
    Shows the OP_RETURN data
    """

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTOpReturnScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser

        if not psbt_parser:
            # Should not be able to get here
            raise Exception("Routing error")

        title = _("OP_RETURN")
        button_data = [ButtonOption("Next")]

        selected_menu_num = self.run_screen(
            PSBTOpReturnScreen,
            title=title,
            button_data=button_data,
            op_return_data=psbt_parser.op_return_data,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if psbt_parser.is_signed:
            return Destination(PSBTFinalizeView)
        return Destination(PSBTConfirmationView)

class PSBTConfirmationView(View):
    """
    Shows the user a confirmation screen before signing the PSBT.
    """
    SIGN_PSBT = ButtonOption("Sign PSBT")
    DELETE_PSBT = ButtonOption("Delete PSBT")


    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTFinalizeScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser

        if not psbt_parser:
            # Should not be able to get here
            return Destination(MainMenuView)

        selected_menu_num = self.run_screen(
            PSBTFinalizeScreen,
            button_data=[self.SIGN_PSBT, self.DELETE_PSBT],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if selected_menu_num == 0:
            try:
                psbt_parser.sign_with_wallet_xpriv(self.controller._storage._wallet._xpriv)
            except Exception as e:
                return Destination(PSBTSigningErrorView)
            # Keep controller bytes in sync with parser after signing.
            self.controller.psbt_bytes = bytearray(psbt_parser.psbt_bytes)
            return Destination(PSBTFinalizeView)
        elif selected_menu_num == 1:
            self.controller.discard_psbt()
            return Destination(MainMenuView, clear_history=True)

class PSBTFinalizeView(View):
    """ """

    SHOW_SIGNED_PSBT = ButtonOption("Show Signed PSBT")
    SAVE_SIGNED_PSBT = ButtonOption("Save Signed PSBT")
    DELETE_SIGNED_PSBT = ButtonOption("Delete Signed PSBT")
    
    def __init__(self):
        super().__init__()

    def run(self):
        
        if self.controller.is_saved_psbt:
            button_data = [self.SHOW_SIGNED_PSBT, self.DELETE_SIGNED_PSBT]
        else:
            button_data = [self.SHOW_SIGNED_PSBT, self.SAVE_SIGNED_PSBT, self.DELETE_SIGNED_PSBT]
        
        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            title="Sign Transaction",
            button_data=button_data,
            show_back_button=False,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if button_data[selected_menu_num] == self.SHOW_SIGNED_PSBT:
            return Destination(PSBTSignedQRDisplayView)
        elif button_data[selected_menu_num] == self.SAVE_SIGNED_PSBT:
            signed_psbt = self.controller.psbt_parser.psbt_bytes
            self.controller.psbt_bytes = bytearray(signed_psbt)
            self.controller._storage._wallet.add_transaction(self.controller.psbt_bytes)
            return Destination(MainMenuView, clear_history=True)
        elif button_data[selected_menu_num] == self.DELETE_SIGNED_PSBT:
            if self.controller.is_saved_psbt:
                self.controller._storage._wallet.remove_transaction(self.controller.psbt_bytes)
            self.controller.discard_psbt()
            return Destination(MainMenuView, clear_history=True)

class PSBTSignedQRDisplayView(View):
    def run(self):
        from seedcash.models.encode_qr import UrPsbtQrEncoder
        from seedcash.models.threads import ThreadsafeCounter
        from seedcash.models.settings_definition import SettingsConstants

        psbt_bytes = self.controller.psbt_bytes
        if self.controller.psbt_parser and self.controller.psbt_parser.psbt_bytes:
            psbt_bytes = self.controller.psbt_parser.psbt_bytes

        # UR encoder expects mutable bytearray fragments internally.
        psbt_bytes = bytearray(psbt_bytes)
        self.controller.psbt_bytes = psbt_bytes

        qr_encoder = UrPsbtQrEncoder(psbt=psbt_bytes)

        current_brightness = self.controller.settings.get_value(
            SettingsConstants.SETTING__QR_BRIGHTNESS
        )
        if current_brightness is None:
            current_brightness = 255

        brightness_counter = ThreadsafeCounter(initial_value=int(current_brightness))

        self.run_screen(
            QRDisplayScreen, qr_encoder=qr_encoder, qr_brightness=brightness_counter
        )

        # Save any brightness adjustments made by the user
        self.controller.settings.set_value(
            SettingsConstants.SETTING__QR_BRIGHTNESS, brightness_counter.cur_count
        )

        # We're done with this PSBT. Route back to MainMenuView which always
        #   clears all ephemeral data (except in-memory seeds).
        return Destination(MainMenuView, clear_history=True)

class PSBTSigningErrorView(View):
    SELECT_DIFF_SEED = ButtonOption("Select Diff Seed")

    def run(self):
        psbt_parser: PSBTParser = self.controller.psbt_parser
        if not psbt_parser:
            # Should not be able to get here
            return Destination(MainMenuView)

        # Just a WarningScreen here; only use DireWarningScreen for true security risks.
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("PSBT Error"),
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Signing Failed"),
            text=_("Signing with this seed did not add a valid signature."),
            button_data=[self.SELECT_DIFF_SEED],
        )

        if selected_menu_num == 0:
            # clear seed selected for psbt signing since it did not add a valid signature
            self.controller.psbt_seed = None
            return Destination(WalletOptionsView, clear_history=True)

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
