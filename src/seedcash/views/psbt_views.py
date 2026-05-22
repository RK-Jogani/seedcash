import time
from gettext import gettext as _
from seedcash.gui.components import SeedCashIconsConstants
from seedcash.gui.screens import RET_CODE__BACK_BUTTON
from seedcash.gui.screens.screen import (
    ButtonOption,
    DireWarningScreen,
    QRDisplayScreen,
    WarningScreen,
)
from seedcash.models import psbt_parser
from seedcash.models.psbt_parser import PSBTParser
from seedcash.models.settings_definition import SettingsConstants
from seedcash.views.view import (
    MainMenuView,
    NotYetImplementedView,
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

        change_data = [
            {
                "address": "bc1q............",
                "amount": 397621401,
                "fingerprint": ["22bde1a9", "73c5da0a"],
                "derivation_path": ["m/48h/1h/0h/2h/1/0", "m/48h/1h/0h/2h/1/0"],
            },
            {},
        ]

        num_change_outputs = 0
        num_self_transfer_outputs = 0
        for change_output in change_data:
            # print(f"""{change_output["derivation_path"][0]}""")
            if change_output["derivation_path"][0].split("/")[-2] == "1":
                num_change_outputs += 1
            else:
                num_self_transfer_outputs += 1

        # Everything is set. Stop the loading screen
        if self.loading_screen:
            self.loading_screen.stop()

        # Run the overview screen
        selected_menu_num = self.run_screen(
            PSBTOverviewScreen,
            spend_amount=psbt_parser.spend_amount,
            change_amount=psbt_parser.change_amount,
            fee_amount=psbt_parser.fee_amount,
            num_inputs=psbt_parser.num_inputs,
            num_self_transfer_outputs=num_self_transfer_outputs,
            num_change_outputs=num_change_outputs,
            destination_addresses=psbt_parser.destination_addresses,
            has_op_return=psbt_parser.op_return_data is not None,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            self.controller.psbt_seed = None
            return Destination(BackStackView)

        # expecting p2sh (legacy multisig) and p2pkh to have no policy set
        # skip change warning and psbt math view
        if psbt_parser.policy == None:
            return Destination(PSBTUnsupportedScriptTypeWarningView)

        elif psbt_parser.change_amount == 0:
            return Destination(PSBTNoChangeWarningView)

        else:
            return Destination(PSBTMathView)


class PSBTUnsupportedScriptTypeWarningView(View):
    def run(self):
        selected_menu_num = WarningScreen(
            status_headline=_("Unsupported Script Type!"),
            text=_(
                "PSBT has unsupported input script type, please verify your change addresses."
            ),
            button_data=[ButtonOption("Continue")],
        ).display()

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        # Only one exit point
        # skip PSBTMathView
        return Destination(
            PSBTAddressDetailsView,
            view_args={"address_num": 0},
            skip_current_view=True,  # Prevent going BACK to WarningViews
        )


class PSBTNoChangeWarningView(View):
    def run(self):
        selected_menu_num = WarningScreen(
            # TRANSLATOR_NOTE: User will receive no change back; the inputs to this transaction are fully spent
            status_headline=_("Full Spend!"),
            text=_(
                "This PSBT spends its entire input value. No change is coming back to your wallet."
            ),
            button_data=[ButtonOption("Continue")],
        ).display()

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        # Only one exit point
        return Destination(
            PSBTMathView,
            skip_current_view=True,  # Prevent going BACK to WarningViews
        )


class PSBTMathView(View):
    """
    Follows the Overview pictogram. Shows:
    + total input value
    - recipients' value
    - fees
    -------------------
    + change value
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
            num_recipients=psbt_parser.num_destinations,
            fee_amount=psbt_parser.fee_amount,
            change_amount=psbt_parser.change_amount,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if len(psbt_parser.destination_addresses) > 0:
            return Destination(PSBTAddressDetailsView, view_args={"address_num": 0})
        else:
            # This is a self-transfer
            return Destination(
                PSBTChangeDetailsView, view_args={"change_address_num": 0}
            )


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

        elif psbt_parser.change_amount > 0:
            # Move on to display change
            return Destination(
                PSBTChangeDetailsView, view_args={"change_address_num": 0}
            )

        elif psbt_parser.op_return_data:
            return Destination(PSBTOpReturnView)

        else:
            # There's no change output to verify. Move on to sign the PSBT.
            return Destination(PSBTFinalizeView)


class PSBTChangeDetailsView(View):
    NEXT = ButtonOption("Next")
    SKIP_VERIFICATION = ButtonOption("Skip Verification")
    VERIFY_MULTISIG = ButtonOption("Verify Multisig Change")

    def __init__(self, change_address_num):
        super().__init__()
        self.change_address_num = change_address_num

    def run(self):
        from seedcash.gui.screens.psbt_screens import PSBTChangeDetailsScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser

        if not psbt_parser:
            # Should not be able to get here
            return Destination(MainMenuView)

        # Can we verify this change addr?
        change_data = psbt_parser.get_change_data(change_num=self.change_address_num)
        """
            change_data:
            {
                'address': 'bc1q............', 
                'amount': 397621401, 
                'fingerprint': ['22bde1a9', '73c5da0a'], 
                'derivation_path': ['m/48h/1h/0h/2h/1/0', 'm/48h/1h/0h/2h/1/0']
            }
        """

        # Single-sig verification is easy. We expect to find a single fingerprint
        # and derivation path.
        seed_fingerprint = self.controller._storage._wallet._fingerprint

        if seed_fingerprint not in change_data.get("fingerprint"):
            # TODO: Something is wrong with this psbt(?). Reroute to warning?
            return Destination(NotYetImplementedView)

        i = change_data.get("fingerprint").index(seed_fingerprint)
        derivation_path = change_data.get("derivation_path")[i]

        # 'm/84h/1h/0h/1/0' would be a change addr while 'm/84h/1h/0h/0/0' is a self-receive
        is_change_derivation_path = int(derivation_path.split("/")[-2]) == 1
        derivation_path_addr_index = int(derivation_path.split("/")[-1])

        if is_change_derivation_path:
            # TRANSLATOR_NOTE: The amount you're receiving back from the transaction
            title = _("Your Change")
        else:
            title = _("Self-Transfer")
            self.VERIFY_MULTISIG.button_label = _("Verify Multisig Addr")
        # if psbt_parser.num_change_outputs > 1:
        #     title += f" (#{self.change_address_num + 1})"

        is_change_addr_verified = False
        if psbt_parser.is_multisig:
            # if the known-good multisig descriptor is already onboard:
            if self.controller.multisig_wallet_descriptor:
                is_change_addr_verified = psbt_parser.verify_multisig_output(
                    self.controller.multisig_wallet_descriptor,
                    change_num=self.change_address_num,
                )
                button_data = [self.NEXT]

            else:
                # Have the Screen offer to load in the multisig descriptor.
                button_data = [self.VERIFY_MULTISIG, self.SKIP_VERIFICATION]

        else:
            # Single sig
            try:
                from embit import script
                from embit.networks import NETWORKS

                if is_change_derivation_path:
                    loading_screen_text = _("Verifying Change...")
                else:
                    loading_screen_text = _("Verifying Self-Transfer...")
                from seedcash.gui.screens.screen import LoadingScreenThread

                loading_screen = LoadingScreenThread(text=loading_screen_text)
                loading_screen.start()

                # convert change address to script pubkey to get script type
                pubkey = script.address_to_scriptpubkey(change_data["address"])
                script_type = pubkey.script_type()

                # extract derivation path to get wallet and change derivation
                change_path = "/".join(derivation_path.split("/")[-2:])
                wallet_path = "/".join(derivation_path.split("/")[:-2])

                xpub = self.controller._storage._wallet._xpub

                # take script type and call script method to generate address from seed / derivation
                xpub_key = xpub.derive(change_path).key
                network = self.settings.get_value(SettingsConstants.SETTING__NETWORK)
                scriptcall = getattr(script, script_type)
                if script_type == "p2sh":
                    # single sig only so p2sh is always p2sh-p2wpkh
                    calc_address = script.p2sh(script.p2wpkh(xpub_key)).address(
                        network=NETWORKS[
                            SettingsConstants.map_network_to_embit(network)
                        ]
                    )
                else:
                    # single sig so this handles p2wpkh and p2wpkh (and p2tr in the future)
                    calc_address = scriptcall(xpub_key).address(
                        network=NETWORKS[
                            SettingsConstants.map_network_to_embit(network)
                        ]
                    )

                if change_data["address"] == calc_address:
                    is_change_addr_verified = True
                    button_data = [self.NEXT]

            finally:
                loading_screen.stop()

        if is_change_addr_verified == False and (
            not psbt_parser.is_multisig
            or self.controller.multisig_wallet_descriptor is not None
        ):
            return Destination(
                PSBTAddressVerificationFailedView,
                view_args=dict(
                    is_change=is_change_derivation_path,
                    is_multisig=psbt_parser.is_multisig,
                ),
                clear_history=True,
            )

        selected_menu_num = self.run_screen(
            PSBTChangeDetailsScreen,
            title=title,
            button_data=button_data,
            address=change_data.get("address"),
            amount=change_data.get("amount"),
            is_multisig=psbt_parser.is_multisig,
            fingerprint=seed_fingerprint,
            derivation_path=derivation_path,
            is_change_derivation_path=is_change_derivation_path,
            derivation_path_addr_index=derivation_path_addr_index,
            is_change_addr_verified=is_change_addr_verified,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        elif (
            button_data[selected_menu_num] == self.NEXT
            or button_data[selected_menu_num] == self.SKIP_VERIFICATION
        ):
            if self.change_address_num < psbt_parser.num_change_outputs - 1:
                return Destination(
                    PSBTChangeDetailsView,
                    view_args={"change_address_num": self.change_address_num + 1},
                )

            elif psbt_parser.op_return_data:
                return Destination(PSBTOpReturnView)

            else:
                # There's no more change to verify. Move on to sign the PSBT.
                return Destination(PSBTFinalizeView)

        elif button_data[selected_menu_num] == self.VERIFY_MULTISIG:
            from seedcash.controller import Controller
            from seedcash.views.seed_views import LoadMultisigWalletDescriptorView

            self.controller.resume_main_flow = Controller.FLOW__PSBT
            return Destination(LoadMultisigWalletDescriptorView)


class PSBTAddressVerificationFailedView(View):
    def __init__(self, is_change: bool = True, is_multisig: bool = False):
        super().__init__()
        self.is_change = is_change
        self.is_multisig = is_multisig

    def run(self):
        if self.is_multisig:
            # TRANSLATOR_NOTE: Variable is either "change" or "self-transfer".
            text = _(
                "PSBT's {} address could not be verified from wallet descriptor."
            ).format(_("change") if self.is_change else _("self-transfer"))
        else:
            # TRANSLATOR_NOTE: Variable is either "change" or "self-transfer".
            text = _("PSBT's {} address could not be generated from your seed.").format(
                _("change") if self.is_change else _("self-transfer")
            )

        DireWarningScreen(
            title=_("Suspicious PSBT"),
            status_headline=_("Address Verification Failed"),
            text=text,
            button_data=[ButtonOption("Discard PSBT")],
            show_back_button=False,
        ).display()

        # We're done with this PSBT. Route back to MainMenuView which always
        #   clears all ephemeral data (except in-memory seeds).
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

        return Destination(PSBTFinalizeView)


class PSBTFinalizeView(View):
    """ """

    APPROVE_PSBT = ButtonOption("Approve PSBT")

    def run(self):
        from embit.psbt import PSBT
        from seedcash.gui.screens.psbt_screens import PSBTFinalizeScreen

        psbt_parser: PSBTParser = self.controller.psbt_parser
        psbt: PSBT = self.controller.psbt

        if not psbt_parser:
            # Should not be able to get here
            return Destination(MainMenuView)

        selected_menu_num = self.run_screen(
            PSBTFinalizeScreen, button_data=[self.APPROVE_PSBT]
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        else:
            # Sign PSBT
            sig_cnt = PSBTParser.sig_count(psbt)
            psbt.sign_with(psbt_parser.root)
            trimmed_psbt = PSBTParser.trim(psbt)

            if sig_cnt == PSBTParser.sig_count(trimmed_psbt):
                # Signing failed / didn't do anything
                # TODO: Reserved for Nick. Are there different failure scenarios that we can detect?
                # Would be nice to alter the message on the next screen w/more detail.
                return Destination(PSBTSigningErrorView)

            else:
                self.controller.psbt = trimmed_psbt
                return Destination(PSBTSignedQRDisplayView)


class PSBTSignedQRDisplayView(View):
    def run(self):
        from seedcash.models.encode_qr import UrPsbtQrEncoder

        qr_encoder = UrPsbtQrEncoder(
            psbt=self.controller.psbt,
            qr_density=self.settings.get_value(SettingsConstants.SETTING__QR_DENSITY),
        )
        self.run_screen(QRDisplayScreen, qr_encoder=qr_encoder)

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
