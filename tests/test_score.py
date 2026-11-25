from trend_scout import score, hooks


def test_velocity_prefers_newer():
    assert score.velocity(100, 10, 0, 2) > score.velocity(100, 10, 0, 20)


def test_velocity_weights():
    assert score.velocity(0, 0, 1, 1) == 3 and score.velocity(0, 1, 0, 1) == 2 and score.velocity(1, 0, 0, 1) == 1


def test_outlier_unknown_is_none():
    assert score.outlier_ratio(1000, None) is None and score.outlier_ratio(1000, 100) == 10


def test_intent():
    cs = ["how do you train for this?", "nice", "@sam we need this", "where did you get that jacket", "cool"]
    assert score.intent_ratio(cs) == 0.6 and score.intent_ratio([]) is None


def test_median_outliers():
    assert score.median_outliers([10, 12, 11, 50, 9]) == [3] and score.median_outliers([1, 2]) == []


def test_rank_norm():
    xs = [{"v": 1}, {"v": 5}, {"v": 3}]
    score.rank_norm(xs, "v")
    assert [x["rank_score"] for x in xs] == [0.333, 1.0, 0.667]


def test_youtube_id():
    assert hooks.youtube_id("https://www.youtube.com/shorts/abcdefghijk") == "abcdefghijk"
    assert hooks.youtube_id("https://youtu.be/abcdefghijk?t=3") == "abcdefghijk"
    assert hooks.youtube_id("https://www.tiktok.com/@x/video/123") is None


def test_hook_words_cut_at_3s():
    assert hooks._words([(0, "you are training"), (1.5, "wrong for sailing"), (4.0, "here is why")]) == "you are training wrong for sailing"


def test_ig_budget(tmp_path, monkeypatch):
    from trend_scout import store
    monkeypatch.setattr(store, "DB", tmp_path / "t.db")
    for i in range(29):
        store.ig_tag_used(f"t{i}")
    ok, refused = store.ig_tag_budget(["t1", "new1", "new2"])
    assert ok == ["t1", "new1"] and refused == ["new2"]
