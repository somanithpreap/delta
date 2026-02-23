import sys, ctypes, os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, 
                             QHBoxLayout, QVBoxLayout, QFrame, 
                             QLabel, QTabWidget, QLineEdit, QPushButton, QScrollArea)
from PySide6.QtGui import QIcon, QPixmap, QPalette
from PySide6.QtCore import Qt, QThread, QObject, Signal
from qt_material import apply_stylesheet
from pathlib import Path
import hashlib

# Components modules
from components.hash_mode import DropZone
from components.delta_mode import FileView, QSplitter

class HashWorker(QObject):
    finished = Signal(dict)

    def __init__(self, file_path, algorithms):
        super().__init__()
        self.file_path = file_path
        self.algorithms = algorithms

    def run(self):
        hashers = {algo: hashlib.new(algo) for algo in self.algorithms}
        try:
            with open(self.file_path, "rb") as f:
                # Use a memory-mapped file for efficiency
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    # Read in chunks to avoid holding large chunks in memory
                    chunk_size = 65536
                    for i in range(0, len(mm), chunk_size):
                        chunk = mm[i:i+chunk_size]
                        for hasher in hashers.values():
                            hasher.update(chunk)

            results = {algo: hasher.hexdigest() for algo, hasher in hashers.items()}
            self.finished.emit(results)
        except Exception as e:
            results = {algo: f"Error: {e}" for algo in self.algorithms}
            self.finished.emit(results)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class DeltaApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Delta — File Integrity Checker")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet("background-color: #232629;")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0) # No gaps at edges
        main_layout.setSpacing(0)

        # --- LEFT SIDEBAR ---
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(440)
        self.sidebar.setStyleSheet("border: none;")
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        
        # Set app icon and show logo on the left
        icon_path = resource_path('img/logo-light.png')
        if Path(icon_path).is_file():
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)
        
        logo_path = resource_path('img/logo-name-dark.png')
        if Path(logo_path).is_file():
            logo = QLabel()
            pixmap = QPixmap(logo_path)
            logo.setPixmap(pixmap.scaledToWidth(384, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignCenter)
            sidebar_layout.addWidget(logo)
        else:
            app_name = QLabel("D  E  L  T  A")
            app_name.setAlignment(Qt.AlignCenter)
            app_name.setStyleSheet("font-size: 64px; font-weight: bold; font-family: 'Times New Roman';")
            sidebar_layout.addWidget(app_name)

        # --- RIGHT CONTENT AREA ---
        self.tabs = QTabWidget()

        # Tab pages
        self.hash_page = QWidget()
        self.delta_page = QWidget()

        # --- HASH PAGE ---
        hash_layout = QVBoxLayout(self.hash_page)
        hash_layout.setContentsMargins(20, 20, 20, 20)
        
        self.drop_zone = DropZone()
        hash_layout.addWidget(self.drop_zone)
        
        self.selected_file_label = QLabel("")
        self.selected_file_label.setStyleSheet("font-size: 14px; margin-top: 10px; color: #aaa;")
        hash_layout.addWidget(self.selected_file_label)
        hash_layout.addSpacing(10)

        # Retrieve all guranteed algorithms and excluding variable length ones
        self.supported_algorithms = sorted([algo for algo in hashlib.algorithms_guaranteed if not algo.startswith('shake')])

        # Create a scrollable area for the hash outputs
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 10, 0, 0)

        self.hash_outputs = {}
        for algo in self.supported_algorithms:
            row_layout, output_box = self.create_hash_output(algo.upper() + ':')
            scroll_layout.addLayout(row_layout)
            self.hash_outputs[algo] = output_box

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        hash_layout.addWidget(scroll_area)

        self.drop_zone.file_ready.connect(self.process_file)

        self.tabs.addTab(self.hash_page, "Hash Mode")
        self.tabs.addTab(self.delta_page, "Delta Mode")

        # --- DELTA PAGE ---
        delta_layout = QVBoxLayout(self.delta_page)
        delta_layout.setContentsMargins(20, 20, 20, 20)

        splitter = QSplitter(Qt.Vertical)
        delta_layout.addWidget(splitter)

        self.file1_view = FileView("File 1")
        self.file2_view = FileView("File 2")

        # Explicitly link the two views for comparison
        self.file1_view.other_view = self.file2_view
        self.file2_view.other_view = self.file1_view

        splitter.addWidget(self.file1_view)
        splitter.addWidget(self.file2_view)

        self.compare_button = QPushButton("Compare Files")
        self.compare_button.clicked.connect(self.start_comparison)
        self.compare_button.setCursor(Qt.PointingHandCursor)
        delta_layout.addWidget(self.compare_button)

        # Connect the custom compare_files signal from FileView to a method in DeltaApp
        self.file1_view.update_hashes_signal.connect(self.update_hash_colors)
        self.file2_view.update_hashes_signal.connect(self.update_hash_colors)

        # Assemble
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.tabs)

    def start_comparison(self):
        # First, check if hashes are identical
        hash1 = self.file1_view.hash_output.text()
        hash2 = self.file2_view.hash_output.text()

        if hash1 and hash2 and hash1 == hash2:
            # Hashes match, no need for byte-by-byte comparison.
            # Just ensure both views are displayed without diffs.
            self.file1_view.display_hex()
            self.file2_view.display_hex()
            # Also update hash colors to show they match
            self.update_hash_colors()
            return

        # If hashes don't match or one is missing, proceed with full comparison
        if self.file1_view.file_data and self.file2_view.file_data:
            self.file1_view.compare_and_highlight(self.file2_view.file_data)
            self.file2_view.compare_and_highlight(self.file1_view.file_data)

    def compare_files(self):
        # This method is now primarily for updating hash colors after a file load.
        # The main comparison is triggered by the button.
        self.update_hash_colors()

    def update_hash_colors(self):
        # Compare hashes and update colors
        hash1 = self.file1_view.hash_output.text()
        hash2 = self.file2_view.hash_output.text()
        file1_data = self.file1_view.file_data
        file2_data = self.file2_view.file_data
        limit = 1024 * 1024 # 1 MiB

        primary_color = self.palette().color(QPalette.ColorRole.Highlight).name()
        
        default_stylesheet = f"padding: 5px; color: #aaa;"
        match_stylesheet = f"padding: 5px; color: {primary_color};"
        mismatch_stylesheet = "padding: 5px; color: red;"

        # Enable/disable compare button based on file size
        button_enabled = True
        if (file1_data and len(file1_data) > limit) or \
           (file2_data and len(file2_data) > limit):
            button_enabled = False
        
        # The button should only be active if both files are loaded.
        if not file1_data or not file2_data:
            button_enabled = False

        self.compare_button.setEnabled(button_enabled)

        if hash1 and hash2:
            if hash1 == hash2:
                self.file1_view.hash_output.setStyleSheet(match_stylesheet)
                self.file2_view.hash_output.setStyleSheet(match_stylesheet)
            else:
                self.file1_view.hash_output.setStyleSheet(mismatch_stylesheet)
                self.file2_view.hash_output.setStyleSheet(mismatch_stylesheet)
        elif hash1:
            self.file1_view.hash_output.setStyleSheet(default_stylesheet)
        elif hash2:
            self.file2_view.hash_output.setStyleSheet(default_stylesheet)
    
    def create_hash_output(self, hash_name):
        row_layout = QHBoxLayout()
        
        label = QLabel(hash_name)
        label.setFixedWidth(65) # Fixed width keeps all the text boxes perfectly aligned
        label.setStyleSheet("font-weight: bold;")
        
        # The output box
        output_box = QLineEdit()
        output_box.setReadOnly(True)
        output_box.setPlaceholderText("No file selected...")
        output_box.setStyleSheet("padding: 5px; color: #aaa;") 
        
        # The copy button
        copy_btn = QPushButton("Copy")
        copy_btn.setFixedWidth(70)
        copy_btn.setCursor(Qt.PointingHandCursor)
        
        # Wire the button to the system clipboard
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(output_box.text())
        )
        
        row_layout.addWidget(label)
        row_layout.addWidget(output_box)
        row_layout.addWidget(copy_btn)
        
        return row_layout, output_box
    
    def process_file(self, file_path):
        self.selected_file_label.setText(f"File: {file_path}")
        for box in self.hash_outputs.values():
            box.setText("Calculating...")
        
        self.thread = QThread()
        self.worker = HashWorker(file_path, self.supported_algorithms)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.update_hash_outputs)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def update_hash_outputs(self, results):
        for algo, result in results.items():
            if algo in self.hash_outputs:
                self.hash_outputs[algo].setText(result)
        self.thread.quit()

    def calculate_hashes(self, file_path):
        # This method is now replaced by the HashWorker
        pass

    def process_file_old(self, file_path):
        self.selected_file_label.setText(f"File: {file_path}")
        # Update all UI boxes to show we are working
        for box in self.hash_outputs.values():
            box.setText("Calculating...")
        
        QApplication.processEvents() # Force UI refresh
        
        results = self.calculate_hashes(file_path)
        
        for algo, result in results.items():
            self.hash_outputs[algo].setText(result)

if __name__ == "__main__":
    # Set the taskbar icon on Windows
    if sys.platform == "win32":
        app_id = 'luca.delta.fileintegrity.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)

    app = QApplication([])
    window = DeltaApp()
    apply_stylesheet(app, theme='dark_teal.xml')
    window.show()
    sys.exit(app.exec())