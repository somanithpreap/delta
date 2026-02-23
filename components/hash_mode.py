from PySide6.QtWidgets import QLabel, QFileDialog
from PySide6.QtCore import Qt, Signal

class DropZone(QLabel):
    file_ready = Signal(str) 

    def __init__(self):
        super().__init__("Drag & drop a file here\n(or click to browse)")
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor) # Changes mouse to a hand on hover
        
        self.default_style = "border: 2px dashed #888; border-radius: 10px; font-size: 18px; margin-top: 10px; padding: 40px; color: #aaa;"
        self.hover_style = "border: 2px dashed #4db6ac; border-radius: 10px; font-size: 18px; margin-top: 10px; padding: 40px; color: #4db6ac; background-color: #1e2b2c;"
        self.setStyleSheet(self.default_style)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self.hover_style)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.default_style)

    def dropEvent(self, event):
        self.setStyleSheet(self.default_style)
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            
            self.file_ready.emit(file_path) 
            break 

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Open the native OS file browser
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "Select a file to hash", 
                "", 
                "All Files (*)"
            )

            if file_path:
                self.file_ready.emit(file_path)