/* Shared helpers: API calls with automatic session refresh, DOM building, toasts, overlays. */
(function () {
  "use strict";

  class ApiError extends Error {
    constructor(status, message, errors) { super(message); this.status = status; this.errors = errors || []; }
  }

  let refreshing = null;
  async function refresh() {
    if (!refreshing) {
      refreshing = fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" })
        .then((r) => r.ok).finally(() => { setTimeout(() => { refreshing = null; }, 0); });
    }
    return refreshing;
  }

  async function api(method, url, body, opts) {
    opts = opts || {};
    const init = { method, credentials: "same-origin", headers: Object.assign({ Accept: "application/json" }, opts.headers || {}) };
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) { init.body = JSON.stringify(body); init.headers["Content-Type"] = "application/json"; }
    let r;
    try { r = await fetch(url, init); }
    catch (e) { throw new ApiError(0, "You seem to be offline. Check your connection and try again."); }
    if (r.status === 401 && !opts.noRefresh && !url.startsWith("/api/auth/")) {
      if (await refresh()) return api(method, url, body, Object.assign({}, opts, { noRefresh: true }));
    }
    if (r.status === 204) return null;
    let data = null;
    try { data = await r.json(); } catch (e) { /* non-JSON */ }
    if (!r.ok) {
      let msg = (data && data.detail) || "Something went wrong. Please try again.";
      if (data && data.errors && data.errors.length) msg += " " + data.errors.map((e) => e.message).join(" ");
      throw new ApiError(r.status, msg, data && data.errors);
    }
    return data;
  }

  async function me() {
    try { return await api("GET", "/api/auth/me"); }
    catch (e) {
      if (e.status === 401 && (await refresh())) { try { return await api("GET", "/api/auth/me"); } catch (_) { return null; } }
      return null;
    }
  }

  function h(tag, attrs) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "class") el.className = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (let i = 2; i < arguments.length; i++) {
      const kids = [].concat(arguments[i]);
      for (const c of kids) if (c != null && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }

  function toast(msg) {
    const t = document.getElementById("toast");
    if (!t) return;
    t.textContent = msg; t.hidden = false;
    clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 3200);
  }

  function hasRole(user, role) { return !!user && (user.roles.includes("owner") || user.roles.includes(role)); }

  function initOverlays() {
    document.querySelectorAll(".overlay").forEach((o) => {
      o.addEventListener("click", (ev) => {
        if (ev.target === o || (ev.target.hasAttribute && ev.target.hasAttribute("data-close")) || o.classList.contains("lightbox")) o.hidden = true;
      });
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") document.querySelectorAll(".overlay").forEach((o) => { o.hidden = true; });
    });
  }

  function confirmClick(btn, label, action) {
    btn.addEventListener("click", async () => {
      if (!btn.dataset.armed) {
        btn.dataset.armed = "1"; const orig = btn.textContent; btn.textContent = label;
        setTimeout(() => { delete btn.dataset.armed; btn.textContent = orig; }, 4000);
        return;
      }
      delete btn.dataset.armed;
      await action();
    });
  }

  function remember(k, v) { try { if (v === undefined) return localStorage.getItem("mm." + k) || ""; localStorage.setItem("mm." + k, v); } catch (e) { return ""; } }

  function newKey() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, "");
    const a = new Uint8Array(16); crypto.getRandomValues(a);
    return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  window.MM = { api, me, h, toast, hasRole, initOverlays, confirmClick, remember, newKey, ApiError };
})();
