import time
from gettext import gettext as _
from typing import List
from seedcash.gui.components import GUIConstants, SeedCashIconsConstants, get_category_color
from seedcash.gui.screens import RET_CODE__BACK_BUTTON
from seedcash.gui.screens.screen import (
    ButtonOption,
    QRDisplayScreen,
    WarningScreen,
)
from seedcash.models.psbt_parser import PSBTParser, TxOutput
from seedcash.views.view import (
    MainMenuView,
    View,
    Destination,
    BackStackView,
)
from seedcash.gui.screens.psbt_screens import PSBTOverviewScreen
from seedcash.views.wallet_views import WalletOptionsView

class LoadingPSBTView(View):
    def __init__(self):
        super().__init__()

        from seedcash.gui.screens.screen import LoadingScreenThread
        from seedcash.models.psbt_parser import PSBTParser

        self.loading_screen = LoadingScreenThread(text=_("Parsing PSBT..."))
        self.loading_screen.start()
        try:
            self.controller.psbt_parser = PSBTParser(
                bytearray(self.controller.psbt_bytes),
                wallet_fingerprint=self.controller._storage._wallet._fingerprint,
            )
            # Keep one canonical representation shared across all PSBT views.
            self.controller.psbt_bytes = bytearray(self.controller.psbt_parser.psbt_bytes)
        finally:
            time.sleep(2)
            self.loading_screen.stop()

    def run(self):
        print("PSBT inputs:", self.controller.psbt_parser.inputs)
        if len(self.controller.psbt_parser.inputs[0].items()) > 0:
            return Destination(PSBTNFTView, skip_current_view=True)
        elif len(self.controller.psbt_parser.inputs[1].items()) > 0:
            return Destination(PSBTFungibleTokenDetailsView, skip_current_view=True)
        else:
            return Destination(BCHPSBTOverviewView, skip_current_view=True, view_args={"is_last": True})


# BCH
class BCHPSBTOverviewView(View):
    def __init__(self, is_last=False):
        super().__init__()
        self.loading_screen = None
        self.is_last = is_last

    def run(self):
        psbt_parser = self.controller.psbt_parser
        if not psbt_parser:
            return Destination(MainMenuView)

        # Run the overview screen
        selected_menu_num = self.run_screen(
            PSBTOverviewScreen,
            spend_amount=psbt_parser.output_amount,
            fee_amount=psbt_parser.fee_amount,
            num_inputs=psbt_parser.num_inputs,
            destination_addresses=psbt_parser.destination_addresses,
            has_op_return=psbt_parser.op_return_data is not None,
            category_id=None
        )
        if selected_menu_num == RET_CODE__BACK_BUTTON:
            if self.is_last:
                return Destination(PSBTDiscardWarningView)
            return Destination(BackStackView)

        return Destination(PSBTMathView)

# FT View
class PSBTFungibleTokenDetailsView(View):
    def __init__(self, category_num=0):
            super().__init__()
            self.loading_screen = None
            self.category_num = category_num
            
    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTOverviewScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser
        if not psbt_parser:
            # Should not be able to get here
            return Destination(MainMenuView)

        if len(psbt_parser.token_categories) == 0:
            # Should not be able to get here
            return Destination(BCHPSBTOverviewView, skip_current_view=True)
        
        category_id = psbt_parser.token_categories[self.category_num]

        if psbt_parser.ft_burning(category_id):
            return Destination(PSBTBurningFTWarningView, view_args={"category_num": self.category_num, "btn_color": get_category_color(category_id)})

        destination_addresses = psbt_parser.token_destination_addresses(category_id)
        selected_menu_num = self.run_screen(
            PSBTOverviewScreen,
            spend_amount=psbt_parser.ft_output_amount(category_id),
            num_inputs=len(psbt_parser.inputs[1].get(category_id, [])),
            destination_addresses=destination_addresses,
            category_id=category_id
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if selected_menu_num == 0:
            return Destination(PSBTAddressDetailsView, view_args={"address_num": 0, "destination_addresses": destination_addresses, "category_num": self.category_num})
        return Destination(BCHPSBTOverviewView)

# NFT Details View
class PSBTNFTView(View):
    def __init__(self, category_num=0, confirmed=False):
            super().__init__()
            self.category_num = category_num
            self.confirmed = confirmed
            self.loading_screen = None
    
    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTNFTScreen   # correct import

        psbt_parser: PSBTParser = self.controller.psbt_parser

        if not self.confirmed:
            warning = self.controller.psbt_parser.get_warning(self.controller.psbt_parser.nft_categories[self.category_num])
            if warning == "minting":
                return Destination(PSBTMintingNFTWarningView, view_args={"category_num": self.category_num})
            elif warning == "burning":
                return Destination(PSBTBurningNFTWarningView, view_args={"category_num": self.category_num})
        
        selected_menu_num = self.run_screen(
            PSBTNFTScreen,
            category_id=psbt_parser.nft_categories[self.category_num],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if selected_menu_num == 0:
            return Destination(PSBTNFTDetailsView, view_args={"category_num": self.category_num})

# NFT Details View
class PSBTNFTDetailsView(View):
    def __init__(self, output_num: int = 0, category_num: int = 0):
        self.output_num = output_num
        self.category_num = category_num
        super().__init__()
        

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTNFTDetailsScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser
        tx_outputs: List[TxOutput] = psbt_parser.outputs[0].get(psbt_parser.nft_categories[self.category_num], [])

        selected_menu_num = self.run_screen(
            PSBTNFTDetailsScreen,
            output_num=self.output_num + 1,
            nft_commitment=tx_outputs[self.output_num].token.nft_data.commitment,
            nft_capability=tx_outputs[self.output_num].token.nft_data.capability,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        
        return Destination(PSBTNFTAddressDetailsView, view_args={"output_num": self.output_num, "category_num": self.category_num})
class PSBTNFTAddressDetailsView(View):
    def __init__(self, output_num, category_num):
        super().__init__()
        self.output_num = output_num
        self.category_num = category_num

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTNFTAddressScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser

        tx_outputs: List[TxOutput] = psbt_parser.outputs[0].get(psbt_parser.nft_categories[self.category_num], [])
        
        selected_menu_num = self.run_screen(
            PSBTNFTAddressScreen,
            destination_addr=tx_outputs[self.output_num].address,
            index=self.output_num + 1
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if self.output_num < len(tx_outputs) - 1:
            return Destination(
                PSBTNFTDetailsView,
                view_args={"output_num": self.output_num + 1, "category_num": self.category_num},
            )
        if self.category_num < len(psbt_parser.nft_categories) - 1:
            return Destination(
                PSBTNFTDetailsView,
                view_args={"output_num": 0, "category_num": self.category_num + 1},
            )
        
        return Destination(PSBTFungibleTokenDetailsView, view_args={"category_num": 0})

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
            spend_amount=psbt_parser.output_amount,
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

    def __init__(self, address_num, destination_addresses=None, category_num=None):
        super().__init__()
        self.address_num = address_num
        if destination_addresses:
            self.destination_addresses = destination_addresses
        else:
            self.destination_addresses = self.controller.psbt_parser.destination_addresses

        self.category_num = category_num

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

        button_title = "Next"
        if self.address_num < psbt_parser.num_destinations - 1:
            button_title = _("Next Recipient")
        
        if self.category_num is not None:
            selected_menu_num = self.run_screen(
                PSBTAddressDetailsScreen,
                title=title,
                button_title=button_title,
                address=self.destination_addresses[self.address_num],
                amount=psbt_parser.output_at_index(self.address_num).token.ft_amount,
                category_id=psbt_parser.output_at_index(self.address_num).token.category_id,
            )
        else:
            selected_menu_num = self.run_screen(
                PSBTAddressDetailsScreen,
                title=title,
                button_title=button_title,
                address=self.destination_addresses[self.address_num],
                amount=psbt_parser.output_at_index(self.address_num).value_satoshis,
            )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if self.address_num < len(self.destination_addresses) - 1:
            # Show the next receive addr
            return Destination(
                PSBTAddressDetailsView, view_args={"address_num": self.address_num + 1, "destination_addresses": self.destination_addresses, "category_num": self.category_num}
            )
        
        elif psbt_parser.op_return_data:
            return Destination(PSBTOpReturnView)

        elif self.category_num is not None:
            if self.category_num < len(psbt_parser.token_categories) - 1:
                return Destination(PSBTFungibleTokenDetailsView, view_args={"category_num": self.category_num + 1})
            else:
                return Destination(BCHPSBTOverviewView)

        return Destination(MainMenuView, clear_history=True)
            
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
        # TODO: Will function to sign the PSBT be added here? If so, we can route to the signing view.
        return Destination(PSBTSignedQRDisplayView)

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


# PSBT Warning Views

# Discard PSBT Warning
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

# Minting NFT(s) Detected Warning
class PSBTMintingNFTWarningView(View):
    CONFIRM = ButtonOption("Confirm", button_color=GUIConstants.MUSD_BLUE)
    def __init__(self, category_num=0):
        super().__init__()
        self.category_num = category_num
    def run(self):
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Minting NFT(s)"),
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Are you sure?"),
            text=_("Signing would allow transfer, burn, or modify any involved NFT(s)"),
            button_data=[self.CONFIRM],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if selected_menu_num == 0:
            return Destination(PSBTNFTView, view_args={"category_num": self.category_num, "confirmed": True})

# Burning NFT(s) Detected Warning
class PSBTBurningNFTWarningView(View):
    CONFIRM = ButtonOption("Confirm", button_color=GUIConstants.MUSD_BLUE)

    def __init__(self, category_num=0):
        super().__init__()
        self.category_num = category_num

    def run(self):
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Burning NFT(s)"),
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Are you sure?"),
            text=_("At least one NFT in the following category has been modified or burned."),
            button_data=[self.CONFIRM],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if selected_menu_num == 0:
            return Destination(PSBTNFTView, view_args={"category_num": self.category_num})

class PSBTBurningFTWarningView(View):
    def __init__(self, category_num=0, btn_color=GUIConstants.MUSD_BLUE):
        super().__init__()
        self.category_num = category_num
        self.button_color = btn_color

    def run(self):
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Burning Fungible Token(s)"),
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Are you sure?"),
            text=_("At least one fungible token in the following category has been modified or burned."),
            button_data=[ButtonOption("Confirm", button_color=self.button_color)],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if selected_menu_num == 0:
            return Destination(PSBTFungibleTokenDetailsView, view_args={"category_num": self.category_num})