"""The page the merchant OAuth callback returns.

The callback runs in the popup the chat opened. This page tells the chat
window how it went, then closes itself. If there is no chat window to tell
(the shopper opened the link in a plain tab, or the browser cut the link to
the opener), it sends the tab back to the chat the way the old redirect flow
did, so that path keeps working.

Nothing from the request is echoed into the page. The only values embedded are
ones the server computed: the frontend origin, the session id of a session it
just updated, and a fixed error code.
"""
import json
from typing import Optional
from urllib.parse import urlencode, urlsplit

MESSAGE_TYPE = "merchant-auth"

# Error codes the page may report. Anything else becomes "unknown".
ERROR_CODES = {
    "invalid_state",
    "session_not_found",
    "missing_code_verifier",
    "token_exchange_failed",
}


def frontend_origin(frontend_url: str) -> str:
    """scheme://host[:port] of the chat page, the only origin allowed to receive the result."""
    parts = urlsplit(frontend_url)
    return f"{parts.scheme}://{parts.netloc}"


def fallback_url(frontend_url: str, success: bool, session_id: Optional[str], error_code: Optional[str]) -> str:
    """Where a plain tab (no opener) is sent: the chat page, with the outcome in the query."""
    base = frontend_url.rstrip("/")
    if success:
        query = {"merchant_auth": "success", "session_id": session_id or ""}
    else:
        query = {"error": error_code if error_code in ERROR_CODES else "unknown"}
    return f"{base}?{urlencode(query)}"


def _js(value) -> str:
    """JSON for embedding in an inline <script>: no </script> or HTML comment breakouts."""
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def render_callback_page(
    frontend_url: str,
    success: bool,
    session_id: Optional[str] = None,
    error_code: Optional[str] = None,
) -> str:
    """HTML for the OAuth callback response."""
    code = error_code if error_code in ERROR_CODES else "unknown"
    payload = {"type": MESSAGE_TYPE, "status": "success" if success else "error"}
    if success:
        payload["session_id"] = session_id
    else:
        payload["error"] = code

    heading = "Merchant account connected" if success else "Couldn't connect"
    detail = (
        "You can close this window and go back to the chat."
        if success
        else "Close this window and try again from the chat."
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>{heading}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; margin: 0; background: #f6f7fb; color: #333; }}
  main {{ text-align: center; padding: 24px; }}
  h1 {{ font-size: 1.2rem; margin: 0 0 8px; }}
  p {{ margin: 0; color: #666; }}
</style>
</head>
<body>
<main>
  <h1>{heading}</h1>
  <p>{detail}</p>
</main>
<script>
(function () {{
  var payload = {_js(payload)};
  var chatOrigin = {_js(frontend_origin(frontend_url))};
  var fallback = {_js(fallback_url(frontend_url, success, session_id, error_code))};

  // Tell the chat window, but only the chat's own origin.
  if (window.opener && !window.opener.closed) {{
    try {{
      window.opener.postMessage(payload, chatOrigin);
      setTimeout(function () {{ window.close(); }}, 400);
      return;
    }} catch (e) {{ /* fall through to the redirect */ }}
  }}
  // No chat window to report to: go back to the chat in this tab.
  window.location.replace(fallback);
}})();
</script>
</body>
</html>
"""
