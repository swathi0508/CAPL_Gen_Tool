import sys
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QComboBox, QTextEdit, QFileDialog, QCheckBox, QMessageBox)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

from core.logger import log
from pipeline.main_pipeline import CaplGenerationPipeline

def get_asset_path(filename: str) -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        bundle_path = Path(sys._MEIPASS) / "gui" / "images" / filename
        if bundle_path.exists(): return bundle_path
    script_path = Path(__file__).parent.parent / "gui" / "images" / filename
    if script_path.exists(): return script_path
    return Path(__file__).parent.parent.parent / filename

# Signal bridge to handle thread-safe UI updates
class CommSignals(QObject):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

class CaplGenGUI(QMainWindow):
    def __init__(self, root_dummy=None):
        super().__init__()
        
        self.setWindowTitle("Randstad Digital - CAPL Generator")
        self.setMinimumSize(1150, 850)
        self.resize(1150, 850)
        
        self.pre_process_done = False
        self.pipeline = CaplGenerationPipeline()
        self.signals = CommSignals()
        
        # Connect signals
        self.signals.log_signal.connect(self.write_log)
        self.signals.finished_signal.connect(self._on_pre_process_complete)
        
        # Colors
        self.clr_title = "#F8F9FA" 
        self.clr_label = "#E5E7EB" 
        self.clr_input_bg = "rgba(45, 55, 72, 240)"
        self.clr_util_btn = "#4A5568"

        self._setup_canvas()
        self._build_ui_container()
        self._center_window_safely()

    def _center_window_safely(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        self.move(x, 100)

    def _setup_canvas(self):
        bg_path = get_asset_path("background.png")
        self.bg_pixmap = QPixmap(str(bg_path)) if bg_path.exists() else None

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.bg_pixmap:
            painter.drawPixmap(self.rect(), self.bg_pixmap)
        painter.fillRect(self.rect(), QColor(10, 18, 32, 225))

    def _build_ui_container(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.outer_layout = QHBoxLayout(self.central_widget)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)

        self.content_widget = QWidget()
        self.content_widget.setFixedWidth(1020)
        self.main_layout = QVBoxLayout(self.content_widget)
        self.main_layout.setContentsMargins(10, 40, 10, 40)
        self.main_layout.setSpacing(15)

        self.outer_layout.addStretch()
        self.outer_layout.addWidget(self.content_widget)
        self.outer_layout.addStretch()

        self.setStyleSheet(f"""
            QLabel {{ color: {self.clr_label}; font-weight: bold; background: transparent; }}
            QLineEdit, QComboBox {{ 
                background-color: {self.clr_input_bg}; 
                border: 1px solid #4a5568; border-radius: 4px; 
                color: white; padding: 6px; 
            }}
            QPushButton#util_btn {{ 
                background-color: {self.clr_util_btn}; color: #FFFFFF; 
                border-radius: 4px; font-weight: bold; padding: 6px;
            }}
            QPushButton#util_btn:hover {{ background-color: #718096; }}
            QPushButton#util_btn:pressed {{ background-color: #2D3748; }}
            QCheckBox {{ color: {self.clr_label}; background: transparent; }}
        """)

        self._build_header()
        self.main_layout.addSpacing(40)
        self._build_input_section()
        self._build_config_section()
        self._build_log_section()

    def _build_header(self):
        header_widget = QWidget()
        header_widget.setFixedWidth(1000)
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        logo_path = get_asset_path("logo.png")
        if logo_path.exists():
            l_lbl = QLabel()
            l_pix = QPixmap(str(logo_path)).scaledToHeight(55, Qt.TransformationMode.SmoothTransformation)
            l_lbl.setPixmap(l_pix)
            header.addWidget(l_lbl)
        title = QLabel("CAPLBolt | <i>Instant Interface Test Script Generation</i>")
        title.setStyleSheet(f"font-size: 24px; color: {self.clr_title}; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self.main_layout.addWidget(header_widget)

    def _build_input_section(self):
        container = QWidget()
        container.setFixedSize(1000, 140)
        QLabel("Input ETH_CAN.arxml:", container).move(0, 0)
        self.arxml_path_edit = QLineEdit(container)
        self.arxml_path_edit.setGeometry(0, 25, 750, 32)
        self.arxml_path_edit.textChanged.connect(self._check_logic_states)
        btn_br_arxml = QPushButton("BROWSE", container)
        btn_br_arxml.setObjectName("util_btn")
        btn_br_arxml.setGeometry(760, 25, 90, 32)
        btn_br_arxml.clicked.connect(self._browse_arxml_file)
        
        QLabel("Input Requirement Sheet:", container).move(0, 75)
        self.req_path_edit = QLineEdit(container)
        self.req_path_edit.setGeometry(0, 100, 750, 32)
        self.req_path_edit.textChanged.connect(self._check_logic_states)
        btn_br_req = QPushButton("BROWSE", container)
        btn_br_req.setObjectName("util_btn")
        btn_br_req.setGeometry(760, 100, 90, 32)
        btn_br_req.clicked.connect(self._browse_file)
        
        self.btn_preprocess = QPushButton("PRE-PROCESS", container)
        self.btn_preprocess.setEnabled(False)
        self.btn_preprocess.setGeometry(860, 62, 140, 38)
        self.btn_preprocess.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        self.btn_preprocess.setStyleSheet("background-color: #3b3e40; color: #94a3b8; border-radius: 4px; border: none;")
        self.btn_preprocess.clicked.connect(self.run_preprocess)
        self.main_layout.addWidget(container)

    def _build_config_section(self):
        container = QWidget()
        container.setFixedSize(1000, 140)
        QLabel("Test Category:", container).move(0, 0)
        self.cat_combo = QComboBox(container)
        self.cat_combo.addItems(["E2E_CAN", "E2E_ETH"])
        self.cat_combo.setGeometry(0, 25, 850, 32)
        
        QLabel("Test Type:", container).move(0, 75)
        self.typ_combo = QComboBox(container)
        self.typ_combo.addItems(["CAN->SOMEIP", "CAN->SOMEIP_FF", "CAN->SWC", "SWC->CAN", "SOMEIP->CAN"])
        self.typ_combo.setGeometry(0, 100, 850, 32)
        
        self.btn_gen = QPushButton("GENERATE SCRIPTS", container)
        self.btn_gen.setEnabled(False)
        self.btn_gen.setGeometry(860, 62, 140, 38)
        self.btn_gen.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
        self.btn_gen.setStyleSheet("background-color: #3b3e40; color: #94a3b8; border-radius: 4px; border: none;")
        self.btn_gen.clicked.connect(self.run_generation)
        self.main_layout.addWidget(container)

    def _build_log_section(self):
        container = QWidget()
        container.setFixedWidth(1000)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        header = QHBoxLayout()
        header.addWidget(QLabel("EXECUTION LOGS"))
        header.addStretch()
        for text, func in [("DOWNLOAD LOGS", self.download_logs), ("CLEAR", self._clear_log)]:
            btn = QPushButton(text); btn.setObjectName("util_btn"); btn.clicked.connect(func)
            header.addWidget(btn)
        layout.addLayout(header)
        
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #000000; color: #cbd5e1; font-family: Consolas; border: 1px solid #2d3748; border-radius: 4px;")
        layout.addWidget(self.log_text)
        
        # --- SECURITY LOCK: Hide Dev Mode Checkbox in Production ---
        # self.cb_verbose = QCheckBox("Enable Verbose Log / Dev Mode")
        # if not getattr(sys, 'frozen', False):
        #     layout.addWidget(self.cb_verbose)
            
        self.main_layout.addWidget(container, 1) 

    # --- Thread Safe Helpers ---
    def write_log(self, message: str):
        self.log_text.append(f"> {message}")
        self.log_text.ensureCursorVisible()

    def _on_pre_process_complete(self):
        self.pre_process_done = True
        self._update_gen_button_ui()
        self._check_logic_states()

    # --- Actions ---
    def _check_logic_states(self):
        if self.arxml_path_edit.text().strip() and self.req_path_edit.text().strip():
            self.btn_preprocess.setEnabled(True)
            self.btn_preprocess.setStyleSheet("""
                QPushButton { background-color: #1e8449; color: white; border-radius: 4px; font-weight: bold; border: none; }
                QPushButton:hover { background-color: #166534; }
                QPushButton:pressed { background-color: #0d4d26; }
            """)
        else:
            self.btn_preprocess.setEnabled(False)
            self.btn_preprocess.setStyleSheet("background-color: #3b3e40; color: #94a3b8; border-radius: 4px; border: none;")

    def _update_gen_button_ui(self):
        if self.pre_process_done:
            self.btn_gen.setEnabled(True)
            self.btn_gen.setStyleSheet("""
                QPushButton { background-color: #1e8449; color: white; border-radius: 4px; font-weight: bold; border: none; }
                QPushButton:hover { background-color: #166534; }
                QPushButton:pressed { background-color: #0d4d26; }
            """)

    def run_preprocess(self):
        # 1. Prompt if already processed
        if self.pre_process_done:
            reply = QMessageBox.question(
                self, 'Pre-Process Again?', 
                'Previous pre-processed data already exists. Do you want to pre-process again?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        arxml = self.arxml_path_edit.text()
        req = self.req_path_edit.text()
        
        # Pass the UI state down to the pipeline
        self.pipeline.enable_log = self.cb_verbose.isChecked() if hasattr(self, 'cb_verbose') else False
        
        self.btn_preprocess.setEnabled(False)
        self.btn_preprocess.setStyleSheet("""
            QPushButton { background-color: #d68910; color: white; border-radius: 4px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #b9770e; }
            QPushButton:pressed { background-color: #9c640c; }
        """)
        
        self.pre_process_done = False
        self.btn_gen.setEnabled(False)
        self.btn_gen.setStyleSheet("background-color: #3b3e40; color: #94a3b8; border-radius: 4px; border: none;")

        def task():
            start_time = time.time()
            try:
                self.signals.log_signal.emit("⚙️ Pre-Processing started. This will take a few seconds...")
                self.pipeline.build_databases(arxml)
                
                self.signals.log_signal.emit("⚙️ Analyzing requirement specifications...")
                self.pipeline.run_preprocessing_memory(req, "GeneratedTestScripts")
                
                # --- HIGH PRECISION TIME FORMATTING ---
                elapsed = time.time() - start_time
                m, s = divmod(elapsed, 60)
                ms = int((s - int(s)) * 1000)
                formatted_time = f"{int(m):02d}m {int(s):02d}s {ms:03d}ms"
                
                self.signals.log_signal.emit(f"✅ Pre-Processing complete. (Execution Time: {formatted_time})")
                self.signals.finished_signal.emit()
            except Exception as e:
                self.signals.log_signal.emit("❌ Error: Failed to process files. Please verify input documents.")
                log.error(f"Internal Pre-Processing Error: {e}")
                QTimer.singleShot(0, self._check_logic_states)

        threading.Thread(target=task, daemon=True).start()

    def run_generation(self):
        category = self.cat_combo.currentText()
        test_type = self.typ_combo.currentText()
        out_dir = "GeneratedTestScripts"
        
        self.write_log(f"📋 Selected Test Category: {category}")
        self.write_log(f"📋 Selected Test Type: {test_type}")
        
        start_time = time.time()
        try:
            self.write_log(f"✅ CAPL Scripts Generation Started.")
            self.pipeline.run_generation(out_dir, category, test_type)
            
            # --- HIGH PRECISION TIME FORMATTING ---
            elapsed = time.time() - start_time
            m, s = divmod(elapsed, 60)
            ms = int((s - int(s)) * 1000)
            formatted_time = f"{int(m):02d}m {int(s):02d}s {ms:03d}ms"
            
            self.write_log(f"✅ CAPL Scripts Generated Successfully. (Execution Time: {formatted_time})")
            self.write_log(f"📂 Output Location: {os.path.abspath(out_dir)}")
        except Exception as e: 
            self.write_log("❌ Generation failed. An error occurred during file creation.")
            log.error(f"Internal Generation Error: {e}")

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Requirements", "", "Excel Files (*.xlsx *.xls)")
        if f: 
            self.req_path_edit.setText(f)
            self.write_log(f"📄 Requirement Sheet Selected: {os.path.basename(f)}")

    def _browse_arxml_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select ARXML", "", "ARXML Files (*.arxml)")
        if f: 
            # --- FORCE CLEAR RAM CACHE IF FILE CHANGES ---
            if f != self.arxml_path_edit.text():
                self.pipeline.can_db_data = {}
                self.pipeline.eth_db_data = {}
            
            self.arxml_path_edit.setText(f)
            self.write_log(f"🌐 ARXML Selected: {os.path.basename(f)}")

    def _clear_log(self): 
        self.log_text.clear()
    
    def download_logs(self):
        timestamp = datetime.now().strftime("%d_%m_%Y__%H_%M_%S")
        filename = f"CaplGenLogs_{timestamp}.txt"
        f, _ = QFileDialog.getSaveFileName(self, "Save Logs", filename, "Text Files (*.txt)")
        if f: 
            with open(f, 'w', encoding='utf-8') as file: file.write(self.log_text.toPlainText())

def launch_gui():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except: pass
    app = QApplication(sys.argv)
    gui = CaplGenGUI()
    gui.show()
    sys.exit(app.exec())