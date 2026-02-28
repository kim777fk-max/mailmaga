# メルマガいたしん 統合管理ツール 引き継ぎ・再開ドキュメント

> 作成日: 2026-02-27  
> 担当: 板診会 広報部  
> GitHub: https://github.com/kim777fk-max/mailmaga

---

## 1. このプロジェクトの目的

板診会のメールマガジン「メルマガいたしん」の制作フローを自動化・効率化するツール群を開発する。

### 背景
- メルマガは奇数月15日発行（年6回）
- 広報部が全体のとりまとめを担当
- 各部署に原稿依頼→提出→チェック→配信のフローを毎回手作業で実施していた
- これを段階的に自動化していく

---

## 2. 現在の制作フロー（手動）

| ステップ | タイミング | 内容 | 担当 |
|---|---|---|---|
| ① | 偶数月25日 | スケジュール案内メール（内部向け） | 広報部 |
| ② | 偶数月26日 | 原稿依頼メール（執行委員・会長宛） | 広報部 |
| ③ | 締切まで | 各部署が原稿作成・XServerへ提出 | 各部署 |
| ④ | 締切前日（配信月6日） | リマインドメール | 広報部 |
| ⑤ | 締切日（配信月7日） | 締切メール・未提出者リマインド | 広報部 |
| ⑥ | 配信月8〜10日 | 原稿内容チェック（広報部内） | 広報部 |
| ⑦ | 配信月11日 | メルマガ配信フォーマットへ転記 | 広報部 |
| ⑧ | 配信月13日 | 最終チェック | 広報部 |
| ⑨ | 配信月15日 | メルマガ配信 | 広報部 |

### 原稿提出サーバー
- XServer: https://drive.rmc-itabashi.jp/index.php/s/5rX5tfHQep43eZr
- PWは別途メールで案内
- 原稿は現在XServerからローカルに手動ダウンロードして確認

---

## 3. 作成済みツール

### 3-1. 統合管理ツール（`app.py` / Flaskアプリ）

**場所**: `/Users/administrator/Desktop/DEV/melmaga-kanri/`  
**GitHub**: `mailmaga/` リポジトリのルート

| 画面 | URL | 機能 |
|---|---|---|
| ダッシュボード | `/` | 進行中の号の進捗確認・号一覧 |
| 新規号作成 | `/cycle/new` | 配信月を入力→スケジュール自動計算 |
| 号詳細 | `/cycle/<id>` | ①〜⑨のステップ管理・メール作成・原稿確認 |
| メール作成 | `/cycle/<id>/email/<step>` | テンプレート展開・コピー・mailto:リンク |
| 設定 | `/settings` | 送信者情報・メールテンプレート編集 |

**起動方法**:
```bash
cd /Users/administrator/Desktop/DEV/melmaga-kanri
python3 app.py
# → http://localhost:5001 をブラウザで開く
```

または:
```bash
./start.sh
```

### 3-2. 原稿入力フォーム（`form/melmaga.html`）

**場所**: `/Users/administrator/Desktop/DEV/melmaga-kanri/form/melmaga.html`  
**用途**: XServerに設置して、各部署がブラウザで原稿を入力→テキストファイルをダウンロード→XServerへ提出

**主な機能**:
- 20文字自動改行（URLは改行しない）
- 段落先頭に全角スペース自動挿入
- Enterで改行→全角スペース挿入、Backspaceでスペースのみ削除（行は保持）
- Cmd/Ctrl+Z でUndo、Cmd/Ctrl+Shift+Z でRedo
- 全角英数字→半角変換チェック・自動修正
- 誤字脱字チェック（基本的なもの）
- 問い合わせ先記載確認チェックボックス
- 出力ファイル名: `YYYYMMDD_HHMMSS_部署名.txt`

---

## 4. ディレクトリ構成

```
melmaga-kanri/          ← Gitリポジトリルート
│
├── app.py              ← Flaskアプリ本体（全ルート・ロジック）
├── requirements.txt    ← flask>=3.0.0
├── start.sh            ← 起動スクリプト（./start.sh で起動+ブラウザ自動オープン）
├── .gitignore
├── README.md           ← 簡易説明
├── HANDOVER.md         ← このファイル（引き継ぎ・詳細仕様）
│
├── templates/          ← Jinja2テンプレート（Flask）
│   ├── base.html           ナビバー・フラッシュメッセージ共通
│   ├── dashboard.html      ダッシュボード
│   ├── cycle_new.html      新規号作成（スケジュールプレビュー付き）
│   ├── cycle_detail.html   号詳細（タブ: スケジュール/メール/原稿/メモ）
│   ├── email_compose.html  メール作成・コピー画面
│   └── settings.html       設定・テンプレート編集
│
├── static/
│   └── style.css       ← カスタムCSS（Bootstrap 5ベース）
│
├── data/               ← 実行時データ（.gitignore対象・コミットしない）
│   ├── cycles.json         号ごとの管理データ（自動生成）
│   ├── config.json         設定（送信者名・URL等）（自動生成）
│   └── email_templates.json メールテンプレート（カスタマイズ後に生成）
│
└── form/
    └── melmaga.html    ← 原稿入力フォーム（XServerに設置するHTML単体）
```

---

## 5. セットアップ手順（新しいPCや新担当者向け）

### 前提条件
- Python 3.9以上
- Gitインストール済み
- GitHubアカウント: `kim777fk-max`

### 手順

```bash
# 1. リポジトリをクローン
git clone https://github.com/kim777fk-max/mailmaga.git melmaga-kanri
cd melmaga-kanri

# 2. Flaskインストール
pip3 install flask

# 3. 起動
python3 app.py
# または
./start.sh

# 4. ブラウザで開く
open http://localhost:5001
```

### 初回起動後の設定
1. ブラウザで http://localhost:5001/settings を開く
2. 送信者名・メールアドレス・サーバーURLを入力して保存
3. `/cycle/new` から最初の号を作成

---

## 6. app.py の主要ロジック解説

### スケジュール自動計算 (`calc_schedule`)

配信月（例: 3月）を入力すると以下を自動計算:

```
前月25日 → ①スケジュール案内
前月26日 → ②原稿依頼
配信月6日 → ④リマインド
配信月7日 → ⑤締切
配信月8日 → 広報部内確認依頼
配信月10日 → 広報部内確認〆切
配信月11日 → テスト配信
配信月13日 → テスト確認〆切
配信月15日 → ⑨発行
```

### メールテンプレート変数

テンプレート内で使用できる変数:

| 変数 | 内容 |
|---|---|
| `{vol}` | Vol番号（例: 31） |
| `{delivery_year}` | 配信年（例: 2026） |
| `{delivery_month}` | 配信月（例: 3） |
| `{deadline}` | 原稿締切日 |
| `{publish}` | 発行日 |
| `{test_distribution}` | テスト配信日 |
| `{test_deadline}` | テスト確認〆切日 |
| `{server_url}` | XServerのURL |
| `{contact_email}` | 問い合わせメール |
| `{sender_name}` | 送信者名 |
| `{sender_email}` | 送信者メールアドレス |

### 原稿スキャン (`scan_submissions`)

- フォルダ内の `.txt`・`.docx`・`.doc` を自動検出
- ファイル名のパターンから部署名を抽出:
  - `.txt`: `YYYYMMDD_HHMMSS_部署名.txt`（melmaga.html出力形式）
  - `.docx`: `テンプレート名_（部署名）.docx`（旧Wordファイル形式）

---

## 7. データの流れ

```
[各部署]
  ↓ melmaga.html で原稿入力
  ↓ YYYYMMDD_HHMMSS_部署名.txt をダウンロード
  ↓ XServerの「原稿提出」フォルダに手動アップロード

[広報部]
  ↓ XServerから原稿フォルダを手動ダウンロード（ローカルに保存）
  ↓ 統合管理ツール（app.py）でフォルダパスを設定
  ↓ 提出状況を一覧で確認
  ↓ メールテンプレートをコピーしてメール送信
  ↓ ステップを「完了」にチェック
```

---

## 8. 今後の開発ロードマップ

### Phase 2（次のステップ）: メルマガ組版ツール
- 提出された原稿テキストをドラッグ＆ドロップで並び替え
- 部署ごとのヘッダー・区切り線を自動挿入
- 最終メルマガテキストを一括出力

**出力形式（サンプル）**:
```
━━━━━━━━━━━━━━━━━━━━
【会長挨拶】
━━━━━━━━━━━━━━━━━━━━
　（本文）

━━━━━━━━━━━━━━━━━━━━
【広報部】
━━━━━━━━━━━━━━━━━━━━
　（本文）
```

### Phase 3（自動化）: n8n（Elestio）連携
- n8nはElestio上で稼働済み（ブログ生成等ですでに使用中）
- スケジュールトリガーでメール自動送信
- 対象: ①スケジュール案内、②原稿依頼、④リマインド、⑤締切メール
- app.pyにWebhookエンドポイントを追加 → n8nから叩く

**n8nフロー案**:
```
Schedule Trigger（偶数月25日）
  → HTTP Request → /api/trigger/schedule_mail
  → Gmail Node → メール送信
```

### Phase 4（AI活用）: 原稿チェック自動化
- OpenAI API を使った誤字・表記ゆれチェック
- ホモフォン（同音異義語）チェック
- 20文字改行・段落スペースの自動補正

---

## 9. 部署一覧（melmaga.htmlの部署名セレクタ）

```
会長挨拶 / 板診塾 / 副会長 / 理事長 /
研究部 / セミナー部 / 広報部 /
板橋区簡易型BCP策定支援事業 / プロジェクト / その他
```

---

## 10. 注意事項・既知の制約

| 項目 | 内容 |
|---|---|
| サーバー環境 | XServerは静的ファイルサーバー（PHP/Python不可）→ melmaga.htmlは純クライアントサイド |
| データ保存 | cycles.json等はローカルのみ。`.gitignore`対象のため他PCへの引き継ぎは手動コピーが必要 |
| メール送信 | 現在は手動（テンプレートコピー→メールソフトで送信）。Phase 3でn8n自動送信に移行予定 |
| 認証 | ツールにパスワード認証なし。社内ネットワーク前提のローカルツール |
| n8n | Elestio上に稼働中。接続情報は別途管理 |

---

## 11. 連絡先・管理情報

| 項目 | 内容 |
|---|---|
| 問い合わせメール | mmp@rmc-itabashi.jp |
| GitHubリポジトリ | https://github.com/kim777fk-max/mailmaga |
| **原稿フォーム（公開URL）** | **https://kim777fk-max.github.io/mailmaga/form/melmaga.html** |
| ローカルパス | `/Users/administrator/Desktop/DEV/melmaga-kanri/` |
| 原稿提出サーバー | https://drive.rmc-itabashi.jp/index.php/s/5rX5tfHQep43eZr |

## 12. 原稿フォームのホスティングについて

### 公開URL
```
https://kim777fk-max.github.io/mailmaga/form/melmaga.html
```

GitHub Pages（無料）で公開しています。コードを `git push` すると自動で反映されます（数分かかる場合あり）。

### なぜXServer（Nextcloud）ではダメか

XServer/Nextcloudでは以下の理由でJavaScriptが正しく動作しません：

- Nextcloudはファイルを独自のビューアで表示する
- セキュリティポリシー（CSP）でインラインスクリプトをブロックする
- HTMLファイルをWebページとして「実行」するのではなく「プレビュー」する

→ **原稿フォームは必ずGitHub Pages URLで案内すること**

### GitHub Pages 更新方法
```bash
cd /Users/administrator/Desktop/DEV/melmaga-kanri
# melmaga.html を編集後
git add form/melmaga.html
git commit -m "フォーム更新"
git push
# 数分後に https://kim777fk-max.github.io/mailmaga/form/melmaga.html に反映
```
