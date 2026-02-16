import sys, ctypes, os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, 
                             QHBoxLayout, QVBoxLayout, QFrame, 
                             QLabel, QTabWidget, QLineEdit, QPushButton, QScrollArea)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt
from qt_material import apply_stylesheet
from pathlib import Path
import hashlib

# Components modules
from components.hash_mode import DropZone

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
        self.setMinimumSize(1000, 600)
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
        hash_layout.addStretch()

        self.drop_zone.file_ready.connect(self.process_file)

        self.tabs.addTab(self.hash_page, "Hash Mode")
        self.tabs.addTab(self.delta_page, "Delta Mode")

        # --- DELTA PAGE ---
        delta_layout = QVBoxLayout(self.delta_page)
        delta_placeholder = QLabel("Delta Mode is coming soon!")
        delta_placeholder.setAlignment(Qt.AlignCenter)
        delta_placeholder.setStyleSheet("font-size: 32px; color: #1de9b6;")
        delta_layout.addWidget(delta_placeholder)

        # Assemble
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.tabs)
    
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
    
    def calculate_hashes(self, file_path):
        # Create a fresh dictionary of hasher objects for this file
        hashers = {algo: hashlib.new(algo) for algo in self.supported_algorithms}
        
        try:
            with open(file_path, "rb") as f:
                # Read the file in 64KB chunks
                for byte_block in iter(lambda: f.read(65536), b""):
                    # Feed the chunk to every algorithm
                    for hasher in hashers.values():
                        hasher.update(byte_block)
            
            # Return a dictionary of the final string results
            return {algo: hasher.hexdigest() for algo, hasher in hashers.items()}
            
        except Exception as e:
            # If the file is locked or unreadable, return the error for all boxes
            return {algo: f"Error: {str(e)}" for algo in self.supported_algorithms}
    
    def process_file(self, file_path):
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