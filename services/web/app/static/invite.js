/* Accept an invitation. The token travels in the URL fragment, so it never reaches server logs. */
(function () {
  "use strict";
  const { api } = window.MM;
  const $ = (id) => document.getElementById(id);
  const token = decodeURIComponent(location.hash.slice(1));
  history.replaceState(null, "", "/invite");

  function bad(msg) { $("inv-loading").hidden = true; $("inv-bad").hidden = false; $("inv-bad").textContent = msg; }

  (async function () {
    if (!token) return bad("This invitation link is incomplete. Open the full link you were sent.");
    try {
      const info = await api("GET", "/api/auth/invitations/lookup?token=" + encodeURIComponent(token));
      $("inv-loading").hidden = true; $("accept-form").hidden = false;
      $("inv-email").textContent = info.email; $("a-name").value = info.display_name || "";
    } catch (e) { bad(e.message); }
  })();

  $("accept-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("a-err").textContent = "";
    try {
      await api("POST", "/api/auth/invitations/accept", { token, display_name: $("a-name").value.trim(), password: $("a-password").value });
      location.href = "/";
    } catch (e) { $("a-err").textContent = e.message; }
  });
})();
