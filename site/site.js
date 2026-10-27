// moosewear: the few things a static page can't know at build time.
(() => {
  const pad = (n) => String(n).padStart(2, "0");
  const now = new Date();
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

  // The calendar was built on push day; the viewer's today moves on.
  for (const cell of document.querySelectorAll(".cal-day[data-date]")) {
    const day = cell.dataset.date;
    if (day === today) cell.classList.add("is-today");
    else if (day > today && !cell.classList.contains("has-fit")) cell.classList.add("is-future");
  }

  for (const label of document.querySelectorAll("[data-latest]")) {
    if (label.dataset.latest === today) label.textContent = "Today’s fit";
  }

  // ← → flip through days (or months).
  document.addEventListener("keydown", (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (e.target.closest("input, textarea, select, [contenteditable]")) return;
    const rel = { ArrowLeft: "prev", ArrowRight: "next" }[e.key];
    const link = rel && document.querySelector(`a[rel~="${rel}"]`);
    if (link) location.href = link.href;
  });
})();
