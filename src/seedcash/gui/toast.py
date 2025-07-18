import logging
import time
from dataclasses import dataclass
from gettext import gettext as _

from seedcash.gui.components import (
    BaseComponent,
    GUIConstants,
    Icon,
    SeedSignerIconConstants,
    TextArea,
)
from seedcash.models.threads import BaseThread

logger = logging.getLogger(__name__)


@dataclass
class ToastOverlay(BaseComponent):
    icon_name: str = None
    color: str = GUIConstants.NOTIFICATION_COLOR
    font_color: str = GUIConstants.NOTIFICATION_COLOR
    label_text: str = None
    height: int = GUIConstants.ICON_TOAST_FONT_SIZE + 2 * GUIConstants.EDGE_PADDING
    font_size: int = 19
    outline_thickness: int = 2  # pixels

    def __post_init__(self):
        super().__post_init__()

        icon_delta_x = 0
        if self.icon_name:
            self.icon = Icon(
                image_draw=self.image_draw,
                canvas=self.canvas,
                screen_x=self.outline_thickness
                + GUIConstants.EDGE_PADDING,  # Push the icon further from the left edge than strictly necessary
                icon_name=self.icon_name,
                icon_size=GUIConstants.ICON_TOAST_FONT_SIZE,
                icon_color=self.color,
            )
            icon_delta_x = self.icon.width + self.icon.screen_x

        self.label = TextArea(
            image_draw=self.image_draw,
            canvas=self.canvas,
            text=self.label_text,
            font_size=self.font_size,
            font_color=self.font_color,
            edge_padding=0,
            is_text_centered=False,
            auto_line_break=True,
            width=self.canvas_width
            - icon_delta_x
            - 2 * GUIConstants.COMPONENT_PADDING
            - 2 * self.outline_thickness,
            screen_x=icon_delta_x + GUIConstants.COMPONENT_PADDING,
            allow_text_overflow=False,
            height_ignores_below_baseline=True,
        )

        if self.label.height > GUIConstants.ICON_FONT_SIZE:
            self.height = self.label.height + GUIConstants.EDGE_PADDING * 2

        # Vertically center the message and icon within the toast (for single- or multi-line
        # messages).
        self.label.screen_y = (
            self.canvas_height
            - self.height
            + self.outline_thickness
            + int((self.height - 2 * self.outline_thickness - self.label.height) / 2)
        )

        if self.icon_name:
            self.icon.screen_y = (
                self.canvas_height
                - self.height
                + int((self.height - self.icon.height) / 2)
            )

    def render(self):
        # Render the toast's solid background
        self.image_draw.rounded_rectangle(
            (
                0,
                self.canvas_height - self.height,
                self.canvas_width,
                self.canvas_height,
            ),
            fill=GUIConstants.BACKGROUND_COLOR,
            radius=8,
            outline=self.color,
            width=self.outline_thickness,
        )

        # Draw the toast visual elements
        if self.icon_name:
            self.icon.render()

        self.label.render()

        self.renderer.show_image()


class BaseToastOverlayManagerThread(BaseThread):
    """
    The toast notification popup consists of a gui component (`ToastOverlay`) and this
    manager thread that the Controller will use to coordinate handing off resources
    between competing toasts, the screensaver, and the current underlying Screen.

    Controller should set BaseThread.keep_running = False to terminate the toast when it
    needs to be removed or replaced.

    Controller should set toggle_renderer_lock = True to make the toast temporarily
    release the Renderer.lock so another process (e.g. screensaver) can use it. The toast
    thread will immediately try to reacquire the lock, but will have to block and wait
    until it's available again. Note that this thread will be unresponsive while it
    waits to reacquire the lock!

    Note: any process can call lock.release() but it simplifies the logic to try to keep
    each process aware of whether it is currently holding the lock or not (i.e. it's
    better for the "owner" thread to release the lock itself).
    """

    def __init__(
        self,
        activation_delay: int = 0,  # seconds before toast is displayed
        duration: int = 3,  # seconds toast is displayed
    ):
        from seedcash.controller import Controller
        from seedcash.gui.renderer import Renderer
        from seedcash.hardware.buttons import HardwareButtons

        super().__init__()
        self.activation_delay: int = activation_delay
        self.duration: int = duration
        self._toggle_renderer_lock: bool = False

        self.renderer = Renderer.get_instance()
        self.controller = Controller.get_instance()
        self.hw_inputs = HardwareButtons.get_instance()

        # Special case when screensaver is running
        self.hw_inputs.override_ind = True

        self.toast = self.instantiate_toast()

    def instantiate_toast(self) -> ToastOverlay:
        raise Exception("Must be implemented by subclass")

    def should_keep_running(self) -> bool:
        """Placeholder for custom exit conditions"""
        return True

    def toggle_renderer_lock(self):
        self._toggle_renderer_lock = True

    def run(self):
        logger.info(f"{self.__class__.__name__}: started")
        start = time.time()
        time.sleep(0.2)
        while time.time() - start < self.activation_delay:
            if self.hw_inputs.has_any_input():
                # User has pressed a button, cancel the toast
                logger.info(
                    f"{self.__class__.__name__}: Canceling toast due to user input"
                )
                return
            time.sleep(0.1)

        try:
            # Hold onto the Renderer lock so we're guaranteed to restore the original
            # screen before any other listener can get a screen write in.
            logger.info(f"{self.__class__.__name__}: Acquiring lock")
            self.renderer.lock.acquire()
            logger.info(f"{self.__class__.__name__}: Lock acquired")

            has_rendered = False
            previous_screen_state = None
            while self.keep_running and self.should_keep_running():
                if self.hw_inputs.has_any_input():
                    # User has pressed a button, hide the toast
                    logger.info(f"{self.__class__.__name__}: Exiting due to user input")
                    break

                if self._toggle_renderer_lock:
                    # Controller has notified us that another process needs the lock
                    logger.info(f"{self.__class__.__name__}: Releasing lock")
                    self._toggle_renderer_lock = False
                    self.renderer.lock.release()

                    # pause to avoid race conditions reacquiring the lock
                    while not self.renderer.lock.locked():
                        # Wait for a different process to grab the lock
                        time.sleep(0.1)

                    # Block while waiting to reaquire the lock
                    logger.info(
                        f"{self.__class__.__name__}: Blocking to re-acquire lock"
                    )
                    self.renderer.lock.acquire()
                    logger.info(f"{self.__class__.__name__}: Lock re-acquired")

                if not has_rendered:
                    previous_screen_state = self.renderer.canvas.copy()
                    logger.info(f"{self.__class__.__name__}: Showing toast")
                    self.toast.render()
                    has_rendered = True

                if (
                    time.time() - start > self.activation_delay + self.duration
                    and has_rendered
                ):
                    logger.info(f"{self.__class__.__name__}: Hiding toast")
                    break

                # Free up cpu resources for main thread
                time.sleep(0.1)

        finally:
            logger.info(f"{self.__class__.__name__}: exiting")
            if has_rendered and self.renderer.lock.locked():
                # As far as we know, we currently hold the Renderer.lock
                self.renderer.show_image(previous_screen_state)
                logger.info(
                    f"{self.__class__.__name__}: restored previous screen state"
                )

            # We're done, release the lock
            self.renderer.lock.release()


class RemoveSDCardToastManagerThread(BaseToastOverlayManagerThread):
    def __init__(self, activation_delay: int = 3, duration: int = 1e6):
        """
        * activation_delay: configurable so the screenshot generator can get the
            toast to immediately render.
        * duration: default value is essentially forever. Overrideable for the
            screenshot generator.
        """
        super().__init__(
            activation_delay=activation_delay,
            duration=duration,
        )

    def instantiate_toast(self) -> ToastOverlay:
        body_font_size = GUIConstants.BODY_FONT_SIZE
        return ToastOverlay(
            icon_name=SeedSignerIconConstants.MICROSD,
            label_text=_("You can remove\nthe SD card now"),
            font_size=body_font_size,
            height=body_font_size * 2
            + GUIConstants.BODY_LINE_SPACING
            + GUIConstants.EDGE_PADDING,
        )

    def should_keep_running(self) -> bool:
        """Custom exit condition: keep running until the SD card is removed"""
        from seedcash.hardware.microsd import MicroSD

        return MicroSD.get_instance().is_inserted


class SDCardStateChangeToastManagerThread(BaseToastOverlayManagerThread):
    def __init__(self, action: str, *args, **kwargs):
        # Note: we could just directly detect the MicroSD status here, but passing it in
        # via `action` lets us simulate the state we want in the screenshot generator.
        from seedcash.hardware.microsd import MicroSD

        if action not in [MicroSD.ACTION__INSERTED, MicroSD.ACTION__REMOVED]:
            raise Exception(f"Invalid MicroSD action: {action}")
        self.message = (
            _("SD card removed")
            if action == MicroSD.ACTION__REMOVED
            else _("SD card inserted")
        )

        super().__init__(*args, **kwargs)

    def instantiate_toast(self) -> ToastOverlay:
        logger.info("instantiating toast!")
        return ToastOverlay(
            icon_name=SeedSignerIconConstants.MICROSD,
            label_text=self.message,
        )


"""****************************************************************************
    Messaging toasts
****************************************************************************"""


class DefaultToast(BaseToastOverlayManagerThread):
    def __init__(
        self, label_text="This is a notification toast", activation_delay=0, duration=3
    ):
        # Note: activation_delay is configurable so the screenshot generator can get the
        # toast to immediately render.
        self.label_text = label_text
        super().__init__(
            activation_delay=activation_delay, duration=duration  # seconds  # seconds
        )

    def instantiate_toast(self) -> ToastOverlay:
        body_font_size = GUIConstants.BODY_FONT_SIZE
        return ToastOverlay(
            label_text=self.label_text,
            color=GUIConstants.BODY_FONT_COLOR,
            font_color=GUIConstants.BODY_FONT_COLOR,
            font_size=body_font_size,
        )


class InfoToast(DefaultToast):
    def instantiate_toast(self) -> ToastOverlay:
        body_font_size = GUIConstants.BODY_FONT_SIZE
        return ToastOverlay(
            icon_name=SeedSignerIconConstants.INFO,
            label_text=self.label_text,
            color=GUIConstants.INFO_COLOR,
            font_color=GUIConstants.BODY_FONT_COLOR,
            font_size=body_font_size,
        )


class SuccessToast(DefaultToast):
    def instantiate_toast(self) -> ToastOverlay:
        body_font_size = GUIConstants.BODY_FONT_SIZE
        return ToastOverlay(
            icon_name=SeedSignerIconConstants.SUCCESS,
            label_text=self.label_text,
            color=GUIConstants.SUCCESS_COLOR,
            font_color=GUIConstants.BODY_FONT_COLOR,
            font_size=body_font_size,
        )


class WarningToast(DefaultToast):
    def instantiate_toast(self) -> ToastOverlay:
        body_font_size = GUIConstants.BODY_FONT_SIZE
        return ToastOverlay(
            icon_name=SeedSignerIconConstants.WARNING,
            label_text=self.label_text,
            color=GUIConstants.WARNING_COLOR,
            font_color=GUIConstants.BODY_FONT_COLOR,
            font_size=body_font_size,
        )


class DireWarningToast(DefaultToast):
    def instantiate_toast(self) -> ToastOverlay:
        body_font_size = GUIConstants.BODY_FONT_SIZE
        return ToastOverlay(
            icon_name=SeedSignerIconConstants.WARNING,
            label_text=self.label_text,
            color=GUIConstants.DIRE_WARNING_COLOR,
            font_color=GUIConstants.BODY_FONT_COLOR,
            font_size=body_font_size,
        )


class ErrorToast(DefaultToast):
    def instantiate_toast(self) -> ToastOverlay:
        body_font_size = GUIConstants.BODY_FONT_SIZE
        return ToastOverlay(
            icon_name=SeedSignerIconConstants.ERROR,
            label_text=self.label_text,
            color=GUIConstants.ERROR_COLOR,
            font_color=GUIConstants.BODY_FONT_COLOR,
            font_size=body_font_size,
        )
