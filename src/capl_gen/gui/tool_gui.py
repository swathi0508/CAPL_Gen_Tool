import tkinter as tk
from tkinter import filedialog, messagebox

from core.logger import log


class CaplGenGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CAPL Generation Tool")
        self.root.geometry("400x200")

        tk.Label(root, text="CAPL Generator", font=("Arial", 16)).pack(pady=10)

        self.btn_run = tk.Button(root, text="Select Excel & Generate", command=self.run_generation)
        self.btn_run.pack(pady=20)

    def run_generation(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel Files", "*.xlsx")])
        if file_path:
            log.info(f"GUI selected file: {file_path}")
            # Orchestrate logic here by calling main.py functions
            messagebox.showinfo("Success", "Generation triggered! Check console.")

def launch_gui():
    root = tk.Tk()
    CaplGenGUI(root)
    root.mainloop()
