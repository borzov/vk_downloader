from vkdl.quality import extract_quality_urls, guess_extension

STYLE = (
    "background-image:url(https://sun9.userapi.com/impf/abc/photo.jpg"
    "?quality=96&as=32x24,160x120,1280x960,2560x1920&from=bu&cs=240x0)"
)


def test_returns_urls_highest_first():
    urls = extract_quality_urls(STYLE)
    assert urls, "must produce at least one candidate"
    # the `as` size list is identical in every URL; ranking lives in `cs`
    assert "cs=2560x0" in urls[0]
    big = next(i for i, u in enumerate(urls) if "cs=2560x0" in u)
    small = next(i for i, u in enumerate(urls) if "cs=160x0" in u)
    assert big < small


def test_no_paramless_base_first_candidate():
    urls = extract_quality_urls(STYLE)
    assert "?" in urls[0], "first candidate must carry sizing params"


def test_raw_url_without_css_wrapper():
    raw = "https://sun9.userapi.com/impf/x/p.jpg?as=100x100,800x600&cs=100x0"
    urls = extract_quality_urls(raw)
    assert any("800" in u for u in urls)


def test_no_match_returns_empty():
    assert extract_quality_urls("background:none") == []


def test_guess_extension():
    assert guess_extension("https://x/p.png?as=1") == ".png"
    assert guess_extension("https://x/p.webp") == ".webp"
    assert guess_extension("https://x/p.jpg?q=1") == ".jpg"
    assert guess_extension("https://x/p") == ".jpg"
