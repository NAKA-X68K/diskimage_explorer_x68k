"""複数 QListView を水平配置したカラムビュー実装。

X68000 ディスク イメージ ブラウザ用に、シンプルで確実なカラムビューを提供。
各列が階層レベルを表し、選択変更で次の列が更新される。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QMimeData, QUrl, Signal, QAbstractListModel, QModelIndex
from PySide6.QtGui import QDrag, QColor
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QListView, QAbstractItemView, QMenu
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
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setMinimumWidth(200)
    
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
                self.parent_view.on_drop_files(local_paths)
    
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
        
        # メニュー作成
        menu = QMenu(self)
        
        # 削除アクション
        delete_action = menu.addAction("削除")
        delete_action.triggered.connect(
            lambda: self.parent_view.on_delete_selected(self)
        )
        
        # 詳細アクション
        info_action = menu.addAction("情報")
        info_action.triggered.connect(
            lambda: self.parent_view.on_show_info(self)
        )
        
        menu.exec(event.globalPos())


class CustomColumnView(QWidget):
    """複数 QListView を水平配置したカラムビュー。"""
    
    pathChanged = Signal(str)
    filesDropped = Signal(str, list)  # path, local_file_paths
    
    def __init__(self, backend=None, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.current_path = "/"
        self.models: dict[int, ColumnViewModel] = {}  # depth -> model
        self.views: list[ColumnListView] = []  # depth 順のビューリスト
        
        # UI 設定
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)
        
        if backend:
            self._init_columns()
    
    def _init_columns(self) -> None:
        """初期カラムを作成。"""
        if not self.backend:
            return
        
        # ルートカラムを作成
        self._add_column(0, "/")
    
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
            # ファイルの場合、親パスで pathChanged
            self.current_path = item_path
            self.pathChanged.emit(item_path)
    
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
        
        if backend:
            self._init_columns()
    
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
        
        self.pathChanged.emit(path)
    
    def on_drop_files(self, local_paths: list[str]) -> None:
        """ファイルがドロップされた。"""
        self.filesDropped.emit(self.current_path, local_paths)
    
    def refresh(self) -> None:
        """すべてのカラムを再読み込み。"""
        for model in self.models.values():
            model._load_items()
    
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
