"use strict";
// RiskWatch front end. Agent output is untrusted, so all text goes in through DOM calls, never innerHTML.

const TOKEN = document.querySelector("meta[name=token]").content;
const page = document.getElementById("page");
let summary = null;
let catalog = null;
let onPoll = null;      // the current page's refresh hook, if it has one
let lastJobState = "";

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-RiskWatch-Token": TOKEN },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected") el[k] = v;
    else el.setAttribute(k, v);
  }
  el.append(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
  return el;
}

function toast(text, isError) {
  const el = h("div", { class: "toast" + (isError ? " err" : "") }, text);
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), isError ? 7000 : 3500);
}

const guard = (fn) => async (...args) => {
  try { return await fn(...args); } catch (e) { toast(e.message, true); }
};

const pct = (v, d = 2) => `${(v * 100).toFixed(d)}%`;
const usd = (v) => `$${(v / 1e6).toFixed(1)}m`;
const title = (s) => String(s).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function formatMetric(metric) {
  if (!metric) return "n/a";
  const { value, unit } = metric;
  if (unit === "pct") return pct(value);
  if (unit === "usd") return usd(value);
  if (unit === "days") return `${value.toFixed(2)} days`;
  if (unit === "ratio") return value.toFixed(2);
  return String(value);
}

function limitValue(row, value) {
  return row.metric === "liq_days_max" ? `${value.toFixed(2)} days` : row.metric.startsWith("beta") ? value.toFixed(2) : pct(value);
}

const STATUS = {
  ok: ["good", "✓", "OK"], NORMAL: ["good", "✓", "Normal"], warning: ["warn", "!", "Warning"], WARNING: ["warn", "!", "Warning"],
  breach: ["bad", "✕", "Breach"], BREACH: ["bad", "✕", "Breach"], completed: ["good", "✓", "Completed"],
  awaiting_approval: ["warn", "!", "Needs approval"], rejected: ["serious", "✕", "Rejected"], running: ["idle", "…", "Running"],
  pending: ["idle", "…", "Pending"], blocked_input: ["warn", "!", "Waiting for data"], blocked_dependency: ["idle", "…", "Waiting"],
  halted_error: ["bad", "✕", "Halted"], halted_budget: ["bad", "✕", "Over budget"], halted_no_input: ["bad", "✕", "No data"],
  done: ["good", "✓", "Done"], skipped: ["idle", "–", "Skipped"], failed: ["bad", "✕", "Failed"], waiting: ["warn", "!", "Waiting"],
  degraded: ["serious", "!", "Degraded"], interrupted: ["serious", "!", "Interrupted"],
  critical: ["bad", "✕", "Critical"], high: ["serious", "!", "High"], medium: ["warn", "!", "Medium"],
};

function status(key) {
  const [cls, icon, label] = STATUS[key] || ["idle", "•", title(key)];
  return h("span", { class: `status ${cls}` }, h("i", { "aria-hidden": "true" }, icon), label);
}

// ---- Minimal Markdown, built as DOM nodes ----
function inline(text) {
  const out = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[(?:L|F|DQ):[^\]]+\])/g;
  let at = 0;
  for (const m of text.matchAll(pattern)) {
    out.push(text.slice(at, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(h("strong", {}, t.slice(2, -2)));
    else if (t.startsWith("`")) out.push(h("code", {}, t.slice(1, -1)));
    else out.push(h("span", { class: "tag" }, t.slice(1, -1)));
    at = m.index + t.length;
  }
  out.push(text.slice(at));
  return out;
}

function markdown(text) {
  const root = h("div", { class: "memo" });
  let list = null;
  for (const raw of (text || "").split("\n")) {
    const line = raw.trimEnd();
    if (!line.startsWith("- ")) list = null;
    if (!line) continue;
    if (line.startsWith("# ")) root.append(h("h1", {}, inline(line.slice(2))));
    else if (line.startsWith("## ")) root.append(h("h2", {}, inline(line.slice(3))));
    else if (line.startsWith("> ")) root.append(h("blockquote", {}, inline(line.slice(2))));
    else if (line.startsWith("- ")) {
      if (!list) { list = h("ul"); root.append(list); }
      list.append(h("li", {}, inline(line.slice(2))));
    } else root.append(h("p", {}, inline(line)));
  }
  return root;
}

function table(headers, rows, opts = {}) {
  // Each cell carries its column name, so on a phone a row can stack into "name: value" lines.
  const labels = headers.map((c) => c.replace(/^>/, ""));
  for (const tr of [rows].flat(Infinity)) {
    if (tr && tr.children) [...tr.children].forEach((cell, i) => { if (labels[i]) cell.setAttribute("data-label", labels[i]); });
  }
  return h("div", { class: "scroll stack" + (opts.tall ? " scroll-y" : "") }, h("table", {},
    h("thead", {}, h("tr", {}, headers.map((c) => h("th", { class: c.startsWith(">") ? "r" : "" }, c.replace(/^>/, ""))))),
    h("tbody", {}, rows)));
}

function td(content, right) { return h("td", { class: right ? "r" : "" }, content); }
function choice(group, value, current, strong, span, onchange) {
  return h("label", { class: "choice" + (value === current ? " on" : "") },
    h("input", { type: "radio", name: group, value, checked: value === current, onchange }),
    h("strong", {}, strong), h("span", {}, span));
}

// ---- Navigation ----
function renderNav() {
  const s = summary;
  const ran = s && Object.keys(s.counts).length > 0;
  const steps = [
    ["#/connect", "1", "Connect a model", s && s.settings.configured],
    ["#/run", "2", "Run the workflow", ran],
    ["#/approvals", "3", "Approve", ran && s.pending === 0],
  ];
  const results = [["#/dashboard", "Dashboard"], ["#/reports", "Reports"], ["#/runs", "Run inspector"]];
  const more = [["#/improve", "Improve"], ["#/help", "Help"]];
  const here = location.hash.split("/").slice(0, 2).join("/") || "#/connect";
  const item = (href, label, dot, extra) => h("a", { class: "nav-item" + (here === href ? " active" : ""), href }, dot, label, extra);
  const nav = document.getElementById("nav");
  nav.replaceChildren(
    h("div", { class: "nav-label" }, "Steps"),
    ...steps.map(([href, n, label, done]) => item(href, label, h("span", { class: "step-dot" + (done ? " done" : "") }, done ? "✓" : n),
      href === "#/approvals" && s && s.pending ? h("span", { class: "badge" }, String(s.pending)) : null)),
    h("div", { class: "nav-label" }, "Results"),
    ...results.map(([href, label]) => item(href, label, h("span", { class: "step-dot" }, "›"))),
    h("div", { class: "nav-label" }, "More"),
    ...more.map(([href, label]) => item(href, label, h("span", { class: "step-dot" }, "›"))));
  // Always on screen, so the full output is one click away from any page once a run exists.
  // Phones show the short label, because the button shares the top bar with the menu.
  const label = [h("span", { class: "long" }, "Download full output (ZIP)"), h("span", { class: "short" }, "Download")];
  const download = ran
    ? h("a", { class: "btn side-download", href: "/api/download", id: "side-download", "aria-label": "Download full output (ZIP)" }, label)
    : h("span", { class: "btn side-download off", id: "side-download", "aria-disabled": "true", title: "Available after a run" }, label);
  document.getElementById("side-dl").replaceChildren(download, ran ? "" : h("div", { class: "side-hint" }, "Available after a run"));
  document.getElementById("side-foot").replaceChildren(h("div", {}, s ? s.backend : ""),
    s && s.last_day ? h("div", {}, `Reached ${s.last_day}`) : "");
  // The menu hides the Approve badge on phones, so the menu button carries it too.
  const badge = document.getElementById("menu-badge");
  badge.hidden = !(s && s.pending);
  badge.textContent = s && s.pending ? String(s.pending) : "";
}

function renderBanner() {
  const banner = document.getElementById("banner");
  const job = summary && summary.job;
  const parts = [];
  if (job && job.state === "running" && !location.hash.startsWith("#/run")) {
    parts.push(h("div", { class: "notice info" }, job.kind === "run"
      ? `Running: ${job.days_done} of ${job.days_total} days done. `
      : "Evaluation running. ", h("a", { href: job.kind === "run" ? "#/run" : "#/improve" }, "View")));
  }
  if (summary && summary.decision_error) parts.push(h("div", { class: "notice bad" }, summary.decision_error));
  banner.replaceChildren(...parts);
}

async function poll() {
  try {
    summary = await api("/api/summary");
    renderNav();
    renderBanner();
    const state = summary.job ? `${summary.job.id}:${summary.job.state}` : "";
    if (state !== lastJobState) {
      if (lastJobState && summary.job && summary.job.state === "finished") toast("Finished.");
      lastJobState = state;
    }
    if (onPoll) await onPoll();
  } catch (e) { /* server restarting; the next poll will recover */ }
}

// ---- 1. Connect ----
const PROVIDERS = [
  ["claude-code", "Claude login", "Use the Claude Code account signed in on this computer. No key needed."],
  ["anthropic", "Anthropic API", "Claude models with an API key."],
  ["openai", "OpenAI", "GPT models with an API key."],
  ["kimi", "Kimi (Moonshot)", "Kimi models with an API key."],
  ["openrouter", "OpenRouter", "Hundreds of models with one key."],
  ["deepseek", "DeepSeek", "DeepSeek models with an API key."],
  ["qwen", "Qwen (DashScope)", "Qwen models with an API key."],
  ["mistral", "Mistral", "Mistral models with an API key."],
  ["groq", "Groq", "Fast open models with an API key."],
  ["ollama", "Ollama", "A model on this computer. No key needed."],
  ["custom", "Other address", "Any endpoint compatible with OpenAI or Anthropic."],
  ["scripted", "Offline demo", "No model. Rule-based stand-in, to see the workflow."],
];

function pageConnect() {
  const form = { ...summary.settings, api_key: "", reviewer_api_key: "", remember_key: false };
  if (!form.provider) { form.provider = "claude-code"; form.model = "sonnet"; }
  const panel = h("div");
  const result = h("div");
  let models = [];

  const collect = () => ({ ...form });

  const renderPanel = async () => {
    const info = catalog.providers[form.provider] || {};
    const kids = [];
    if (form.provider === "claude-code") {
      const state = h("div", { class: "notice info" }, "Checking Claude Code on this computer…");
      kids.push(state);
      api("/api/claude").then((c) => {
        if (!c.installed) {
          state.className = "notice bad";
          state.replaceChildren("Claude Code is not installed here. Choose another option, or install it from claude.com/product/claude-code and reload.");
        } else if (c.logged_in) {
          state.className = "notice good";
          state.replaceChildren(`Signed in as ${c.email || "your account"}${c.plan ? ` (${c.plan} plan)` : ""}. Model calls count against that plan.`);
        } else {
          state.className = "notice warn";
          state.replaceChildren("Claude Code is installed but not signed in. ", h("button", {
            onclick: guard(async () => { await api("/api/claude/login", {}); toast("Finish signing in in the browser window that opens, then reload this page."); }),
          }, "Sign in with Claude"));
        }
      }).catch((e) => state.replaceChildren(e.message));
      kids.push(h("label", { class: "field" }, "Model",
        h("span", { class: "hint" }, "Sonnet is a good balance. Default uses the account's own setting."),
        h("select", { onchange: (e) => { form.model = e.target.value; } },
          [["", "Default"], ["sonnet", "Sonnet"], ["opus", "Opus"], ["haiku", "Haiku"]].map(([v, t]) =>
            h("option", { value: v, selected: form.model === v }, t)))));
    } else if (form.provider === "scripted") {
      kids.push(h("div", { class: "notice warn" }, "This is rule-based code, not an AI model. It is useful for seeing the workflow and its failure handling, but its writing is template text."));
    } else {
      kids.push(h("label", { class: "field" }, "API address",
        h("span", { class: "hint" }, info.base_url ? "Filled in for you. Change it only if your provider gave you a different one." : "The base URL of your endpoint, for example https://host/v1"),
        h("input", { type: "text", id: "base-url", value: form.base_url || info.base_url, placeholder: "https://…", oninput: (e) => { form.base_url = e.target.value; } })));
      if (form.provider === "custom") {
        kids.push(h("label", { class: "field" }, "API style",
          h("select", { onchange: (e) => { form.protocol = e.target.value; } },
            h("option", { value: "openai", selected: form.protocol !== "anthropic" }, "OpenAI compatible (most providers)"),
            h("option", { value: "anthropic", selected: form.protocol === "anthropic" }, "Anthropic Messages"))));
      }
      if (info.needs_key || form.provider === "custom") {
        kids.push(h("label", { class: "field" }, "API key",
          h("span", { class: "hint" }, summary.settings.has_key ? `A key is saved (${summary.settings.key_hint}). Leave this empty to keep it.` : "Kept in memory while the app runs, and never shown again."),
          h("input", { type: "password", id: "api-key", autocomplete: "off", oninput: (e) => { form.api_key = e.target.value; } })));
        kids.push(h("label", { class: "row small" }, h("input", { type: "checkbox", onchange: (e) => { form.remember_key = e.target.checked; } }),
          "Remember the key on this computer (saved to .env, which is never committed or zipped)"));
      }
      const list = h("datalist", { id: "model-list" }, models.map((m) => h("option", { value: m })));
      kids.push(h("label", { class: "field", style: "margin-top:14px" }, "Model",
        h("span", { class: "hint" }, "The model id from your provider. Load the list, or type it."),
        h("div", { class: "row" },
          h("input", { type: "text", class: "grow", id: "model", list: "model-list", value: form.model, oninput: (e) => { form.model = e.target.value; } }),
          h("button", { type: "button", onclick: guard(async () => {
            const res = await api("/api/models", collect());
            models = res.models;
            if (models.length) { toast(`${models.length} models found.`); list.replaceChildren(...models.map((m) => h("option", { value: m }))); }
            else toast(res.message || "This provider did not list any models. Type the id instead.", true);
          }) }, "Load models")), list));
      kids.push(h("details", { class: "small" }, h("summary", {}, "Optional: prices and a separate reviewer model"),
        h("p", { class: "muted", style: "margin-top:8px" }, "Prices let the dollar limit work. Without them, the call and token limits still apply."),
        h("div", { class: "grid cols-2" },
          h("label", { class: "field" }, "Input, USD per million tokens", h("input", { type: "number", min: "0", step: "any", value: form.price_in, oninput: (e) => { form.price_in = e.target.value; } })),
          h("label", { class: "field" }, "Output, USD per million tokens", h("input", { type: "number", min: "0", step: "any", value: form.price_out, oninput: (e) => { form.price_out = e.target.value; } }))),
        h("p", { class: "muted" }, "An independent reviewer is stronger if it runs on a different model. Leave these empty to use the main model."),
        h("div", { class: "grid cols-2" },
          h("label", { class: "field" }, "Reviewer provider", h("select", { onchange: (e) => { form.reviewer_provider = e.target.value; } },
            h("option", { value: "" }, "Same as main"),
            PROVIDERS.filter(([id]) => id !== "scripted").map(([id, name]) => h("option", { value: id, selected: form.reviewer_provider === id }, name)))),
          h("label", { class: "field" }, "Reviewer model", h("input", { type: "text", value: form.reviewer_model, oninput: (e) => { form.reviewer_model = e.target.value; } }))),
        h("label", { class: "field" }, "Reviewer API key", h("input", { type: "password", autocomplete: "off", oninput: (e) => { form.reviewer_api_key = e.target.value; } }))));
    }
    panel.replaceChildren(...kids);
  };

  const cards = h("div", { class: "choices" });
  const renderCards = () => cards.replaceChildren(...PROVIDERS.map(([id, name, text]) => choice("provider", id, form.provider, name, text, () => {
    form.provider = id;
    form.base_url = ""; form.model = id === "claude-code" ? "sonnet" : ""; form.protocol = "";
    models = [];
    result.replaceChildren();
    renderCards();
    renderPanel();
  })));
  renderCards();
  renderPanel();

  const test = guard(async (button) => {
    const needsModel = !["claude-code", "scripted"].includes(form.provider);
    if (needsModel && !form.model) { toast("Enter a model first.", true); return; }
    button.disabled = true;
    result.replaceChildren(h("div", { class: "notice info" }, "Sending one small test message…"));
    try {
      const res = await api("/api/test", collect());
      form.api_key = ""; form.reviewer_api_key = "";
      summary.settings = (await api("/api/summary")).settings;
      result.replaceChildren(h("div", { class: `notice ${res.ok ? "good" : "bad"}` },
        res.ok ? `Connected. ${res.message}` : `Could not connect: ${res.message}`,
        res.ok && res.follows_format === false ? " It replied, but not in the required JSON format, so this model may struggle." : ""));
    } finally { button.disabled = false; }
  });

  page.replaceChildren(
    h("h1", {}, "Connect a model"),
    h("p", { class: "lede" }, "RiskWatch needs an AI model for its five agents. The risk numbers never depend on it: they are calculated by code."),
    h("div", { class: "card" }, h("h2", {}, "Your name"),
      h("label", { class: "field" }, h("span", { class: "hint" }, "Recorded on every approval you make, as the audit trail requires."),
        h("input", { type: "text", id: "name", value: form.name, placeholder: "For example, Jane Smith", oninput: (e) => { form.name = e.target.value; } }))),
    h("div", { class: "card" }, h("h2", {}, "Which model?"), cards),
    h("div", { class: "card" }, h("h2", {}, "Connection details"), panel,
      h("div", { class: "row", style: "margin-top:14px" },
        h("button", { type: "button", id: "test", onclick: (e) => test(e.currentTarget) }, "Test connection"),
        h("button", { type: "button", class: "primary", id: "continue", onclick: guard(async () => {
          if (!form.name.trim()) { toast("Enter your name first.", true); return; }
          if (!["claude-code", "scripted"].includes(form.provider) && !form.model) { toast("Enter a model first.", true); return; }
          await api("/api/settings", collect());
          location.hash = "#/run";
        }) }, "Save and continue")),
      h("div", { style: "margin-top:12px" }, result)));
}

// ---- 2. Run ----
const PERIODS = [
  ["quick", "Quick look", "Five days at the height of the 2020 crash.", "2020-03-09", "2020-03-13"],
  ["crash", "Crash month", "From the February 2020 peak through the sell-off.", "2020-02-18", "2020-03-13"],
  ["half", "First half of 2020", "Crash and recovery, with monthly reviews.", "2020-01-02", "2020-06-30"],
  ["full", "Test year", "July 2019 to June 2020, with every injected fault and drill.", "2019-07-01", "2020-06-30"],
  ["y1987", "Black Monday 1987", "October 1987, when the market fell 20% in a day.", "1987-10-01", "1987-10-30"],
  ["y2008", "2008 financial crisis", "Lehman's collapse and the sell-off that followed.", "2008-09-02", "2008-11-28"],
  ["y2022", "2022 rate shock", "Inflation and rising rates, January to June 2022.", "2022-01-03", "2022-06-30"],
  ["custom", "Choose dates", "", "", ""],
];

function longDate(iso) {
  return new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

// Drills and injected vendor faults live only in the fixed test window.
function hasDrills(start, end) {
  const w = catalog.drill_window;
  return Boolean(start && end && start <= w.end && end >= w.start);
}
const CALLS_PER_DAY = 5;
const SECONDS_PER_DAY_OFFLINE = 2;
const SECONDS_PER_DAY_LIVE = 75;

function tradingDaysRough(start, end) {
  if (!start || !end || end < start) return 0;
  return Math.round(((new Date(end) - new Date(start)) / 864e5 + 1) * 252 / 365);
}

function duration(seconds) {
  if (seconds < 90) return `${Math.max(1, Math.round(seconds / 10) * 10)} seconds`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} minutes`;
  return `${(seconds / 3600).toFixed(1)} hours`;
}

function pageRun() {
  if (!summary.settings.configured) { location.hash = "#/connect"; return; }
  const offline = summary.settings.provider === "scripted";
  const form = { period: "crash", start: "2020-02-18", end: "2020-03-13", approvals: "manual", drills: offline };
  const setup = h("div");
  const live = h("div");

  const renderSetup = () => {
    const days = tradingDaysRough(form.start, form.end);
    const seconds = days * (offline ? SECONDS_PER_DAY_OFFLINE : SECONDS_PER_DAY_LIVE);
    const calls = Math.round(days * CALLS_PER_DAY);
    const heavy = !offline && days > 30;
    const drills = hasDrills(form.start, form.end);
    const ws = summary.book_start ? { from: summary.book_start, to: summary.last_day, next: summary.continue_from } : null;
    const fresh = ws && (form.start < ws.from || form.start > ws.next);
    setup.replaceChildren(
      h("div", { class: "card" }, h("h2", {}, "Period"),
        h("div", { class: "choices" }, PERIODS.map(([id, name, text, s, e]) => choice("period", id, form.period, name,
          text || `Any period from ${longDate(catalog.first_day)} to ${longDate(catalog.last_day)}.`, () => {
          form.period = id;
          if (s) { form.start = s; form.end = e; }
          renderSetup();
        }))),
        form.period === "custom" ? h("div", { class: "grid cols-2", style: "margin-top:14px" },
          h("label", { class: "field" }, "From", h("input", { type: "date", min: catalog.first_day, max: catalog.last_day, value: form.start, onchange: (e) => { form.start = e.target.value; renderSetup(); } })),
          h("label", { class: "field" }, "To", h("input", { type: "date", min: catalog.first_day, max: catalog.last_day, value: form.end, onchange: (e) => { form.end = e.target.value; renderSetup(); } }))) : null),
      h("div", { class: "card" }, h("h2", {}, "Who approves?"),
        h("div", { class: "choices" },
          choice("approvals", "manual", form.approvals, "I will review them", "Breach days wait in the Approve step, while later days keep running.", () => { form.approvals = "manual"; renderSetup(); }),
          choice("approvals", "auto", form.approvals, "Approve automatically", "A simulated approver signs everything, for a fast full output.", () => { form.approvals = "auto"; renderSetup(); })),
        offline && drills ? h("label", { class: "row small", style: "margin-top:12px" },
          h("input", { type: "checkbox", id: "drills", checked: form.drills, onchange: (e) => { form.drills = e.target.checked; } }),
          "Include failure drills: bad drafts, provider outages and a prompt injection, to watch the workflow handle them") : null,
        drills ? null : h("p", { class: "muted small", id: "no-drills", style: "margin-top:12px" },
          `The failure drills and injected vendor faults sit between ${longDate(catalog.drill_window.start)} and `,
          `${longDate(catalog.drill_window.end)}. This period has none, so it runs on clean market data.`)),
      h("div", { class: "card" },
        h("div", { class: "row" },
          h("div", { class: "grow" }, h("strong", {}, `About ${days} trading days`),
            h("div", { class: "muted small" }, offline ? `Takes about ${duration(seconds)}. No model calls.`
              : `About ${calls} model calls on ${summary.backend}. Allow roughly ${duration(seconds)}.`)),
          h("button", { class: "primary", id: "start", disabled: !days, onclick: guard(() => (fresh ? startOverAndRun() : start(false))) },
            fresh ? "Start over and run" : "Start run")),
        heavy ? h("div", { class: "notice warn", style: "margin:12px 0 0" }, "That is a long run on a real model and will use a lot of your plan or budget. Consider a shorter period first.") : null,
        fresh ? h("div", { class: "notice warn", id: "fresh-notice", style: "margin:12px 0 0" },
          `This workspace holds results from ${longDate(ws.from)}${ws.to ? ` to ${longDate(ws.to)}` : ""}, and a new run `,
          `can only continue it from ${longDate(ws.next)}. Running this period starts a fresh workspace: the current `,
          "results move to an archive folder first.") : null,
        ws && !fresh ? h("p", { class: "muted small", style: "margin-top:12px" },
          `This workspace already has results from ${longDate(ws.from)}. A new run continues it. `,
          h("button", { onclick: guard(startOver) }, "Start over")) : null));
  };

  const start = async (resume) => {
    await api("/api/start", { ...(resume && summary.job ? { start: summary.job.start, end: summary.job.end, approvals: summary.job.manual ? "manual" : "auto", drills: summary.job.drills }
      : { ...form, drills: form.drills && hasDrills(form.start, form.end) }), resume });
    await poll();
    renderLive();
  };

  const startOver = async () => {
    if (!confirm("Start over? Current results move to an archive folder and the workspace starts empty.")) return;
    await api("/api/start-over", {});
    await poll();
    route();
  };

  const startOverAndRun = async () => {
    if (!confirm("Start a fresh workspace for this period? Current results move to an archive folder.")) return;
    await api("/api/start-over", {});
    await poll();
    await start(false);
  };

  const activity = h("div", { class: "muted small" });
  const renderLive = () => {
    const job = summary.job;
    const isRun = job && job.kind === "run";
    setup.hidden = Boolean(isRun && job.state === "running");
    if (!isRun) { live.replaceChildren(); return; }
    const share = job.days_total ? (job.days_done / job.days_total) * 100 : 0;
    const running = job.state === "running";
    const kids = [h("div", { class: "row" }, h("h2", { style: "margin:0", class: "grow" }, `${job.start} to ${job.end}`),
      running ? status("running") : job.state === "finished" ? status("completed") : status(job.state === "stopped" ? "interrupted" : "failed"))];
    kids.push(h("div", { class: "progress" }, h("div", { style: `width:${share}%` })));
    kids.push(h("div", { class: "muted small" }, `${job.days_done} of ${job.days_total} days processed, on ${job.backend}`));
    if (running) kids.push(activity);
    if (job.state === "failed") kids.push(h("pre", { class: "code" }, job.error || "The run failed."));
    const halted = Object.entries(summary.counts).filter(([k]) => k.startsWith("halted")).reduce((n, [, v]) => n + v, 0);
    if (halted) kids.push(h("div", { class: "notice bad", style: "margin-top:10px" }, `${halted} runs stopped on an error and need a look. `, h("a", { href: "#/runs" }, "See the runs")));
    const actions = [];
    if (running) actions.push(h("button", { class: "danger", onclick: guard(() => api("/api/stop", {})) }, "Stop"));
    if (job.state === "stopped" || job.state === "failed") {
      actions.push(h("button", { class: "primary", onclick: guard(() => start(true)) }, "Resume"));
      kids.push(h("p", { class: "small muted", style: "margin-top:10px" }, "Stopping is the same event as a crash. Resume picks up where it left off, without repeating finished work."));
    }
    if (!running) {
      if (summary.pending) actions.push(h("a", { class: "btn", href: "#/approvals" }, `Review ${summary.pending} approvals`));
      actions.push(h("a", { class: "btn", href: "#/dashboard" }, "Open dashboard"), h("a", { class: "btn", href: "/api/download" }, "Download full output"));
    }
    kids.push(h("div", { class: "row", style: "margin-top:12px" }, actions));
    live.replaceChildren(h("div", { class: "card" }, kids));
  };

  page.replaceChildren(h("h1", {}, "Run the workflow"),
    h("p", { class: "lede" }, "Choose a period of history. RiskWatch replays each day as if it were live, seeing only what was known at that day's cutoff."),
    live, setup);
  renderSetup();
  renderLive();
  onPoll = async () => {
    renderLive();
    if (summary.job && summary.job.state === "running" && summary.job.kind === "run") {
      const data = await api("/api/runs");
      const active = data.runs.find((r) => r.status === "running");
      activity.textContent = active ? `Working on ${active.run_id}` : "";
    } else if (setup.hidden === false && !setup.childElementCount) renderSetup();
  };
}

// ---- 3. Approvals ----
const REASON_SHORT = {
  hard_breach: "Hard breach", new_warning: "New warning", dq_override: "Data override", dq_escalation: "Data question",
  degraded_memo: "Needs extra care", material_restatement: "Restatement", model_review: "Model review",
};
const REASONS = {
  hard_breach: "A hard limit is breached", new_warning: "A new warning or breach opened", dq_override: "Data was overridden",
  dq_escalation: "A data question needs a person", degraded_memo: "The agents could not finish normally. See the note in the memo",
  material_restatement: "A vendor correction changed the numbers", model_review: "Monthly model review",
};

async function pageApprovals() {
  let selected = null;
  const body = h("div");
  page.replaceChildren(h("h1", {}, "Approve"),
    h("p", { class: "lede" }, "Nothing consequential is released without a named person. Your decision and note go on the record."), body);

  const render = async () => {
    const { items } = await api("/api/pending");
    if (!items.length) {
      const note = summary.queued_decisions ? `Applying ${summary.queued_decisions} decisions…` : "Nothing is waiting for you.";
      body.replaceChildren(h("div", { class: "card" }, h("p", {}, note), h("a", { class: "btn", href: "#/dashboard" }, "Open dashboard")));
      return;
    }
    if (!items.find((i) => i.run_id === selected)) selected = items[0].run_id;
    const item = items.find((i) => i.run_id === selected);
    const noteBox = h("textarea", { id: "note", placeholder: "Required to reject or request changes" });
    const act = (decision) => guard(async () => {
      if (decision !== "approve" && !noteBox.value.trim()) { toast("Add a note so the record explains this decision.", true); noteBox.focus(); return; }
      await api("/api/decide", { run_id: item.run_id, decision, note: noteBox.value });
      toast(decision === "approve" ? "Approved." : "Recorded.");
      selected = null;
      setTimeout(render, 700);
    });
    const hard = item.limits.filter((r) => r.status !== "ok");
    body.replaceChildren(h("div", { class: "split" },
      h("div", {},
        h("div", { class: "card", style: "padding:0;overflow:hidden" }, h("div", { class: "list" }, items.map((i) =>
          h("button", { class: i.run_id === selected ? "on" : "", onclick: () => { selected = i.run_id; render(); } },
            i.run_id, h("small", {}, i.reasons.map((r) => REASON_SHORT[r] || title(r)).join(", ")))))),
        h("button", { style: "width:100%", onclick: guard(async () => {
          if (!confirm(`Approve all ${items.length} waiting items? Your name is recorded on each one.`)) return;
          await api("/api/approve-all", {});
          setTimeout(render, 900);
        }) }, `Approve all ${items.length}`)),
      h("div", {},
        h("div", { class: "card" }, h("h2", {}, "Why this needs you"),
          h("ul", { style: "margin:0;padding-left:20px" }, item.reasons.map((r) => h("li", {}, REASONS[r] || title(r))))),
        h("div", { class: "card" }, markdown(item.text)),
        hard.length ? h("div", { class: "card" }, h("h2", {}, "Limits not OK"), table(["Limit", ">Value", ">Warning", ">Hard limit", "Status"],
          hard.map((r) => h("tr", {}, td(r.label), td(limitValue(r, r.value), 1), td(limitValue(r, r.warn), 1), td(limitValue(r, r.hard), 1), td(status(r.status)))))) : null,
        h("div", { class: "card" }, h("h2", {}, "Your decision"),
          h("label", { class: "field" }, "Note", noteBox),
          h("div", { class: "row" },
            h("button", { class: "primary", id: "approve", onclick: act("approve") }, "Approve"),
            item.workflow === "eod" && !item.degraded ? h("button", { onclick: act("request_changes") }, "Request changes") : null,
            h("button", { class: "danger", onclick: act("reject") }, "Reject")),
          h("p", { class: "small muted", style: "margin:10px 0 0" }, `Signed as ${summary.settings.name || "web user"}. Request changes sends your note to the agents, then the memo comes back here.`)))));
  };
  await render();
  let seen = summary.pending;
  onPoll = async () => { if (summary.pending !== seen) { seen = summary.pending; if (!document.activeElement || document.activeElement.id !== "note") await render(); } };
}

// ---- 4. Dashboard ----
function varChart(rows) {
  const data = rows.filter((r) => r.hit !== null);
  if (data.length < 2) return h("p", { class: "muted" }, "The chart appears after two days have been scored.");
  const W = 1040, H = 320, L = 44, R = 12, T = 12, B = 26;
  const ns = "http://www.w3.org/2000/svg";
  const s = (tag, attrs, text) => {
    const el = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const losses = data.map((d) => -d.next_return * 100);
  const vars = data.map((d) => d.var99 * 100);
  const top = Math.ceil(Math.max(...losses, ...vars) / 2) * 2;
  const bottom = Math.floor(Math.min(...losses, 0) / 2) * 2;
  const x = (i) => L + ((i + 0.5) / data.length) * (W - L - R);
  const y = (v) => T + ((top - v) / (top - bottom)) * (H - T - B);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Daily loss against the VaR forecast" });
  const css = getComputedStyle(document.documentElement);
  const color = (name) => css.getPropertyValue(name).trim();
  const step = (top - bottom) > 12 ? 4 : 2;
  const ticks = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  for (let v = -step; v >= bottom; v -= step) ticks.push(v);
  for (const v of ticks) {
    svg.append(s("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: color(v === 0 ? "--line-2" : "--line"), "stroke-width": 1 }));
    svg.append(s("text", { x: L - 7, y: y(v) + 4, "text-anchor": "end", "font-size": 11, fill: color("--ink-2") }, `${v}%`));
  }
  const barW = Math.min(16, Math.max(1.2, ((W - L - R) / data.length) * 0.72));
  data.forEach((d, i) => {
    const v = losses[i];
    svg.append(s("rect", { x: x(i) - barW / 2, y: Math.min(y(v), y(0)), width: barW, height: Math.max(Math.abs(y(v) - y(0)), 0.5), fill: color("--series-1") }));
    if (i === 0 || d.as_of.slice(0, 7) !== data[i - 1].as_of.slice(0, 7)) {
      if (data.length < 45 || d.as_of.slice(5, 7) % 2 === 1 || i === 0) svg.append(s("text", { x: x(i), y: H - 8, "font-size": 11, fill: color("--ink-2"), "text-anchor": "middle" }, d.as_of.slice(0, 7)));
    }
  });
  svg.append(s("polyline", { points: data.map((d, i) => `${x(i)},${y(vars[i])}`).join(" "), fill: "none", stroke: color("--series-2"), "stroke-width": 2, "stroke-linejoin": "round" }));
  data.forEach((d, i) => {
    if (d.hit) svg.append(s("circle", { cx: x(i), cy: y(losses[i]), r: 4.5, fill: color("--ink"), stroke: color("--card"), "stroke-width": 2 }));
  });
  const cross = s("line", { y1: T, y2: H - B, stroke: color("--ink-3"), "stroke-width": 1, visibility: "hidden" });
  svg.append(cross);
  const tip = h("div", { class: "tip", hidden: true });
  const wrap = h("div", { class: "chart-wrap" }, svg, tip);
  const move = (e) => {
    const box = svg.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.min(data.length - 1, Math.max(0, Math.floor(((px - L) / (W - L - R)) * data.length)));
    const d = data[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.replaceChildren(h("strong", {}, `Forecast ${d.as_of}`), h("br"), `Next-day result ${pct(d.next_return)}`, h("br"), `99% VaR ${pct(d.var99)}`, d.hit ? h("div", {}, "Exception") : "");
    const left = (x(i) / W) * box.width;
    tip.style.left = `${left > box.width * 0.7 ? left - tip.offsetWidth - 12 : left + 12}px`;
    tip.style.top = "8px";
  };
  svg.addEventListener("pointermove", move);
  svg.addEventListener("pointerleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
  return wrap;
}

async function pageDashboard() {
  const d = await api("/api/dashboard");
  if (!d.day) {
    page.replaceChildren(h("h1", {}, "Dashboard"), h("div", { class: "card" }, h("p", {}, "No results yet."), h("a", { class: "btn", href: "#/run" }, "Run the workflow")));
    return;
  }
  const m = d.day.metrics;
  const bt = d.day.backtest || {};
  const tile = (label, value, sub) => h("div", { class: "tile" }, h("div", { class: "label" }, label), h("div", { class: "value" }, value), sub ? h("div", { class: "sub" }, sub) : null);
  const open = d.breaches.filter((b) => !b.closed_on);
  const limitName = Object.fromEntries(d.day.limits.map((r) => [r.limit_id, r.label]));
  const exceptions = d.var.filter((r) => r.hit === 1);
  page.replaceChildren(
    h("h1", {}, "Dashboard"),
    h("p", { class: "lede" }, `Latest day: ${d.day.as_of}. Model: ${d.day.llm}.`),
    h("div", { class: "tiles" },
      h("div", { class: "tile" }, h("div", { class: "label" }, "Overall status"), h("div", { style: "margin:7px 0" }, status(d.day.overall || "NORMAL")), h("div", { class: "sub" }, `${open.length} limits open`)),
      tile("Net asset value", formatMetric(m.nav_usd), `Day return ${formatMetric(m.daily_return)}`),
      tile("1-day 99% VaR", formatMetric(m.var99_1d), `97.5% ES ${formatMetric(m.es975_1d)}`),
      tile("Drawdown", formatMetric(m.drawdown), `Volatility ${formatMetric(m.vol_ann_ewma)}`),
      tile("VaR exceptions", String(bt.exceptions ?? "n/a"), `${title(bt.zone || "n/a")} zone, ${(bt.expected ?? 0).toFixed(1)} expected`)),
    h("div", { class: "card" }, h("h2", {}, "Did VaR hold? Next-day loss against the forecast"),
      h("div", { class: "legend" },
        h("span", {}, h("i", { class: "bar", style: "background:var(--series-1)" }), "Next-day loss (gain below zero)"),
        h("span", {}, h("i", { style: "background:var(--series-2)" }), "99% VaR forecast"),
        h("span", {}, h("i", { class: "dot", style: "background:var(--ink)" }), `Exception (${exceptions.length})`)),
      varChart(d.var)),
    h("div", { class: "grid cols-2" },
      h("div", { class: "card" }, h("h2", {}, `Limits on ${d.day.as_of}`),
        table(["Limit", ">Value", ">Hard limit", "Status"], d.day.limits.map((r) => h("tr", {}, td(r.label), td(limitValue(r, r.value), 1), td(limitValue(r, r.hard), 1), td(status(r.status)))))),
      h("div", { class: "card" }, h("h2", {}, "Breach register"),
        d.breaches.length ? table(["Limit", "Severity", "Opened", "Closed", ">Days"], d.breaches.map((b) =>
          h("tr", {}, td(limitName[b.limit_id] || title(b.limit_id)), td(status(b.severity)), td(b.opened_on), td(b.closed_on || "Open"), td(String(b.days_open), 1))), { tall: true })
          : h("p", { class: "muted" }, "No limits have been crossed."))),
    h("div", { class: "card" }, h("h2", {}, "Escalations"),
      d.escalations.length ? table(["When", "Severity", "Run", "Reason"], d.escalations.map((e) =>
        h("tr", {}, td(e.sim_ts), td(status(e.severity)), td(e.run_id ? h("a", { href: `#/run/${e.run_id}` }, e.run_id) : "System"), td(e.reason))), { tall: true })
        : h("p", { class: "muted" }, "None.")),
    h("p", { class: "small muted" }, `Model usage so far: ${d.usage.calls.toLocaleString()} calls, ${d.usage.tokens.toLocaleString()} tokens.`));
  let seen = summary.job ? summary.job.days_done : 0;
  onPoll = async () => { const now = summary.job ? summary.job.days_done : 0; if (now !== seen) { seen = now; await route(true); } };
}

// ---- Reports ----
async function pageReports() {
  const { items } = await api("/api/reports");
  const viewer = h("div", { class: "card" }, h("p", { class: "muted" }, "Select a report."));
  const LABELS = { memos: "Daily memos", notices: "Breach notices", restatements: "Restatements", reviews: "Monthly reviews" };
  const groups = Object.keys(LABELS).filter((k) => items.some((i) => i.kind === k));
  let kind = groups[0];
  let chosen = null;
  const list = h("div", { class: "card", style: "padding:0;overflow:hidden" });
  const tabs = h("div", { class: "tabs" });
  const show = guard(async (item) => {
    chosen = item.path;
    const { text } = await api(`/api/report?path=${encodeURIComponent(item.path)}`);
    viewer.replaceChildren(item.path.endsWith(".json") ? h("pre", { class: "code" }, JSON.stringify(JSON.parse(text), null, 1)) : markdown(text));
    render();
  });
  const render = () => {
    tabs.replaceChildren(...groups.map((g) => h("button", { class: g === kind ? "on" : "", onclick: () => { kind = g; render(); } }, `${LABELS[g]} (${items.filter((i) => i.kind === g).length})`)));
    list.replaceChildren(h("div", { class: "list" }, items.filter((i) => i.kind === kind).map((i) =>
      h("button", { class: i.path === chosen ? "on" : "", onclick: () => show(i) }, i.name))));
  };
  page.replaceChildren(
    h("div", { class: "row" }, h("h1", { class: "grow" }, "Reports"), h("a", { class: "btn", href: "/api/download", id: "download" }, "Download full output (ZIP)")),
    h("p", { class: "lede" }, "Everything released so far. The ZIP adds a period summary and the full audit tables."),
    items.length ? tabs : null,
    items.length ? h("div", { class: "split" }, list, viewer) : h("div", { class: "card" }, h("p", {}, "Nothing has been published yet.")));
  if (items.length) { render(); await show(items.find((i) => i.kind === kind)); }
}

// ---- Run inspector ----
async function pageRuns() {
  const { runs } = await api("/api/runs");
  const search = h("input", { type: "text", placeholder: "Filter, for example 2020-03 or awaiting", oninput: () => render() });
  const holder = h("div");
  const render = () => {
    const q = search.value.toLowerCase();
    const rows = runs.filter((r) => `${r.run_id} ${r.status} ${r.workflow}`.toLowerCase().includes(q));
    holder.replaceChildren(table(["Run", "Status", ">Rounds", "Notes", "Model"], rows.map((r) =>
      h("tr", { class: "click", onclick: () => { location.hash = `#/run/${r.run_id}`; } }, td(h("a", { href: `#/run/${r.run_id}` }, r.run_id)), td(status(r.status)), td(String(r.round + 1), 1),
        td(r.degraded ? "Needs extra care" : r.halted_reason || ""), td(r.llm)))));
  };
  page.replaceChildren(h("h1", {}, "Run inspector"), h("p", { class: "lede" }, "Every run, with its stages, checks and what each agent said."), h("div", { class: "card" }, search, h("div", { style: "height:12px" }), holder));
  render();
}

async function pageRunDetail(id) {
  const d = await api(`/api/run?id=${encodeURIComponent(id)}`);
  let tab = "Memo";
  const content = h("div");
  const tabs = h("div", { class: "tabs" });
  const views = {
    Memo: () => d.memo ? markdown(d.memo) : h("p", { class: "muted" }, "No memo for this run."),
    Checks: () => Object.keys(d.verification).length ? Object.entries(d.verification).map(([name, v]) => h("div", {},
      h("h3", {}, `Round ${Number(name.match(/r(\d+)/)[1]) + 1}: ${v.passed ? "passed" : "failed"}`),
      table(["Check", "Result", "Detail"], v.checks.map((c) => h("tr", {}, td(title(c.id)), td(status(c.passed ? "ok" : "failed")), td(c.detail)))))) : h("p", { class: "muted" }, "No checks ran."),
    "Data quality": () => d.dq && d.dq.items.length ? table(["Item", "Action", "Why"], d.dq.items.map((i) => h("tr", {}, td(i.id), td(title(i.action)), td(i.rationale)))) : h("p", { class: "muted" }, "No exceptions."),
    "Agent replies": () => d.llm_calls.length ? d.llm_calls.map((c) => h("div", {},
      h("h3", {}, `${title(c.role)} (${c.provider}: ${c.model}), ${c.tokens_in + c.tokens_out} tokens`), h("pre", { class: "code" }, c.response))) : h("p", { class: "muted" }, "No model calls."),
    Events: () => table(["When", "Stage", "Event", "Detail"], d.events.map((e) => h("tr", {}, td(e.sim_ts), td(e.stage || ""), td(title(e.type)), td(e.detail === "{}" ? "" : e.detail))), { tall: true }),
    Files: () => {
      const view = h("div");
      return [h("div", { class: "row" }, d.files.filter((f) => !f.endsWith(".csv")).map((f) => h("button", { class: "small", onclick: guard(async () => {
        const r = await api(`/api/file?run=${encodeURIComponent(id)}&name=${encodeURIComponent(f)}`);
        view.replaceChildren(h("h3", {}, f), h("pre", { class: "code" }, r.text));
      }) }, f))), view];
    },
  };
  const render = () => {
    tabs.replaceChildren(...Object.keys(views).map((t) => h("button", { class: t === tab ? "on" : "", onclick: () => { tab = t; render(); } }, t)));
    content.replaceChildren(...[views[tab]()].flat());
  };
  page.replaceChildren(
    h("p", { class: "small" }, h("a", { href: "#/runs" }, "‹ All runs")),
    h("div", { class: "row" }, h("h1", { class: "grow" }, id), status(d.run.status)),
    h("p", { class: "lede" }, `Cutoff ${d.run.cutoff}. Version ${d.run.version}. Model ${d.run.llm}. Started by ${d.run.trigger}.`),
    d.run.degraded ? h("div", { class: "notice warn" }, `The agents could not finish normally: ${d.run.degraded_reason}`) : null,
    d.run.halted_reason ? h("div", { class: "notice bad" }, d.run.halted_reason) : null,
    h("div", { class: "card" }, h("h2", {}, "Stages"), h("div", { class: "timeline" }, d.stages.map((s) =>
      h("div", { class: "stage" }, h("b", {}, s.round ? `${s.stage} (round ${s.round + 1})` : s.stage), status(s.status), s.attempts > 1 ? h("div", { class: "small muted" }, `${s.attempts} attempts`) : null)))),
    h("div", { class: "card" }, tabs, content));
  render();
}

// ---- Improve ----
async function pageImprove() {
  const d = await api("/api/improve");
  const busy = summary.job && summary.job.state === "running";
  const rows = d.candidates.map((c) => {
    const r = c.result;
    return h("tr", {}, td(h("div", {}, h("strong", {}, title(c.name)), h("div", { class: "small muted" }, c.hypothesis))),
      td(r ? String(r.scorecard.var_exceptions) : "", 1), td(r ? r.scorecard.kupiec_p.toFixed(4) : "", 1), td(r ? pct(r.scorecard.avg_var99) : "", 1),
      td(r ? h("div", {}, status(r.verdict.decision === "accept" ? "ok" : "failed"), h("div", { class: "small muted" }, r.verdict.decision === "accept" ? "Accepted" : r.verdict.reasons.join("; "))) : "Not run here"),
      td(h("button", { disabled: busy, onclick: guard(async () => { await api("/api/evaluate", { candidate: c.name }); toast("Evaluation started. It takes about 4 minutes."); await poll(); route(true); }) }, "Evaluate")));
  });
  const job = summary.job && summary.job.kind === "evaluate" ? summary.job : null;
  page.replaceChildren(
    h("h1", {}, "Improve"),
    h("p", { class: "lede" }, "A change goes live only by beating the fixed baseline under rules written before it was tested. Evaluation always replays the full year on the offline backend, so scorecards compare like with like."),
    job ? h("div", { class: `notice ${job.state === "failed" ? "bad" : "info"}` }, `Evaluating ${job.candidate}: ${job.state}. ${job.last_line || ""}`, job.error ? h("pre", { class: "code" }, job.error) : null) : null,
    h("div", { class: "card" }, h("div", { class: "row" }, h("div", { class: "grow" }, h("h2", { style: "margin:0" }, "Active version"), h("code", {}, d.active)),
      d.can_rollback ? h("button", { class: "danger", onclick: guard(async () => { if (confirm("Roll back to the previous version?")) { await api("/api/rollback", {}); route(true); } }) }, "Roll back") : null,
      d.can_promote.map((v) => h("button", { class: "primary", onclick: guard(async () => {
        if (confirm(`Promote ${v}? New runs in this workspace will use it.`)) { await api("/api/promote", { version: v }); route(true); }
      }) }, `Promote ${v}`)))),
    h("div", { class: "card" }, h("h2", {}, "Candidates"), table(["Change", ">Exceptions", ">Kupiec p", ">Average VaR", "Decision", ""], rows)),
    h("div", { class: "card" }, h("h2", {}, "Version history"), table(["Event", "Version", "Detail"], d.history.slice().reverse().map((e) =>
      h("tr", {}, td(title(e.event)), td(h("code", {}, e.version)), td(e.note || e.decision || e.by || ""))), { tall: true })),
    h("p", { class: "small muted" }, "These changes affect this workspace's copy of the version registry, not the repository's."));
  let state = job ? job.state : "";
  onPoll = async () => { const now = summary.job && summary.job.kind === "evaluate" ? summary.job.state : ""; if (now !== state) { state = now; await route(true); } };
}

// ---- Help ----
function pageHelp() {
  const step = (name, text) => h("div", { style: "margin-bottom:12px" }, h("strong", {}, name), h("div", { class: "muted" }, text));
  page.replaceChildren(h("h1", {}, "Help"),
    h("div", { class: "card" }, h("h2", {}, "Getting a full output"),
      step("1. Connect a model", "Enter your name, then choose Claude login, an API provider, or the offline demo. Test the connection."),
      step("2. Run the workflow", "Pick a period and who approves. Quick look or Crash month is a good first run."),
      step("3. Approve", "Read each flagged memo and decide. If you chose automatic approval, there is nothing to do here."),
      step("4. Collect the results", "The Dashboard shows the position, Reports holds everything released, and Download full output gives you a ZIP.")),
    h("div", { class: "card" }, h("h2", {}, "Good to know"),
      step("What is real", "Market returns are real, from the Ken French data library. The portfolio, limits and vendor faults are fictional."),
      step("Your key", "API keys stay on this computer. The app listens only on this machine, and a key is saved to disk only if you ask."),
      step("Stopping", "Stop is the same as a crash, and Resume continues without repeating finished work."),
      step("The agents cannot act", "They read data and write text. They have no tools that publish, trade or change anything."),
      step("Files", "Results are in runtime/web/ inside the project folder. Start over archives them rather than deleting.")));
}

// ---- Router ----
async function route(keep) {
  if (!keep) onPoll = null;
  const [, name, arg] = (location.hash || "#/connect").split("/");
  renderNav();
  try {
    if (name === "connect") pageConnect();
    else if (name === "run" && arg) await pageRunDetail(arg);
    else if (name === "run") pageRun();
    else if (name === "approvals") await pageApprovals();
    else if (name === "dashboard") await pageDashboard();
    else if (name === "reports") await pageReports();
    else if (name === "runs") await pageRuns();
    else if (name === "improve") await pageImprove();
    else if (name === "help") pageHelp();
    else pageConnect();
  } catch (e) {
    page.replaceChildren(h("div", { class: "notice bad" }, e.message));
  }
  if (!keep) window.scrollTo(0, 0);
}

(async function start() {
  [summary, catalog] = await Promise.all([api("/api/summary"), api("/api/catalog")]);
  if (!location.hash) location.hash = summary.settings.configured ? (Object.keys(summary.counts).length ? "#/dashboard" : "#/run") : "#/connect";
  // The menu button only shows on narrow screens. Choosing a page, or pressing Escape, closes it.
  const sidebar = document.getElementById("sidebar"), toggle = document.getElementById("menu-toggle");
  const setMenu = (open) => { sidebar.classList.toggle("open", open); toggle.setAttribute("aria-expanded", String(open)); };
  toggle.addEventListener("click", () => setMenu(!sidebar.classList.contains("open")));
  document.getElementById("nav").addEventListener("click", (e) => { if (e.target.closest("a")) setMenu(false); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sidebar.classList.contains("open")) { setMenu(false); toggle.focus(); }
  });
  window.addEventListener("hashchange", () => route());
  await route();
  setInterval(poll, 2000);
})();
