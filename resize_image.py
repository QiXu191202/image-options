import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QRadioButton, QButtonGroup, QCheckBox, QFileDialog, QProgressBar,
    QGroupBox, QSpinBox, QMessageBox, QAbstractItemView, QFrame,
)
from PyQt6.QtCore import Qt, QThread, QEvent, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QDragEnterEvent, QDropEvent
from PIL import Image


SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'}


class DropArea(QFrame):
    files_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self._hovering = False
        self._updating_style = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        self._arrow = QLabel("↓")
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont()
        f.setPointSize(28)
        self._arrow.setFont(f)

        self._hint = QLabel("拖放图片到这里，或点击选择文件")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._sub = QLabel("支持 JPG · PNG · WEBP · BMP · TIFF")
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub.setStyleSheet("font-size: 11px;")

        layout.addWidget(self._arrow)
        layout.addWidget(self._hint)
        layout.addWidget(self._sub)

        self._set_style(False)

    def _is_dark(self) -> bool:
        # palette().window() 返回 QBrush，避免直接传枚举给 color() 的兼容问题
        return self.palette().window().color().lightness() < 128

    def _set_style(self, hover: bool):
        if self._updating_style:
            return
        self._updating_style = True
        self._hovering = hover
        dark = self._is_dark()
        if dark:
            border = "#409EFF" if hover else "#555555"
            bg     = "#1C2F45" if hover else "#2C2C2E"
            sub_fg = "#AAAAAA"
        else:
            border = "#007AFF" if hover else "#C0C0C0"
            bg     = "#EBF5FF" if hover else "#F5F5F5"
            sub_fg = "#888888"

        self.setStyleSheet(f"""
            DropArea {{
                border: 2px dashed {border};
                border-radius: 10px;
                background-color: {bg};
            }}
        """)
        # QFrame stylesheet 不会向子 QLabel 传递 color，需单独设置
        if hasattr(self, '_sub'):
            self._sub.setStyleSheet(f"font-size: 11px; color: {sub_fg};")
        self._updating_style = False

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:
            self._set_style(self._hovering)
        super().changeEvent(event)

    def _collect_image_paths(self, paths: list[str]) -> list[str]:
        result = []
        for p in paths:
            path = Path(p)
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                result.append(str(path))
            elif path.is_dir():
                for child in sorted(path.iterdir()):
                    if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                        result.append(str(child))
        return result

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            if self._collect_image_paths(paths):
                event.acceptProposedAction()
                self._set_style(True)
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_style(False)

    def dropEvent(self, event: QDropEvent):
        self._set_style(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        files = self._collect_image_paths(paths)
        if files:
            self.files_dropped.emit(files)
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "",
            "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.tif)"
        )
        if files:
            self.files_dropped.emit(files)


class ResizeWorker(QThread):
    progress = pyqtSignal(int, int, str)   # current, total, filename
    finished = pyqtSignal(int, int)         # success_count, fail_count
    log_error = pyqtSignal(str)

    def __init__(self, files: list[str], width: int, output_dir: str | None, replace: bool):
        super().__init__()
        self.files = files
        self.width = width
        self.output_dir = output_dir
        self.replace = replace

    def run(self):
        success, failed = 0, 0
        total = len(self.files)

        for i, filepath in enumerate(self.files):
            path = Path(filepath)
            self.progress.emit(i + 1, total, path.name)
            try:
                with Image.open(filepath) as img:
                    orig_w, orig_h = img.size
                    if orig_w > self.width:
                        new_h = round(orig_h * self.width / orig_w)
                        new_w = self.width
                    else:
                        new_w, new_h = orig_w, orig_h

                    # Preserve EXIF for JPEG
                    exif = img.info.get('exif')

                    resized = img.resize((new_w, new_h), Image.LANCZOS)

                    out_path = self._resolve_output_path(path)
                    os.makedirs(out_path.parent, exist_ok=True)

                    save_kwargs: dict = {}
                    suffix = path.suffix.lower()
                    if suffix in ('.jpg', '.jpeg'):
                        # Convert palette/RGBA modes to RGB for JPEG
                        if resized.mode in ('RGBA', 'P', 'LA'):
                            resized = resized.convert('RGB')
                        save_kwargs['quality'] = 90
                        save_kwargs['optimize'] = True
                        if exif:
                            save_kwargs['exif'] = exif
                    elif suffix == '.png':
                        save_kwargs['optimize'] = True
                    elif suffix == '.webp':
                        save_kwargs['quality'] = 90
                        if exif:
                            save_kwargs['exif'] = exif

                    resized.save(str(out_path), **save_kwargs)
                    success += 1

            except Exception as exc:
                failed += 1
                self.log_error.emit(f"{path.name}: {exc}")

        self.finished.emit(success, failed)

    def _resolve_output_path(self, src: Path) -> Path:
        if self.replace:
            return src
        if self.output_dir:
            return Path(self.output_dir) / src.name
        # Same directory, add _resized suffix
        return src.parent / f"{src.stem}_resized{src.suffix}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.image_files: list[str] = []
        self.worker: ResizeWorker | None = None
        self.errors: list[str] = []
        self.setWindowTitle("批量图片调整尺寸")
        self.setMinimumSize(740, 540)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(self._build_left(), stretch=1)
        layout.addWidget(self._build_right())

    # ── Left panel ────────────────────────────────────────────────────────────

    def _build_left(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        v.setContentsMargins(0, 0, 0, 0)

        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self.add_files)

        list_label = QLabel("待处理图片")
        list_label.setStyleSheet("font-weight: bold;")

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setStyleSheet("font-size: 12px;")

        self.count_label = QLabel("0 张图片")
        self.count_label.setStyleSheet("color: #888; font-size: 11px;")

        remove_btn = QPushButton("移除选中")
        remove_btn.setFixedHeight(30)
        remove_btn.clicked.connect(self.remove_selected)

        v.addWidget(self.drop_area)
        v.addWidget(list_label)
        v.addWidget(self.file_list, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self.count_label)
        bottom_row.addStretch()
        bottom_row.addWidget(remove_btn)
        v.addLayout(bottom_row)
        return w

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(240)
        v = QVBoxLayout(w)
        v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)

        # Size group
        size_group = QGroupBox("调整尺寸")
        sg = QVBoxLayout(size_group)

        row = QHBoxLayout()
        row.addWidget(QLabel("目标宽度："))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 20000)
        self.width_spin.setValue(1920)
        self.width_spin.setSuffix(" px")
        self.width_spin.setSingleStep(10)
        self.width_spin.setFixedWidth(110)
        row.addStretch()
        row.addWidget(self.width_spin)
        sg.addLayout(row)

        note = QLabel("高度按比例自动计算\n原图已小于目标宽度时不放大")
        note.setStyleSheet("color: #888; font-size: 11px;")
        sg.addWidget(note)

        # Output group
        out_group = QGroupBox("输出设置")
        og = QVBoxLayout(out_group)
        og.setSpacing(8)

        self._btn_group = QButtonGroup(self)
        self.radio_same = QRadioButton("保存到原目录")
        self.radio_new = QRadioButton("保存到指定目录")
        self.radio_same.setChecked(True)
        self._btn_group.addButton(self.radio_same)
        self._btn_group.addButton(self.radio_new)

        self.chk_replace = QCheckBox("替换原图（覆盖原始文件）")
        self.chk_replace.setStyleSheet("font-size: 12px; padding-left: 4px;")

        # Custom dir picker (shown only when radio_new is selected)
        self._custom_dir_widget = QWidget()
        cdl = QVBoxLayout(self._custom_dir_widget)
        cdl.setContentsMargins(0, 0, 0, 0)
        cdl.setSpacing(4)
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("点击浏览选择目录…")
        self.dir_input.setReadOnly(True)
        browse_btn = QPushButton("浏览…")
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self.browse_output_dir)
        cdl.addWidget(self.dir_input)
        cdl.addWidget(browse_btn)
        self._custom_dir_widget.setVisible(False)

        self.radio_same.toggled.connect(self._on_output_mode_changed)

        og.addWidget(self.radio_same)
        og.addWidget(self.chk_replace)
        og.addWidget(self.radio_new)
        og.addWidget(self._custom_dir_widget)

        # Action buttons
        clear_btn = QPushButton("清空列表")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self.clear_files)

        self.process_btn = QPushButton("开始处理")
        self.process_btn.setFixedHeight(40)
        self.process_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border-radius: 7px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover  { background-color: #0066DD; }
            QPushButton:pressed { background-color: #0055BB; }
            QPushButton:disabled { background-color: #AAAAAA; }
        """)
        self.process_btn.clicked.connect(self.start_processing)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #555; font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        v.addWidget(size_group)
        v.addWidget(out_group)
        v.addStretch()
        v.addWidget(clear_btn)
        v.addWidget(self.process_btn)
        v.addWidget(self.progress_bar)
        v.addWidget(self.status_label)
        return w

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_output_mode_changed(self, same_checked: bool):
        self.chk_replace.setVisible(same_checked)
        self._custom_dir_widget.setVisible(not same_checked)

    def add_files(self, files: list[str]):
        existing = set(self.image_files)
        for f in files:
            if f not in existing:
                self.image_files.append(f)
                existing.add(f)
                item = QListWidgetItem(Path(f).name)
                item.setToolTip(f)
                self.file_list.addItem(item)
        self._update_count()

    def remove_selected(self):
        rows = sorted(
            {self.file_list.row(it) for it in self.file_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            self.file_list.takeItem(row)
            self.image_files.pop(row)
        self._update_count()

    def clear_files(self):
        self.file_list.clear()
        self.image_files.clear()
        self._update_count()
        self.status_label.setText("")

    def browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.dir_input.setText(d)

    def _update_count(self):
        n = len(self.image_files)
        self.count_label.setText(f"{n} 张图片")

    def start_processing(self):
        if not self.image_files:
            QMessageBox.warning(self, "提示", "请先添加图片文件")
            return

        width = self.width_spin.value()
        replace = self.radio_same.isChecked() and self.chk_replace.isChecked()

        if self.radio_new.isChecked():
            output_dir = self.dir_input.text().strip()
            if not output_dir:
                QMessageBox.warning(self, "提示", "请先选择输出目录")
                return
        else:
            output_dir = None

        self.errors.clear()
        self.process_btn.setEnabled(False)
        self.progress_bar.setMaximum(len(self.image_files))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("准备中…")

        self.worker = ResizeWorker(self.image_files.copy(), width, output_dir, replace)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.log_error.connect(self.errors.append)
        self.worker.start()

    def _on_progress(self, current: int, total: int, name: str):
        self.progress_bar.setValue(current)
        self.status_label.setText(f"{current}/{total}  {name}")

    def _on_finished(self, success: int, failed: int):
        self.process_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if failed == 0:
            msg = f"全部完成，共处理 {success} 张图片。"
            self.status_label.setText(f"完成 {success} 张 ✓")
            QMessageBox.information(self, "完成", msg)
        else:
            msg = f"完成 {success} 张，失败 {failed} 张。\n\n失败详情：\n" + "\n".join(self.errors)
            self.status_label.setText(f"完成 {success} 张，失败 {failed} 张")
            QMessageBox.warning(self, "部分失败", msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("批量图片调整尺寸")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
