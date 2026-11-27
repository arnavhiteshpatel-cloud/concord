# Founder Playbook B — experiments and decision rules (verbatim summary)

Source: "Playbook B - Neural interface real-world evidence" (founder document, 27 Nov 2026), §8.
Transcribed here so repository documents can reference the original rules. Labels as in source.

| # | Hypothesis | Method | Metric | Decision rule |
|---|---|---|---|---|
| E1 (U7) | The SRAlab DAI is open and SRAlab welcomes an implementation or home-extension partner | Conversation with the DAI team via the NCT07407725 study contact | Stance on licensing and partnership | Continue if open and welcoming. If they already have an implementation vendor, pivot to the AT-outcomes product or F5b |
| E2 (U6) | ≥2 non-Neuralink sponsors or CUC members will pay for neutral home evidence and payer packaging | 10–20 interviews with a one-page offer and a price (per study-year) | LOIs or pilots | Continue at ≥2 LOIs or pilots. Pivot if fewer than 2 of ~10 are willing within 90 days, or sponsors say CMS evidence will come from their own registries |
| E3 (B5) | The CUC wants measurement or registry infrastructure | Ask iBCI-CC contacts who is in the CUC and what they need | Membership identified; stated need | If the CUC needs only consulting, focus on sponsors and F5b |
| E4 (B7) | Battery scores fall monotonically with simulated decoder degradation | Harness sweep over noise, latency, drift and dropout | Score vs degradation curves | Monotonic and detectable, or rework the primitives |
| E5 (U8) | The battery is reliable (ICC ≥0.8) in ≥2 input modalities | 10 able-bodied users × 3 inputs (30 days), then an IRB pilot with 10–15 AT users | ICC, SEM/MDC, known-groups validity, responsiveness | Continue if ICC ≥0.8 in ≥2 modalities |
| E6 (U9) | Real-world use can be logged on at least one major sponsor platform | OS technical spike (Windows, macOS, Android, iOS); ask sponsors which platforms participants use | Loggable platforms | Continue if ≥1 major platform is loggable or a sponsor agrees to an export; iOS-only deployments without cooperation are pivot evidence |
| E7 (B8) | Home logging is feasible and acceptable | 2-week home-logger study with 5 users on Windows/Android | Data completeness; participant burden | Usable logs from ≥4 of 5 users |
| E8 (B6) | Home neuromodulation makers will buy a home-outcomes companion (F5b) | LOI conversations with 3 makers | LOIs | Whichever of F5 or F5b reaches ≥2 LOIs first becomes the lead |
| E9 | Logged use correlates with care-partner hours (the chain link) | Within the AT pilot, collect logs plus care-partner minutes | Correlation and confidence interval | A publishable "measurement chain" signal; if absent, rethink which logged features matter |

90-day gate (25 Feb 2027): ≥2 sponsors, CUC members or makers say they would pay for home
evidence (or SRAlab agrees to scope a collaboration); IRB pilot with AT users under way; an LOI or
paid pilot ($25–75K [HYP]).

Pivot evidence: fewer than 2 of ~10 sponsor/market-access contacts willing to pilot or pay within
90 days; SRAlab or the CUC already has an implementation vendor; sponsors state CMS evidence will
come from their own registries; iOS-only deployments block logging without sponsor cooperation.

Status from this session: E4 is executed computationally (experiments B–F, G); E6 is
investigated by desk research (docs/research/platform_matrix.md) and the probe contract; E5, E7,
E9 have protocols (CLINICAL_VALIDATION_PLAN.md) but need participants; E1–E3, E8 need the founder.
