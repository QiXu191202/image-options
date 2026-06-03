"""Entry point: home window with feature card navigation."""

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QStackedWidget,
)
from PyQt6.QtCore import Qt, QEvent, pyqtSignal, QVariantAnimation, QAbstractAnimation
from PyQt6.QtGui import QFont, QIcon, QColor
from PyQt6.QtSvgWidgets import QSvgWidget

from common import is_dark
from resize import ResizePage
from compress import CompressPage
from split import SplitPage

_STATIC = Path(__file__).parent / "static"

# Hover target: soft sky-blue, ~13% opacity — visible on both light & dark
_HOVER_BG = QColor(30, 144, 255, 33)


class FeatureCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, icon_path: str, title: str, desc: str, accent: str):
        super().__init__()
        self._accent = accent
        self._updating = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(84)

        # Smooth background animation
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setStartValue(QColor(30, 144, 255, 0))
        self._anim.setEndValue(_HOVER_BG)
        self._anim.valueChanged.connect(self._apply_bg)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        icon_w = QSvgWidget(icon_path)
        icon_w.setFixedSize(36, 36)

        text_w = QWidget()
        tv = QVBoxLayout(text_w)
        tv.setSpacing(2)
        tv.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(title)
        tf = QFont()
        tf.setPointSize(13)
        tf.setBold(True)
        title_lbl.setFont(tf)

        self._desc_lbl  = QLabel(desc)
        self._arrow_lbl = QLabel("›")
        af = QFont()
        af.setPointSize(22)
        self._arrow_lbl.setFont(af)

        tv.addWidget(title_lbl)
        tv.addWidget(self._desc_lbl)

        layout.addWidget(icon_w)
        layout.addWidget(text_w, stretch=1)
        layout.addWidget(self._arrow_lbl)

        self._refresh_colors()

    # ── style helpers ──────────────────────────────────────────────────────

    def _apply_bg(self, color: QColor):
        """Called every animation frame — only touch the card background."""
        if self._updating:
            return
        self._updating = True
        dark = is_dark(self)
        border = "#555555" if dark else "#DDDDDD"
        r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
        self.setStyleSheet(f"""
            FeatureCard {{
                background-color: rgba({r},{g},{b},{a});
                border: 1.5px solid {border};
                border-radius: 12px;
            }}
        """)
        self._updating = False

    def _refresh_colors(self):
        """Re-apply static sub-label colors (called on init & palette change)."""
        if self._updating:
            return
        self._updating = True
        dark = is_dark(self)
        self.setStyleSheet(f"""
            FeatureCard {{
                background-color: transparent;
                border: 1.5px solid {"#555555" if dark else "#DDDDDD"};
                border-radius: 12px;
            }}
        """)
        self._desc_lbl.setStyleSheet(
            f"font-size: 12px; color: {'#AAAAAA' if dark else '#888888'};"
        )
        self._arrow_lbl.setStyleSheet(
            f"color: {'#888888' if dark else '#BBBBBB'};"
        )
        self._updating = False

    # ── events ─────────────────────────────────────────────────────────────

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:
            self._refresh_colors()
        super().changeEvent(event)

    def enterEvent(self, event):
        self._anim.setDirection(QAbstractAnimation.Direction.Forward)
        self._anim.start()

    def leaveEvent(self, event):
        self._anim.setDirection(QAbstractAnimation.Direction.Backward)
        self._anim.start()

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
        self.split_page    = SplitPage()

        self.resize_page.go_back.connect(lambda: self.stack.setCurrentIndex(0))
        self.compress_page.go_back.connect(lambda: self.stack.setCurrentIndex(0))
        self.split_page.go_back.connect(lambda: self.stack.setCurrentIndex(0))

        self.stack.addWidget(self._build_home())   # 0
        self.stack.addWidget(self.resize_page)     # 1
        self.stack.addWidget(self.compress_page)   # 2
        self.stack.addWidget(self.split_page)      # 3

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

        resize_card   = FeatureCard(str(_STATIC / "resize.svg"),   "批量调整图片尺寸", "拖入图片，批量按指定宽度缩放", "#007AFF")
        compress_card = FeatureCard(str(_STATIC / "compress.svg"), "图片压缩",       "调节质量参数，减小图片文件体积", "#34C759")
        split_card    = FeatureCard(str(_STATIC / "split.svg"),    "长图切割",       "将长图沿长边均匀切割成多份短图", "#FF9500")

        resize_card.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        compress_card.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        split_card.clicked.connect(lambda: self.stack.setCurrentIndex(3))

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.addWidget(resize_card, stretch=1)
        row1.addWidget(compress_card, stretch=1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(split_card, stretch=1)
        row2.addStretch(1)

        v.addWidget(title)
        v.addWidget(sub)
        v.addSpacing(16)
        v.addLayout(row1)
        v.addLayout(row2)
        v.addStretch(3)
        return page


if __name__ == "__main__":
    if sys.platform == "darwin":
        try:
            from Foundation import NSBundle
            _info = NSBundle.mainBundle().infoDictionary()
            _info["CFBundleName"] = "图片工具箱"
            _info["CFBundleDisplayName"] = "图片工具箱"
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("图片工具箱")

    icon_path = Path(__file__).parent / "static" / "EditImage.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
