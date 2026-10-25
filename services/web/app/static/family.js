/* Family dashboard: sign in, approve tributes, invite family, contributions ledger, account. */
(function () {
  "use strict";
  const { api, me, h, toast, hasRole, initOverlays, confirmClick } = window.MM;
  const $ = (id) => document.getElementById(id);
  const fmt = (d) => (d ? new Date(d).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
  const kes = (n) => (n == null ? "—" : "KES " + Number(n).toLocaleString());
  const ROLE_NAMES = { owner: "Owner", editor: "Editor", treasurer: "Treasurer" };
  initOverlays();
  let user = null;

  async function start() {
    user = await me();
    if (!user) { $("login-form").hidden = false; $("dash").hidden = true; return; }
    $("login-form").hidden = true; $("dash").hidden = false;
    $("me-name").textContent = user.display_name;
    $("me-roles").textContent = "(" + user.roles.map((r) => ROLE_NAMES[r] || r).join(", ") + ")";
    document.querySelectorAll("[data-role]").forEach((b) => { b.hidden = !hasRole(user, b.dataset.role); });
    const wanted = location.hash.replace("#", "");
    const tab = document.querySelector(`[data-tab="${wanted}"]:not([hidden])`) || document.querySelector("[data-tab=tributes]");
    select(tab.dataset.tab);
  }

  // ---- Tabs ----
  document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => select(b.dataset.tab)));
  function select(name) {
    document.querySelectorAll("[data-tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    document.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== name; });
    history.replaceState(null, "", "#" + name);
    ({ tributes: loadTributes, people: loadPeople, ledger: loadLedger, account: () => {} })[name]();
  }

  // ---- Sign in / out ----
  $("login-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("l-err").textContent = "";
    try { await api("POST", "/api/auth/login", { email: $("l-email").value.trim(), password: $("l-password").value }); $("l-password").value = ""; await start(); }
    catch (e) { $("l-err").textContent = e.message; }
  });
  $("logout").addEventListener("click", async () => { try { await api("POST", "/api/auth/logout"); } catch (e) { /* ignore */ } location.href = "/"; });

  // ---- Tributes ----
  async function loadTributes() {
    const list = $("pending-list");
    try {
      const rows = await api("GET", "/api/memorial/tributes?status=pending");
      list.replaceChildren();
      if (!rows.length) { list.append(h("p", { class: "empty" }, "Nothing waiting. New tributes from visitors will appear here.")); return; }
      rows.forEach((t) => {
        const card = h("article", { class: "tribute" },
          h("p", { class: "msg" }, t.message),
          h("div", { class: "byline" }, h("span", null, h("strong", null, t.name), t.relation ? ", " + t.relation : ""), h("span", null, "· " + fmt(t.created_at))),
          h("div", { class: "form-actions" },
            h("button", { class: "btn small", type: "button", onclick: () => moderate(t.id, "approved", card) }, "Approve"),
            h("button", { class: "btn small ghost", type: "button", onclick: () => moderate(t.id, "rejected", card) }, "Don't publish")));
        list.append(card);
      });
    } catch (e) { list.replaceChildren(h("p", { class: "err" }, e.message)); }
  }
  async function moderate(id, status, card) {
    try { await api("POST", `/api/memorial/tributes/${id}/moderate`, { status }); card.remove(); toast(status === "approved" ? "Tribute published" : "Tribute won't be published"); }
    catch (e) { toast(e.message); }
  }

  // ---- People ----
  async function loadPeople() {
    try {
      const [users, invites] = await Promise.all([api("GET", "/api/auth/users"), api("GET", "/api/auth/invitations")]);
      $("users-body").replaceChildren(...users.map((u) => {
        const act = h("button", { class: "btn link danger", type: "button" }, u.is_active ? "Remove access" : "Restore access");
        if (u.id !== user.id) confirmClick(act, "Confirm", async () => {
          try { await api("PATCH", `/api/auth/users/${u.id}`, { is_active: !u.is_active }); loadPeople(); } catch (e) { toast(e.message); }
        });
        return h("tr", null, h("td", null, u.display_name), h("td", null, u.email), h("td", null, u.roles.map((r) => ROLE_NAMES[r]).join(", ")),
          h("td", null, fmt(u.last_login_at)), h("td", null, u.id === user.id ? "You" : u.is_active ? act : h("span", null, "No access ", act)));
      }));
      $("invites-body").replaceChildren(...invites.map((i) => {
        const state = i.accepted_at ? "Accepted" : i.revoked_at ? "Cancelled" : new Date(i.expires_at) < new Date() ? "Expired" : "Waiting";
        const cancel = state === "Waiting" ? h("button", { class: "btn link danger", type: "button" }, "Cancel") : null;
        if (cancel) confirmClick(cancel, "Confirm cancel", async () => { await api("DELETE", `/api/auth/invitations/${i.id}`); loadPeople(); });
        return h("tr", null, h("td", null, i.email), h("td", null, i.roles.map((r) => ROLE_NAMES[r]).join(", ")), h("td", null, state), h("td", null, cancel));
      }));
    } catch (e) { toast(e.message); }
  }
  $("invite-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("i-err").textContent = "";
    const roles = [...document.querySelectorAll("input[name=role]:checked")].map((c) => c.value);
    try {
      const r = await api("POST", "/api/auth/invitations", { email: $("i-email").value.trim(), display_name: $("i-name").value.trim(), roles });
      $("invite-url").value = r.invite_url; $("invite-result").hidden = false; $("invite-hint").hidden = false;
      $("i-email").value = ""; $("i-name").value = ""; loadPeople();
    } catch (e) { $("i-err").textContent = e.message; }
  });
  $("copy-invite").addEventListener("click", async () => {
    const input = $("invite-url");
    try { await navigator.clipboard.writeText(input.value); toast("Link copied"); } catch (e) { input.select(); toast("Select the link and copy it"); }
  });

  // ---- Ledger ----
  let reviewing = null;
  async function loadLedger() {
    try {
      const data = await api("GET", "/api/contributions/ledger");
      const bs = data.by_status;
      $("ledger-kpis").replaceChildren(
        h("div", null, h("span", { class: "label" }, "Confirmed total"), h("span", { class: "v" }, kes(data.total_confirmed))),
        h("div", null, h("span", { class: "label" }, "Confirmed"), h("span", { class: "v" }, bs.confirmed || 0)),
        h("div", null, h("span", { class: "label" }, "Waiting on M-Pesa"), h("span", { class: "v" }, (bs.pending || 0) + (bs.verifying || 0))),
        h("div", null, h("span", { class: "label" }, "Needs review"), h("span", { class: "v" }, bs.mismatch || 0)));
      $("ledger-body").replaceChildren(...data.rows.map((r) => {
        const review = (r.status === "mismatch" || (r.status === "confirmed" && r.method !== "mpesa_stk"))
          ? h("button", { class: "btn link", type: "button", onclick: () => openReview(r) }, "Review") : null;
        return h("tr", null, h("td", null, fmt(r.created_at)), h("td", null, r.contributor_name),
          h("td", null, { mpesa_stk: "M-Pesa prompt", mpesa_manual: "M-Pesa direct", cash: "Cash", bank: "Bank" }[r.method] || r.method),
          h("td", null, h("span", { class: "pill " + r.status }, r.status)),
          h("td", { class: "num" }, kes(r.amount_received != null ? r.amount_received : r.amount_requested)),
          h("td", null, r.mpesa_receipt || r.reference || "—"), h("td", null, r.phone_masked || "—"), h("td", null, review));
      }));
    } catch (e) { toast(e.message); }
  }
  function openReview(r) {
    reviewing = r;
    $("review-summary").textContent = `${r.contributor_name}: requested ${kes(r.amount_requested)}, received ${kes(r.amount_received)} (${r.status}).`;
    $("r-to").replaceChildren(...(r.status === "mismatch"
      ? [h("option", { value: "confirmed" }, "Confirm: the amount was received"), h("option", { value: "void" }, "Withdraw this entry")]
      : [h("option", { value: "void" }, "Withdraw this entry")]));
    $("r-note").value = ""; $("r-err").textContent = ""; $("review-ov").hidden = false;
  }
  $("review-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try { await api("POST", `/api/contributions/${reviewing.id}/review`, { to: $("r-to").value, note: $("r-note").value.trim() }); $("review-ov").hidden = true; toast("Decision saved"); loadLedger(); }
    catch (e) { $("r-err").textContent = e.message; }
  });
  $("manual-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("m-err").textContent = "";
    const amount = Number(String($("m-amount").value).replace(/[,\s]/g, ""));
    if (!Number.isInteger(amount) || amount <= 0) { $("m-err").textContent = "Enter the amount in whole shillings."; return; }
    try {
      await api("POST", "/api/contributions/manual", { method: $("m-method").value, amount, name: $("m-name").value.trim(), reference: $("m-ref").value.trim(), show_name: $("m-show").checked });
      ev.target.reset(); toast("Contribution recorded"); loadLedger();
    } catch (e) { $("m-err").textContent = e.message; }
  });

  // ---- Account ----
  $("password-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("pw-err").textContent = "";
    try {
      await api("POST", "/api/auth/password", { current_password: $("pw-current").value, new_password: $("pw-new").value });
      toast("Password changed. Please sign in again."); setTimeout(() => { location.reload(); }, 1200);
    } catch (e) { $("pw-err").textContent = e.message; }
  });

  start();
})();
