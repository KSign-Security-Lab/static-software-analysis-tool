#!/usr/bin/env node
/**
 * Screenshot a page after it has settled, and report what it said.
 *
 * `chrome --screenshot` fires on the load event, which is before React has
 * rendered anything the queries fetched -- and `--virtual-time-budget`, which
 * would normally wait, hangs forever here because the workbench holds an SSE
 * connection open and virtual time never advances past a pending request.
 *
 * So: drive Chrome over the DevTools protocol, wait a real interval, capture,
 * and print the console. A screenshot that looks right while the console is
 * full of errors is not a passing check.
 *
 * No dependency -- node has had a WebSocket client built in since 22.
 *
 *   node scripts/shot.mjs <url> <out.png> [--wait 3500] [--size 1700x950]
 *                         [--theme dark|light] [--click <selector>]
 *                         [--eval <expression>]
 */

import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = process.argv.slice(2);
const [url, out] = args;
if (!url || !out) {
  console.error("usage: shot.mjs <url> <out.png> [--wait ms] [--size WxH] [--theme t] [--click sel] [--eval expr]");
  process.exit(2);
}

const flag = (name, fallback) => {
  const at = args.indexOf(`--${name}`);
  return at >= 0 ? args[at + 1] : fallback;
};

const wait = Number(flag("wait", 3500));
const [width, height] = flag("size", "1700x950").split("x").map(Number);
const theme = flag("theme", null);
const click = flag("click", null);
const evaluate = flag("eval", null);

const profile = mkdtempSync(join(tmpdir(), "ssat-shot-"));
const port = 9222 + Math.floor((Date.now() / 1000) % 500);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const chrome = spawn(
  "google-chrome",
  [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--hide-scrollbars",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    `--window-size=${width},${height}`,
    "about:blank",
  ],
  { stdio: "ignore" },
);

async function endpoint() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      return (await res.json()).webSocketDebuggerUrl;
    } catch {
      await sleep(250);
    }
  }
  throw new Error("chrome never opened its debugging port");
}

function connect(target, onEvent) {
  const socket = new WebSocket(target);
  const pending = new Map();
  let next = 0;

  const ready = new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id === undefined) {
      onEvent(message);
      return;
    }
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id);
    if (message.error) waiter.reject(new Error(message.error.message));
    else waiter.resolve(message.result);
  });

  const send = (method, params = {}, sessionId) =>
    new Promise((resolve, reject) => {
      const id = (next += 1);
      pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, method, params, sessionId }));
    });

  return { ready, send, close: () => socket.close() };
}

const said = [];

try {
  const client = connect(await endpoint(), (message) => {
    if (message.method === "Runtime.consoleAPICalled") {
      const text = (message.params.args ?? [])
        .map((arg) => arg.value ?? arg.description ?? arg.type)
        .join(" ");
      said.push(`${message.params.type}: ${text}`);
    }
    if (message.method === "Runtime.exceptionThrown") {
      const detail = message.params.exceptionDetails;
      said.push(`uncaught: ${detail.exception?.description ?? detail.text}`);
    }
    if (message.method === "Log.entryAdded" && message.params.entry.level === "error") {
      said.push(`log: ${message.params.entry.text}`);
    }
  });
  await client.ready;

  const { targetId } = await client.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await client.send("Target.attachToTarget", { targetId, flatten: true });
  const call = (method, params) => client.send(method, params, sessionId);

  await call("Page.enable");
  await call("Runtime.enable");
  await call("Log.enable");
  await call("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });

  if (theme) {
    // Before navigation, so next-themes' pre-paint script reads it and the
    // page never renders in the other theme first.
    await call("Page.addScriptToEvaluateOnNewDocument", {
      source: `try{localStorage.setItem("ssat-theme",${JSON.stringify(theme)})}catch(e){}`,
    });
  }

  await call("Page.navigate", { url });
  await sleep(wait);

  if (click) {
    // `text=…` matches on visible text. Radix does not put its `value` in an
    // attribute, so a tab is not addressable by CSS -- and matching what the
    // user would actually read is the more honest target anyway.
    const finder = click.startsWith("text=")
      ? `[...document.querySelectorAll("button, a, [role=tab], [role=button], [role=menuitem]")]
           .find((e) => (e.textContent || "").trim().includes(${JSON.stringify(click.slice(5))}))`
      : `document.querySelector(${JSON.stringify(click)})`;

    // Returns the centre point, so the caller can aim a real pointer at it.
    const expression = `(() => {
      const el = ${finder};
      if (!el) return "no match";
      el.scrollIntoView({ block: "center" });
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return "not visible";
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    })()`;

    const { result } = await call("Runtime.evaluate", { expression, returnByValue: true });
    if (typeof result.value === "string") {
      console.log(`click ${click}: ${result.value}`);
    } else if (result.value) {
      // A real pointer, not element.click(). Radix activates a tab on
      // mousedown and focus; a synthetic click event alone does nothing, which
      // looks exactly like a broken app when it is a broken test.
      const { x, y } = result.value;
      for (const type of ["mousePressed", "mouseReleased"]) {
        await call("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 });
      }
      console.log(`click ${click}: at ${Math.round(x)},${Math.round(y)}`);
    }
    await sleep(2000);
  }

  if (evaluate) {
    // awaitPromise, or an async probe returns the Promise serialised as `{}`.
    const { result, exceptionDetails } = await call("Runtime.evaluate", {
      expression: evaluate,
      returnByValue: true,
      awaitPromise: true,
    });
    if (exceptionDetails) console.log(`eval threw: ${exceptionDetails.exception?.description ?? exceptionDetails.text}`);
    else console.log(`eval: ${JSON.stringify(result.value)}`);
  }

  const { data } = await call("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(out, Buffer.from(data, "base64"));
  console.log(`wrote ${out}`);

  if (said.length) {
    console.error(`\n${said.length} console message(s):`);
    for (const line of said.slice(0, 40)) console.error(`  ${line}`);
  }

  client.close();
} finally {
  chrome.kill();
  // Chrome keeps flushing its profile for a moment after SIGTERM, so a rmdir
  // straight away races it and throws ENOTEMPTY on a run that succeeded.
  await sleep(400);
  try {
    rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  } catch {
    /* a temp directory left behind is not worth a non-zero exit */
  }
}
