from .test_production_tools import tool


def test_cloudflare_review_returns_only_requested_routing_fields():
    review = tool("staging/review_cloudflare_route.py")
    value = review.summarize({"ingress": [
        {"hostname": "watch.lgw323.com", "service": "http://localhost:8000", "secret": "private"},
        {"hostname": "private.example", "service": "http://127.0.0.1:9010"},
        {"service": "http_status:404"}], "token": "private"})
    assert value["origin_targets"] == ["http://localhost:8000"]
    assert value["internal_port_route_count"] == 1
    assert "private" not in str(value)
    assert review.summarize({"ingress": [{"hostname": review.HOST, "service": "https://user:private@localhost/"}]})["origin_targets"] == ["other_target_withheld"]
