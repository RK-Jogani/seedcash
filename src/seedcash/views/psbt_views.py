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
            is_ft = len(self.controller.psbt_parser.genesis.categories["ft"]) > 0
            return Destination(GenesisWarningView, view_args={"is_ft": is_ft}, skip_current_view=True)
        elif self.controller.psbt_parser.inputs.ft:
            return Destination(PSBTFungibleTokenDetailsView, skip_current_view=True, view_args={"is_last": True})
        elif self.controller.psbt_parser.inputs.nft:
            return Destination(PSBTNFTView, skip_current_view=True, view_args={"is_last": True})
        else:
            return Destination(BCHPSBTOverviewView, skip_current_view=True, view_args={"is_last": True})

# GENESIS View
class GenesisWarningView(View):
    def __init__(self, is_ft: bool = False):
        super().__init__()
        self.loading_screen = None
        self.is_ft = is_ft

    def run(self):
        if self.is_ft:
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

        else:
            result = self.run_screen(
                WarningScreen,
                title=_("Genesis Transaction"),
                show_back_button=True,
                status_icon_name=SeedCashIconsConstants.WARNING,
                status_headline=_("New Non-Fungible Token"),
                text=_("This transaction will create a new NFT category."),
                button_data=[ButtonOption("Confirm")],
                selected_color=GUIConstants.MUSD_BLUE
                )

        if result == RET_CODE__BACK_BUTTON:
            return Destination(PSBTDiscardWarningView)
        if result == 0:
            if self.is_ft:
                return Destination(PSBTGenesisFTDetailsView, view_args={"category_num": 0})
            else:
                return Destination(PSBTNFTView, view_args={"category_num": 0, "is_genesis": True})

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
    def __init__(self, category_num: int = 0, is_last: bool = False, warning: bool = True):
        super().__init__()
        self.loading_screen = None
        self.category_num = category_num
        self.is_last = is_last
        self.warning = warning
            
    def run(self):
        psbt_parser: PSBTParser = self.controller.psbt_parser
        if not psbt_parser:
            return Destination(MainMenuView, skip_current_view=True)
        category_id = self.controller.psbt_parser.inputs.get_ft_category_ids[self.category_num]
        category: Category = get_category(category_id)
        spend_amount = psbt_parser.inputs.get_ft_total_amount(category_id)
        is_ft_burned = psbt_parser.is_ft_burned(category_id)

        if self.warning:
            return Destination(
                PSBTFungibleWarningView, 
                view_args={
                    "category_num": self.category_num,
                    "is_ft_burned": is_ft_burned,
                    "spend_amount": spend_amount,
                    "category": category
                }, skip_current_view=True)

        outputs = psbt_parser.outputs.get_ft(category_id)

        selected_menu_num = self.run_screen(
            PSBTOverviewScreen,
            spend_amount=spend_amount,
            input_count=psbt_parser.inputs.get_ft_count(category_id),
            destination_addresses=[output.address for output in outputs],
            selected_color=category.icon_color,
            category=category
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            if self.is_last:
                return Destination(PSBTDiscardWarningView)
            return Destination(BackStackView)
        if selected_menu_num == 0:
            if len(outputs) == 0:
                return Destination(
                    PSBTFungibleTokenDetailsView,
                    view_args={"category_num": self.category_num + 1}
                )
            return Destination(PSBTAddressDetailsView, view_args={"output_num": 0, "outputs": outputs, "category_id": category_id, "category_num": self.category_num})

class PSBTFungibleWarningView(View):
    def __init__(self, 
                 category_num: int = 0, 
                 is_ft_burned: bool = False,
                 spend_amount: int = 0,
                 category: Category = None,
                 check_point: bool = True):
        super().__init__()
        self.category_num = category_num
        self.is_ft_burned = is_ft_burned
        self.spend_amount = spend_amount
        self.category = category
        self.check_point = check_point

    def run(self):

        if self.is_ft_burned and self.check_point:
            result = self.run_screen(
                WarningScreen,
                title=_("Burning Fungible Token(s)"),
                show_back_button=True,
                status_icon_name=SeedCashIconsConstants.WARNING,
                status_headline=_("Are you sure?"),
                text=_("At least one fungible token in the following category has been modified or burned."),
                button_data=[ButtonOption("Confirm")],
                selected_color=self.category.icon_color
            )
            if result == RET_CODE__BACK_BUTTON:
                return Destination(BackStackView)

        if self.category.token_symbol == "[?]":
            result = self.run_screen(
                WarningScreen,
                title=_("Unknown Token ID"),
                show_back_button=True,
                status_headline=_(""),
                status_icon_name=SeedCashIconsConstants.WARNING,
                text=_(f"Unknown token ID, No decimal conversion applied!"),
                button_data=[ButtonOption("Confirm")],
                selected_color=self.category.icon_color
            )
            if result == RET_CODE__BACK_BUTTON:
                return Destination(
                    PSBTFungibleWarningView,
                    view_args={
                        "category_num": self.category_num,
                        "is_ft_burned": self.is_ft_burned,
                        "spend_amount": self.spend_amount,
                        "category": self.category,
                    },
                    skip_current_view=True)
    
        if self.spend_amount >= 10e8:
            result = self.run_screen(
                WarningScreen,
                title=_("High Raw Amount"),
                show_back_button=True,
                status_headline=_(""),
                status_icon_name=SeedCashIconsConstants.WARNING,
                text=_(f"This transaction will send {self.spend_amount} {self.category.token_symbol}"),
                button_data=[ButtonOption("Confirm")],
                selected_color=self.category.icon_color
            )
            if result == RET_CODE__BACK_BUTTON:
                return Destination(
                    PSBTFungibleWarningView,
                    view_args={
                        "category_num": self.category_num,
                        "is_ft_burned": self.is_ft_burned,
                        "spend_amount": self.spend_amount,
                        "category": self.category,
                        "check_point": False
                    },
                    skip_current_view=True
                )
        
        return Destination(
            PSBTFungibleTokenDetailsView,
            view_args={"category_num": self.category_num, "warning": False},
            skip_current_view=True
        )

# NFT Details View
class PSBTNFTView(View):
    def __init__(self, category_num=0, is_genesis=False, is_last=False, warning=True):
            super().__init__()
            self.category_num = category_num
            self.is_genesis = is_genesis
            self.loading_screen = None
            self.is_last = is_last
            self.warning = warning
    
    def run(self):
        if self.is_genesis:
            nft_category_ids = self.controller.psbt_parser.genesis.inputs.get_nft_category_ids
            if nft_category_ids is not None or len(nft_category_ids) > 0:
                return Destination(GenesisWarningView, view_args={"is_ft": False}, skip_current_view=True)
        
        nft_category_ids = self.controller.psbt_parser.inputs.get_nft_category_ids

        if nft_category_ids is None or len(nft_category_ids) == 0:
            return Destination(BCHPSBTOverviewView, skip_current_view=True)
        
        category_id = nft_category_ids[self.category_num]

        if self.warning:
            is_minting = self.controller.psbt_parser.is_nft_minting(category_id)
            is_burning = self.controller.psbt_parser.is_nft_burned(category_id)
            return Destination(
                PSBTNFTWarningView,
                view_args={
                    "category_num": self.category_num,
                    "is_genesis": self.is_genesis,
                    "is_last": self.is_last,
                    "is_minting": is_minting,
                    "is_burning": is_burning
                },
                skip_current_view=True
            )

        from seedcash.gui.screens.psbt_screens import PSBTNFTScreen
        selected_menu_num = self.run_screen(
            PSBTNFTScreen,
            button_data=[ButtonOption("Next")],
            selected_color=GUIConstants.MUSD_BLUE,
            category_id=category_id,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            if self.is_last:
                return Destination(PSBTDiscardWarningView)
            return Destination(BackStackView)
        if selected_menu_num == 0:
            return Destination(PSBTNFTDetailsView, view_args={"category_num": self.category_num, "category_id": category_id, "is_genesis": self.is_genesis})

class PSBTNFTWarningView(View):
    def __init__(
            self,
            category_num=0,
            is_genesis=False,
            is_last=False,
            is_minting=False,
            is_burning=False):
        super().__init__()
        self.category_num = category_num
        self.is_genesis = is_genesis
        self.is_last = is_last
        self.is_minting = is_minting
        self.is_burning = is_burning

    def run(self):
        if self.is_minting:
            result = self.run_screen(
                WarningScreen,
                title=_("Minting NFT(s)"),
                show_back_button=True,
                status_icon_name=SeedCashIconsConstants.WARNING,
                status_headline=_("Are you sure?"),
                text=_("Signing would allow transfer, burn, or modify any involved NFT(s)"),
                button_data=[ButtonOption("Confirm")],
                selected_color=GUIConstants.MUSD_BLUE
            )
            if result == RET_CODE__BACK_BUTTON:
                return Destination(BackStackView)
            
        if self.is_burning:
            result = self.run_screen(
                WarningScreen,
                title=_("Burning NFT(s)"),
                show_back_button=True,
                status_icon_name=SeedCashIconsConstants.WARNING,
                status_headline=_("Are you sure?"),
                text=_("At least one NFT in the following category has been modified or burned."),
                button_data=[ButtonOption("Confirm")],
                selected_color=GUIConstants.MUSD_BLUE
            )

            if result == RET_CODE__BACK_BUTTON:
                return Destination(
                    PSBTNFTWarningView,
                    view_args={
                        "category_num": self.category_num,
                        "is_genesis": self.is_genesis,
                        "is_last": self.is_last,
                        "is_minting": self.is_minting,
                        "is_burning": self.is_burning,
                    },
                    skip_current_view=True
                )

        return Destination(
            PSBTNFTView,
            view_args={
                "category_num": self.category_num,
                "is_genesis": self.is_genesis,
                "is_last": self.is_last,
                "is_minting": self.is_minting,
                "is_burning": self.is_burning,
                "warning": False
            },
            skip_current_view=True
        )

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

        if not outputs or self.output_num >= len(outputs):
            return Destination(
                PSBTNFTView,
                view_args={
                    "category_num": self.category_num + 1,
                    "is_genesis": self.is_genesis},
                skip_current_view=True
            )
        
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
                return Destination(PSBTDiscardWarningView)
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

    def __init__(
            self,
            output_num: int = 0,
            outputs: List[TxOutput] = None,
            category_id: str = None, 
            category_num: int = 0,
            is_genesis: bool = False,
            warning: bool = True):

        super().__init__()

        if not outputs:
            raise ValueError("Outputs list cannot be empty")
        self.output_num = output_num
        self.outputs = outputs
        self.category_id = category_id
        self.category_num = category_num
        self.is_genesis = is_genesis
        self.warning = warning

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTAddressDetailsScreen

        # TRANSLATOR_NOTE: Future-tense used to indicate that this transaction will send this amount, as opposed to "Send" on its own which could be misread as an instant command (e.g. "Send Now").
        title = _("Will Send")
        if len(self.outputs) > 1:
            title += f" (#{self.output_num + 1})"
    
        if self.category_id is not None:
            category: Category = get_category(self.category_id)
            amount = self.outputs[self.output_num].token.ft_amount

            if self.warning and amount >= 10e8:
                return Destination(
                    PSBTAddressDetailsWarningView,
                    view_args={
                        "output_num": self.output_num,
                        "outputs": self.outputs,
                        "category_id": self.category_id,
                        "category_num": self.category_num,
                        "is_genesis": self.is_genesis,
                        "amount": amount,
                        "category": category
                    },
                    skip_current_view=True
                )
            
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
                if self.category_num < len(self.controller.psbt_parser.genesis.inputs.get_ft_category_ids) - 1:
                    return Destination(PSBTGenesisFTDetailsView, view_args={"category_num": self.category_num + 1})
                else:
                    return Destination(PSBTNFTView, view_args={"category_num": 0, "is_genesis": True})
            if self.category_num < len(self.controller.psbt_parser.inputs.get_ft_category_ids) - 1:
                return Destination(PSBTFungibleTokenDetailsView, view_args={"category_num": self.category_num + 1})    
            else:
                return Destination(PSBTNFTView, view_args={"category_num": 0})

        elif self.controller.psbt_parser.has_op_return:
            return Destination(PSBTOpReturnView, view_args={"output_num": 0})
        elif self.controller.psbt_parser.has_p2pk:
            return Destination(PSBTP2PKView, view_args={"output_num": 0})
        elif self.controller.psbt_parser.has_unknown_outputs:
            return Destination(PSBTUnknownOutputsView, view_args={"output_num": 0})
    
        return Destination(PSBTConfirmationView)

class PSBTAddressDetailsWarningView(View):
    def __init__(
            self,
            output_num: int = 0,
            outputs: List[TxOutput] = None,
            category_id: str = None, 
            category_num: int = 0,
            is_genesis: bool = False,
            amount: int = 0,
            category: Category = None):
        super().__init__()
        self.output_num = output_num
        self.outputs = outputs
        self.category_id = category_id
        self.category_num = category_num
        self.is_genesis = is_genesis
        self.amount = amount
        self.category = category

    def run(self):
        if self.amount >= 10e8:
            result = self.run_screen(
            WarningScreen,
            title=_("High Raw Amount"),
            show_back_button=True,
            status_headline=_(""),
            status_icon_name=SeedCashIconsConstants.WARNING,
            text=_(f"This transaction will send {self.amount} {self.category.token_symbol}"),
            button_data=[ButtonOption("Confirm")],
            selected_color=self.category.icon_color
        )

        if result == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        return Destination(
            PSBTAddressDetailsView,
            view_args={
                "output_num": self.output_num,
                "outputs": self.outputs,
                "category_id": self.category_id,
                "category_num": self.category_num,
                "is_genesis": self.is_genesis,
                "warning": False,
            }
        )

class PSBTOpReturnView(View):
    """
    Shows the OP_RETURN data
    """
    def __init__(self, output_num: int = 0):
        super().__init__()
        self.output_num = output_num

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTOpReturnScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser
        outputs:List[TxOutput] = psbt_parser.op_return_outputs

        if not psbt_parser:
            # Should not be able to get here
            raise Exception("Routing error")

        title = _("OP_RETURN")
        button_data = [ButtonOption("Next")]

        selected_menu_num = self.run_screen(
            PSBTOpReturnScreen,
            title=title,
            button_data=button_data,
            op_return_data=outputs[self.output_num].full_script,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif self.output_num < len(outputs) - 1:
            return Destination(
                PSBTOpReturnView, view_args={"output_num": self.output_num + 1}
            )
        elif psbt_parser.has_p2pk:
            return Destination(PSBTP2PKView, view_args={"output_num": 0})
        elif psbt_parser.has_unknown_outputs:
            return Destination(PSBTUnknownOutputsView, view_args={"output_num": 0})

        return Destination(PSBTConfirmationView)

class PSBTP2PKView(View):
    """
    Shows the P2PK data
    """
    def __init__(self, output_num: int = 0):
        super().__init__()
        self.output_num = output_num

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTOpReturnScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser
        outputs:List[TxOutput] = psbt_parser.p2pk_outputs

        if not psbt_parser:
            # Should not be able to get here
            raise Exception("Routing error")

        title = _("P2PK")
        button_data = [ButtonOption("Next")]

        selected_menu_num = self.run_screen(
            PSBTOpReturnScreen,
            title=title,
            button_data=button_data,
            op_return_data=outputs[self.output_num].full_script,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if self.output_num < len(outputs) - 1:
            return Destination(
                PSBTP2PKView, view_args={"output_num": self.output_num + 1}
            )
        if psbt_parser.has_unknown_outputs:
            return Destination(PSBTUnknownOutputsView, view_args={"output_num": 0})
        return Destination(PSBTConfirmationView)

class PSBTUnknownOutputsView(View):
    """
    Shows the Unknown Outputs data
    """
    def __init__(self, output_num: int = 0):
        super().__init__()
        self.output_num = output_num

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTOpReturnScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser
        outputs:List[TxOutput] = psbt_parser.unknown_outputs

        if not psbt_parser:
            # Should not be able to get here
            raise Exception("Routing error")

        title = _("Unknown Outputs")
        button_data = [ButtonOption("Next")]

        selected_menu_num = self.run_screen(
            PSBTOpReturnScreen,
            title=title,
            button_data=button_data,
            op_return_data=outputs[self.output_num].full_script,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if self.output_num < len(outputs) - 1:
            return Destination(
                PSBTUnknownOutputsView, view_args={"output_num": self.output_num + 1}
            )
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
                self.controller.psbt_bytes = self.controller._storage._wallet.sign_psbt(self.controller.psbt_parser)
            except Exception as e:
                return Destination(PSBTSigningErrorView)
            
            return Destination(PSBTSignedQRDisplayView)
        elif selected_menu_num == 1:
            self.controller.discard_psbt()
            return Destination(MainMenuView, clear_history=True)

# Signing Error View
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
            return Destination(MainMenuView, clear_history=True)