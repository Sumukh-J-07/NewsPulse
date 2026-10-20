from newspulse.processing.sentiment import score_headline

def test_sentiment_positive_and_negative():
    pos = score_headline("Alfa Systems announces strong profit growth and dividend boost")
    assert pos.label == "positive"
    assert pos.score > 0
    assert "profit" in pos.positive_hits

    neg = score_headline("Brio Energy warns of quarterly loss amid rising debt headwinds")
    assert neg.label == "negative"
    assert neg.score < 0
    assert "loss" in neg.negative_hits

def test_sentiment_negation():
    negated = score_headline("Company did not miss estimates despite headwinds")
    assert any("negated:" in f for f in negated.flags)

def test_sentiment_empty_and_neutral():
    assert score_headline(None) is None
    assert score_headline("") is None

    neutral = score_headline("Company schedules annual general meeting for shareholders")
    assert neutral.label == "neutral"
    assert neutral.score == 0.0
