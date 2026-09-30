# Submission kit - Build with AI: Code for Communities, Track 05

Deadline: **Wed 30 Sep 2026, ~23:59 IST**. Aim to submit by **20:00** and leave the rest as buffer.

## Required package
| # | Item | Status / how |
|---|---|---|
| 1 | Source code - public GitHub repo | Push this repo to a public repository you control; verify it opens in a private window |
| 2 | Demo video, 3-5 min | Script below. Upload **unlisted** to YouTube; keep it under 5:00 |
| 3 | Pitch deck, 10-12 slides | Outline below; export **PDF** and share a public link |
| 4 | Brief description, 2-3 lines | Below |
| 5 | Deployed link | Cloud Run URL from `docs/DEPLOY.md`; open it in a private window before submitting |

## Brief description (paste into the form)
> CycloneShield AI turns an official IMD cyclone forecast into hour-by-hour impact forecasts for power substations, arterial roads, hospitals and shelters in any Indian coastal district, using Gemini 3.7 Flash's multimodal reasoning and Google Earth Engine. Gemini reads the bulletin, writes validated multilingual advisories and answers officers' questions through function calling; an officer approves and dispatches CAP-ready alerts with a tamper-evident audit trail, alongside anticipatory-finance recommendations. Replays of real cyclones (Hudhud, Fani, Yagi) run for Andhra Pradesh, Odisha and Vietnam by configuration.

## Rubric map (say this out loud and show it on a slide)
| Criterion (weight) | Evidence in the product |
|---|---|
| AI / technical execution (25%) | Three Gemini jobs (read / write / act) + AI-trace panel + validator badges + Earth Engine; 43 automated tests; deployed on Cloud Run |
| Problem-solution fit (20%) | Checklist slide: surge, rainfall damage pathways, power grid / arterial roads / medical + shelters, automated advisory dispatch, GEE, real-time met data, Gemini multimodal, parametric |
| Depth & reach across India (20%) | Region switcher: Andhra Pradesh -> Odisha -> Vietnam by JSON config; 6+ languages; basin-agnostic storm layer (BRICS/APAC) |
| Deployability & scalability (20%) | CAP 1.2 (SACHET profile, Exercise/Restricted), human approval, one-URL container, add-a-state guide, cost caveats stated |
| Impact (15%) | Odisha 1999 (~10,000 deaths) vs Phailin/Fani (double digits); 24 h warning ~30% less damage (Global Commission on Adaptation); asset-level lead time per hospital/substation/road |

Numbers to quote **only with their source** (all from `research/`): 13 coastal States/UTs and ~84 coastal districts (NCRMP; not re-verified live), Odisha deaths 1999 vs 2013/2019 (World Bank / UN ESCAP), GCA 24 h warning = ~30% less damage. Fani damage figures are media-reported: label them so.

## Demo video script (target 4:30, hard cap 5:00)
Record at 1080p, browser zoom 100%, screen only + voice. Use the **deployed URL**. Have a phone with the Telegram bot on screen (picture-in-picture or a second recording) for the wow moment.

1. **0:00-0:20 Hook.** "What if Cyclone Hudhud hit Visakhapatnam today - which hospitals, substations and roads fail first, and who needs to be told what?" Show the map: track, asset clusters, REPLAY badge.
2. **0:20-0:55 Read (multimodal).** Click *Read a bulletin*, upload an IMD bulletin PDF. Show what Gemini extracted, the validator issues (units converted, ranges checked), *Simulate this track*. Say: "IMD publishes only PDFs - Gemini is the bridge; code validates every field."
3. **0:55-1:50 Impact.** Overview cards; drag the **event clock** to T-24 h (tier turns orange by rule); Assets tab: hospitals with first-impact times and *k of 9 scenarios*; Roads & evac: safe routes, "leave before" times, stranded localities with shelter-in-place.
4. **1:50-2:40 Dispatch - the wow.** Advisories tab: district collector, Telugu. Show validator checks (numbers match, places in scope). Submit as *Duty officer*, approve as *Approver A* and *Approver B* (orange needs two), **Dispatch** -> the Telegram message arrives on the phone -> press **Acknowledge** -> status ACKED. Open the CAP XML (Exercise / Restricted).
5. **2:40-3:10 Stress test and honesty.** *What-if*: +20 kt or a 40 km shift; ensemble spread. Switch storm to **Montha** (near miss): tier stays **Monitor - no action** - "it doesn't cry wolf".
6. **3:10-3:45 Scale.** Switch region to Odisha (Fani) then Vietnam (Yagi): same pipeline, Odia / Vietnamese advisory. "New state = a JSON file."
7. **3:45-4:20 Trust and money.** Trust tab: methodology, calibration disclosure (in-sample), AI trace, *Verify hash chain*. Finance tab: tier reached and the recommended release memo - "no money moves".
8. **4:20-4:30 Close.** "Downstream of IMD, ready to pilot with APSDMA and OSDMA in weeks."

## Pitch deck (11 slides, export PDF)
1. Title, value proposition, live link + QR
2. Problem: forecasts exist; asset-level "who does what, when" is still manual (IMD -> Web-DCRA -> SACHET chain we plug into)
3. Users and a persona story (district collector; hospital; DISCOM)
4. Solution in 3 screenshots: read -> simulate -> dispatch
5. Google AI approach: Gemini read / write / act, Earth Engine, validator, AI trace
6. Architecture diagram (README mermaid)
7. Evidence: 43 tests, extraction checks, validator behaviour, calibration table with the in-sample disclosure
8. Challenge checklist: every phrase of Track 05 -> feature
9. Scale across India and BRICS/APAC: tenants, languages, rollout order (NCRMP Category I first)
10. Deployability: 4-6 week pilot plan (APSDMA shadow mode -> OSDMA/TNSDMA -> CAP feed to state EOC), cost incl. Earth Engine commercial terms and Gemini 2027 pricing, governance, limitations
11. Impact, roadmap (WeatherNext ensembles, Flood Hub, Bhashini, Firestore + KMS-signed audit), team

## Final checklist (do in this order)
- [ ] Repo public; README renders; LICENSE present; `.env` not committed (`git log -p | grep -i GEMINI_API_KEY` returns nothing)
- [ ] Deployed URL opens in a private window; `/api/health` shows gemini/earth_engine/telegram as expected
- [ ] Run the video path once on the deployed URL (bulletin -> simulate -> draft -> approve x2 -> dispatch -> acknowledge)
- [ ] Video <= 5:00 uploaded unlisted; link works logged out
- [ ] Deck PDF <= 12 slides; link works logged out
- [ ] Submit on Hack2skill (check the dashboard for whether edits are allowed after submission)
- [ ] After judging: delete the Cloud Run service and revoke/rotate the API key
