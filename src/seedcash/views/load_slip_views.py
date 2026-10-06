from gettext import gettext as _
from seedcash.gui.components import SeedCashIconsConstants
from seedcash.gui.screens.load_seed_screens import SeedMnemonicEntryScreen
from seedcash.gui.screens.screen import (
    RET_CODE__BACK_BUTTON,
    DireWarningScreen,
    WarningScreen,
)

from seedcash.views.view import (
    BackStackView,
    View,
    Destination,
    ButtonOption,
    MainMenuView,
)

from seedcash.gui.screens.slip_screens import (
    GroupShareListScreen,
    VisualLoadedSchemeScreen,
    SingleLevelVisualLoadedSchemeScreen,
)


class SeedSlipMnemonicEntryView(View):
    """
    View for entering a Slip39 seed phrase.
    """

    def __init__(self, cur_word_index: int = 0):
        super().__init__()
        self.cur_word_index = cur_word_index
        self.cur_word = self.controller.storage.get_mnemonic_word(cur_word_index)

    def run(self):
        ret = self.run_screen(
            SeedMnemonicEntryScreen,
            title=f"Seed Word #{self.cur_word_index + 1}",
            initial_letters=list(self.cur_word) if self.cur_word else ["a"],
            wordlist=self.controller.storage.get_wordlist,
        )

        if ret == RET_CODE__BACK_BUTTON:
            # remove the cur_word
            self.controller.storage.update_mnemonic(None, self.cur_word_index)

            if (
                self.cur_word_index == 0
                and self.controller.storage.mnemonic
                != [None] * self.controller.storage.mnemonic_length
            ):
                return Destination(SeedShareDiscardView, skip_current_view=True)

            return Destination(BackStackView)

        # ret will be our new mnemonic word
        self.controller.storage.update_mnemonic(ret, self.cur_word_index)

        if self.cur_word_index < (self.controller.storage.mnemonic_length - 1):
            return Destination(
                SeedSlipMnemonicEntryView,
                view_args={
                    "cur_word_index": self.cur_word_index + 1,
                },
            )
        else:
            # Display the seed words for confirmation
            from seedcash.gui.screens.load_seed_screens import SeedCashSeedWordsScreen

            confirm = self.run_screen(
                SeedCashSeedWordsScreen,
                seed_words=self.controller.storage.mnemonic,
            )

            if confirm == "CONFIRM":
                try:
                    self.controller.storage.add_share_to_scheme()
                    self.controller.storage.discard_mnemonic()
                except Exception as e:
                    return Destination(
                        SeedShareInvalidView
                    )
                finally:
                    for _ in range(self.controller.storage.mnemonic_length):
                        self.controller.back_stack.pop()

                if self.controller.storage._scheme.is_single_level():
                    return Destination(VisualLoadedSchemeView, view_args={"is_single_level": True})

                return Destination(VisualLoadedSchemeView)

class VisualLoadedSchemeView(View):
    """
    View to display the loaded scheme.
    """

    def __init__(self, is_single_level: bool = False):
        super().__init__()
        self.is_single_level = is_single_level

        # Ensure the scheme is loaded
        if not self.controller.storage.scheme:
            raise ValueError("No scheme loaded. Please load a scheme first.")

    def run(self):
        """
        Run the view to display the loaded scheme.
        """

        if self.controller.storage.scheme.is_complete():
            self.controller.storage.create_wallet()
            from seedcash.views.wallet_views import WalletFinalizeView
            return Destination(WalletFinalizeView)

        # Display the seed words for confirmation
        if self.is_single_level:
            self.shares_count, self.member_threshold = self.controller.storage.scheme.get_group_info(0)
            ret = self.run_screen(
                SingleLevelVisualLoadedSchemeScreen,
                title="Shares Scheme",
                shares_count=self.shares_count,
                member_threshold=self.member_threshold,
                show_back_button=False,
            )
        else:
            ret = self.run_screen(
                VisualLoadedSchemeScreen,
                scheme=self.controller.storage._scheme,
                show_back_button=False,
            )

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(DiscardSchemeView)
        elif ret == "REVIEW":
            return Destination(
                ReviewLoadedSchemeView, view_args={"are_shares": False, "is_single_level": self.is_single_level}
            )
        elif ret == "ADD":
            return Destination(
                SeedSlipMnemonicEntryView, view_args={"cur_word_index": 0}
            )

class ReviewLoadedSchemeView(View):
    """
    View to display the list of groups.
    """

    def __init__(
        self,
        group_index: int = 0,
        are_shares: bool = False,
        is_single_level: bool = False,
    ):
        super().__init__()
        self.group_index = group_index
        self.are_shares = are_shares or is_single_level
        if self.are_shares:
            if is_single_level:
                self.text = "Shares"
            else:
                self.text = f"Group {self.group_index}"
        else:
            self.text = "Groups"

        if self.are_shares:
            self.shares = self.controller.storage.scheme.get_shares_indices_of_group(
                self.group_index
            )
            # create button options for each share
            self.button_data = [ButtonOption(f"Share {i}") for i in self.shares]
        else:
            self.groups = self.controller.storage.scheme.get_group_indices()

            # create button options for each group
            self.button_data = [ButtonOption(f"Group {i}") for i in self.groups]

    def run(self):
        """
        Run the view to display the list of groups.
        """
        ret = self.run_screen(
            GroupShareListScreen,
            title=self.text,
            show_back_button=True,
            button_data=self.button_data,
        )

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if self.are_shares:
            from seedcash.views.generate_slip_views import ViewShareView

            return Destination(
                ViewShareView,
                view_args={
                    "group_index": self.group_index,
                    "share_index": self.shares[ret],
                },
            )

        else:
            # If not in view mode, proceed to share generation
            return Destination(
                ReviewLoadedSchemeView,
                view_args={
                    "group_index": self.groups[ret],
                    "are_shares": True,
                },
            )

class DiscardSchemeView(View):
    """
    View to discard the current scheme.
    """

    def run(self):
        """
        Run the view to discard the current scheme.
        """
        ret = self.run_screen(
            DireWarningScreen,
            text="Discard Scheme",
            button_data=[
                ButtonOption("Keep Scheme"),
                ButtonOption("Discard", icon_color="red"),
            ],
        )

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if ret == 0:
            if self.controller.storage.scheme.is_single_level():
                return Destination(VisualLoadedSchemeView, view_args={"is_single_level": True})
            return Destination(VisualLoadedSchemeView)

        # Discard current scheme
        self.controller.storage.discard_wallet()
        return Destination(MainMenuView)

class SeedShareInvalidView(View):
    EDIT = ButtonOption("Review & Edit")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def __init__(self):
        super().__init__()

    def run(self):
        button_data = [self.EDIT, self.DISCARD]
        selected_menu_num = self.run_screen(
            DireWarningScreen,
            title=_("Invalid Share!"),
            status_icon_name=SeedCashIconsConstants.ERROR,
            status_headline=None,
            text=_("The share you entered is invalid. Please review and edit the share or discard it."),
            show_back_button=False,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(
                SeedSlipMnemonicEntryView,
                view_args={"cur_word_index": 0},
                skip_current_view=True,
            )

        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.storage.discard_mnemonic()
            return Destination(BackStackView)

class SeedShareDiscardView(View):
    EDIT = ButtonOption("Review & Edit")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def __init__(self):
        super().__init__()
        self.mnemonic: list[str] = self.controller.storage.mnemonic

    def run(self):
        button_data = [self.EDIT, self.DISCARD]
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Discard Share!"),
            status_icon_name=SeedCashIconsConstants.ERROR,
            status_headline=None,
            text=_("Are you sure you want to discard this share?"),
            show_back_button=False,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(
                SeedSlipMnemonicEntryView,
                view_args={"cur_word_index": 0},
                skip_current_view=True,
            )

        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.storage.discard_mnemonic()
            return Destination(BackStackView)

class Slip39SeedViewView(View):
    """
    View to display the list of groups.
    """

    def __init__(self):
        super().__init__()
        self.fingerprint: str = None
        self.groups = self.controller.storage.scheme.groups
        self.group_indices = sorted(self.groups)
        
        # create button options for each group
        self.button_data = [ButtonOption(f"Group {i}") for i in self.group_indices]

        if self.controller.storage.scheme:
            self.fingerprint = self.controller.storage._scheme._wallet.fingerprint

    def run(self):
        """
        Run the view to display the list of groups.
        """

        ret = self.run_screen(
            GroupShareListScreen,
            title=("Groups"),
            fingerprint=self.fingerprint,
            button_data=self.button_data,
            show_back_button=True,
        )

        if ret == RET_CODE__BACK_BUTTON:
            from seedcash.views.wallet_views import ViewSeedView
            return Destination(ViewSeedView, view_args={"index": 1 if self.controller.storage.passphrase else 0}, skip_current_view=True)
        
        from seedcash.views.generate_slip_views import ListOfSharesView
        return Destination(ListOfSharesView, view_args={"group_index": self.group_indices[ret]})
