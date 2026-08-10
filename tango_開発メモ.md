# tango_開発メモ.md — AI向け技術ドキュメント

> **このメモの目的**: どのAIモデルでも tango.html を安全に編集できるようにするための引き継ぎ資料。
> tango.html を編集する前に、必ずこのファイルを最後まで読むこと。

## アプリ概要

- 英単語学習アプリ「tango.」。HTML/CSS/JavaScript が1ファイルに全部入り（`tango.html`・依存ライブラリなし）
- 公開先: GitHub Pages https://himaridonna1103-create.github.io/task-manager-cli/tango.html
  （リポジトリ: himaridonna1103-create/task-manager-cli・masterブランチ直下）
- データ保存: ブラウザの localStorage のみ。サーバーなし。**ユーザーの学習データはユーザーの端末にしかない**

## データ構造（localStorage キー: `tango-app-v1`）

```
S = {
  v: 3,                     // データバージョン。サンプル語を変えたら必ず +1（下記「移行の仕組み」参照）
  words: [ { id, en, ja, pos, img, pr, ex, fam, ant }, ... ],
  nextId: 次に振るid,
  stats: { <id>: { seen, miss, forgot } },   // 学習記録
  startDate: "YYYY-MM-DD" | null,            // 週サイクルの起点
  daily: { date, doneIds, ok, ng }           // 当日分（日付が変わるとリセット）
}
```

- word のフィールド: en=英語 / ja=意味 / pos=品詞 / img=イメージ(1=＋, -1=−, 0=中立) /
  **pr=優先度(1=★★★→1週目, 2=★★→2週目, 3=★→3週目)** / ex=フレーズ / fam=品詞ファミリー / ant=反意語

## 絶対に守るルール（壊すと事故になる）

1. **XSS対策**: ユーザー入力・単語データをHTMLに埋め込むときは必ず `esc()` を通す。
   `onclick="...speak('...')"` のような**属性内に埋め込む場合は `esc(jsq(...))` の二段**（jsqだけでは不十分。過去にレビューで重大指摘を受けて修正済み）
2. **サンプル単語を追加・変更したら `S.v` のバージョン番号を上げる**（seed値と `load()` 内の比較、`migrate()` 内の代入の3箇所）。
   上げないと既存ユーザーに変更が反映されない。`migrate()` は en の一致で照合し、学習記録・自作単語を保持したまま新サンプルを取り込む設計
3. **アプリをコピーして別バージョンを作るときは、`KEY` 定数（`tango-app-v1`）を必ず別名に変える**。
   同じだと同一オリジン上でデータが混ざる
4. **importData() のゼロトラスト検証を弱めない**。外部JSONは1語ずつ型検証・正規化してから取り込む（改造時もこの構造を維持）
5. **削除系・リセット系の操作には confirm() を残す**

## 編集後の検証手順（毎回必ず実行）

```bash
# 1. JS構文チェック
cd "C:\Users\karim\Claud 4.26"
sed -n '/<script>/,/<\/script>/p' tango.html | sed '1d;$d' > "$TEMP/tango_check.js"
node --check "$TEMP/tango_check.js"

# 2. 単語数・重複チェック（サンプル語を触った場合）
grep -c '^w(' tango.html
grep -o '^w("[^"]*"' tango.html | sort | uniq -d   # 出力ゼロが正常
```

サンプル語や移行処理を触った場合は、さらに「migrate() のシミュレーションテスト」を行う
（localStorage をスタブして旧データ→新データの移行で、語数・学習記録・自作単語が保持されるか確認。過去のセッションで使った手法）。

## デプロイ（公開）の手順とルール

1. **push（公開）の前に、必ずひまりさんに確認を取る**（取説のルール。勝手に公開しない）
2. OKが出たら: `git add tango.html` → `git commit` → `git push origin master`
3. 1〜2分でGitHub Pagesに自動反映。`curl` で公開URLの反映を確認する
4. 大きめの変更のときは、push前に **engineer-assistant-advocate**（品質検証エージェント）にレビューさせるのが定石

## 関連ファイル

- `tango_取説_管理用.md` — ひまりさん向けの運用手順
- `tango_使い方ガイド_生徒用.md` — 生徒配布用
- `Desktop/portfolio/英単語学習 tango/` — ポートフォリオ一式（アプリ更新時はコピーの更新も検討）

## 設計の背景（なぜこうなっているか）

- 学習方式はひまりさんの授業メソッド：「同じ100語を1週間毎日」×4週サイクル。1週目=pr1、2週目=pr2、3週目=pr3、4週目以降=全体（忘れた単語を先頭に）
- ×（忘れた）は stats.forgot に記録され、出題キューの先頭に並ぶ
- 音声は Web Speech API（iOSでは自動再生が不安定なため、🔊ボタンが主導線という割り切り）
- 収録は342語（★★★107 / ★★102+熟語25 / ★91+熟語17。熟語カード計49）

---
*作成: 2026-07-14。大きな設計変更をしたら、このメモも必ず更新すること。*
