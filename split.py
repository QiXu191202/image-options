"""Long-image split feature: split a tall/wide image into N chunks."""

import math
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QGroupBox, QSpinBox,
    QLineEdit, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PIL import Image

from common import (
    PROCESS_BTN_STYLE,
    DropArea, make_back_header,
    info_box, warning_box, critical_box,
)


def _n_range(width: int, height: int) -> tuple[int, int]:
    """Return (n_min, n_max) based on image dimensions for a 4:3 target ratio."""
    long_edge  = max(width, height)
    short_edge = min(width, height)
    if short_edge == 0:
        return 2, 2
    n_max = max(2, math.ceil(long_edge / (short_edge * 4 / 3)))
    return 2, n_max


class SplitWorker(QThread):
    progress  = pyqtSignal(int, int)  # current piece, total
    finished  = pyqtSignal(int)       # saved count
    log_error = pyqtSignal(str)

    def __init__(self, filepath: str, n: int, prefix: str, output_dir: str):
        super().__init__()
        self.filepath   = filepath
        self.n          = n
        self.prefix     = prefix
        self.output_dir = output_dir

    def run(self):
        path = Path(self.filepath)
        try:
            with Image.open(self.filepath) as img:
                w, h      = img.size
                portrait  = h >= w
                long_edge = h if portrait else w
                piece_len = long_edge // self.n

                out_dir = Path(self.output_dir)
                os.makedirs(out_dir, exist_ok=True)

                ext   = path.suffix.lower()
                saved = 0

                for i in range(self.n):
                    self.progress.emit(i + 1, self.n)
                    start = i * piece_len
                    end   = long_edge if i == self.n - 1 else start + piece_len

                    box   = (0, start, w, end) if portrait else (start, 0, end, h)
                    piece = img.crop(box)

                    kw: dict = {}
                    if ext in ('.jpg', '.jpeg'):
                        if piece.mode in ('RGBA', 'P', 'LA'):
                            piece = piece.convert('RGB')
                        kw = {'quality': 92, 'optimize': True}
                    elif ext == '.png':
                        kw = {'optimize': True}
                    elif ext == '.webp':
                        kw = {'quality': 92}

                    piece.save(str(out_dir / f"{self.prefix}-{i + 1}{ext}"), **kw)
                    saved += 1

                self.finished.emit(saved)

        except Exception as e:
            self.log_error.emit(str(e))
            self.finished.emit(0)


class SplitPage(QWidget):
    go_back = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._image_path: str | None = None
        self._img_w = 0
        self._img_h = 0
        self.worker: SplitWorker | None = None
        self._build_ui()

    # ------------------------------------------------------------------ layout

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 14, 20, 16)
        v.setSpacing(8)

        v.addWidget(make_back_header("长图切割", self.go_back.emit))

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
        self.drop_area._hint.setText("拖放图片到这里，或点击选择（单张）")
        self.drop_area._sub.setText("每次仅处理一张，支持 JPG · PNG · WEBP · BMP · TIFF")
        self.drop_area.files_dropped.connect(self._on_files_dropped)

        # Image info card — hidden until an image is loaded
        self.info_frame = QFrame()
        self.info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.info_frame.setVisible(False)
        info_v = QVBoxLayout(self.info_frame)
        info_v.setContentsMargins(12, 10, 12, 10)
        info_v.setSpacing(4)

        self.img_name_lbl = QLabel()
        bold = self.img_name_lbl.font()
        bold.setBold(True)
        self.img_name_lbl.setFont(bold)

        self.img_size_lbl = QLabel()
        self.img_size_lbl.setStyleSheet("color: #888; font-size: 12px;")

        info_v.addWidget(self.img_name_lbl)
        info_v.addWidget(self.img_size_lbl)

        v.addWidget(self.drop_area)
        v.addWidget(self.info_frame)
        v.addStretch()
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(240)
        v = QVBoxLayout(w)
        v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)

        # ── 切割设置 ────────────────────────────────────────────────────────
        split_group = QGroupBox("切割设置")
        sg = QVBoxLayout(split_group)
        sg.setSpacing(8)

        n_row = QHBoxLayout()
        n_row.addWidget(QLabel("切割份数："))
        self.n_spin = QSpinBox()
        self.n_spin.setRange(2, 2)
        self.n_spin.setValue(2)
        self.n_spin.setFixedWidth(80)
        self.n_spin.setEnabled(False)
        n_row.addStretch()
        n_row.addWidget(self.n_spin)
        sg.addLayout(n_row)

        self.n_range_lbl = QLabel("请先选择图片")
        self.n_range_lbl.setStyleSheet("color: #888; font-size: 11px;")
        sg.addWidget(self.n_range_lbl)

        prefix_row = QHBoxLayout()
        prefix_row.addWidget(QLabel("前缀/文件夹："))
        self.prefix_input = QLineEdit("split")
        self.prefix_input.setFixedWidth(100)
        self.prefix_input.setPlaceholderText("split")
        self.prefix_input.textChanged.connect(self._update_out_path_lbl)
        prefix_row.addStretch()
        prefix_row.addWidget(self.prefix_input)
        sg.addLayout(prefix_row)

        naming_note = QLabel("文件名：前缀-1.jpg, 前缀-2.jpg …")
        naming_note.setStyleSheet("color: #888; font-size: 11px;")
        sg.addWidget(naming_note)

        # Output path preview
        out_header = QLabel("保存位置：")
        out_header.setStyleSheet("font-size: 11px; margin-top: 4px;")
        self.out_path_lbl = QLabel("—")
        self.out_path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        self.out_path_lbl.setWordWrap(True)
        sg.addWidget(out_header)
        sg.addWidget(self.out_path_lbl)

        # ── 操作区 ──────────────────────────────────────────────────────────
        self.process_btn = QPushButton("开始切割")
        self.process_btn.setFixedHeight(40)
        self.process_btn.setEnabled(False)
        self.process_btn.setStyleSheet(
            PROCESS_BTN_STYLE.format(color="#FF9500", hover="#E08500", pressed="#C07500")
        )
        self.process_btn.clicked.connect(self._start_processing)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #555; font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        v.addWidget(split_group)
        v.addStretch()
        v.addWidget(self.process_btn)
        v.addWidget(self.progress_bar)
        v.addWidget(self.status_label)
        return w

    # ------------------------------------------------------------------ helpers

    def _update_out_path_lbl(self):
        if not self._image_path:
            self.out_path_lbl.setText("—")
            return
        prefix  = self.prefix_input.text().strip() or "split"
        out_dir = Path(self._image_path).parent / prefix
        self.out_path_lbl.setText(str(out_dir))

    # ------------------------------------------------------------------ slots

    def _on_files_dropped(self, files: list[str]):
        if not files:
            return
        filepath = files[0]
        try:
            with Image.open(filepath) as img:
                w, h = img.size
        except Exception as e:
            warning_box(self, "错误", f"无法读取图片：{e}")
            return

        self._image_path    = filepath
        self._img_w, self._img_h = w, h
        self._refresh_ui()

    def _refresh_ui(self):
        w, h       = self._img_w, self._img_h
        long_edge  = max(w, h)
        short_edge = min(w, h)
        n_min, n_max = _n_range(w, h)
        direction  = "纵向" if h >= w else "横向"

        self.img_name_lbl.setText(Path(self._image_path).name)
        self.img_size_lbl.setText(
            f"{w} × {h} 像素  ·  {direction}  ·  长边 {long_edge} / 短边 {short_edge}"
        )
        self.info_frame.setVisible(True)

        self.n_spin.setEnabled(True)
        self.n_spin.setRange(n_min, n_max)
        self.n_spin.setValue(n_max)
        self.n_range_lbl.setText(f"范围：{n_min} ~ {n_max}（按 4:3 比例推算）")

        self._update_out_path_lbl()
        self.process_btn.setEnabled(True)
        self.status_label.setText("")

    def _start_processing(self):
        if not self._image_path:
            return

        prefix     = self.prefix_input.text().strip() or "split"
        output_dir = str(Path(self._image_path).parent / prefix)
        n          = self.n_spin.value()

        self.process_btn.setEnabled(False)
        self.progress_bar.setMaximum(n)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("切割中…")

        self.worker = SplitWorker(self._image_path, n, prefix, output_dir)
        self.worker.progress.connect(
            lambda c, t: (
                self.progress_bar.setValue(c),
                self.status_label.setText(f"{c} / {t}"),
            )
        )
        self.worker.finished.connect(self._on_finished)
        self.worker.log_error.connect(
            lambda msg: critical_box(self, "切割出错", msg)
        )
        self.worker.start()

    def _on_finished(self, saved: int):
        self.process_btn.setEnabled(bool(self._image_path))
        self.progress_bar.setVisible(False)
        if saved > 0:
            prefix  = self.prefix_input.text().strip() or "split"
            out_dir = str(Path(self._image_path).parent / prefix)
            self.status_label.setText(f"完成，共保存 {saved} 张 ✓")
            info_box(self, "完成",
                f"切割完成，共保存 {saved} 张图片。\n\n保存位置：{out_dir}"
            )
        else:
            self.status_label.setText("切割失败")
