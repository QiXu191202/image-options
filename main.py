"""Entry point: home window with feature card navigation."""

import sys

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QStackedWidget,
)
from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QFont

from common import is_dark
from resize import ResizePage
from compress import CompressPage


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
        self._arrow_lbl = QLabel("›")
        af = QFont()
        af.setPointSize(22)
        self._arrow_lbl.setFont(af)

        tv.addWidget(title_lbl)
        tv.addWidget(self._desc_lbl)

        layout.addWidget(icon_lbl)
        layout.addWidget(text_w, stretch=1)
        layout.addWidget(self._arrow_lbl)

        self._set_style(False)

    def _set_style(self, hover: bool):
        if self._updating:
            return
        self._updating = True
        self._hovering = hover
        dark = is_dark(self)

        border = f"{self._accent}99" if hover else ("#555555" if dark else "#DDDDDD")
        bg     = f"{self._accent}18" if hover else "transparent"
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
