# diskimage_explorer_x68k (Python GUI)

X68000 のハードディスクイメージ (`.HDF`, `.HDS`) を GUI で編集するツールです。

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
2. `Open HDF/HDS` でイメージを開く
3. `Offset` でパーティション/候補を切り替える
4. 必要なら `Backup Now` で明示バックアップを作成
5. ツリーへローカルファイル/フォルダを D&D
6. ファイル上に単体ファイルをドロップすると置換
7. `New File`, `New Folder`, `Delete` で編集

## 安全対策

- 初回の書き込み前に、自動でバックアップ (`*.bak-YYYYMMDD-HHMMSS`) を作成します。
- `Backup on Open` を有効にすると、マウント直後に全体バックアップを作成します。
- 過去3回分のみ保持し、古いものから削除します。
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

生成物:

- `dist/diskimage_explorer_x68k/`
- `dist/diskimage_explorer_x68k.app` (macOS app build)
- `dist/diskimage_explorer_x68k-mac.dmg` (macOS DMG build)

## 注意

- FAT として解釈できる領域をオフセット探索してマウントします。
- 画像形式によっては先頭に独自ヘッダを持つため、`Offset` コンボで切り替えて確認してください。
- 文字コードやファイル名制約は FAT の制約に従います。

### 現在の制限

- FAT ブートセクタが通常配置の形式に加え、X68000 の SASI/SCSI パーティションテーブル + パーティション IPL 形式（BPB が非標準配置）にも対応しました。
- X68000 固有形式は内部で互換ヘッダを合成してマウントします。
- すべての HDF/HDS 形式を網羅しているわけではないため、特殊フォーマットでは失敗することがあります。

## 今後の拡張案

- フォルダ抽出
- タイムスタンプ編集
- パーティションテーブルの厳密解析
- PyInstaller による単体配布

## 免責事項 (Disclaimer)
本ソフトウェアは無保証です。本ソフトウェアの使用により生じた損害（ディスクイメージの破損、データ損失などを含む）について、作者は一切の責任を負いかねます。自己責任でご利用ください。

## 再配布について
本ソフトウェアの再配布は自由ですが、以下の情報を明記してください。
- オリジナルソースのURL: [ここにあなたのGitHubリポジトリURLを記載]

## バグ報告・お問い合わせ
バグや不具合を見つけた場合は、以下の連絡先までお知らせください。
- Twitter (X): @NAKA_X68K
