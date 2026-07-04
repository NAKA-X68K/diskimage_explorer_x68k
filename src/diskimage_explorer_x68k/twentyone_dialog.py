"""
TwentyOne File Creation Dialog for GUI Integration

GUI での21文字ファイル名作成をサポートするダイアログ
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QDialogButtonBox,
    QMessageBox,
    QFrame,
)
from PySide6.QtGui import QFont

from .twentyone import TwentyOneName, TWENTYONE_NAME_MAX


class TwentyOneFileDialog(QDialog):
    """TwentyOne (21文字) ファイル名で新規ファイルを作成するダイアログ"""
    
    def __init__(self, parent=None, default_filename: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Create TwentyOne File")
        self.setMinimumWidth(500)
        
        self.filename = None
        self._init_ui(default_filename)
    
    def _init_ui(self, default_filename: str):
        """UI を初期化"""
        layout = QVBoxLayout()
        
        # タイトル
        title = QLabel("TwentyOne File Name")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # 説明テキスト
        desc = QLabel(
            f"Enter a file name (up to {TWENTYONE_NAME_MAX} characters).\n"
            "Format: <name (18)>.<extension (3)>\n"
            "Example: verylongfilename.tar or foo.tar.gz"
        )
        desc.setStyleSheet("color: #666; font-size: 10pt;")
        layout.addWidget(desc)
        
        # ファイル名入力フィールド
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("File Name:"))
        
        self.input_field = QLineEdit()
        self.input_field.setText(default_filename)
        self.input_field.setMaxLength(TWENTYONE_NAME_MAX)
        self.input_field.textChanged.connect(self._on_filename_changed)
        input_layout.addWidget(self.input_field)
        
        layout.addLayout(input_layout)
        
        # ファイル名プレビュー
        preview_layout = QVBoxLayout()
        preview_label = QLabel("Preview:")
        preview_label.setStyleSheet("font-weight: bold;")
        preview_layout.addWidget(preview_label)
        
        self.preview_text = QLabel("")
        self.preview_text.setStyleSheet(
            "background-color: #f5f5f5; "
            "padding: 8px; "
            "border: 1px solid #ccc; "
            "border-radius: 3px; "
            "font-family: monospace;"
        )
        preview_layout.addWidget(self.preview_text)
        
        layout.addLayout(preview_layout)
        
        # 分割情報
        info_layout = QVBoxLayout()
        info_label = QLabel("Name Structure:")
        info_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(info_label)
        
        self.structure_text = QLabel("")
        self.structure_text.setStyleSheet(
            "background-color: #e8f4f8; "
            "padding: 8px; "
            "border: 1px solid #b3d9e6; "
            "border-radius: 3px; "
            "font-family: monospace; "
            "color: #0066cc;"
        )
        info_layout.addWidget(self.structure_text)
        
        layout.addLayout(info_layout)
        
        # エラー/警告メッセージ
        self.message_label = QLabel("")
        self.message_label.setStyleSheet("color: #cc0000; font-weight: bold;")
        layout.addWidget(self.message_label)
        
        # ボタン
        button_layout = QHBoxLayout()
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        
        button_layout.addStretch()
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 初期表示
        self._on_filename_changed()
    
    def _on_filename_changed(self):
        """ファイル名が変更されたときの処理"""
        filename = self.input_field.text().strip()
        
        # メッセージをクリア
        self.message_label.setText("")
        
        if not filename:
            self.preview_text.setText("(empty)")
            self.structure_text.setText("")
            self.ok_button.setEnabled(False)
            return
        
        # 検証
        try:
            TwentyOneName.validate(filename)
            tw_name = TwentyOneName.parse(filename)
            
            # プレビュー表示
            self.preview_text.setText(f"File: {tw_name.full_name}")
            
            # 構造表示
            structure = tw_name.name_display
            self.structure_text.setText(f"SFN: {tw_name.sfn_name}\nStructure: {structure}")
            
            self.ok_button.setEnabled(True)
        
        except ValueError as e:
            self.message_label.setText(f"❌ {str(e)}")
            self.preview_text.setText("")
            self.structure_text.setText("")
            self.ok_button.setEnabled(False)
    
    def _accept(self):
        """OK ボタンを押した時の処理"""
        filename = self.input_field.text().strip()
        
        if not filename:
            QMessageBox.warning(self, "Error", "Please enter a file name")
            return
        
        try:
            TwentyOneName.validate(filename)
            self.filename = filename
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Invalid File Name", str(e))
    
    def get_filename(self) -> str:
        """入力されたファイル名を取得"""
        return self.filename or ""


class TwentyOneFileContentDialog(QDialog):
    """TwentyOne ファイルの内容を編集するダイアログ"""
    
    def __init__(self, parent=None, filename: str = "", initial_content: bytes = b""):
        super().__init__(parent)
        self.setWindowTitle(f"Edit TwentyOne File: {filename}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        self.content = initial_content
        self._init_ui(filename)
    
    def _init_ui(self, filename: str):
        """UI を初期化"""
        layout = QVBoxLayout()
        
        # ファイル情報
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel(f"File: {filename}"))
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        # テキスト編集エリア
        from PySide6.QtWidgets import QPlainTextEdit
        
        self.text_edit = QPlainTextEdit()
        
        # 初期内容を表示（テキストとして解釈可能な場合）
        try:
            initial_text = self.content.decode('utf-8', errors='replace')
            self.text_edit.setPlainText(initial_text)
        except Exception:
            self.text_edit.setPlainText("")
        
        layout.addWidget(self.text_edit)
        
        # ボタン
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def _save(self):
        """保存ボタンを押した時の処理"""
        text = self.text_edit.toPlainText()
        self.content = text.encode('utf-8')
        self.accept()
    
    def get_content(self) -> bytes:
        """編集内容を取得"""
        return self.content
