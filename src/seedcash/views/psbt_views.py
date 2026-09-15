import time
from gettext import gettext as _
from typing import List
from seedcash.gui.components import Category, GUIConstants, SeedCashIconsConstants, get_category
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
            self.controller.psbt_parser = PSBTParser(self.controller.psbt_bytes)
        finally:
            time.sleep(2)
            self.loading_screen.stop()

    def run(self):
        if self.controller.psbt_parser.is_genesis:
            return Destination(GenesisWarningView, skip_current_view=True)
        elif self.controller.psbt_parser.inputs.ft:
            return Destination(PSBTFungibleTokenDetailsView, skip_current_view=True)
        elif self.controller.psbt_parser.inputs.nft:
            return Destination(PSBTNFTView, skip_current_view=True)
        else:
            return Destination(BCHPSBTOverviewView, skip_current_view=True, view_args={"is_last": True})

# GENESIS View
class GenesisWarningView(View):
    def run(self):
        result = self.run_screen(
            WarningScreen,
            title=_("Genesis Transaction"),
            show_back_button=True,
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("New Fungible Token"),
            text=_("This transaction will create a new token category."),
            button_data=[ButtonOption("Confirm")],
            selected_color=GUIConstants.MUSD_BLUE
        )

        if result == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if result == 0:
            return Destination(PSBTGenesisFTDetailsView, view_args={"category_num": 0})

class PSBTGenesisFTDetailsView(View):
    def __init__(self, category_num: int = 0):
        super().__init__()
        self.loading_screen = None
        self.category_num = category_num

    def run(self):
        psbt_parser: PSBTParser = self.controller.psbt_parser
        if not psbt_parser:
            return Destination(MainMenuView)
        category_ids = self.controller.psbt_parser.genesis.categories["ft"]

        if not category_ids or self.category_num >= len(category_ids):
            return Destination(PSBTNFTView, view_args={"category_num": 0, "is_genesis": True})

        category_id = category_ids[self.category_num]
        category: Category = get_category(category_id)

        outputs = psbt_parser.genesis.outputs.get_ft(category_id)

        selected_menu_num = self.run_screen(
            PSBTOverviewScreen,
            input_count=psbt_parser.genesis.inputs.get_ft_count(category_id),
            destination_addresses=[output.address for output in outputs],
            selected_color=category.icon_color,
            category=category,
            is_genesis=True
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if selected_menu_num == 0:
            return Destination(PSBTAddressDetailsView, view_args={"output_num": 0, "outputs": outputs, "category_id": category_id, "category_num": self.category_num, "is_genesis": True})

# FT View
class PSBTFungibleTokenDetailsView(View):
    def __init__(self, category_num: int = 0):
        super().__init__()
        self.loading_screen = None
        self.category_num = category_num
            
    def run(self):
        psbt_parser: PSBTParser = self.controller.psbt_parser
        if not psbt_parser:
            return Destination(MainMenuView)
        category_id = self.controller.psbt_parser.inputs.get_ft_category_ids [self.category_num]
        category: Category = get_category(category_id)

        if psbt_parser.is_ft_burning(category_id):
            
            if result == RET_CODE__BACK_BUTTON:
                return Destination(BackStackView)

        outputs = psbt_parser.outputs.get_ft(category_id)
        spend_amount = psbt_parser.inputs.get_ft_total_amount(category_id)

        if category.token_symbol == "[?]":
            # If the category is unknown, show a warning screen before proceeding to the overview screen
            result = self.run_screen(
                WarningScreen,
                title=_("Unknown Token ID"),
                show_back_button=True,
                status_headline=_(""),
                status_icon_name=SeedCashIconsConstants.WARNING,
                text=_(f"Unknown token ID, No decimal conversion applied!"),
                button_data=[ButtonOption("Confirm")],
                selected_color=category.icon_color
            )
            if result == RET_CODE__BACK_BUTTON:
                return Destination(BackStackView)
        if spend_amount >= 10e8:
            # If the spend amount is greater than 10M, show a warning screen before proceeding to the overview screen
            result = self.run_screen(
                WarningScreen,
                title=_("High Raw Amount"),
                show_back_button=True,
                status_headline=_(""),
                status_icon_name=SeedCashIconsConstants.WARNING,
                text=_(f"This transaction will send {spend_amount} {category.token_symbol}"),
                button_data=[ButtonOption("Confirm")],
                selected_color=category.icon_color
            )
            if result == RET_CODE__BACK_BUTTON:
                return Destination(BackStackView)


        selected_menu_num = self.run_screen(
            PSBTOverviewScreen,
            spend_amount=spend_amount,
            input_count=psbt_parser.inputs.get_ft_count(category_id),
            destination_addresses=[output.address for output in outputs],
            selected_color=category.icon_color,
            category=category
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if selected_menu_num == 0:
            return Destination(PSBTAddressDetailsView, view_args={"output_num": 0, "outputs": outputs, "category_id": category_id, "category_num": self.category_num})

class PSBTFungibleBurningWarningView(View):
    def run(self):
        result = self.run_screen(
            WarningScreen,
            title=_("Burning Fungible Token(s)"),
            show_back_button=True,
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Are you sure?"),
            text=_("At least one fungible token in the following category has been modified or burned."),
            button_data=[ButtonOption("Confirm")],
            selected_color=GUIConstants.MUSD_BLUE
        )
        if result == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if result == 0:
            return Destination(PSBTFungibleTokenDetailsView, view_args={"category_num": self.category_num, "confirmed": True})

# NFT Details View
class PSBTNFTView(View):
    def __init__(self, category_num=0, is_genesis=False, confirmed=False):
            super().__init__()
            self.category_num = category_num
            self.is_genesis = is_genesis
            self.confirmed = confirmed
            self.loading_screen = None
    
    def run(self):
        if self.is_genesis:
            nft_category_ids = self.controller.psbt_parser.genesis.inputs.get_nft_category_ids
        else:
            nft_category_ids = self.controller.psbt_parser.inputs.get_nft_category_ids

        if nft_category_ids is None or len(nft_category_ids) == 0:
            return Destination(BCHPSBTOverviewView)
        
        category_id = nft_category_ids[self.category_num]

        if not self.confirmed:
            warnings = self.controller.psbt_parser.get_nft_warnings(category_id)
            if "minting" in warnings:
                result = self.run_screen(
                    WarningScreen,
                    title=_("Minting NFT(s)"),
                    show_back_button=True,
                    status_icon_name=SeedCashIconsConstants.WARNING,
                    status_headline=_("Are you sure?"),
                    text=_("Signing would allow transfer, burn, or modify any involved NFT(s)"),
                    button_data=[ButtonOption("Confirm")],
                    selected_color=self.selected_color
                )
                if result == RET_CODE__BACK_BUTTON:
                    return Destination(BackStackView)
                if result == 0:
                    return Destination(PSBTNFTView, view_args={"category_num": self.category_num, "confirmed": True})
            if "burning" in warnings:
                result = self.run_screen(
                    WarningScreen,
                    title=_("Burning NFT(s)"),
                    show_back_button=True,
                    status_icon_name=SeedCashIconsConstants.WARNING,
                    status_headline=_("Are you sure?"),
                    text=_("At least one NFT in the following category has been modified or burned."),
                    button_data=[ButtonOption("Confirm")],
                    selected_color=self.selected_color
                )
                if result == RET_CODE__BACK_BUTTON:
                    return Destination(BackStackView)
                if result == 0:
                    return Destination(PSBTNFTView, view_args={"category_num": self.category_num, "confirmed": True})

        from seedcash.gui.screens.psbt_screens import PSBTNFTScreen
        selected_menu_num = self.run_screen(
            PSBTNFTScreen,
            button_data=[ButtonOption("Next")],
            selected_color=GUIConstants.MUSD_BLUE,
            category_id=category_id,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if selected_menu_num == 0:
            return Destination(PSBTNFTDetailsView, view_args={"category_num": self.category_num, "category_id": category_id, "is_genesis": self.is_genesis})

# NFT Details View
class PSBTNFTDetailsView(View):
    def __init__(self, output_num: int = 0, category_num: int = 0, category_id: str = "", is_genesis: bool = False):
        self.output_num = output_num
        self.category_num = category_num
        self.category_id = category_id
        self.is_genesis = is_genesis
        super().__init__()
        

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTNFTDetailsScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser
        if self.is_genesis:
            outputs = psbt_parser.genesis.outputs.get_nft(self.category_id)
        else:
            outputs = psbt_parser.outputs.get_nft(self.category_id)

        selected_menu_num = self.run_screen(
            PSBTNFTDetailsScreen,
            button_data=[ButtonOption("Next")],
            selected_color=GUIConstants.MUSD_BLUE,
            output_num=self.output_num + 1,
            nft_commitment=outputs[self.output_num].token.nft_data.commitment,
            nft_capability=outputs[self.output_num].token.nft_data.capability,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        
        return Destination(PSBTNFTAddressDetailsView, view_args={"output_num": self.output_num, "outputs": outputs, "category_num": self.category_num, "category_id": self.category_id, "is_genesis": self.is_genesis})

class PSBTNFTAddressDetailsView(View):
    def __init__(self, output_num: int = 0, outputs: List[TxOutput] = 0, category_num: int = 0, category_id: str = "", is_genesis: bool = False):
        super().__init__()
        self.output_num = output_num
        self.outputs = outputs
        self.category_num = category_num
        self.category_id = category_id
        self.is_genesis = is_genesis
    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTNFTAddressScreen
        
        selected_menu_num = self.run_screen(
            PSBTNFTAddressScreen,
            button_data=[ButtonOption("Next")],
            selected_color=GUIConstants.MUSD_BLUE,
            destination_addr=self.outputs[self.output_num].address,
            index=self.output_num + 1
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if self.output_num < len(self.outputs) - 1:
            return Destination(
                PSBTNFTDetailsView,
                view_args={"output_num": self.output_num + 1, "category_num": self.category_num, "category_id": self.category_id, "is_genesis": self.is_genesis},
            )

        if self.is_genesis and self.category_num < self.controller.psbt_parser.genesis.inputs.get_nft_count(self.category_id) - 1:
            return Destination(
                PSBTNFTView,
                view_args={"category_num": self.category_num + 1, "is_genesis": True},
            )
        elif self.category_num < self.controller.psbt_parser.outputs.get_nft_count(self.category_id) - 1:
            return Destination(
                PSBTNFTView,
                view_args={"category_num": self.category_num + 1, "is_genesis": self.is_genesis},
            )
            
        return Destination(BCHPSBTOverviewView)

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
            spend_amount=psbt_parser.input_amount,
            fee_amount=psbt_parser.fee_amount,
            input_count=psbt_parser.input_count,
            destination_addresses=[output.address for output in psbt_parser.bch_outputs],
            category=None,
            has_op_return=psbt_parser.has_op_return,
        )
        if selected_menu_num == RET_CODE__BACK_BUTTON:
            if self.is_last:
                return Destination(PSBTWarningView, args={"title": _("Discard PSBT"), "headline": _("Are you sure?"), "text": _("Discarding this PSBT will remove it from memory and cannot be undone."), "button_title": _("Discard")})
            return Destination(BackStackView)

        return Destination(PSBTMathView)

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
            input_amount=psbt_parser.total_input_amount,
            input_count=psbt_parser.input_count,
            spend_amount=psbt_parser.total_output_amount,
            output_count=psbt_parser.output_count,
            fee_amount=psbt_parser.fee_amount,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if len([output for output in self.controller.psbt_parser.bch_outputs if output.address]) > 0:
            return Destination(PSBTAddressDetailsView,  view_args={"output_num": 0, "outputs": self.controller.psbt_parser.bch_outputs})

class PSBTAddressDetailsView(View):
    """
    Shows the recipient's address and amount they will receive
    """

    def __init__(self, output_num: int = 0, outputs: List[TxOutput] = None, category_id: str = None, category_num: int = 0, is_genesis: bool = False):
        super().__init__()
        if not outputs:
            raise ValueError("Outputs list cannot be empty")
        self.output_num = output_num
        self.outputs = outputs
        self.category_id = category_id
        self.category_num = category_num
        self.is_genesis = is_genesis

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTAddressDetailsScreen

        # TRANSLATOR_NOTE: Future-tense used to indicate that this transaction will send this amount, as opposed to "Send" on its own which could be misread as an instant command (e.g. "Send Now").
        title = _("Will Send")
        if len(self.outputs) > 1:
            title += f" (#{self.output_num + 1})"
    
        if self.category_id is not None:
            category: Category = get_category(self.category_id)
            amount = self.outputs[self.output_num].token.ft_amount
            if amount >= 10e8:
                result = self.run_screen(
                    WarningScreen,
                    title=_("High Raw Amount"),
                    show_back_button=True,
                    status_headline=_(""),
                    status_icon_name=SeedCashIconsConstants.WARNING,
                    text=_(f"This transaction will send {amount} {category.token_symbol}"),
                    button_data=[ButtonOption("Confirm")],
                    selected_color=category.icon_color
                )
                if result == RET_CODE__BACK_BUTTON:
                    return Destination(BackStackView)
            selected_menu_num = self.run_screen(
                PSBTAddressDetailsScreen,
                title=title,
                button_data=[ButtonOption("Next Recipient" if self.output_num < len(self.outputs) - 1 else "Next")],
                selected_color=category.icon_color,
                address=self.outputs[self.output_num].address,
                amount=amount,
                category=category,
            )
        else:
            selected_menu_num = self.run_screen(
                PSBTAddressDetailsScreen,
                title=title,
                button_data=[ButtonOption("Next Recipient" if self.output_num < len(self.outputs) - 1 else "Next")],
                address=self.outputs[self.output_num].address,
                amount=self.outputs[self.output_num].value_satoshis,
            )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if self.output_num < len(self.outputs) - 1:
            return Destination(
                PSBTAddressDetailsView, view_args={"output_num": self.output_num + 1, "outputs": self.outputs, "category_id": self.category_id}
            )
    
        elif self.category_id is not None:
            if self.is_genesis:
                if self.category_num < self.controller.psbt_parser.genesis.inputs.get_ft_count(self.category_id) - 1:
                    return Destination(PSBTGenesisFTDetailsView, view_args={"category_num": self.category_num + 1})
                else:
                    return Destination(PSBTNFTView, view_args={"category_num": 0, "is_genesis": True})
            if self.category_num < self.controller.psbt_parser.inputs.get_ft_count(self.category_id) - 1:
                return Destination(PSBTFungibleTokenDetailsView, view_args={"category_num": self.category_num + 1})    
            else:
                return Destination(PSBTNFTView, view_args={"category_num": 0})
    
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
        print(f"PSBT BYTES: {self.controller.psbt_bytes}")

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
                self.controller.psbt_bytes = self.controller._storage._wallet.sign_psbt(self.controller.psbt_parser)
            except Exception as e:
                print(f"Error signing PSBT: {e}")
                return Destination(PSBTSigningErrorView )
            
            return Destination(PSBTSignedQRDisplayView)
        elif selected_menu_num == 1:
            self.controller.discard_psbt()
            return Destination(MainMenuView, clear_history=True)

class PSBTSignedQRDisplayView(View):
    def run(self):
        from seedcash.models.encode_qr import UrPsbtQrEncoder
        from seedcash.models.threads import ThreadsafeCounter
        from seedcash.models.settings_definition import SettingsConstants

        qr_encoder = UrPsbtQrEncoder(psbt=self.controller.psbt_bytes, qr_max_fragment_size=self.controller.settings.get_value(SettingsConstants.SETTING_QR_DENSITY))

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
    DISCARD_PSBT = ButtonOption("Discard PSBT")

    def run(self):
        psbt_parser: PSBTParser = self.controller.psbt_parser
        if not psbt_parser:
            # Should not be able to get here
            return Destination(MainMenuView)

        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("PSBT Error"),
            show_back_button=True,
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Signing Failed"),
            text=_("Signing with this seed did not add a valid signature."),
            button_data=[self.DISCARD_PSBT],
        )

        if selected_menu_num == 0:
            # clear seed selected for psbt signing since it did not add a valid signature
            self.controller.psbt_seed = None
            return Destination(WalletOptionsView, clear_history=True)

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

# # TODO: Will do it in Future
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
        return Destination(PSBTConfirmationView)

# Discard PSBT Warning
class PSBTWarningView(View):

    def __init__(self, title: str = "", headline: str = "", text: str = "", button_title: str = "Confirm"):
        super().__init__()
        self.title = title
        self.headline = headline
        self.text = text
        self.button_title = button_title
    def run(self):
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=self.title,
            show_back_button=True,
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=self.headline,
            text_=self.text,
            button_data=[ButtonOption(self.button_title)],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if selected_menu_num == 0:
            self.controller.discard_psbt()
            return Destination(MainMenuView, clear_history=True)