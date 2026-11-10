// ReelTrip home page. Two flows share it:
//  - Check: paste any itinerary, follow the check, read the report.
//  - Plan:  discover TikTok spots, keep or skip them, get a checked plan.
(() => {
  const $ = (id) => document.getElementById(id);
  const show = (el, on = true) => { el.hidden = !on; };
  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const iso = (d) => d.toISOString().slice(0, 10);

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

  // One polling loop at a time: coming back to the tab must not start a second.
  let pollTimer = null;
  function schedule(fn, ms) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(fn, ms);
  }

  // --- Tabs ----------------------------------------------------------------------

  // Each flow lives in its own container, so switching tabs keeps whatever
  // the other flow was showing (a running check, a finished plan).
  let mode = "check";
  function setMode(next) {
    mode = next;
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.mode === next));
    show($("mode-check"), next === "check");
    show($("mode-plan"), next === "plan");
    if (next === "plan" && map) setTimeout(() => map.invalidateSize(), 50);
    history.replaceState(null, "", next === "plan" ? "#plan" : location.pathname);
  }
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  window.addEventListener("hashchange", () => setMode(location.hash === "#plan" ? "plan" : "check"));

  // --- Check an itinerary ------------------------------------------------------------

  const checkForm = $("check-form");
  let checkId = null;
  let report = null;

  const EXAMPLE = `Here's your 5-day Tunisia itinerary!

Day 1 – Tunis: Morning: explore the Medina of Tunis and Zitouna Mosque. Lunch at Dar El Jeld. Afternoon: Bardo National Museum to see the Roman mosaics. Evening: stroll Avenue Habib Bourguiba.

Day 2 – Carthage & Sidi Bou Said: Morning: Antonine Baths and the Carthage National Museum. Lunch at Dar Zarrouk. Afternoon: wander Sidi Bou Said, coffee at Café des Délices. Sunset at the Crystal Lagoon Viewpoint.

Day 3 – Kairouan day trip: Great Mosque of Kairouan, Aghlabid Basins, Mausoleum of Sidi Sahab. Lunch at Dar Zarrouk in Kairouan. Then drive to El Jem Amphitheatre and on to Sousse Medina for dinner before returning to Tunis.

Day 4 – Dougga: Full-day trip to the Roman ruins of Dougga. Dinner back in Tunis at Fondouk El Attarine.

Day 5 – Departure: Last-minute shopping at Souk El Attarine, then transfer to the airport.`;

  function checkFail(message) {
    $("check-error").textContent = message;
    show($("check-error"));
    show($("check-progress"), false);
    $("check-go").disabled = false;
  }

  $("example").addEventListener("click", () => {
    checkForm.text.value = EXAMPLE;
    // A Monday, so the example's museum visit lands on its closing day.
    const d = new Date(Date.now() + 30 * 864e5);
    d.setDate(d.getDate() + ((8 - d.getDay()) % 7));
    checkForm.start.value = iso(d);
    checkForm.text.focus();
  });

  checkForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    show($("check-error"), false);
    show($("check-result"), false);
    const text = checkForm.text.value.trim();
    if (text.length < 40) return checkFail("Paste the itinerary itself: the day-by-day plan with its places.");
    $("check-go").disabled = true;
    $("check-label").textContent = "Reading the itinerary…";
    $("check-bar").style.width = "4%";
    show($("check-progress"));
    $("check-progress").scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const job = await api("/api/checks", {
        text,
        start: checkForm.start.value || null,
        halal: checkForm.halal.checked,
      });
      checkId = job.id;
      pollCheck();
    } catch (err) {
      checkFail(err.message);
    }
  });

  async function pollCheck() {
    let job;
    try {
      job = await api(`/api/checks/${checkId}`);
    } catch {
      return schedule(pollCheck, 4000); // transient network blip: keep trying
    }
    if (job.status === "error") return checkFail(job.error);
    if (job.status === "done") return showReport(job.report);
    if (job.total) {
      $("check-label").textContent = job.done >= job.total
        ? "Checking opening days…"
        : `Looking up place ${job.done + 1} of ${job.total}: ${job.label}`;
      $("check-bar").style.width = `${Math.max(6, (job.done / job.total) * 92)}%`;
    }
    schedule(pollCheck, 1500);
  }

  function showReport(data) {
    report = data;
    show($("check-progress"), false);
    window.renderReport(report, $("report"));
    show($("copy-fix"), Boolean(report.fix_prompt));
    $("open-report").href = `/c/${checkId}`;
    show($("check-result"));
    $("check-result").scrollIntoView({ behavior: "smooth", block: "start" });
    $("check-go").disabled = false;
  }

  $("copy-report").addEventListener("click", (e) => window.copyText(`${location.origin}/c/${checkId}`, e.currentTarget, "✓ Link copied"));
  $("copy-fix").addEventListener("click", (e) => window.copyText(report.fix_prompt, e.currentTarget));
  $("check-again").addEventListener("click", () => {
    show($("check-result"), false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // --- Plan from TikTok ----------------------------------------------------------------

  const form = $("trip-form");
  const TICKERS = [
    "Reading local guides…", "Checking the season…", "Grouping places by neighbourhood…",
    "Adding buffer time…", "Looking up each place on the map…", "Checking opening days…",
  ];
  // A spot further than this from the destination city is unticked by default.
  const DAY_TRIP_KM = 60;
  const TOO_FAR_KM = 150;

  let map = null;
  let spots = [];      // every spot shown, with a .keep flag
  let request = null;  // the trip form values
  let planId = null;
  let planText = "";

  // Default dates: a week, starting a month from now.
  const start = new Date(Date.now() + 30 * 864e5);
  form.start.value = iso(start);
  form.end.value = iso(new Date(start.getTime() + 6 * 864e5));
  form.start.min = form.end.min = iso(new Date());

  function fail(message) {
    $("form-error").textContent = message;
    show($("form-error"));
    $("go").disabled = false;
  }

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
    let unticked = 0;

    for (const group of results) {
      notes.push(...(group.notes || []));
      if (!group.spots.length) continue;
      const title = document.createElement("p");
      title.className = "group-title";
      title.textContent = `${group.destination} · from ${group.videos.length} TikTok videos`;
      box.appendChild(title);

      for (const spot of group.spots) {
        const km = spot.distance_km ? Math.round(spot.distance_km) : 0;
        // Far-away favourites are shown but left out unless the traveller opts in.
        spot.keep = km <= TOO_FAR_KM;
        if (!spot.keep) unticked += 1;
        spots.push(spot);
        const card = document.createElement("div");
        card.className = `spot${spot.keep ? "" : " skipped"}`;
        const where = km > TOO_FAR_KM
          ? `<span class="pill warn">~${km} km away: its own trip</span>`
          : km > DAY_TRIP_KM ? `<span class="pill moved">Day trip · ~${km} km</span>`
            : km ? ` · ~${km} km from ${escapeHtml(group.destination)}` : "";
        const vids = spot.videos.slice(0, 3)
          .map((u, i) => `<a href="${escapeHtml(u)}" target="_blank" rel="noopener">▶ video ${i + 1}</a>`).join("");
        card.innerHTML = `
          <h3>${escapeHtml(spot.name)}</h3>
          <p class="why">${escapeHtml(spot.why)}</p>
          <p class="meta"><span class="pill">📍 on the map</span> ${spot.mentions} video${spot.mentions > 1 ? "s" : ""} ${where}</p>
          <p class="vids">${vids}</p>
          <label class="check"><input type="checkbox" ${spot.keep ? "checked" : ""}> Include in my trip</label>`;
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
        also.textContent = `Also mentioned (not found on the map): ${group.unverified.join(", ")}`;
        box.appendChild(also);
      }
    }

    if (bounds.length) m.fitBounds(bounds, { padding: [30, 30], maxZoom: 11 });
    else m.setView([30, 10], 3);
    setTimeout(() => m.invalidateSize(), 50);

    $("discover-status").textContent = spots.length
      ? "Each place below was found on OpenStreetMap. Untick anything you'd rather skip."
        + (unticked ? ` ${unticked} far-away spot${unticked > 1 ? "s are" : " is"} unticked: tick ${unticked > 1 ? "them" : "it"} only if you have days to spare.` : "")
      : "We couldn't find TikTok spots on the map this time. We'll plan from local research instead.";
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
    } catch {
      return schedule(poll, 4000); // transient network blip: keep trying
    }
    const items = [...$("phases").children];
    items.forEach((li, i) => {
      li.classList.toggle("done", i < job.completed);
      li.classList.toggle("active", i === job.completed && job.status === "running");
    });
    $("bar-fill").style.width = `${Math.max(4, (job.completed / job.total) * 100)}%`;
    $("phase-label").textContent = `${job.phase}…`;
    $("ticker").textContent = job.detail || TICKERS[tick++ % TICKERS.length];

    if (job.status === "done") return showResult(job);
    if (job.status === "error") {
      show($("progress"), false);
      return fail(`Something went wrong while planning your trip: ${job.error}`);
    }
    schedule(poll, 2500);
  }

  function showResult(job) {
    planText = job.result;
    show($("progress"), false);
    $("plan").innerHTML = DOMPurify.sanitize(marked.parse(job.result));
    if (job.review) window.renderReport(job.review, $("checks"), { title: "✅ What we checked" });
    else window.renderChecks(job.checks, $("checks"));
    $("post").href = `/p/${planId}/post`;
    $("ics").href = `/p/${planId}/plan.ics`;
    $("plan").querySelectorAll("a").forEach((a) => { a.target = "_blank"; a.rel = "noopener"; });
    show($("result"));
    $("result").scrollIntoView({ behavior: "smooth", block: "start" });
    $("go").disabled = false;
  }

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
      halal: f.get("halal") === "on",
      language: f.get("language"),
    };
    if (request.end < request.start) return fail("The trip must end after it starts.");
    // One entry per line: links are looked up, any other text is read as a
    // pasted caption (for posts search engines haven't indexed yet).
    const lines = f.get("links").split(/\n+/).map((l) => l.trim()).filter(Boolean);
    const links = lines.filter((l) => /^https?:\/\//.test(l));
    const captions = lines.filter((l) => !/^https?:\/\//.test(l));
    const trending = f.get("trending") === "on";
    $("go").disabled = true;

    if (!trending && !links.length && !captions.length) {
      spots = [];
      show($("discover"), false);
      return startPlan();
    }

    show($("discover"));
    show($("build"), false);
    $("spots").innerHTML = "";
    $("discover-status").textContent = "Reading TikTok and looking up each place on the map… (up to a minute per destination)";
    $("discover").scrollIntoView({ behavior: "smooth", block: "start" });
    ensureMap().setView([30, 10], 3);
    try {
      const month = new Date(request.start).toLocaleString("en", { month: "long" });
      const data = await api("/api/discover", {
        destinations: trending ? request.cities : "",
        month,
        interests: request.interests,
        links,
        captions,
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
    if (document.hidden) return;
    if (mode === "plan" && planId && !$("progress").hidden) poll();
    if (mode === "check" && checkId && !$("check-progress").hidden) pollCheck();
  });

  $("share").addEventListener("click", (e) => window.copyText(`${location.origin}/p/${planId}`, e.currentTarget, "✓ Link copied"));

  $("download").addEventListener("click", () => {
    const blob = new Blob([planText], { type: "text/plain" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob), download: "reeltrip-plan.txt",
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

  setMode(location.hash === "#plan" ? "plan" : "check");
})();
