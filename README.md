# diskimage_explorer_x68k (Python GUI)

X68000 のディスクイメージ (`.HDF`, `.HDS`, `.XDF`) を GUI で編集するツールです。

## できること

- イメージを開いてファイル/フォルダを一覧表示
- 検出したパーティション/オフセット候補をラベル付きで切り替え
- Drag and Drop でホスト側ファイル/フォルダを取り込み
- ファイルへの単体ドロップで内容を置換
- ファイル/フォルダの削除
- 空ファイル/フォルダの新規作成
- 選択ファイルの抽出
- 任意タイミングの手動バックアップ作成
- Open 時の自動バックアップ（ON/OFF）

## 対応環境

- macOS
- Windows

Python 3.10+ を想定しています。

## セットアップ

```bash
cd diskimage_explorer_x68k
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

## 起動

```bash
PYTHONPATH=src python -m diskimage_explorer_x68k.main
```

Windows の場合:

```powershell
$env:PYTHONPATH = "src"
python -m diskimage_explorer_x68k.main
```

## 使い方

1. `Backup on Open` を必要に応じて ON/OFF
2. `Mount` で既存イメージを開く
3. `Offset` でパーティション/候補を切り替える
4. 必要なら `Backup Now` で明示バックアップを作成
5. ツリーへローカルファイル/フォルダを D&D
6. ファイル上に単体ファイルをドロップすると置換
7. `New File`, `New Folder`, `Delete` で編集

## 安全対策

- 初回の書き込み前に、自動でバックアップ (`*.bak-YYYYMMDD-HHMMSS`) を作成します。
- `Backup on Open` を有効にすると、マウント直後に全体バックアップを作成します。
- バックアップは過去3回分のみ保持し、古いものから削除します。
- `Backup Now` で任意のタイミングでバックアップを作成できます。

## 配布ビルド (PyInstaller)

開発依存を導入:

```bash
pip install -r requirements-dev.txt
```

macOS:

```bash
./scripts/build-macos.sh
```

Windows (PowerShell):

```powershell
.\scripts\build-windows.ps1
```

### Windows 実行前に必要なもの

- Microsoft Visual C++ 再頒布可能パッケージ (x64, 2015-2022)
	- `winget install Microsoft.VCRedist.2015+.x64`
	- もしくは Microsoft 公式ページから `vc_redist.x64.exe` をインストール
- 実行は `build\` ではなく `dist\diskimage_explorer_x68k\diskimage_explorer_x68k.exe` を使う
- `diskimage_explorer_x68k.exe` 単体では起動できません。`_internal\` を含むフォルダ一式が必要です

### Windows トラブルシュート

`Failed to load Python DLL ... _internal\\python3xx.dll` が出る場合:

1. `build\...` 側の EXE を実行していないか確認する
2. `dist\diskimage_explorer_x68k\` フォルダを丸ごと保持して実行する（EXE だけコピーしない）
3. Visual C++ 再頒布可能パッケージ (x64) をインストールする
4. もう一度 `.\scripts\build-windows.ps1` を実行して作り直す

Windows インストーラ (Inno Setup):

```powershell
.\scripts\build-windows-installer.ps1
```

- Inno Setup 6 が必要です（`ISCC.exe`）。
- 既定では PyInstaller ビルド後にインストーラを生成します。
- すでに `dist/diskimage_explorer_x68k/` がある場合は次でビルド工程を省略できます。

```powershell
.\scripts\build-windows-installer.ps1 -SkipBuild
```

Windows MSI (WiX v4):

```powershell
.\scripts\build-windows-msi.ps1
```

Windows 側の初回セットアップ（推奨）:

```powershell
.\scripts\setup-windows-msi-tools.ps1
```

- `winget` で .NET SDK 8 を導入し、`dotnet tool` で WiX v4 (`wix`) を導入します。
- すでに導入済みの場合は更新のみ行います。

- 既定では PyInstaller ビルド後に MSI を生成します。
- すでに `dist/diskimage_explorer_x68k/` がある場合は次でビルド工程を省略できます。

```powershell
.\scripts\build-windows-msi.ps1 -SkipBuild
```

Windows での最短手順:

1. PowerShell を開く
2. `cd <repo>`
3. `.\scripts\setup-windows-msi-tools.ps1`
4. `.\scripts\build-windows.ps1`
5. `.\scripts\build-windows-msi.ps1 -SkipBuild`
6. `dist\diskimage_explorer_x68k-windows-<version>.msi` を配布

MSI ビルドで `wix.exe : error WIX0118: Additional argument ... was unexpected` が出る場合:

1. `.\scripts\setup-windows-msi-tools.ps1` を再実行して WiX を更新する
2. `.\scripts\build-windows-msi.ps1 -SkipBuild` を再実行する
3. それでも失敗する場合は、`wix --version` とエラーログを共有する

注意:

- `dist/diskimage_explorer_x68k-windows-setup-<version>.exe` は Windows 上で `build-windows-installer.ps1` を実行したときに生成されます。
- macOS で作成した `dist/diskimage_explorer_x68k/` は macOS バイナリのため、そのままでは Windows インストーラ出力に使えません。

生成物:

- `dist/diskimage_explorer_x68k/`
- `dist/diskimage_explorer_x68k-windows-setup-<version>.exe` (Windows installer)
- `dist/diskimage_explorer_x68k-windows-<version>.msi` (Windows MSI)
- `dist/diskimage_explorer_x68k.app` (macOS app build)
- `dist/diskimage_explorer_x68k-mac.dmg` (macOS DMG build)

## 注意

- FAT として解釈できる領域をオフセット探索してマウントします。
- 画像形式によっては先頭に独自ヘッダを持つため、`Offset` コンボで切り替えて確認してください。
- 文字コードやファイル名制約は FAT の制約に従います。

### 現在の制限

- FAT ブートセクタが通常配置の形式に加え、X68000 の SASI/SCSI パーティションテーブル + パーティション IPL 形式、XDF フロッピー形式（BPB が非標準配置）にも対応しました。
- X68000 固有形式は内部で互換ヘッダを合成してマウントします。
- すべての HDF/HDS/XDF 形式を網羅しているわけではないため、特殊フォーマットでは失敗することがあります。

## 今後の拡張案

- フォルダ抽出
- タイムスタンプ編集
- パーティションテーブルの厳密解析
- PyInstaller による単体配布

## 免責事項 (Disclaimer)
本ソフトウェアは無保証です。本ソフトウェアの使用により生じた損害（ディスクイメージの破損、データ損失などを含む）について、作者は一切の責任を負いかねます。自己責任でご利用ください。

## 再配布について

本ソフトウェアの再配布は自由ですが、以下の情報を明記してください。

- オリジナルソースのURL: https://github.com/NAKA-X68K/diskimage_explorer_x68k

## バグ報告・お問い合わせ
バグや不具合を見つけた場合は、以下の連絡先までお知らせください。
- Twitter (X): @NAKA_X68K
