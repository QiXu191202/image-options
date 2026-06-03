import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QRadioButton, QButtonGroup, QCheckBox, QFileDialog, QProgressBar,
    QGroupBox, QSpinBox, QMessageBox, QAbstractItemView, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QSlider, QStackedWidget,
)
from PyQt6.QtCore import Qt, QThread, QEvent, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QDragEnterEvent, QDropEvent
from PIL import Image


SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'}


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.2f} MB"


def is_dark(widget: QWidget) -> bool:
    return widget.palette().window().color().lightness() < 128


# ── Shared: drag-and-drop area ────────────────────────────────────────────────

class DropArea(QFrame):
    files_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self._hovering = False
        self._updating = False

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

        layout.addWidget(self._arrow)
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
        if hasattr(self, '_sub'):
            self._sub.setStyleSheet(f"font-size: 11px; color: {sub_fg};")
        self._updating = False

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:
            self._set_style(self._hovering)
        super().changeEvent(event)

    def _collect(self, paths: list[str]) -> list[str]:
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
            if self._collect(paths):
                event.acceptProposedAction()
                self._set_style(True)
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_style(False)

    def dropEvent(self, event: QDropEvent):
        self._set_style(False)
        files = self._collect([u.toLocalFile() for u in event.mimeData().urls()])
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


# ── Shared: output settings ───────────────────────────────────────────────────

def build_output_group(parent: QWidget):
    """Returns (group_widget, radio_same, radio_new, chk_replace, dir_input)."""
    group = QGroupBox("输出设置")
    og = QVBoxLayout(group)
    og.setSpacing(8)

    btn_group  = QButtonGroup(parent)
    radio_same = QRadioButton("保存到原目录")
    radio_new  = QRadioButton("保存到指定目录")
    radio_same.setChecked(True)
    btn_group.addButton(radio_same)
    btn_group.addButton(radio_new)

    chk_replace = QCheckBox("替换原图（覆盖原始文件）")
    chk_replace.setStyleSheet("font-size: 12px; padding-left: 4px;")

    custom = QWidget()
    cdl = QVBoxLayout(custom)
    cdl.setContentsMargins(0, 0, 0, 0)
    cdl.setSpacing(4)
    dir_input = QLineEdit()
    dir_input.setPlaceholderText("点击浏览选择目录…")
    dir_input.setReadOnly(True)
    browse_btn = QPushButton("浏览…")
    browse_btn.setFixedHeight(28)
    browse_btn.clicked.connect(
        lambda: dir_input.setText(
            d if (d := QFileDialog.getExistingDirectory(parent, "选择输出目录")) else dir_input.text()
        )
    )
    cdl.addWidget(dir_input)
    cdl.addWidget(browse_btn)
    custom.setVisible(False)

    radio_same.toggled.connect(lambda same: (
        chk_replace.setVisible(same),
        custom.setVisible(not same),
    ))

    og.addWidget(radio_same)
    og.addWidget(chk_replace)
    og.addWidget(radio_new)
    og.addWidget(custom)
    return group, radio_same, radio_new, chk_replace, dir_input


PROCESS_BTN_STYLE = """
    QPushButton {{
        background-color: {color};
        color: white;
        border-radius: 7px;
        font-weight: bold;
        font-size: 14px;
    }}
    QPushButton:hover    {{ background-color: {hover}; }}
    QPushButton:pressed  {{ background-color: {pressed}; }}
    QPushButton:disabled {{ background-color: #888888; }}
"""


def make_back_header(title: str, back_slot) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(10)

    back_btn = QPushButton("← 返回")
    back_btn.setFixedWidth(76)
    back_btn.clicked.connect(back_slot)

    title_lbl = QLabel(title)
    tf = QFont()
    tf.setPointSize(15)
    tf.setBold(True)
    title_lbl.setFont(tf)

    h.addWidget(back_btn)
    h.addWidget(title_lbl)
    h.addStretch()
    return w


# ── Resize feature ────────────────────────────────────────────────────────────

class ResizeWorker(QThread):
    progress  = pyqtSignal(int, int, str)
    finished  = pyqtSignal(int, int)
    log_error = pyqtSignal(str)

    def __init__(self, files, width, output_dir, replace):
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
            lambda c, t, n: (self.progress_bar.setValue(c),
                             self.status_label.setText(f"{c}/{t}  {n}"))
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


# ── Compress feature ──────────────────────────────────────────────────────────

class CompressWorker(QThread):
    file_done = pyqtSignal(int, int, int)
    finished  = pyqtSignal(int, int)
    log_error = pyqtSignal(str)

    def __init__(self, files, quality, output_dir, replace):
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


# ── Feature card (home page) ──────────────────────────────────────────────────

class FeatureCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, desc: str, accent: str):
        super().__init__()
        self._accent = accent
        self._hovering = False
        self._updating = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(84)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setFixedSize(48, 48)
        fi = QFont()
        fi.setPointSize(24)
        icon_lbl.setFont(fi)
        icon_lbl.setStyleSheet(f"background-color: {accent}22; border-radius: 12px;")

        text_w = QWidget()
        tv = QVBoxLayout(text_w)
        tv.setSpacing(2)
        tv.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(title)
        tf = QFont()
        tf.setPointSize(13)
        tf.setBold(True)
        title_lbl.setFont(tf)

        self._desc_lbl = QLabel(desc)

        tv.addWidget(title_lbl)
        tv.addWidget(self._desc_lbl)

        arrow_lbl = QLabel("›")
        af = QFont()
        af.setPointSize(22)
        arrow_lbl.setFont(af)
        self._arrow_lbl = arrow_lbl

        layout.addWidget(icon_lbl)
        layout.addWidget(text_w, stretch=1)
        layout.addWidget(arrow_lbl)

        self._set_style(False)

    def _set_style(self, hover: bool):
        if self._updating:
            return
        self._updating = True
        self._hovering = hover
        dark = is_dark(self)

        if hover:
            border = f"{self._accent}99"
            bg     = f"{self._accent}18"
        else:
            border = "#555555" if dark else "#DDDDDD"
            bg     = "transparent"

        desc_color  = "#AAAAAA" if dark else "#888888"
        arrow_color = "#888888" if dark else "#BBBBBB"

        self.setStyleSheet(f"""
            FeatureCard {{
                background-color: {bg};
                border: 1.5px solid {border};
                border-radius: 12px;
            }}
        """)
        if hasattr(self, '_desc_lbl'):
            self._desc_lbl.setStyleSheet(f"font-size: 12px; color: {desc_color};")
        if hasattr(self, '_arrow_lbl'):
            self._arrow_lbl.setStyleSheet(f"color: {arrow_color};")
        self._updating = False

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:
            self._set_style(self._hovering)
        super().changeEvent(event)

    def enterEvent(self, event):
        self._set_style(True)

    def leaveEvent(self, event):
        self._set_style(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片工具箱")
        self.setMinimumSize(760, 540)
        self.resize(820, 580)
        self._build_ui()

    def _build_ui(self):
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.resize_page   = ResizePage()
        self.compress_page = CompressPage()

        self.resize_page.go_back.connect(lambda: self.stack.setCurrentIndex(0))
        self.compress_page.go_back.connect(lambda: self.stack.setCurrentIndex(0))

        self.stack.addWidget(self._build_home())   # 0
        self.stack.addWidget(self.resize_page)     # 1
        self.stack.addWidget(self.compress_page)   # 2

    def _build_home(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(48, 0, 48, 0)
        v.setSpacing(12)
        v.addStretch(2)

        title = QLabel("图片工具箱")
        tf = QFont()
        tf.setPointSize(22)
        tf.setBold(True)
        title.setFont(tf)

        sub = QLabel("选择要使用的功能")
        sub.setStyleSheet("color: #888888; font-size: 13px;")

        resize_card   = FeatureCard("⊡", "批量调整图片尺寸", "拖入图片，批量按指定宽度缩放", "#007AFF")
        compress_card = FeatureCard("◈", "图片压缩", "调节质量参数，减小图片文件体积", "#34C759")

        resize_card.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        compress_card.clicked.connect(lambda: self.stack.setCurrentIndex(2))

        v.addWidget(title)
        v.addWidget(sub)
        v.addSpacing(16)
        v.addWidget(resize_card)
        v.addWidget(compress_card)
        v.addStretch(3)
        return page


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("图片工具箱")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
