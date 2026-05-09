-- entries テーブルにチルト角カラムを追加
-- チルト角は fetch_exhibition.py で取得し、scoring.py の pre_race_score で使用
-- 値域: -3.0 〜 +3.0 (NUMERIC(4,2) で十分)
ALTER TABLE entries ADD COLUMN IF NOT EXISTS tilt NUMERIC(4, 2);

COMMENT ON COLUMN entries.tilt IS 'チルト角 (-3.0〜+3.0)。正値=攻めセット、負値=守りセット。fetch_exhibition.py で取得。';
