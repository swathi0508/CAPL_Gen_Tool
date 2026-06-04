import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from logger import log
from pipeline.main_pipeline import CaplGenerationPipeline


def get_asset_path(filename: str) -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        bundle_path = Path(sys._MEIPASS) / "gui" / "images" / filename
        if bundle_path.exists(): return bundle_path
    script_path = Path(__file__).parent.parent / "gui" / "images" / filename
    if script_path.exists(): return script_path
    return Path(__file__).parent.parent.parent / filename


class CommSignals(QObject):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()


class CaplGenGUI(QMainWindow):
    def __init__(self, root_dummy=None):
        super().__init__()

        self.setWindowTitle("Randstad Digital - CAPL Generator")
        self.setMinimumSize(1150, 850)
        self.resize(1150, 850)

        icon_path = get_asset_path("app_icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.pre_process_done = False
        self.pipeline = CaplGenerationPipeline()
        self.signals = CommSignals()

        self.signals.log_signal.connect(self.write_log)
        self.signals.finished_signal.connect(self._on_pre_process_complete)

        self.clr_title = "#F8F9FA"
        self.clr_label = "#E5E7EB"
        self.clr_input_bg = "rgba(45, 55, 72, 240)"
        self.clr_util_btn = "#4A5568"

        # Math for perfect alignment
        self.LBL_W = 230
        self.EDIT_W = 510
        self.BROWSE_W = 90
        self.ACTION_W = 150
        self.SP_H = 10
        self.ACTION_GAP = 35
        self.ROW_W = self.LBL_W + self.EDIT_W + self.BROWSE_W + (self.SP_H * 2)
        self.TOTAL_W = self.ROW_W + self.ACTION_GAP + self.ACTION_W

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
        self.content_widget.setFixedWidth(1060)
        self.main_layout = QVBoxLayout(self.content_widget)
        self.main_layout.setContentsMargins(10, 40, 10, 40)
        self.main_layout.setSpacing(25)

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
        """)

        self._build_header()
        self.main_layout.addSpacing(30)
        self._build_input_section()
        self._build_config_section()
        self.main_layout.addSpacing(30)
        self._build_log_section()

    def _create_input_row(self, label_text, edit_obj, btn_obj):
        row = QWidget()
        # 1. Let the row expand horizontally, but keep the height consistent
        row.setMinimumHeight(32) 
        
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.SP_H)
        
        # 2. The Label: Use MinimumWidth instead of FixedSize
        lbl = QLabel(label_text)
        lbl.setMinimumWidth(self.LBL_W) # Allows Linux fonts to push the boundary wider if needed
        lbl.setFixedHeight(32)
        layout.addWidget(lbl)
        
        # 3. The LineEdit: Use stretch=1 so it acts like a spring and fills all remaining space
        edit_obj.setFixedHeight(32)
        layout.addWidget(edit_obj, stretch=1)
        
        # 4. The Button: Buttons are usually safe to keep fixed so they don't look warped
        btn_obj.setFixedSize(self.BROWSE_W, 32)
        layout.addWidget(btn_obj)
        
        return row

    def _build_input_section(self):
        container = QWidget()
        container.setFixedSize(self.TOTAL_W, 160)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        inputs_vbox = QVBoxLayout()
        inputs_vbox.setContentsMargins(0, 0, 0, 0)
        inputs_vbox.setSpacing(10)

        self.req_path_edit = QLineEdit(); self.req_path_edit.textChanged.connect(self._check_logic_states)
        btn_req = QPushButton("BROWSE"); btn_req.setObjectName("util_btn"); btn_req.clicked.connect(self._browse_file)
        inputs_vbox.addWidget(self._create_input_row("Input Requirements Sheet (.xlsx):", self.req_path_edit, btn_req))

        self.arxml_path_edit = QLineEdit(); self.arxml_path_edit.textChanged.connect(self._check_logic_states)
        btn_arxml = QPushButton("BROWSE"); btn_arxml.setObjectName("util_btn"); btn_arxml.clicked.connect(self._browse_arxml_file)
        inputs_vbox.addWidget(self._create_input_row("Input Signal DB (ETH_CAN.arxml):", self.arxml_path_edit, btn_arxml))

        self.aacp_path_edit = QLineEdit(); self.aacp_path_edit.textChanged.connect(self._check_logic_states)
        btn_aacp = QPushButton("BROWSE"); btn_aacp.setObjectName("util_btn"); btn_aacp.clicked.connect(self._browse_aacp_file)
        inputs_vbox.addWidget(self._create_input_row("Input AACP sysvar (aacp.vsysvar):", self.aacp_path_edit, btn_aacp))

        self.someip_path_edit = QLineEdit(); self.someip_path_edit.textChanged.connect(self._check_logic_states)
        btn_someip = QPushButton("BROWSE"); btn_someip.setObjectName("util_btn"); btn_someip.clicked.connect(self._browse_someip_file)
        inputs_vbox.addWidget(self._create_input_row("Input SOMEIP_FF sysvar (SysVarDef.xml):", self.someip_path_edit, btn_someip))

        layout.addLayout(inputs_vbox)
        layout.addSpacing(self.ACTION_GAP)

        self.btn_preprocess = QPushButton("PRE-PROCESS")
        self.btn_preprocess.setEnabled(False)
        self.btn_preprocess.setFixedSize(self.ACTION_W, 38)
        self.btn_preprocess.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
        self.btn_preprocess.setStyleSheet("background-color: #3b3e40; color: #94a3b8; border-radius: 4px; border: none;")
        self.btn_preprocess.clicked.connect(self.run_preprocess)
        layout.addWidget(self.btn_preprocess, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.main_layout.addWidget(container)

    def _build_config_section(self):
        container = QWidget()
        container.setMinimumHeight(40) # Allow horizontal stretch, fix vertical
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        config_left = QWidget()
        config_left.setMinimumHeight(32)
        
        c_layout = QHBoxLayout(config_left)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(self.SP_H)
        
        # --- Label 1: Let it size itself naturally ---
        lbl_cat = QLabel("Test Category:")
        lbl_cat.setFixedHeight(32)
        c_layout.addWidget(lbl_cat)
        
        # --- Combo 1: Add stretch=1 to consume leftover space ---
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(["E2E_CAN", "E2E_ETH"])
        self.cat_combo.setFixedHeight(32)
        c_layout.addWidget(self.cat_combo, stretch=1)
        
        # --- Label 2: Add a small spacer before it, let it size naturally ---
        c_layout.addSpacing(15) 
        lbl_typ = QLabel("Test Type:")
        lbl_typ.setFixedHeight(32)
        lbl_typ.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        c_layout.addWidget(lbl_typ)
        
        # --- Combo 2: Add stretch=1 to consume leftover space ---
        self.typ_combo = QComboBox()
        self.typ_combo.setFixedHeight(32)
        c_layout.addWidget(self.typ_combo, stretch=1)

        self.cat_combo.currentTextChanged.connect(self._update_test_types)
        self._update_test_types(self.cat_combo.currentText())

        # Give the left configuration block a stretch factor so it pushes the Generate button to the right
        layout.addWidget(config_left, stretch=1) 
        layout.addSpacing(self.ACTION_GAP)
        
        # Generate Button (Safe to keep FixedSize so it doesn't warp)
        self.btn_gen = QPushButton("GENERATE SCRIPTS")
        self.btn_gen.setEnabled(False)
        self.btn_gen.setFixedSize(self.ACTION_W, 38)
        self.btn_gen.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
        self.btn_gen.setStyleSheet("background-color: #3b3e40; color: #94a3b8; border-radius: 4px; border: none;")
        self.btn_gen.clicked.connect(self.run_generation)
        layout.addWidget(self.btn_gen, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        self.main_layout.addWidget(container)

    def _update_test_types(self, category):
        self.typ_combo.clear()
        if category == "E2E_CAN":
            self.typ_combo.addItems([
                "CAN->CAN", "CAN->SOMEIP", "CAN->SOMEIP_AACP", "CAN->SOMEIP_FF", "SOMEIP->CAN", "SOMEIP_FF->CAN"
                #, "CAN->SWC", "CAN->SWC_HVB", "SWC->CAN"
            ])
        elif category == "E2E_ETH":
            self.typ_combo.addItems([
                "CAN->SOMEIP", "CAN->SOMEIP_AACP", "CAN->SOMEIP_FF", "SOMEIP->CAN", "SOMEIP_FF->CAN"
                #, "SOMEIP->SWC", "SOMEIP_FF->SWC", "SWC->SOMEIP", "SWC->SOMEIP_AACP", "SWC->SOMEIP_FF", "CAROS->SWC"
            ])

    def run_preprocess(self):
        if self.pre_process_done:
            reply = QMessageBox.question(self, 'Pre-Process Again?', 'Previous data exists. Re-process?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No: return

        self.btn_preprocess.setEnabled(False); self.btn_preprocess.setStyleSheet("background-color: #d68910; color: white; border-radius: 4px; border: none;")
        self.pre_process_done = False; self.btn_gen.setEnabled(False); self.btn_gen.setStyleSheet("background-color: #3b3e40; color: #94a3b8; border-radius: 4px; border: none;")

        def task():
            total_start_time = time.time()
            try:
                # --- PHASE 1: PARSING / CACHE VALIDATION ---
                parse_start = time.time()
                self.signals.log_signal.emit("⚙️ Pre-Processing Started: Validating and Parsing ARXML, AACP, and SOMEIP_FF Databases...")

                # Unpacking all 4 return values from the pipeline
                can_built, eth_built, aacp_built, someip_built = self.pipeline.build_databases(
                    self.arxml_path_edit.text(),
                    self.someip_path_edit.text(),
                    self.aacp_path_edit.text()
                )
                parse_time = self._format_time(time.time() - parse_start)

                if not any([can_built, eth_built, aacp_built, someip_built]):
                    self.signals.log_signal.emit("⚡ Valid Database/Sysvar cache was found. Re-Parsing skipped.")
                else:
                    if can_built or eth_built: self.signals.log_signal.emit("✅ ARXML Databases parsed successfully.")
                    if aacp_built: self.signals.log_signal.emit("✅ AACP System Variables processed.")
                    if someip_built: self.signals.log_signal.emit("✅ SOMEIP_FF Definitions processed.")
                    self.signals.log_signal.emit(f"⏱️ Parsing Phase Time: {parse_time}")

                # --- PHASE 2: PRE-PROCESSING ---
                pre_start = time.time()
                self.signals.log_signal.emit("⚙️ Pre-Processing Input requirement specifications ...")
                self.pipeline.run_preprocessing_memory(self.req_path_edit.text(), "GeneratedTestScripts")

                pre_time = self._format_time(time.time() - pre_start)
                self.signals.log_signal.emit(f"✅ Requirements mapping complete. (Time: {pre_time})")
                
                total_time = self._format_time(time.time() - total_start_time)
                self.signals.log_signal.emit(f"🏁 Pre-Processing Complete. (Total Elapsed Time: {total_time})")
                self.signals.finished_signal.emit()

            except Exception as e:
                self.signals.log_signal.emit(f"❌ Error: {str(e)}")
                log.error(f"Internal Pre-Processing Error: {e}")
                QTimer.singleShot(0, self._check_logic_states)

        threading.Thread(target=task, daemon=True).start()

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Requirements", "", "Excel Files (*.xlsx *.xls)")
        if f: self.req_path_edit.setText(f); self.write_log(f"📄 Excel Selected: {os.path.basename(f)}")

    def _browse_arxml_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select ARXML", "", "ARXML Files (*.arxml)")
        if f:
            if f != self.arxml_path_edit.text():
                self.pipeline.can_db_data = {}; self.pipeline.eth_db_data = {}
            self.arxml_path_edit.setText(f); self.write_log(f"🌐 ARXML Selected: {os.path.basename(f)}")

    def _browse_aacp_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select AACP Sysvar", "", "vsysvar Files (*.vsysvar)")
        if f:
            if f != self.aacp_path_edit.text():
                self.pipeline.aacp_data = {} # Assuming your pipeline tracks this cache
            self.aacp_path_edit.setText(f); self.write_log(f"🔗 AACP Selected: {os.path.basename(f)}")

    def _browse_someip_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select SOMEIP FF", "", "XML Files (*.xml)")
        if f:
            if f != self.someip_path_edit.text():
                self.pipeline.someip_ff_data = {} # Assuming your pipeline tracks this cache
            self.someip_path_edit.setText(f); self.write_log(f"🔗 SOMEIP_FF Selected: {os.path.basename(f)}")

    def _build_header(self):
        header_widget = QWidget(); header_widget.setFixedWidth(self.TOTAL_W)
        header = QHBoxLayout(header_widget); header.setContentsMargins(0, 0, 0, 0)
        logo_path = get_asset_path("logo.png")
        if logo_path.exists():
            l_lbl = QLabel(); l_pix = QPixmap(str(logo_path)).scaledToHeight(55, Qt.TransformationMode.SmoothTransformation); l_lbl.setPixmap(l_pix); header.addWidget(l_lbl)
        title = QLabel("CAPLBolt | <i>Instant Interface Test Script Generator</i>"); title.setStyleSheet(f"font-size: 24px; color: {self.clr_title}; font-weight: bold;"); header.addWidget(title); header.addStretch(); self.main_layout.addWidget(header_widget)

    def _build_log_section(self):
        container = QWidget(); container.setFixedWidth(self.TOTAL_W); layout = QVBoxLayout(container); layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout(); header.addWidget(QLabel("EXECUTION LOGS")); header.addStretch()
        for text, func in [("SAVE", self.download_logs), ("CLEAR", self._clear_log)]:
            btn = QPushButton(text); btn.setObjectName("util_btn"); btn.setFixedSize(90, 30); btn.clicked.connect(func); header.addWidget(btn)
        layout.addLayout(header)
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True); self.log_text.setStyleSheet("background-color: #000000; color: #cbd5e1; font-family: Consolas; border: 1px solid #2d3748; border-radius: 4px;")
        layout.addWidget(self.log_text); self.main_layout.addWidget(container, 1)

    def write_log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S"); self.log_text.append(f"[{ts}] : > {message}"); self.log_text.ensureCursorVisible()

    def _format_time(self, elapsed: float) -> str:
        m, s = divmod(elapsed, 60); ms = int((s - int(s)) * 1000); return f"{int(m):02d}m {int(s):02d}s {ms:03d}ms"

    def _on_pre_process_complete(self):
        self.pre_process_done = True; self._update_gen_button_ui(); self._check_logic_states()

    def _check_logic_states(self):
        paths = [self.req_path_edit.text(), self.arxml_path_edit.text(), self.aacp_path_edit.text(), self.someip_path_edit.text()]
        if all(p.strip() for p in paths):
            self.btn_preprocess.setEnabled(True); self.btn_preprocess.setStyleSheet("background-color: #1e8449; color: white; border-radius: 4px; font-weight: bold; border: none;")
        else:
            self.btn_preprocess.setEnabled(False); self.btn_preprocess.setStyleSheet("background-color: #3b3e40; color: #94a3b8; border-radius: 4px; border: none;")

    def _update_gen_button_ui(self):
        if self.pre_process_done:
            self.btn_gen.setEnabled(True); self.btn_gen.setStyleSheet("background-color: #1e8449; color: white; border-radius: 4px; font-weight: bold; border: none;")

    def run_generation(self):
        ts = time.time()
        try:
            self.write_log(f"📋 Generating: {self.cat_combo.currentText()} / {self.typ_combo.currentText()}")
            self.pipeline.run_generation("GeneratedTestScripts", self.cat_combo.currentText(), self.typ_combo.currentText())
            self.write_log(f"✅ CAPL Scripts Generated Successfully. (Time: {self._format_time(time.time() - ts)})")
        except Exception as e: self.write_log(f"❌ Generation failed: {e}")

    def _clear_log(self): self.log_text.clear()

    def download_logs(self):
        ts = datetime.now().strftime("%d_%m_%Y__%H_%M_%S")
        f, _ = QFileDialog.getSaveFileName(self, "Save Logs", f"CaplGenLogs_{ts}.txt", "Text Files (*.txt)")
        if f:
            with open(f, 'w', encoding='utf-8') as file: file.write(self.log_text.toPlainText())

def launch_gui():
    app = QApplication(sys.argv); gui = CaplGenGUI(); gui.show(); sys.exit(app.exec())
