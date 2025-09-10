import time

from dataclasses import dataclass
from gettext import gettext as _
from PIL import Image, ImageDraw

from seedcash.gui import renderer
from seedcash.gui.components import GUIConstants, Fonts, resize_image_to_fill
from seedcash.models.threads import BaseThread

from .screen import BaseScreen




@dataclass
class ScanScreen(BaseScreen):
    """
    Camera preview screen that displays live camera feed.

    Live preview has to balance camera capturing frames and display rendering:
    * Camera capturing frames and making them available to read.
    * Live preview display writing frames to the screen.

    The camera runs at a modest fps target: 6fps. At this pace, the live display
    can keep up with the flow of frames without much wasted effort.

    Note: performance tuning was targeted for the Pi Zero.

    The resolution (480x480) provides a good balance between quality and performance.
    """
    instructions_text: str = None
    resolution: tuple[int,int] = (480, 480)
    framerate: int = 6  # TODO: alternate optimization for Pi Zero 2W?
    render_rect: tuple[int,int,int,int] = None

    def __post_init__(self):
        from seedcash.hardware.camera import Camera
        # Initialize the base class
        super().__post_init__()

        # TODO: Arrange this with UI elements rather than text
        self.instructions_text = "< " + _("back") + "  |  Camera Preview"

        self.camera = Camera.get_instance()
        self.camera.start_video_stream_mode(resolution=self.resolution, framerate=self.framerate, format="rgb")

        self.threads.append(ScanScreen.LivePreviewThread(
            renderer=self.renderer,
            instructions_text=self.instructions_text,
            render_rect=self.render_rect,
        ))


    class LivePreviewThread(BaseThread):
        def __init__(self, renderer: renderer.Renderer, instructions_text: str, render_rect: tuple[int,int,int,int]):
            from seedcash.hardware.camera import Camera

            self.camera = Camera.get_instance()
            self.renderer = renderer
            self.instructions_text = instructions_text
            if render_rect:
                self.render_rect = render_rect            
            else:
                self.render_rect = (0, 0, self.renderer.canvas_width, self.renderer.canvas_height)
            self.render_width = self.render_rect[2] - self.render_rect[0]
            self.render_height = self.render_rect[3] - self.render_rect[1]

            super().__init__()


        def run(self):
            from timeit import default_timer as timer

            instructions_font = Fonts.get_font(GUIConstants.BODY_FONT_NAME, GUIConstants.BUTTON_FONT_SIZE)

            start_time = time.time()
            num_frames = 0
            show_framerate = False  # enable for debugging / testing
            while self.keep_running:
                frame = self.camera.read_video_stream(as_image=True)
                if frame is not None:
                    num_frames += 1
                    cur_time = time.time()
                    cur_fps = num_frames / (cur_time - start_time)
                    
                    scan_text = None
                    if show_framerate:
                        scan_text = f"FPS: {cur_fps:0.2f}"
                    else:
                        scan_text = self.instructions_text

                    with self.renderer.lock:
                        # Use nearest neighbor resizing for max speed
                        frame = resize_image_to_fill(frame, self.render_width, self.render_height, sampling_method=Image.Resampling.NEAREST)

                        if scan_text:
                            # Note: shadowed text (adding a 'stroke' outline) can
                            # significantly slow down the rendering.
                            # Temp solution: render a slight 1px shadow behind the text
                            draw = ImageDraw.Draw(frame)
                            draw.text(xy=(
                                        int(self.renderer.canvas_width/2 + 2),
                                        self.renderer.canvas_height - GUIConstants.EDGE_PADDING + 2
                                     ),
                                     text=scan_text,
                                     fill="black",
                                     font=instructions_font,
                                     anchor="ms")

                            # Render the onscreen instructions
                            draw.text(xy=(
                                        int(self.renderer.canvas_width/2),
                                        self.renderer.canvas_height - GUIConstants.EDGE_PADDING
                                     ),
                                     text=scan_text,
                                     fill=GUIConstants.BODY_FONT_COLOR,
                                     font=instructions_font,
                                     anchor="ms")

                        self.renderer.show_image(frame, show_direct=True)

                if self.camera._video_stream is None:
                    break


    def _run(self):
        """
            _render() is mostly meant to be a one-time initial drawing call to set up the
            Screen. Once interaction starts, the display updates have to be managed in
            _run(). The live preview is a simple camera display.
        """
        from seedcash.hardware.buttons import HardwareButtonsConstants

        while True:
            # Check for button press to exit camera view
            if self.hw_inputs.check_for_low(HardwareButtonsConstants.KEY_RIGHT) or self.hw_inputs.check_for_low(HardwareButtonsConstants.KEY_LEFT):
                self.camera.stop_video_stream_mode()
                return False