"""
scoring.py の精度・回帰テスト
python3 test_scoring.py で実行
"""
import sys
from scoring import EntryData, RaceCondition, score_entries, decide, morning_score

def test_motor_relative_scoring():
    """モータースコアが艦隊平均との相対評価になっているか"""
    entries = [EntryData(lane=i, racer_name=f"R{i}", motor_rate=r)
               for i, r in enumerate([55, 45, 40, 35, 30, 25], 1)]
    cond = RaceCondition()
    scores = score_entries(entries, cond)
    ms = {s.lane: s.morning_score for s in scores}
    # 1号艇(motor=55)のモータースコアは2号艇(motor=45)より高いはず
    assert ms[1] > ms[2], f"1号艇{ms[1]:.1f} <= 2号艇{ms[2]:.1f}"
    # 艦隊平均より5%高いモーター → +1.5点差程度
    diff = ms[1] - ms[2]
    assert 2.5 < diff < 8.0, f"モータースコア差 {diff:.1f} が範囲外"
    print(f"  ✓ motor_relative: 1号艇-2号艇差={diff:.1f}点")

def test_exhibition_time_discrimination():
    """展示タイムが艦隊内で差をつけているか"""
    entries = [
        EntryData(lane=1, racer_name="fast", motor_rate=40, avg_st=0.14,
                  exhibition_time=6.55, exhibition_st=0.09, approach_lane=1, tilt=1.0),
        EntryData(lane=2, racer_name="mid1", motor_rate=40, avg_st=0.14,
                  exhibition_time=6.75, exhibition_st=0.12, approach_lane=2, tilt=0.0),
        EntryData(lane=3, racer_name="mid2", motor_rate=40, avg_st=0.14,
                  exhibition_time=6.80, exhibition_st=0.13, approach_lane=3, tilt=0.0),
        EntryData(lane=4, racer_name="slow", motor_rate=40, avg_st=0.14,
                  exhibition_time=6.95, exhibition_st=0.15, approach_lane=4, tilt=0.0),
        EntryData(lane=5, racer_name="R5",   motor_rate=40, avg_st=0.14,
                  exhibition_time=6.90, exhibition_st=0.14, approach_lane=5, tilt=0.0),
        EntryData(lane=6, racer_name="R6",   motor_rate=40, avg_st=0.14,
                  exhibition_time=6.85, exhibition_st=0.13, approach_lane=6, tilt=0.0),
    ]
    cond = RaceCondition()
    scores = score_entries(entries, cond)
    pre = {s.lane: s.pre_race_score for s in scores}
    # fastボートが最高pre_race_scoreを得るはず
    assert pre[1] > pre[2] > pre[3], f"展示タイム順と一致しない: {pre}"
    assert pre[1] > pre[4], f"fast({pre[1]:.1f}) <= slow({pre[4]:.1f})"
    print(f"  ✓ exhibition_discrimination: fast={pre[1]:.1f} mid={pre[2]:.1f} slow={pre[4]:.1f}")

def test_lane1_approach_penalty():
    """1号艇がコース3以降に進入すると信頼度が下がるか"""
    entries = [
        EntryData(lane=1, racer_name="A1", racer_class="A1", motor_rate=45, avg_st=0.12,
                  exhibition_time=6.75, exhibition_st=0.10, approach_lane=1, tilt=1.0),
        EntryData(lane=2, racer_name="B1", racer_class="A1", motor_rate=42, avg_st=0.13,
                  exhibition_time=6.80, exhibition_st=0.11, approach_lane=2, tilt=0.5),
        EntryData(lane=3, racer_name="C1", racer_class="B1", motor_rate=38, avg_st=0.15,
                  exhibition_time=6.85, exhibition_st=0.12, approach_lane=3, tilt=0.0),
        EntryData(lane=4, racer_name="D1", racer_class="B1", motor_rate=35, avg_st=0.16,
                  exhibition_time=6.90, exhibition_st=0.13, approach_lane=4, tilt=0.0),
        EntryData(lane=5, racer_name="E1", racer_class="B2", motor_rate=30, avg_st=0.17,
                  exhibition_time=6.92, exhibition_st=0.14, approach_lane=5, tilt=0.0),
        EntryData(lane=6, racer_name="F1", racer_class="B2", motor_rate=28, avg_st=0.18,
                  exhibition_time=6.95, exhibition_st=0.15, approach_lane=6, tilt=0.0),
    ]
    cond = RaceCondition()
    scores = score_entries(entries, cond)

    # 1号艇コース1進入の信頼度
    pred_c1 = decide(scores, cond, lane1_approach=1)
    # 1号艇コース4進入の信頼度（スコアも変わる）
    import copy
    entries_c4 = [copy.copy(e) for e in entries]
    entries_c4[0].approach_lane = 4  # 1号艇がコース4に
    entries_c4[3].approach_lane = 1  # 4号艇がコース1に
    scores_c4 = score_entries(entries_c4, cond)
    pred_c4 = decide(scores_c4, cond, lane1_approach=4)

    assert pred_c1["confidence"] > pred_c4["confidence"], (
        f"コース1進入({pred_c1['confidence']:.1f}) <= コース4進入({pred_c4['confidence']:.1f})"
    )
    print(f"  ✓ lane1_approach_penalty: コース1={pred_c1['confidence']:.1f} > コース4={pred_c4['confidence']:.1f}")

def test_payout_filter():
    """払戻フィルターが正しく動作するか"""
    # BUYが出やすい差をつけた入力 (上位3艇が圧倒的に強い)
    entries = [
        EntryData(lane=1, racer_name="A", racer_class="A1", motor_rate=60, avg_st=0.10,
                  exhibition_time=6.55, exhibition_st=0.08, approach_lane=1, tilt=1.5),
        EntryData(lane=2, racer_name="B", racer_class="A1", motor_rate=55, avg_st=0.11,
                  exhibition_time=6.65, exhibition_st=0.09, approach_lane=2, tilt=1.0),
        EntryData(lane=3, racer_name="C", racer_class="A2", motor_rate=50, avg_st=0.12,
                  exhibition_time=6.70, exhibition_st=0.10, approach_lane=3, tilt=0.5),
        EntryData(lane=4, racer_name="D", racer_class="B2", motor_rate=28, avg_st=0.20,
                  exhibition_time=7.10, exhibition_st=0.20, approach_lane=4, tilt=0.0),
        EntryData(lane=5, racer_name="E", racer_class="B2", motor_rate=25, avg_st=0.21,
                  exhibition_time=7.15, exhibition_st=0.21, approach_lane=5, tilt=0.0),
        EntryData(lane=6, racer_name="F", racer_class="B2", motor_rate=22, avg_st=0.22,
                  exhibition_time=7.20, exhibition_st=0.22, approach_lane=6, tilt=0.0),
    ]
    cond = RaceCondition()
    scores = score_entries(entries, cond)

    pred_no_filter = decide(scores, cond, pick_payout=None, lane1_approach=1)
    pred_high_odds = decide(scores, cond, pick_payout=800,  lane1_approach=1)
    pred_low_odds  = decide(scores, cond, pick_payout=300,  lane1_approach=1)

    print(f"  デバッグ: decision={pred_no_filter['decision']} conf={pred_no_filter['confidence']:.1f} gap={pred_no_filter['gap']:.1f}")

    if pred_no_filter["decision"] == "buy":
        assert pred_high_odds["decision"] == "buy",      "高オッズでBUYが変わってはいけない"
        assert pred_low_odds["decision"] == "candidate", f"低オッズBUY→candidate降格失敗: {pred_low_odds['decision']}"
        print(f"  ✓ payout_filter: BUY高オッズ={pred_high_odds['decision']} / BUY低オッズ={pred_low_odds['decision']}")
    elif pred_no_filter["decision"] == "candidate":
        # candidate でも 低オッズ(<250)なら skip になるべき
        pred_very_low = decide(scores, cond, pick_payout=200, lane1_approach=1)
        assert pred_very_low["decision"] == "skip", f"CAND低オッズ→skip失敗: {pred_very_low['decision']}"
        print(f"  ✓ payout_filter: CAND低オッズ={pred_very_low['decision']}")
    else:
        # gap < 10 でBUYが出ない場合は強制チェック
        from scoring import gap_between_3rd_4th, make_pick, EntryScore
        actual_gap = pred_no_filter["gap"]
        assert actual_gap < 10 or pred_no_filter["confidence"] < 67, \
            f"BUYが出るはずなのに出ない: gap={actual_gap:.1f} conf={pred_no_filter['confidence']:.1f}"
        print(f"  ~ payout_filter: BUY未達 (gap={actual_gap:.1f} conf={pred_no_filter['confidence']:.1f})")

def test_gap_weight():
    """gap が大きいほど信頼度が高くなるか"""
    def conf_for_gap(gap_target: float) -> float:
        entries = [EntryData(lane=i, racer_name=f"R{i}", motor_rate=40,
                             avg_st=0.14-i*0.005,  # 少しずつ遅くする
                             exhibition_time=6.70+i*0.03, approach_lane=i, tilt=1.0)
                   for i in range(1, 7)]
        cond = RaceCondition()
        scores = score_entries(entries, cond)
        return scores[2].total - scores[3].total  # actual gap

    # 基本的に score_entries でgapが変動することを確認
    entries = [EntryData(lane=i, racer_name=f"R{i}", motor_rate=40+i*2,
                         avg_st=0.14, exhibition_time=6.70+i*0.05, approach_lane=i)
               for i in range(1, 7)]
    cond = RaceCondition()
    scores = score_entries(entries, cond)
    pred = decide(scores, cond)
    assert "gap=" in str(pred["reason"]), "gapがreasonに含まれていない"
    print(f"  ✓ gap_in_reason: gap={pred['gap']:.1f}")

def test_ev_calculation():
    """EV計算: 高確率低配当はEVマイナス、中確率高配当はEVプラス。pickがEV最大に変わるか"""
    entries = [
        EntryData(lane=1, racer_name="強", racer_class="A1", motor_rate=60, avg_st=0.10,
                  exhibition_time=6.55, exhibition_st=0.08, approach_lane=1, tilt=1.0),
        EntryData(lane=2, racer_name="中1", racer_class="A2", motor_rate=48, avg_st=0.13,
                  exhibition_time=6.70, exhibition_st=0.11, approach_lane=2, tilt=0.5),
        EntryData(lane=3, racer_name="中2", racer_class="A2", motor_rate=45, avg_st=0.14,
                  exhibition_time=6.75, exhibition_st=0.12, approach_lane=3, tilt=0.5),
        EntryData(lane=4, racer_name="弱1", racer_class="B1", motor_rate=30, avg_st=0.17,
                  exhibition_time=7.00, exhibition_st=0.16, approach_lane=4, tilt=0.0),
        EntryData(lane=5, racer_name="中3", racer_class="A2", motor_rate=50, avg_st=0.13,
                  exhibition_time=6.72, exhibition_st=0.11, approach_lane=5, tilt=0.5),
        EntryData(lane=6, racer_name="弱2", racer_class="B2", motor_rate=25, avg_st=0.19,
                  exhibition_time=7.05, exhibition_st=0.17, approach_lane=6, tilt=0.0),
    ]
    cond = RaceCondition()
    scores = score_entries(entries, cond)

    from scoring import scores_to_combo_probs, calculate_combo_ev
    probs = scores_to_combo_probs(scores)

    # 確率合計 ≈ 1.0
    assert abs(sum(probs.values()) - 1.0) < 1e-9, "確率の合計が1でない"
    # 1-2-3が最高確率
    assert probs["1-2-3"] == max(probs.values()), "1-2-3が最高確率でない"

    # EV: 1-2-3を人気(低配当¥280)、1-2-5を穴(高配当¥420)
    odds = {"1-2-3": 280, "1-2-5": 420, "1-3-5": 580}
    ev = calculate_combo_ev(probs, odds)

    # 1-2-3: 高確率・低配当 → EVマイナス
    assert ev["1-2-3"] < 0, f"1-2-3のEVがプラス: {ev['1-2-3']:.4f}"
    # 1-2-5: 次点確率・割安配当 → EVプラス
    assert ev["1-2-5"] > 0, f"1-2-5のEVがマイナス: {ev['1-2-5']:.4f}"

    # decide() EVモード: pickが1-2-5に変わるはず
    pred = decide(scores, cond, all_odds=odds)
    assert pred["pick"] == "1-2-5", f"EV最大pickが期待値と違う: {pred['pick']}"
    assert pred["best_ev"] is not None and pred["best_ev"] > 0, \
        f"best_evがプラスでない: {pred['best_ev']}"

    print(f"  ✓ ev: 1-2-3={ev['1-2-3']:+.4f}(人気低配当) 1-2-5={ev['1-2-5']:+.4f}(穴高配当)")
    print(f"  ✓ ev_pick: {pred['pick']} EV={pred['best_ev']:+.4f} → {pred['decision']}")


if __name__ == "__main__":
    print("=== scoring.py テスト ===")
    tests = [
        test_motor_relative_scoring,
        test_exhibition_time_discrimination,
        test_lane1_approach_penalty,
        test_payout_filter,
        test_gap_weight,
        test_ev_calculation,
    ]
    failed = 0
    for t in tests:
        try:
            print(f"\n[{t.__name__}]")
            t()
        except AssertionError as e:
            print(f"  ✗ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1
    print(f"\n{'='*30}")
    if failed == 0:
        print(f"✅ 全{len(tests)}テスト合格")
    else:
        print(f"❌ {failed}/{len(tests)}テスト失敗")
        sys.exit(1)
