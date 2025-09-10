import logging
import time

from dataclasses import dataclass
from gettext import gettext as _

from seedcash.gui.components import load_image
from seedcash.gui.screens.screen import BaseScreen
from seedcash.views.view import View

logger = logging.getLogger(__name__)


# TODO: This early code is now outdated vis-a-vis Screen vs View distinctions
class LogoScreen(BaseScreen):
    def __init__(self):
        super().__init__()
        self.logo = load_image("seedcash.png", "img")

    def _run(self):
        pass


@dataclass
class OpeningSplashView(View):
    is_screenshot_renderer: bool = False

    def run(self):
        self.run_screen(
            OpeningSplashScreen,
            is_screenshot_renderer=self.is_screenshot_renderer,
        )


class OpeningSplashScreen(LogoScreen):
    def __init__(self, is_screenshot_renderer=False):
        self.is_screenshot_renderer = is_screenshot_renderer
        super().__init__()

    def _render(self):
        from PIL import Image
        from seedcash.controller import Controller

        controller = Controller.get_instance()

        # TODO: Fix for the screenshot generator. When generating screenshots for
        # multiple locales, there is a button still in the canvas from the previous
        # screenshot, even though the Renderer has been reconfigured and re-
        # instantiated. This is a hack to clear the screen for now.
        self.clear_screen()

        logo_offset_x = 0
        logo_offset_y = 0

        background = Image.new("RGBA", size=self.logo.size, color="black")
        if not self.is_screenshot_renderer:
            # Fade in alpha
            for i in range(250, -1, -25):
                self.logo.putalpha(255 - i)
                self.renderer.canvas.paste(
                    Image.alpha_composite(background, self.logo),
                    (logo_offset_x, logo_offset_y),
                )
                self.renderer.show_image()
        else:
            # Skip animation for the screenshot generator
            self.renderer.canvas.paste(self.logo, (logo_offset_x, logo_offset_y))

        if not self.is_screenshot_renderer:
            self.renderer.show_image()

        if not self.is_screenshot_renderer:
            # Hold on the splash screen for a moment
            time.sleep(2)


class ScreensaverScreen(LogoScreen):
    def __init__(self, buttons):
        from PIL import Image

        super().__init__()

        self.buttons = buttons

        # Paste the logo in a bigger image that is the canvas + the logo dims (half the
        # logo will render off the canvas at each edge).
        self.logo_image = Image.new(
            "RGB",
            (
                self.renderer.canvas_width + self.logo.width,
                self.renderer.canvas_height + self.logo.height,
            ),
            (0, 0, 0),
        )

        # paste image
        self.image = self.logo_image

        # Place the logo centered on the larger image
        self.logo_x = int((self.image.width - self.logo.width) / 2)
        self.logo_y = int((self.image.height - self.logo.height) / 2)
        self.image.paste(self.logo, (self.logo_x, self.logo_y))

        # Update our first rendering position so we're centered
        self.cur_x = int(self.logo.width / 2)
        self.cur_y = int(self.logo.height / 2)

        self._is_running = False
        self.last_screen = None

    @property
    def is_running(self):
        return self._is_running

    def start(self):
        if self.is_running:
            return

        self.start_time = time.time()

        self._is_running = True

        # Store the current screen in order to restore it later
        self.last_screen = self.renderer.canvas.copy()

        # Screensaver must block any attempts to use the Renderer in another thread so it
        # never gives up the lock until it returns.
        with self.renderer.lock:
            try:
                while self._is_running:
                    if self.buttons.has_any_input() or self.buttons.override_ind:
                        break

                    self.image = self.logo_image
                    # Must crop the image to the exact display size
                    crop = self.image.crop(
                        (
                            self.cur_x,
                            self.cur_y,
                            self.cur_x + self.renderer.canvas_width,
                            self.cur_y + self.renderer.canvas_height,
                        )
                    )
                    self.renderer.disp.show_image(crop, 0, 0)

            except KeyboardInterrupt as e:
                # Exit triggered; close gracefully
                logger.info("Shutting down Screensaver")

                # Have to let the interrupt bubble up to exit the main app
                raise e
            finally:
                # Restore the last screen
                self._is_running = False
                self.renderer.show_image(self.last_screen)

    def stop(self):
        self._is_running = False
