# ReelTrip launch kit

How to get ReelTrip its first users and its first paying clients, with no budget. Based on market research done in November 2026.

## Positioning (one line, use it everywhere)

> **Your AI planned your trip. ReelTrip checks it.** Paste any itinerary: each place is looked up on the map, and closed days, wrong cities and impossible days are flagged. Free, no account.

### What is new, and what is not

Be precise about this, in posts and in conversations. Overclaiming is the fastest way to lose a tool whose whole point is honesty.

- **Not new:** "itinerary checker" as a name. At least three free tools use it (TripSapien, SuperTravel, Journey Planner). TripSapien also checks closed days against your dates, from its own catalogue of places, and has an MCP endpoint. None of them shows traction.
- **Not new:** turning TikToks into pins. More than 20 iOS apps do it, mostly for about $50 a year.
- **New, as a combination:** one report that checks existence (map, then web), the **wrong city**, the **weekly closing day against the scheduled weekday**, **distance covered in a day** and **day load**, with a shareable page and a fix list to paste back into the assistant. The research found no tool that does all of these.
- **New:** **Friday prayer and Ramadan flags**, and plans in **French and Arabic** for North Africa and the Middle East. No checker has them.
- **Different by design:** web, no install, no login, no subscription. The top complaints about the iOS apps are surprise charges and paywalls.

### Proof points to quote (with sources)

- Among travellers who used AI, 55% got at least one bad recommendation: 27% wrong prices or hours, 16% a place that did not exist, 10% a business that had closed (Greetwell survey, 2026, n=485).
- An SEO Travel test of 100 ChatGPT itineraries found 90% had an error and 52% scheduled a visit outside opening hours (May 2024).
- BBC Travel (Sept 2025): tourists in Peru looking for a "Sacred Canyon of Humantay" that does not exist; a couple stranded on Mt Misen after an AI gave the wrong last ropeway time.
- CNN (Jan 2026): an AI-written travel page sent tourists to "Weldborough Hot Springs" in Tasmania, which does not exist.

Closing-day traps that are confirmed on official pages and make good demos: Louvre (Tuesday), Musée d'Orsay and Versailles (Monday), Uffizi (Monday), Vatican Museums (most Sundays), Topkapı Palace (Tuesday), Dolmabahçe (Monday), Bardo Museum in Tunis (Monday), Musée YSL Marrakech (Wednesday), Louvre Abu Dhabi (Monday), Taj Mahal (Friday), Gyeongbokgung (Tuesday).

## 1. Before any promotion (one evening)

1. Deploy the latest code (push, then Manual Deploy on Render) and open `/healthz`: it should list `fallback_models` and `"plans_persist": true`.
2. On Render, delete `VOYAGENT_DISCOVERY_MODEL` if it is set to `groq/openai/gpt-oss-120b`, so the fast model is used for the small jobs. Add `TAVILY_API_KEY` if you create a free Tavily account.
3. Keep the site awake: a free uptime monitor (UptimeRobot, cron-job.org) pinging `https://reeltrip.onrender.com/healthz` every 10 minutes. A first visitor who meets a 70-second loading screen leaves.
4. Run three checks yourself on itineraries you know well and read every line of the report. Fix or report anything wrong before strangers see it.
5. Add free analytics (Cloudflare Web Analytics or GoatCounter: no cookies, no banner) so you can tell which channel works.

## 2. The first 100 users (weeks 1 to 3)

Ranked by expected users per hour of your time.

### A. Answer "itinerary check" posts with real findings

People post their itineraries for review every day. r/JapanTravel titles them "[Itinerary Check]"; the Rick Steves and Fodor's forums are full of them; so are country subreddits.

How to do it without getting banned (r/travel bans AI content and self-promotion, r/solotravel and r/TravelHacks ban self-promotion):

1. Run their itinerary through ReelTrip.
2. Read the report and keep only what you have confirmed yourself.
3. Reply **as a person, in text**: "Day 3 has the Uffizi on a Monday, it's closed. Day 5 is about 300 km of driving between Siena, Pisa and Cinque Terre." Add one human tip.
4. No link in the reply. Put the site in your profile. If someone asks how you checked, answer.

Ten useful replies a week is the target. This is also your product research: every wrong finding is a bug to fix.

### B. Short vertical video (TikTok, Reels, Shorts)

2026 data has video getting about 5.6 times the views of carousels, and the only large travel-app growth stories found came from founder-made short video.

Format, 20 to 30 seconds, screen recording with your voice:

1. Hook on screen in the first second: **"ChatGPT planned my trip to Tunis. I checked it."**
2. Paste the plan, press Check.
3. Cut to the report: zoom on the red findings one by one. "Museum on the day it's closed. This restaurant is in another city, 135 km away. This viewpoint doesn't exist."
4. End on the map and "Free, link in bio."

Twelve scripts to start (each one is a real check you run first):

| # | Hook | Destination |
|---|---|---|
| 1 | ChatGPT planned my trip to Tunis. I checked it. | Tunis |
| 2 | This AI itinerary sends you to the Louvre on a Tuesday. | Paris |
| 3 | I asked three AIs for a Marrakech plan. One invented a restaurant. | Marrakech |
| 4 | "A quick day trip": 330 km. | Tunisia |
| 5 | Your Istanbul plan has Topkapı on a Tuesday. It's closed. | Istanbul |
| 6 | Ramadan trip? Here's what your AI plan forgot. | Cairo |
| 7 | Friday in Morocco: what closes at midday. | Fes |
| 8 | I checked a viral TikTok itinerary. 2 of 9 places aren't where it says. | Djerba |
| 9 | The Uffizi is closed on Mondays. Half the AI plans don't know. | Florence |
| 10 | Halal trip to Paris: checked plan in 60 seconds. | Paris |
| 11 | The restaurant your AI recommended doesn't exist. How to tell. | Lisbon |
| 12 | 3 things I check before trusting any AI itinerary. | any |

Post once a day for three weeks on one platform before adding another. Turn on the AI-content label only where a post uses an AI voice or AI images; screen recordings of the tool don't need it. Reply to every comment in the first hour.

### C. One small original study

"We checked 50 AI itineraries. X% had a visit on a closing day, Y% named a place we couldn't find anywhere." Run 50 checks (10 destinations, ChatGPT and Gemini), count the findings, publish the method and the list.

- Each check costs a handful of searches, so spread the runs over a few days.
- Verify every headline finding by hand before publishing.
- Post it as Show HN, on dev.to, r/SideProject and r/dataisbeautiful, and send it to the reporters who covered the stories above. A number is what gets quoted.

### D. Assistant directories (one afternoon, permanent)

- **Official MCP Registry**: free. Publish a `server.json` with the `mcp-publisher` CLI under your GitHub-verified name. Glama and mcp.so pick up from GitHub or a form.
- **ChatGPT app directory**: open to verified individuals. Needs the HTTPS MCP endpoint, a verification file at `/.well-known/openai-apps-challenge`, a privacy policy (`/privacy` exists now), terms, a support contact, test cases and a demo video. The site must be awake during review.
- **Claude connector directory**: no fee, but submitting needs a paid Claude plan. Skip unless you have one.

Pitch for the listing: "Check any itinerary you or the assistant wrote: real places, closing days, distances. Halal and Ramadan aware."

### E. Communities that welcome it

r/SideProject, r/InternetIsBeautiful (free, no sign-up tools qualify), r/mcp, the r/ClaudeAI showcase thread, Show HN (must be usable without sign-up: it is), Peerlist and AlternativeTo. One post each, spaced out, written for that community.

Skip: Product Hunt as a priority, paid directories, `llms.txt`, the WhatsApp API.

## 3. The first paying clients (weeks 3 to 8)

The research points to one buyer who has the problem every week and already pays for tools: **independent travel advisors**.

- 59% of US advisors use AI and 63% worry about its accuracy (Travel Weekly / Phocuswright, 2025).
- 30% see clients arriving with AI-made itineraries to review (WeTravel, 2026).
- They already pay $35 to $59 a month for itinerary builders (Travefy, Tern, Axus).
- Human itinerary reviews sell for €49 to $400 each.

### The offer

> **ReelTrip Pro for advisors.** Check every itinerary before it goes to a client. Unlimited checks, and a client-ready report page with your name and logo that says "checked on <date>". $9 a month, or $19 for a team of five. Ten checks free.

What exists today: the check and the dated report page. What Pro needs (build it only after three advisors say yes): a logo and name on the report, and a private list of your reports. Until then, do it by hand for the first three clients: send them their report links and ask what is missing.

### Where to find them, free

- Host Agency Reviews' community and Cheryl Rosen's Facebook group for travel professionals.
- Travel Massive (creators and small operators).
- LinkedIn: search "travel advisor" plus a destination you know; send the check of one of their public sample itineraries, not a pitch.
- North Africa: riads, small DMCs and tour operators in Tunisia and Morocco who publish itineraries on their sites. Check one of theirs, send them the report, offer to keep their itineraries checked.

### Second buyer: creators who sell guides

Guides sell for $8 to $39 on Rexby and (formerly) Thatch, which has been absorbed by Mindtrip. Offer a free "Checked by ReelTrip on <date>" link they can put on their guide. It costs you nothing, puts the name in front of their buyers, and tells you whether creators would pay for a badge later.

### Taking payment without a company

Lemon Squeezy lists bank payouts to Tunisia, Morocco, Egypt and Algeria. Polar covers Tunisia, Egypt and Algeria. Dodo Payments covers Tunisia. Confirm with a small test payment before advertising a price. GitHub Sponsors (Tunisia, Morocco and Egypt supported) is the simplest rail for donations.

## 4. Accounts and bios

| Platform | Handle to try | Notes |
|---|---|---|
| TikTok | `reeltrip.app` | Main channel for the first three weeks. |
| Instagram | `reeltrip.app` | Repost the same videos as Reels. |
| Reddit | `u/reeltrip_founder` | For replies; link in profile only. |
| X | `reeltripapp` | Build-in-public notes, the study. |

Check the name first: an iOS app called ReelTravel exists, and the name "ReelTrip" itself has not been searched for clashes.

**English**
> Your AI planned your trip. We check it ✅
> Closed days · wrong cities · places that don't exist
> Halal and Ramadan aware · 🇹🇳🇲🇦🇪🇬 · free, no account
> 👇 Check yours

**Français**
> Ton IA a planifié ton voyage. On le vérifie ✅
> Jours de fermeture · mauvaise ville · lieux qui n'existent pas
> Halal et Ramadan pris en compte · 🇹🇳🇲🇦🇪🇬 · gratuit, sans compte
> 👇 Vérifie le tien

**العربية**
> الذكاء الاصطناعي خطط رحلتك؟ نحن نتحقق منها ✅
> أيام الإغلاق · المدينة الخطأ · أماكن غير موجودة
> نراعي الحلال ورمضان · 🇹🇳🇲🇦🇪🇬 · مجاناً وبدون حساب
> 👇 تحقق من رحلتك

(Have a native speaker from your target country read the Arabic before posting.)

## 5. Weekly routine (about 4 hours)

- Monday: run the week's checks and record the videos (1.5 hours).
- Daily: post one video, answer comments for 15 minutes, write two itinerary-check replies.
- Friday: look at the numbers. Keep what brought **checks started**, not views.
- Once a week: one build-in-public post (what shipped, one number, one thing that was wrong).

## What not to do

- Don't say "verified" or "every place". Say what was checked, in numbers. The product does; the marketing must too.
- Don't post a finding you haven't confirmed by hand. One wrong "this place doesn't exist" about a real place undoes the pitch.
- Don't drop links in communities that ban them.
- Don't buy followers or use engagement pods.
- Don't use other creators' videos; name the places and link to the creators.
