"""Small local-only Chrome CDP smoke helper for shadow-readiness remediation.

This is test/debug tooling, not a runtime dependency. It records only bounded
UI/network/error metadata; it never writes query, answer, evidence, or DOM
content to its result file.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from websockets.sync.client import connect

_EVENT_LOG: list[dict[str, Any]] = []


def http_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def cdp_call(ws: Any, counter: list[int], method: str, params: dict[str, Any] | None = None) -> Any:
    counter[0] += 1
    message_id = counter[0]
    ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        message = json.loads(ws.recv(timeout=max(0.2, deadline - time.monotonic())))
        if message.get("id") != message_id:
            _EVENT_LOG.append(message)
            continue
        if "error" in message:
            raise RuntimeError(f"CDP {method} failed")
        return message.get("result", {})
    raise TimeoutError(f"CDP {method} timed out")


def evaluate(ws: Any, counter: list[int], expression: str) -> Any:
    result = cdp_call(
        ws,
        counter,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    return result.get("result", {}).get("value")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    args = parser.parse_args()

    targets = http_json(f"{args.cdp}/json/list")
    pages = [item for item in targets if item.get("type") == "page"]
    if not pages:
        browser = http_json(f"{args.cdp}/json/version")
        browser_socket = browser.get("webSocketDebuggerUrl")
        if not browser_socket:
            raise RuntimeError("no page target and no browser websocket")
        with connect(browser_socket, open_timeout=10, close_timeout=3) as browser_ws:
            cdp_call(
                browser_ws,
                [0],
                "Target.createTarget",
                {"url": "about:blank"},
            )
        targets = http_json(f"{args.cdp}/json/list")
        pages = [item for item in targets if item.get("type") == "page"]
    if not pages:
        raise RuntimeError("no page target available after target creation")
    target = next(
        (item for item in pages if item.get("webSocketDebuggerUrl")),
        pages[0],
    )
    websocket_url = target.get("webSocketDebuggerUrl")
    if not websocket_url:
        raise RuntimeError("page target has no webSocketDebuggerUrl")

    counter = [0]
    network: list[dict[str, Any]] = []
    console_errors = 0
    resource_failures = 0
    with connect(websocket_url, open_timeout=10, close_timeout=3) as ws:
        cdp_call(ws, counter, "Page.enable")
        cdp_call(ws, counter, "Runtime.enable")
        cdp_call(ws, counter, "Log.enable")
        cdp_call(ws, counter, "Network.enable")
        cdp_call(ws, counter, "Page.navigate", {"url": args.url})
        time.sleep(1.5)

        initial = evaluate(
            ws,
            counter,
            """({url: location.href, title: document.title,
                signIn: location.pathname === '/sign-in',
                input: !!document.querySelector('input[placeholder=\"Ask anything…\"]')})""",
        ) or {}
        if initial.get("signIn"):
            clicked = evaluate(
                ws,
                counter,
                """(() => { const b = [...document.querySelectorAll('button')].find(x =>
                    /tenant-a.*user/i.test(x.innerText));
                    if (b) { b.click(); return true; } return false; })()""",
            )
            if not clicked:
                raise RuntimeError("development sign-in button not found")
            time.sleep(1.5)
            cdp_call(ws, counter, "Page.navigate", {"url": args.url})
            time.sleep(1.5)

        page = evaluate(
            ws,
            counter,
            """({url: location.href, title: document.title,
                input: !!document.querySelector('input[placeholder=\"Ask anything…\"]'),
                bodyLength: document.body?.innerText?.length || 0})""",
        ) or {}
        if not page.get("input"):
            raise RuntimeError("chat input not found")
        initial_body_length = int(page.get("bodyLength", 0))
        question_json = json.dumps(args.question)
        filled = evaluate(
            ws,
            counter,
            f"""(() => {{
                const el = document.querySelector(
                    'input[placeholder=\"Ask anything…\"]');
                if (!el) return false;
                const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value').set;
                setter.call(el, {question_json});
                el.dispatchEvent(new Event('input', {{bubbles:true}}));
                el.dispatchEvent(new Event('change', {{bubbles:true}}));
                return true; }})()""",
        )
        clicked = evaluate(
            ws,
            counter,
            """(() => { const b = document.querySelector('button[aria-label="Ask"]');
                if (!b || b.disabled) return false; b.click(); return true; })()""",
        )
        if not filled or not clicked:
            raise RuntimeError("chat input or Ask action failed")

        deadline = time.monotonic() + 60
        rendered = False
        while time.monotonic() < deadline:
            try:
                message = json.loads(ws.recv(timeout=1))
            except TimeoutError:
                message = {}
            method = message.get("method")
            params = message.get("params", {})
            if method == "Network.responseReceived":
                response = params.get("response", {})
                url = response.get("url", "")
                if "/chat" in url:
                    network.append(
                        {
                            "method": response.get("requestHeaders", {}).get(":method", "POST"),
                            "path": urllib.parse.urlparse(url).path,
                            "status": response.get("status"),
                        }
                    )
            elif method == "Runtime.consoleAPICalled":
                if params.get("type") in {"error", "assert"}:
                    console_errors += 1
            elif method == "Log.entryAdded":
                if params.get("entry", {}).get("level") == "error":
                    console_errors += 1
            elif method == "Network.loadingFailed":
                resource_failures += 1
            status = evaluate(
                ws,
                counter,
                """(() => { const body = document.body?.innerText || '';
                    return {url: location.href, title: document.title,
                      bodyLength: body.length,
                      streaming: !!document.querySelector('button[aria-label="Cancel"]'),
                      citationSignals: (body.match(
                        /Citation integrity verified|Citation validation failed/g) || [])
                        .length
                    }; })()""",
            ) or {}
            if (
                int(status.get("bodyLength", 0)) > initial_body_length
                and not status.get("streaming")
            ):
                rendered = True
                break

        for message in _EVENT_LOG:
            if message.get("method") != "Network.responseReceived":
                continue
            response = message.get("params", {}).get("response", {})
            url = response.get("url", "")
            if "/chat" in url:
                network.append(
                    {
                        "method": response.get("requestHeaders", {}).get(":method", "POST"),
                        "path": urllib.parse.urlparse(url).path,
                        "status": response.get("status"),
                    }
                )
        deduped_network = []
        seen_network: set[tuple[str, str, int | None]] = set()
        for item in network:
            key = (item["method"], item["path"], item["status"])
            if key not in seen_network:
                seen_network.add(key)
                deduped_network.append(item)

        result = {
            "cdp_target_type": target.get("type"),
            "final_url": status.get("url", page.get("url")),
            "title": status.get("title", page.get("title")),
            "page_loaded": True,
            "chat_input_found": True,
            "input_and_click_succeeded": True,
            "ui_response_rendered": rendered,
            "response_body_length": int(status.get("bodyLength", 0)),
            "citation_signal_count": int(status.get("citationSignals", 0)),
            "network": deduped_network,
            "console_fatal_error_count": console_errors,
            "resource_failure_count": resource_failures,
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if rendered else 1


if __name__ == "__main__":
    raise SystemExit(main())
