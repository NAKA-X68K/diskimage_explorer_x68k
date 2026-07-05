"""複数 QListView を水平配置したカラムビュー実装。

X68000 ディスク イメージ ブラウザ用に、シンプルで確実なカラムビューを提供。
各列が階層レベルを表し、選択変更で次の列が更新される。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QMimeData, QUrl, Signal, QAbstractListModel, QModelIndex, QItemSelectionModel
from PySide6.QtGui import QDrag, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QListView, QAbstractItemView, QMenu, QApplication, QStyle,
    QVBoxLayout, QLabel, QPushButton
)


class DiskFileInfo:
    """ディスク ファイル情報。"""
    
    def __init__(self, name: str, is_dir: bool, size: int, modified: str, path: str = ""):
        self.name = name
        self.is_dir = is_dir
        self.size = size
        self.modified = modified  # ISO format string: "2024-01-15 10:30:00"
        self.path = path
    
    def size_str(self) -> str:
        """サイズを人間が読みやすい文字列に変換。"""
        if self.is_dir:
            return "<DIR>"
        
        size = float(self.size)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.0f}{unit}"
            size /= 1024
        
        return f"{size:.0f}TB"
    
    def date_str(self) -> str:
        """日付を文字列に変換。"""
        # modified は既に ISO format string
        if not self.modified:
            return ""
        # "2024-01-15 10:30:00" -> "2024-01-15 10:30"
        return self.modified[:16]


class ColumnViewModel(QAbstractListModel):
    """カラムビュー用データモデル。"""
    
    def __init__(self, backend, path: str = "/"):
        super().__init__()
        self.backend = backend
        self.path = path
        self.items: list[DiskFileInfo] = []
        app = QApplication.instance()
        self._dir_icon = app.style().standardIcon(QStyle.SP_DirIcon) if app else None
        self._item_font = QFont(app.font()) if app else QFont()
        self._load_items()
    
    def _load_items(self) -> None:
        """パスからアイテムを読み込み。"""
        self.beginResetModel()
        self.items = []
        
        try:
            entries = self.backend.list_dir(self.path)
            for entry in entries:
                self.items.append(DiskFileInfo(
                    name=entry.name,
                    is_dir=entry.is_dir,
                    size=entry.size,
                    modified=entry.modified,
                    path=entry.path,
                ))
        except Exception:
            pass
        
        self.endResetModel()
    
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """アイテム数を返す。"""
        if parent.isValid():
            return 0
        return len(self.items)
    
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        """データを返す。"""
        if not index.isValid() or index.row() >= len(self.items):
            return None
        
        item = self.items[index.row()]
        
        if role == Qt.DisplayRole:
            # 表示テキスト：フォルダなら末尾に「/」をつける
            if item.is_dir:
                return f"{item.name}/"
            return item.name
        
        elif role == Qt.UserRole:
            # カスタム情報
            return {
                'name': item.name,
                'is_dir': item.is_dir,
                'size': item.size_str(),
                'date': item.date_str(),
                'path': item.path,
            }

        elif role == Qt.DecorationRole:
            if item.is_dir:
                return self._dir_icon

        elif role == Qt.FontRole:
            # ディレクトリ/ファイルで同じフォントサイズを使う
            return self._item_font
        
        elif role == Qt.ForegroundRole:
            # フォルダは青色
            if item.is_dir:
                return QColor(0, 0, 255)
        
        return None
    
    def get_item_path(self, index: QModelIndex) -> Optional[str]:
        """指定インデックスのパスを取得。"""
        if not index.isValid():
            return None
        return self.items[index.row()].path
    
    def get_item_is_dir(self, index: QModelIndex) -> bool:
        """指定インデックスがディレクトリかどうか。"""
        if not index.isValid():
            return False
        return self.items[index.row()].is_dir


class ColumnListView(QListView):
    """ドラッグ&ドロップ対応のカラム用リストビュー。"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.backend = None
        self.parent_view = None
        self.setIconSize(QSize(16, 16))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setUniformItemSizes(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setMinimumWidth(200)
        self._set_inactive_style()
    
    def _set_active_style(self) -> None:
        """アクティブカラムのスタイル。"""
        self.setStyleSheet(
            "QListView { border: 2px solid #0078d4; background-color: #f5f9ff; }"
        )
    
    def _set_inactive_style(self) -> None:
        """非アクティブカラムのスタイル。"""
        self.setStyleSheet(
            "QListView { border: 1px solid #cccccc; background-color: white; }"
        )
    
    def mousePressEvent(self, event) -> None:
        """空白領域クリック時に深いカラムを閉じる。"""
        index = self.indexAt(event.position().toPoint())
        if not index.isValid():
            # 空白領域クリック → このカラム以降を閉じる
            self.clearSelection()
            if self.parent_view:
                self.parent_view.collapse_after_depth(self)
        super().mousePressEvent(event)
    
    def dragEnterEvent(self, event) -> None:
        """ドラッグ開始時。"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
    
    def dragMoveEvent(self, event) -> None:
        """ドラッグ移動時。"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
    
    def dropEvent(self, event) -> None:
        """ドロップ時。"""
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return
        
        # 親ウィジェット（CustomColumnView）に処理を委譲
        if self.parent_view and hasattr(self.parent_view, 'on_drop_files'):
            local_paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if local_paths:
                target_path = self.model().path if self.model() else "/"
                target_is_dir = True

                idx = self.indexAt(event.position().toPoint())
                if idx.isValid() and self.model():
                    data = self.model().data(idx, Qt.UserRole)
                    if isinstance(data, dict) and data.get('path'):
                        target_path = data['path']
                        target_is_dir = bool(data.get('is_dir', False))

                self.parent_view.on_drop_files(local_paths, target_path, target_is_dir)
                event.acceptProposedAction()
                return

        event.ignore()
    
    def startDrag(self, supported_actions) -> None:
        """ドラッグ開始。"""
        selection_model = self.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            return
        
        model = self.model()
        if not model or not self.backend:
            return
        
        urls = []
        for index in selection_model.selectedIndexes():
            if index.isValid():
                data = model.data(index, Qt.UserRole)
                if data:
                    try:
                        import tempfile
                        temp_dir = Path(tempfile.gettempdir()) / "xdf_drag"
                        temp_dir.mkdir(exist_ok=True)
                        
                        local_path = temp_dir / data['name']
                        self.backend.export_path_to_local(data['path'], local_path)
                        urls.append(QUrl.fromLocalFile(str(local_path)))
                    except Exception:
                        pass
        
        if urls:
            mime = QMimeData()
            mime.setUrls(urls)
            
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.CopyAction)
    
    def contextMenuEvent(self, event) -> None:
        """コンテキストメニュー表示。"""
        selection_model = self.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            return
        
        model = self.model()
        if not model or not self.parent_view:
            return
        
        # 選択アイテムがファイルかどうか判定
        indices = selection_model.selectedIndexes()
        is_single_file = False
        if len(indices) == 1 and indices[0].isValid():
            index = indices[0]
            if index.row() < len(model.items):
                is_single_file = not model.items[index.row()].is_dir
        
        # メニュー作成
        menu = QMenu(self)
        
        # ファイル操作（ファイルのみ）
        if is_single_file:
            view_action = menu.addAction("View File")
            view_action.triggered.connect(
                lambda: self.parent_view.on_view_file(self)
            )
            edit_action = menu.addAction("Edit File (text only)")
            edit_action.triggered.connect(
                lambda: self.parent_view.on_edit_file(self)
            )
        
        if not menu.isEmpty():
            menu.exec(event.globalPos())


class CustomColumnView(QWidget):
    """複数 QListView を水平配置したカラムビュー。"""
    
    pathChanged = Signal(str)
    filesDropped = Signal(list, str, bool)  # local_file_paths, target_path, target_is_dir
    fileViewRequested = Signal(str, str)  # fs_path, name
    fileEditRequested = Signal(str, str)  # fs_path, name
    
    def __init__(self, backend=None, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.current_path = "/"
        self.models: dict[int, ColumnViewModel] = {}  # depth -> model
        self.views: list[ColumnListView] = []  # depth 順のビューリスト
        
        # UI 設定
        self.root_layout = QVBoxLayout()
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)
        self.setLayout(self.root_layout)

        # パンくず（1行）
        self.breadcrumb_row = QWidget(self)
        self.breadcrumb_row.setStyleSheet(
            "QWidget { border-bottom: 1px solid #d0d0d0; background-color: #f7f7f7; }"
        )
        self.breadcrumb_row.setMinimumHeight(34)
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_row)
        self.breadcrumb_layout.setContentsMargins(8, 4, 8, 4)
        self.breadcrumb_layout.setSpacing(6)
        self.root_layout.addWidget(self.breadcrumb_row)

        # カラム本体
        self.columns_widget = QWidget(self)
        self.layout = QHBoxLayout(self.columns_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.root_layout.addWidget(self.columns_widget, 1)

        self._update_breadcrumbs()
        
        if backend:
            self._init_columns()
    
    def _init_columns(self) -> None:
        """初期カラムを作成。"""
        if not self.backend:
            return
        
        # ルートカラムを作成
        self._add_column(0, "/")
        self._update_breadcrumbs()

    def _clear_breadcrumbs(self) -> None:
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _update_breadcrumbs(self) -> None:
        self._clear_breadcrumbs()

        parts = self.current_path.strip("/").split("/") if self.current_path != "/" else []
        crumbs: list[tuple[str, str]] = [("ROOT", "/")]
        if parts:
            cur = ""
            for part in parts:
                cur = f"{cur}/{part}" if cur else f"/{part}"
                crumbs.append((part, cur))

        for idx, (label, target_path) in enumerate(crumbs):
            is_current = idx == len(crumbs) - 1
            btn = QPushButton(label, self.breadcrumb_row)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            if is_current:
                btn.setEnabled(False)
                btn.setStyleSheet("QPushButton { color: #202020; font-weight: 600; border: none; }")
            else:
                btn.setStyleSheet(
                    "QPushButton { color: #005fb8; text-decoration: underline; border: none; }"
                    "QPushButton:hover { color: #004080; }"
                )
                btn.clicked.connect(lambda _checked=False, p=target_path: self.navigate_to(p))
            self.breadcrumb_layout.addWidget(btn)

            if idx < len(crumbs) - 1:
                sep = QLabel(">", self.breadcrumb_row)
                sep.setStyleSheet("QLabel { color: #707070; }")
                self.breadcrumb_layout.addWidget(sep)

        self.breadcrumb_layout.addStretch(1)
    
    def _add_column(self, depth: int, path: str) -> None:
        """指定深さにカラムを追加。"""
        # 既存カラムをクリア
        while len(self.views) > depth:
            view = self.views.pop()
            self.layout.removeWidget(view)
            view.deleteLater()
        
        while len(self.models) > depth:
            self.models.pop(len(self.models) - 1, None)
        
        # 新しいモデルとビューを作成
        model = ColumnViewModel(self.backend, path)
        self.models[depth] = model
        
        view = ColumnListView(self)
        view.backend = self.backend
        view.parent_view = self
        view.setModel(model)
        view.clicked.connect(lambda idx: self._on_column_clicked(depth, idx))
        
        self.views.append(view)
        self.layout.addWidget(view)
    
    def _on_column_clicked(self, depth: int, index) -> None:
        """カラムのアイテムがクリックされた。"""
        model = self.models.get(depth)
        if not model or not index.isValid():
            return
        
        item_path = model.get_item_path(index)
        is_dir = model.get_item_is_dir(index)
        
        if is_dir and item_path:
            # ディレクトリの場合、次のカラムを表示
            self.current_path = item_path
            self._add_column(depth + 1, item_path)
            self.pathChanged.emit(item_path)
        elif item_path:
            # ファイルの場合、depth+1 以降のカラムを削除
            self.current_path = item_path
            while len(self.views) > depth + 1:
                view = self.views.pop()
                self.layout.removeWidget(view)
                view.deleteLater()
            while len(self.models) > depth + 1:
                self.models.pop(max(self.models.keys()))
            self.pathChanged.emit(item_path)

        self._update_breadcrumbs()
        
        # アクティブカラムをハイライト
        if depth < len(self.views):
            self._set_active_view(self.views[depth])
    
    def set_backend(self, backend) -> None:
        """Backend を設定。"""
        self.backend = backend
        
        # すべてのビューをクリア
        for view in self.views:
            self.layout.removeWidget(view)
            view.deleteLater()
        
        self.views = []
        self.models = {}
        self.current_path = "/"
        self._update_breadcrumbs()
        
        if backend:
            self._init_columns()

    def _set_active_view(self, active_view: 'ColumnListView') -> None:
        """アクティブカラムをハイライトし、他を非ハイライトにする。"""
        for view in self.views:
            if view is active_view:
                view._set_active_style()
            else:
                view._set_inactive_style()

    def collapse_after_depth(self, list_view: 'ColumnListView') -> None:
        """指定ビューより深いカラムを閉じ、そのビューをアクティブにする。"""
        if list_view not in self.views:
            return
        depth = self.views.index(list_view)
        while len(self.views) > depth + 1:
            view = self.views.pop()
            self.layout.removeWidget(view)
            view.deleteLater()
        while len(self.models) > depth + 1:
            self.models.pop(max(self.models.keys()))
        model = self.models.get(depth)
        if model:
            self.current_path = model.path
            self.pathChanged.emit(self.current_path)
            self._update_breadcrumbs()
        self._set_active_view(list_view)
    
    def navigate_to(self, path: str) -> None:
        """パスに移動。"""
        if not self.backend:
            return
        
        self.current_path = path
        
        # パスを分割
        parts = path.strip("/").split("/") if path != "/" else []
        
        # 必要なカラムを作成
        for depth in range(len(parts) + 1):
            if depth == 0:
                current_path = "/"
            else:
                current_path = "/" + "/".join(parts[:depth])
            
            if depth not in self.models:
                self._add_column(depth, current_path)

        self._update_breadcrumbs()
        self.pathChanged.emit(path)
    
    def on_drop_files(self, local_paths: list[str], target_path: Optional[str] = None, target_is_dir: bool = True) -> None:
        """ファイルがドロップされた。"""
        if not target_path:
            target_path = self.current_path
        self.filesDropped.emit(local_paths, target_path, target_is_dir)
    
    def refresh(self) -> None:
        """すべてのカラムを再読み込み。"""
        for model in self.models.values():
            model._load_items()

    def select_path(self, path: str) -> bool:
        """指定パスのアイテムを選択してハイライトする。"""
        if not self.backend:
            return False

        if not path or path == "/":
            for view in self.views:
                view.clearSelection()
            if self.views:
                self._set_active_view(self.views[0])
            self.current_path = "/"
            self._update_breadcrumbs()
            return True

        # 親ディレクトリまで展開し、その列で対象パスを選択する
        parent = path.rsplit("/", 1)[0]
        parent_path = parent if parent else "/"
        self.navigate_to(parent_path)

        for depth, model in self.models.items():
            if model.path != parent_path:
                continue

            if depth >= len(self.views):
                return False

            view = self.views[depth]
            for row, item in enumerate(model.items):
                if item.path == path:
                    index = model.index(row, 0)
                    if index.isValid():
                        for v in self.views:
                            v.clearSelection()
                        view.selectionModel().setCurrentIndex(
                            index,
                            QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
                        )
                        view.scrollTo(index)
                        self.current_path = path
                        self._update_breadcrumbs()
                        self._set_active_view(view)
                        return True
            return False

        return False
    
    def on_delete_selected(self, list_view: ColumnListView) -> None:
        """選択アイテムを削除。"""
        if not self.backend or not list_view:
            return
        
        selection_model = list_view.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            return
        
        model = list_view.model()
        
        # 削除対象を収集
        paths_to_delete = []
        for index in selection_model.selectedIndexes():
            if index.isValid() and index.row() < len(model.items):
                item = model.items[index.row()]
                paths_to_delete.append(item.path)
        
        if not paths_to_delete:
            return
        
        # 削除実行
        try:
            self.backend.delete_paths(paths_to_delete)
            # 再読み込み
            self.navigate_to(self.current_path)
        except Exception as e:
            print(f"Delete error: {e}")
    
    def on_show_info(self, list_view: ColumnListView) -> None:
        """選択アイテムの情報を表示。"""
        if not list_view:
            return
        
        selection_model = list_view.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            return
        
        model = list_view.model()
        indices = selection_model.selectedIndexes()
        
        if not indices or not indices[0].isValid():
            return
        
        index = indices[0]
        if index.row() < len(model.items):
            item = model.items[index.row()]
            info = f"""
Item Info:
Name: {item.name}
Path: {item.path}
Type: {"Directory" if item.is_dir else "File"}
Size: {item.size_str()}
Modified: {item.date_str()}
            """.strip()
            print(info)  # For now, just print to console

    def _get_selected_file_item(self, list_view: ColumnListView):
        """選択されたファイルアイテムを返す（ディレクトリは除く）。"""
        if not list_view:
            return None
        selection_model = list_view.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            return None
        model = list_view.model()
        indices = selection_model.selectedIndexes()
        if not indices or not indices[0].isValid():
            return None
        index = indices[0]
        if index.row() < len(model.items):
            item = model.items[index.row()]
            if not item.is_dir:
                return item
        return None

    def on_view_file(self, list_view: ColumnListView) -> None:
        """ファイルを表示。"""
        item = self._get_selected_file_item(list_view)
        if item:
            self.fileViewRequested.emit(item.path, item.name)

    def on_edit_file(self, list_view: ColumnListView) -> None:
        """ファイルを編集。"""
        item = self._get_selected_file_item(list_view)
        if item:
            self.fileEditRequested.emit(item.path, item.name)

    def get_target_dir(self) -> str:
        """New File/New Folder の作成先ディレクトリを返す。

        - ディレクトリが選択されている場合 → そのディレクトリ内
        - ファイルが選択されている場合 → そのファイルと同じ階層（ファイルを含むカラムのディレクトリ）
        - 何も選択されていない場合 → 最後のカラムのディレクトリ
        """
        if not self.views or not self.models:
            return "/"

        # 後ろのカラムから選択を探す
        for depth in range(len(self.views) - 1, -1, -1):
            view = self.views[depth]
            sel = view.selectionModel()
            if sel and sel.hasSelection():
                model = view.model()
                indices = sel.selectedIndexes()
                if indices and indices[0].isValid():
                    idx = indices[0]
                    if idx.row() < len(model.items):
                        item = model.items[idx.row()]
                        if item.is_dir:
                            return item.path  # 選択されたディレクトリ内
                        else:
                            return model.path  # ファイルと同じ階層

        # 何も選択されていない → 最後のカラムのディレクトリ
        last_depth = max(self.models.keys())
        return self.models[last_depth].path

    def get_selected_paths(self) -> list[str]:
        """削除対象のパスを返す（最も深いカラムの選択のみ）。

        ナビゲーションで通過したカラムにも選択が残るため、
        最も深い（後ろの）カラムの選択だけを使う。
        """
        for view in reversed(self.views):
            sel = view.selectionModel()
            if sel and sel.hasSelection():
                model = view.model()
                paths = []
                for idx in sel.selectedIndexes():
                    if idx.isValid() and idx.row() < len(model.items):
                        paths.append(model.items[idx.row()].path)
                if paths:
                    return paths
        return []
