# boat-onepick-app

三連複1点・的中率重視のボートレース予想Webアプリ。

今日の全レースを自動スキャンし、三連複1点で的中確率が高そうなレースだけを表示する。

## 技術構成

| 役割 | 技術 |
|---|---|
| フロントエンド | Next.js 14 (App Router) + Tailwind CSS |
| DB | Supabase |
| スクレイパー | Python 3.11 + requests + BeautifulSoup4 |
| 自動実行 | GitHub Actions |
| 公開 | Vercel |

---

## セットアップ

### 1. Supabase テーブル作成

Supabase のSQLエディタで `supabase/schema.sql` を実行する。

### 2. 環境変数

`.env.example` をコピーして `.env.local` を作成し、Supabase の URL とキーを設定する。

```bash
cp .env.example .env.local
```

### 3. フロントエンド起動

```bash
npm install
npm run dev
```

### 4. Pythonスクレイパー

```bash
cd scraper
pip install -r requirements.txt
cp ../.env.example .env
# .env に SUPABASE_URL と SUPABASE_SERVICE_ROLE_KEY を設定

# 朝スキャン (手動実行)
python main.py morning

# 直前スキャン
python main.py pre_race

# 結果スキャン
python main.py result
```

### 5. GitHub Actions シークレット設定

GitHub リポジトリの Settings → Secrets に以下を登録する:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

---

## 処理フロー

```
毎朝 7:00    → morning_scan    : 出走表取得 + 仮スコア計算
5分おき      → pre_race_scan   : 締切10分前レースの展示取得 + 最終判定
毎晩 23:00   → result_scan     : 結果取得 + 的中判定
```

---

## スコア設計

| フェーズ | 項目 | 最大 |
|---|---|---|
| 朝 | 選手力 | 20 |
| 朝 | モーター | 15 |
| 朝 | 枠・コース | 10 |
| 朝 | スタート力 | 10 |
| 朝 | 当地相性 | 10 |
| 朝 | 荒れにくさ | 5 |
| 直前 | 展示タイム | 10 |
| 直前 | 展示ST | 5 |
| 直前 | 周回展示 | 5 |
| 直前 | 進入安定 | 5 |
| 直前 | 風・波 | 5 |
| **合計** | | **100** |

---

## 判定基準

| ランク | 信頼度 | 3番手と4番手の差 | 判定 |
|---|---|---|---|
| S | 92点以上 | 10点以上 | 買い |
| A | 88〜91点 | 7点以上 | 候補 |
| B | 80〜87点 | — | 見送り寄り |
| C | 79点以下 | — | 非表示 |

---

## 注意事項

- このアプリは必勝を保証するものではない。あくまで三連複1点候補の機械的な抽出・検証ツール。
- データ取得元の利用規約を確認し、過度なアクセスを避けること。
- スクレイパーのアクセス間隔は `REQUEST_INTERVAL = 2.0秒` を下回らないこと。
