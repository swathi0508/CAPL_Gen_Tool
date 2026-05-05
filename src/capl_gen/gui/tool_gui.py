import sys
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from PIL import Image, ImageTk

from core.logger import log
from pipeline.main_pipeline import CaplGenerationPipeline

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
        self.arxml_path_var = tk.StringVar(value="Network.arxml")
        self.test_cat_var = tk.StringVar(value="E2E_CAN")
        self.test_type_var = tk.StringVar(value="CAN->SOMEIP")
        self.output_folder_var = tk.StringVar(value="GeneratedTestScripts")
        self.enable_log_var = tk.BooleanVar(value=False)
        
        self.pipeline = CaplGenerationPipeline()

        self.colors = {
            'text_light': '#e0e0e0', 'text_title': '#4ba3e3', 'input_bg': '#ffffff', 
            'input_fg': '#000000', 'btn_preprocess': '#3b7a57', 'btn_generate': '#a14040', 
            'btn_browse': '#2c476b', 'btn_fg': 'white', 'log_bg': '#050a12', 'log_fg': '#d1d1d1'
        }

        self._setup_canvas()
        self._build_header()
        self._build_input_section()
        self._build_action_buttons()
        self._build_log_section()
        self._start_background_db_build()

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
                self.canvas.coords("lbl_sheet", left_align, height * 0.16)
                self.canvas.coords("lbl_arxml", left_align, height * 0.23) 
                self.canvas.coords("lbl_cat", left_align, height * 0.30)
                self.canvas.coords("lbl_type", left_align, height * 0.37)
                self.canvas.coords("lbl_out", left_align, height * 0.44)
                self.canvas.coords("lbl_log", left_align, height * 0.67) 

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
                pass
        self.canvas.create_text(
            500, 90, text="AI ASSIST INTERFACE SCRIPT GENERATOR TOOL",
            font=("Helvetica", 15, "bold"), fill=self.colors['text_title'], anchor="center", tags="title"
        )

    def _build_input_section(self):
        font_style = ("Helvetica", 10, "bold")
        self.canvas.create_text(0, 0, text="Input Requirement Sheet:", font=font_style, fill=self.colors['text_light'], anchor="sw", tags="lbl_sheet")
        self.canvas.create_text(0, 0, text="Input Unified ARXML Network:", font=font_style, fill=self.colors['text_light'], anchor="sw", tags="lbl_arxml")
        self.canvas.create_text(0, 0, text="Test Category:", font=font_style, fill=self.colors['text_light'], anchor="sw", tags="lbl_cat")
        self.canvas.create_text(0, 0, text="Test Type:", font=font_style, fill=self.colors['text_light'], anchor="sw", tags="lbl_type")
        self.canvas.create_text(0, 0, text="Output Folder Name:", font=font_style, fill=self.colors['text_light'], anchor="sw", tags="lbl_out")

        tk.Entry(self.root, textvariable=self.sheet_path_var, bg=self.colors['input_bg'], fg=self.colors['input_fg'], relief="flat").place(relx=0.1, rely=0.17, relwidth=0.68, height=30)
        tk.Button(self.root, text="Browse...", bg=self.colors['btn_browse'], fg=self.colors['btn_fg'], relief="flat", cursor="hand2", command=self._browse_file).place(relx=0.79, rely=0.17, relwidth=0.11, height=30)

        tk.Entry(self.root, textvariable=self.arxml_path_var, bg=self.colors['input_bg'], fg=self.colors['input_fg'], relief="flat").place(relx=0.1, rely=0.24, relwidth=0.68, height=30)
        tk.Button(self.root, text="Browse...", bg=self.colors['btn_browse'], fg=self.colors['btn_fg'], relief="flat", cursor="hand2", command=self._browse_arxml_file).place(relx=0.79, rely=0.24, relwidth=0.11, height=30)

        ttk.Combobox(self.root, textvariable=self.test_cat_var, values=["E2E_CAN", "E2E_ETH"], state="readonly").place(relx=0.1, rely=0.31, relwidth=0.8, height=30)
        ttk.Combobox(self.root, textvariable=self.test_type_var, values=["CAN->SOMEIP", "CAN->SOMEIP_FF", "CAN->SWC", "SWC->CAN", "SOMEIP->CAN"], state="readonly").place(relx=0.1, rely=0.38, relwidth=0.8, height=30)
        tk.Entry(self.root, textvariable=self.output_folder_var, bg=self.colors['input_bg'], fg=self.colors['input_fg'], relief="flat").place(relx=0.1, rely=0.45, relwidth=0.8, height=30)
        
        tk.Checkbutton(self.root, text="Enable Verbose Log / Dev Mode", variable=self.enable_log_var, bg=self.colors['log_bg'], fg=self.colors['text_title'], selectcolor=self.colors['log_bg'], activebackground=self.colors['log_bg']).place(relx=0.1, rely=0.50)

    def _build_action_buttons(self):
        self.btn_preprocess = tk.Button(self.root, text="PRE - PROCESS", bg=self.colors['btn_preprocess'], fg=self.colors['btn_fg'], font=("Arial", 11, "bold"), relief="flat", cursor="hand2", command=self.run_preprocess)
        self.btn_preprocess.place(relx=0.1, rely=0.55, relwidth=0.8, height=38)

        self.btn_generate = tk.Button(self.root, text="GENERATE SCRIPTS", bg=self.colors['btn_generate'], fg=self.colors['btn_fg'], font=("Arial", 11, "bold"), relief="flat", cursor="hand2", command=self.run_generation)
        self.btn_generate.place(relx=0.1, rely=0.62, relwidth=0.8, height=38)

    def _build_log_section(self):
        self.canvas.create_text(0, 0, text="EXECUTION LOGS", font=("Helvetica", 10, "bold"), fill=self.colors['text_light'], anchor="sw", tags="lbl_log")
        tk.Button(self.root, text="Clear", bg=self.colors['btn_browse'], fg=self.colors['btn_fg'], relief="flat", cursor="hand2", command=self._clear_log).place(relx=0.90, rely=0.67, relwidth=0.08, height=25, anchor="se")
        log_frame = tk.Frame(self.root, bg=self.colors['log_bg'])
        log_frame.place(relx=0.1, rely=0.68, relwidth=0.8, relheight=0.28) 
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, state="disabled", wrap="word", bg=self.colors['log_bg'], fg=self.colors['log_fg'], insertbackground='white', relief="flat", padx=5, pady=5)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.write_log("System UI initialized.")

    def _start_background_db_build(self):
        if not self.pipeline.can_db_data and os.path.exists(self.arxml_path_var.get()):
            self.write_log("⚙️ Starting background database parsers...")
            self.btn_preprocess.config(state="disabled") 
            thread = threading.Thread(target=self._run_parsers_in_background, daemon=True)
            thread.start()

    def _run_parsers_in_background(self):
        try:
            self.pipeline.enable_log = self.enable_log_var.get()
            self.pipeline.build_databases(self.arxml_path_var.get())
            self.root.after(0, lambda: self.write_log("✅ Network Databases Parsed successfully."))
            self.root.after(0, self._on_parsing_complete)
        except Exception as e:
            self.root.after(0, lambda: self.write_log(f"❌ Background Parsing Failed: {e}"))
            self.root.after(0, lambda: self.btn_preprocess.config(state="normal"))

    def _on_parsing_complete(self):
        self.btn_preprocess.config(state="normal")

    def _browse_file(self):
        file_path = filedialog.askopenfilename(title="Select Requirements Excel", filetypes=[("Excel Files", ".xlsx;.xls"), ("All Files", "*.*")])
        if file_path: self.sheet_path_var.set(file_path)

    def _browse_arxml_file(self):
        file_path = filedialog.askopenfilename(title="Select Unified ARXML File", filetypes=[("ARXML Files", "*.arxml"), ("All Files", "*.*")])
        if file_path:
            self.arxml_path_var.set(file_path)
            self._start_background_db_build()

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

    def run_preprocess(self):
        self.pipeline.enable_log = self.enable_log_var.get()
        input_excel = self.sheet_path_var.get()
        out_dir = self.output_folder_var.get()
        arxml_path = self.arxml_path_var.get()

        if not os.path.exists(input_excel):
            self.write_log(f"❌ Error: Input Excel '{input_excel}' not found.")
            return

        self.write_log("--- Starting Pre-Processing (Mapping & Validation) ---")
        self.btn_preprocess.config(state="disabled")
        
        try:
            if not self.pipeline.can_db_data:
                self.pipeline.build_databases(arxml_path)
            
            # Now runs purely in memory!
            self.pipeline.run_preprocessing_memory(input_excel, out_dir)
            self.write_log(f"✅ Pre-Processing Complete. Memory mapping secured.")
        except Exception as e:
            self.write_log(f"❌ Fatal error during Pre-Processing: {e}")
        finally:
            self.btn_preprocess.config(state="normal")

    def run_generation(self):
        out_dir = self.output_folder_var.get()
        category = self.test_cat_var.get()
        test_type = self.test_type_var.get()

        if not self.pipeline.in_memory_dfs:
            self.write_log("❌ Error: Memory mapping missing. Please run PRE - PROCESS first.")
            return

        self.write_log(f"--- Starting CAPL Generation ({category} | {test_type}) ---")
        self.btn_generate.config(state="disabled")
        
        try:
            self.pipeline.run_generation(out_dir, category, test_type)
            self.write_log(f"✅ CAPL Scripts Generated in '{out_dir}'!")
        except Exception as e:
            self.write_log(f"❌ Generation failed: {e}")
        finally:
            self.btn_generate.config(state="normal")

def launch_gui():
    root = tk.Tk()
    style = ttk.Style()
    if "clam" in style.theme_names(): style.theme_use("clam")
    app = CaplGenGUI(root)
    root.mainloop()