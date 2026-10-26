/* Public memorial page: tributes, candles, lightbox, and family editing. */
(function () {
  "use strict";
  const { api, me, h, toast, hasRole, initOverlays, confirmClick, remember } = window.MM;
  const $ = (id) => document.getElementById(id);
  initOverlays();

  // ---- Lightbox ----
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest("[data-full]");
    if (!t) return;
    const img = $("lightbox-img");
    img.src = t.getAttribute("data-full");
    img.alt = (t.querySelector("img") || t).getAttribute("alt") || "Photograph";
    $("lightbox").hidden = false;
  });

  // ---- Prefill names ----
  ["t-name", "c-name"].forEach((id) => { const el = $(id); if (el && !el.value) el.value = remember("name"); });

  function formError(statusEl, err) { statusEl.textContent = err.message; statusEl.className = "err"; }

  // ---- Tributes ----
  const tf = $("tribute-form");
  if (tf) tf.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const st = $("t-status"), btn = tf.querySelector("button[type=submit]");
    const body = { name: $("t-name").value.trim(), relation: $("t-rel").value.trim(), message: $("t-msg").value.trim(), website: $("t-website").value };
    if (!body.name || body.message.length < 2) { st.className = "err"; st.textContent = "Add your name and a few words."; return; }
    btn.disabled = true;
    try {
      const t = await api("POST", "/api/memorial/tributes", body);
      remember("name", body.name);
      $("t-msg").value = "";
      st.className = "hint";
      st.textContent = t.status === "approved" ? "Your tribute has been posted." : "Thank you. Your tribute will appear once the family has approved it.";
      if (t.status === "approved") setTimeout(() => location.reload(), 900);
    } catch (e) { formError(st, e); } finally { btn.disabled = false; }
  });

  // ---- Candles ----
  const cf = $("candle-form");
  if (cf) cf.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const st = $("c-status"), btn = cf.querySelector("button[type=submit]");
    const body = { name: $("c-name").value.trim(), note: $("c-note").value.trim(), website: $("c-website").value };
    if (!body.name) { st.className = "err"; st.textContent = "Add your name to light a candle."; return; }
    btn.disabled = true;
    try {
      const c = await api("POST", "/api/memorial/candles", body);
      remember("name", body.name);
      $("c-note").value = "";
      $("candle-list").prepend(h("div", { class: "candle" }, h("span", { class: "c", "aria-hidden": "true" }), h("span", null, h("strong", null, c.name), c.note ? " — " + c.note : "")));
      const cc = $("candle-count"); const n = Number(cc.dataset.count || 0) + 1; cc.dataset.count = n;
      cc.textContent = n + (n === 1 ? " candle lit" : " candles lit");
      st.className = "hint"; st.textContent = "Your candle is lit.";
    } catch (e) { formError(st, e); } finally { btn.disabled = false; }
  });

  // ---- Family editing ----
  (async function editorMode() {
    const user = await me();
    if (!user) return;
    const link = $("family-link"); if (link) link.textContent = "Family area";
    const isEditor = hasRole(user, "editor"), isOwner = user.roles.includes("owner");
    if (!isEditor) return;
    document.querySelectorAll(".editor-only").forEach((el) => { el.hidden = false; });
    let story = await api("GET", "/api/memorial/story");
    const entries = new Map();
    story.chapters.forEach((c) => c.entries.forEach((e) => entries.set(e.id, e)));

    document.querySelectorAll(".entry").forEach((art) => {
      const e = entries.get(art.dataset.entryId);
      if (!e || !(e.author_id === user.id || isOwner)) return;
      const edit = art.querySelector(".entry-edit"), del = art.querySelector(".entry-delete");
      edit.hidden = false; del.hidden = false;
      edit.addEventListener("click", () => openEntry(e.chapter_id, e));
      confirmClick(del, "Confirm remove", async () => {
        try { await api("DELETE", `/api/memorial/entries/${e.id}`); art.remove(); toast("Removed from the memorial"); }
        catch (err) { toast(err.message); }
      });
    });
    document.querySelectorAll(".chapter").forEach((sec) => {
      const ch = story.chapters.find((c) => c.id === sec.dataset.chapterId);
      if (!ch) return;
      sec.querySelector(".add-entry").addEventListener("click", () => openEntry(ch.id));
      sec.querySelector(".edit-chapter").addEventListener("click", () => openChapter(ch));
    });
    $("add-chapter").addEventListener("click", () => openChapter(null));
    $("edit-profile").addEventListener("click", openProfile);

    async function uploadPhoto(file) {
      const fd = new FormData(); fd.append("file", file);
      return (await api("POST", "/api/media/upload", fd)).id;
    }

    // Entry form
    let editing = null;
    function openEntry(chapterId, e) {
      editing = e || null;
      const sel = $("f-chapter");
      sel.replaceChildren(...story.chapters.map((c) => h("option", { value: c.id }, c.title)));
      sel.value = chapterId;
      $("entry-title").textContent = e ? "Edit memory" : "Add to her story";
      $("f-title").value = e ? e.title : ""; $("f-period").value = e ? e.period : ""; $("f-body").value = e ? e.body : "";
      $("f-caption").value = e ? e.caption : ""; $("f-photo").value = ""; $("f-remove").checked = false;
      $("f-remove-wrap").hidden = !(e && e.media_id);
      $("f-preview").hidden = !(e && e.media_id); if (e && e.media_id) $("f-preview").src = `/api/media/${e.media_id}/thumb`;
      $("f-name").value = e ? e.author_name : (remember("name") || user.display_name);
      $("f-rel").value = e ? e.relation : remember("relation");
      $("f-err").textContent = ""; $("entry-ov").hidden = false; $("f-body").focus();
    }
    $("f-photo").addEventListener("change", (ev) => {
      const f = ev.target.files[0];
      if (f) { $("f-preview").src = URL.createObjectURL(f); $("f-preview").hidden = false; }
    });
    $("entry-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const err = $("f-err"), btn = $("f-save"), file = $("f-photo").files[0];
      const body = {
        chapter_id: $("f-chapter").value, title: $("f-title").value.trim(), period: $("f-period").value.trim(),
        body: $("f-body").value.trim(), caption: $("f-caption").value.trim(),
        author_name: $("f-name").value.trim(), relation: $("f-rel").value.trim(),
      };
      if (!body.author_name) { err.textContent = "Add your name."; return; }
      if (!body.body && !body.title && !file && !(editing && editing.media_id)) { err.textContent = "Write a memory or choose a photograph first."; return; }
      btn.disabled = true;
      try {
        if (file) { err.textContent = "Uploading photograph…"; body.media_id = await uploadPhoto(file); }
        if (editing) {
          if ($("f-remove").checked && !file) body.remove_media = true;
          await api("PATCH", `/api/memorial/entries/${editing.id}`, body);
        } else {
          await api("POST", "/api/memorial/entries", body);
        }
        remember("name", body.author_name); remember("relation", body.relation);
        $("entry-ov").hidden = true; toast("Saved to the memorial");
        setTimeout(() => location.reload(), 500);
      } catch (e) { err.textContent = e.message; } finally { btn.disabled = false; }
    });

    // Chapter form
    let chEditing = null;
    function openChapter(c) {
      chEditing = c;
      $("chapter-form-title").textContent = c ? "Edit chapter" : "Add a new chapter";
      $("k-title").value = c ? c.title : ""; $("k-intro").value = c ? c.intro : "";
      $("k-hidden").checked = !!(c && c.hidden); $("k-hidden-wrap").hidden = !c;
      $("k-err").textContent = ""; $("chapter-ov").hidden = false; $("k-title").focus();
    }
    $("chapter-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const body = { title: $("k-title").value.trim(), intro: $("k-intro").value.trim() };
      if (!body.title) { $("k-err").textContent = "Give the chapter a title."; return; }
      try {
        if (chEditing) await api("PATCH", `/api/memorial/chapters/${chEditing.id}`, Object.assign(body, { hidden: $("k-hidden").checked }));
        else await api("POST", "/api/memorial/chapters", body);
        $("chapter-ov").hidden = true; toast("Chapter saved"); setTimeout(() => location.reload(), 500);
      } catch (e) { $("k-err").textContent = e.message; }
    });

    // Profile form
    const PF = ["full_name", "known_as", "born", "died", "birthplace", "resting_place", "epitaph", "service_date", "service_venue", "stream_url"];
    function openProfile() {
      const p = story.profile || {};
      PF.forEach((k) => { $("p-" + k).value = p[k] || ""; });
      $("p-portrait").value = ""; $("p-err").textContent = ""; $("profile-ov").hidden = false;
    }
    $("profile-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const body = {}; PF.forEach((k) => { body[k] = $("p-" + k).value.trim(); });
      body.portrait_media_id = (story.profile && story.profile.portrait_media_id) || null;
      try {
        const f = $("p-portrait").files[0];
        if (f) { $("p-err").textContent = "Uploading portrait…"; body.portrait_media_id = await uploadPhoto(f); }
        await api("PUT", "/api/memorial/profile", body);
        $("profile-ov").hidden = true; toast("Details saved"); setTimeout(() => location.reload(), 500);
      } catch (e) { $("p-err").textContent = e.message; }
    });
  })();
})();
