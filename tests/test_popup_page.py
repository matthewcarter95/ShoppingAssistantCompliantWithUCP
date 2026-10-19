"""Tests for the page the merchant OAuth callback returns inside the popup."""
import json
import re

import pytest

from src.chatbot.services.popup_page import (
    ERROR_CODES, fallback_url, frontend_origin, render_callback_page)

FRONTEND = "https://main.d7stwkdmkar4g.amplifyapp.com"


def embedded(html, name):
    """The JSON value assigned to `name` in the page's inline script."""
    match = re.search(rf"var {name} = (.+?);\n", html)
    assert match, name
    return json.loads(match.group(1))


def test_success_reports_to_the_opener_and_names_the_session():
    html = render_callback_page(FRONTEND, True, session_id="abc-123")
    assert embedded(html, "payload") == {"type": "merchant-auth", "status": "success", "session_id": "abc-123"}
    assert "window.opener.postMessage(payload, chatOrigin)" in html
    assert "window.close()" in html


def test_message_goes_to_the_chat_origin_only_never_a_wildcard():
    html = render_callback_page(FRONTEND, True, session_id="s")
    assert embedded(html, "chatOrigin") == FRONTEND
    assert 'postMessage(payload, "*")' not in html and "postMessage(payload, '*')" not in html


def test_origin_ignores_any_path_on_the_configured_frontend_url():
    assert frontend_origin("https://example.com/app/index.html?x=1") == "https://example.com"
    assert frontend_origin("http://localhost:3000/") == "http://localhost:3000"


def test_without_an_opener_the_tab_is_sent_back_to_the_chat():
    html = render_callback_page(FRONTEND, True, session_id="s1")
    assert embedded(html, "fallback") == f"{FRONTEND}?merchant_auth=success&session_id=s1"
    assert "window.location.replace(fallback)" in html


def test_error_page_reports_a_fixed_code_not_free_text():
    html = render_callback_page(FRONTEND, False, error_code="token_exchange_failed")
    assert embedded(html, "payload") == {"type": "merchant-auth", "status": "error", "error": "token_exchange_failed"}
    assert embedded(html, "fallback") == f"{FRONTEND}?error=token_exchange_failed"


def test_unknown_error_codes_are_replaced_so_arbitrary_text_cannot_get_through():
    attack = '"><script>alert(1)</script>'
    html = render_callback_page(FRONTEND, False, error_code=attack)
    assert attack not in html and "alert(1)" not in html
    assert embedded(html, "payload")["error"] == "unknown"
    assert fallback_url(FRONTEND, False, None, attack) == f"{FRONTEND}?error=unknown"


@pytest.mark.parametrize("code", sorted(ERROR_CODES))
def test_every_known_error_code_round_trips(code):
    assert embedded(render_callback_page(FRONTEND, False, error_code=code), "payload")["error"] == code


def test_a_session_id_cannot_break_out_of_the_script():
    hostile = '</script><img src=x onerror=alert(1)>'
    html = render_callback_page(FRONTEND, True, session_id=hostile)
    assert hostile not in html
    assert html.count("</script>") == 1                     # only the page's own closing tag
    assert embedded(html, "payload")["session_id"] == hostile   # decodes back to the original value


def test_session_id_is_url_encoded_in_the_fallback():
    assert fallback_url(FRONTEND, True, "a b&c=d", None) == f"{FRONTEND}?merchant_auth=success&session_id=a+b%26c%3Dd"


def test_page_does_not_leak_the_referrer_and_shows_a_human_message():
    ok = render_callback_page(FRONTEND, True, session_id="s")
    bad = render_callback_page(FRONTEND, False, error_code="invalid_state")
    assert 'name="referrer" content="no-referrer"' in ok
    assert "Merchant account connected" in ok and "Couldn't connect" in bad
