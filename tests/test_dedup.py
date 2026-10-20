from newspulse.processing.dedup import normalize_url, normalize_headline, DedupIndex
from datetime import datetime, timezone

UTC = timezone.utc

def test_normalize_url():
    url = "https://www.marketwatch.com/story/test-article/?utm_source=twitter&utm_medium=social&ref=123"
    norm = normalize_url(url)
    assert norm == "https://marketwatch.com/story/test-article"
    assert "utm_" not in norm

def test_dedup_index():
    idx = DedupIndex()
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    
    # 1. Source ID dedup
    dup1, reason1 = idx.classify(1, "Reuters", "id-123", "https://reuters.com/1", "Strong quarterly profits", now)
    assert dup1 is None
    
    dup2, reason2 = idx.classify(2, "Reuters", "id-123", "https://reuters.com/1-dup", "Different headline", now)
    assert dup2 == 1
    assert reason2 == "source_id"

    # 2. Normalized URL dedup
    dup3, reason3 = idx.classify(3, "Bloomberg", None, "https://reuters.com/1", "Third headline", now)
    assert dup3 == 1
    assert reason3 == "normalized_url"
