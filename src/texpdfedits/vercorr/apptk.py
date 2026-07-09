import bisect
import tkinter as tk
from tkinter import ttk
from tkinter import font
from PIL import Image, ImageTk  # pip install Pillow
from pathlib import Path

import texpdfedits.vercorr.manu as manu
from texpdfedits.vercorr.manu import Manuscript
from texpdfedits.extractanns import XrefObj

# ---------------------------------------------------------------------------
# Placeholder data -- replace with your real PDF-backed values.
# ---------------------------------------------------------------------------

STATUS_OPTIONS = [
    XrefObj.STATUS_NONE,
    XrefObj.STATUS_ACCEPTED,
    XrefObj.STATUS_REJECTED,
    XrefObj.STATUS_CANCELLED,
    XrefObj.STATUS_COMPLETED,
]

# ---------------------------------------------------------------------------
# Configuration -- every visual/behavioral constant lives here, grouped by
# category, so tweaking the look or feel never means hunting through the
# widget-building code below.
# ---------------------------------------------------------------------------

# --- Window ---
WINDOW_TITLE = "Correction Review"
WINDOW_SIZE = "1000x700"

# --- Layout proportions (relative to the whole window; must stay in [0, 1]) ---
PANEL_PROPORTION = 0.25   # right-hand annotation panel: fraction of window WIDTH
DIVISION_PROP = 0.025      # divider line: fraction of window HEIGHT

# --- Colors ---
DEFAULT_BG = "black"
DEFAULT_FG = "white"
SELECTED_BG = "#2f6fba"
SELECTED_FG = "white"
REPLY_FG = "#bbbbbb"
META_FG = "#999999"
DIVIDER_BG = "#444444"
IMAGE_AREA_BG = "gray85"          # letterbox color behind top/bottom images
BOX_BORDER_COLOR = "gray30"       # thin border around each annotation box

# --- Scrollbar ---
SCROLLBAR_WIDTH = 18
SCROLLBAR_TROUGH_COLOR = "#222222"
SCROLLBAR_BG = "#555555"
SCROLLBAR_ACTIVE_BG = "#777777"

# --- Fonts ---
FONT_FAMILY = "Ubuntu Mono"
FONT_SIZE_TYPE = 16        # annotation type label (e.g. "Highlight"), bold
FONT_SIZE_COMMENT = 15
FONT_SIZE_META = 14        # page number, replies
FONT_SIZE_NO_IMG = 50
TYPE_FONT = (FONT_FAMILY, FONT_SIZE_TYPE, "bold")
META_FONT = (FONT_FAMILY, FONT_SIZE_META)
COMMENT_FONT = (FONT_FAMILY, FONT_SIZE_COMMENT)
REPLY_FONT = (FONT_FAMILY, FONT_SIZE_META)
NO_IMG_FONT = (FONT_FAMILY, FONT_SIZE_NO_IMG, "bold")

# --- Spacing / padding within each annotation box ---
BOX_BORDER_WIDTH = 1
BOX_INNER_PADX = 8
BOX_INNER_PADY = 6
BOX_OUTER_PADX = 6         # space between adjacent boxes and the panel edges
BOX_OUTER_PADY = 4
COMMENT_TOP_PADDING = 4
REPLY_INDENT = 15          # left indent for reply lines, relative to comment
REPLY_TOP_PADDING = 2
CONTROLS_TOP_PADDING = 6
STATUS_DROPDOWN_WIDTH = 9
CONTROL_ROW_HEIGHT = 30    # vertical space reserved for the checkbox/dropdown row

CHECKBOX_PADX = 20

# --- Text wrapping (comment/reply text rewraps as the panel is resized) ---
WRAP_LENGTH_PADDING = 40   # subtracted from panel pixel width to get wraplength
MIN_WRAP_LENGTH = 50       # never wrap narrower than this, even in a tiny panel

# --- Image containers: fallback size used only before the window has been
#     drawn once and real container dimensions aren't available yet ---
FALLBACK_CONTAINER_WIDTH = 400
FALLBACK_CONTAINER_HEIGHT = 300

# --- Timing ---
RESIZE_DEBOUNCE_MS = 100      # wait this long after a resize before rescaling images / relayout
INITIAL_SELECT_DELAY_MS = 50  # wait for first layout pass before selecting annotation 0

# --- Keyboard shortcuts (each maps to a list of Tk event sequences) ---
KEY_NEXT = ["<Key-n>", "<Down>"]
KEY_PREV = ["<Key-p>", "<Up>"]

KEY_SHORTCUT_NONE = ["<Key-d>"]
KEY_SHORTCUT_ACCEPTED = ["<Key-a>"]
KEY_SHORTCUT_REJECTED = ["<Key-r>"]
KEY_SHORTCUT_COMPLETED = ["<Key-c>"]
KEY_SHORTCUT_CANCELLED = ["<Key-x>"]
KEY_TOGGLE_CHECKED = ["<Key-m>"]


# ---------------------------------------------------------------------------
# Annotation list panel.
#
# Each row is drawn directly as Canvas items (text + a background rectangle)
# instead of as a tree of native widgets (Frame/Label/...). Canvas is built
# to scroll drawn items efficiently and doesn't suffer the redraw glitches
# that come from scrolling many embedded native windows -- that combination
# (Canvas + create_window + lots of child widgets, scrolled via yview) is a
# known rough edge in Tk, not something you can code your way around by
# being clever about which widgets exist at a given moment.
#
# Only the *currently selected* row gets real interactive widgets (the
# status dropdown and the checkbox), overlaid via a single create_window
# call that moves to the new row on selection change. At most one small
# set of native widgets is ever alive in the whole panel.
# ---------------------------------------------------------------------------
class AnnotationPanel(tk.Frame):
    def __init__(self, master, annotations, man, on_select, on_check_toggle, on_status_change):
        super().__init__(master, bg=DEFAULT_BG)
        self.annotations = annotations
        self.man = man
        self.on_select = on_select
        self.on_check_toggle = on_check_toggle
        self.on_status_change = on_status_change

        self.canvas = tk.Canvas(self, highlightthickness=0, bg=DEFAULT_BG)
        # Classic tk.Scrollbar instead of ttk.Scrollbar: always shows a
        # visible trough + draggable thumb (plus arrow buttons), rather
        # than following macOS's thin auto-hiding Aqua scrollbar style.
        self.scrollbar = tk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview,
            width=SCROLLBAR_WIDTH, troughcolor=SCROLLBAR_TROUGH_COLOR,
            bg=SCROLLBAR_BG, activebackground=SCROLLBAR_ACTIVE_BG,
            highlightthickness=0,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.row_layout = []   # per-annotation dict of item ids / geometry
        self._tops = []        # parallel list of row["top"], for hit-testing
        self._total_height = 0
        self.selected_index = None
        self._controls = None  # currently-alive real widgets, or None
        self._resize_job = None

        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self._on_click)

        # Mouse wheel support: bound globally, filtered by whether the
        # pointer is over this panel (works for clicks landing on the
        # embedded control frame too, since its widget path is nested
        # under the canvas's path).
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel_global)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_global)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_global)

        self._layout_all()

    # ------------------------------------------------------------------
    # Layout: draw every row as canvas items. Cheap even for thousands of
    # annotations, since canvas items aren't OS windows.
    # ------------------------------------------------------------------
    def _page_text(self, annotation):
        before_page = annotation.pageno + 1  # both pages are 0-based
        if annotation.xref not in self.man.xref_to_synctex:
            after_page = 'none'
        else:
            line, synctex_out = self.man.xref_to_synctex[annotation.xref]
            pageno = synctex_out.page + 1
            after_page = f'{pageno}, line {line}'
        return f"Page {before_page} vs. {after_page}"

    def _layout_all(self):
        previously_selected = self.selected_index

        self._destroy_controls()
        self.canvas.delete("all")
        self.row_layout = []
        self._tops = []

        width = self.canvas.winfo_width()
        if width <= 1:
            width = FALLBACK_CONTAINER_WIDTH
        wrap = max(width - WRAP_LENGTH_PADDING, MIN_WRAP_LENGTH)
        left = BOX_OUTER_PADX + BOX_INNER_PADX
        right = width - BOX_OUTER_PADX - BOX_INNER_PADX

        y = BOX_OUTER_PADY
        for i, annotation in enumerate(self.annotations):
            row_top = y
            content_top = y + BOX_INNER_PADY

            type_id = self.canvas.create_text(
                left, content_top, anchor="nw", text=annotation.type,
                font=TYPE_FONT, fill=DEFAULT_FG,
            )
            page_id = self.canvas.create_text(
                right, content_top, anchor="ne", text=self._page_text(annotation),
                font=META_FONT, fill=META_FG,
            )
            header_bottom = max(self.canvas.bbox(type_id)[3], self.canvas.bbox(page_id)[3])

            comment_id = self.canvas.create_text(
                left, header_bottom + COMMENT_TOP_PADDING, anchor="nw",
                text=f"\"{annotation.comment}\"", font=COMMENT_FONT, fill=DEFAULT_FG,
                width=wrap,
            )
            cursor = self.canvas.bbox(comment_id)[3]

            reply_ids = []
            for reply in annotation.responses:
                reply_id = self.canvas.create_text(
                    left + REPLY_INDENT, cursor + REPLY_TOP_PADDING, anchor="nw",
                    text=f"\u21b3 \"{reply}\"", font=REPLY_FONT, fill=REPLY_FG,
                    width=max(wrap - REPLY_INDENT, MIN_WRAP_LENGTH),
                )
                cursor = self.canvas.bbox(reply_id)[3]
                reply_ids.append(reply_id)

            control_y = cursor + CONTROLS_TOP_PADDING
            index_id = self.canvas.create_text(
                right, control_y, anchor="ne", text=str(i + 1),
                font=META_FONT, fill=META_FG,
            )

            row_bottom = control_y + CONTROL_ROW_HEIGHT + BOX_INNER_PADY
            rect_id = self.canvas.create_rectangle(
                BOX_OUTER_PADX, row_top, width - BOX_OUTER_PADX, row_bottom,
                outline=BOX_BORDER_COLOR, width=BOX_BORDER_WIDTH, fill=DEFAULT_BG,
            )
            self.canvas.tag_lower(rect_id)  # behind the text items of this row

            self.row_layout.append({
                "top": row_top, "bottom": row_bottom, "control_y": control_y,
                "rect_id": rect_id, "type_id": type_id, "page_id": page_id,
                "comment_id": comment_id, "reply_ids": reply_ids, "index_id": index_id,
            })
            self._tops.append(row_top)
            y = row_bottom + BOX_OUTER_PADY

        self._total_height = y
        self.canvas.configure(scrollregion=(0, 0, width, self._total_height))

        if previously_selected is not None and previously_selected < len(self.annotations):
            self.select(previously_selected, scroll=False)

    def _on_resize(self, event):
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(RESIZE_DEBOUNCE_MS, self._layout_all)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    def select(self, index, scroll=True):
        if self.selected_index is not None and self.selected_index < len(self.row_layout):
            self._set_row_colors(self.selected_index, selected=False)
        self.selected_index = index
        self._set_row_colors(index, selected=True)
        self._create_controls_for_row(index)
        if scroll:
            self._scroll_to_row(index)

    def refresh_controls(self):
        """Re-read the annotation's current status/checked state into the
        live widgets. Call this after changing status/checked via a
        keyboard shortcut rather than by interacting with the widgets
        directly, so the displayed dropdown/checkbox stays in sync."""
        if self._controls is not None:
            self._create_controls_for_row(self._controls["index"])

    def _set_row_colors(self, index, selected):
        row = self.row_layout[index]
        bg = SELECTED_BG if selected else DEFAULT_BG
        fg = SELECTED_FG if selected else DEFAULT_FG
        meta_fg = SELECTED_FG if selected else META_FG
        reply_fg = SELECTED_FG if selected else REPLY_FG
        self.canvas.itemconfig(row["rect_id"], fill=bg)
        self.canvas.itemconfig(row["type_id"], fill=fg)
        self.canvas.itemconfig(row["page_id"], fill=meta_fg)
        self.canvas.itemconfig(row["comment_id"], fill=fg)
        self.canvas.itemconfig(row["index_id"], fill=meta_fg)
        for rid in row["reply_ids"]:
            self.canvas.itemconfig(rid, fill=reply_fg)

    def _scroll_to_row(self, index):
        self.canvas.update_idletasks()
        if self._total_height <= 0:
            return
        row = self.row_layout[index]
        visible_top = self.canvas.canvasy(0)
        visible_height = self.canvas.winfo_height()
        visible_bottom = visible_top + visible_height
        if row["top"] < visible_top:
            self.canvas.yview_moveto(row["top"] / self._total_height)
        elif row["bottom"] > visible_bottom:
            self.canvas.yview_moveto((row["bottom"] - visible_height) / self._total_height)

    # ------------------------------------------------------------------
    # Controls: real widgets, only ever for the selected row.
    # ------------------------------------------------------------------
    def _create_controls_for_row(self, index):
        self._destroy_controls()
        annotation = self.annotations[index]
        row = self.row_layout[index]

        frame = tk.Frame(self.canvas, bg=SELECTED_BG)

        status_var = tk.StringVar(value=str(annotation.status.state))
        dropdown = ttk.Combobox(
            frame, textvariable=status_var, values=STATUS_OPTIONS,
            state="readonly", width=STATUS_DROPDOWN_WIDTH,
        )
        dropdown.pack(side="left")
        dropdown.bind(
            "<<ComboboxSelected>>",
            lambda e: self.on_status_change(index, status_var.get()),
        )
        # Don't let the mouse wheel silently change the value while
        # scrolling the panel -- redirect that scroll to the panel instead.
        dropdown.bind("<MouseWheel>", self._redirect_scroll)
        dropdown.bind("<Button-4>", self._redirect_scroll)
        dropdown.bind("<Button-5>", self._redirect_scroll)

        is_checked = annotation.checkmark.state == XrefObj.CHECKED
        checked_var = tk.BooleanVar(value=is_checked)
        checkbox = tk.Checkbutton(
            frame, variable=checked_var,
            bg=SELECTED_BG, fg=SELECTED_FG, selectcolor=SELECTED_BG,
            activebackground=SELECTED_BG, activeforeground=SELECTED_FG,
            command=lambda: self.on_check_toggle(index, checked_var.get()),
        )
        checkbox.pack(side="left", padx=CHECKBOX_PADX)

        window_id = self.canvas.create_window(
            BOX_OUTER_PADX + BOX_INNER_PADX, row["control_y"], anchor="nw", window=frame,
        )

        self._controls = {"frame": frame, "window_id": window_id, "index": index}

    def _destroy_controls(self):
        if self._controls is not None:
            self.canvas.delete(self._controls["window_id"])
            self._controls["frame"].destroy()
            self._controls = None

    def _redirect_scroll(self, event):
        self._on_mousewheel(event)
        return "break"  # stop the combobox's own wheel handling

    # ------------------------------------------------------------------
    # Hit testing / scrolling
    # ------------------------------------------------------------------
    def _on_click(self, event):
        y = self.canvas.canvasy(event.y)
        idx = self._row_at(y)
        if idx is not None:
            self.on_select(idx)

    def _row_at(self, y):
        i = bisect.bisect_right(self._tops, y) - 1
        if 0 <= i < len(self.row_layout) and y <= self.row_layout[i]["bottom"]:
            return i
        return None

    def _on_mousewheel_global(self, event):
        if not self._is_within_panel(event.widget):
            return
        self._on_mousewheel(event)

    def _is_within_panel(self, widget):
        try:
            widget_path = str(widget)
            return widget_path == str(self.canvas) or widget_path.startswith(str(self.canvas))
        except Exception:
            return False

    def _on_mousewheel(self, event):
        # Treat every wheel "tick" as one scroll unit (see note in the
        # original ScrollableFrame about why sign-only is more robust
        # than dividing event.delta by 120).
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self.canvas.yview_scroll(-1, "units")
        else:
            self.canvas.yview_scroll(1, "units")


# ---------------------------------------------------------------------------
# Main application frame.
# ---------------------------------------------------------------------------
class CopyEditReviewApp(tk.Frame):
    def __init__(self, master, man: Manuscript):
        super().__init__(master, bg=DEFAULT_BG)
        self.grid(row=0, column=0, sticky="nsew")
        master.grid_rowconfigure(0, weight=1)
        master.grid_columnconfigure(0, weight=1)

        self.man = man
        self.annotations = self.man.gui_annotations
        self.selected_index = 0

        self._top_photo = None
        self._bottom_photo = None
        self._resize_job = None

        self._build_ui()
        self._bind_shortcuts()

        self.after(INITIAL_SELECT_DELAY_MS, lambda: self._select_annotation(0))

    # ------------------------------------------------------------------
    def _build_ui(self):
        image_frame_width = 1 - PANEL_PROPORTION
        each_image_height = (1 - DIVISION_PROP) / 2

        self.top_frame = tk.Frame(self, bg=IMAGE_AREA_BG)
        self.top_frame.place(relx=0, rely=0, relwidth=image_frame_width, relheight=each_image_height)

        self.divider = tk.Frame(self, bg=DIVIDER_BG)
        self.divider.place(
            relx=0, rely=each_image_height, relwidth=image_frame_width, relheight=DIVISION_PROP
        )

        self.bottom_frame = tk.Frame(self, bg=IMAGE_AREA_BG)
        self.bottom_frame.place(
            relx=0, rely=each_image_height + DIVISION_PROP,
            relwidth=image_frame_width, relheight=each_image_height,
        )

        self.top_image_label = tk.Label(self.top_frame, bg=self.top_frame["bg"])
        self.top_image_label.place(relx=0.5, rely=0.5, anchor="center")

        self.bottom_image_label = tk.Label(self.bottom_frame, bg=self.bottom_frame["bg"])
        self.bottom_image_label.place(relx=0.5, rely=0.5, anchor="center")

        self.top_frame.bind("<Configure>", lambda e: self._schedule_resize())
        self.bottom_frame.bind("<Configure>", lambda e: self._schedule_resize())

        # --- Right-hand proportional-width annotation panel ---
        self.panel = AnnotationPanel(
            self,
            annotations=self.annotations,
            man=self.man,
            on_select=self._select_annotation,
            on_check_toggle=self._on_check_toggle,
            on_status_change=self._on_status_change,
        )
        self.panel.place(relx=image_frame_width, rely=0, relwidth=PANEL_PROPORTION, relheight=1)

    def _bind_shortcuts(self):
        top = self.winfo_toplevel()
        for key in KEY_NEXT:
            top.bind(key, lambda e: self._navigate(1))
        for key in KEY_PREV:
            top.bind(key, lambda e: self._navigate(-1))
        for key in KEY_TOGGLE_CHECKED:
            top.bind(key, lambda e: self._toggle_current_checked())
        for key in KEY_SHORTCUT_NONE:
            top.bind(key, lambda e: self._shortcut_change_status(XrefObj.STATUS_NONE))
        for key in KEY_SHORTCUT_ACCEPTED:
            top.bind(key, lambda e: self._shortcut_change_status(XrefObj.STATUS_ACCEPTED))
        for key in KEY_SHORTCUT_REJECTED:
            top.bind(key, lambda e: self._shortcut_change_status(XrefObj.STATUS_REJECTED))
        for key in KEY_SHORTCUT_COMPLETED:
            top.bind(key, lambda e: self._shortcut_change_status(XrefObj.STATUS_COMPLETED))
        for key in KEY_SHORTCUT_CANCELLED:
            top.bind(key, lambda e: self._shortcut_change_status(XrefObj.STATUS_CANCELLED))

    # ------------------------------------------------------------------
    # Selection / navigation
    # ------------------------------------------------------------------
    def _select_annotation(self, index):
        self.selected_index = index
        self.panel.select(index)
        self._load_current_pair()

    def _navigate(self, delta):
        new_index = (self.selected_index + delta) % len(self.annotations)
        self._select_annotation(new_index)

    def _toggle_current_checked(self):
        annotation = self.annotations[self.selected_index]
        new_checked = annotation.checkmark.state != XrefObj.CHECKED
        self._on_check_toggle(self.selected_index, new_checked)
        self.panel.refresh_controls()

    def _shortcut_change_status(self, status):
        self._on_status_change(self.selected_index, status)
        self.panel.refresh_controls()

    def _on_check_toggle(self, index, checked):
        annotation = self.annotations[index]
        if checked:
            annotation.checkmark.state = XrefObj.CHECKED
        else:
            annotation.checkmark.state = XrefObj.UNCHECKED
        self.man.update_from_tannot(annotation.checkmark)
        # TODO: persist this change to your real annotation store.

    def _on_status_change(self, index, status):
        annotation = self.annotations[index]
        annotation.status.state = status
        self.man.update_from_tannot(annotation.status)
        # TODO: persist this change to your real annotation store.

    # ------------------------------------------------------------------
    # Image loading / resizing
    # ------------------------------------------------------------------
    def _schedule_resize(self):
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(RESIZE_DEBOUNCE_MS, self._load_current_pair)

    def _load_current_pair(self):
        self._resize_job = None
        annotation = self.annotations[self.selected_index]

        top_path = annotation.before_path
        bottom_path = annotation.after_path

        if top_path is None or not Path(top_path).exists():
            self.top_image_label.config(image="", text="Not available", font=NO_IMG_FONT)
            self._top_photo = None
        else:
            self._top_photo = self._load_image_fit(top_path, self.top_frame)
            self.top_image_label.config(image=self._top_photo)

        if bottom_path is None or not Path(bottom_path).exists():
            self.bottom_image_label.config(image="", text="Not available", font=NO_IMG_FONT)
            self._bottom_photo = None
        else:
            self._bottom_photo = self._load_image_fit(bottom_path, self.bottom_frame)
            self.bottom_image_label.config(image=self._bottom_photo)
        return

    def _load_image_fit(self, path, container):
        container.update_idletasks()
        box_w = container.winfo_width()
        box_h = container.winfo_height()
        if box_w <= 1 or box_h <= 1:
            box_w, box_h = FALLBACK_CONTAINER_WIDTH, FALLBACK_CONTAINER_HEIGHT

        img = Image.open(path)
        img_ratio = img.width / img.height
        box_ratio = box_w / box_h

        if img_ratio > box_ratio:
            new_w = box_w
            new_h = max(int(box_w / img_ratio), 1)
        else:
            new_h = box_h
            new_w = max(int(box_h * img_ratio), 1)

        img = img.resize((new_w, new_h), Image.LANCZOS)
        return ImageTk.PhotoImage(img)


def on_quit(root, app):
    """
    Called when the user tries to close the window (X button, and on
    Mac, also wired up to Cmd+Q / the app menu below). This is your
    hook to check e.g. whether any annotation changes are unsaved and
    decide whether to actually exit.
    """
    # TODO: replace with your real "do I need to save anything?" check.
    unsaved_changes = False  # placeholder

    if unsaved_changes:
        # e.g. prompt the user, write out changes, etc. For now just
        # print so you can see the hook firing.
        print("Would prompt to save changes here.")

    app.man.save()

    root.destroy()

def run_gui(man: Manuscript):
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry(WINDOW_SIZE)

    # --- App icon ---
    # Cross-platform (PNG/GIF), sets window/taskbar icon on Windows/Linux:
    #     icon_image = tk.PhotoImage(file="path/to/icon.png")
    #     root.iconphoto(True, icon_image)
    # Windows-only, for a native .ico file instead:
    #     root.iconbitmap("path/to/icon.ico")

    app = CopyEditReviewApp(root, man)

    # --- Quit hook ---
    root.protocol("WM_DELETE_WINDOW", lambda: on_quit(root, app))
    # macOS: Cmd+Q / app-menu quit bypasses WM_DELETE_WINDOW, needs its own hook.
    root.createcommand("::tk::mac::Quit", lambda: on_quit(root, app))

    root.mainloop()
