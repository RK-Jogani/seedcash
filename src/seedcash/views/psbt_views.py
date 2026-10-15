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
    View,
    Destination,
    BackStackView,
)
from seedcash.gui.screens.psbt_screens import PSBTNFTScreen, PSBTOverviewScreen
from seedcash.views.wallet_views import WalletOptionsView

class PSBTTokenView(View):
    """Shared category navigation for the separate token review screens."""

    @property
    def review(self):
        return self.controller.psbt_parser.token_review

    @property
    def category(self):
        return self.review.current_category

    def category_start_view(self, include_genesis=True):
        if include_genesis and self.category.is_genesis:
            return GenesisWarningView
        if self.category.is_ft:
            if get_category(self.category.category_id).token_symbol == "[?]":
                return PSBTFTUnknownWarningView
            if self.category.ft_inputs_total_amount >= 10e6:
                return PSBTFTHighRawAmountWarningsView
            return PSBTFungibleTokenDetailsView
        if self.category.is_nft_minted:
            return PSBTMintingNFTWarningView
        return PSBTTokenDetailsView

    def next_category(self):
        if self.review.next_category is None:
            return Destination(BCHPSBTOverviewView)
        return Destination(self.category_start_view())

    def previous_category(self):
        # Restore category state before the controller restores its screen.
        if self.review.previous_category is None:
            return Destination(PSBTDiscardWarningView)
        return Destination(BackStackView)

    def back(self):
        if self.category_start_view() is type(self):
            return self.previous_category()
        return Destination(BackStackView)

class LoadingPSBTView(PSBTTokenView):
    def __init__(self):
        super().__init__()
        self.loading_screen = None
        from seedcash.gui.screens.screen import LoadingScreenThread
        self.loading_screen = LoadingScreenThread(text=_("Parsing PSBT..."))
        self.loading_screen.start()
        self.controller.psbt_parser = None

    def run(self):

        try:
            self.controller.psbt_parser = PSBTParser(self.controller.psbt_bytes)
        except Exception as e:
            # To run animation for 2 seconds if error occurs
            time.sleep(2)
            self.loading_screen.stop()
            return Destination(PSBTParsingErrorView, skip_current_view=True)

        # To run animation for 2 seconds if parsing is successful
        time.sleep(2)
        self.loading_screen.stop()

        if self.controller.psbt_parser.token_review is not None:
            self.controller.psbt_parser.token_review.initiate
            return Destination(
                self.category_start_view(),
                skip_current_view=True,
            )
        else:
            return Destination(BCHPSBTOverviewView, view_args={"is_last": True}, skip_current_view=True)

# GENESIS View
class GenesisWarningView(PSBTTokenView):
    def run(self):

        result = self.run_screen(
            WarningScreen,
            title=_("Genesis Transaction"),
            show_back_button=True,
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("New Fungible Token") if self.category.is_ft else _("New Non-Fungible Token"),
            text=_("This transaction will create a new token category."),
            button_data=[ButtonOption("Confirm")],
            selected_color=GUIConstants.MUSD_BLUE
        )

        if result == RET_CODE__BACK_BUTTON:
            return self.previous_category()

        return Destination(self.category_start_view(include_genesis=False))

# FT Views
class PSBTFTUnknownWarningView(PSBTTokenView):
    def run(self):
        result = self.run_screen(
            WarningScreen,
            title=_("Unknown FT token ID"),
            show_back_button=True,
            status_headline=_(""),
            status_icon_name=SeedCashIconsConstants.WARNING,
            text=_(f"Unknown token ID, No decimal conversion applied."),
            button_data=[ButtonOption("Confirm")],
            selected_color=get_category(self.category.category_id).icon_color
        )

        if result == RET_CODE__BACK_BUTTON:
            return self.back()

        return Destination(PSBTTokenDetailsView)


class PSBTFTHighRawAmountWarningsView(PSBTTokenView):
    def run(self):

        category: Category = get_category(self.category.category_id)

        result = self.run_screen(
            WarningScreen,
            title=_("High Raw Amount"),
            show_back_button=True,
            status_headline=_(""),
            status_icon_name=SeedCashIconsConstants.WARNING,
            text=_(f"This transaction will send {self.category.ft_inputs_total_amount} {category.token_symbol}"),
            button_data=[ButtonOption("Confirm")],
            selected_color=category.icon_color
        )

        if result == RET_CODE__BACK_BUTTON:
            return self.back()

        return Destination(PSBTFungibleTokenDetailsView)

class PSBTFungibleTokenDetailsView(PSBTTokenView):
    def run(self):

        selected_menu_num = self.run_screen(
            PSBTOverviewScreen,
            inputs_amount= 0 if self.category.is_genesis else self.category.ft_inputs_total_amount,
            input_count=self.category.inputs_count,
            destination_addresses=[output.address for output in self.category.outputs],
            category=get_category(self.category.category_id),
            is_genesis=self.category.is_genesis
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return self.back()
        if not self.category.outputs:
            return self.next_category()
        self.category.output_no = 0
        if self.category.ft_output_amount >= 10e8:
            return Destination(PSBTAddressDetailsWarningView, view_args={"output_num": self.category.output_no})
        return Destination(PSBTFungibleTokenAddressDetailsView, view_args={"output_num": self.category.output_no})

class PSBTAddressDetailsWarningView(PSBTTokenView):
    def __init__(self, output_num=0):
        super().__init__()
        self.output_num = output_num
        self.category.output_no = output_num

    def run(self):

        category: Category = get_category(self.category.category_id)

        result = self.run_screen(
            WarningScreen,
            title=_("High Raw Amount"),
            show_back_button=True,
            status_headline=_(""),
            status_icon_name=SeedCashIconsConstants.WARNING,
            text=_(f"This transaction will send {self.category.ft_output_amount} {category.token_symbol}"),
            button_data=[ButtonOption("Confirm")],
            selected_color=category.icon_color
        )

        if result == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        return Destination(PSBTFungibleTokenAddressDetailsView, view_args={"output_num": self.category.output_no})

class PSBTFungibleTokenAddressDetailsView(PSBTTokenView):
    def __init__(self, output_num=0):
        super().__init__()
        self.output_num = output_num
        self.category.output_no = output_num

    def run(self):

        from seedcash.gui.screens.psbt_screens import PSBTAddressDetailsScreen
        selected_menu_num = self.run_screen(
            PSBTAddressDetailsScreen,
            title=f"Will Send (#{self.category.output_no + 1})",
            button_data=[ButtonOption("Next" if self.category.is_last_output else "Next Recipient")],
            address=self.category.address,
            amount=self.category.ft_output_amount,
            category=get_category(self.category.category_id),
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if self.category.next_output:
            if self.category.ft_output_amount >= 10e8:
                return Destination(PSBTAddressDetailsWarningView, view_args={"output_num": self.category.output_no})
            return Destination(PSBTFungibleTokenAddressDetailsView, view_args={"output_num": self.category.output_no})


        return self.next_category()

# NFT Views
class PSBTMintingNFTWarningView(PSBTTokenView):
    def run(self):
        result = self.run_screen(
            WarningScreen,
            title=_("Minting Non-Fungible Token(s)"),
            show_back_button=True,
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Are you sure?"),
            text=_("Signing would allow transfer, modify any involved NFT(s)"),
            button_data=[ButtonOption("Confirm")],
            selected_color=GUIConstants.MUSD_BLUE,
        )

        if result == RET_CODE__BACK_BUTTON:
            return self.back()
        return Destination(PSBTTokenDetailsView)


class PSBTTokenDetailsView(PSBTTokenView):
    def run(self):

        category: Category = get_category(self.category.category_id)

        selected_menu_num = self.run_screen(
            PSBTNFTScreen,
            button_data=[ButtonOption("Next")],
            selected_color=category.icon_color,
            category_id=self.category.category_id,
            is_ft=self.category.is_ft,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return self.back()

        if self.category.is_ft:
            if self.category.ft_inputs_total_amount >= 10e6:
                return Destination(PSBTFTHighRawAmountWarningsView)
            return Destination(PSBTFungibleTokenDetailsView)

        return Destination(PSBTNFTDetailsView, view_args={"output_num": 0})


class PSBTNFTDetailsView(PSBTTokenView):
    def __init__(self, output_num=0):
        super().__init__()
        self.output_num = output_num
        self.category.nft_detail_no = output_num

    def run(self):

        from seedcash.gui.screens.psbt_screens import PSBTNFTDetailsScreen
        selected_menu_num = self.run_screen(
            PSBTNFTDetailsScreen,
            button_data=[ButtonOption("Next")],
            selected_color=GUIConstants.MUSD_BLUE,
            output_num=self.category.nft_detail_no + 1,
            nft_commitment=self.category.nft_commitment,
            nft_capability=self.category.nft_capability,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if self.category.next_nft_detail:
            return Destination(PSBTNFTDetailsView, view_args={"output_num": self.category.nft_detail_no})

        return Destination(PSBTNFTAddressDetailsView, view_args={"output_num": 0})

class PSBTNFTAddressDetailsView(PSBTTokenView):
    def __init__(self, output_num=0):
        super().__init__()
        self.output_num = output_num
        self.category.output_no = output_num

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTNFTAddressScreen

        selected_menu_num = self.run_screen(
            PSBTNFTAddressScreen,
            button_data=[ButtonOption("Next")],
            selected_color=GUIConstants.MUSD_BLUE,
            destination_addr=self.category.address,
            index=self.category.output_no + 1
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if self.category.next_output:
            return Destination(PSBTNFTAddressDetailsView, view_args={"output_num": self.category.output_no})

        return self.next_category()

# BCH
class BCHPSBTOverviewView(View):
    def __init__(self, is_last=False):
        super().__init__()
        self.loading_screen = None
        self.is_last = is_last
        self.parser = self.controller.psbt_parser

    def run(self):

        # Run the overview screen
        selected_menu_num = self.run_screen(
            PSBTOverviewScreen,
            inputs_amount=self.parser.input_amount,
            fee_amount=self.parser.fee_amount,
            input_count=self.parser.input_count,
            destination_addresses=[output.address for output in self.parser.outputs],
            category=None,
            has_op_return=self.parser.has_op_return,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            if self.is_last:
                return Destination(PSBTDiscardWarningView)
            return Destination(BackStackView)

        return Destination(PSBTMathView)

class PSBTMathView(View):
    def __init__(self):
        super().__init__()
        self.parser = self.controller.psbt_parser
    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTMathScreen



        selected_menu_num = self.run_screen(
            PSBTMathScreen,
            input_amount=self.parser.total_input_amount,
            input_count=self.parser.input_count,
            spend_amount=self.parser.total_output_amount,
            output_count=self.parser.output_count,
            fee_amount=self.parser.fee_amount,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if len(self.parser.outputs) > 0:
            return Destination(PSBTAddressDetailsView)
        if self.parser.has_op_return:
            return Destination(PSBTOpReturnView)
        if self.parser.has_p2pk:
            return Destination(PSBTP2PKView)
        return Destination(PSBTConfirmationView)

class PSBTAddressDetailsView(View):
    def __init__(self, output_num: int = 0):
        super().__init__()
        self.output_num = output_num
        self.outputs = self.controller.psbt_parser.outputs

    def run(self):

        from seedcash.gui.screens.psbt_screens import PSBTAddressDetailsScreen
        selected_menu_num = self.run_screen(
            PSBTAddressDetailsScreen,
            title=f"Will Send (#{self.output_num + 1})",
            button_data=[ButtonOption("Next Recipient" if self.output_num < len(self.outputs) - 1 else "Next")],
            address=self.outputs[self.output_num].address,
            amount=self.outputs[self.output_num].value_satoshis,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if self.output_num < len(self.outputs) - 1:
            return Destination(
                PSBTAddressDetailsView,
                view_args={"output_num": self.output_num + 1}
            )

        elif self.controller.psbt_parser.has_op_return:
            return Destination(PSBTOpReturnView, view_args={"output_num": 0})
        elif self.controller.psbt_parser.has_p2pk:
            return Destination(PSBTP2PKView, view_args={"output_num": 0})

        return Destination(PSBTConfirmationView)

class PSBTOpReturnView(View):
    """
    Shows the OP_RETURN data
    """
    def __init__(self, output_num: int = 0):
        super().__init__()
        self.output_num = output_num
        self.outputs:List[TxOutput] = self.controller.psbt_parser.op_return_outputs

    def run(self):


        try:
            review_text = self.outputs[self.output_num].op_return_text
        except Exception as e:
            review_text = _("Unable to decode OP_RETURN data. It may not be valid UTF-8 text.")

        from seedcash.gui.screens.psbt_screens import PSBTCardTextScreen
        selected_menu_num = self.run_screen(
            PSBTCardTextScreen,
            title=_("OP_RETURN"),
            button_data=[ButtonOption("Next")],
            text=review_text,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif self.output_num < len(self.outputs) - 1:
            return Destination(PSBTOpReturnView, view_args={"output_num": self.output_num + 1})
        elif self.controller.psbt_parser.has_p2pk:
            return Destination(PSBTP2PKView, view_args={"output_num": 0})

        return Destination(PSBTConfirmationView)

class PSBTP2PKView(View):
    """
    Shows the P2PK data
    """
    def __init__(self, output_num: int = 0):
        super().__init__()
        self.output_num = output_num
        self.outputs = self.controller.psbt_parser.p2pk_outputs

    def run(self):

        from seedcash.gui.screens.psbt_screens import PSBTCardTextScreen
        selected_menu_num = self.run_screen(
            PSBTCardTextScreen,
            title=_("P2PK"),
            button_data=[ButtonOption("Next")],
            text=self.outputs[self.output_num].full_script.hex(),
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if self.output_num < len(self.outputs) - 1:
            return Destination(PSBTP2PKView, view_args={"output_num": self.output_num + 1})
        return Destination(PSBTConfirmationView)

class PSBTConfirmationView(View):
    """
    Shows the user a confirmation screen before signing the PSBT.
    """
    SIGN_PSBT = ButtonOption("Sign PSBT")
    DELETE_PSBT = ButtonOption("Delete PSBT")


    def run(self):

        from seedcash.gui.screens.psbt_screens import PSBTFinalizeScreen
        selected_menu_num = self.run_screen(
            PSBTFinalizeScreen,
            button_data=[self.SIGN_PSBT, self.DELETE_PSBT],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if selected_menu_num == 0:
            try:
                self.controller.psbt_bytes = self.controller.storage.wallet.sign_psbt(self.controller.psbt_parser)
            except Exception as e:
                return Destination(PSBTSigningErrorView)
            return Destination(PSBTSignedQRDisplayView)
        elif selected_menu_num == 1:
            self.controller.discard_psbt()
            return Destination(WalletOptionsView, clear_history=True)

# Signing Error View
class PSBTSigningErrorView(View):
    DISCARD_PSBT = ButtonOption("Discard PSBT")

    def run(self):
        psbt_parser: PSBTParser = self.controller.psbt_parser
        if not psbt_parser:
            return Destination(WalletOptionsView, clear_history=True)

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

        return Destination(WalletOptionsView, clear_history=True)

# Discard PSBT Warning
class PSBTDiscardWarningView(View):
    DISCARD_PSBT = ButtonOption("Discard PSBT")

    def run(self):
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Discard PSBT"),
            show_back_button=True,
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Are you sure?"),
            text=_("Discarding this PSBT will remove it from memory and cannot be undone."),
            button_data=[self.DISCARD_PSBT],
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if selected_menu_num == 0:
            self.controller.discard_psbt()
            return Destination(WalletOptionsView, clear_history=True)

class PSBTParsingErrorView(View):
    def run(self):
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("PSBT Error"),
            status_icon_name=SeedCashIconsConstants.WARNING,
            status_headline=_("Parsing Failed"),
            text=_("The PSBT could not be parsed. Please check the PSBT data and try again."),
            button_data=[ButtonOption("Back to Wallet")],
        )

        if selected_menu_num == 0:
            return Destination(WalletOptionsView, clear_history=True)

