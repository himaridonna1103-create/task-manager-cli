#!/usr/bin/env python3
"""
documents.jsonl（1行1議題セクション）を読み込み、RAG用にチャンク分割して
SQLite（chunks テーブル + FTS5 全文検索テーブル）に格納するスクリプト。

チャンク分割ルール:
  - 議題セクション = 1チャンクが基本単位
  - セクションが長い場合のみ、300〜500文字を目安に「。」や改行（＝文/箇条書きの境界）
    でのみ分割する。文字数だけで機械的に切ることはしない
  - 各チャンクの先頭行に「{開催日} {議題名}」を付与する

実行方法（Windows）:
    python -X utf8 load_sqlite.py
    python -X utf8 load_sqlite.py --input documents.jsonl --db minutes.db
"""
import argparse
import json
import re
import sqlite3
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TARGET_MAX = 500   # チャンクの目安上限文字数
MIN_TARGET = 300   # チャンクの目安下限文字数
TAIL_MERGE_CAP = 650  # 末尾の小さすぎるチャンクを前のチャンクへ統合してよい上限


# ---- 分割ロジック -------------------------------------------------------

def split_units(text):
    """
    改行（＝行・箇条書きの境界）を最優先の分割候補とし、
    1行がTARGET_MAXを超える場合のみ「。」の直後でさらに分割する。
    戻り値: [(片, 新しい行の先頭か)] のリスト
    """
    units = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) <= TARGET_MAX:
            units.append((stripped, True))
        else:
            parts = [p for p in re.split(r'(?<=。)', stripped) if p]
            for i, p in enumerate(parts):
                units.append((p, i == 0))
    return units


def pack_units(units, target_max=TARGET_MAX):
    """境界（文・行）を保ったまま、target_max文字を目安に貪欲に詰めていく"""
    chunks = []
    cur_parts = []
    cur_len = 0

    for text, is_new_line in units:
        sep = ("\n" if is_new_line else "") if cur_parts else ""
        piece = sep + text
        if cur_parts and cur_len + len(piece) > target_max:
            chunks.append("".join(cur_parts))
            cur_parts = [text]
            cur_len = len(text)
        else:
            cur_parts.append(piece)
            cur_len += len(piece)

    if cur_parts:
        chunks.append("".join(cur_parts))

    return chunks


def merge_small_tail(chunks):
    """末尾のチャンクがMIN_TARGET未満なら、TAIL_MERGE_CAPを超えない範囲で前のチャンクに統合する"""
    while len(chunks) >= 2 and len(chunks[-1]) < MIN_TARGET:
        merged = chunks[-2] + "\n" + chunks[-1]
        if len(merged) <= TAIL_MERGE_CAP:
            chunks = chunks[:-2] + [merged]
        else:
            break
    return chunks


def chunk_body(body):
    """1議題セクションの本文をチャンクのリストに分割する（ヘッダー行は含まない）"""
    content = body.strip()
    if not content:
        return []
    if len(content) <= TARGET_MAX:
        return [content]

    units = split_units(content)
    if not units:
        return [content]

    chunks = pack_units(units, TARGET_MAX)
    chunks = merge_small_tail(chunks)
    return chunks


# ---- DB構築 --------------------------------------------------------------

def init_schema(cur):
    cur.executescript("""
        DROP TRIGGER IF EXISTS chunks_ai;
        DROP TRIGGER IF EXISTS chunks_ad;
        DROP TRIGGER IF EXISTS chunks_au;
        DROP TABLE IF EXISTS chunks_fts;
        DROP TABLE IF EXISTS chunks;

        CREATE TABLE chunks (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            source  TEXT,
            date    TEXT,
            heading TEXT,
            ord     INTEGER,
            text    TEXT NOT NULL
        );

        CREATE INDEX idx_chunks_date   ON chunks(date);
        CREATE INDEX idx_chunks_source ON chunks(source);
    """)

    # FTS5: 日本語の部分一致検索に強いtrigramトークナイザを優先し、
    # 使えない環境ではデフォルト(unicode61)にフォールバックする
    try:
        cur.execute("""
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                text, content='chunks', content_rowid='id', tokenize='trigram'
            )
        """)
        tokenizer = "trigram"
    except sqlite3.OperationalError:
        cur.execute("""
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                text, content='chunks', content_rowid='id'
            )
        """)
        tokenizer = "unicode61（trigram非対応のためフォールバック）"

    # chunks への増減・更新をFTS側に自動反映するトリガー
    cur.executescript("""
        CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
        END;
        CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
        END;
        CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
            INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
        END;
    """)

    return tokenizer


def load_documents(jsonl_path):
    docs = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


def main():
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="documents.jsonl をチャンク分割してSQLiteに格納する")
    parser.add_argument("--input", default=str(script_dir / "documents.jsonl"), help="入力JSONL（既定: rag-webinar/documents.jsonl）")
    parser.add_argument("--db", default=str(script_dir / "minutes.db"), help="出力DB（既定: rag-webinar/minutes.db）")
    args = parser.parse_args()

    jsonl_path = Path(args.input)
    db_path = Path(args.db)

    if not jsonl_path.exists():
        print(f"入力ファイルが見つかりません: {jsonl_path}")
        sys.exit(1)

    docs = load_documents(jsonl_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tokenizer = init_schema(cur)

    lengths = []
    total_chunks = 0

    for doc in docs:
        source = doc.get("source")
        date = doc.get("date")
        heading = doc.get("heading")
        body = doc.get("body") or ""

        date_disp = date if date else "日付不明"
        heading_disp = heading if heading else "見出しなし"
        header = f"{date_disp} {heading_disp}"

        for i, sub in enumerate(chunk_body(body)):
            text = f"{header}\n{sub}"
            cur.execute(
                "INSERT INTO chunks (source, date, heading, ord, text) VALUES (?, ?, ?, ?, ?)",
                (source, date, heading, i, text),
            )
            lengths.append(len(text))
            total_chunks += 1

    conn.commit()
    conn.close()

    print("=" * 50)
    print(f"総チャンク数: {total_chunks} 件")
    if lengths:
        lengths_sorted = sorted(lengths)
        median = statistics.median(lengths_sorted)
        print(f"チャンク文字数 — 最小: {min(lengths_sorted)} / 中央値: {median:.1f} / 最大: {max(lengths_sorted)}")
    else:
        print("チャンクが1件も生成されませんでした（documents.jsonlが空の可能性）")
    print(f"FTS5トークナイザ: {tokenizer}")
    print(f"出力先: {db_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()
