"""Batch image resize feature: worker thread and page widget."""

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QSpinBox, QProgressBar, QMessageBox,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PIL import Image

from common import (
    SUPPORTED_EXTENSIONS, PROCESS_BTN_STYLE,
    DropArea, build_output_group, make_back_header,
)


class ResizeWorker(QThread):
    progress  = pyqtSignal(int, int, str)  # current, total, filename
    finished  = pyqtSignal(int, int)       # success, failed
    log_error = pyqtSignal(str)

    def __init__(self, files: list[str], width: int,
                 output_dir: str | None, replace: bool):
        super().__init__()
        self.files = files
        self.width = width
        self.output_dir = output_dir
        self.replace = replace

    def run(self):
        success, failed = 0, 0
        for i, filepath in enumerate(self.files):
            path = Path(filepath)
            self.progress.emit(i + 1, len(self.files), path.name)
            try:
                with Image.open(filepath) as img:
                    ow, oh = img.size
                    nw = min(ow, self.width)
                    nh = round(oh * nw / ow)
                    exif = img.info.get('exif')
                    out = img.resize((nw, nh), Image.LANCZOS)
                    dst = self._dst(path)
                    os.makedirs(dst.parent, exist_ok=True)
                    kw: dict = {}
                    s = path.suffix.lower()
                    if s in ('.jpg', '.jpeg'):
                        if out.mode in ('RGBA', 'P', 'LA'):
                            out = out.convert('RGB')
                        kw = {'quality': 90, 'optimize': True}
                        if exif:
                            kw['exif'] = exif
                    elif s == '.png':
                        kw = {'optimize': True}
                    elif s == '.webp':
                        kw = {'quality': 90}
                        if exif:
                            kw['exif'] = exif
                    out.save(str(dst), **kw)
                    success += 1
            except Exception as e:
                failed += 1
                self.log_error.emit(f"{path.name}: {e}")
        self.finished.emit(success, failed)

    def _dst(self, src: Path) -> Path:
        if self.replace:
            return src
        if self.output_dir:
            return Path(self.output_dir) / src.name
        return src.parent / f"{src.stem}_resized{src.suffix}"


class ResizePage(QWidget):
    go_back = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.image_files: list[str] = []
        self.worker: ResizeWorker | None = None
        self.errors: list[str] = []
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 14, 20, 16)
        v.setSpacing(8)

        v.addWidget(make_back_header("批量调整图片尺寸", self.go_back.emit))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(sep)

        content = QWidget()
        h = QHBoxLayout(content)
        h.setSpacing(16)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self._build_left(), stretch=1)
        h.addWidget(self._build_right())
        v.addWidget(content, stretch=1)

    def _build_left(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        v.setContentsMargins(0, 0, 0, 0)

        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self.add_files)

        lbl = QLabel("待处理图片")
        lbl.setStyleSheet("font-weight: bold;")

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
        v.addWidget(lbl)
        v.addWidget(self.file_list, stretch=1)

        row = QHBoxLayout()
        row.addWidget(self.count_label)
        row.addStretch()
        row.addWidget(remove_btn)
        v.addLayout(row)
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(240)
        v = QVBoxLayout(w)
        v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)

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

        out_group, self.radio_same, self.radio_new, self.chk_replace, self.dir_input = \
            build_output_group(self)

        clear_btn = QPushButton("清空列表")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self.clear_files)

        self.process_btn = QPushButton("开始处理")
        self.process_btn.setFixedHeight(40)
        self.process_btn.setStyleSheet(
            PROCESS_BTN_STYLE.format(color="#007AFF", hover="#0066DD", pressed="#0055BB")
        )
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

    def add_files(self, files: list[str]):
        existing = set(self.image_files)
        for f in files:
            if f not in existing:
                self.image_files.append(f)
                existing.add(f)
                item = QListWidgetItem(Path(f).name)
                item.setToolTip(f)
                self.file_list.addItem(item)
        self.count_label.setText(f"{len(self.image_files)} 张图片")

    def remove_selected(self):
        rows = sorted(
            {self.file_list.row(it) for it in self.file_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            self.file_list.takeItem(row)
            self.image_files.pop(row)
        self.count_label.setText(f"{len(self.image_files)} 张图片")

    def clear_files(self):
        self.file_list.clear()
        self.image_files.clear()
        self.count_label.setText("0 张图片")
        self.status_label.setText("")

    def start_processing(self):
        if not self.image_files:
            QMessageBox.warning(self, "提示", "请先添加图片文件")
            return
        if self.radio_new.isChecked():
            output_dir = self.dir_input.text().strip()
            if not output_dir:
                QMessageBox.warning(self, "提示", "请先选择输出目录")
                return
        else:
            output_dir = None

        replace = self.radio_same.isChecked() and self.chk_replace.isChecked()
        self.errors.clear()
        self.process_btn.setEnabled(False)
        self.progress_bar.setMaximum(len(self.image_files))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("准备中…")

        self.worker = ResizeWorker(
            self.image_files.copy(), self.width_spin.value(), output_dir, replace
        )
        self.worker.progress.connect(
            lambda c, t, n: (
                self.progress_bar.setValue(c),
                self.status_label.setText(f"{c}/{t}  {n}"),
            )
        )
        self.worker.finished.connect(self._on_finished)
        self.worker.log_error.connect(self.errors.append)
        self.worker.start()

    def _on_finished(self, success: int, failed: int):
        self.process_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        if failed == 0:
            self.status_label.setText(f"完成 {success} 张 ✓")
            QMessageBox.information(self, "完成", f"全部完成，共处理 {success} 张图片。")
        else:
            self.status_label.setText(f"完成 {success} 张，失败 {failed} 张")
            QMessageBox.warning(self, "部分失败",
                f"完成 {success} 张，失败 {failed} 张。\n\n" + "\n".join(self.errors))
