// The itinerary check report: verdict, map, findings and a per-day list of
// what was checked. Shared by the home page (after a check or a plan), the
// shared report page (check.html) and the shared plan page (plan.html).
(() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const safeUrl = (u) => (/^https?:\/\//.test(u || "") ? u : "");
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  // One colour per day, repeated after seven.
  const DAY_COLOURS = ["#ff3d77", "#7c3cff", "#1f9d6b", "#ff7a3d", "#0ea5e9", "#b45309", "#d23bdb"];
  const dayColour = (n) => DAY_COLOURS[(Math.max(n, 1) - 1) % DAY_COLOURS.length];

  // "2026-12-14" -> "14 Dec"
  const niceDate = (isoDate) => {
    const d = new Date(`${isoDate}T12:00:00`);
    return Number.isNaN(d.getTime()) ? isoDate : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  };

  // 160 -> "2 h 40"
  const duration = (minutes) => {
    const h = Math.floor(minutes / 60);
    const m = String(minutes % 60).padStart(2, "0");
    return h ? `${h} h ${m}` : `${minutes} min`;
  };

  const STATUS = {
    found: ["ok", "📍 On the map"],
    far: ["warn", "↔ Far from this day"],
    web: ["unknown", "Online only, not on the map"],
    no_trace: ["bad", "No trace found"],
    not_found: ["warn", "Not found on the map"],
    unchecked: ["unknown", "Not checked"],
  };
  const LEVEL = { problem: ["bad", "Problem"], warning: ["warn", "Check"], note: ["info", "Note"] };

  function verdict(s) {
    if (s.problems) return ["bad", `${plural(s.problems, "problem")} to fix`];
    if (s.warnings) return ["warn", `${plural(s.warnings, "thing")} to double-check`];
    return ["ok", "No problems found in what we could check"];
  }

  function chips(s) {
    const onMap = s.confirmed + (s.far || 0);
    const out = [`<span class="chip">${onMap} of ${s.places} places found on the map</span>`];
    if (s.far) out.push(`<span class="chip warn">${s.far} far from their day</span>`);
    if (s.no_trace) out.push(`<span class="chip bad">${s.no_trace} with no trace</span>`);
    if (s.online_only) out.push(`<span class="chip">${s.online_only} online only</span>`);
    if (s.sights) out.push(`<span class="chip">Opening days checked for ${s.hours_checked} of ${plural(s.sights, "sight")}</span>`);
    return out.join("");
  }

  function hoursLine(stop) {
    if (stop.kind !== "sight" || !stop.hours_status) return "";
    if (stop.hours_status !== "ok") return `<span class="muted">Opening days not verified</span>`;
    const closed = stop.closed_days && stop.closed_days.length
      ? `Closed ${esc(stop.closed_days.join(", "))}` : "Open every day";
    const src = stop.hours_source === "OpenStreetMap" ? " (OpenStreetMap)"
      : safeUrl(stop.hours_source) ? ` (<a href="${esc(stop.hours_source)}" target="_blank" rel="noopener">source</a>)` : "";
    return `<span>${closed}${stop.hours ? ` · ${esc(stop.hours)}` : ""}${src}</span>`;
  }

  function stopRow(stop) {
    const [cls, label] = STATUS[stop.status] || STATUS.unchecked;
    const badge = stop.osm_url && safeUrl(stop.osm_url)
      ? `<a class="pill ${cls}" href="${esc(stop.osm_url)}" target="_blank" rel="noopener">${label}</a>`
      : stop.status === "web" && safeUrl(stop.web_source)
        ? `<a class="pill ${cls}" href="${esc(stop.web_source)}" target="_blank" rel="noopener">${label}</a>`
        : `<span class="pill ${cls}">${label}</span>`;
    const far = stop.status === "far" ? ` <span class="muted small">~${esc(stop.distance_km)} km away${stop.where ? `, in ${esc(stop.where)}` : ""}</span>` : "";
    const moved = stop.moved_from != null ? ` <span class="pill moved">↪ Moved from Day ${esc(stop.moved_from)}</span>` : "";
    const hours = hoursLine(stop);
    const query = stop.lat != null ? `${stop.lat},${stop.lon}` : `${stop.name} ${stop.city || ""}`.trim();
    const maps = `<a class="maps" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}" target="_blank" rel="noopener">Google Maps ↗</a>`;
    return `<li><span class="stop-name">${esc(stop.name)}</span> ${badge}${moved}${far} ${maps}
      ${hours ? `<div class="small">${hours}</div>` : ""}</li>`;
  }

  function dayBlocks(report) {
    return report.days.map((day) => {
      const stops = report.stops.filter((s) => s.day === day.number);
      if (!stops.length) return "";
      const when = day.weekday ? ` · ${esc(day.weekday)} ${esc(niceDate(day.date))}` : "";
      const road = day.drive_minutes
        ? `<span class="pill ${day.drive_minutes >= 120 ? "warn" : "unknown"}">🚗 ${esc(duration(day.drive_minutes))} by road · ${esc(day.drive_km)} km</span>` : "";
      // The day's route in Google Maps, through the stops that were located.
      const placed = stops.filter((s) => s.lat != null && s.status !== "far").slice(0, 10);
      const point = (s) => `${s.lat},${s.lon}`;
      const route = placed.length >= 2
        ? `<a class="maps" href="https://www.google.com/maps/dir/?api=1&origin=${point(placed[0])}&destination=${point(placed[placed.length - 1])}${placed.length > 2 ? `&waypoints=${placed.slice(1, -1).map(point).join("%7C")}` : ""}" target="_blank" rel="noopener">Open this day's route ↗</a>` : "";
      const holiday = day.holiday ? `<span class="pill warn">Public holiday: ${esc(day.holiday)}</span>` : "";
      return `<div class="day-block">
        <h3><span class="dot" style="background:${dayColour(day.number)}"></span>Day ${esc(day.number)}${when}${day.city ? ` · ${esc(day.city)}` : ""} ${holiday} ${road} ${route}</h3>
        <ul class="stops">${stops.map(stopRow).join("")}</ul></div>`;
    }).join("");
  }

  function issueList(issues) {
    if (!issues.length) return "";
    return `<ul class="issues">${issues.map((i) => {
      const [cls, label] = LEVEL[i.level] || LEVEL.note;
      const src = safeUrl(i.source) ? ` <a href="${esc(i.source)}" target="_blank" rel="noopener">Source</a>` : "";
      return `<li class="issue ${cls}"><span class="pill ${cls}">${label}</span>
        <strong>${esc(i.title)}</strong><div class="small">${esc(i.detail)}${src}</div></li>`;
    }).join("")}</ul>`;
  }

  function drawMap(report, node) {
    if (!window.L) return;
    const placed = report.stops.filter((s) => s.lat != null && s.lon != null);
    if (!placed.length) { node.hidden = true; return; }
    const map = L.map(node, { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    const bounds = [];
    for (const stop of placed) {
      const far = stop.status === "far";
      const icon = L.divIcon({
        className: "",
        html: `<span class="pin${far ? " far" : ""}" style="background:${dayColour(stop.day)}">${esc(stop.day)}</span>`,
        iconSize: [26, 26], iconAnchor: [13, 13],
      });
      L.marker([stop.lat, stop.lon], { icon }).addTo(map)
        .bindPopup(`<strong>${esc(stop.name)}</strong><br>Day ${esc(stop.day)}${far ? `<br>~${esc(stop.distance_km)} km from ${esc(stop.city)}` : ""}`);
      bounds.push([stop.lat, stop.lon]);
    }
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
    setTimeout(() => map.invalidateSize(), 60);
  }

  // Render `report` into `el`. Options: { title } to change the heading.
  window.renderReport = (report, el, options = {}) => {
    if (!el) return;
    if (!report || !report.summary) { el.hidden = true; return; }
    const s = report.summary;
    const [cls, headline] = verdict(s);
    const notes = (report.notes || []).map((n) => `<p class="muted small">${esc(n)}</p>`).join("");
    const b = options.before;
    const before = b
      ? `<p class="before-after">Before: <s>${plural(b.problems, "problem")}, ${b.warnings} to double-check</s>
         → now: <strong>${plural(s.problems, "problem")}, ${s.warnings} to double-check</strong></p>` : "";
    el.innerHTML = `
      ${options.title ? `<h2>${esc(options.title)}</h2>` : ""}
      ${before}
      <div class="verdict ${cls}"><strong>${headline}</strong><div class="chips">${chips(s)}</div></div>
      <div class="map report-map"></div>
      ${issueList(report.issues || [])}
      <details class="by-day" open><summary>What was checked, day by day</summary>${dayBlocks(report)}</details>
      ${notes}
      <p class="muted small">Places are looked up on OpenStreetMap, and opening days on OpenStreetMap or a published page.
      Distances are straight lines. This check can't see strikes, renovations, sold-out tickets or prices, and hours change:
      confirm what matters before you go.</p>
      <p class="feedback small">Was this check right?
        <button type="button" data-vote="up">👍 Yes</button>
        <button type="button" data-vote="down">👎 Something's off</button></p>`;
    el.hidden = false;
    drawMap(report, el.querySelector(".report-map"));
    el.querySelectorAll(".feedback button").forEach((button) => button.addEventListener("click", () => {
      fetch("/api/feedback", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vote: button.dataset.vote }),
      }).catch(() => {});
      el.querySelector(".feedback").textContent = button.dataset.vote === "up"
        ? "Thanks. Glad it helped."
        : "Thanks. If a finding is wrong, use “Report a problem” below so we can fix it.";
    }));
  };

  // Copy `text`, show "Copied" on the button, and fall back to a prompt.
  window.copyText = async (text, button, done = "✓ Copied") => {
    const label = button.textContent;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = done;
    } catch {
      prompt("Copy this:", text);
    }
    setTimeout(() => { button.textContent = label; }, 2500);
  };
})();
