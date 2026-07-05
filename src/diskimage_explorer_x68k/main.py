from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Callable

from PySide6.QtCore import QMimeData, QSettings, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDrag, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QTabWidget,
)

from .backend import FatImageBackend, ImageMountError, _normalize_path_for_x68k, _to_fat_sfn, HAS_TWENTYONE_SUPPORT
from .column_view import CustomColumnView

# TwentyOne support imports (conditional)
if HAS_TWENTYONE_SUPPORT:
    try:
        from .twentyone_dialog import TwentyOneFileDialog, TwentyOneFileContentDialog
    except ImportError:
        HAS_TWENTYONE_SUPPORT = False


def _join(base: str, name: str) -> str:
    if base == "/":
        return f"/{name}"
    return f"{base.rstrip('/')}/{name}"


def _parent(path: str) -> str:
    p = PurePosixPath(path)
    pp = str(p.parent)
    return pp if pp.startswith("/") else "/"


class DropTreeWidget(QTreeWidget):
    localPathsDropped = Signal(list, str, bool)

    def __init__(self) -> None:
        super().__init__()
        self._external_url_provider: Callable[[], list[QUrl]] | None = None
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeWidget.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        
        # ハイライト設定
        self.setStyleSheet(
            "QTreeWidget { "
            "background-color: white; "
            "} "
            "QTreeWidget::item { "
            "padding: 2px; "
            "} "
            "QTreeWidget::item:selected { "
            "background-color: #0078d4 !important; "
            "color: white !important; "
            "} "
            "QTreeWidget::item:hover { "
            "background-color: #e8f0f8; "
            "}"
        )
        self.setFocusPolicy(Qt.StrongFocus)

    def set_external_url_provider(self, provider: Callable[[], list[QUrl]]) -> None:
        self._external_url_provider = provider

    def startDrag(self, supportedActions: Qt.DropActions) -> None:
        if self._external_url_provider is None:
            return

        urls = self._external_url_provider()
        if not urls:
            return

        mime = QMimeData()
        mime.setUrls(urls)

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return

        local_paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                local_paths.append(url.toLocalFile())

        item = self.itemAt(event.position().toPoint())
        if item is not None:
            target_path = item.data(0, Qt.UserRole)
            target_is_dir = bool(item.data(0, Qt.UserRole + 1))
        else:
            target_path = "/"
            target_is_dir = True

        if local_paths:
            self.localPathsDropped.emit(local_paths, target_path, target_is_dir)
            event.acceptProposedAction()


class SpinnerWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(80)
        self.setFixedSize(42, 42)

    def start(self) -> None:
        self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        radius = min(self.width(), self.height()) / 2 - 4
        for i in range(12):
            alpha = int(255 * (i + 1) / 12)
            color = QColor(64, 128, 255, alpha)
            pen = QPen(color, 3)
            p.setPen(pen)
            p.save()
            p.translate(center)
            p.rotate(self._angle - i * 30)
            p.drawLine(0, int(-radius), 0, int(-(radius - 7)))
            p.restore()


class BusyOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 72);")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QFrame(self)
        panel.setStyleSheet(
            "QFrame {"
            "background-color: rgba(25, 25, 25, 220);"
            "border: 1px solid rgba(255, 255, 255, 48);"
            "border-radius: 10px;"
            "}"
            "QLabel { color: white; }"
        )

        panel_l = QVBoxLayout(panel)
        panel_l.setContentsMargins(22, 18, 22, 18)
        panel_l.setSpacing(10)
        panel_l.setAlignment(Qt.AlignCenter)

        self.spinner = SpinnerWidget(panel)
        self.label = QLabel("Processing...", panel)
        self.label.setAlignment(Qt.AlignCenter)
        panel_l.addWidget(self.spinner, alignment=Qt.AlignCenter)
        panel_l.addWidget(self.label)

        outer.addStretch(1)
        outer.addWidget(panel, alignment=Qt.AlignCenter)
        outer.addStretch(1)

        self.hide()

    def show_with_message(self, message: str) -> None:
        self.label.setText(message)
        self.show()
        self.raise_()
        self.spinner.start()

    def hide_overlay(self) -> None:
        self.spinner.stop()
        self.hide()


class TaskThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, work: Callable[[], Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._work = work

    def run(self) -> None:
        try:
            result = self._work()
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.backend = FatImageBackend()
        self._updating_offset_combo = False
        self._syncing_selection = False
        self._drag_export_dirs: list[Path] = []
        self._busy_thread: TaskThread | None = None
        self._busy_overlay: BusyOverlay | None = None
        self._settings = QSettings("diskimage_explorer_x68k", "diskimage_explorer_x68k")
        self._mount_history: list[str] = []
        self._max_mount_history = 12

        self.setWindowTitle("diskimage_explorer_x68k")
        self.resize(1080, 720)

        self._build_ui()
        self._build_menu()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)

        top = QHBoxLayout()
        outer.addLayout(top)

        self.btn_open = QPushButton("Mount")
        self._mount_menu = QMenu(self.btn_open)
        self.btn_unmount = QPushButton("Unmount")
        self.btn_refresh = QPushButton("Refresh")
        self.btn_new_file = QPushButton("New File")
        self.btn_new_dir = QPushButton("New Folder")
        self.btn_delete = QPushButton("Delete")
        self.btn_backup_now = QPushButton("Backup Now")
        self.chk_backup_on_open = QCheckBox("Backup on Open")
        self.chk_backup_on_open.setChecked(True)

        self.offset_combo = QComboBox()
        self.offset_combo.setMinimumWidth(250)
        self.lbl_info = QLabel("No image loaded")

        top.addWidget(self.btn_open)
        top.addWidget(self.btn_unmount)
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_new_file)
        top.addWidget(self.btn_new_dir)
        top.addWidget(self.btn_delete)
        top.addWidget(self.btn_backup_now)
        top.addWidget(self.chk_backup_on_open)
        top.addWidget(QLabel("Offset:"))
        top.addWidget(self.offset_combo)
        top.addStretch(1)

        outer.addWidget(self.lbl_info)

        # ツリービュー設定
        self.tree = DropTreeWidget()
        self.tree.set_external_url_provider(self._build_external_drag_urls)
        self.tree.setHeaderLabels(["Name", "Type", "Size", "Modified"])
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 88)
        self.tree.setColumnWidth(2, 92)
        self.tree.setColumnWidth(3, 190)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setSelectionBehavior(QTreeWidget.SelectRows)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setUniformRowHeights(True)
        
        # カラムビュー設定
        self.column_view = CustomColumnView(None)
        
        # タブウィジェットで両方を表示
        self.view_tabs = QTabWidget()
        self.view_tabs.addTab(self.tree, "Tree View")
        self.view_tabs.addTab(self.column_view, "Column View")
        outer.addWidget(self.view_tabs)

        self._busy_overlay = BusyOverlay(root)
        self._busy_overlay.setGeometry(root.rect())

        self.statusBar().showMessage("Ready")

        self._load_mount_history()
        self._rebuild_mount_history_menu()

        self.btn_unmount.clicked.connect(self.unmount_image)
        self.btn_open.clicked.connect(self._show_mount_menu)
        self.btn_refresh.clicked.connect(self.refresh_tree)
        self.btn_new_file.clicked.connect(self.create_new_file)
        self.btn_new_dir.clicked.connect(self.create_new_dir)
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_backup_now.clicked.connect(self.backup_now)
        self.offset_combo.currentIndexChanged.connect(self.on_offset_changed)
        self.tree.localPathsDropped.connect(self.on_local_paths_dropped)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.column_view.filesDropped.connect(self.on_local_paths_dropped)
        self.column_view.pathChanged.connect(self._on_column_view_path_changed)
        self.column_view.fileViewRequested.connect(self._view_file)
        self.column_view.fileEditRequested.connect(self._edit_file)
        self._update_mount_controls()

    def _load_mount_history(self) -> None:
        raw = self._settings.value("mount_history", [])
        if isinstance(raw, str):
            self._mount_history = [raw]
        elif isinstance(raw, list):
            self._mount_history = [str(x) for x in raw if str(x)]
        else:
            self._mount_history = []

    def _save_mount_history(self) -> None:
        self._settings.setValue("mount_history", self._mount_history)

    def _push_mount_history(self, image_path: str) -> None:
        image_path = str(Path(image_path))
        self._mount_history = [p for p in self._mount_history if p != image_path]
        self._mount_history.insert(0, image_path)
        self._mount_history = self._mount_history[: self._max_mount_history]
        self._save_mount_history()
        self._rebuild_mount_history_menu()

    def _rebuild_mount_history_menu(self) -> None:
        self._mount_menu.clear()

        act_choose = self._mount_menu.addAction("Choose file")
        act_choose.triggered.connect(self.open_image)

        self._mount_menu.addSeparator()

        if not self._mount_history:
            act_empty = self._mount_menu.addAction("No recent images")
            act_empty.setEnabled(False)
            return

        for path in self._mount_history:
            act = self._mount_menu.addAction(path)
            act.setToolTip(path)
            act.triggered.connect(lambda _checked=False, selected=path: self._mount_image_path(selected))

    def _show_mount_menu(self) -> None:
        pos = self.btn_open.mapToGlobal(self.btn_open.rect().bottomLeft())
        self._mount_menu.exec(pos)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._busy_overlay is not None and self.centralWidget() is not None:
            self._busy_overlay.setGeometry(self.centralWidget().rect())

    def _set_interaction_enabled(self, enabled: bool) -> None:
        self.btn_open.setEnabled(enabled)
        self.btn_unmount.setEnabled(enabled)
        self.btn_refresh.setEnabled(enabled)
        self.btn_new_file.setEnabled(enabled)
        self.btn_new_dir.setEnabled(enabled)
        self.btn_delete.setEnabled(enabled)
        self.btn_backup_now.setEnabled(enabled)
        self.chk_backup_on_open.setEnabled(enabled)
        self.offset_combo.setEnabled(enabled)
        self.tree.setEnabled(enabled)

    def _is_mounted(self) -> bool:
        return self.backend.fs is not None

    def _update_mount_controls(self) -> None:
        mounted = self._is_mounted()
        self.btn_unmount.setEnabled(mounted)

    def _run_busy_task(
        self,
        message: str,
        work: Callable[[], Any],
        on_success: Callable[[Any], None],
        error_title: str,
    ) -> None:
        if self._busy_thread is not None:
            return
        if self._busy_overlay is None:
            return

        self._set_interaction_enabled(False)
        self._busy_overlay.show_with_message(message)

        thread = TaskThread(work, self)
        self._busy_thread = thread

        thread.succeeded.connect(on_success)
        thread.failed.connect(lambda msg: QMessageBox.critical(self, error_title, msg))
        thread.finished.connect(self._on_busy_finished)
        thread.start()

    def _on_busy_finished(self) -> None:
        if self._busy_overlay is not None:
            self._busy_overlay.hide_overlay()
        self._set_interaction_enabled(True)
        self._update_mount_controls()

        if self._busy_thread is not None:
            self._busy_thread.deleteLater()
            self._busy_thread = None

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")

        act_open = QAction("Open...", self)
        act_open.triggered.connect(self.open_image)
        file_menu.addAction(act_open)

        act_extract = QAction("Extract Selected File...", self)
        act_extract.triggered.connect(self.extract_selected_file)
        file_menu.addAction(act_extract)

    def _set_info_label(self) -> None:
        if self.backend.image_path is None:
            self.lbl_info.setText("No image loaded")
            return

        label = self.backend.get_offset_label(self.backend.current_offset)
        text = f"Image: {self.backend.image_path} | Mount: {label}"
        if self.backend.backup_path is not None:
            text += f" | Backup: {self.backend.backup_path}"
        self.lbl_info.setText(text)

    def _selected_items(self) -> list[QTreeWidgetItem]:
        return self.tree.selectedItems()

    def _selected_top_level_paths(self) -> list[str]:
        items = self._selected_items()
        selected_paths = [str(i.data(0, Qt.UserRole)) for i in items]
        selected_set = set(selected_paths)
        out: list[str] = []
        for p in selected_paths:
            parent = _parent(p)
            keep = True
            while parent != "/":
                if parent in selected_set:
                    keep = False
                    break
                parent = _parent(parent)
            if keep:
                out.append(p)
        return out

    def _unique_local_target(self, root: Path, name: str) -> Path:
        base = name.strip() or "item"
        candidate = root / base
        if not candidate.exists():
            return candidate
        idx = 1
        while True:
            alt = root / f"{base}_{idx}"
            if not alt.exists():
                return alt
            idx += 1

    def _build_external_drag_urls(self) -> list[QUrl]:
        if self.backend.fs is None:
            return []

        fs_paths = self._selected_top_level_paths()
        if not fs_paths:
            return []

        tmp_root = Path(tempfile.mkdtemp(prefix="x68k-hdf-export-"))
        urls: list[QUrl] = []

        try:
            for fs_path in fs_paths:
                src_name = PurePosixPath(fs_path).name or "item"
                local_target = self._unique_local_target(tmp_root, src_name)
                self.backend.export_path_to_local(fs_path, local_target)
                urls.append(QUrl.fromLocalFile(str(local_target)))
        except Exception as exc:
            shutil.rmtree(tmp_root, ignore_errors=True)
            QMessageBox.critical(self, "Drag failed", str(exc))
            return []

        self._drag_export_dirs.append(tmp_root)
        self.statusBar().showMessage("Prepared files for drag out")
        return urls

    def _selected_fs_path(self) -> str | None:
        items = self._selected_items()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)

    def _show_tree_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return

        fs_path = item.data(0, Qt.UserRole)
        is_dir = bool(item.data(0, Qt.UserRole + 1))
        item_name = item.text(0)
        
        self.tree.setCurrentItem(item)

        menu = QMenu(self)
        
        if is_dir:
            # ディレクトリ用メニュー
            if HAS_TWENTYONE_SUPPORT:
                act_create_21 = menu.addAction("Create TwentyOne File (21 chars)")
                menu.addSeparator()
            act_create = menu.addAction("Create File...")
            
            chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
            
            if HAS_TWENTYONE_SUPPORT and chosen == act_create_21:
                self._create_twentyone_file(fs_path)
            elif chosen == act_create:
                self._create_file(fs_path)
        else:
            # ファイル用メニュー
            act_view = menu.addAction("View File")
            act_edit = menu.addAction("Edit File (text only)")
            
            if HAS_TWENTYONE_SUPPORT:
                menu.addSeparator()
                act_edit_21 = menu.addAction("Edit TwentyOne Name")
            
            chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
            
            if chosen == act_view:
                self._view_file(fs_path, item_name)
            elif chosen == act_edit:
                self._edit_file(fs_path, item_name)
            elif HAS_TWENTYONE_SUPPORT and chosen == act_edit_21:
                self._edit_twentyone_name(fs_path, item_name)

    def _on_tree_selection_changed(self) -> None:
        """ツリーの選択が変更された。"""
        if self._syncing_selection:
            return
        selected = self.tree.selectedItems()
        if not selected:
            return
        
        item = selected[0]
        path = self._get_tree_item_path(item)
        self._syncing_selection = True
        try:
            self.column_view.navigate_to(path)
        finally:
            self._syncing_selection = False
    
    def _get_tree_item_path(self, item: QTreeWidgetItem) -> str:
        """ツリーアイテムのフルパスを取得（UserRole から直接取得）。"""
        path = item.data(0, Qt.UserRole)
        if path:
            return str(path)
        return "/"

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        is_dir = bool(item.data(0, Qt.UserRole + 1))
        if is_dir:
            return

        fs_path = item.data(0, Qt.UserRole)
        self._view_file(fs_path, item.text(0))

    @staticmethod
    def _looks_reasonable_text(text: str) -> bool:
        if not text:
            return True

        bad = 0
        for ch in text:
            if ch in "\n\r\t":
                continue
            code = ord(ch)
            if code < 0x20 or (0x7F <= code <= 0x9F):
                bad += 1

        return (bad / max(1, len(text))) < 0.02

    @staticmethod
    def _decode_text_preview(data: bytes) -> tuple[str, str] | None:
        if not data:
            return "", "utf-8"

        bom_encodings = (
            (b"\x00\x00\xFE\xFF", "utf-32-be"),
            (b"\xFF\xFE\x00\x00", "utf-32-le"),
            (b"\xEF\xBB\xBF", "utf-8-sig"),
            (b"\xFE\xFF", "utf-16-be"),
            (b"\xFF\xFE", "utf-16-le"),
        )
        for bom, enc in bom_encodings:
            if data.startswith(bom):
                try:
                    return data.decode(enc), enc
                except UnicodeDecodeError:
                    break

        if len(data) >= 8:
            even = data[0::2]
            odd = data[1::2]
            if even and odd:
                zero_even = even.count(0) / len(even)
                zero_odd = odd.count(0) / len(odd)
                if zero_even > 0.3 and zero_odd < 0.05:
                    try:
                        return data.decode("utf-16-be"), "utf-16-be"
                    except UnicodeDecodeError:
                        pass
                if zero_odd > 0.3 and zero_even < 0.05:
                    try:
                        return data.decode("utf-16-le"), "utf-16-le"
                    except UnicodeDecodeError:
                        pass

        try:
            cn = import_module("charset_normalizer")
            best = cn.from_bytes(data).best()
            if best is not None and best.encoding:
                text = str(best)
                if text and MainWindow._looks_reasonable_text(text):
                    return text, best.encoding
        except Exception:
            pass

        if b"\x00" in data:
            return None

        for enc in ("utf-8", "cp932", "shift_jis", "euc_jp", "iso2022_jp"):
            try:
                text = data.decode(enc)
                if MainWindow._looks_reasonable_text(text):
                    return text, enc
            except UnicodeDecodeError:
                continue
        return None

    def _view_file(self, fs_path: str, name: str) -> None:
        if self.backend.fs is None:
            return

        try:
            data = self.backend.read_file_bytes(fs_path)
        except Exception as exc:
            QMessageBox.critical(self, "View File failed", str(exc))
            return

        max_preview_bytes = 512 * 1024
        truncated = len(data) > max_preview_bytes
        data_preview = data[:max_preview_bytes]

        decoded = self._decode_text_preview(data_preview)
        if decoded is None:
            QMessageBox.information(
                self,
                "View File",
                "This file does not look like a text file, or encoding is unsupported.",
            )
            return

        text, enc = decoded
        if truncated:
            text += "\n\n--- Preview truncated (first 512KB only) ---"

        dlg = QDialog(self)
        dlg.setWindowTitle(f"View File - {name}")
        dlg.resize(900, 620)

        layout = QVBoxLayout(dlg)
        info = QLabel(f"Path: {fs_path}")

        enc_row = QHBoxLayout()
        enc_row.addWidget(QLabel("Encoding:"))
        enc_combo = QComboBox(dlg)
        enc_combo.addItems(
            [
                "shift_jis",
                "cp932",
                "utf-8",
                "utf-8-sig",
                "euc_jp",
                "iso2022_jp",
                "utf-16-le",
                "utf-16-be",
                "auto",
            ]
        )
        enc_combo.setCurrentText("shift_jis")
        enc_status = QLabel(f"Auto detected: {enc}")
        enc_row.addWidget(enc_combo)
        enc_row.addStretch(1)
        enc_row.addWidget(enc_status)

        editor = QPlainTextEdit(dlg)
        editor.setReadOnly(True)

        def render_text(selected_encoding: str) -> None:
            if selected_encoding == "auto":
                auto_decoded = self._decode_text_preview(data_preview)
                if auto_decoded is None:
                    editor.setPlainText("(Unable to decode text with auto detection)")
                    enc_status.setText("Auto detected: unknown")
                    return
                current_text, current_enc = auto_decoded
                enc_status.setText(f"Auto detected: {current_enc}")
            else:
                try:
                    current_text = data_preview.decode(selected_encoding)
                    enc_status.setText(f"Manual: {selected_encoding}")
                except UnicodeDecodeError:
                    current_text = data_preview.decode(selected_encoding, errors="replace")
                    enc_status.setText(f"Manual: {selected_encoding} (with replacement)")

            if truncated:
                current_text += "\n\n--- Preview truncated (first 512KB only) ---"
            editor.setPlainText(current_text)

        enc_combo.currentTextChanged.connect(render_text)
        render_text(enc_combo.currentText())

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=dlg)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)

        layout.addWidget(info)
        layout.addLayout(enc_row)
        layout.addWidget(editor)
        layout.addWidget(buttons)

        dlg.exec()

    def _edit_file(self, fs_path: str, name: str) -> None:
        if self.backend.fs is None:
            return

        try:
            data = self.backend.read_file_bytes(fs_path)
        except Exception as exc:
            QMessageBox.critical(self, "Edit File failed", str(exc))
            return

        if self._decode_text_preview(data[: min(len(data), 256 * 1024)]) is None:
            QMessageBox.information(
                self,
                "Edit File",
                "This file does not look like a text file, or encoding is unsupported.",
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit File - {name}")
        dlg.resize(960, 680)

        layout = QVBoxLayout(dlg)
        info = QLabel(f"Path: {fs_path}")

        enc_row = QHBoxLayout()
        enc_row.addWidget(QLabel("Encoding:"))
        enc_combo = QComboBox(dlg)
        enc_combo.addItems(
            [
                "shift_jis",
                "cp932",
                "utf-8",
                "utf-8-sig",
                "euc_jp",
                "iso2022_jp",
                "utf-16-le",
                "utf-16-be",
                "auto",
            ]
        )
        enc_combo.setCurrentText("shift_jis")
        enc_status = QLabel("")
        enc_row.addWidget(enc_combo)
        enc_row.addStretch(1)
        enc_row.addWidget(enc_status)

        editor = QPlainTextEdit(dlg)
        editor.setReadOnly(False)
        save_status = QLabel("")

        def normalize_to_x68k_text_newline(text: str) -> str:
            unified = text.replace("\r\n", "\n").replace("\r", "\n")
            return unified.replace("\n", "\r\n")

        buttons = QDialogButtonBox(parent=dlg)
        btn_save = buttons.addButton(QDialogButtonBox.Save)
        btn_close = buttons.addButton(QDialogButtonBox.Close)
        btn_close.clicked.connect(dlg.reject)

        def update_save_state() -> None:
            selected = enc_combo.currentText()
            if selected == "auto":
                btn_save.setEnabled(False)
                return

            try:
                encoded = normalize_to_x68k_text_newline(editor.toPlainText()).encode(selected)
            except UnicodeEncodeError:
                btn_save.setEnabled(False)
                return

            btn_save.setEnabled(encoded != data)

        def render_text(selected_encoding: str) -> None:
            if selected_encoding == "auto":
                auto_decoded = self._decode_text_preview(data)
                if auto_decoded is None:
                    editor.setPlainText("(Unable to decode text with auto detection)")
                    enc_status.setText("Auto detected: unknown")
                    save_status.setText("")
                    dlg.setWindowTitle(f"Edit File - {name}")
                    update_save_state()
                    return
                current_text, current_enc = auto_decoded
                enc_status.setText(f"Auto detected: {current_enc}")
            else:
                try:
                    current_text = data.decode(selected_encoding)
                    enc_status.setText(f"Manual: {selected_encoding}")
                except UnicodeDecodeError:
                    current_text = data.decode(selected_encoding, errors="replace")
                    enc_status.setText(f"Manual: {selected_encoding} (with replacement)")

            editor.setPlainText(current_text)
            save_status.setText("")
            dlg.setWindowTitle(f"Edit File - {name}")
            update_save_state()

        enc_combo.currentTextChanged.connect(render_text)
        render_text(enc_combo.currentText())

        def save_current_text() -> None:
            selected = enc_combo.currentText()
            if selected == "auto":
                QMessageBox.information(dlg, "Edit File", "Select an explicit encoding before save.")
                return

            text = normalize_to_x68k_text_newline(editor.toPlainText())
            try:
                encoded = text.encode(selected)
            except UnicodeEncodeError as exc:
                QMessageBox.critical(dlg, "Save failed", f"Encoding error ({selected}): {exc}")
                return

            try:
                self.backend.write_file_bytes(fs_path, encoded)
            except Exception as exc:
                QMessageBox.critical(dlg, "Save failed", str(exc))
                return

            self.refresh_tree()
            self._set_info_label()
            self.statusBar().showMessage("File saved")
            nonlocal data
            data = encoded
            enc_status.setText(f"Saved as: {selected}")
            save_status.setText("Saved")
            dlg.setWindowTitle(f"Edit File - {name} (saved)")
            update_save_state()

        btn_save.clicked.connect(save_current_text)
        editor.textChanged.connect(lambda: save_status.setText("Unsaved changes"))
        editor.textChanged.connect(lambda: dlg.setWindowTitle(f"Edit File - {name}"))
        editor.textChanged.connect(update_save_state)
        enc_combo.currentTextChanged.connect(lambda _value: update_save_state())
        update_save_state()

        layout.addWidget(info)
        layout.addLayout(enc_row)
        layout.addWidget(editor)
        layout.addWidget(save_status)
        layout.addWidget(buttons)

        dlg.exec()

    def _create_file(self, parent_path: str) -> None:
        """Create a new file in the specified directory."""
        if self.backend.fs is None:
            return

        filename = self._prompt_sfn_filename(
            title="Create File",
            default_text="newfile.txt",
        )
        if filename is None:
            return

        # Create empty file
        try:
            self.backend.create_empty_file(_join(parent_path, filename))
            self.refresh_tree()
            self._set_info_label()
            QMessageBox.information(self, "Create File", f"File created: {filename}")
        except Exception as exc:
            QMessageBox.critical(self, "Create File failed", str(exc))

    def _create_twentyone_file(self, parent_path: str) -> None:
        """Create a new TwentyOne file (21-character name) in the specified directory."""
        if self.backend.fs is None:
            return
        
        if not HAS_TWENTYONE_SUPPORT:
            QMessageBox.warning(self, "TwentyOne Support", "TwentyOne support is not available")
            return
        
        # Show TwentyOne file creation dialog
        dlg = TwentyOneFileDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        
        filename = dlg.get_filename()
        
        # Show content editor dialog
        content_dlg = TwentyOneFileContentDialog(self)
        if content_dlg.exec() != QDialog.Accepted:
            return
        
        content = content_dlg.get_content()
        if isinstance(content, str):
            content_bytes = content.encode('utf-8')
        else:
            content_bytes = bytes(content)
        
        # Write file to image
        try:
            self.backend.write_file_twentyone(parent_path, filename, content_bytes)
            self.refresh_tree()
            self._set_info_label()
            QMessageBox.information(self, "Create TwentyOne File", f"File created: {filename}")
        except Exception as exc:
            QMessageBox.critical(self, "Create TwentyOne File failed", str(exc))

    def _edit_twentyone_name(self, fs_path: str, current_name: str) -> None:
        """Edit TwentyOne filename for an existing file."""
        if self.backend.fs is None:
            return
        
        if not HAS_TWENTYONE_SUPPORT:
            QMessageBox.warning(self, "TwentyOne Support", "TwentyOne support is not available")
            return
        
        # Show info about current name
        info_text = f"Current name: {current_name}\n\nNote: TwentyOne name editing requires FAT entry modification.\nThis is currently a view-only feature."
        QMessageBox.information(self, "TwentyOne Name Info", info_text)

    def _selected_target_dir(self) -> str:
        path = self._selected_fs_path()
        if path is None:
            return "/"
        is_dir = bool(self._selected_items()[0].data(0, Qt.UserRole + 1))
        return path if is_dir else _parent(path)

    @staticmethod
    def _validate_sfn_filename(name: str) -> str | None:
        """Validate strict FAT 8.3 filename. Returns error text when invalid."""
        n = name.strip()
        if not n:
            return "ファイル名を入力してください。"

        if "/" in n or "\\" in n:
            return "'/' と '\\' は使用できません。"

        if n in (".", ".."):
            return "'.' と '..' は使用できません。"

        parts = n.split(".")
        if len(parts) > 2:
            return "New File は 8.3 形式のみ対応です（ピリオドは1つまで）。"

        base = parts[0]
        ext = parts[1] if len(parts) == 2 else ""

        if len(base) == 0:
            return "ファイル名本体（拡張子の前）は1文字以上必要です。"

        if len(base) > 8 or len(ext) > 3:
            return "New File は 8.3 形式のみ対応です。21文字名は右クリックの Create TwentyOne File を使用してください。"

        forbidden = set(' \":;,[]<>|?*')
        for ch in n:
            if ord(ch) < 0x20 or ch in forbidden:
                return "使用できない文字が含まれています。"

        return None

    def _prompt_sfn_filename(self, title: str, default_text: str = "") -> str | None:
        """Prompt filename with strict 8.3 validation and keep dialog open while invalid."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(560)

        layout = QVBoxLayout(dlg)
        notice = QLabel(
            "New File は FAT の 8.3 形式専用です。\n"
            "21文字ファイル名（TwentyOne）は右クリックの Create TwentyOne File を使用してください。"
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        row = QHBoxLayout()
        row.addWidget(QLabel("File name:"))
        edit = QLineEdit(dlg)
        edit.setText(default_text)
        row.addWidget(edit)
        layout.addLayout(row)

        hint = QLabel("")
        hint.setStyleSheet("color: #b00020;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        buttons.rejected.connect(dlg.reject)

        def refresh_state() -> None:
            err = self._validate_sfn_filename(edit.text())
            if err:
                hint.setText(err)
                ok_btn.setEnabled(False)
            else:
                hint.setText("")
                ok_btn.setEnabled(True)

        def accept_if_valid() -> None:
            err = self._validate_sfn_filename(edit.text())
            if err:
                hint.setText(err)
                return
            dlg.accept()

        edit.textChanged.connect(lambda _value: refresh_state())
        buttons.accepted.connect(accept_if_valid)
        layout.addWidget(buttons)

        refresh_state()
        edit.setFocus()
        edit.selectAll()

        if dlg.exec() != QDialog.Accepted:
            return None
        return edit.text().strip()

    def _fill_offset_combo(self) -> None:
        self._updating_offset_combo = True
        self.offset_combo.clear()

        for off in self.backend.offset_candidates:
            self.offset_combo.addItem(self.backend.get_offset_label(off), off)

        idx = self.offset_combo.findData(self.backend.current_offset)
        if idx >= 0:
            self.offset_combo.setCurrentIndex(idx)

        self._updating_offset_combo = False

    @staticmethod
    def _is_image_file(path: Path) -> bool:
        return path.suffix.lower() in (".hdf", ".hds", ".xdf")

    def _mount_image_path(self, image_path: str) -> None:
        backup_on_open = self.chk_backup_on_open.isChecked()

        def work() -> list[dict[str, Any]]:
            self.backend.mount(image_path)
            if backup_on_open:
                self.backend.create_backup_now()
            return self._build_tree_snapshot("/")

        def on_success(snapshot: Any) -> None:
            self._push_mount_history(image_path)
            self._fill_offset_combo()
            self._set_info_label()
            self.tree.clear()
            self._apply_tree_snapshot(snapshot, self.tree.invisibleRootItem())
            # カラムビューもセットアップ
            self.column_view.set_backend(self.backend)
            self._update_mount_controls()
            self.statusBar().showMessage("Image mounted")

        self._run_busy_task("Opening image...", work, on_success, "Open failed")

    def _build_tree_snapshot(self, dir_path: str = "/") -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for e in self.backend.list_dir(dir_path):
            node: dict[str, Any] = {
                "name": e.name,
                "path": e.path,
                "is_dir": e.is_dir,
                "size": e.size,
                "modified": e.modified,
                "children": [],
            }
            if e.is_dir:
                node["children"] = self._build_tree_snapshot(e.path)
            out.append(node)
        return out

    def _apply_tree_snapshot(self, snapshot: list[dict[str, Any]], parent_item) -> None:
        for n in snapshot:
            item = QTreeWidgetItem(
                [
                    str(n["name"]),
                    "DIR" if bool(n["is_dir"]) else "FILE",
                    "" if bool(n["is_dir"]) else str(n["size"]),
                    str(n["modified"]),
                ]
            )
            item.setData(0, Qt.UserRole, n["path"])
            item.setData(0, Qt.UserRole + 1, bool(n["is_dir"]))
            parent_item.addChild(item)
            if bool(n["is_dir"]):
                self._apply_tree_snapshot(n["children"], item)

    def _save_tree_expanded_state(self) -> set[str]:
        """展開済みディレクトリのパスセットを返す。"""
        expanded: set[str] = set()
        def collect(item) -> None:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.isExpanded():
                    path = child.data(0, Qt.UserRole)
                    if path:
                        expanded.add(str(path))
                collect(child)
        collect(self.tree.invisibleRootItem())
        return expanded

    def _save_tree_selection(self) -> str | None:
        """選択中アイテムのパスを返す。"""
        items = self.tree.selectedItems()
        if items:
            return items[0].data(0, Qt.UserRole)
        return None

    def _restore_tree_state(self, expanded: set[str], selected_path: str | None) -> None:
        """展開状態と選択を復元する。"""
        def restore(item) -> None:
            for i in range(item.childCount()):
                child = item.child(i)
                path = child.data(0, Qt.UserRole)
                if path and str(path) in expanded:
                    child.setExpanded(True)
                if selected_path and path and str(path) == selected_path:
                    self.tree.setCurrentItem(child)
                restore(child)
        restore(self.tree.invisibleRootItem())

    def open_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Mount image",
            "",
            "X68000 Images (*.hdf *.HDF *.hds *.HDS *.xdf *.XDF);;All Files (*)",
        )
        if not filename:
            return

        self._mount_image_path(filename)
    
    def _on_column_view_path_changed(self, path: str) -> None:
        """カラムビューでパスが変更された。"""
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self._select_tree_item_by_path(path)
        finally:
            self._syncing_selection = False
    
    def _select_tree_item_by_path(self, path: str) -> None:
        """指定パスに対応するツリーアイテムを選択。"""
        if path == "/":
            # ルートの場合は何も変更しない（選択を維持）
            self._set_info_label()
            return
        
        # パスを分割
        parts = path.strip("/").split("/")
        current_item = self.tree.invisibleRootItem()
        
        # 階層を辿る
        for part in parts:
            found = False
            for i in range(current_item.childCount()):
                child = current_item.child(i)
                child_path = child.data(0, Qt.UserRole)
                if child_path and PurePosixPath(str(child_path)).name == part:
                    current_item = child
                    found = True
                    break
            
            if not found:
                break
        
        self.tree.setCurrentItem(current_item)
        self._set_info_label()

    def unmount_image(self) -> None:
        if not self._is_mounted():
            return

        self.backend.unmount()
        self.tree.clear()
        self.column_view.set_backend(None)
        self._fill_offset_combo()
        self._set_info_label()
        self._update_mount_controls()
        self.statusBar().showMessage("Image unmounted")

    def on_offset_changed(self, index: int) -> None:
        if self._updating_offset_combo or index < 0:
            return
        off = int(self.offset_combo.itemData(index))

        if off == self.backend.current_offset:
            return

        def work() -> list[dict[str, Any]]:
            self.backend.remount_at_offset(off)
            return self._build_tree_snapshot("/")

        def on_success(snapshot: Any) -> None:
            self.tree.clear()
            self._apply_tree_snapshot(snapshot, self.tree.invisibleRootItem())
            # カラムビューをリセット
            self.column_view.set_backend(self.backend)
            self._set_info_label()
            self.statusBar().showMessage(f"Remounted: {self.backend.get_offset_label(off)}")

        self._run_busy_task("Switching partition...", work, on_success, "Remount failed")

    def backup_now(self) -> None:
        if self.backend.image_path is None:
            return

        def work() -> str:
            return str(self.backend.create_backup_now())

        def on_success(backup_path: Any) -> None:
            self._set_info_label()
            self.statusBar().showMessage(f"Backup created: {backup_path}")

        self._run_busy_task("Creating backup...", work, on_success, "Backup failed")

    def refresh_tree(self) -> None:
        if self.backend.fs is None:
            return

        # 展開状態と選択を保存
        expanded = self._save_tree_expanded_state()
        selected_path = self._save_tree_selection()

        def work() -> list[dict[str, Any]]:
            return self._build_tree_snapshot("/")

        def on_success(snapshot: Any) -> None:
            self.tree.clear()
            self._apply_tree_snapshot(snapshot, self.tree.invisibleRootItem())
            # 展開状態と選択を復元
            self._restore_tree_state(expanded, selected_path)
            self._set_info_label()
            # カラムビューも更新
            self.column_view.refresh()
            self.statusBar().showMessage("Refreshed")

        self._run_busy_task("Refreshing file tree...", work, on_success, "Refresh failed")

    def _populate_dir(self, dir_path: str, parent_item) -> None:
        entries = self.backend.list_dir(dir_path)
        for e in entries:
            item = QTreeWidgetItem(
                [
                    e.name,
                    "DIR" if e.is_dir else "FILE",
                    "" if e.is_dir else str(e.size),
                    e.modified,
                ]
            )
            item.setData(0, Qt.UserRole, e.path)
            item.setData(0, Qt.UserRole + 1, e.is_dir)
            parent_item.addChild(item)

            if e.is_dir:
                self._populate_dir(e.path, item)

    def on_local_paths_dropped(self, local_paths: list[str], target_path: str, target_is_dir: bool) -> None:
        if len(local_paths) == 1:
            dropped = Path(local_paths[0])
            if dropped.is_file() and self._is_image_file(dropped):
                self._mount_image_path(str(dropped))
                return

        if self.backend.fs is None:
            return

        def work() -> list[dict[str, Any]]:
            p_objs = [Path(p) for p in local_paths]
            if not target_is_dir and len(p_objs) == 1 and p_objs[0].is_file():
                self.backend.replace_file(target_path, p_objs[0])
            else:
                dest_dir = target_path if target_is_dir else _parent(target_path)
                for local in p_objs:
                    self.backend.import_local_path(local, dest_dir)
            return self._build_tree_snapshot("/")

        def on_success(snapshot: Any) -> None:
            self.tree.clear()
            self._apply_tree_snapshot(snapshot, self.tree.invisibleRootItem())
            self._set_info_label()
            self.statusBar().showMessage("Import complete")

        self._run_busy_task("Importing files...", work, on_success, "Drop failed")

    def _is_column_view_active(self) -> bool:
        """Column View タブが表示中か。"""
        return self.view_tabs.currentWidget() is self.column_view

    def create_new_file(self) -> None:
        if self.backend.fs is None:
            return

        if self._is_column_view_active():
            target_dir = self.column_view.get_target_dir()
        else:
            target_dir = self._selected_target_dir()

        name = self._prompt_sfn_filename(title="New File")
        if name is None:
            return

        try:
            self.backend.create_empty_file(_join(target_dir, name))
            self.refresh_tree()
            self.statusBar().showMessage("File created")
        except Exception as exc:
            QMessageBox.critical(self, "Create file failed", str(exc))

    def create_new_dir(self) -> None:
        if self.backend.fs is None:
            return

        if self._is_column_view_active():
            target_dir = self.column_view.get_target_dir()
        else:
            target_dir = self._selected_target_dir()

        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip():
            return

        try:
            sfn_name = _to_fat_sfn(name.strip())
            self.backend.create_dir(_join(target_dir, sfn_name))
            self.refresh_tree()
            msg = f"Folder created as: {sfn_name}" if sfn_name != name.strip() else "Folder created"
            self.statusBar().showMessage(msg)
        except Exception as exc:
            QMessageBox.critical(self, "Create folder failed", str(exc))

    def delete_selected(self) -> None:
        if self.backend.fs is None:
            return

        if self._is_column_view_active():
            paths = self.column_view.get_selected_paths()
            names = ", ".join(p.split("/")[-1] for p in paths)
        else:
            items = self._selected_items()
            if not items:
                return
            paths = [i.data(0, Qt.UserRole) for i in items]
            names = ", ".join(i.text(0) for i in items)

        if not paths:
            return

        answer = QMessageBox.question(
            self,
            "Confirm delete",
            f"Delete selected entries?\n{names}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            self.backend.delete_paths(paths)
            self.refresh_tree()
            self.statusBar().showMessage("Delete complete")
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))

    def extract_selected_file(self) -> None:
        if self.backend.fs is None:
            return

        items = self._selected_items()
        if len(items) != 1:
            QMessageBox.information(self, "Extract", "Select one file to extract.")
            return

        item = items[0]
        is_dir = bool(item.data(0, Qt.UserRole + 1))
        if is_dir:
            QMessageBox.information(self, "Extract", "Folder extraction is not implemented yet.")
            return

        fs_path = item.data(0, Qt.UserRole)
        suggested = item.text(0)

        save_path, _ = QFileDialog.getSaveFileName(self, "Extract file", suggested, "All Files (*)")
        if not save_path:
            return

        def work() -> None:
            data = self.backend.read_file_bytes(fs_path)
            Path(save_path).write_bytes(data)
            return None

        def on_success(_: Any) -> None:
            self.statusBar().showMessage("Extract complete")

        self._run_busy_task("Extracting file...", work, on_success, "Extract failed")

    def closeEvent(self, event) -> None:
        self.backend.close()
        for tmp in self._drag_export_dirs:
            shutil.rmtree(tmp, ignore_errors=True)
        super().closeEvent(event)


def run() -> int:
    app = QApplication(sys.argv)
    # Apply Fusion style for better selection highlighting
    from PySide6.QtWidgets import QStyleFactory
    app.setStyle(QStyleFactory.create('Fusion'))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
