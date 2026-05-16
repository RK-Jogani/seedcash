import time
from gettext import gettext as _
from seedcash.gui.screens import RET_CODE__BACK_BUTTON
from seedcash.views.view import View, Destination, BackStackView
from seedcash.gui.screens.psbt_screens import PSBTOverviewScreen


class PSBTOverviewView(View):
    def __init__(self):
        super().__init__()

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
                'address': 'bc1q............', 
                'amount': 397621401, 
                'fingerprint': ['22bde1a9', '73c5da0a'], 
                'derivation_path': ['m/48h/1h/0h/2h/1/0', 'm/48h/1h/0h/2h/1/0']
            }, {},
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

