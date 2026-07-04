"""QColumnView ベースのカラムビュー実装。

X68000 ディスク イメージ ブラウザ用に ドラッグ&ドロップ 対応のカラムビューを提供。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
from datetime import datetime

from PySide6.QtCore import Qt, QMimeData, QUrl, Signal, QAbstractListModel, QModelIndex, QSize
from PySide6.QtGui import QDrag, QColor
from PySide6.QtWidgets import QColumnView, QListView, QAbstractItemView, QFileIconProvider, QStyle


class DiskFileInfo:
    """ディスク ファイル情報。"""
    
    def __init__(self, name: str, is_dir: bool, size: int, modified: datetime):
        self.name = name
        self.is_dir = is_dir
        self.size = size
        self.modified = modified
    
    def size_str(self) -> str:
        """サイズを人間が読みやすい文字列に変換。"""
        if self.is_dir:
            return ""
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.size < 1024:
                return f"{self.size:.0f}{unit}"
            self.size /= 1024
        
        return f"{self.size:.0f}TB"
    
    def date_str(self) -> str:
        """日付を文字列に変換。"""
        return self.modified.strftime("%Y-%m-%d %H:%M")


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
            return item.name
        elif role == Qt.DecorationRole:
            # アイコン（フォルダまたはファイル）
            style = self.backend._app.style() if hasattr(self.backend, '_app') else None
            if item.is_dir:
                return style.standardIcon(QStyle.SP_DirIcon) if style else None
            else:
                return style.standardIcon(QStyle.SP_FileIcon) if style else None
        elif role == Qt.UserRole:
            # ファイル情報用カスタムロール
            return {
                'name': item.name,
                'is_dir': item.is_dir,
                'size': item.size_str(),
                'date': item.date_str(),
            }
        
        return None
    
    def is_dir(self, index: QModelIndex) -> bool:
        """ディレクトリかどうか。"""
        if not index.isValid():
            return False
        return self.items[index.row()].is_dir


class CustomColumnView(QColumnView):
    """ドラッグ&ドロップ 対応のカラムビュー。"""
    
    pathChanged = Signal(str)
    filesDropped = Signal(str, list)  # path, local_file_paths
    
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.current_path = "/"
        self.models: dict[str, ColumnViewModel] = {}
        
        # UI 設定
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        
        # シグナル接続
        self.clicked.connect(self._on_item_clicked)
    
    def set_backend(self, backend) -> None:
        """Backend を設定。"""
        self.backend = backend
        self.clear()
        self.current_path = "/"
        self.models = {}
    
    def navigate_to(self, path: str) -> None:
        """パスに移動。"""
        self.current_path = path
        self._update_columns()
        self.pathChanged.emit(path)
    
    def _update_columns(self) -> None:
        """カラムを更新。"""
        # すべてのモデルをクリア
        self.setModel(None)
        self.models = {}
        
        # ルートモデルを作成
        root_model = ColumnViewModel(self.backend, "/")
        self.models["/"] = root_model
        self.setModel(root_model)
    
    def _on_item_clicked(self, index) -> None:
        """アイテムクリック時。"""
        if not index.isValid():
            return
        
        model = self.model()
        if not isinstance(model, ColumnViewModel):
            return
        
        if model.is_dir(index):
            item_name = model.data(index, Qt.DisplayRole)
            new_path = f"{self.current_path.rstrip('/')}/{item_name}"
            self.navigate_to(new_path)
    
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
        
        local_paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                local_paths.append(url.toLocalFile())
        
        if local_paths:
            self.filesDropped.emit(self.current_path, local_paths)
    
    def startDrag(self, supported_actions) -> None:
        """ドラッグ開始。"""
        # 選択されたアイテムのファイルパスを取得
        selection_model = self.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            return
        
        model = self.model()
        if not isinstance(model, ColumnViewModel):
            return
        
        # 選択されたアイテムのパスを構築
        urls = []
        for index in selection_model.selectedIndexes():
            if index.isValid():
                item_name = model.data(index, Qt.DisplayRole)
                full_path = f"{self.current_path.rstrip('/')}/{item_name}"
                
                # 一時ファイルとしてエクスポート
                try:
                    import tempfile
                    temp_dir = Path(tempfile.gettempdir()) / "xdf_drag"
                    temp_dir.mkdir(exist_ok=True)
                    
                    local_path = temp_dir / item_name
                    self.backend.export_path_to_local(full_path, local_path)
                    urls.append(QUrl.fromLocalFile(str(local_path)))
                except Exception:
                    pass
        
        if urls:
            mime = QMimeData()
            mime.setUrls(urls)
            
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.CopyAction)
