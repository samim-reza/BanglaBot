/* Website chat widget — the same AI agent as the phone line, typed.
 * Embed: <script src="https://YOUR-SERVER/api/public/widget.js" data-key="WIDGET_KEY" async></script>
 */
(function () {
  "use strict";
  var script = document.currentScript || (function () {
    var all = document.getElementsByTagName("script");
    for (var i = all.length - 1; i >= 0; i--) if ((all[i].src || "").indexOf("widget.js") !== -1) return all[i];
    return null;
  })();
  if (!script) return;
  var key = script.getAttribute("data-key");
  if (!key || window.__agentWidgetLoaded) return;
  window.__agentWidgetLoaded = true;
  var base = new URL(script.src, location.href).origin + "/api/public/widget/" + encodeURIComponent(key);
  var storeKey = "agent-widget-" + key;

  function post(path, body) {
    // text/plain keeps it a "simple" CORS request (no preflight).
    return fetch(base + path, { method: "POST", headers: { "Content-Type": "text/plain" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Request failed"); return j; }); });
  }

  fetch(base + "/config").then(function (r) { return r.ok ? r.json() : null; }).then(function (cfg) {
    if (!cfg || !cfg.enabled) return;
    build(cfg);
  }).catch(function () {});

  function build(cfg) {
    var color = cfg.color || "#0f766e";
    var host = document.createElement("div");
    host.setAttribute("data-agent-widget", key);
    host.style.cssText = "position:fixed;bottom:20px;" + (cfg.position === "left" ? "left" : "right") + ":20px;z-index:2147483000;";
    document.body.appendChild(host);
    var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    root.innerHTML =
      "<style>" +
      "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}" +
      ".btn{width:58px;height:58px;border-radius:50%;border:0;cursor:pointer;background:" + color + ";color:#fff;box-shadow:0 8px 24px rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center}" +
      ".btn svg{width:26px;height:26px}" +
      ".panel{position:absolute;bottom:72px;" + (cfg.position === "left" ? "left" : "right") + ":0;width:min(370px,calc(100vw - 32px));height:min(540px,calc(100vh - 110px));background:#fff;border-radius:16px;box-shadow:0 18px 50px rgba(0,0,0,.28);display:none;flex-direction:column;overflow:hidden;color:#111827}" +
      ".panel.open{display:flex}" +
      ".head{background:" + color + ";color:#fff;padding:14px 16px}" +
      ".head b{display:block;font-size:15px}.head span{font-size:12px;opacity:.9}" +
      ".msgs{flex:1;overflow-y:auto;padding:14px;background:#f8fafc;display:flex;flex-direction:column;gap:8px}" +
      ".m{max-width:82%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word}" +
      ".a{background:#fff;border:1px solid #e5e7eb;align-self:flex-start;border-bottom-left-radius:4px}" +
      ".u{background:" + color + ";color:#fff;align-self:flex-end;border-bottom-right-radius:4px}" +
      ".sys{align-self:center;font-size:12px;color:#6b7280}" +
      "form{display:flex;gap:8px;padding:10px;border-top:1px solid #e5e7eb;background:#fff}" +
      "input{flex:1;border:1px solid #d1d5db;border-radius:10px;padding:10px 12px;font-size:14px;outline:none}" +
      "input:focus{border-color:" + color + "}" +
      "button.send{border:0;border-radius:10px;padding:0 14px;background:" + color + ";color:#fff;font-weight:600;cursor:pointer}" +
      "button.send:disabled{opacity:.5;cursor:default}" +
      ".foot{font-size:11px;color:#9ca3af;text-align:center;padding:0 0 8px;background:#fff}" +
      ".restart{background:none;border:0;color:#fff;text-decoration:underline;cursor:pointer;font-size:12px;float:right}" +
      "</style>" +
      "<div class='panel' role='dialog' aria-label='Chat'>" +
      "<div class='head'><button class='restart' type='button'>New chat</button><b></b><span></span></div>" +
      "<div class='msgs' aria-live='polite'></div>" +
      "<form><input type='text' maxlength='600' placeholder='Type a message…' aria-label='Message'/><button class='send' type='submit'>Send</button></form>" +
      "<div class='foot'>AI assistant · replies may take a moment</div>" +
      "</div>" +
      "<button class='btn' type='button' aria-label='Open chat'><svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'/></svg></button>";
    var panel = root.querySelector(".panel"), msgs = root.querySelector(".msgs"), form = root.querySelector("form");
    var input = root.querySelector("input"), send = root.querySelector("button.send");
    root.querySelector(".head b").textContent = cfg.title || "Chat with us";
    root.querySelector(".head span").textContent = cfg.subtitle || "We usually reply instantly";
    var sessionId = null, ended = false, busy = false;
    try { sessionId = sessionStorage.getItem(storeKey); } catch (e) {}

    function add(text, cls) {
      var d = document.createElement("div");
      d.className = "m " + cls;
      d.textContent = text;
      msgs.appendChild(d);
      msgs.scrollTop = msgs.scrollHeight;
      return d;
    }
    function setBusy(v) { busy = v; send.disabled = v || ended; input.disabled = ended; }
    function start() {
      setBusy(true);
      var typing = add("…", "a");
      post("/start", {}).then(function (res) {
        typing.remove();
        sessionId = res.session_id; ended = false;
        try { sessionStorage.setItem(storeKey, sessionId); } catch (e) {}
        (res.messages || []).forEach(function (t) { add(t, "a"); });
      }).catch(function (err) { typing.remove(); add(err.message || "Chat is unavailable right now.", "sys"); })
        .then(function () { setBusy(false); input.focus(); });
    }
    function restart() {
      sessionId = null; ended = false; msgs.innerHTML = "";
      try { sessionStorage.removeItem(storeKey); } catch (e) {}
      start();
    }
    root.querySelector(".btn").addEventListener("click", function () {
      panel.classList.toggle("open");
      if (panel.classList.contains("open") && !msgs.childElementCount) { sessionId = null; start(); }
    });
    root.querySelector(".restart").addEventListener("click", restart);
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var text = input.value.trim();
      if (!text || busy || ended) return;
      input.value = "";
      add(text, "u");
      if (!sessionId) { start(); return; }
      setBusy(true);
      var typing = add("…", "a");
      post("/say", { session_id: sessionId, text: text }).then(function (res) {
        typing.remove();
        (res.messages || []).forEach(function (t) { add(t, "a"); });
        if (res.ended) { ended = true; add("Conversation ended · New chat to start again", "sys"); }
      }).catch(function (err) {
        typing.remove();
        add(err.message || "Something went wrong.", "sys");
        if (/ended|start a new/i.test(err.message || "")) { ended = true; }
      }).then(function () { setBusy(false); input.focus(); });
    });
  }
})();
