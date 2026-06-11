"""PDF to image feature: convert each PDF page to a JPEG image."""

import os
from pathlib import Path

try:
    import fitz  # PyMuPDF (old import style)
except ModuleNotFoundError:
    import pymupdf as fitz  # PyMuPDF >= 1.24

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QGroupBox, QLineEdit,
    QProgressBar, QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent

from common import (
    PROCESS_BTN_STYLE,
    make_back_header,
    info_box, warning_box, critical_box,
    is_dark,
)

TARGET_WIDTH = 1500


class PdfDropArea(QFrame):
    file_dropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self._hovering = False
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        arrow = QLabel("↓")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont()
        f.setPointSize(28)
        arrow.setFont(f)

        self._hint = QLabel("拖放 PDF 到这里，或点击选择文件")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._sub = QLabel("每次仅处理一个 PDF 文件")
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(arrow)
        layout.addWidget(self._hint)
        layout.addWidget(self._sub)

        self._set_style(False)

    def _set_style(self, hover: bool):
        if self._updating:
            return
        self._updating = True
        self._hovering = hover
        dark = is_dark(self)
        if dark:
            border = "#FF6B35" if hover else "#555555"
            bg     = "#2D1F15" if hover else "#2C2C2E"
            sub_fg = "#AAAAAA"
        else:
            border = "#FF6B35" if hover else "#C0C0C0"
            bg     = "#FFF3EE" if hover else "#F5F5F5"
            sub_fg = "#888888"
        self.setStyleSheet(f"""
            PdfDropArea {{
                border: 2px dashed {border};
                border-radius: 10px;
                background-color: {bg};
            }}
        """)
        self._sub.setStyleSheet(f"font-size: 11px; color: {sub_fg};")
        self._updating = False

    def changeEvent(self, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.PaletteChange:
            self._set_style(self._hovering)
        super().changeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            if any(Path(p).suffix.lower() == ".pdf" for p in paths):
                event.acceptProposedAction()
                self._set_style(True)
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_style(False)

    def dropEvent(self, event: QDropEvent):
        self._set_style(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        pdfs = [p for p in paths if Path(p).suffix.lower() == ".pdf"]
        if pdfs:
            self.file_dropped.emit(pdfs[0])
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 PDF 文件", "", "PDF 文件 (*.pdf)"
        )
        if path:
            self.file_dropped.emit(path)


class PdfWorker(QThread):
    progress  = pyqtSignal(int, int)   # current page (1-based), total
    finished  = pyqtSignal(int)        # saved count
    log_error = pyqtSignal(str)

    def __init__(self, pdf_path: str, prefix: str, output_dir: str):
        super().__init__()
        self.pdf_path   = pdf_path
        self.prefix     = prefix
        self.output_dir = output_dir

    def run(self):
        try:
            doc = fitz.open(self.pdf_path)
            total = doc.page_count
            out_dir = Path(self.output_dir)
            os.makedirs(out_dir, exist_ok=True)
            saved = 0

            for i in range(total):
                self.progress.emit(i + 1, total)
                page = doc[i]
                # Calculate zoom so rendered width = TARGET_WIDTH
                natural_w = page.rect.width
                if natural_w > 0:
                    zoom = TARGET_WIDTH / natural_w
                else:
                    zoom = 1.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                out_path = str(out_dir / f"{self.prefix}-{i + 1}.jpg")
                pix.save(out_path, jpg_quality=92)
                saved += 1

            doc.close()
            self.finished.emit(saved)
        except Exception as e:
            self.log_error.emit(str(e))
            self.finished.emit(0)


class PdfToImagePage(QWidget):
    go_back = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._pdf_path: str | None = None
        self._page_count: int = 0
        self.worker: PdfWorker | None = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 14, 20, 16)
        v.setSpacing(8)

        v.addWidget(make_back_header("PDF 转图片", self.go_back.emit))

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

        self.drop_area = PdfDropArea()
        self.drop_area.file_dropped.connect(self._on_file_dropped)

        self.info_frame = QFrame()
        self.info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.info_frame.setVisible(False)
        info_v = QVBoxLayout(self.info_frame)
        info_v.setContentsMargins(12, 10, 12, 10)
        info_v.setSpacing(4)

        self.pdf_name_lbl = QLabel()
        bold = self.pdf_name_lbl.font()
        bold.setBold(True)
        self.pdf_name_lbl.setFont(bold)

        self.pdf_info_lbl = QLabel()
        self.pdf_info_lbl.setStyleSheet("color: #888; font-size: 12px;")

        info_v.addWidget(self.pdf_name_lbl)
        info_v.addWidget(self.pdf_info_lbl)

        v.addWidget(self.drop_area)
        v.addWidget(self.info_frame)
        v.addStretch()
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(260)
        v = QVBoxLayout(w)
        v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)

        # ── 转换设置 ────────────────────────────────────────────────────────
        conv_group = QGroupBox("转换设置")
        cg = QVBoxLayout(conv_group)
        cg.setSpacing(8)

        width_note = QLabel(f"图片宽度：{TARGET_WIDTH} px（不足时取最大可用宽度）")
        width_note.setStyleSheet("color: #888; font-size: 11px;")
        width_note.setWordWrap(True)
        cg.addWidget(width_note)

        prefix_row = QHBoxLayout()
        prefix_row.addWidget(QLabel("图片前缀："))
        self.prefix_input = QLineEdit("pdf-to")
        self.prefix_input.setFixedWidth(110)
        self.prefix_input.setPlaceholderText("pdf-to")
        self.prefix_input.textChanged.connect(self._update_preview)
        prefix_row.addStretch()
        prefix_row.addWidget(self.prefix_input)
        cg.addLayout(prefix_row)

        naming_note = QLabel("生成文件：前缀-1.jpg, 前缀-2.jpg …")
        naming_note.setStyleSheet("color: #888; font-size: 11px;")
        cg.addWidget(naming_note)

        # ── 保存位置 ────────────────────────────────────────────────────────
        save_group = QGroupBox("保存位置")
        sg = QVBoxLayout(save_group)
        sg.setSpacing(6)

        self.out_path_lbl = QLabel("—")
        self.out_path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        self.out_path_lbl.setWordWrap(True)
        sg.addWidget(self.out_path_lbl)

        browse_row = QHBoxLayout()
        self.custom_dir_input = QLineEdit()
        self.custom_dir_input.setPlaceholderText("默认与 PDF 同级目录")
        self.custom_dir_input.setReadOnly(True)
        self.custom_dir_input.textChanged.connect(self._update_preview)

        browse_btn = QPushButton("选择目录…")
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse_dir)

        clear_btn = QPushButton("恢复默认")
        clear_btn.setFixedHeight(28)
        clear_btn.clicked.connect(self._clear_custom_dir)

        browse_row.addWidget(browse_btn)
        browse_row.addWidget(clear_btn)
        sg.addWidget(self.custom_dir_input)
        sg.addLayout(browse_row)

        # ── 操作区 ──────────────────────────────────────────────────────────
        self.process_btn = QPushButton("开始转换")
        self.process_btn.setFixedHeight(40)
        self.process_btn.setEnabled(False)
        self.process_btn.setStyleSheet(
            PROCESS_BTN_STYLE.format(color="#FF6B35", hover="#E05520", pressed="#C04010")
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

        v.addWidget(conv_group)
        v.addWidget(save_group)
        v.addStretch()
        v.addWidget(self.process_btn)
        v.addWidget(self.progress_bar)
        v.addWidget(self.status_label)
        return w

    # ------------------------------------------------------------------ helpers

    def _output_dir(self) -> str:
        custom = self.custom_dir_input.text().strip()
        prefix = self.prefix_input.text().strip() or "pdf-to"
        if custom:
            return str(Path(custom) / prefix)
        if self._pdf_path:
            return str(Path(self._pdf_path).parent / prefix)
        return "—"

    def _update_preview(self):
        self.out_path_lbl.setText(self._output_dir())

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出根目录")
        if d:
            self.custom_dir_input.setText(d)

    def _clear_custom_dir(self):
        self.custom_dir_input.clear()

    # ------------------------------------------------------------------ slots

    def _on_file_dropped(self, path: str):
        try:
            doc = fitz.open(path)
            n = doc.page_count
            doc.close()
        except Exception as e:
            warning_box(self, "错误", f"无法读取 PDF：{e}")
            return

        self._pdf_path  = path
        self._page_count = n

        self.pdf_name_lbl.setText(Path(path).name)
        self.pdf_info_lbl.setText(f"共 {n} 页")
        self.info_frame.setVisible(True)
        self._update_preview()
        self.process_btn.setEnabled(True)
        self.status_label.setText("")

    def _start_processing(self):
        if not self._pdf_path:
            return

        prefix     = self.prefix_input.text().strip() or "pdf-to"
        output_dir = self._output_dir()

        self.process_btn.setEnabled(False)
        self.progress_bar.setMaximum(self._page_count)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("转换中…")

        self.worker = PdfWorker(self._pdf_path, prefix, output_dir)
        self.worker.progress.connect(
            lambda c, t: (
                self.progress_bar.setValue(c),
                self.status_label.setText(f"{c} / {t}"),
            )
        )
        self.worker.finished.connect(self._on_finished)
        self.worker.log_error.connect(
            lambda msg: critical_box(self, "转换出错", msg)
        )
        self.worker.start()

    def _on_finished(self, saved: int):
        self.process_btn.setEnabled(bool(self._pdf_path))
        self.progress_bar.setVisible(False)
        if saved > 0:
            out_dir = self._output_dir()
            self.status_label.setText(f"完成，共保存 {saved} 张 ✓")
            info_box(self, "完成",
                f"转换完成，共保存 {saved} 张图片。\n\n保存位置：{out_dir}"
            )
        else:
            self.status_label.setText("转换失败")
