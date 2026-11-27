// NeuroMetric site: progressive enhancement only. No tracking, no cookies, no storage.
// Collapses the main navigation behind a button on narrow screens. Without JS the nav wraps.
(function () {
  "use strict";
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (!toggle || !nav) return;

  var narrow = window.matchMedia("(max-width: 62rem)");

  function setOpen(open) {
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    nav.setAttribute("data-open", open ? "true" : "false");
  }

  function sync() {
    // Wide screens always show the nav; narrow screens start collapsed.
    setOpen(!narrow.matches);
  }

  toggle.addEventListener("click", function () {
    setOpen(toggle.getAttribute("aria-expanded") !== "true");
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && narrow.matches && toggle.getAttribute("aria-expanded") === "true") {
      setOpen(false);
      toggle.focus();
    }
  });

  if (narrow.addEventListener) narrow.addEventListener("change", sync);
  else if (narrow.addListener) narrow.addListener(sync);
  sync();
})();
