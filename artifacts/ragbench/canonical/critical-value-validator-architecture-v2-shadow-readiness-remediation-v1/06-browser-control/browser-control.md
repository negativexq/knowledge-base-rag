# Direct Chrome CDP control

The browser connector was unavailable even though Chrome's CDP endpoint was
reachable. Remediation uses a small local-only helper,
`scripts/direct_chrome_cdp_smoke.py`, with the already-installed `websockets`
runtime. It attaches to the page websocket from `/json/list`; when no page
target exists it uses the browser websocket `Target.createTarget` command.

The helper controls navigation, DOM inspection, input assignment, click, UI
completion polling, console/error observation, and bounded `/chat` network
observation. It does not require the external browser connector, Playwright,
or Selenium and does not persist query/answer/DOM text.
