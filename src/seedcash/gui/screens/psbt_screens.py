import time

from dataclasses import dataclass
from gettext import gettext as _
from PIL import Image, ImageDraw

from seedcash.gui import renderer
from seedcash.gui.components import GUIConstants, Fonts
from seedcash.models.threads import BaseThread

from .screen import ButtonListScreen, ButtonOption

@dataclass
class PSBTOverviewScreen(ButtonListScreen):
    spend_amount: int = 0
    change_amount: int = 0
    fee_amount: int = 0
    num_inputs: int = 0
    num_self_transfer_outputs: int = 0
    num_change_outputs: int = 0
    destination_addresses: list[str] = None
    has_op_return: bool = False
    

    def __post_init__(self):
        # Customize defaults
        self.title = _("Review PSBT")
        self.is_bottom_list = True
        self.button_data = [ButtonOption("Review Details")]

        # This screen can take a while to load while parsing the PSBT
        self.show_loading_screen = True

        super().__post_init__()

        # Prep the headline amount being spent in large callout
        # icon_text_lines_y = self.components[-1].screen_y + self.components[-1].height
        icon_text_lines_y = self.top_nav.height + GUIConstants.COMPONENT_PADDING

        if not self.destination_addresses:
            # This is a self-transfer
            spend_amount = self.change_amount
        else:
            spend_amount = self.spend_amount

        self.components.append(BtcAmount(
            total_sats=spend_amount,
            screen_y=icon_text_lines_y,
        ))

        # Prep the transaction flow chart
        self.chart_x = 0
        self.chart_y = self.components[-1].screen_y + self.components[-1].height + int(GUIConstants.COMPONENT_PADDING/2)
        chart_height = self.buttons[0].screen_y - self.chart_y - GUIConstants.COMPONENT_PADDING

        # We need to supersample the whole panel so that small/thin elements render
        # clearly.
        ssf = 4  # super-sampling factor

        # Set up our temp supersampled rendering surface
        image = Image.new(
            "RGB",
            (self.canvas_width * ssf, chart_height * ssf),
            GUIConstants.BACKGROUND_COLOR
        )
        draw = ImageDraw.Draw(image)

        font_size = GUIConstants.BODY_FONT_MIN_SIZE * ssf
        font = Fonts.get_font(GUIConstants.get_body_font_name(), font_size)

        (left, top, right, bottom) = font.getbbox(text="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890[]", anchor="lt")
        chart_text_height = bottom
        vertical_center = int(image.height/2)
        # Supersampling renders thin elements poorly if they land on an even line before scaling down
        if vertical_center % 2 == 1:
            vertical_center += 1

        association_line_color = "#666"
        association_line_width = 3*ssf
        curve_steps = 4
        chart_font_color = "#ddd"
        
        # First calculate how wide the inputs col will be
        inputs_column = []
        if self.num_inputs == 1:
            inputs_column.append(_("1 input"))
        elif self.num_inputs > 5:
            inputs_column.append(_("input 1"))
            inputs_column.append(_("input 2"))
            # TRANSLATOR_NOTE: Indicates that items have been omitted from a series: e.g. "1, 2, 3, [...], 8"
            inputs_column.append(_("[ ... ]"))
            # TRANSLATOR_NOTE: Input number will be inserted (e.g. "input 3")
            inputs_column.append(_("input {}").format(self.num_inputs-1))
            inputs_column.append(_("input {}").format(self.num_inputs))
        else:
            for i in range(0, self.num_inputs):
                inputs_column.append(_("input {}").format(i+1))

        max_inputs_text_width = 0
        for input in inputs_column:
            left, top, right, bottom  = font.getbbox(input)
            tw, th = right - left, bottom - top
            max_inputs_text_width = max(tw, max_inputs_text_width)

        # Given how wide we want our curves on each side to be...
        curve_width = 4*GUIConstants.COMPONENT_PADDING*ssf

        # ...and the minimum center divider width...
        center_bar_width = 2*GUIConstants.COMPONENT_PADDING*ssf

        # We can calculate how wide the destination col can be
        max_destination_col_width = image.width - (GUIConstants.EDGE_PADDING*ssf + max_inputs_text_width + \
            int(GUIConstants.COMPONENT_PADDING*ssf/4) + curve_width + \
                center_bar_width + \
                    curve_width + int(GUIConstants.COMPONENT_PADDING*ssf/4) + \
                        GUIConstants.EDGE_PADDING*ssf)
        
        # if self.num_inputs == 1:
        #     # Use up more of the space on the input side
        #     max_destination_col_width += curve_width
        
        # Now let's maximize the actual destination col by adjusting our addr truncation
        def calculate_destination_col_width(truncate_at: int = 0):
            def truncate_destination_addr(addr):
                # TRANSLATOR_NOTE: Ellipsis ("...") characters used to truncate an address (e.g. "bc1qabc...")
                if len(addr) <= truncate_at + len(_("...")):
                    # No point in truncating
                    return addr

                return addr[:truncate_at] + _("...")
            
            destination_column = []

            if len(self.destination_addresses) + self.num_self_transfer_outputs <= 3:
                for addr in self.destination_addresses:
                    destination_column.append(truncate_destination_addr(addr))

                for i in range(0, self.num_self_transfer_outputs):
                    destination_column.append(truncate_destination_addr(_("self-transfer")))
            else:
                # destination_column.append(f"{len(self.destination_addresses)} recipients")
                destination_column.append(_("recipient 1"))
                # TRANSLATOR_NOTE: Indicates that items have been omitted from a series: e.g. "1, 2, 3, [...], 8"
                destination_column.append(_("[ ... ]"))
                # TRANSLATOR_NOTE: Inserts the recipient number (e.g. the fifth one is: "recipient 5")
                destination_column.append(_("recipient {}").format(len(self.destination_addresses) + self.num_self_transfer_outputs))

            destination_column.append(_("fee"))

            if self.has_op_return:
                # TRANSLATOR_NOTE: Technical term, should probably NOT be translated in most languages
                destination_column.append(_("OP_RETURN"))

            if self.num_change_outputs > 0:
                for i in range(0, self.num_change_outputs):
                    # TRANSLATOR_NOTE: Label for a change output in the PSBT Overview flow diagram
                    destination_column.append(_("change"))

            max_destination_text_width = 0
            for destination in destination_column:
                left, top, right, bottom  = font.getbbox(destination)
                tw, th = right - left, bottom - top
                max_destination_text_width = max(tw, max_destination_text_width)
            
            return (max_destination_text_width, destination_column)
        
        if len(self.destination_addresses) + self.num_self_transfer_outputs > 3:
            # We're not going to display any destination addrs so truncation doesn't matter
            (destination_text_width, destination_column) = calculate_destination_col_width()
        else:
            destination_text_width = None
            destination_column = None
            # Steadliy widen out the destination column until we run out of space
            for i in range(6, 14):
                (new_width, new_col_text) = calculate_destination_col_width(truncate_at=i)
                if new_width > max_destination_col_width:
                    if not destination_text_width:
                        destination_text_width = new_width
                    if not destination_column:
                        destination_column = new_col_text
                    break
                destination_text_width = new_width
                destination_column = new_col_text

        destination_col_x = image.width - (destination_text_width + GUIConstants.EDGE_PADDING*ssf)

        # Now we can finalize our center bar values
        center_bar_x = GUIConstants.EDGE_PADDING*ssf + max_inputs_text_width + int(GUIConstants.COMPONENT_PADDING*ssf/4) + curve_width

        # Center bar stretches to fill any excess width
        center_bar_width = destination_col_x - int(GUIConstants.COMPONENT_PADDING*ssf/4) - curve_width - center_bar_x 

        # Position each input row
        num_rendered_inputs = len(inputs_column)
        if self.num_inputs == 1:
            inputs_y = vertical_center - int(chart_text_height/2)
            inputs_y_spacing = 0  # Not used
        else:
            inputs_y = int((image.height - num_rendered_inputs*chart_text_height) / (num_rendered_inputs + 1))
            inputs_y_spacing = inputs_y + chart_text_height

        # Don't render lines from an odd number
        if inputs_y % 2 == 1:
            inputs_y += 1
        if inputs_y_spacing % 2 == 1:
            inputs_y_spacing += 1

        inputs_conjunction_x = center_bar_x
        inputs_x = GUIConstants.EDGE_PADDING*ssf

        input_curves = []
        for input in inputs_column:
            # Calculate right-justified input display
            left, top, right, bottom  = font.getbbox(input)
            tw, th = right - left, bottom - top
            cur_x = inputs_x + max_inputs_text_width - tw
            draw.text(
                (cur_x, inputs_y),
                text=input,
                font=font,
                fill=chart_font_color,
                anchor="lt",
            )

            # Render the association line to the conjunction point
            # First calculate a bezier curve to an inflection point
            start_pt = (
                inputs_x + max_inputs_text_width + int(GUIConstants.COMPONENT_PADDING*ssf/4),
                inputs_y + int(chart_text_height/2)
            )
            conjunction_pt = (inputs_conjunction_x, vertical_center)
            mid_pt = (
                int(start_pt[0]*0.5 + conjunction_pt[0]*0.5), 
                int(start_pt[1]*0.5 + conjunction_pt[1]*0.5)
            )

            if len(inputs_column) == 1:
                # Use fewer segments for single input straight line
                bezier_points = [
                    start_pt,
                    linear_interp(start_pt, conjunction_pt, 0.33),
                    linear_interp(start_pt, conjunction_pt, 0.66),
                    conjunction_pt
                ]
            else:
                bezier_points = calc_bezier_curve(
                    start_pt,
                    (mid_pt[0], start_pt[1]),
                    mid_pt,
                    curve_steps
                )
                # We don't need the "final" point as it's repeated below
                bezier_points.pop()

                # Now render the second half after the inflection point
                bezier_points += calc_bezier_curve(
                    mid_pt,
                    (mid_pt[0], conjunction_pt[1]),
                    conjunction_pt,
                    curve_steps
                )

            input_curves.append(bezier_points)

            prev_pt = bezier_points[0]
            for pt in bezier_points[1:]:
                draw.line(
                    (prev_pt[0], prev_pt[1], pt[0], pt[1]),
                    fill=association_line_color,
                    width=association_line_width + 1,
                    joint="curve",
                )
                prev_pt = pt

            inputs_y += inputs_y_spacing
        
        # Render center bar
        draw.line(
            (
                center_bar_x,
                vertical_center,
                center_bar_x + center_bar_width,
                vertical_center
            ),
            fill=association_line_color,
            width=association_line_width
        )

        # Position each destination
        num_rendered_destinations = len(destination_column)
        if num_rendered_destinations == 1:
            destination_y = vertical_center - int(chart_text_height/2)
            destination_y_spacing = 0
        else:
            destination_y = int((image.height - num_rendered_destinations*chart_text_height) / (num_rendered_destinations + 1))
            destination_y_spacing = destination_y + chart_text_height

        # Don't render lines from an odd number
        if destination_y % 2 == 1:
            destination_y += 1
        if destination_y_spacing % 2 == 1:
            destination_y_spacing += 1

        destination_conjunction_x = center_bar_x + center_bar_width
        recipients_text_x = destination_col_x

        output_curves = []
        for destination in destination_column:
            draw.text(
                (recipients_text_x, destination_y),
                text=destination,
                font=font,
                fill=chart_font_color,
                anchor="lt"
            )

            # Render the association line from the conjunction point
            # First calculate a bezier curve to an inflection point
            conjunction_pt = (destination_conjunction_x, vertical_center)
            end_pt = (
                conjunction_pt[0] + curve_width,
                destination_y + int(chart_text_height/2)
            )
            mid_pt = (
                int(conjunction_pt[0]*0.5 + end_pt[0]*0.5), 
                int(conjunction_pt[1]*0.5 + end_pt[1]*0.5)
            )

            bezier_points = calc_bezier_curve(
                conjunction_pt,
                (mid_pt[0], conjunction_pt[1]),
                mid_pt,
                curve_steps
            )
            # We don't need the "final" point as it's repeated below
            bezier_points.pop()

            # Now render the second half after the inflection point
            curve_bias = 1.0
            bezier_points += calc_bezier_curve(
                mid_pt,
                (int(mid_pt[0]*curve_bias + end_pt[0]*(1.0-curve_bias)), end_pt[1]),
                end_pt,
                curve_steps
            )

            output_curves.append(bezier_points)

            prev_pt = bezier_points[0]
            for pt in bezier_points[1:]:
                draw.line(
                    (prev_pt[0], prev_pt[1], pt[0], pt[1]),
                    fill=association_line_color,
                    width=association_line_width + 1,
                    joint="curve",
                )
                prev_pt = pt

            destination_y += destination_y_spacing

        # Resize to target and sharpen final image
        image = image.resize((self.canvas_width, chart_height), Image.Resampling.LANCZOS)
        self.paste_images.append((image.filter(ImageFilter.SHARPEN), (self.chart_x, self.chart_y)))

        # Pass input and output curves to the animation thread
        self.threads.append(
            PSBTOverviewScreen.TxExplorerAnimationThread(
                inputs=input_curves,
                outputs=output_curves,
                supersampling_factor=ssf,
                offset_y=self.chart_y,
                renderer=self.renderer
            )
        )



    class TxExplorerAnimationThread(BaseThread):
        def __init__(self, inputs, outputs, supersampling_factor, offset_y, renderer: Renderer):
            super().__init__()

            # Translate the point coords into renderer space
            ssf = supersampling_factor
            self.inputs = [[(int(i[0]/ssf), int(i[1]/ssf + offset_y)) for i in curve] for curve in inputs]
            self.outputs = [[(int(i[0]/ssf), int(i[1]/ssf + offset_y)) for i in curve] for curve in outputs]
            self.renderer = renderer


        def run(self):
            pulse_color = GUIConstants.ACCENT_COLOR
            reset_color = "#666"
            line_width = 3

            pulses = []

            # The center bar needs to be segmented to support animation across it
            start_pt = self.inputs[0][-1]
            end_pt = self.outputs[0][0]
            if start_pt == end_pt:
                # In single input the center bar width can be zeroed out.
                # Ugly hack: Insert this line segment that will be skipped otherwise.
                center_bar_pts = [end_pt, self.outputs[0][1]]
            else:
                center_bar_pts = [
                    start_pt,
                    linear_interp(start_pt, end_pt, 0.25),
                    linear_interp(start_pt, end_pt, 0.50),
                    linear_interp(start_pt, end_pt, 0.75),
                    end_pt,
                ]

            def draw_line_segment(curves, i, j, color):
                # print(f"draw: {curves[0][i]} to {curves[0][j]}")
                for points in curves:
                    pt1 = points[i]
                    pt2 = points[j]
                    self.renderer.draw.line(
                        (pt1[0], pt1[1], pt2[0], pt2[1]),
                        fill=color,
                        width=line_width
                    )

            prev_color = reset_color
            while self.keep_running:
                with self.renderer.lock:
                    # Only generate one new pulse at a time; trailing "reset_color" pulse
                    # erases the most recent pulse.
                    if not pulses or (
                        prev_color == pulse_color and pulses[-1][0] == 10):
                        # Create a new pulse
                        if prev_color == pulse_color:
                            pulses.append([0, reset_color])
                        else:
                            pulses.append([0, pulse_color])
                        prev_color = pulses[-1][1]

                    for pulse_num, pulse in enumerate(pulses):
                        i = pulse[0]
                        color = pulse[1]
                        if i < len(self.inputs[0]) - 1:
                            # We're in the input curves
                            draw_line_segment(self.inputs, i, i+1, color)
                        elif i < len(self.inputs[0]) + len(center_bar_pts) - 2:
                            # We're in the center bar
                            index = i - len(self.inputs[0]) + 1
                            draw_line_segment([center_bar_pts], index, index+1, color)
                        elif i < len(self.inputs[0]) + len(center_bar_pts) - 2 + len(self.outputs[0]) - 1:
                            index = i - (len(self.inputs[0]) + len(center_bar_pts) - 2)
                            draw_line_segment(self.outputs, index, index+1, color)
                        else:
                            # This pulse is done
                            del pulses[pulse_num]
                            continue

                        pulse[0] += 1

                    self.renderer.show_image()

                # No need to CPU limit when running in its own thread?
                time.sleep(0.02)
