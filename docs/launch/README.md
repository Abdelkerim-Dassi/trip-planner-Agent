# ReelTrip launch kit

Everything needed to open ReelTrip's social accounts and post for the first month. You create the accounts yourself; this kit holds the names, bios, posting plan and post templates.

## Positioning (one line, use it everywhere)

> **Saw a place on TikTok? ReelTrip turns it into a real, checked day-by-day trip plan. Free, no account.**

Why people should care, in order (from the research in `reports/`):

1. **It checks what AI planners get wrong.** Surveys keep finding wrong opening hours and closed venues in AI itineraries. ReelTrip puts every stop on the map and checks its closing days, then shows what it checked.
2. **It starts from what you saved.** Paste the TikToks you saved; the plan is built around them.
3. **It knows North Africa and the Middle East.** Prayer times, halal food, Ramadan hours, Friday prayers, louages and transfers. Most planners ignore these.

Other apps also import TikToks (Triply, Wandereel, Plotline, Mindtrip). Don't compete on "AI itinerary". Compete on **checked** plans and **regional know-how**.

## 1. Accounts to open (in this order)

| Platform | Handle to try first | Fallbacks | Why |
|---|---|---|---|
| Instagram | `reeltrip.app` | `reeltrip.travel`, `getreeltrip` | Carousels and Reels; the research found one founder getting far more views on Reels than TikTok for the same content. **Main channel for the first 3 weeks.** |
| TikTok | `reeltrip.app` | `reeltrip.travel`, `getreeltrip` | Photo posts (the carousel) and short videos. Start in week 3. |
| X | `reeltripapp` | `reeltrip_app` | Build-in-public posts, developer audience. |
| Reddit | `u/reeltrip_founder` | — | Answering trip questions honestly (see rules below). |
| Threads | same as Instagram | — | Created with the Instagram account; repost there. |

Use the same profile picture everywhere: the ✈️ on the sunset gradient (same colours as the site). Put `reeltrip.onrender.com` in every bio link.

Pick **one** main channel and post there every day for 3 weeks before adding the next. Indie founders report that one repeatable channel beats spreading thin.

## 2. Bios

**English**
> Saw it on TikTok? We turn it into a real trip plan ✈️
> Every stop checked on the map + opening days
> 🇹🇳🇲🇦🇪🇬 North Africa & Middle East know-how · free, no account
> 👇 Plan yours

**Français**
> Vu sur TikTok ? On en fait un vrai itinéraire ✈️
> Chaque étape vérifiée sur la carte + jours d'ouverture
> 🇹🇳🇲🇦🇪🇬 Spécialiste Afrique du Nord & Moyen-Orient · gratuit, sans compte
> 👇 Planifie ton voyage

**العربية**
> شفتها على تيك توك؟ نحولها لرحلة حقيقية يوم بيوم ✈️
> كل محطة متأكدين منها على الخريطة وأيام فتحها
> 🇹🇳🇲🇦🇪🇬 خبرة في شمال أفريقيا والشرق الأوسط · مجاناً وبدون حساب
> 👇 خطط رحلتك

(The Arabic is written in a light, everyday register. Have a native speaker from your target country check it before posting.)

## 3. How each post is made

1. Make a real plan on reeltrip.onrender.com (use trips people actually ask about: see the calendar below).
2. Open **📸 Post this trip** on the plan page.
3. Save the slides (cover, one per day, map, closing slide) and copy the caption. Both come from the plan, so nothing is invented.
4. For a Reel or TikTok video: put the same slides in a slideshow, read the voice-over script, add trending audio quietly underneath.
5. Post, then reply to every comment in the first hour.

Turn on TikTok's "AI-generated content" label when a post uses an AI voice or images.

## 4. First 30 days

Three content types, rotated. Each one is a real plan made with the app.

| Type | Example | Format |
|---|---|---|
| **Saved vs. planned** | "I saved 6 TikToks about Djerba. Here's the 3-day plan they became." | Carousel |
| **AI got this wrong** | "An AI planner sent me to the Bardo Museum on a Monday. It's closed Mondays. Here's what checking looks like." | Reel with screen recording |
| **Budget reality** | "3 days in Tunis for 358 TND (~$115): every cost." | Carousel |

| Week | Mon | Wed | Fri | Sun |
|---|---|---|---|---|
| 1 | Saved vs. planned: Tunis | AI got this wrong: Bardo on Monday | Budget: Tunis 3 days | Saved vs. planned: Djerba |
| 2 | Saved vs. planned: Marrakech | AI got this wrong: Friday prayers and closed souks | Budget: Cairo 4 days | Ramadan trip: what changes (Istanbul) |
| 3 | Saved vs. planned: Tozeur & Chebika | Halal food plan: Paris weekend | Budget: Chefchaouen 2 days | Start TikTok: repost the 3 best carousels |
| 4 | Saved vs. planned: Amman & Petra | AI got this wrong: a place that doesn't exist | Budget: Istanbul 4 days | Recap: "what 30 days of checked plans taught me" |

Post in the evening for your audience's time zone. Keep a simple sheet: date, post, views, saves, profile visits, link clicks, plans created that day (visible in `data/plans` or Upstash).

## 5. Launch posts (week 2, once 10+ posts are up)

**Show HN** (title): `Show HN: ReelTrip – turns saved TikToks into checked trip plans (open source)`
Body: what it does in 2 lines, the opening-hours check and why (the Bardo example), the free stack (Groq, Gemini, Serper, OpenStreetMap, Render), link to the repo, ask for feedback on the checker.

**Reddit** (r/solotravel, r/travel, r/Tunisia, r/Morocco, r/Egypt): read each subreddit's self-promotion rules first. Most allow it only in a weekly thread or not at all. Better: answer real "help me plan X" questions with a useful answer written by hand, and mention the tool only if the rules allow. Never post the same link to many subreddits at once.

**Product Hunt**: after the first users' feedback is in. Tagline: `Saw it on TikTok? Get a real, checked trip plan`. First comment: the founder story (why North Africa, why checking).

## 6. Weekly routine (about 3 hours)

- Monday: make the week's 4 plans and save their slides and captions (1 hour).
- Every posting day: post, then answer comments for 15 minutes.
- Friday: look at the sheet. Make more of whatever got the most **saves** and **link clicks**, not views.
- Once a week: one build-in-public post on X (what shipped, one number, one lesson).

## What not to do

- Don't buy followers or use engagement pods: both hurt reach on Instagram and TikTok.
- Don't post plans you haven't read. One wrong fact in a post about "checked plans" undoes the whole pitch.
- Don't use other creators' TikTok videos in your posts. Name the places and link to the creators instead.
