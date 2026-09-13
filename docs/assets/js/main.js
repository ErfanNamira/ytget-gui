/* YTGet website - small vanilla helper script (no build step, no deps) */
(function () {
  "use strict";

  var REPO = "ErfanNamira/ytget-gui";
  var RELEASES = "https://github.com/" + REPO + "/releases";
  var API = "https://api.github.com/repos/" + REPO + "/releases/latest";

  /* ---------- mobile nav ---------- */
  var toggle = document.querySelector(".nav-toggle");
  var links = document.querySelector(".nav-links");
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    links.addEventListener("click", function (e) {
      if (e.target.tagName === "A") links.classList.remove("open");
    });
  }

  /* ---------- current year ---------- */
  var year = document.querySelector("[data-year]");
  if (year) year.textContent = String(new Date().getFullYear());

  /* ---------- release data ---------- */
  function bytes(n) {
    if (!n && n !== 0) return "";
    var mb = n / 1048576;
    return mb >= 1 ? mb.toFixed(1) + " MB" : Math.round(n / 1024) + " KB";
  }

  function pick(assets, test) {
    for (var i = 0; i < assets.length; i++) {
      if (test.test(assets[i].name)) return assets[i];
    }
    return null;
  }

  function setLink(sel, asset, label) {
    var el = document.querySelector(sel);
    if (!el) return;
    if (asset) {
      el.href = asset.browser_download_url;
      var size = el.querySelector("[data-size]");
      if (size) size.textContent = bytes(asset.size);
      el.removeAttribute("data-pending");
    } else if (label) {
      el.href = RELEASES + "/latest";
    }
  }

  function fill(data) {
    var tag = (data.tag_name || "").replace(/^v/i, "");
    var assets = data.assets || [];

    document.querySelectorAll("[data-version]").forEach(function (el) {
      if (tag) el.textContent = el.getAttribute("data-version-prefix") ? "v" + tag : tag;
    });

    var date = document.querySelector("[data-published]");
    if (date && data.published_at) {
      date.textContent = new Date(data.published_at).toLocaleDateString(
        document.documentElement.lang || "en",
        { year: "numeric", month: "short", day: "numeric" }
      );
    }

    var notes = document.querySelector("[data-notes-link]");
    if (notes && data.html_url) notes.href = data.html_url;

    setLink("[data-dl-installer]", pick(assets, /setup\.exe$/i), true);
    setLink("[data-dl-zip]", pick(assets, /windows.*\.zip$/i) || pick(assets, /\.zip$/i), true);
    setLink("[data-dl-7z]", pick(assets, /\.7z$/i), true);

    var total = 0;
    for (var i = 0; i < assets.length; i++) total += assets[i].download_count || 0;
    var counter = document.querySelector("[data-downloads]");
    if (counter && total > 0) counter.textContent = total.toLocaleString();
  }

  if (window.fetch) {
    fetch(API, { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) {
        return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status));
      })
      .then(fill)
      .catch(function () {
        /* GitHub API unreachable or rate limited: the static fallback links still work. */
      });
  }
})();
