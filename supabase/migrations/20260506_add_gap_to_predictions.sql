-- predictions テーブルに gap カラムを追加
-- gap = 3位スコア - 4位スコア（scoring.py の gap_between_3rd_4th）
ALTER TABLE predictions
  ADD COLUMN IF NOT EXISTS gap NUMERIC(6, 2);

-- 既存データのうち reason テキストに gap=X.X が含まれるものをバックフィル
UPDATE predictions
SET gap = CAST(
  (regexp_match(reason, 'gap=([0-9]+\.?[0-9]*)'))[1]
  AS NUMERIC(6, 2)
)
WHERE gap IS NULL
  AND reason IS NOT NULL
  AND reason ~ 'gap=[0-9]';
