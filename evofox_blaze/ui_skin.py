"""Cairo/Pango renderer for the original Blaze skin, with live text layers.

The JPEGs are skin atlases, not screenshots of controls: text, selection,
focus, navigation, tooltips, and device actions belong to the GTK application.
No vendor executable, INI code, or device transport is loaded here.
"""

import ctypes
import ctypes.util
from pathlib import Path
import math

from .ui_layout import HEIGHT, WIDTH, TABS, PROFILES, BUTTON_LABELS


# Display-only coordinates on the supplied illustration, not device event IDs.
MOUSE_MARKERS = ((1, 457, 246), (2, 551, 246), (3, 503, 242),
                 (4, 414, 318), (5, 425, 363), (6, 503, 307),
                 (7, 503, 342), (8, 425, 240))


class Skin:
    def __init__(self, directory, mouse_image=None):
        import gi
        gi.require_version("Gdk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Gdk, GdkPixbuf, Pango, PangoCairo
        import cairo
        self.Gdk, self.Pango, self.PangoCairo = Gdk, Pango, PangoCairo
        self.cairo = cairo
        self.directory = Path(directory)
        self.atlases = {}
        for name in ("main_normal", "main_over", "main_down", "advanced_normal",
                     "advanced_down", "mac_normal", "mac_down", "led_null",
                     "led_normal", "led_down"):
            path = self.directory / f"{name}.jpg"
            if not path.is_file():
                raise FileNotFoundError(
                    f"Reference skin is not prepared: {path}\n"
                    "Run python3 -m tools.prepare_ui_skin --from-directory <extracted-app/skins>\n"
                    "or use --extractor <trusted-innoextract-binary>. "
                    "The existing controls remain available with --diagnostics.")
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
            if (pixbuf.get_width(), pixbuf.get_height()) != (WIDTH, HEIGHT):
                raise ValueError(f"Unexpected reference atlas dimensions: {path}")
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
            ctx = cairo.Context(surface)
            Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
            ctx.paint()
            self.atlases[name] = surface
        self.font_family = "Liberation Sans Narrow"
        font = self.directory / "config/font/Roboto-Regular.ttf"
        library = ctypes.util.find_library("fontconfig")
        if font.is_file() and library:
            # App-local registration only; does not install a system font.
            fontconfig = ctypes.CDLL(library)
            fontconfig.FcConfigAppFontAddFile.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
            fontconfig.FcConfigAppFontAddFile.restype = ctypes.c_int
            if fontconfig.FcConfigAppFontAddFile(None, str(font).encode()):
                self.font_family = "Roboto"
                PangoCairo.FontMap.get_default().changed()
        self.mouse = None
        self.mouse_backdrop = None
        if mouse_image is not None:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(mouse_image))
            if (pixbuf.get_width(), pixbuf.get_height()) != (1254, 1254):
                raise ValueError("The supplied-mouse cutout expects the 1254 × 1254 MouseImage.png reference")
            self.mouse = self.cutout_mouse(pixbuf)

    def cutout_mouse(self, pixbuf):
        """Trace the supplied image's silhouette; preserve the source unchanged."""
        surface = self.cairo.ImageSurface(self.cairo.FORMAT_ARGB32, 680, 1165)
        ctx = self.cairo.Context(surface)
        ctx.translate(-280, 0)
        # Source-space outline, including the cable and the narrow side buttons.
        ctx.move_to(606, 0)
        ctx.line_to(641, 0)
        ctx.line_to(642, 52)
        ctx.curve_to(662, 53, 660, 84, 661, 89)
        ctx.line_to(675, 128)
        ctx.line_to(680, 121)
        ctx.curve_to(705, 115, 824, 168, 868, 209)
        ctx.line_to(876, 397)
        ctx.curve_to(900, 457, 898, 511, 911, 578)
        ctx.curve_to(940, 723, 967, 880, 894, 977)
        ctx.curve_to(825, 1097, 732, 1156, 620, 1156)
        ctx.curve_to(501, 1155, 429, 1081, 399, 981)
        ctx.line_to(381, 987)
        ctx.curve_to(303, 897, 298, 758, 297, 700)
        ctx.curve_to(292, 661, 335, 620, 360, 571)
        ctx.line_to(354, 459)
        ctx.line_to(364, 452)
        ctx.line_to(363, 428)
        ctx.curve_to(336, 404, 329, 378, 337, 340)
        ctx.line_to(349, 241)
        ctx.curve_to(352, 208, 399, 188, 425, 177)
        ctx.line_to(430, 174)
        ctx.line_to(568, 119)
        ctx.line_to(574, 122)
        ctx.line_to(575, 131)
        ctx.line_to(583, 94)
        ctx.line_to(599, 87)
        ctx.line_to(600, 62)
        ctx.line_to(608, 53)
        ctx.close_path()
        ctx.clip()
        self.Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
        ctx.paint()
        return surface

    def make_mouse_backdrop(self):
        """Recover unobstructed backdrop from complementary reference atlases.

        The lighting atlas has no central mouse; the performance atlas has no
        left assignment rows. Undo their panel tints only in the replacement
        areas. This is used only for the optional, non-reference mouse artwork.
        """
        from gi.repository import GdkPixbuf, GLib
        normal, advanced, lighting = (
            GdkPixbuf.Pixbuf.new_from_file(str(self.directory / f"{name}.jpg"))
            for name in ("main_normal", "advanced_normal", "led_null"))
        stride = normal.get_rowstride()
        pixels, advance, light = (image.get_pixels() for image in (normal, advanced, lighting))
        result = bytearray(pixels)

        def transform(source, xs, ys):
            coefficients = []
            for channel in range(3):
                pairs = [(source[y * stride + x * 3 + channel], pixels[y * stride + x * 3 + channel])
                         for x in xs for y in ys]
                mx = sum(x for x, _ in pairs) / len(pairs)
                my = sum(y for _, y in pairs) / len(pairs)
                slope = sum((x - mx) * (y - my) for x, y in pairs) / sum((x - mx) ** 2 for x, _ in pairs)
                coefficients.append((slope, my - slope * mx))
            return coefficients

        advanced_tint = transform(advance, range(100, 371, 10), (201, 211, 281, 291, 421, 431, 511))
        lighting_tint = transform(light, range(620, 881, 10), (201, 211, 281, 351, 421, 511))
        for y in range(143, 534):
            for x in range(387, 619):
                # Beyond the original mouse, retain the unmodified backdrop.
                if y > 526:
                    continue
                sx, sy = x, y
                tinted = x >= 539 and 188 <= y <= 532
                if y >= 519 and 538 <= x <= 557:
                    # The panel's bottom-left chamfer crosses this small area.
                    sx = x - 25
                    tinted = False
                elif tinted:
                    if 538 <= x <= 541 or 583 <= x <= 586:
                        sx = x - 5
                    if 188 <= y <= 191:
                        sy = 185
                        tinted = False
                for c in range(3):
                    value = light[sy * stride + sx * 3 + c]
                    if tinted:
                        slope, intercept = lighting_tint[c]
                        value = round(value * slope + intercept)
                    result[y * stride + x * 3 + c] = max(0, min(255, value))
        for top in (234, 309, 383, 458):
            for y in range(top, top + 42):
                # Do not copy the performance atlas's slider rule.
                sy = y - 10 if any(abs(y - line) <= 4 for line in (255, 372, 488)) else y
                for x in range(183, 370):
                    for c in range(3):
                        slope, intercept = advanced_tint[c]
                        value = round(advance[sy * stride + x * 3 + c] * slope + intercept)
                        result[y * stride + x * 3 + c] = max(0, min(255, value))
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(result)),
                                                GdkPixbuf.Colorspace.RGB, False, 8,
                                                WIDTH, HEIGHT, stride)
        surface = self.cairo.ImageSurface(self.cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
        ctx = self.cairo.Context(surface)
        self.Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
        ctx.paint()
        return surface

    def patch(self, ctx, atlas, rect):
        x, y, width, height = rect
        ctx.save()
        ctx.rectangle(x, y, width, height)
        ctx.clip()
        ctx.set_source_surface(self.atlases[atlas], 0, 0)
        ctx.paint()
        ctx.restore()

    def text(self, ctx, text, x, y, width=200, height=20, size=13, center=False, color="#eeeeee", wrap=False,
             ellipsize=False):
        layout = self.PangoCairo.create_layout(ctx)
        font = self.Pango.FontDescription(self.font_family)
        font.set_absolute_size(size * self.Pango.SCALE)
        layout.set_font_description(font)
        layout.set_text(str(text), -1)
        if wrap:
            layout.set_width(round(width * self.Pango.SCALE))
            layout.set_height(round(height * self.Pango.SCALE))
            layout.set_wrap(self.Pango.WrapMode.WORD_CHAR)
            layout.set_ellipsize(self.Pango.EllipsizeMode.END)
        _, logical = layout.get_pixel_extents()
        if ellipsize and not wrap and logical.width > width:
            layout.set_width(round(width * self.Pango.SCALE))
            layout.set_ellipsize(self.Pango.EllipsizeMode.END)
            _, logical = layout.get_pixel_extents()
        tx = x + (width - logical.width) / 2 if center else x
        ty = y + (height - logical.height) / 2
        ctx.save()
        ctx.rectangle(x, y, width, height)
        ctx.clip()
        ctx.move_to(tx + 1, ty + 1)
        ctx.set_source_rgba(0, 0, 0, 0.85)
        self.PangoCairo.show_layout(ctx, layout)
        ctx.move_to(tx, ty)
        self.color(ctx, color)
        self.PangoCairo.show_layout(ctx, layout)
        ctx.restore()

    @staticmethod
    def color(ctx, color):
        ctx.set_source_rgb(*(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)))

    def slider(self, ctx, x, y, width, fraction):
        ctx.save()
        gradient = self.cairo.LinearGradient(x, y, x + width, y)
        gradient.add_color_stop_rgb(0, 0.02, 0.25, 0.44)
        gradient.add_color_stop_rgb(1, 0.02, 0.72, 0.91)
        ctx.set_source(gradient)
        ctx.rectangle(x, y, width * fraction, 2)
        ctx.fill()
        cx = x + width * fraction
        ctx.arc(cx, y + 1, 8, 0, 2 * math.pi)
        ctx.set_source_rgb(0, 0, 0)
        ctx.fill_preserve()
        ctx.set_source_rgb(0.03, 0.62, 0.82)
        ctx.set_line_width(2)
        ctx.stroke()
        ctx.restore()

    def generated_mouse(self, ctx, page):
        if self.mouse is None or page not in ("buttons", "backlight"):
            return
        if self.mouse_backdrop is None:
            self.mouse_backdrop = self.make_mouse_backdrop()
        # Alternative artwork intentionally differs from the exact reference.
        # Restore the backdrop from the other atlas before replacing the mouse.
        if page == "buttons":
            replacement = (387, 143, 232, 391)
            x, y, width, height = 391, 144, 222, 381
        else:
            replacement = (151, 155, 224, 394)
            x, y, width, height = 153, 163, 222, 380
        ctx.save()
        ctx.rectangle(*replacement)
        ctx.clip()
        ctx.set_source_surface(self.mouse_backdrop, 0, 0)
        ctx.paint()
        ctx.restore()
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(width / 680, height / 1165)
        ctx.set_source_surface(self.mouse, 0, 0)
        ctx.paint()
        ctx.restore()
        if page == "buttons":
            # Markers follow the supplied illustration's button locations.
            for label, cx, cy in MOUSE_MARKERS:
                ctx.move_to(cx, cy - 12)
                for angle in (-30, 30, 90, 150, 210, 270):
                    a = math.radians(angle)
                    ctx.line_to(cx + 12 * math.cos(a), cy + 12 * math.sin(a))
                ctx.close_path()
                ctx.set_source_rgb(0.01, 0.02, 0.03)
                ctx.fill_preserve()
                ctx.set_source_rgb(0.05, 0.7, 0.88)
                ctx.set_line_width(2)
                ctx.stroke()
                self.text(ctx, label, cx - 12, cy - 11, 24, 22, 14, True)

    def draw(self, ctx, page="buttons", hover=None, focus=None, polling=None,
             generated_mouse=True, can_apply=False, button_labels=None, button_message=None, assignment_source=None,
             has_error=False):
        base = {"buttons": "main_normal", "macros": "mac_normal",
                "performance": "advanced_normal", "backlight": "led_null"}[page]
        ctx.set_source_surface(self.atlases[base], 0, 0)
        ctx.paint()
        # All chrome uses its original atlas coordinates; only the active tab
        # and hovered enabled controls use alternate-state atlas patches.
        for tab in TABS:
            if tab.name == page or tab.name == hover:
                self.patch(ctx, "main_down" if tab.name == page else "main_over",
                           (tab.rect.x, tab.rect.y, tab.rect.width, tab.rect.height))
            self.text(ctx, tab.label, tab.rect.x, 74, tab.rect.width, 30, 13, True)
        self.patch(ctx, "main_down", (300, 620, 67, 70))
        for profile in PROFILES:
            self.text(ctx, profile.label, profile.rect.x - 8, 697, 83, 24, 13, True)
        for label, x in (("Import", 410), ("Export", 483), ("Reset", 553)):
            self.text(ctx, label, x, 697, 60, 24, 13, True)
        for name, rect in (("minimize", (940, 7, 32, 28)), ("close", (977, 7, 34, 28)),
                           ("cancel", (852, 647, 140, 44)), ("apply", (700, 647, 140, 44))):
            if name == hover:
                self.patch(ctx, "main_over", rect)
        if can_apply:
            self.patch(ctx, "main_down", (700, 647, 140, 44))
        self.text(ctx, "Apply", 700, 648, 140, 44, 13, True)
        self.text(ctx, "Cancel", 852, 648, 140, 44, 13, True)
        if generated_mouse:
            self.generated_mouse(ctx, page)
        if page == "buttons":
            for i, label in enumerate(button_labels if button_labels is not None else BUTTON_LABELS):
                self.text(ctx, label, 222 if i < 4 else 693, (236, 311, 385, 460)[i % 4],
                          144, 35, 13, True, ellipsize=True)
            self.text(ctx, "Music-lighting", 5, 580, 100, 20, 13, True)
            if button_message:
                self.text(ctx, button_message, 185, 547, 665 if has_error else 805, 40, 12,
                          color="#c3dbe4", wrap=True)
            if has_error:
                ctx.set_source_rgb(0.035, 0.10, 0.14)
                ctx.rectangle(866, 550, 126, 28)
                ctx.fill_preserve()
                ctx.set_source_rgb(0.06, 0.60, 0.75)
                ctx.set_line_width(1)
                ctx.stroke()
                self.text(ctx, "Error details…", 866, 550, 126, 28, 12, True)
            ctx.set_source_rgb(0.025, 0.10, 0.15)
            ctx.rectangle(657, 510, 292, 32)
            ctx.fill_preserve()
            ctx.set_source_rgb(0.06, 0.60, 0.75)
            ctx.set_line_width(1)
            ctx.stroke()
            self.text(ctx, "Read mouse assignments…", 657, 510, 292, 32, 13, True)
            if assignment_source is None:
                assignment_source = "Reference preview — not mouse state"
            if assignment_source:
                self.text(ctx, assignment_source, 186, 510, 181, 32, 11, color="#a8c8d7", wrap=True)
        elif page == "performance":
            self.performance(ctx, polling)
        elif page == "macros":
            self.macros(ctx)
        else:
            self.backlight(ctx)
        if focus is not None:
            ctx.save()
            ctx.set_source_rgba(0.4, 0.85, 1, 0.9)
            ctx.set_line_width(1)
            ctx.set_dash((3, 3))
            ctx.rectangle(focus.x + 4, focus.y + 4, focus.width - 8, focus.height - 8)
            ctx.stroke()
            ctx.restore()

    def performance(self, ctx, polling):
        for label, y in (("Mouse Sensitivity", 216), ("Scroll Speed", 332), ("Double Click Speed", 448)):
            self.text(ctx, label, 139, y, 210, 23, 13)
        self.text(ctx, "Polling Rate", 568, 216, 200, 23, 13)
        self.text(ctx, "DPI Control", 568, 332, 200, 23, 13)
        for y, fraction, value, suffix, sx in ((255, 0.55, "6", "/ 11", 468),
                                              (371, 0.18, "2", "/ 11", 468),
                                              (487, 0.167, "50", "/ 300ms", 489)):
            self.slider(ctx, 139, y, 291, fraction)
            self.text(ctx, value, 438 if value != "50" else 448, y - 8, 33, 20, 13, True)
            self.text(ctx, suffix, sx, y - 8, 70, 20, 13)
        # 500 Hz is a visual reference until explicitly read. Never call it live.
        selected = polling if polling is not None else 500
        for hz, x in zip((125, 250, 500, 1000), (568, 658, 749, 839)):
            if hz == selected:
                self.patch(ctx, "advanced_down", (x - 1, 249, 54, 31))
        for i, (dpi, x, color) in enumerate(zip((600, 1200, 2400, 4800, 7200, 12800),
                                               (575, 630, 688, 744, 801, 857),
                                               ("#ffff00", "#0800ff", "#ff00e5", "#00f52a", "#ff182b", "#00ffff"))):
            self.patch(ctx, "advanced_down", (x + 3, 362, 19, 19))
            self.text(ctx, dpi, x - 11, 397, 53, 22, 13, True,
                      "#02a7d1" if i == 1 else "#eeeeee")
            self.color(ctx, color)
            ctx.rectangle(x, 428, 26, 5)
            ctx.fill()
        self.slider(ctx, 574, 466, 314, 0.26)

    def macros(self, ctx):
        for label, x, width in (("Macro List", 38, 202), ("Key in macro", 280, 202),
                                 ("Led parameters in macro", 520, 240)):
            self.text(ctx, label, x, 164, width, 23, 13)
        self.text(ctx, "Record", 38, 517, 202, 32, 13, True)
        self.text(ctx, "Insert Event", 280, 517, 202, 32, 13, True)
        for label, y in (("Cycle until the key released", 188),
                         ("Cycle until the key clicked again", 228),
                         ("Specified cycle times", 264)):
            self.text(ctx, label, 776, y, 248, 20, 13)
        self.patch(ctx, "mac_down", (751, 261, 23, 23))
        self.text(ctx, "1", 932, 263, 72, 20, 13, True)

    def backlight(self, ctx):
        self.text(ctx, "Flowing Water Effect", 662, 225, 147, 25, 13, True)
        colors = ("#ffff00", "#0088ff", "#ff0088", "#00ff42", "#ff172b", "#00ffff", "#8000ff")
        for x, color in zip((632, 666, 700, 733, 767, 800, 834), colors):
            self.color(ctx, color)
            ctx.rectangle(x, 289, 19, 18)
            ctx.fill()
            self.patch(ctx, "led_down", (x, 325, 20, 19))
        self.patch(ctx, "led_normal", (662, 378, 169, 8))
        self.patch(ctx, "led_normal", (662, 407, 169, 8))
        self.slider(ctx, 662, 382, 169, 1)
        self.slider(ctx, 662, 411, 169, 1)
        self.text(ctx, "Brightness", 595, 375, 65, 20, 13)
        self.text(ctx, "Speed", 620, 402, 40, 20, 13)
        for label, x, y, width in (("Symmetry", 634, 440, 100), ("Clockwise", 634, 463, 115),
                                    ("Anti Clockwise", 772, 463, 115), ("Two way", 634, 486, 100),
                                    ("Overwrite", 772, 486, 115)):
            self.text(ctx, label, x, y, width, 19, 13)
        for rect in ((615, 443, 12, 12), (615, 466, 12, 12), (753, 466, 12, 12),
                     (615, 488, 12, 12), (753, 488, 12, 12)):
            self.patch(ctx, "led_normal", rect)
        self.patch(ctx, "led_down", (615, 466, 12, 12))

    def export(self, destination, scale=1, generated_mouse=True):
        from .ui_layout import PAGES
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for page in PAGES:
            surface = self.cairo.ImageSurface(self.cairo.FORMAT_ARGB32,
                                               round(WIDTH * scale), round(HEIGHT * scale))
            ctx = self.cairo.Context(surface)
            ctx.scale(scale, scale)
            self.draw(ctx, page, generated_mouse=generated_mouse)
            surface.write_to_png(str(destination / f"{page}.png"))
