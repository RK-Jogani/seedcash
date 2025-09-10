from gettext import gettext as _
from seedcash.views.view import View, Destination


class ScanView(View):
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

