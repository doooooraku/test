
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
フォルダ仕分け v1.10
- Excel/CSVの列でフォルダ階層を決定する方針は v1.09 と同じ
- 変更点：フォルダ順を <体・服装・小物>/<背景環境>/<写真の写り方>/<光雰囲気> に変更
- 変更点：列「factor_ポーズ」があっても**フォルダは作らない**（完全に無視）
- 欠けている factor は階層を作らずスキップ（未分類は作らない）
- 2つ目の連番と末尾アンダーバーは削除して正規名に統一
- after_dir/after_filename を追記し、常に *_画像仕分け済み.* で新規保存
"""
from __future__ import annotations
import os, re, sys, shutil, argparse, logging, hashlib
from pathlib import Path
from typing import Optional, Tuple, List, Dict

try:
    import pandas as pd
except Exception:
    pd = None

try:
    import openpyxl  # for writing xlsx
except Exception:
    openpyxl = None

VALID_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

def normalize_filename(name: str) -> str:
    name = name.replace("＿", "_").replace("·", "").replace("・", "")
    name = re.sub(r"\s*_\s*", "_", name)
    name = re.sub(r"\s+\.", ".", name)
    return name.strip()

# face の後～5桁連番の直前までを middle として全部受け取る（v1.08以降の仕様）
NAME_RE = re.compile(
    r"""^
    (?P<date>\d{8})_
    (?P<content>[^_]+)_
    (?P<char>[^_]+)_
    (?P<face>[^_]+)_
    (?P<middle>.+?)_
    (?P<num>\d{5})
    (?:_\d{5})?
    _?
    \.(?P<ext>png|jpg|jpeg|webp|bmp|gif)$
    """, re.IGNORECASE | re.VERBOSE
)

def parse_filename(name: str):
    norm = normalize_filename(name)
    m = NAME_RE.match(norm)
    if not m: return None
    d = m.groupdict()
    return (d["date"], d["content"], d["char"], d["face"], d["middle"], d["num"], d["ext"].lower())

def build_canonical_name(date, content, char, face, middle, num, ext) -> str:
    return f"{date}_{content}_{char}_{face}_{middle}_{num}.{ext}"

def safe_join(base: Path, *parts: str) -> Path:
    p = base
    for s in parts:
        s = str(s).strip().replace("\\", "_").replace("/", "_")
        if s:
            p = p / s
    return p

def ensure_unique_path(path: Path) -> Path:
    if not path.exists(): return path
    stem, ext = path.stem, path.suffix
    i = 2
    while True:
        cand = path.with_name(f"{stem}_{i}{ext}")
        if not cand.exists(): return cand
        i += 1

def sha1sum(path: Path, bufsize: int = 1024*1024) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b: break
            h.update(b)
    return h.hexdigest()

def find_same_hash(dest_dir: Path, digest: str) -> Optional[Path]:
    if not dest_dir.exists(): return None
    for p in dest_dir.iterdir():
        if p.is_file():
            try:
                if sha1sum(p) == digest:
                    return p
            except Exception:
                pass
    return None

def move_or_copy(src: Path, dst: Path, copy: bool) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copy2(src, dst); return dst
    else:
        shutil.move(src, dst); return dst

def list_images(root: Path, recurse: bool) -> List[Path]:
    if not recurse:
        return [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VALID_EXTS]
    out: List[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in VALID_EXTS:
            out.append(p)
    return out

def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("image_sorter_v110")
    logger.setLevel(logging.INFO); logger.handlers.clear()
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8"); fh.setFormatter(fmt); logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); logger.addHandler(sh)
    return logger

def detect_mode_from_excel_name(path: Path) -> str | None:
    n = path.name.lower()
    if ("nsfw" in n) or ("nswf" in n): return "NSFW"
    if ("sfw" in n) or ("swf" in n): return "SFW"
    return None

def ask_mode_interactively(default: str="SFW") -> str:
    while True:
        s = input(f"SFW/NSFW を選択してください [S/N]（Enterで{default}）: ").strip().lower()
        if s == "": return default
        if s in ("s","sfw"): return "SFW"
        if s in ("n","nsfw"): return "NSFW"
        print("入力が不正です。S または N を入力してください。")

def read_table_auto(path: Path):
    if pd is None:
        raise RuntimeError("pandas が必要です。pip install pandas")
    ext = path.suffix.lower()
    if ext == ".csv":
        try:
            return pd.read_csv(path, encoding="utf-8-sig"), "csv"
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="cp932"), "csv"
    elif ext in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        return pd.read_excel(path, sheet_name=0), "xlsx"
    else:
        raise ValueError("対応拡張子は .csv / .xlsx です")

def write_table_auto(df, path: Path, kind: str):
    if kind == "csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
    elif kind == "xlsx":
        if openpyxl is None:
            raise RuntimeError("openpyxl が必要です。pip install openpyxl")
        df.to_excel(path, index=False)
    else:
        raise ValueError("unknown kind")

def common_parent(paths: List[Path]) -> Optional[Path]:
    if not paths: return None
    try:
        cp = os.path.commonpath([str(p) for p in paths])
        cp = Path(cp)
        return cp if cp.exists() and cp.is_dir() else None
    except Exception:
        return None

def prompt_for_dir(prompt: str, default: Optional[Path]=None) -> Path:
    while True:
        if default:
            s = input(f"{prompt}（Enterで {default} ）: ").strip()
            if s == "":
                p = default
            else:
                p = Path(os.path.expanduser(os.path.expandvars(s))).resolve()
        else:
            s = input(f"{prompt}: ").strip()
            p = Path(os.path.expanduser(os.path.expandvars(s))).resolve()
        if p.exists() and p.is_dir():
            return p
        print("ディレクトリが見つかりません。再入力してください。")

def decide_root_interactively(args_src: Optional[str], excel_path: Path, df) -> Path:
    if args_src:
        p = Path(os.path.expanduser(os.path.expandvars(args_src))).resolve()
        if p.exists() and p.is_dir():
            return p
        print(f"[WARN] --src のディレクトリが見つかりません: {p}")
    cand: Optional[Path] = None
    if df is not None and "img_dir" in df.columns:
        dirs = []
        for v in df["img_dir"].dropna().unique().tolist():
            vv = str(v).strip()
            if not vv: continue
            d = Path(os.path.expanduser(os.path.expandvars(vv))).resolve()
            if d.exists() and d.is_dir():
                dirs.append(d)
        if len(dirs) == 1:
            cand = dirs[0]
        elif len(dirs) > 1:
            cp = common_parent(dirs)
            cand = cp if cp else None
    if cand is None:
        eparent = excel_path.parent
        cand = eparent if (eparent.exists() and eparent.is_dir()) else Path.cwd()
    return prompt_for_dir("画像フォルダの絶対パス", default=cand)

def suffixed_output_path(src_path: Path, suffix: str="画像仕分け済み") -> Path:
    stem = src_path.stem
    if not stem.endswith(suffix):
        stem = f"{stem}_{suffix}"
    out = src_path.with_name(stem + src_path.suffix)
    if not out.exists():
        return out
    i = 2
    while True:
        cand = src_path.with_name(f"{stem}_{i}{src_path.suffix}")
        if not cand.exists():
            return cand
        i += 1

def build_category_from_excel_row(row: "pd.Series") -> Dict[str,str]:
    """Excelの1行からカテゴリを取り出す。存在しない列/空文字は除外。
       factor_ポーズ は読み取ってもフォルダに使わない（無視）。"""
    def val(col):
        return str(row.get(col, "")).strip()
    cats = {
        "content": val("content"),
        "character": val("character"),
        "face": val("factor_顔"),
        "body": val("factor_体・服装・小物"),
        "backg": val("factor_背景環境"),
        "photo": val("factor_写真の写り方"),
        "light": val("factor_光雰囲気"),
        # "pose": val("factor_ポーズ"),  # 読むだけならこうだが、フォルダは作らないので保持しない
    }
    # 空文字は削る（後段で階層を作らない）
    for k,v in list(cats.items()):
        if v in ("", "nan", "None"):
            cats[k] = ""
    return cats

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="フォルダ仕分け v1.10（背景→写真の順・ポーズ列は無視）")
    ap.add_argument("--src", type=str, help="画像が置かれているフォルダ（省略可。未指定なら対話）")
    ap.add_argument("--excel", type=str, help="Excel/CSVの絶対パス（省略可。未指定なら対話）")
    ap.add_argument("--mode", choices=["SFW","NSFW"], help="（任意）SFW/NSFWを明示。Excel/CSV名で判定不可なら対話へ")
    ap.add_argument("--copy", action="store_true", help="移動ではなくコピーで仕分け")
    ap.add_argument("--dry-run", action="store_true", help="移動/コピーせず仕分け計画のみ（Excel/CSVは更新しない）")
    ap.add_argument("--on-conflict", choices=["dup","skip","overwrite","hash"], default="dup", help="同名時の挙動")
    ap.add_argument("--batch", type=str, default="", help='"now" で HHMMSS を追加。任意文字列も可')
    ap.add_argument("--recurse", action="store_true", help="サブフォルダも探索")
    ap.add_argument("--min-bytes", type=int, default=1, help="このサイズ未満はスキップ")
    ap.add_argument("--out-suffix", type=str, default="画像仕分け済み", help="出力ファイル名に付与する末尾文字")
    args = ap.parse_args(argv)

    # Excel/CSV の決定（対話）
    excel_path: Path | None = None
    if args.excel:
        excel_path = Path(os.path.expanduser(os.path.expandvars(args.excel))).resolve()
    else:
        while True:
            s = input('Excelの絶対パス: ').strip()
            if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
                s = s[1:-1]
            p = Path(os.path.expanduser(os.path.expandvars(s))).resolve()
            if p.exists() and p.is_file():
                excel_path = p; break
            print("指定されたファイルが見つかりません。再入力してください。")

    # 読み込み
    df = None; io_kind = None
    if excel_path:
        try:
            df, io_kind = read_table_auto(excel_path)
        except Exception as e:
            print(f"[ERROR] Excel/CSV の読み込みに失敗: {e}")
            return 2

    # 画像フォルダの決定（対話補完）
    root = decide_root_interactively(args.src, excel_path, df)

    # SFW/NSFW の決定
    mode = None
    if excel_path:
        mode = detect_mode_from_excel_name(excel_path)
    if not mode:
        if args.mode:
            mode = args.mode
        else:
            mode = ask_mode_interactively(default="SFW")

    # ロガー
    log_path = root / "image_sorter_v110.log"
    logger = setup_logger(log_path)

    # バッチ
    if args.batch == "now":
        from datetime import datetime
        args.batch = datetime.now().strftime("%H%M%S")

    # 画像列挙
    files = list_images(root, recurse=args.recurse)
    if not files:
        logger.warning("対象拡張子のファイルが見つかりません。対応拡張子: %s", ", ".join(VALID_EXTS))
        return 0

    # Excel 側の prefix -> row 情報マップ（カテゴリ取得用）
    row_map: Dict[str, Dict[str,str]] = {}
    if df is not None and "filename_prefix" in df.columns:
        for _, row in df.iterrows():
            key = str(row.get("filename_prefix","")).strip()
            if not key: continue
            row_map[key] = build_category_from_excel_row(row)

    moved=copied=skipped_unmatched=skipped_small=skipped_conflict=skipped_hash_dup=overwritten=dupped=0
    moved_records: List[Path] = []

    for f in sorted(files):
        size = f.stat().st_size
        if size < max(0, int(args.min_bytes)):
            logger.warning("小さすぎるためスキップ(%d bytes): %s", size, f)
            skipped_small += 1; continue

        parsed = parse_filename(f.name)
        if not parsed:
            logger.warning("命名規則に一致しないためスキップ: %s", f.name)
            skipped_unmatched += 1; continue

        date, content0, char0, face0, middle, num, ext = parsed

        # 正規名に統一（2連番と末尾_を除去）
        canonical = build_canonical_name(date, content0, char0, face0, middle, num, ext)
        if canonical != f.name:
            new_path = f.with_name(canonical)
            if new_path.exists():
                new_path = ensure_unique_path(new_path)
            if not args.dry_run:
                try:
                    f.rename(new_path)
                except Exception as e:
                    logger.error("   リネーム失敗: %s -> %s (%s)", f.name, new_path.name, e)
                f = new_path
            else:
                logger.info("   正規名へリネーム予定: %s -> %s", f.name, new_path.name)
                f = new_path

        # Excel からカテゴリ取得（なければファイル名の値を使用）
        stem = f.stem
        cats = None
        if row_map:
            cats = row_map.get(stem)
            if not cats:
                for k, v in row_map.items():
                    if stem.startswith(k):
                        cats = v; break
        if cats is None:
            cats = {
                "content": content0,
                "character": char0,
                "face": face0,
                "body": middle,  # Excel未一致時のみ middle を body として使用
                "backg": "",
                "photo": "",
                "light": "",
            }
            logger.info("   Excel未一致のためファイル名からカテゴリを使用: %s", f.name)

        # <<< フォルダ順を body -> backg -> photo -> light に変更 >>>
        parts: List[str] = [mode, cats["content"], cats["character"], cats["face"], cats["body"], cats["backg"], cats["photo"], cats["light"], date]
        parts = [p for p in parts if p]  # 空はスキップ

        dest_dir = safe_join(root, *parts)
        if args.batch:
            dest_dir = dest_dir / args.batch
        dest_path = dest_dir / f.name

        logger.info("→ %s  ->  %s", f, dest_path.relative_to(root))
        if args.dry_run: continue

        try:
            if args.on_conflict == "hash":
                digest = sha1sum(f)
                same = find_same_hash(dest_dir, digest)
                if same:
                    logger.info("   内容重複のためスキップ（hash-dup）: %s == %s", f.name, same.name)
                    skipped_hash_dup += 1; continue

            final_path = dest_path
            if dest_path.exists():
                if args.on_conflict == "skip":
                    logger.info("   既存のためスキップ（skip）: %s", dest_path.relative_to(root))
                    skipped_conflict += 1; continue
                elif args.on_conflict == "overwrite":
                    logger.info("   既存を削除（overwrite）: %s", dest_path.relative_to(root))
                    dest_path.unlink()
                else:
                    final_path = ensure_unique_path(dest_path)

            final_path = move_or_copy(f, final_path, copy=args.copy)
            moved_records.append(final_path)
            if args.copy: copied += 1
            else: moved += 1
            logger.info("   完了: %s", final_path.relative_to(root))
        except Exception as e:
            logger.error("   失敗: %s (%s)", f, e)

    # Excel/CSV 更新（本番のみ）
    out_path = None
    if (df is not None) and (not args.dry_run):
        if "after_dir" not in df.columns:
            df["after_dir"] = ""
        if "after_filename" not in df.columns:
            df["after_filename"] = ""

        stem_map: Dict[str, Path] = {}
        for p in moved_records:
            stem_map.setdefault(p.stem, p)

        for i, row in df.iterrows():
            prefix = str(row.get("filename_prefix", "")).strip()
            if not prefix: continue
            p = stem_map.get(prefix)
            if p is None:
                for stem2, path in stem_map.items():
                    if stem2.startswith(prefix):
                        p = path; break
            if p is not None:
                df.at[i, "after_dir"] = str(p.parent)
                df.at[i, "after_filename"] = p.name

        out_path = suffixed_output_path(excel_path, args.out_suffix)
        try:
            write_table_auto(df, out_path, io_kind)
            logger.info("Excel/CSV を更新しました: %s", out_path)
        except PermissionError:
            alt = ensure_unique_path(out_path)
            try:
                write_table_auto(df, alt, io_kind)
                out_path = alt
                logger.info("Excel/CSV を更新しました（代替名）: %s", out_path)
            except Exception as e2:
                logger.error("Excel/CSV の保存に失敗: %s (%s)", out_path, e2)
        except Exception as e:
            logger.error("Excel/CSV の保存に失敗: %s (%s)", out_path, e)

    logger.info("=== サマリ ===")
    logger.info("moved: %d / copied: %d", moved, copied)
    logger.info("skipped_unmatched: %d  skipped_small: %d", skipped_unmatched, skipped_small)
    logger.info("skipped_conflict: %d  skipped_hash_dup: %d", skipped_conflict, skipped_hash_dup)
    logger.info("overwritten: %d  dupped: %d", overwritten, dupped)
    if out_path:
        logger.info("追記保存ファイル: %s", out_path)
    logger.info("ログ: %s", log_path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
