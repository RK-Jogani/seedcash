from gettext import gettext as _
from seedcash.gui.screens import RET_CODE__BACK_BUTTON
from seedcash.views.view import (
    BackStackView,
    ErrorView,
    NotYetImplementedView,
    View,
    Destination,
)


class TestCamera(View):
    """
    Camera preview View that displays the live camera feed.

    This view simply shows the camera output without any QR code processing.
    """

    instructions_text = _("Camera Preview")

    def __init__(self):
        super().__init__()

    def run(self):
        from seedcash.gui.screens.scan_screens import ScanScreen

        # Start the live camera preview
        self.run_screen(
            ScanScreen,
            instructions_text=self.instructions_text,
        )

        # A long preview might have exceeded the screensaver timeout; ensure screensaver
        # doesn't immediately engage when we leave here.
        self.controller.reset_screensaver_timeout()

        # Return to main menu when camera preview is closed
        from seedcash.views.setting_views import SettingOptionsView

        return Destination(SettingOptionsView)


class ScanInvalidQRTypeView(View):
    """
    View to show when an invalid QR code is scanned in a scanning flow. Offers the
    user a chance to go back and try scanning again.
    """

    def __init__(self):
        super().__init__()

    def run(self):

        return Destination(
            ErrorView,
            view_args=dict(
                title="Error",
                status_headline=_("Invalid QR Code"),
                text=_(
                    "The scanned QR code was not recognized or is not yet supported."
                ),
                button_text="Back",
                next_destination=Destination(BackStackView, skip_current_view=True),
            ),
        )


class ScanView(View):
    """
    The catch-all generic scanning View that will accept any of our supported QR
    formats and will route to the most sensible next step.

    Can also be used as a base class for more specific scanning flows with
    dedicated errors when an unexpected QR type is scanned (e.g. Scan PSBT was
    selected but a SeedQR was scanned).
    """

    instructions_text = "Scan a QR code"
    invalid_qr_type_message = "QRCode not recognized or not yet supported."

    def __init__(self):
        from seedcash.models.decode_qr import DecodeQR

        super().__init__()
        # Define the decoder here to make it available to child classes' is_valid_qr_type
        # checks and so we can inject data into it in the test suite's `before_run()`.
        self.decoder: DecodeQR = DecodeQR()

    @property
    def is_valid_qr_type(self):
        return True

    def run(self):
        from seedcash.gui.screens.scan_screens import ScanScreen

        # Start the live preview and background QR reading
        scan_result = self.run_screen(
            ScanScreen, instructions_text=self.instructions_text, decoder=self.decoder
        )

        # A long scan might have exceeded the screensaver timeout; ensure screensaver
        # doesn't immediately engage when we leave here.
        self.controller.reset_screensaver_timeout()

        if scan_result in (False, RET_CODE__BACK_BUTTON):
            return Destination(BackStackView)

        # Handle the results
        if self.decoder.is_complete:
            if not self.is_valid_qr_type:
                # We recognized the QR type but it was not the type expected for the
                # current flow.
                # Report QR types in more human-readable text (e.g. QRType
                # `seed__compactseedqr` as "seed: compactseedqr").
                # TODO: cleanup l10n presentation
                return Destination(
                    ErrorView,
                    view_args=dict(
                        title="Error",
                        status_headline=_("Wrong QR Type"),
                        text=_(self.invalid_qr_type_message)
                        + f""", received "{self.decoder.qr_type.replace("__", ": ").replace("_", " ")}\" format""",
                        button_text="Back",
                        next_destination=Destination(
                            BackStackView, skip_current_view=True
                        ),
                    ),
                )

            elif self.decoder.is_psbt:
                from seedcash.views.wallet_views import LoadingPSBTView

                self.controller.psbt_bytes = self.decoder.get_psbt()
                return Destination(LoadingPSBTView, skip_current_view=True)

            else:
                return Destination(NotYetImplementedView)

        elif self.decoder.is_invalid:
            # For now, don't even try to re-do the attempted operation, just reset and
            # start everything over.
            return Destination(ScanInvalidQRTypeView)


class ScanPSBTView(ScanView):
    instructions_text = "Scan PSBT"
    invalid_qr_type_message = "Expected a PSBT"

    @property
    def is_valid_qr_type(self):
        return self.decoder.is_psbt
