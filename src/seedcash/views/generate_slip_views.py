import logging

from gettext import gettext as _
from seedcash.gui.screens import load_seed_screens
from seedcash.gui.screens.load_seed_screens import SeedMnemonicEntryScreen
from seedcash.gui.screens.screen import (
    RET_CODE__BACK_BUTTON,
    RET_CODE__CHECK_BUTTON,
    DireWarningScreen,
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
)

logger = logging.getLogger(__name__)


# For Generating Slip39 Seed Views
class SeedSlipEntryView(View):
    """
    View for entering a Slip39 seed phrase.
    """

    def __init__(self):
        super().__init__()
        self.num_words = self.controller.storage.mnemonic_length

    def run(self):
        """
        Run the view to enter the Slip39 seed phrase.
        """
        from seedcash.gui.screens.slip_screens import SlipEntryScreen

        ret = self.run_screen(SlipEntryScreen, num_words=self.num_words)

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if len(ret) == 128 or len(ret) == 256:
            self.controller.storage.set_scheme_params(ret)
            return Destination(SeedSlipBitsView)


class SeedSlipBitsView(View):
    """
    View for entering a Slip39 seed phrase in bits.
    """

    def __init__(self):
        super().__init__()
        self.bits = self.controller.storage.scheme_params._bits

    def run(self):
        """
        Run the view to enter the Slip39 seed phrase in bits.
        """
        from seedcash.gui.screens.slip_screens import SlipBitsScreen

        ret = self.run_screen(SlipBitsScreen, bits=self.bits)

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if ret == "CONFIRM":
            return Destination(SeedSlipSchemeView)


class SeedSlipSchemeView(View):
    """
    View for displaying the Slip39 group scheme.
    """

    SINGLE_LEVEL = ButtonOption("Single Level Backup")
    TWO_LEVEL = ButtonOption("Two Level Backup")

    def __init__(self):
        super().__init__()

        self.button_data = [
            self.SINGLE_LEVEL,
            self.TWO_LEVEL,
        ]

    def run(self):
        """
        Run the view to display the Slip39 group scheme.
        """

        selected_menu_num = self.run_screen(
            GroupShareListScreen,
            button_data=self.button_data,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif self.button_data[selected_menu_num] == self.SINGLE_LEVEL:
            return Destination(VisualSharesView, view_args={"is_single_level": True})
        elif self.button_data[selected_menu_num] == self.TWO_LEVEL:
            return Destination(VisualGroupView)


class VisualGroupView(View):
    """
    View for visualizing the groups in a Slip39 scheme.
    """

    def __init__(self):
        super().__init__()
        self.groups = self.controller.storage.scheme_params._groups_length
        self.group_threshold = self.controller.storage.scheme_params._group_threshold

        logger.info(
            "VisualGroupView initialized with %d groups and threshold %d",
            self.groups,
            self.group_threshold,
        )

    def run(self):
        """
        Run the view to visualize the groups.
        """
        from seedcash.gui.screens.slip_screens import VisualGroupShareScreen

        # Show the visual group share screen
        result = self.run_screen(
            VisualGroupShareScreen,
            text="Groups",
            threshold=self.group_threshold,
            total_members=self.groups,
            passphrase=self.controller.storage.passphrase,
        )

        if result == RET_CODE__BACK_BUTTON:
            return Destination(DiscardGroupsView, skip_current_view=True)

        self.controller.storage.scheme_params.set_group_threshold(result[1])
        self.controller.storage.scheme_params.set_groups_length(result[2])

        logger.info(
            "Action: %d Group threshold set to %d and groups length set to %d",
            result[0],
            result[1],
            result[2],
        )

        if result[0] == "PASSPHRASE":
            return Destination(SchemeAddPassphraseView)
        elif result[0] == "CONFIRM":
            return Destination(ListOfGroupsView)


class ListOfGroupsView(View):
    """
    View to display the list of groups.
    """

    def __init__(self, is_view_mode: bool = False):
        super().__init__()
        self.is_view_mode = is_view_mode
        self.fingerprint: str = None

        self.groups = self.controller.storage.scheme_params._groups_length

        # create button options for each group
        self.button_data = [ButtonOption(f"Group {i}") for i in range(self.groups)]

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
            show_back_button=not self.is_view_mode,
            show_check_button=self.is_view_mode,
            button_data=self.button_data,
        )

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if ret == RET_CODE__CHECK_BUTTON:
            # If in view mode, finalize the groups
            if self.is_view_mode:
                self.controller.storage.discard_scheme()
                return Destination(MainMenuView)

            # If not in view mode, proceed to share generation
            return Destination(VisualSharesView, view_args={"group_index": 0})

        if self.is_view_mode:
            return Destination(ListOfSharesView, view_args={"group_index": ret})

        return Destination(VisualSharesView, view_args={"group_index": ret})


class VisualSharesView(View):
    threshold = 1
    total_members = 1

    def __init__(self, group_index=0, is_single_level=False):
        super().__init__()
        self.group_index = group_index
        self.is_single_level = is_single_level

        self.group = self.controller.storage.scheme_params.get_group_at(
            self.group_index
        )

        if self.group:
            self.threshold = self.group[0]
            self.total_members = self.group[1]

    def run(self):
        from seedcash.gui.screens.slip_screens import VisualGroupShareScreen

        result = self.run_screen(
            VisualGroupShareScreen,
            text="Shares",
            threshold=self.threshold,
            total_members=self.total_members,
            passphrase=(
                self.controller.storage.passphrase if self.is_single_level else None
            ),
        )

        if result == RET_CODE__BACK_BUTTON:
            return Destination(
                DiscardSharesView,
                view_args={
                    "group_index": self.group_index,
                    "is_single_level": self.is_single_level,
                },
                skip_current_view=True,
            )

        self.controller.storage.scheme_params.update_groups(
            self.group_index, (result[1], result[2])
        )

        if result[0] == "PASSPHRASE":
            return Destination(SchemeAddPassphraseView)

        if self.is_single_level:
            self.controller.storage.generate_scheme_with_params()
            return Destination(
                ListOfSharesView, view_args={"group_index": 0, "is_single_level": True}
            )

        if self.controller.storage.scheme_params.scheme_is_complete():
            self.controller.storage.generate_scheme_with_params()
            return Destination(ListOfGroupsView, view_args={"is_view_mode": True})

        return Destination(ListOfGroupsView, view_args={"is_view_mode": False})


class ListOfSharesView(View):
    """
    View to display the list of shares.
    """

    def __init__(self, group_index: int = 0, is_single_level: bool = False):
        super().__init__()
        self.group_index = group_index
        self.shares = self.controller.storage.scheme.get_shares_indices_of_group(
            group_index
        )
        logger.info("Shares in group %d: %s", group_index, self.shares)

        self.fingerprint = None
        if is_single_level:
            if self.controller.storage.scheme:
                self.fingerprint = self.controller.storage._scheme._wallet.fingerprint

        # create button options for each group
        self.button_data = [ButtonOption(f"Share {i}") for i in self.shares]

    def run(self):
        """
        Run the view to display the list of groups.
        """
        ret = self.run_screen(
            GroupShareListScreen,
            title=(f"Group {self.group_index}"),
            fingerprint=self.fingerprint,
            button_data=self.button_data,
            show_check_button=True if self.fingerprint else False,
            show_back_button=False if self.fingerprint else True,
        )

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if ret == RET_CODE__CHECK_BUTTON:
            # If not in view mode, proceed to mnemonic generation
            self.controller.storage.discard_scheme()
            return Destination(MainMenuView)

        share = self.controller.storage.scheme.get_mnemonics_share_of_group(
            ret, self.group_index
        )
        return Destination(MnemonicView, view_args={"words": share})


class MnemonicView(View):
    """
    View to display the mnemonic.
    """

    def __init__(self, words):
        super().__init__()
        self.words = words

    def run(self):
        """
        Run the view to display the mnemonic.
        """

        from seedcash.gui.screens.load_seed_screens import SeedCashSeedWordsScreen

        self.run_screen(SeedCashSeedWordsScreen, seed_words=self.words)

        return Destination(BackStackView)


class DiscardGroupsView(View):
    """
    View to discard the groups.
    """

    KEEP_GROUPS = ButtonOption("Keep")
    DISCARD_GROUPS = ButtonOption("Discard Groups", icon_color="red")

    def __init__(self):
        super().__init__()
        self.groups = self.controller.storage.scheme_params._groups_length
        self.group_threshold = self.controller.storage.scheme_params._group_threshold

        self.button_data = [
            self.KEEP_GROUPS,
            self.DISCARD_GROUPS,
        ]

    def run(self):
        """
        Run the view to discard the groups.
        """

        ret = self.run_screen(
            DireWarningScreen,
            text="Discard Groups Scheme",
            button_data=self.button_data,
        )

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if self.button_data[ret] == self.KEEP_GROUPS:
            # Keep groups scheme
            return Destination(VisualGroupView, skip_current_view=True)
        elif self.button_data[ret] == self.DISCARD_GROUPS:
            # Discard groups scheme
            self.controller.storage.set_passphrase("")
            self.controller.storage.scheme_params.discard_groups()
            return Destination(BackStackView)


class DiscardSharesView(View):
    """
    View to discard the shares.
    """

    KEEP_SHARE = ButtonOption("Keep")
    DISCARD_SHARE = ButtonOption("Discard Shares", icon_color="red")

    def __init__(self, group_index: int = 0, is_single_level: bool = False):
        super().__init__()
        self.group_index = group_index
        self.is_single_level = is_single_level

        self.button_data = [
            self.KEEP_SHARE,
            self.DISCARD_SHARE,
        ]

    def run(self):
        """
        Run the view to discard the shares.
        """

        ret = self.run_screen(
            DireWarningScreen,
            text="Discard Shares Scheme",
            button_data=self.button_data,
        )

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        if self.button_data[ret] == self.KEEP_SHARE:
            # Keep shares scheme
            return Destination(
                VisualSharesView,
                view_args={
                    "group_index": self.group_index,
                    "is_single_level": self.is_single_level,
                },
                skip_current_view=True,
            )
        elif self.button_data[ret] == self.DISCARD_SHARE:
            if self.is_single_level:
                # Discard single level shares scheme
                self.controller.storage.set_passphrase("")

            # Discard shares scheme
            self.controller.storage.scheme_params.update_groups(self.group_index, None)
            return Destination(BackStackView)


class SchemeFinalizeView(View):
    """
    View to finalize the scheme.
    """

    CONFIRM = ButtonOption("Confirm Scheme", icon_color="green")

    def run(self):
        """
        Run the view to finalize the scheme.
        """
        # If not complete, show a warning
        button_data = [
            self.CONFIRM,
        ]

        selected_menu_num = self.run_screen(
            load_seed_screens.SeedFinalizeScreen,
            fingerprint=(
                self.controller.storage._scheme._wallet.fingerprint
                if self.controller.storage._scheme
                else None
            ),
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.CONFIRM:
            if self.controller.storage.wallet:
                from seedcash.views.wallet_views import WalletOptionsView

                return Destination(WalletOptionsView)

            self.controller.storage.discard_mnemonic()
            return Destination(MainMenuView)

        return Destination(BackStackView)


class SchemeAddPassphraseView(View):
    """
    initial_keyboard: used by the screenshot generator to render each different keyboard layout.
    """

    def __init__(
        self,
        initial_keyboard: str = load_seed_screens.SeedAddPassphraseScreen.KEYBOARD__LOWERCASE_BUTTON_TEXT,
    ):
        super().__init__()
        self.initial_keyboard = initial_keyboard

    def run(self):
        ret_dict = self.run_screen(
            load_seed_screens.SeedAddPassphraseScreen,
            passphrase=self.controller.storage.passphrase,
            title="Enter Passphrase",
            initial_keyboard=self.initial_keyboard,
        )

        # The new passphrase will be the return value; it might be empty.
        self.controller.storage.set_passphrase(ret_dict["passphrase"])

        if len(self.controller.storage.passphrase) > 0:
            if "is_back_button" in ret_dict:
                return Destination(
                    SchemeAddPassphraseExitDialogView, skip_current_view=True
                )
            else:
                return Destination(SchemeReviewPassphraseView, skip_current_view=True)
        else:
            return Destination(BackStackView)


# Fifth Possible Load Seed View if the user wants to add a passphrase if BACK is pressed
class SchemeAddPassphraseExitDialogView(View):
    EDIT = ButtonOption("Edit passphrase")
    DISCARD = ButtonOption("Discard passphrase", button_label_color="red")

    def __init__(self):
        super().__init__()

    def run(self):
        button_data = [self.EDIT, self.DISCARD]

        from seedcash.gui.screens.screen import WarningScreen

        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Discard passphrase?"),
            status_headline=None,
            text=_("Your current passphrase entry will be erased"),
            show_back_button=False,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(SchemeAddPassphraseView, skip_current_view=True)

        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.storage.set_passphrase("")
            return Destination(BackStackView)


# Fifth Possible Load Seed View if the user wants to add a passphrase
class SchemeReviewPassphraseView(View):
    """
    Display the completed passphrase back to the user.
    """

    EDIT = ButtonOption("Edit passphrase")
    DONE = ButtonOption("Confirm")

    def __init__(self):
        super().__init__()

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
            return Destination(SchemeAddPassphraseView, skip_current_view=True)

        elif button_data[selected_menu_num] == self.DONE:
            if self.controller.storage.scheme:
                self.controller.storage.create_wallet()
                return Destination(SchemeFinalizeView)
            return Destination(BackStackView)
