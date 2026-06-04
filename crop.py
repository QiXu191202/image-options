"""Image crop feature: single-image crop in a separate window."""

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QGroupBox, QSpinBox, QComboBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QRectF, QPointF
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush,
    QMouseEvent, QPaintEvent, QGuiApplication,
)
from PIL import Image

from common import (
    PROCESS_BTN_STYLE,
    DropArea, build_output_group, make_back_header,
    info_box, warning_box, critical_box,
)


# (label, w, h) — (0, 0) marks 自由 (free)
RATIO_CHOICES = [
    ("自由比例", 0, 0),
    ("1:1",      1, 1),
    ("4:3",      4, 3),
    ("3:4",      3, 4),
    ("16:9",    16, 9),
    ("9:16",     9, 16),
    ("3:2",      3, 2),
    ("2:3",      2, 3),
]
DEFAULT_RATIO_IDX = 2  # 4:3

HANDLE_SIZE = 10
HANDLE_HIT  = 14
MIN_CROP_PX = 16  # minimum crop side in image pixels


class CropCanvas(QWidget):
    """Interactive crop area: shows the image and a draggable crop rect."""

    cropChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._pixmap: QPixmap | None = None
        self._img_w = 0
        self._img_h = 0
        self._crop = QRectF()  # in image coords
        self._ratio: tuple[int, int] | None = None
        self._drag_mode: str | None = None
        self._drag_anchor_img = QPointF()
        self._drag_crop_start = QRectF()
        self.setMouseTracking(True)
        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ── public API ────────────────────────────────────────────────────────

    def set_image(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self._img_w = pixmap.width()
        self._img_h = pixmap.height()
        self._reset_crop()
        self.update()
        self.cropChanged.emit()

    def set_ratio(self, ratio: tuple[int, int] | None):
        self._ratio = ratio if (ratio and ratio[0] > 0 and ratio[1] > 0) else None
        self._reset_crop()
        self.update()
        self.cropChanged.emit()

    def crop_rect_img(self) -> QRect:
        """Return crop rect in image coordinates (integers, clamped)."""
        if self._img_w == 0 or self._img_h == 0:
            return QRect()
        x = int(round(self._crop.x()))
        y = int(round(self._crop.y()))
        w = int(round(self._crop.width()))
        h = int(round(self._crop.height()))
        x = max(0, min(self._img_w - 1, x))
        y = max(0, min(self._img_h - 1, y))
        w = max(1, min(self._img_w - x, w))
        h = max(1, min(self._img_h - y, h))
        return QRect(x, y, w, h)

    # ── coordinate helpers ────────────────────────────────────────────────

    def _display_rect(self) -> QRectF:
        if not self._pixmap or self._img_w == 0:
            return QRectF()
        ww = max(1, self.width())
        wh = max(1, self.height())
        s = min(ww / self._img_w, wh / self._img_h)
        dw = self._img_w * s
        dh = self._img_h * s
        return QRectF((ww - dw) / 2, (wh - dh) / 2, dw, dh)

    def _scale(self) -> float:
        if self._img_w == 0:
            return 1.0
        return self._display_rect().width() / self._img_w

    def _img_rect_to_widget(self, r: QRectF) -> QRectF:
        d = self._display_rect()
        s = self._scale()
        return QRectF(
            d.x() + r.x() * s, d.y() + r.y() * s,
            r.width() * s, r.height() * s,
        )

    def _widget_to_img(self, p: QPointF) -> QPointF:
        d = self._display_rect()
        s = self._scale() or 1.0
        return QPointF((p.x() - d.x()) / s, (p.y() - d.y()) / s)

    # ── crop initialisation ───────────────────────────────────────────────

    def _reset_crop(self):
        if self._img_w == 0 or self._img_h == 0:
            self._crop = QRectF()
            return
        if self._ratio:
            rw, rh = self._ratio
            target = rw / rh
            img_ratio = self._img_w / self._img_h
            if img_ratio > target:
                ch = float(self._img_h)
                cw = ch * target
            else:
                cw = float(self._img_w)
                ch = cw / target
            cx = (self._img_w - cw) / 2
            cy = (self._img_h - ch) / 2
            self._crop = QRectF(cx, cy, cw, ch)
        else:
            self._crop = QRectF(0, 0, self._img_w, self._img_h)

    # ── hit testing / cursors ─────────────────────────────────────────────

    def _handle_at(self, pos: QPointF) -> str | None:
        if self._crop.isEmpty() or not self._pixmap:
            return None
        cw = self._img_rect_to_widget(self._crop)
        cx1, cy1, cx2, cy2 = cw.left(), cw.top(), cw.right(), cw.bottom()
        ctx = (cx1 + cx2) / 2
        cty = (cy1 + cy2) / 2
        handles = (
            ('nw', cx1, cy1), ('n', ctx, cy1), ('ne', cx2, cy1),
            ('w',  cx1, cty),                  ('e',  cx2, cty),
            ('sw', cx1, cy2), ('s', ctx, cy2), ('se', cx2, cy2),
        )
        for name, hx, hy in handles:
            if abs(pos.x() - hx) <= HANDLE_HIT and abs(pos.y() - hy) <= HANDLE_HIT:
                return name
        if cw.contains(pos):
            return 'move'
        return None

    @staticmethod
    def _cursor_for(mode: str | None) -> Qt.CursorShape:
        return {
            'move': Qt.CursorShape.SizeAllCursor,
            'n': Qt.CursorShape.SizeVerCursor,
            's': Qt.CursorShape.SizeVerCursor,
            'e': Qt.CursorShape.SizeHorCursor,
            'w': Qt.CursorShape.SizeHorCursor,
            'nw': Qt.CursorShape.SizeFDiagCursor,
            'se': Qt.CursorShape.SizeFDiagCursor,
            'ne': Qt.CursorShape.SizeBDiagCursor,
            'sw': Qt.CursorShape.SizeBDiagCursor,
        }.get(mode or '', Qt.CursorShape.ArrowCursor)

    # ── mouse events ──────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        mode = self._handle_at(event.position())
        if not mode:
            return
        self._drag_mode = mode
        self._drag_anchor_img = self._widget_to_img(event.position())
        self._drag_crop_start = QRectF(self._crop)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_mode is None:
            self.setCursor(self._cursor_for(self._handle_at(event.position())))
            return
        cur = self._widget_to_img(event.position())
        dx = cur.x() - self._drag_anchor_img.x()
        dy = cur.y() - self._drag_anchor_img.y()
        self._apply_drag(dx, dy)
        self.update()
        self.cropChanged.emit()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = None
            self.setCursor(self._cursor_for(self._handle_at(event.position())))

    # ── drag math ─────────────────────────────────────────────────────────

    def _apply_drag(self, dx: float, dy: float):
        r = self._drag_crop_start
        if self._drag_mode == 'move':
            nx = max(0, min(self._img_w - r.width(), r.x() + dx))
            ny = max(0, min(self._img_h - r.height(), r.y() + dy))
            self._crop = QRectF(nx, ny, r.width(), r.height())
            return

        left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
        mode = self._drag_mode or ''
        if 'w' in mode:
            left = r.left() + dx
        if 'e' in mode:
            right = r.right() + dx
        if 'n' in mode:
            top = r.top() + dy
        if 's' in mode:
            bottom = r.bottom() + dy

        # Keep min size while preserving anchor sides.
        if right - left < MIN_CROP_PX:
            if 'w' in mode and 'e' not in mode:
                left = right - MIN_CROP_PX
            elif 'e' in mode and 'w' not in mode:
                right = left + MIN_CROP_PX
            else:
                cx = (left + right) / 2
                left, right = cx - MIN_CROP_PX / 2, cx + MIN_CROP_PX / 2
        if bottom - top < MIN_CROP_PX:
            if 'n' in mode and 's' not in mode:
                top = bottom - MIN_CROP_PX
            elif 's' in mode and 'n' not in mode:
                bottom = top + MIN_CROP_PX
            else:
                cy = (top + bottom) / 2
                top, bottom = cy - MIN_CROP_PX / 2, cy + MIN_CROP_PX / 2

        new = QRectF(left, top, right - left, bottom - top)

        if self._ratio:
            new = self._apply_ratio(new, mode)

        new = self._fit_into_image(new, keep_ratio=bool(self._ratio))
        self._crop = new

    def _apply_ratio(self, rect: QRectF, mode: str) -> QRectF:
        rw, rh = self._ratio
        target = rw / rh

        if mode in ('n', 's'):
            new_w = rect.height() * target
            cx = rect.center().x()
            return QRectF(cx - new_w / 2, rect.top(), new_w, rect.height())
        if mode in ('e', 'w'):
            new_h = rect.width() / target
            cy = rect.center().y()
            return QRectF(rect.left(), cy - new_h / 2, rect.width(), new_h)

        # Corner: anchor opposite corner; choose the larger candidate dimension
        anchor_x = rect.right() if 'w' in mode else rect.left()
        anchor_y = rect.bottom() if 'n' in mode else rect.top()
        if rect.width() / target >= rect.height():
            new_w = rect.width()
            new_h = new_w / target
        else:
            new_h = rect.height()
            new_w = new_h * target
        new_x = anchor_x - new_w if 'w' in mode else anchor_x
        new_y = anchor_y - new_h if 'n' in mode else anchor_y
        return QRectF(new_x, new_y, new_w, new_h)

    def _fit_into_image(self, rect: QRectF, keep_ratio: bool) -> QRectF:
        if rect.width() <= 0 or rect.height() <= 0:
            return rect
        if keep_ratio:
            if rect.width() > self._img_w:
                s = self._img_w / rect.width()
                rect = QRectF(rect.left(), rect.top(),
                              rect.width() * s, rect.height() * s)
            if rect.height() > self._img_h:
                s = self._img_h / rect.height()
                rect = QRectF(rect.left(), rect.top(),
                              rect.width() * s, rect.height() * s)
            # Shift into bounds without resizing.
            if rect.left() < 0:
                rect.translate(-rect.left(), 0)
            if rect.top() < 0:
                rect.translate(0, -rect.top())
            if rect.right() > self._img_w:
                rect.translate(self._img_w - rect.right(), 0)
            if rect.bottom() > self._img_h:
                rect.translate(0, self._img_h - rect.bottom())
            return rect

        left = max(0.0, rect.left())
        top = max(0.0, rect.top())
        right = min(float(self._img_w), rect.right())
        bottom = min(float(self._img_h), rect.bottom())
        return QRectF(left, top, max(MIN_CROP_PX, right - left),
                      max(MIN_CROP_PX, bottom - top))

    # ── painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#1f1f1f"))
        if not self._pixmap:
            return
        d = self._display_rect()
        p.drawPixmap(d.toRect(), self._pixmap)
        if self._crop.isEmpty():
            return
        cw = self._img_rect_to_widget(self._crop)
        overlay = QColor(0, 0, 0, 140)
        # Dim outside-crop band on each side.
        if cw.top() > d.top():
            p.fillRect(QRectF(d.left(), d.top(), d.width(), cw.top() - d.top()), overlay)
        if cw.bottom() < d.bottom():
            p.fillRect(QRectF(d.left(), cw.bottom(), d.width(), d.bottom() - cw.bottom()), overlay)
        if cw.left() > d.left():
            p.fillRect(QRectF(d.left(), cw.top(), cw.left() - d.left(), cw.height()), overlay)
        if cw.right() < d.right():
            p.fillRect(QRectF(cw.right(), cw.top(), d.right() - cw.right(), cw.height()), overlay)

        p.setPen(QPen(QColor("#FFFFFF"), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(cw)

        p.setPen(QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DashLine))
        for i in (1, 2):
            x = cw.left() + cw.width() * i / 3
            p.drawLine(QPointF(x, cw.top()), QPointF(x, cw.bottom()))
            y = cw.top() + cw.height() * i / 3
            p.drawLine(QPointF(cw.left(), y), QPointF(cw.right(), y))

        p.setPen(QPen(QColor("#1E90FF"), 1))
        p.setBrush(QBrush(QColor("#FFFFFF")))
        hs = HANDLE_SIZE
        ctx = (cw.left() + cw.right()) / 2
        cty = (cw.top() + cw.bottom()) / 2
        for hx, hy in (
            (cw.left(), cw.top()),   (ctx, cw.top()),    (cw.right(), cw.top()),
            (cw.left(), cty),                            (cw.right(), cty),
            (cw.left(), cw.bottom()), (ctx, cw.bottom()), (cw.right(), cw.bottom()),
        ):
            p.drawRect(QRectF(hx - hs / 2, hy - hs / 2, hs, hs))


class CropWindow(QDialog):
    """Stand-alone window: crop UI plus output settings."""

    saved = pyqtSignal(str)

    def __init__(self, image_path: str, pixmap: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)
        self._image_path = image_path
        self._pixmap = pixmap
        self._img_w = pixmap.width()
        self._img_h = pixmap.height()
        self.setWindowTitle(f"裁剪图片 — {Path(image_path).name}")
        self._suppress_link = False
        self._build_ui()
        self._fit_to_screen()
        self.ratio_combo.setCurrentIndex(DEFAULT_RATIO_IDX)
        if DEFAULT_RATIO_IDX == 0:
            self._on_ratio_changed(0)  # ensure initial sync if combo didn't change

    # ── layout ────────────────────────────────────────────────────────────

    def _build_ui(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 12, 12, 12)
        h.setSpacing(12)

        self.canvas = CropCanvas()
        h.addWidget(self.canvas, stretch=1)

        right = QWidget()
        right.setFixedWidth(260)
        v = QVBoxLayout(right)
        v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)

        info = QLabel(f"原图：{self._img_w} × {self._img_h} px")
        info.setStyleSheet("color: #888; font-size: 12px;")

        # ── 比例 ────────────────────────────────────────────────────────
        ratio_group = QGroupBox("裁剪比例")
        rg = QVBoxLayout(ratio_group)
        self.ratio_combo = QComboBox()
        for label, _, _ in RATIO_CHOICES:
            self.ratio_combo.addItem(label)
        self.ratio_combo.currentIndexChanged.connect(self._on_ratio_changed)
        rg.addWidget(self.ratio_combo)
        ratio_note = QLabel("选定比例后裁剪框按最大可见区域居中")
        ratio_note.setStyleSheet("color: #888; font-size: 11px;")
        ratio_note.setWordWrap(True)
        rg.addWidget(ratio_note)

        # ── 输出尺寸 ────────────────────────────────────────────────────
        size_group = QGroupBox("输出尺寸")
        sg = QVBoxLayout(size_group)
        sg.setSpacing(6)

        crop_row = QHBoxLayout()
        crop_row.addWidget(QLabel("裁剪框："))
        self.crop_size_lbl = QLabel("—")
        self.crop_size_lbl.setStyleSheet("color: #888; font-size: 11px;")
        crop_row.addStretch()
        crop_row.addWidget(self.crop_size_lbl)
        sg.addLayout(crop_row)

        self.canvas.cropChanged.connect(self._on_crop_changed)
        self.canvas.set_image(self._pixmap)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("宽"))
        self.out_w_spin = QSpinBox()
        self.out_w_spin.setRange(1, max(self._img_w, 1))
        self.out_w_spin.setFixedWidth(86)
        self.out_w_spin.setSuffix(" px")
        out_row.addWidget(self.out_w_spin)
        out_row.addWidget(QLabel("×"))
        self.out_h_spin = QSpinBox()
        self.out_h_spin.setRange(1, max(self._img_h, 1))
        self.out_h_spin.setFixedWidth(86)
        self.out_h_spin.setSuffix(" px")
        out_row.addWidget(self.out_h_spin)
        sg.addLayout(out_row)

        self.out_w_spin.valueChanged.connect(self._on_out_w_changed)
        self.out_h_spin.valueChanged.connect(self._on_out_h_changed)

        self.use_crop_btn = QPushButton("使用裁剪框原始尺寸")
        self.use_crop_btn.setFixedHeight(26)
        self.use_crop_btn.clicked.connect(self._set_out_to_crop_size)
        sg.addWidget(self.use_crop_btn)

        size_note = QLabel("最大不超过原图实际尺寸")
        size_note.setStyleSheet("color: #888; font-size: 11px;")
        sg.addWidget(size_note)

        # ── 输出位置 ────────────────────────────────────────────────────
        out_group, self.radio_same, self.radio_new, self.chk_replace, self.dir_input = \
            build_output_group(self)

        # ── 按钮 ────────────────────────────────────────────────────────
        self.confirm_btn = QPushButton("保存裁剪")
        self.confirm_btn.setFixedHeight(40)
        self.confirm_btn.setStyleSheet(
            PROCESS_BTN_STYLE.format(color="#AF52DE", hover="#9540C2", pressed="#7A30A0")
        )
        self.confirm_btn.clicked.connect(self._save)

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self.reject)

        v.addWidget(info)
        v.addWidget(ratio_group)
        v.addWidget(size_group)
        v.addWidget(out_group)
        v.addStretch()
        v.addWidget(self.confirm_btn)
        v.addWidget(cancel_btn)
        h.addWidget(right)

    # ── sizing ────────────────────────────────────────────────────────────

    def _fit_to_screen(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            self.resize(1000, 700)
            return
        available = screen.availableGeometry()
        max_w = int(available.width() * 0.95)
        max_h = int(available.height() * 0.92)

        side_panel = 260
        h_margins  = 12 * 3   # left, middle, right
        v_margins  = 12 * 2
        canvas_max_w = max_w - side_panel - h_margins
        canvas_max_h = max_h - v_margins

        if self._img_w > 0 and self._img_h > 0:
            s = min(canvas_max_w / self._img_w, canvas_max_h / self._img_h, 1.0)
            canvas_w = max(420, int(self._img_w * s))
            canvas_h = max(420, int(self._img_h * s))
        else:
            canvas_w, canvas_h = 600, 500

        win_w = min(max_w, canvas_w + side_panel + h_margins)
        win_h = min(max_h, canvas_h + v_margins)
        self.resize(win_w, win_h)
        self.move(
            available.x() + (available.width() - win_w) // 2,
            available.y() + (available.height() - win_h) // 2,
        )

    # ── ratio + spin sync ─────────────────────────────────────────────────

    def _current_ratio(self) -> tuple[int, int] | None:
        _, rw, rh = RATIO_CHOICES[self.ratio_combo.currentIndex()]
        return (rw, rh) if rw > 0 else None

    def _on_ratio_changed(self, idx: int):
        _, rw, rh = RATIO_CHOICES[idx]
        ratio = (rw, rh) if rw > 0 else None
        self.canvas.set_ratio(ratio)
        self._set_out_to_crop_size()

    def _on_crop_changed(self):
        cr = self.canvas.crop_rect_img()
        self.crop_size_lbl.setText(f"{cr.width()} × {cr.height()} px")

    def _set_out_to_crop_size(self):
        cr = self.canvas.crop_rect_img()
        if cr.isEmpty():
            return
        self.crop_size_lbl.setText(f"{cr.width()} × {cr.height()} px")
        self._suppress_link = True
        self.out_w_spin.setMaximum(self._img_w)
        self.out_h_spin.setMaximum(self._img_h)
        self.out_w_spin.setValue(cr.width())
        self.out_h_spin.setValue(cr.height())
        self._suppress_link = False

    def _on_out_w_changed(self, v: int):
        if self._suppress_link:
            return
        ratio = self._current_ratio()
        if not ratio:
            return
        rw, rh = ratio
        new_h = max(1, min(self._img_h, int(round(v * rh / rw))))
        self._suppress_link = True
        self.out_h_spin.setValue(new_h)
        self._suppress_link = False

    def _on_out_h_changed(self, v: int):
        if self._suppress_link:
            return
        ratio = self._current_ratio()
        if not ratio:
            return
        rw, rh = ratio
        new_w = max(1, min(self._img_w, int(round(v * rw / rh))))
        self._suppress_link = True
        self.out_w_spin.setValue(new_w)
        self._suppress_link = False

    # ── save ──────────────────────────────────────────────────────────────

    def _save(self):
        cr = self.canvas.crop_rect_img()
        if cr.width() < 1 or cr.height() < 1:
            warning_box(self, "提示", "裁剪框无效")
            return

        out_w = self.out_w_spin.value()
        out_h = self.out_h_spin.value()

        src = Path(self._image_path)
        if self.radio_same.isChecked():
            if self.chk_replace.isChecked():
                dst = src
            else:
                dst = src.parent / f"{src.stem}_cropped{src.suffix}"
        else:
            d = self.dir_input.text().strip()
            if not d:
                warning_box(self, "提示", "请先选择输出目录")
                return
            dst = Path(d) / src.name

        try:
            os.makedirs(dst.parent, exist_ok=True)
            with Image.open(self._image_path) as img:
                exif = img.info.get('exif')
                box = (cr.x(), cr.y(), cr.x() + cr.width(), cr.y() + cr.height())
                piece = img.crop(box)
                if (piece.width, piece.height) != (out_w, out_h):
                    piece = piece.resize((out_w, out_h), Image.LANCZOS)
                s = src.suffix.lower()
                kw: dict = {}
                if s in ('.jpg', '.jpeg'):
                    if piece.mode in ('RGBA', 'P', 'LA'):
                        piece = piece.convert('RGB')
                    kw = {'quality': 92, 'optimize': True}
                    if exif:
                        kw['exif'] = exif
                elif s == '.png':
                    kw = {'optimize': True}
                elif s == '.webp':
                    kw = {'quality': 92}
                    if exif:
                        kw['exif'] = exif
                piece.save(str(dst), **kw)
        except Exception as e:
            critical_box(self, "裁剪失败", str(e))
            return

        self.saved.emit(str(dst))
        info_box(self, "完成", f"裁剪完成，已保存到：\n{dst}")
        self.accept()


class CropPage(QWidget):
    """Entry page inside the main window — opens CropWindow on file drop."""

    go_back = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._crop_window: CropWindow | None = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 14, 20, 16)
        v.setSpacing(8)

        v.addWidget(make_back_header("图片裁剪", self.go_back.emit))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(sep)

        self.drop_area = DropArea()
        self.drop_area._hint.setText("拖放图片到这里，或点击选择（单张）")
        self.drop_area._sub.setText("每次仅处理一张，支持 JPG · PNG · WEBP · BMP · TIFF")
        self.drop_area.files_dropped.connect(self._on_files_dropped)

        note = QLabel(
            "选择图片后将打开独立的裁剪窗口；\n"
            "可在新窗口中设置裁剪比例、输出尺寸与保存方式"
        )
        note.setStyleSheet("color: #888; font-size: 12px;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)

        v.addWidget(self.drop_area)
        v.addSpacing(4)
        v.addWidget(note)
        v.addStretch()

    def _on_files_dropped(self, files: list[str]):
        if not files:
            return
        path = files[0]
        pixmap = QPixmap(path)
        if pixmap.isNull():
            warning_box(self, "错误", f"无法读取图片：\n{path}")
            return
        win = CropWindow(path, pixmap, parent=self.window())
        win.setModal(False)
        win.show()
        win.raise_()
        win.activateWindow()
        self._crop_window = win  # retain reference so it isn't GC'd
