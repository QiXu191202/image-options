"""Image compression feature: worker thread and page widget."""

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QProgressBar, QMessageBox,
    QGroupBox, QSlider, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PIL import Image

from common import (
    PROCESS_BTN_STYLE, fmt_size,
    DropArea, build_output_group, make_back_header,
)


class CompressWorker(QThread):
    file_done = pyqtSignal(int, int, int)  # index, orig_bytes, new_bytes
    finished  = pyqtSignal(int, int)       # success, failed
    log_error = pyqtSignal(str)

    def __init__(self, files: list[str], quality: int,
                 output_dir: str | None, replace: bool):
        super().__init__()
        self.files = files
        self.quality = quality
        self.output_dir = output_dir
        self.replace = replace

    def run(self):
        success, failed = 0, 0
        for i, filepath in enumerate(self.files):
            path = Path(filepath)
            try:
                orig = path.stat().st_size
                with Image.open(filepath) as img:
                    exif = img.info.get('exif')
                    s = path.suffix.lower()
                    kw: dict = {}
                    if s in ('.jpg', '.jpeg'):
                        if img.mode in ('RGBA', 'P', 'LA'):
                            img = img.convert('RGB')
                        kw = {'quality': self.quality, 'optimize': True}
                        if exif:
                            kw['exif'] = exif
                    elif s == '.png':
                        # PNG is lossless; map quality → compress_level (higher quality = less compression)
                        level = max(0, min(9, 9 - round(self.quality / 100 * 9)))
                        kw = {'compress_level': level, 'optimize': True}
                    elif s == '.webp':
                        kw = {'quality': self.quality}
                        if exif:
                            kw['exif'] = exif
                    else:
                        kw = {'optimize': True}
                    dst = self._dst(path)
                    os.makedirs(dst.parent, exist_ok=True)
                    img.save(str(dst), **kw)
                self.file_done.emit(i, orig, dst.stat().st_size)
                success += 1
            except Exception as e:
                failed += 1
                self.log_error.emit(f"{path.name}: {e}")
                self.file_done.emit(i, 0, 0)
        self.finished.emit(success, failed)

    def _dst(self, src: Path) -> Path:
        if self.replace:
            return src
        if self.output_dir:
            return Path(self.output_dir) / src.name
        return src.parent / f"{src.stem}_compressed{src.suffix}"


class CompressPage(QWidget):
    go_back = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.image_files: list[str] = []
        self.worker: CompressWorker | None = None
        self.errors: list[str] = []
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 14, 20, 16)
        v.setSpacing(8)

        v.addWidget(make_back_header("图片压缩", self.go_back.emit))

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

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["文件名", "原始大小", "压缩后大小", "压缩率"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("font-size: 12px;")
        self.table.verticalHeader().setVisible(False)

        self.count_label = QLabel("0 张图片")
        self.count_label.setStyleSheet("color: #888; font-size: 11px;")

        remove_btn = QPushButton("移除选中")
        remove_btn.setFixedHeight(30)
        remove_btn.clicked.connect(self.remove_selected)

        v.addWidget(self.drop_area)
        v.addWidget(lbl)
        v.addWidget(self.table, stretch=1)

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

        quality_group = QGroupBox("压缩质量")
        qg = QVBoxLayout(quality_group)

        self.quality_val = QLabel("85")
        self.quality_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nf = QFont()
        nf.setPointSize(24)
        nf.setBold(True)
        self.quality_val.setFont(nf)

        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(85)
        self.quality_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.quality_slider.setTickInterval(10)
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_val.setText(str(v))
        )

        marks = QHBoxLayout()
        marks.addWidget(QLabel("低"))
        marks.addStretch()
        marks.addWidget(QLabel("高"))

        note = QLabel("JPEG / WebP：直接控制质量\nPNG：无损格式，调节压缩速度")
        note.setStyleSheet("color: #888; font-size: 11px;")
        note.setWordWrap(True)

        qg.addWidget(self.quality_val)
        qg.addWidget(self.quality_slider)
        qg.addLayout(marks)
        qg.addWidget(note)

        out_group, self.radio_same, self.radio_new, self.chk_replace, self.dir_input = \
            build_output_group(self)

        clear_btn = QPushButton("清空列表")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self.clear_files)

        self.process_btn = QPushButton("开始压缩")
        self.process_btn.setFixedHeight(40)
        self.process_btn.setStyleSheet(
            PROCESS_BTN_STYLE.format(color="#34C759", hover="#28A745", pressed="#1E8035")
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

        v.addWidget(quality_group)
        v.addWidget(out_group)
        v.addStretch()
        v.addWidget(clear_btn)
        v.addWidget(self.process_btn)
        v.addWidget(self.progress_bar)
        v.addWidget(self.status_label)
        return w

    def _cell(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def add_files(self, files: list[str]):
        existing = set(self.image_files)
        for f in files:
            if f not in existing:
                self.image_files.append(f)
                existing.add(f)
                r = self.table.rowCount()
                self.table.insertRow(r)
                name_item = QTableWidgetItem(Path(f).name)
                name_item.setToolTip(f)
                self.table.setItem(r, 0, name_item)
                self.table.setItem(r, 1, self._cell(fmt_size(Path(f).stat().st_size)))
                self.table.setItem(r, 2, self._cell("–"))
                self.table.setItem(r, 3, self._cell("–"))
        self.count_label.setText(f"{len(self.image_files)} 张图片")

    def remove_selected(self):
        rows = sorted(
            {self.table.row(it) for it in self.table.selectedItems()},
            reverse=True,
        )
        for row in rows:
            self.table.removeRow(row)
            self.image_files.pop(row)
        self.count_label.setText(f"{len(self.image_files)} 张图片")

    def clear_files(self):
        self.table.setRowCount(0)
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

        for r in range(self.table.rowCount()):
            self.table.setItem(r, 2, self._cell("–"))
            self.table.setItem(r, 3, self._cell("–"))

        replace = self.radio_same.isChecked() and self.chk_replace.isChecked()
        self.errors.clear()
        self.process_btn.setEnabled(False)
        self.progress_bar.setMaximum(len(self.image_files))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("准备中…")

        self.worker = CompressWorker(
            self.image_files.copy(), self.quality_slider.value(), output_dir, replace
        )
        self.worker.file_done.connect(self._on_file_done)
        self.worker.finished.connect(self._on_finished)
        self.worker.log_error.connect(self.errors.append)
        self.worker.start()

    def _on_file_done(self, idx: int, orig: int, new: int):
        self.progress_bar.setValue(idx + 1)
        self.status_label.setText(
            f"{idx + 1}/{len(self.image_files)}  {Path(self.image_files[idx]).name}"
        )
        if orig > 0 and new > 0:
            ratio = (1 - new / orig) * 100
            ratio_item = self._cell(f"{ratio:+.1f}%")
            ratio_item.setForeground(QColor("#28A745") if ratio > 0 else QColor("#FF3B30"))
            self.table.setItem(idx, 2, self._cell(fmt_size(new)))
            self.table.setItem(idx, 3, ratio_item)

    def _on_finished(self, success: int, failed: int):
        self.process_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        if failed == 0:
            self.status_label.setText(f"完成 {success} 张 ✓")
            QMessageBox.information(self, "完成", f"全部完成，共压缩 {success} 张图片。")
        else:
            self.status_label.setText(f"完成 {success} 张，失败 {failed} 张")
            QMessageBox.warning(self, "部分失败",
                f"完成 {success} 张，失败 {failed} 张。\n\n" + "\n".join(self.errors))
