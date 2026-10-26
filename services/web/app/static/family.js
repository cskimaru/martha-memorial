/* Family dashboard: sign in, approve tributes, invite family, account. */
(function () {
  "use strict";
  const { api, me, h, toast, hasRole, initOverlays, confirmClick } = window.MM;
  const $ = (id) => document.getElementById(id);
  const fmt = (d) => (d ? new Date(d).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
  const ROLE_NAMES = { owner: "Owner", editor: "Editor" };
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
    ({ tributes: loadTributes, people: loadPeople, account: () => {} })[name]();
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
