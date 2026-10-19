import pytest


@pytest.mark.parametrize("path", ["/api/v1/portfolio/analytics/brinson?book=__none__",
                                  "/api/v1/portfolio/analytics/tracking-error?book=__none__",
                                  "/api/v1/portfolio/analytics/liquidity?book=__none__",
                                  "/api/v1/portfolio/lots?book=__none__"])
def test_endpoints_answer_with_structured_absence_for_an_empty_book(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert r.json()["available"] is False
