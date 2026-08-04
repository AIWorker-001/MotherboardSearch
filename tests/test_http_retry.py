from src.motherboard_search import build_http_session


def test_http_session_has_retry_policy():
    session = build_http_session(retries=3)
    adapter = session.get_adapter("https://example.com")
    assert adapter.max_retries.total == 3
    assert 429 in adapter.max_retries.status_forcelist
    assert adapter.max_retries.respect_retry_after_header
    session.close()
