import hashlib
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QFileDialog, QFrame, QSplitter, QLineEdit)
from PySide6.QtCore import Qt, QThread, QObject, Signal, QThreadPool, QRunnable

class FileDropZone(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setAlignment(Qt.AlignCenter)
        self.setText("Drag & Drop File Here\nor\nClick to Select")
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            FileDropZone {
                border: 2px dashed #aaa;
                border-radius: 5px;
                padding: 20px;
                font-size: 16px;
                color: #aaa;
                background-color: #2a2d30;
            }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            self.parent().set_file(files[0])

    def mousePressEvent(self, event):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_path:
            self.parent().set_file(file_path)

class Worker(QObject):
    finished = Signal(object)
    progress = Signal(int)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            with open(self.file_path, 'rb') as f:
                file_data = f.read()
            sha256_hash = hashlib.sha256(file_data).hexdigest()
            self.finished.emit((file_data, sha256_hash))
        except Exception as e:
            self.finished.emit(e)

class ChunkComparisonWorker(QRunnable):
    def __init__(self, data1_chunk, data2_chunk, offset, signals):
        super().__init__()
        self.data1_chunk = data1_chunk
        self.data2_chunk = data2_chunk
        self.offset = offset
        self.signals = signals

    def run(self):
        diffs = []
        len1 = len(self.data1_chunk)
        len2 = len(self.data2_chunk)
        max_len = max(len1, len2)

        for i in range(max_len):
            byte1 = self.data1_chunk[i] if i < len1 else -1
            byte2 = self.data2_chunk[i] if i < len2 else -1
            if byte1 != byte2:
                diffs.append(self.offset + i)
        
        # Emit the signal with the result
        self.signals.finished.emit(diffs)


class FileView(QWidget):
    # Signal to notify the parent to update hash colors
    update_hashes_signal = Signal()

    # Define the signals class here
    class WorkerSignals(QObject):
        finished = Signal(list)

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.file_path = None
        self.file_data = None
        self.other_view = None # Will be set by the parent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)

        self.drop_zone = FileDropZone(self)
        layout.addWidget(self.drop_zone)

        hash_layout = QHBoxLayout()
        hash_label = QLabel("SHA256:")
        hash_label.setStyleSheet("font-weight: bold;")
        self.hash_output = QLineEdit()
        self.hash_output.setReadOnly(True)
        self.hash_output.setPlaceholderText("No file selected...")
        self.hash_output.setStyleSheet("padding: 5px; color: #aaa;")
        hash_layout.addWidget(hash_label)
        hash_layout.addWidget(self.hash_output)
        layout.addLayout(hash_layout)

        self.hex_view = QTextEdit()
        self.hex_view.setReadOnly(True)
        self.hex_view.setLineWrapMode(QTextEdit.NoWrap)
        self.hex_view.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #333; font-family: Consolas; font-size: 16px;")
        layout.addWidget(self.hex_view)

        self.threadpool = QThreadPool()
        self.active_comparisons = 0
        self.all_diffs = []

    def set_file(self, file_path):
        self.file_path = file_path
        self.hash_output.setText("Loading...")
        self.hex_view.setText("Loading...")

        self.thread = QThread()
        self.worker = Worker(file_path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.handle_worker_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def handle_worker_finished(self, result):
        if isinstance(result, Exception):
            self.hex_view.setText(f"Error reading file: {result}")
            self.hash_output.setText(f"Error: {result}")
            return

        self.file_data, sha256_hash = result
        self.hash_output.setText(sha256_hash)
        self.display_hex()
        # We no longer automatically compare, just update hash colors
        self.update_hashes_signal.emit()
        self.thread.quit()

    def compare_and_highlight(self, other_data):
        if not self.file_data or not other_data:
            self.display_hex() # Show content if no comparison
            return

        self.display_hex(show_content=False) # Show "Comparing..."

        self.all_diffs = []
        num_threads = self.threadpool.maxThreadCount()
        chunk_size = (max(len(self.file_data), len(other_data)) + num_threads - 1) // num_threads
        
        if chunk_size == 0:
            self.display_hex() # Show content if nothing to compare
            return

        self.active_comparisons = (max(len(self.file_data), len(other_data)) + chunk_size - 1) // chunk_size

        for i in range(0, max(len(self.file_data), len(other_data)), chunk_size):
            data1_chunk = self.file_data[i:i+chunk_size]
            data2_chunk = other_data[i:i+chunk_size]
            
            # Create a signals object for this worker
            signals = self.WorkerSignals()
            signals.finished.connect(self.collect_diffs)
            
            # The worker will emit a signal on this object when done
            worker = ChunkComparisonWorker(data1_chunk, data2_chunk, i, signals)
            self.threadpool.start(worker)

    def collect_diffs(self, diffs):
        self.all_diffs.extend(diffs)
        self.active_comparisons -= 1
        if self.active_comparisons == 0:
            # Sort the diffs to ensure chronological processing
            self.all_diffs.sort()
            self.apply_highlights(self.all_diffs)

    def apply_highlights(self, diff_indices):
        if not self.file_data:
            return

        diff_set = set(diff_indices)
        
        # Using HTML for highlighting is much faster for large numbers of changes
        # than using QTextCursor.
        html_lines = []
        
        # Style for the hex view
        html_lines.append("<pre style='color: #d4d4d4; font-family: Consolas; font-size: 16px; white-space: pre;'>")

        # Determine the maximum length to handle files of different sizes
        max_len = len(self.file_data) if self.file_data else 0
        if self.other_view and self.other_view.file_data:
            max_len = max(max_len, len(self.other_view.file_data))


        for i in range(0, max_len, 16):
            chunk = self.file_data[i:i+16] if self.file_data and i < len(self.file_data) else b''
            
            hex_parts = []
            ascii_parts = []
            for j in range(16):
                byte_pos = i + j
                if j < len(chunk):
                    hex_val = f'{chunk[j]:02X}'
                    if byte_pos in diff_set:
                        hex_parts.append(f'<span style="background-color: red; color: white;">{hex_val}</span>')
                        ascii_parts.append(f'<span style="background-color: red; color: white;">{chr(chunk[j]) if 32 <= chunk[j] <= 126 else "."}</span>')
                    else:
                        hex_parts.append(hex_val)
                        ascii_parts.append(chr(chunk[j]) if 32 <= chunk[j] <= 126 else '.')
                else:
                    # This position doesn't exist in this file but might in the other.
                    # If it's a diff, it means the other file has extra bytes.
                    if byte_pos in diff_set:
                        hex_parts.append('<span style="background-color: red; color: white;">  </span>')
                        ascii_parts.append('<span style="background-color: red; color: white;"> </span>')
                    else:
                        hex_parts.append('  ')
                        ascii_parts.append(' ')

            hex_representation = ' '.join(hex_parts)
            ascii_part = ''.join(ascii_parts) if ascii_parts else ''
            html_lines.append(f'{hex_representation} | {ascii_part}')
        
        html_lines.append("</pre>")
        self.hex_view.setHtml('\n'.join(html_lines))

    def set_file_old(self, file_path):
        self.file_path = file_path
        try:
            with open(file_path, 'rb') as f:
                self.file_data = f.read()
            
            # Calculate and display SHA256 hash
            sha256_hash = hashlib.sha256(self.file_data).hexdigest()
            self.hash_output.setText(sha256_hash)

            self.display_hex()
            self.parent().compare_files()
        except Exception as e:
            self.hex_view.setText(f"Error reading file: {e}")
            self.hash_output.setText(f"Error: {e}")

    def display_hex(self, show_content=True):
        if not self.file_data:
            self.hex_view.setText("")
            return

        if not show_content:
            self.hex_view.setText("Comparing...")
            return
        
        lines = []
        for i in range(0, len(self.file_data), 16):
            chunk = self.file_data[i:i+16]
            
            # Hex part
            hex_representation = ' '.join(f'{byte:02X}' for byte in chunk)
            hex_part = hex_representation.ljust(16 * 3 - 1)

            # ASCII part
            ascii_part = ''.join(chr(byte) if 32 <= byte <= 126 else '.' for byte in chunk)

            lines.append(f'{hex_part} | {ascii_part}')
        
        self.hex_view.setText('\n'.join(lines))

    def highlight_diffs(self, other_data):
        # This method is now replaced by compare_and_highlight and apply_highlights
        pass

class DeltaModeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        main_layout = QVBoxLayout(self)
        
        splitter = QSplitter(Qt.Horizontal)
        
        self.file1_view = FileView("File 1")
        self.file2_view = FileView("File 2")

        splitter.addWidget(self.file1_view)
        splitter.addWidget(self.file2_view)
        
        main_layout.addWidget(splitter)
