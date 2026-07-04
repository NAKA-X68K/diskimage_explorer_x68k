# x68k-hdf-editor プロジェクト分析

## 1. プロジェクト構造

```
x68k-hdf-editor/
├── README.md
├── pyproject.toml                    # プロジェクト設定
├── requirements.txt                  # 依存関係
├── requirements-dev.txt
├── diskimage_explorer_x68k.spec      # PyInstaller設定
│
├── src/
│   ├── launcher.py                   # エントリーポイント
│   └── diskimage_explorer_x68k/
│       ├── __init__.py
│       ├── __main__.py               # __main__モジュール
│       ├── main.py                   # GUI実装 (1157行)
│       └── backend.py                # FAT操作実装 (1016行)
│
├── scripts/                          # ユーティリティスクリプト
├── build/                            # ビルド出力
├── dist/                             # 配布パッケージ
├── installer/                        # インストーラー
└── .venv/                            # 仮想環境 (pyfatfs含む)
```

## 2. 依存関係

### requirements.txt
```
PySide6>=6.7          # GUI フレームワーク (Qt)
pyfatfs>=1.1.0        # FAT ファイルシステムライブラリ
charset-normalizer>=3.3   # 文字エンコーディング検出
setuptools<81
```

### pyfatfs のインストール位置
- `.venv/lib/python3.13/site-packages/pyfatfs/`
  - `PyFat.py`: FAT テーブル管理
  - `PyFatFS.py`: FAT ファイルシステム API
  - `FATDirectoryEntry.py`: ディレクトリエントリ処理
  - 他 (EightDotThree, DosDateTime, FatIO など)

---

## 3. pyfatfs の使用状況

### backend.py での使用

#### インポート
```python
from pyfatfs.PyFat import PyFat
from pyfatfs.PyFatFS import PyFatFS, PyFatBytesIOFS
```

#### 使用場所と具体的な使用方法

| 機能 | 実装箇所 | 詳細 |
|------|---------|------|
| **FAT型判定** | line 58 | `PyFat.FAT_TYPE_FAT12` を使用してプロファイル定義 |
| **ファイルシステムマウント** | `FatImageBackend._mount_with_kind()` (line ~840) | `PyFatFS()` / `PyFatBytesIOFS()` で FAT マウント |
| **ディレクトリ列挙** | `FatImageBackend.list_dir()` (line ~903) | `fs.listdir()`, `fs.getinfo()` でエントリ取得 |
| **ファイル読み込み** | `FatImageBackend.read_file_bytes()` (line ~959) | `fs.openbin()` でバイナリ読み込み |
| **ファイル書き込み** | `FatImageBackend.write_file_bytes()` (line ~966) | `fs.openbin("w")` でバイナリ書き込み |
| **ディレクトリ作成** | `FatImageBackend.create_dir()` (line ~949) | `fs.makedir()` で新規作成 |
| **ファイル削除** | `FatImageBackend.delete_paths()` (line ~941) | `fs.removetree()` / `fs.remove()` で削除 |
| **ファイルコピー** | `FatImageBackend.import_local_path()` (line ~926) | `fs.openbin("w")` + `shutil.copyfileobj()` |

### 重要な使用パターン

#### 1. FAT マウント処理
```python
# X68000 形式（カスタムアダプタ経由）
adapter = X68kFatAdapter(image_path, offset)
fs = PyFatBytesIOFS(fp=adapter, offset=0, preserve_case=False, lazy_load=True)

# 標準 FAT 形式
fs = PyFatFS(
    filename=str(image_path),
    offset=offset,
    preserve_case=False,
    read_only=False,
    lazy_load=True,
)
```

#### 2. ファイル操作
```python
# ディレクトリ列挙
names = fs.listdir(path)
info = fs.getinfo(child, namespaces=["details"])
size = info.raw.get("details", {}).get("size", 0)

# ファイル I/O
with fs.openbin(target_file, "w") as dst:
    shutil.copyfileobj(src, dst)

# ディレクトリ操作
fs.makedir(path, recreate=True)
fs.removetree(path)
fs.remove(path)
```

---

## 4. FAT ファイルシステム操作の現在の実装パターン

### 4.1 X68000 固有の処理

#### X68kFatAdapter クラス (line ~640)
- **目的**: X68000 XDF/HDF イメージの特殊なブートセクタ形式に対応
- **機能**:
  - X68000 IPL（Intelligent Program Loader）署名を検出
  - ビッグエンディアン BPB (BIOS Parameter Block) をサポート
  - 合成ブートセクタを生成し、pyfatfs が認識できる形式に変換
  - X68000 形式のメディアバイト値を保護（ディスク書き込み時に元の値を保全）

#### X68000 XDF プロファイル (line ~44-56)
```python
X68K_XDF_PROFILES = (
    X68kFloppyProfile("2HD (1232KB)", 1024, 1, 2, 1, 192, 1232, 0xFE, 2, FAT12),
    X68kFloppyProfile("2HC (1200KB)", 512, 1, 2, 1, 224, 2400, 0xFD, 7, FAT12),
    X68kFloppyProfile("2DD (640KB)", 512, 2, 2, 1, 112, 1280, 0xFB, 2, FAT12),
    X68kFloppyProfile("2DD (720KB)", 512, 2, 2, 1, 112, 1440, 0xFC, 3, FAT12),
    X68kFloppyProfile("2HQ (1440KB)", 512, 1, 2, 1, 224, 2880, 0xFA, 9, FAT12),
)
```

### 4.2 パス処理

#### 正規化関数
```python
def _normalize_path_for_x68k(path: str) -> str:
    """パスコンポーネントを大文字に正規化"""
    p = PurePosixPath(path)
    parts = [part.upper() for part in p.parts if part and part != "/"]
    return "/" + "/".join(parts) if parts else "/"

def _to_fat_sfn(filename: str) -> str:
    """FAT 8.3 Short File Name (SFN) 形式に変換
    - X68000/XEiJ との互換性を確保
    - Long File Name (LFN) エントリ生成を回避
    - 例: "verylongfilename.txt" -> "VERYLO~1.TXT"
    """
```

### 4.3 イメージ検出

#### 複数の検出メカニズム
1. **FAT オフセット検出** (`detect_fat_offsets()`)
   - FAT ブートセクタシグネチャ (0x55AA) をスキャン
   - 複数の FAT パーティションに対応

2. **X68000 パーティション検出** (`detect_x68k_partition_candidates()`)
   - SASI ハードディスク形式 (BPB at 0x400)
   - SCSI ハードディスク形式 (BPB at 0x800)
   - 複数パーティションをサポート

3. **X68000 フロッピー検出** (`detect_x68k_floppy_candidate()`)
   - X68IPL30 シグネチャ検出
   - ファイルサイズとプロファイル照合
   - BPB パーサー

---

## 5. GUI と FAT 操作の結合ポイント

### 5.1 main.py (1157行) - GUI 実装

#### 主要コンポーネント

| クラス | 役割 | 主要メソッド |
|--------|------|------------|
| **MainWindow** | メインウィンドウ | `_build_ui()`, `_mount_image_path()`, `refresh_tree()` |
| **DropTreeWidget** | ツリービュー（ドラッグ&ドロップ対応） | `dropEvent()`, `dragEnterEvent()` |
| **TaskThread** | バックグラウンド処理用スレッド | `run()` で非同期実行 |
| **BusyOverlay** | 処理中表示オーバーレイ | `show_with_message()`, `hide_overlay()` |
| **SpinnerWidget** | ローディングスピナー | `paintEvent()` でアニメーション |

#### ツリービュー構成
```
QTreeWidget
├── Column 0: Name (ファイル/フォルダ名) [ストレッチ可能]
├── Column 1: Type (DIR / FILE) [固定 88px]
├── Column 2: Size (ファイルサイズ) [固定 92px]
└── Column 3: Modified (更新日時) [固定 190px]

各アイテム:
├── UserRole: ファイルシステムパス
└── UserRole+1: ディレクトリフラグ (bool)
```

### 5.2 GUI → Backend インターフェース

#### イメージマウント → ツリー表示フロー

```python
def _mount_image_path(self, image_path: str) -> None:
    def work() -> list[dict]:
        self.backend.mount(image_path)          # FAT マウント
        if backup_on_open:
            self.backend.create_backup_now()    # バックアップ作成
        return self._build_tree_snapshot("/")   # ツリースナップショット構築

    def on_success(snapshot) -> None:
        self._fill_offset_combo()               # マウント候補コンボボックス更新
        self.tree.clear()
        self._apply_tree_snapshot(snapshot)     # ツリーに反映
        self._update_mount_controls()           # UI 状態更新

    self._run_busy_task("Opening image...", work, on_success, "Open failed")
```

### 5.3 操作別の結合ポイント

#### 1. ファイル/フォルダ作成
```python
create_new_file/create_new_dir()
    ↓ (ユーザー入力 → SFN 変換)
backend.create_empty_file() / backend.create_dir()
    ↓ (pyfatfs 操作)
fs.openbin() / fs.makedir()
    ↓ (ツリー更新)
refresh_tree() → _build_tree_snapshot()
```

#### 2. ファイル削除
```python
delete_selected()
    ↓ (選択アイテム取得)
backend.delete_paths(paths)
    ↓ (pyfatfs 削除)
fs.removetree() / fs.remove()
    ↓ (ツリー更新)
refresh_tree()
```

#### 3. ドラッグ&ドロップ → インポート
```python
DropTreeWidget.dropEvent()
    ↓ (ローカルファイルパス抽出)
on_local_paths_dropped(local_paths, target_path, target_is_dir)
    ↓ (マウント判定)
backend.import_local_path() / backend.replace_file()
    ↓ (pyfatfs 操作)
fs.openbin("w") + shutil.copyfileobj()
    ↓ (ツリー更新)
refresh_tree()
```

#### 4. ドラッグ → エクスポート
```python
_build_external_drag_urls()
    ↓ (一時ディレクトリ生成)
backend.export_path_to_local()
    ↓ (再帰的にエクスポート)
fs.openbin("r") → local file write
    ↓ (Qt MimeData に QUrl 登録)
startDrag() → Qt ドラッグシステム
```

### 5.4 スレッド管理

#### バックグラウンド処理パターン
```python
TaskThread (QThread)
├── run() で work() 実行（重い処理）
├── succeeded(result) シグナル発火
└── failed(error_msg) シグナル発火

MainWindow
├── _run_busy_task()
│   ├── BusyOverlay 表示（スピナー + メッセージ）
│   ├── UI 操作無効化
│   └── TaskThread 実行
├── on_success() で UI 更新
└── _on_busy_finished() で UI 復帰
```

---

## 6. FAT 操作 API サマリー

### FatImageBackend クラスの主要メソッド

```python
class FatImageBackend:
    # マウント関連
    mount(image_file)               # イメージマウント
    unmount()                       # アンマウント
    remount_at_offset(offset)       # 別オフセットで再マウント
    
    # ファイルシステム操作
    list_dir(dir_path) → [ImageEntry]
    create_dir(fs_dir_path)
    create_empty_file(fs_file_path)
    delete_paths(paths)
    
    # ファイル I/O
    read_file_bytes(fs_file_path) → bytes
    write_file_bytes(fs_file_path, data)
    
    # ファイル転送
    import_local_path(local_path, dest_dir)  # ローカル → イメージ
    replace_file(fs_file_path, local_file)
    export_path_to_local(fs_path, local_target)  # イメージ → ローカル
    
    # バックアップ
    create_backup_now() → Path
    
    # プロパティ
    image_path, current_offset, mount_candidates, offset_candidates
    backup_path, fs (PyFatFS インスタンス)
```

---

## 7. キーポイント

### X68000 互換性
- **LFN 回避**: `_to_fat_sfn()` で FAT SFN 形式に強制変換
- **大文字正規化**: `_normalize_path_for_x68k()` でファイル名を大文字化
- **IPL 対応**: X68IPL30 シグネチャ持つイメージをサポート
- **メディアバイト保護**: X68000 形式のディスク書き込み時に元値を保全

### 非同期処理
- **TaskThread**: 重い FAT 操作をバックグラウンド実行
- **BusyOverlay**: 処理中をユーザーに通知
- **シグナル/スロット**: PySide6 の非同期コールバック

### マルチパーティション
- 複数の FAT オフセット検出
- X68000 SASI/SCSI ハードディスク形式対応
- コンボボックスで動的切り替え
