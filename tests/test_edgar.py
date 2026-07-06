from signal_to_ticket.edgar import _strip_html


def test_strips_tags():
    html = "<html><body><p>Revenue was <b>$35.1 billion</b></p></body></html>"
    assert _strip_html(html) == "Revenue was $35.1 billion"


def test_strips_script_and_style_blocks():
    html = "<style>.a{color:red}</style><script>alert(1)</script><p>Item 1.01 Disclosure text</p>"
    text = _strip_html(html)
    assert "color:red" not in text
    assert "alert" not in text
    assert "Disclosure text" in text


def test_decodes_common_entities():
    html = "<p>Q3&nbsp;revenue &amp; margins &#8211; record highs</p>"
    text = _strip_html(html)
    assert "Q3 revenue & margins - record highs" in text


def test_skips_cover_page_to_first_item():
    cover = "UNITED STATES SECURITIES AND EXCHANGE COMMISSION Washington, D.C. FORM 8-K " * 10
    html = f"<p>{cover}</p><p>Item 2.02 Results of Operations. Revenue grew 94%.</p>"
    text = _strip_html(html)
    assert text.startswith("Item 2.02")


def test_keeps_short_documents_intact():
    html = "<p>Item 2.02 appears early here, keep everything.</p>"
    text = _strip_html(html)
    assert "keep everything" in text
