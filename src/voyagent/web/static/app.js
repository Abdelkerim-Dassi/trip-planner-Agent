// ReelTrip planner page: discover TikTok spots, let the traveller keep or skip
// them, then run the crew and render the finished plan.
(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("trip-form");
  const show = (el, on = true) => { el.hidden = !on; };
  const TICKERS = [
    "Comparing destinations…", "Reading local guides…", "Checking the season…",
    "Grouping places by neighbourhood…", "Pricing transfers…", "Adding buffer time…",
    "Double-checking opening days…",
  ];

  let map = null;
  let spots = [];      // every spot shown, with a .keep flag
  let request = null;  // the trip form values
  let planId = null;
  let planText = "";

  // Default dates: a week, starting a month from now.
  const iso = (d) => d.toISOString().slice(0, 10);
  const start = new Date(Date.now() + 30 * 864e5);
  form.start.value = iso(start);
  form.end.value = iso(new Date(start.getTime() + 6 * 864e5));
  form.start.min = form.end.min = iso(new Date());

  async function api(path, body) {
    const res = await fetch(path, body === undefined ? {} : {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join(", ") : data.detail;
      throw new Error(detail || `Request failed (${res.status})`);
    }
    return data;
  }

  function fail(message) {
    $("form-error").textContent = message;
    show($("form-error"));
    $("go").disabled = false;
  }

  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));

  // --- Discovery ---------------------------------------------------------------

  function ensureMap() {
    if (map) return map;
    map = L.map("map", { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    return map;
  }

  function renderSpots(results) {
    const box = $("spots");
    box.innerHTML = "";
    spots = [];
    const m = ensureMap();
    const bounds = [];
    const notes = [];

    for (const group of results) {
      notes.push(...(group.notes || []));
      if (!group.spots.length) continue;
      const title = document.createElement("p");
      title.className = "group-title";
      title.textContent = `${group.destination} · from ${group.videos.length} TikTok videos`;
      box.appendChild(title);

      for (const spot of group.spots) {
        spot.keep = true;
        spots.push(spot);
        const card = document.createElement("div");
        card.className = "spot";
        const away = spot.distance_km ? ` · ~${Math.round(spot.distance_km)} km from ${escapeHtml(group.destination)}` : "";
        const vids = spot.videos.slice(0, 3)
          .map((u, i) => `<a href="${escapeHtml(u)}" target="_blank" rel="noopener">▶ video ${i + 1}</a>`).join("");
        card.innerHTML = `
          <h3>${escapeHtml(spot.name)}</h3>
          <p class="why">${escapeHtml(spot.why)}</p>
          <p class="meta"><span class="pill">✓ on the map</span> ${spot.mentions} video${spot.mentions > 1 ? "s" : ""}${away}</p>
          <p class="vids">${vids}</p>
          <label class="check"><input type="checkbox" checked> Include in my trip</label>`;
        card.querySelector("input").addEventListener("change", (e) => {
          spot.keep = e.target.checked;
          card.classList.toggle("skipped", !spot.keep);
          updateBuildButton();
        });
        box.appendChild(card);

        if (spot.lat != null) {
          bounds.push([spot.lat, spot.lon]);
          L.marker([spot.lat, spot.lon]).addTo(m)
            .bindPopup(`<strong>${escapeHtml(spot.name)}</strong><br>${escapeHtml(spot.why)}`);
        }
      }

      // Places the videos name that OpenStreetMap couldn't confirm: worth
      // knowing about, but kept out of the plan.
      if (group.unverified && group.unverified.length) {
        const also = document.createElement("p");
        also.className = "also muted small";
        also.textContent = `Also mentioned (not confirmed on the map yet): ${group.unverified.join(", ")}`;
        box.appendChild(also);
      }
    }

    if (bounds.length) m.fitBounds(bounds, { padding: [30, 30], maxZoom: 11 });
    else m.setView([30, 10], 3);
    setTimeout(() => m.invalidateSize(), 50);

    $("discover-status").textContent = spots.length
      ? "Every place below is confirmed on OpenStreetMap. Untick anything you'd rather skip."
      : "We couldn't find verified TikTok spots this time. We'll plan from local research instead.";
    $("discover-notes").textContent = notes.join(" ");
    updateBuildButton();
    show($("build"));
  }

  function updateBuildButton() {
    const kept = spots.filter((s) => s.keep).length;
    $("build").textContent = kept
      ? `Build my itinerary with ${kept} spot${kept > 1 ? "s" : ""} →`
      : "Build my itinerary →";
  }

  function inspirationBrief() {
    return spots.filter((s) => s.keep).map((s) => {
      const away = s.distance_km ? ` (~${Math.round(s.distance_km)} km away)` : "";
      return `- ${s.name}${away}: ${s.why} [mentioned in ${s.mentions} TikTok video(s)]`;
    }).join("\n");
  }

  // --- Planning ----------------------------------------------------------------

  async function startPlan() {
    show($("build"), false);
    show($("progress"));
    $("progress").scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const job = await api("/api/plans", { ...request, inspiration: inspirationBrief() });
      planId = job.id;
      poll();
    } catch (err) {
      show($("progress"), false);
      show($("build"), spots.length > 0);
      fail(err.message);
    }
  }

  let tick = 0;
  async function poll() {
    let job;
    try {
      job = await api(`/api/plans/${planId}`);
    } catch (err) {
      setTimeout(poll, 4000); // transient network blip: keep trying
      return;
    }
    const items = [...$("phases").children];
    items.forEach((li, i) => {
      li.classList.toggle("done", i < job.completed);
      li.classList.toggle("active", i === job.completed && job.status === "running");
    });
    $("bar-fill").style.width = `${Math.max(4, (job.completed / job.total) * 100)}%`;
    $("phase-label").textContent = `${job.phase}…`;
    $("ticker").textContent = TICKERS[tick++ % TICKERS.length];

    if (job.status === "done") return showResult(job.result);
    if (job.status === "error") {
      show($("progress"), false);
      return fail(`Something went wrong while planning your trip: ${job.error}`);
    }
    setTimeout(poll, 2500);
  }

  function showResult(markdown) {
    planText = markdown;
    show($("progress"), false);
    $("plan").innerHTML = DOMPurify.sanitize(marked.parse(markdown));
    $("plan").querySelectorAll("a").forEach((a) => { a.target = "_blank"; a.rel = "noopener"; });
    show($("result"));
    $("result").scrollIntoView({ behavior: "smooth", block: "start" });
    $("go").disabled = false;
  }

  // --- Events ------------------------------------------------------------------

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    show($("form-error"), false);
    show($("result"), false);
    const f = new FormData(form);
    request = {
      origin: f.get("origin").trim(),
      cities: f.get("cities").trim(),
      start: f.get("start"),
      end: f.get("end"),
      interests: f.get("interests").trim(),
    };
    if (request.end < request.start) return fail("The trip must end after it starts.");
    const links = f.get("links").split(/\s+/).filter((l) => l.startsWith("http"));
    const trending = f.get("trending") === "on";
    $("go").disabled = true;

    if (!trending && !links.length) {
      spots = [];
      show($("discover"), false);
      return startPlan();
    }

    show($("discover"));
    show($("build"), false);
    $("spots").innerHTML = "";
    $("discover-status").textContent = "Reading TikTok and checking every place on the map… (about 30 seconds per destination)";
    $("discover").scrollIntoView({ behavior: "smooth", block: "start" });
    ensureMap().setView([30, 10], 3);
    try {
      const month = new Date(request.start).toLocaleString("en", { month: "long" });
      const data = await api("/api/discover", {
        destinations: trending ? request.cities : "",
        month,
        interests: request.interests,
        links,
      });
      renderSpots(data.results);
    } catch (err) {
      $("discover-status").textContent = `TikTok discovery failed (${err.message}). You can still build your plan.`;
      show($("build"));
    }
    $("go").disabled = false;
  });

  $("build").addEventListener("click", startPlan);

  // Browsers throttle timers in background tabs; catch up as soon as the
  // traveller comes back to the page.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && planId && !$("progress").hidden) poll();
  });

  $("share").addEventListener("click", async () => {
    const url = `${location.origin}/p/${planId}`;
    try {
      await navigator.clipboard.writeText(url);
      $("share").textContent = "✓ Link copied";
    } catch {
      prompt("Copy your share link:", url);
    }
    setTimeout(() => { $("share").textContent = "🔗 Copy share link"; }, 2500);
  });

  $("download").addEventListener("click", () => {
    const blob = new Blob([planText], { type: "text/markdown" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob), download: "voyagent-trip-plan.md",
    });
    a.click();
    URL.revokeObjectURL(a.href);
  });

  $("print").addEventListener("click", () => window.print());
  $("again").addEventListener("click", () => {
    show($("result"), false);
    show($("discover"), false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
})();
