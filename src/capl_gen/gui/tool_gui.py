import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk

# Placeholder logger
class DummyLogger:
    def info(self, msg): print(f"INFO: {msg}")
    def error(self, msg): print(f"ERROR: {msg}")
log = DummyLogger()

def get_asset_path(filename: str) -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        bundle_path = Path(sys._MEIPASS) / "gui" / "images" / filename
        if bundle_path.exists(): return bundle_path
    script_path = Path(__file__).parent.parent / "gui" / "images" / filename
    if script_path.exists(): return script_path
    return Path(__file__).parent.parent.parent / filename

class CaplGenGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Randstad Digital - DPE | CAPL Generator")
        self.root.geometry("1000x800") 
        self.root.minsize(800, 700)

        self.sheet_path_var = tk.StringVar(value="Requirements.xlsx")
        self.test_cat_var = tk.StringVar(value="-- Select --")
        self.test_type_var = tk.StringVar(value="-- Select Category First --")
        self.output_folder_var = tk.StringVar(value="GeneratedTestScripts")

        # --- COLORS ---
        self.colors = {
            'text_light': '#e0e0e0',   
            'text_title': '#4ba3e3',   
            'input_bg': '#ffffff',     
            'input_fg': '#000000',     
            'btn_preprocess': '#3b7a57', 
            'btn_generate': '#a14040',   
            'btn_browse': '#2c476b',     # Steel Blue for Browse, Clear, and Download
            'btn_fg': 'white',
            'log_bg': '#050a12',       
            'log_fg': '#d1d1d1'        
        }

        self._setup_canvas()
        self._build_header()
        self._build_input_section()
        self._build_action_buttons()
        self._build_log_section()

    def _setup_canvas(self):
        self.bg_image_path = get_asset_path("background.png")
        self.canvas = tk.Canvas(self.root, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        if self.bg_image_path.exists():
            try:
                self.original_bg = Image.open(self.bg_image_path)
                self.root.bind("<Configure>", self._resize_event)
            except Exception as e:
                log.error(f"Error loading background: {e}")

    def _resize_event(self, event):
        if event.widget == self.root:
            width, height = event.width, event.height
            if width > 10 and height > 10:
                resized_image = self.original_bg.resize((width, height), Image.LANCZOS)
                self.bg_photo = ImageTk.PhotoImage(resized_image)
                self.canvas.delete("bg")
                self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw", tags="bg")
                self.canvas.tag_lower("bg")

                self.canvas.coords("logo", width / 2, 40)
                self.canvas.coords("title", width / 2, 90)
                
                left_align = width * 0.1
                # Sync all floating labels dynamically
                self.canvas.coords("lbl_sheet", left_align, height * 0.16)
                self.canvas.coords("lbl_cat", left_align, height * 0.24)
                self.canvas.coords("lbl_type", left_align, height * 0.32)
                self.canvas.coords("lbl_out", left_align, height * 0.40)
                self.canvas.coords("lbl_log", left_align, height * 0.67) # Log label right above the box

    def _build_header(self):
        logo_path = get_asset_path("logo.png")
        if logo_path.exists():
            try:
                original_logo = Image.open(logo_path)
                h_size = 45 
                w_prop = (h_size / float(original_logo.size[1]))
                w_size = int((float(original_logo.size[0]) * float(w_prop)))
                resized_logo = original_logo.resize((w_size, h_size), Image.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(resized_logo) 
                self.canvas.create_image(500, 40, image=self.logo_img, anchor="center", tags="logo") 
            except Exception as e:
                log.error(f"Failed to load logo: {e}")

        self.canvas.create_text(
            500, 90, text="AI ASSIST INTERFACE SCRIPT GENERATOR TOOL",
            font=("Helvetica", 15, "bold"), fill=self.colors['text_title'],
            anchor="center", tags="title"
        )

    def _build_input_section(self):
        font_style = ("Helvetica", 10, "bold")
        self.canvas.create_text(0, 0, text="Input Sheet Link:", font=font_style, fill=self.colors['text_light'], anchor="sw", tags="lbl_sheet")
        self.canvas.create_text(0, 0, text="Test Category:", font=font_style, fill=self.colors['text_light'], anchor="sw", tags="lbl_cat")
        self.canvas.create_text(0, 0, text="Test Type:", font=font_style, fill=self.colors['text_light'], anchor="sw", tags="lbl_type")
        self.canvas.create_text(0, 0, text="Output Folder Name:", font=font_style, fill=self.colors['text_light'], anchor="sw", tags="lbl_out")

        tk.Entry(self.root, textvariable=self.sheet_path_var, bg=self.colors['input_bg'], fg=self.colors['input_fg'], insertbackground='black', relief="flat").place(relx=0.1, rely=0.17, relwidth=0.68, height=30)
        tk.Button(self.root, text="Browse...", bg=self.colors['btn_browse'], fg=self.colors['btn_fg'], relief="flat", cursor="hand2", command=self._browse_file).place(relx=0.79, rely=0.17, relwidth=0.11, height=30)

        cb_cat = ttk.Combobox(self.root, textvariable=self.test_cat_var, values=["E2E_CAN", "E2E_ETH"], state="readonly")
        cb_cat.place(relx=0.1, rely=0.25, relwidth=0.8, height=30)

        cb_type = ttk.Combobox(self.root, textvariable=self.test_type_var, values=["CAN-SOMEIP", "CAN-SOMEIPFF", "CAN-SWC", "SWC_CAN", "SOMEIP-CAN"], state="readonly")
        cb_type.place(relx=0.1, rely=0.33, relwidth=0.8, height=30)

        tk.Entry(self.root, textvariable=self.output_folder_var, bg=self.colors['input_bg'], fg=self.colors['input_fg'], insertbackground='black', relief="flat").place(relx=0.1, rely=0.41, relwidth=0.8, height=30)

    def _build_action_buttons(self):
        self.btn_preprocess = tk.Button(
            self.root, text="PRE - PROCESS", bg=self.colors['btn_preprocess'], fg=self.colors['btn_fg'], 
            font=("Arial", 11, "bold"), relief="flat", cursor="hand2"
        )
        self.btn_preprocess.place(relx=0.1, rely=0.50, relwidth=0.8, height=38)

        self.btn_generate = tk.Button(
            self.root, text="GENERATE SCRIPTS", bg=self.colors['btn_generate'], fg=self.colors['btn_fg'], 
            font=("Arial", 11, "bold"), relief="flat", cursor="hand2", command=self.run_generation
        )
        self.btn_generate.place(relx=0.1, rely=0.57, relwidth=0.8, height=38)

    def _build_log_section(self):
        # 1. 100% Transparent Label drawn directly on Canvas
        self.canvas.create_text(0, 0, text="EXECUTION LOGS", font=("Helvetica", 10, "bold"), fill=self.colors['text_light'], anchor="sw", tags="lbl_log")
        
        # 2. Control Buttons placed cleanly above the log box matching the Browse color
        tk.Button(self.root, text="Clear", bg=self.colors['btn_browse'], fg=self.colors['btn_fg'], relief="flat", cursor="hand2", command=self._clear_log).place(relx=0.90, rely=0.67, relwidth=0.08, height=25, anchor="se")
        tk.Button(self.root, text="Download", bg=self.colors['btn_browse'], fg=self.colors['btn_fg'], relief="flat", cursor="hand2").place(relx=0.81, rely=0.67, relwidth=0.08, height=25, anchor="se")

        # 3. Main Execution Log text box
        log_frame = tk.Frame(self.root, bg=self.colors['log_bg'])
        log_frame.place(relx=0.1, rely=0.68, relwidth=0.8, relheight=0.28) # Placed right below the label/buttons
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame, state="disabled", wrap="word", bg=self.colors['log_bg'], fg=self.colors['log_fg'],
            insertbackground='white', relief="flat", padx=5, pady=5
        )
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.write_log("System ready...")

    # --- ACTION METHODS ---
    def _browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Requirements Excel",
            filetypes=[("Excel Files", ".xlsx;.xls"), ("All Files", ".")]
        )
        if file_path:
            self.sheet_path_var.set(file_path)
            self.write_log(f"Selected file: {file_path}")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

    def write_log(self, message: str):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    def run_generation(self):
        self.write_log("--- Starting Generation Pipeline ---")
        self.write_log(f"Sheet: {self.sheet_path_var.get()}")
        self.write_log(f"Type: {self.test_type_var.get()}")

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
        
    root.option_add('TComboboxListbox.background', '#ffffff')
    root.option_add('TComboboxListbox.foreground', 'black')
    root.option_add('TComboboxListbox.selectBackground', '#a0a0a0')
    root.option_add('TComboboxListbox.selectForeground', 'black')
    
    app = CaplGenGUI(root)
    root.mainloop()