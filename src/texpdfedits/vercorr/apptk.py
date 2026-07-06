import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk  # pip install Pillow
from pathlib import Path

import texpdfedits.vercorr.manu as manu
from texpdfedits.vercorr.manu import Manuscript
from texpdfedits.extractanns import TextAnnotXrefObj

# ---------------------------------------------------------------------------
# Placeholder data -- replace with your real PDF-backed values.
# ---------------------------------------------------------------------------

STATUS_OPTIONS = [
    TextAnnotXrefObj.STATUS_NONE,
    TextAnnotXrefObj.STATUS_ACCEPTED,
    TextAnnotXrefObj.STATUS_REJECTED,
    TextAnnotXrefObj.STATUS_CANCELLED,
    TextAnnotXrefObj.STATUS_COMPLETED,
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
PANEL_PROPORTION = 0.225   # right-hand annotation panel: fraction of window WIDTH
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
FONT_FAMILY = "Arial"
FONT_SIZE_TYPE = 14        # annotation type label (e.g. "Highlight"), bold
FONT_SIZE_BODY = 13        # default/unspecified body text size
FONT_SIZE_META = 12        # page number, replies
FONT_SIZE_NO_IMG = 50
TYPE_FONT = (FONT_FAMILY, FONT_SIZE_TYPE, "bold")
META_FONT = (FONT_FAMILY, FONT_SIZE_META)
REPLY_FONT = (FONT_FAMILY, FONT_SIZE_META)
NO_IMG_FONT = (FONT_FAMILY, FONT_SIZE_NO_IMG, "bold")

# --- Spacing / padding within each annotation box ---
BOX_BORDER_WIDTH = 1
BOX_HIGHLIGHT_THICKNESS = 1
BOX_INNER_PADX = 8
BOX_INNER_PADY = 6
BOX_OUTER_PADX = 6         # space between adjacent boxes and the panel edges
BOX_OUTER_PADY = 4
COMMENT_TOP_PADDING = 4
REPLY_INDENT = 15          # left indent for reply lines, relative to comment
REPLY_TOP_PADDING = 2
CONTROLS_TOP_PADDING = 6
STATUS_DROPDOWN_WIDTH = 9

# --- Text wrapping (comment/reply labels rewrap as the panel is resized) ---
WRAP_LENGTH_PADDING = 40   # subtracted from panel pixel width to get wraplength
MIN_WRAP_LENGTH = 50       # never wrap narrower than this, even in a tiny panel

# --- Image containers: fallback size used only before the window has been
#     drawn once and real container dimensions aren't available yet ---
FALLBACK_CONTAINER_WIDTH = 400
FALLBACK_CONTAINER_HEIGHT = 300

# --- Timing ---
RESIZE_DEBOUNCE_MS = 100      # wait this long after a resize before rescaling images
INITIAL_SELECT_DELAY_MS = 50  # wait for first layout pass before selecting annotation 0

# --- Keyboard shortcuts (each maps to a list of Tk event sequences) ---
KEY_NEXT = ["<Key-n>", "<Down>"]
KEY_PREV = ["<Key-p>", "<Up>"]
KEY_TOGGLE_CHECKED = ["<Key-m>"]


# ---------------------------------------------------------------------------
# Scrollable container -- standard Tkinter canvas+scrollbar pattern.
# ---------------------------------------------------------------------------
class ScrollableFrame(tk.Frame):
    """A vertically scrollable frame. Add children to `self.inner`."""

    def __init__(self, master):
        super().__init__(master, bg=DEFAULT_BG)

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
        self.inner = tk.Frame(self.canvas, bg=DEFAULT_BG)

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self._inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Keep the inner frame's width pinned to the canvas width.
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._inner_window, width=e.width),
        )

        # Pack the scrollbar FIRST so it always reserves its own strip of
        # space, then let the canvas fill whatever remains. Packing the
        # canvas first (with expand=True) let it greedily claim the whole
        # cavity before the scrollbar got a turn, so the scrollbar would
        # collapse to zero width whenever the panel was narrow.
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Mouse wheel support: bound once, globally, and filtered by
        # whether the pointer is actually over this panel. (An earlier
        # Enter/Leave-based bind/unbind was the source of buggy scrolling
        # -- child widgets like labels/checkboxes sit on top of the
        # canvas, so moving over them fires <Leave> on the canvas itself,
        # repeatedly toggling the binding on and off.)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel_global)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_global)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_global)

    def _on_mousewheel_global(self, event):
        if not self._is_within_panel(event.widget):
            return
        self._on_mousewheel(event)

    def _is_within_panel(self, widget):
        try:
            widget_path = str(widget)
            return widget_path == str(self.canvas) or widget_path.startswith(str(self.inner))
        except Exception:
            return False

    def _on_mousewheel(self, event):
        # Treat every wheel "tick" as one scroll unit. (Using event.delta's
        # raw magnitude via floor division caused an up/down asymmetry --
        # on trackpads/some platforms delta is a small number like +-1 or
        # +-2 rather than +-120, and `// 120` silently rounds one
        # direction to zero. Just checking the sign is more robust.)
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self.canvas.yview_scroll(-1, "units")
        else:
            self.canvas.yview_scroll(1, "units")

    def scroll_to_widget(self, widget):
        self.inner.update_idletasks()
        widget_top = widget.winfo_y()
        widget_bottom = widget_top + widget.winfo_height()
        inner_height = self.inner.winfo_height()
        if inner_height <= 0:
            return

        visible_top = self.canvas.canvasy(0)
        visible_bottom = visible_top + self.canvas.winfo_height()

        if widget_top < visible_top:
            self.canvas.yview_moveto(widget_top / inner_height)
        elif widget_bottom > visible_bottom:
            self.canvas.yview_moveto((widget_bottom - self.canvas.winfo_height()) / inner_height)


# ---------------------------------------------------------------------------
# One annotation entry in the right-hand list.
# ---------------------------------------------------------------------------
class AnnotationBox(tk.Frame):
    def __init__(self, master, index, annotation, man, on_select, on_check_toggle, on_status_change,
                 redirect_scroll):
        super().__init__(
            master, bg=DEFAULT_BG, bd=BOX_BORDER_WIDTH, relief="solid",
            padx=BOX_INNER_PADX, pady=BOX_INNER_PADY,
            highlightbackground=BOX_BORDER_COLOR, highlightthickness=BOX_HIGHLIGHT_THICKNESS,
        )
        self.index = index
        self.annotation = annotation
        self.man = man

        header = tk.Frame(self, bg=DEFAULT_BG)
        header.pack(fill="x")
        
        type_label = tk.Label(
            header, text=annotation.type, font=TYPE_FONT, bg=DEFAULT_BG, fg=DEFAULT_FG,
        )
        type_label.pack(side="left")

        before_page = annotation.pageno + 1 # both pages are 0-based
        if annotation.xref not in self.man.xref_to_synctex:
            after_page = 'none'
        else:
            line, synctex_out = self.man.xref_to_synctex[annotation.xref]
            pageno = synctex_out.page + 1
            after_page = f'{pageno}, line {line}'
        page_label = tk.Label(
            header, text=f"Page {before_page} vs. {after_page}", font=META_FONT, bg=DEFAULT_BG, fg=META_FG,
        )
        page_label.pack(side="right")

        comment_label = tk.Label(
            self, text=annotation.comment, justify="left", anchor="w",
            bg=DEFAULT_BG, fg=DEFAULT_FG,
        )
        comment_label.pack(fill="x", pady=(COMMENT_TOP_PADDING, 0))

        reply_widgets = []
        for reply in annotation.responses:
            reply_label = tk.Label(
                self, text=f"\u21b3 {reply}", justify="left", anchor="w",
                font=REPLY_FONT, bg=DEFAULT_BG, fg=REPLY_FG,
            )
            reply_label.pack(fill="x", padx=(REPLY_INDENT, 0), pady=(REPLY_TOP_PADDING, 0))
            reply_widgets.append(reply_label)

        controls = tk.Frame(self, bg=DEFAULT_BG)
        controls.pack(fill="x", pady=(CONTROLS_TOP_PADDING, 0))

        is_checked = annotation.checkmark.state == TextAnnotXrefObj.CHECKMARK_CHECKED
        self.checked_var = tk.BooleanVar(value=is_checked)
        self.checkbox = tk.Checkbutton(
            controls, text="Checked", variable=self.checked_var,
            bg=DEFAULT_BG, fg=DEFAULT_FG, selectcolor=DEFAULT_BG,
            activebackground=DEFAULT_BG, activeforeground=DEFAULT_FG,
            command=lambda: (on_select(self.index), on_check_toggle(self.index, self.checked_var.get())),
        )
        self.checkbox.pack(side="left")

        ann_status = annotation.status.state
        self.status_var = tk.StringVar(value=str(ann_status))
        self.status_dropdown = ttk.Combobox(
            controls, textvariable=self.status_var, values=STATUS_OPTIONS,
            state="readonly", width=STATUS_DROPDOWN_WIDTH,
        )
        self.status_dropdown.pack(side="right")
        self.status_dropdown.bind(
            "<<ComboboxSelected>>",
            lambda e: (on_select(self.index), on_status_change(self.index, self.status_var.get())),
        )
        # Don't let the mouse wheel silently change the value while
        # scrolling the panel -- redirect that scroll to the panel instead.
        self.status_dropdown.bind("<MouseWheel>", redirect_scroll)
        self.status_dropdown.bind("<Button-4>", redirect_scroll)
        self.status_dropdown.bind("<Button-5>", redirect_scroll)

        self.wrap_labels = [comment_label] + reply_widgets
        self._themed_widgets = [self, header, type_label, page_label, comment_label, controls] + reply_widgets

        for widget in [self, header, type_label, page_label, comment_label] + reply_widgets:
            widget.bind("<Button-1>", lambda e: on_select(self.index))

    def set_selected(self, selected):
        bg = SELECTED_BG if selected else DEFAULT_BG
        for widget in self._themed_widgets:
            widget.config(bg=bg)
        self.checkbox.config(bg=bg, activebackground=bg)


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

        self.boxes = []

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

        # --- Right-hand proportional-width scrollable annotation panel ---
        self.panel = ScrollableFrame(self)
        self.panel.place(relx=image_frame_width, rely=0, relwidth=PANEL_PROPORTION, relheight=1)
        # Reflow comment/reply text wrapping whenever the panel is resized
        # (either from a window resize, or if you tweak PANEL_PROPORTION).
        self.panel.canvas.bind("<Configure>", self._on_panel_resize, add="+")

        for i, annotation in enumerate(self.annotations):
            box = AnnotationBox(
                self.panel.inner,
                index=i,
                annotation=annotation,
                man=self.man,
                on_select=self._select_annotation,
                on_check_toggle=self._on_check_toggle,
                on_status_change=self._on_status_change,
                redirect_scroll=self._redirect_scroll_to_panel,
            )
            box.pack(fill="x", padx=BOX_OUTER_PADX, pady=BOX_OUTER_PADY)
            self.boxes.append(box)

    def _redirect_scroll_to_panel(self, event):
        self.panel._on_mousewheel(event)
        return "break"  # stop the combobox's own wheel handling

    def _on_panel_resize(self, event):
        wrap = max(event.width - WRAP_LENGTH_PADDING, MIN_WRAP_LENGTH)
        for box in self.boxes:
            for label in box.wrap_labels:
                label.config(wraplength=wrap)

    def _bind_shortcuts(self):
        top = self.winfo_toplevel()
        for key in KEY_NEXT:
            top.bind(key, lambda e: self._navigate(1))
        for key in KEY_PREV:
            top.bind(key, lambda e: self._navigate(-1))
        for key in KEY_TOGGLE_CHECKED:
            top.bind(key, lambda e: self._toggle_current_checked())

    # ------------------------------------------------------------------
    # Selection / navigation
    # ------------------------------------------------------------------
    def _select_annotation(self, index):
        self.boxes[self.selected_index].set_selected(False)
        self.selected_index = index
        self.boxes[self.selected_index].set_selected(True)
        self.panel.scroll_to_widget(self.boxes[self.selected_index])
        self._load_current_pair()

    def _navigate(self, delta):
        new_index = (self.selected_index + delta) % len(self.annotations)
        self._select_annotation(new_index)

    def _toggle_current_checked(self):
        box = self.boxes[self.selected_index]
        box.checked_var.set(not box.checked_var.get())
        self._on_check_toggle(self.selected_index, box.checked_var.get())

    def _on_check_toggle(self, index, checked):
        annotation = self.annotations[index]
        if checked:
            annotation.checkmark.state = TextAnnotXrefObj.CHECKMARK_CHECKED
        else:
            annotation.checkmark.state = TextAnnotXrefObj.CHECKMARK_UNCHECKED
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
