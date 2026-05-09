-- entries テーブルに F(フライング)回数・L(出遅れ)回数カラムを追加
-- fetch_entries.py で取得済みだが DB に保存していなかったため、
-- pre_race_scan で EntryData を再構築する際にゼロとして扱われていた。
-- これらは scoring.py の _st_score() でペナルティとして使用される。
ALTER TABLE entries ADD COLUMN IF NOT EXISTS f_count SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE entries ADD COLUMN IF NOT EXISTS l_count SMALLINT NOT NULL DEFAULT 0;

COMMENT ON COLUMN entries.f_count IS 'フライング回数 (F持ち選手は ST スコアが -3×f_count 点)';
COMMENT ON COLUMN entries.l_count IS '出遅れ回数 (L持ち選手は ST スコアが -2×l_count 点)';
