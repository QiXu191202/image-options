"""Shared constants, utilities, and reusable widgets."""

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit,
    QGroupBox, QRadioButton, QButtonGroup, QCheckBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent


SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'}


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.2f} MB"


def is_dark(widget: QWidget) -> bool:
    return widget.palette().window().color().lightness() < 128


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


def build_output_group(parent: QWidget):
    """
    Build a reusable output-settings group box.
    Returns (group_widget, radio_same, radio_new, chk_replace, dir_input).
    """
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


def make_back_header(title: str, back_slot) -> QWidget:
    """Top header bar with a back button and page title."""
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
