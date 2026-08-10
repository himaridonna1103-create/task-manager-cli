#!/usr/bin/env python3
"""
minutes/ 配下の議事録テキスト（.txt / .md）を再帰的に読み込み、
議題ごとのセクションに分割して documents.jsonl に書き出す前処理スクリプト。

実行方法（Windows）:
    python -X utf8 preprocess.py
    python -X utf8 preprocess.py --input minutes --output documents.jsonl
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---- 見出し検出 -------------------------------------------------------
# "## 見出し" / "■ 見出し" / "【見出し】残りの文" のいずれかで始まる行を
# 議題の切れ目とみなす
HEADING_RE = re.compile(
    r'^\s*(?:#{2,}\s*(?P<h1>[^\s#].*)|■\s*(?P<h2>[^\s■].*)|【(?P<h3>[^】]+)】\s*(?P<h3rest>.*))\s*$'
)

# ---- 日付検出 ----------------------------------------------------------
DATE_PATTERNS = [
    re.compile(r'(?P<y>\d{4})[-/年](?P<m>\d{1,2})[-/月](?P<d>\d{1,2})日?'),
    re.compile(r'(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})(?!\d)'),
]


def read_text(path: Path):
    """UTF-8 → UTF-8(BOM) → cp932 の順に試して読み込む"""
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    return None


def normalize_date(text):
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        y, mo, d = m.group('y'), m.group('m'), m.group('d')
        try:
            y_i, mo_i, d_i = int(y), int(mo), int(d)
            if 1 <= mo_i <= 12 and 1 <= d_i <= 31:
                return f"{y_i:04d}-{mo_i:02d}-{d_i:02d}"
        except ValueError:
            continue
    return None


def extract_date(path: Path, body: str):
    # まずファイル名から
    date = normalize_date(path.stem)
    if date:
        return date
    # 見つからなければ本文1行目から
    stripped = body.strip()
    if not stripped:
        return None
    first_line = stripped.splitlines()[0]
    return normalize_date(first_line)


def parse_heading_line(line):
    m = HEADING_RE.match(line)
    if not m:
        return None
    if m.group('h1'):
        return m.group('h1').strip()
    if m.group('h2'):
        return m.group('h2').strip()
    if m.group('h3') is not None:
        head = m.group('h3').strip()
        rest = (m.group('h3rest') or '').strip()
        return f"{head} {rest}".strip() if rest else head
    return None


def split_by_heading(lines):
    """見出し行を目印にセクション分割。1件も見出しが無ければ found_any=False を返す"""
    sections = []
    current_heading = None
    current_body = []
    found_any = False

    for line in lines:
        heading = parse_heading_line(line)
        if heading is not None:
            found_any = True
            if current_body or current_heading is not None:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = heading
            current_body = []
        else:
            current_body.append(line)

    if current_body or current_heading is not None:
        sections.append((current_heading, "\n".join(current_body).strip()))

    return sections, found_any


def split_by_blank_lines(lines):
    """見出しが無いファイル用：空行2行以上の連続を話題の切れ目とみなす"""
    sections = []
    current_body = []
    blank_run = 0

    for line in lines:
        if line.strip() == "":
            blank_run += 1
            current_body.append(line)
        else:
            if blank_run >= 2 and any(l.strip() for l in current_body):
                text = "\n".join(current_body).strip()
                if text:
                    sections.append((None, text))
                current_body = []
            blank_run = 0
            current_body.append(line)

    text = "\n".join(current_body).strip()
    if text:
        sections.append((None, text))

    if not sections:
        whole = "\n".join(lines).strip()
        if whole:
            sections = [(None, whole)]

    return sections


def process_file(path: Path, minutes_root: Path):
    text = read_text(path)
    if text is None:
        return None, "読み込み失敗（エンコーディング不明）", False

    lines = text.splitlines()
    heading_sections, found_heading = split_by_heading(lines)

    if found_heading:
        sections = [(h, b) for h, b in heading_sections if b]
    else:
        sections = split_by_blank_lines(lines)

    if not sections:
        return None, "本文が空、またはセクションが抽出できませんでした", found_heading

    date = extract_date(path, text)
    rel_source = str(path.relative_to(minutes_root.parent))

    records = [
        {"source": rel_source, "date": date, "heading": heading, "body": body}
        for heading, body in sections
        if body
    ]

    if not records:
        return None, "本文が空、またはセクションが抽出できませんでした", found_heading

    return records, None, found_heading


def main():
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="minutes/ 配下の議事録を前処理して documents.jsonl を生成する")
    parser.add_argument("--input", default=str(script_dir / "minutes"), help="議事録フォルダ（既定: rag-webinar/minutes）")
    parser.add_argument("--output", default=str(script_dir / "documents.jsonl"), help="出力先（既定: rag-webinar/documents.jsonl）")
    args = parser.parse_args()

    minutes_root = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not minutes_root.exists():
        print(f"入力フォルダが見つかりません: {minutes_root}")
        sys.exit(1)

    target_files = sorted(
        p for p in minutes_root.rglob("*")
        if p.is_file() and p.suffix.lower() in (".txt", ".md")
    )

    all_records = []
    failed_files = []
    no_date_files = []
    no_heading_files = []

    for path in target_files:
        rel = str(path.relative_to(minutes_root.parent))
        records, err, found_heading = process_file(path, minutes_root)

        if records is None:
            failed_files.append(f"{rel}（{err}）")
            continue

        all_records.extend(records)

        if records[0]["date"] is None:
            no_date_files.append(rel)
        if not found_heading:
            no_heading_files.append(rel)

    with output_path.open("w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("=" * 50)
    print(f"対象ファイル数: {len(target_files)} 本")
    print(f"抽出セクション数: {len(all_records)} 件")
    print(f"出力先: {output_path}")
    print("=" * 50)

    if failed_files:
        print(f"\n[読み込み/抽出に失敗したファイル] {len(failed_files)} 件")
        for f_ in failed_files:
            print(f"  - {f_}")

    if no_date_files:
        print(f"\n[開催日が取れなかったファイル] {len(no_date_files)} 件")
        for f_ in no_date_files:
            print(f"  - {f_}")

    if no_heading_files:
        print(f"\n[議題見出しが取れなかったファイル（話題の切り替わりで分割）] {len(no_heading_files)} 件")
        for f_ in no_heading_files:
            print(f"  - {f_}")

    if not (failed_files or no_date_files or no_heading_files):
        print("\nすべてのファイルで日付・見出しを抽出できました。")


if __name__ == "__main__":
    main()
