// "What we checked" card: shows, for each attraction in the plan, whether it
// was found on OpenStreetMap and whether its opening days were checked.
// Shared by the planner page (app.js) and the share page (plan.html).
window.renderChecks = (checks, el) => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const safeUrl = (u) => (/^https?:\/\//.test(u || "") ? u : "");
  if (!el) return;
  if (!checks || !checks.length) { el.hidden = true; return; }

  const status = {
    ok: ["ok", "🕘 Opening days checked"],
    moved: ["moved", "↪ Moved off a day it's closed"],
    warning: ["warn", "⚠️ May be closed that day"],
    unverified: ["unknown", "Hours not verified, check before going"],
  };
  const rows = checks.map((c) => {
    const [cls, label] = status[c.status] || status.unverified;
    const map = c.on_map && safeUrl(c.osm_url)
      ? `<a class="pill" href="${esc(c.osm_url)}" target="_blank" rel="noopener">📍 On the map</a>`
      : `<span class="pill unknown">Not found on the map</span>`;
    const closed = c.closed_days && c.closed_days.length ? `Closed ${esc(c.closed_days.join(", "))}. ` : "";
    const hours = c.hours ? `${esc(c.hours)}. ` : "";
    const src = c.source === "OpenStreetMap"
      ? "Source: OpenStreetMap"
      : safeUrl(c.source) ? `<a href="${esc(c.source)}" target="_blank" rel="noopener">Source</a>` : "";
    const days = c.days && c.days.length ? ` <span class="muted">· Day ${esc(c.days.join(", "))}</span>` : "";
    return `<li><strong>${esc(c.name)}</strong>${days}
      <div class="check-badges">${map} <span class="pill ${cls}">${label}</span></div>
      ${closed || hours || src ? `<div class="small muted">${closed}${hours}${src}</div>` : ""}</li>`;
  }).join("");
  el.innerHTML = `<h2>✅ What we checked</h2>
    <p class="muted small">Every attraction in your plan, checked against OpenStreetMap and published opening hours.
    Hours change, so confirm anything marked "not verified".</p>
    <ul class="checks">${rows}</ul>`;
  el.hidden = false;
};
