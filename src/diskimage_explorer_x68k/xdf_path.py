"""X68000 パス解析・ワイルドカード処理（XEiJ 分析に基づく実装）。"""

import re
from typing import List, Optional, Tuple


class PathParser:
    """X68000 パス解析クラス。
    
    X68000 ではバックスラッシュ（\\）でパスを区切る。
    例: \\DIR\\FILE.TXT
    """
    
    @staticmethod
    def normalize_path(path: str) -> str:
        """パスを正規化（大文字化、区切り文字統一）。
        
        Args:
            path: X68000 スタイルのパス（\\区切り）
        
        Returns:
            正規化されたパス
        """
        # 区切り文字を統一（バックスラッシュ → フォワードスラッシュ）
        normalized = path.replace('\\', '/')
        
        # 大文字化
        normalized = normalized.upper()
        
        # 先頭のスラッシュを削除（相対パス処理のため）
        normalized = normalized.lstrip('/')
        
        return normalized
    
    @staticmethod
    def split_path(path: str) -> List[str]:
        """パスをディレクトリ要素に分割。
        
        Args:
            path: パス（フォワードスラッシュまたはバックスラッシュ区切り）
        
        Returns:
            ディレクトリ/ファイル要素のリスト
        
        例:
            "\\DIR\\SUBDIR\\FILE.TXT" → ["DIR", "SUBDIR", "FILE.TXT"]
            "FILE.TXT" → ["FILE.TXT"]
        """
        normalized = path.replace('\\', '/')
        normalized = normalized.lstrip('/')
        
        if not normalized:
            return []
        
        parts = normalized.split('/')
        return [p for p in parts if p]  # 空の要素を除外
    
    @staticmethod
    def get_directory_path(path: str) -> str:
        """パスからディレクトリ部分を抽出。
        
        Args:
            path: パス
        
        Returns:
            ディレクトリパス（最後のスラッシュまで）
        
        例:
            "\\DIR\\FILE.TXT" → "\\DIR"
            "FILE.TXT" → ""
        """
        normalized = path.replace('\\', '/')
        
        if '/' not in normalized:
            return ""
        
        last_slash = normalized.rfind('/')
        return normalized[:last_slash]
    
    @staticmethod
    def get_filename(path: str) -> str:
        """パスからファイル名部分を抽出。
        
        Args:
            path: パス
        
        Returns:
            ファイル名（最後のスラッシュ以降）
        
        例:
            "\\DIR\\FILE.TXT" → "FILE.TXT"
            "FILE.TXT" → "FILE.TXT"
        """
        normalized = path.replace('\\', '/')
        
        if '/' not in normalized:
            return normalized
        
        return normalized[normalized.rfind('/') + 1:]
    
    @staticmethod
    def split_filename(filename: str) -> Tuple[str, str]:
        """ファイル名を主ファイル名と拡張子に分割。
        
        Args:
            filename: ファイル名（例: "FILE.TXT"）
        
        Returns:
            (主ファイル名, 拡張子) のタプル
        
        例:
            "FILE.TXT" → ("FILE", "TXT")
            "NOEXT" → ("NOEXT", "")
            "MULTI.DOT.TXT" → ("MULTI.DOT", "TXT")
        """
        if '.' not in filename:
            return (filename, "")
        
        # 最後のドットで分割
        dot_pos = filename.rfind('.')
        if dot_pos == 0:  # "." で始まる
            return (filename, "")
        
        name = filename[:dot_pos]
        ext = filename[dot_pos + 1:]
        
        return (name, ext)
    
    @staticmethod
    def to_sfn_format(filename: str) -> Tuple[str, str]:
        """ファイル名を 8.3 SFN（Short File Name）形式に変換。
        
        Args:
            filename: ファイル名
        
        Returns:
            (主ファイル名8バイト, 拡張子3バイト) のタプル（パディング=スペース）
        
        例:
            "FILE.TXT" → ("FILE    ", "TXT")
            "VERYLONGNAME.X" → ("VERYLONG", "X  ")
        """
        name, ext = PathParser.split_filename(filename.upper())
        
        # 主ファイル名を8バイトに（超過時は切り詰め）
        name_padded = name[:8].ljust(8)
        
        # 拡張子を3バイトに（超過時は切り詰め）
        ext_padded = ext[:3].ljust(3)
        
        return (name_padded, ext_padded)


class WildcardMatcher:
    """X68000 ワイルドカード処理クラス。
    
    サポート: * （0個以上の任意文字）、? （任意の1文字）
    """
    
    @staticmethod
    def escape_regex(char: str) -> str:
        """正規表現の特殊文字をエスケープ。"""
        if char in r'\.^$+{}[]|()?':
            return '\\' + char
        return char
    
    @staticmethod
    def pattern_to_regex(pattern: str) -> str:
        """X68000 ワイルドカードを正規表現に変換。
        
        Args:
            pattern: ワイルドカードパターン（例: "FILE*.TXT"）
        
        Returns:
            正規表現パターン
        """
        # 大文字化
        pattern = pattern.upper()
        
        regex = "^"
        i = 0
        while i < len(pattern):
            char = pattern[i]
            
            if char == '*':
                # 0個以上の任意文字（? は含まない）
                regex += ".*"
            elif char == '?':
                # 任意の1文字
                regex += "."
            else:
                # その他の文字
                regex += WildcardMatcher.escape_regex(char)
            
            i += 1
        
        regex += "$"
        return regex
    
    @staticmethod
    def match(filename: str, pattern: str, case_sensitive: bool = False) -> bool:
        """ファイル名がパターンにマッチするか。
        
        Args:
            filename: ファイル名
            pattern: ワイルドカードパターン
            case_sensitive: 大文字小文字を区別するか
        
        Returns:
            マッチしたら True
        
        例:
            match("FILE.TXT", "*.TXT") → True
            match("FILE.TXT", "FILE?.TXT") → True
            match("FILE.TXT", "FILE*.TXT") → True
            match("FILE.TXT", "DATA*") → False
        """
        if not case_sensitive:
            filename = filename.upper()
            pattern = pattern.upper()
        
        try:
            regex = WildcardMatcher.pattern_to_regex(pattern)
            return bool(re.match(regex, filename))
        except re.error:
            # 不正なパターン
            return False
    
    @staticmethod
    def match_multiple(filenames: List[str], pattern: str, 
                      case_sensitive: bool = False) -> List[str]:
        """複数ファイル名に対してワイルドカード検索。
        
        Args:
            filenames: ファイル名リスト
            pattern: ワイルドカードパターン
            case_sensitive: 大文字小文字を区別するか
        
        Returns:
            マッチしたファイル名のリスト
        """
        return [f for f in filenames 
                if WildcardMatcher.match(f, pattern, case_sensitive)]


class PathValidator:
    """パス検証クラス。"""
    
    # X68000 で使用禁止な文字
    INVALID_CHARS = {
        '/', '\\', ':', '*', '?', '"', '<', '>', '|'
    }
    
    @staticmethod
    def is_valid_filename(filename: str) -> bool:
        """ファイル名が有効か。
        
        Args:
            filename: ファイル名
        
        Returns:
            有効なら True
        """
        if not filename or len(filename) > 255:
            return False
        
        # 先頭が '-' でないか
        if filename.startswith('-'):
            return False
        
        # 禁止文字が含まれていないか
        for char in filename:
            if char in PathValidator.INVALID_CHARS or ord(char) < 0x20:
                return False
        
        return True
    
    @staticmethod
    def is_valid_path(path: str) -> bool:
        """パスが有効か。
        
        Args:
            path: パス
        
        Returns:
            有効なら True
        """
        parts = PathParser.split_path(path)
        
        for part in parts:
            if not PathValidator.is_valid_filename(part):
                return False
        
        return True
    
    @staticmethod
    def is_dot_directory(name: str) -> bool:
        """"." または ".." のみか。
        
        Args:
            name: ファイル名
        
        Returns:
            "." または ".." のみなら True
        """
        return name in ('.', '..')


class PathResolver:
    """パス解決クラス（相対パス→絶対パス変換など）。"""
    
    def __init__(self, root_path: str = ""):
        """初期化。
        
        Args:
            root_path: ルートパス（ホストファイルシステムのマウントポイント）
        """
        self.root_path = root_path
        self.current_path = ""
    
    def resolve_path(self, path: str, current_dir: str = "") -> str:
        """パスを絶対パスに解決。
        
        Args:
            path: パス（相対/絶対）
            current_dir: 現在のディレクトリ
        
        Returns:
            解決されたパス（スラッシュ区切り）
        """
        if path.startswith('\\') or path.startswith('/'):
            # 絶対パス
            return PathParser.normalize_path(path)
        else:
            # 相対パス（X68000では基本的に絶対パスのみ）
            if current_dir:
                full_path = current_dir + '/' + path
            else:
                full_path = path
            
            return PathParser.normalize_path(full_path)
    
    def join_path(self, *parts: str) -> str:
        """複数のパス要素を結合。
        
        Args:
            parts: パス要素
        
        Returns:
            結合されたパス（スラッシュ区切り）
        
        例:
            join_path("\\DIR", "FILE.TXT") → "/DIR/FILE.TXT"
        """
        clean_parts = []
        for part in parts:
            part = part.replace('\\', '/').strip('/')
            if part:
                clean_parts.append(part)
        
        return '/' + '/'.join(clean_parts) if clean_parts else '/'
