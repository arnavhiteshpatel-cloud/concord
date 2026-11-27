# NeuroMetric founder learning guide (12 weeks)

A prioritised plan for a founder who already knows biomedical research and BCI software, and now needs to be
credible with clinicians, psychometricians, regulators, payers and investors. About 10–12 hours a week.

Prepared 2026-11-27. Labels follow [`../research/CONVENTIONS.md`](../research/CONVENTIONS.md);
**[V-DOI]** = DOI resolved on Crossref on 2026-11-27 (citation verified, content from memory).
Start with [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) §0 and §8–9; everything below builds on the "levels"
idea.

## How to use this plan

- **Priority order** if time is short: Week 1 (levels), Weeks 5–6 (psychometrics), Week 8 (regulatory),
  Week 4 (HCI metrics), Week 11 (customers). These are what reviewers and buyers test you on first.
- Each week has **must-read** items (do them), **optional** items, a **free course** segment, and
  **exercises** that use this repository. Write a one-page note at the end of each week in your own words;
  that becomes your interview and pitch material.
- Exercises assume the package is installed in editable mode from `neurometric/`:
  `pip install -e ".[dev]"`, and tests pass: `pytest -q`.

### UIUC courses that look relevant

These titles were found in the University of Illinois course catalog API for Fall 2026
([V] `https://courses.illinois.edu/cisapp/explorer/catalog/2026/fall/<SUBJECT>.xml`, accessed 2026-11-27;
ECON 418 and the BADM courses from the Spring 2026 catalog). A catalog listing does **not** mean the course
runs every term or that you meet prerequisites — **check the course catalog and Course Explorer schedule**
before planning around any of them.

| Course | Why it is relevant |
|---|---|
| ECE 421 Neural Interface Engineering (same as NE 420) | Invasive/non-invasive interfaces, neural prosthetics, decoding (description verified) |
| ECE 410 Neural Circuits and Systems | Neural engineering foundations |
| BIOE 414 / 415 Biomedical Instrumentation (+ Lab) | Signal acquisition, useful for the latency bench |
| CS 465 User Interface Design; CS 565 Human-Computer Interaction | HCI evaluation methods |
| IE 340 Human Factors; IE 546 Human Factors in Health Care Engineering Systems | Usability, workload, medical human factors |
| SHS 480 Understanding Disability and Assistive Technology | OS accessibility features, AT, IT accessibility law (description verified) |
| SHS 482 Designing Universally Accessible Web Resources | Accessible task battery design |
| PSYC 490 Measurement & Test Development Lab; PSYC 595 Theories of Measurement I | Psychometrics (595 is graduate level) |
| STAT 212 Biostatistics | Statistics for clinical data |
| BIOE 489 Regulations, Ethics and Logistics in Biomedical Applications of ML | IRB, regulation, clinical adoption (senior/graduate standing) |
| ECON 418 Health Economics | Payer and HEOR thinking |
| TE 461 Technology Entrepreneurship; BADM 446 New Venture Creation; BADM 463/464 iVenture Accelerator Seminar | Entrepreneurship |

Other campus resources (Research Park, EnterpriseWorks, the iVenture Accelerator, Disability Resources and
Educational Services) are [PK]; check their current programmes and eligibility directly.

---

## Week 1 — The levels of evidence and the NeuroMetric thesis

**Goal:** explain, in two minutes, why a good BCI benchmark is not evidence of clinical benefit.

Must read
- [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) §0, §8, §9.
- [`published_bci_functional_measures.md`](../research/published_bci_functional_measures.md) (whole file).
- Dohle et al. 2025, *Adv Sci* ([V-DOI] 10.1002/advs.202501912; PMC12407270).
- Fry et al. 2022, *J Neural Eng*, clinical benefit framework ([V-DOI] 10.1088/1741-2552/ac60ca).
- iBCI-CC Consensus Statement (1 Oct 2026) ([V] https://www.ibci-cc.org/s/iBCI-CC-Assessment-of-the-iBCI-Endpoints-for-Clinical-Utility.pdf).

Optional
- Sawyer et al. 2026, *J Neural Eng*, MAH → COI → COA framework ([V-DOI] 10.1088/1741-2552/ae9eee).

Exercises
1. Take five metrics from [`clinical_trials.md`](../research/clinical_trials.md) §3.1 and place each at a level
   (1–8). For each, write which confounder from KNOWLEDGE_BASE §9 most threatens its link to the next level.
2. Read `DECISIONS.md` D-005 and D-006. In three sentences, explain why metric functions may only use
   observable data.

Deliverable: a one-page "levels" explainer you could hand to a clinician.

---

## Week 2 — Neuroscience foundations for motor and speech BCIs

**Goal:** understand what motor cortex encodes and why paralysis does not silence it.

Must read
- Georgopoulos et al. 1986 ([V-DOI] 10.1126/science.3749885).
- Hochberg et al. 2006 ([V-DOI] 10.1038/nature04970).
- Shenoy & Carmena 2014, *Neuron* ([V-DOI] 10.1016/j.neuron.2014.08.038).

Optional
- Any standard neuroscience text on the motor system and speech production (e.g. Kandel et al., *Principles
  of Neural Science*, or Purves et al., *Neuroscience*) [PK — any recent edition].
- Kunz et al. 2025, inner speech ([V-DOI] 10.1016/j.cell.2025.06.015), for the privacy implications.

Free course
- HarvardX *Fundamentals of Neuroscience, Part 1* on edX ([V] page resolves:
  https://www.edx.org/learn/neuroscience/harvard-university-fundamentals-of-neuroscience-part-1-the-electrical-properties-of-the-neuron).
- or MIT OpenCourseWare 9.40 *Introduction to Neural Computation* (Spring 2018) ([V]
  https://ocw.mit.edu/courses/9-40-introduction-to-neural-computation-spring-2018/), lectures on spike
  trains and tuning.

Exercises
1. Write a 30-line Python script that simulates 50 cosine-tuned neurons (random preferred directions, Poisson
   spikes in 20 ms bins) and decodes direction with a population vector. Plot decoding error against the
   number of neurons. This makes "more channels → better decoding, with diminishing returns" concrete.
2. Open `experiments/external_data/nlb_mc_rtt_dandi000129/README.md`. List which fields are behaviour and which
   are neural. Note why NeuroMetric does not need the `units` table (it measures L3, not L1).

---

## Week 3 — Neural engineering: interfaces, decoders and failure modes

**Goal:** speak precisely about Utah arrays vs N1 vs Stentrode vs ECoG vs EEG, Kalman/ReFIT vs RNN decoders,
and drift.

Must read
- [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) §1–4.
- Gilja et al. 2012, ReFIT ([V-DOI] 10.1038/nn.3265).
- Willett et al. 2019, feedback-control model ([V-DOI] 10.1038/s41598-019-44166-7). This underpins the
  simulator design.
- Perge et al. 2013, intra-day instabilities ([V-DOI] 10.1088/1741-2560/10/3/036004).
- Oxley et al. 2021 (Stentrode, [V-DOI] 10.1136/neurintsurg-2020-016862) and Vansteensel et al. 2016 (home ECoG,
  [V-DOI] 10.1056/NEJMoa1608085).

Optional
- Wolpaw & Wolpaw (eds) 2012, *Brain–Computer Interfaces: Principles and Practice* ([V-DOI]
  10.1093/acprof:oso/9780195388855.001.0001), chapters on signal acquisition and translation algorithms.
- Willett et al. 2023 and Card et al. 2024 (speech; DOIs in KNOWLEDGE_BASE §11).

Free course
- Neuromatch Academy *Computational Neuroscience* ([V] https://compneuro.neuromatch.io/): the "Linear
  systems", "Hidden dynamics" and "Machine learning" tutorials (Kalman filter and HMM notebooks are directly
  relevant).
- University of Washington *Computational Neuroscience* on Coursera ([V] https://www.coursera.org/learn/computational-neuroscience),
  weeks on neural decoding.

Exercises (repository)
1. Read `src/neurometric/simulator/decoder.py` (`DegradationConfig`). For each parameter, write which real
   phenomenon it stands for (e.g. `drift_rate_per_min` → non-stationarity; `dropout_enter_per_s` → signal
   dropout; `false_select_per_min` → click decoder false positives; `latency_ms` → latency budget).
2. **Run the simulator.** In `neurometric/`:
   ```python
   import numpy as np
   from neurometric.simulator.modalities import MODALITIES, sample_population
   from neurometric.simulator.tasks import run_iso
   rng = np.random.default_rng(1)
   mod = MODALITIES["bci_cursor_good_sim"]
   users, ability = sample_population(mod.user, 8, rng)
   trials, tp = run_iso(mod, users, 8, rng, D=400, W=60)
   print(tp[["participant", "tp_bps", "we_px", "mt_ms", "error_rate"]])
   ```
   (Checked on 2026-11-27: throughput around 0.3–1.3 bits/s across simulated participants.) Repeat with
   `"mouse_sim"`, `"eye_gaze_sim"` and `"bci_cursor_poor_sim"` and tabulate mean throughput. Then pass
   `degradation=mod.degradation.with_(latency_ms=300)` to `run_iso` and record the change.
3. Run one registered sweep:
   `python -m neurometric.experiments.registry C_latency --n 20 --processes 2`
   and inspect `experiments/results/C_latency/`. Write which metrics are most and least sensitive to
   latency, and why (KNOWLEDGE_BASE §4.3).

Deliverable: a one-page comparison table of interface classes for an investor.

---

## Week 4 — HCI measurement: Fitts' law and text-entry evaluation

**Goal:** compute and defend pointing throughput and text-entry metrics, and explain their assumptions.

Must read (all in [`methods_references.md`](../research/methods_references.md) §A–C, with DOIs [V-DOI])
- Soukoreff & MacKenzie 2004 (the throughput recipe; 10.1016/j.ijhcs.2004.09.001).
- MacKenzie, Kauppinen & Silfverberg 2001 (path accuracy measures).
- Soukoreff & MacKenzie 2003 (text-entry error taxonomy; 10.1145/642611.642632).
- Wolpaw et al. 1998 / 2002 (ITR) and Yuan et al. 2013 (ITR misuse).
- Nuyujukian et al. 2015 (achieved bitrate; 10.1109/TBME.2014.2354697).

Optional
- MacKenzie, *Human-Computer Interaction: An Empirical Research Perspective* (Morgan Kaufmann, 2013) [PK],
  chapters on experiment design and modelling.
- Play Neuralink's webgrid once ([V] https://neuralink.com/webgrid) and note what it does not measure.

Exercises (repository)
1. **Reproduce a throughput calculation by hand.** Using `trials` from Week 3:
   ```python
   p0 = trials[(trials.participant == 0) & (~trials.timeout)]
   We = 4.133 * p0.endpoint_dx_px.std(ddof=1)        # effective width
   De = p0.amplitude_px.mean()                       # effective distance
   IDe = np.log2(De / We + 1)                        # effective index of difficulty
   MT = p0.movement_time_ms.mean() / 1000            # seconds
   print(IDe / MT, tp.tp_bps[0])
   ```
   (Checked 2026-11-27: the two numbers agree to three decimals.) Then do the same on paper for 5 made-up
   trials. Explain why timeouts are excluded and what bias that introduces (see the `tp_flags` text produced by
   `fitts_throughput` in `src/neurometric/metrics/pointing.py`).
2. Compute Wolpaw ITR and achieved bitrate for 30 correct and 2 incorrect selections on a 24-item grid in 60 s:
   `from neurometric.metrics.pointing import achieved_bitrate, wolpaw_itr_bits`. Explain in two sentences why
   they differ.
3. With `src/neurometric/metrics/text.py`, score a transcribed phrase containing two corrected and one
   uncorrected error. Identify C, INF, IF and F by hand first, then check against the code.
4. Read `tests/test_metrics_analytic.py` and find one test that checks a metric against a hand-derived value.

---

## Week 5 — Psychometrics I: classical test theory, reliability and measurement error

**Goal:** choose and report the right ICC form, SEM and MDC for a performance task.

Must read
- Koo & Li 2016 ([V-DOI] 10.1016/j.jcm.2016.02.012).
- Weir 2005, ICC and SEM for test–retest ([V-DOI] 10.1519/15184.1).
- de Vet et al. 2006, agreement vs reliability ([V-DOI] 10.1016/j.jclinepi.2005.10.015).
- Bland & Altman 1986 (in `methods_references.md` §D).
- [`methods_references.md`](../research/methods_references.md) §D (all).

Book (choose one)
- de Vet, Terwee, Mokkink & Knol 2011, *Measurement in Medicine* ([V-DOI] 10.1017/CBO9780511996214), chapters
  on reliability and measurement error.
- Streiner, Norman & Cairney, *Health Measurement Scales* ([V-DOI] 10.1093/med/9780199685219.001.0001).

Key ideas to be able to explain: observed score = true score + error; reliability = true variance / total
variance, so it depends on how varied the sample is; SEM is in the units of the score; MDC95 = 1.96 × √2 × SEM
is the smallest *individual* change you can distinguish from noise.

Exercises (repository)
1. **Compute an ICC.**
   ```python
   import numpy as np
   from neurometric.psychometrics.reliability import icc, sem_mdc
   rng = np.random.default_rng(0)
   true = rng.normal(2, 0.5, 20)                       # 20 people, true throughput ~2 bits/s
   w = np.c_[true + rng.normal(0, 0.2, 20),            # session 1
             true + 0.1 + rng.normal(0, 0.2, 20)]      # session 2, small practice effect
   r = icc(w, forms=("2,1", "3,1"))
   print(r["table"]); print(sem_mdc(w))
   ```
   Then compute ICC(2,1) **by hand** from the printed mean squares:
   ICC(2,1) = (MSR − MSE) / (MSR + (k−1)·MSE + k·(MSC − MSE)/n). (Checked 2026-11-27: about 0.79.)
2. Explain why ICC(3,1) (consistency) is higher than ICC(2,1) (absolute agreement) here. Which should a
   test–retest study of NeuroMetric tasks report? (Answer in `methods_references.md` §D.)
3. Compare the F-based confidence interval with the generalized confidence interval (`gci_low`) returned by
   `icc`. Why is the GCI so much wider with only two sessions? (Hint: the session variance is estimated with 1
   degree of freedom.) Rerun with 4 sessions.
4. Halve the between-person SD (0.5 → 0.25) and rerun. The SEM barely changes; the ICC falls. Write down why
   this matters when a sponsor compares reliability across populations.
5. Run the simulated test–retest experiment: `python -m neurometric.experiments.registry I_test_retest --n 40`
   and read `experiments/results/I_test_retest/summary.json`. Which metrics would pass an ICC ≥ 0.70 criterion
   in *simulation*? Write why simulation reliability is an upper bound, not an estimate, of human reliability.

---

## Week 6 — Psychometrics II: COSMIN, validity, responsiveness and MCID

**Goal:** design a validation programme a COA reviewer would accept.

Must read
- Mokkink et al. 2010, COSMIN taxonomy (in `methods_references.md` §E) and the COSMIN checklist paper
  ([V-DOI] 10.1186/1471-2288-10-22).
- Mokkink et al. 2020, COSMIN risk-of-bias for outcome measurement *instruments* (performance-based included;
  `methods_references.md` §E).
- Terwee et al. 2007 quality criteria ([V-DOI] 10.1016/j.jclinepi.2006.03.012).
- Revicki et al. 2008, MID methods ([V-DOI] 10.1016/j.jclinepi.2007.03.012).
- Devji et al. 2020, credibility of anchor-based MIDs ([V-DOI] 10.1136/bmj.m1714).
- Norman, Sloan & Wyrwich 2003, the "half a standard deviation" observation ([V-DOI]
  10.1097/01.MLR.0000062554.74615.4C) — know it, and know why it is only supportive.

Anchor-based MCID in one paragraph: ask participants (or clinicians) a global rating of change ("compared with
before, is your ability to use the computer much better / a little better / the same / ..."). The anchor must
itself be understandable and correlate with the score change (≥ about 0.3–0.5). The MCID is the score change
that best separates "a little better" from "the same" (mean change in that group, or an ROC cut-off, adjusted
as in Terwee et al. 2021). Distribution-based values (0.5 SD, 1 SEM, MDC) are supporting evidence only. **An
MCID smaller than the MDC cannot be detected in an individual.**

Exercises (repository)
1. Run `python -m neurometric.experiments.registry K_responsiveness --n 60`. Read the effect sizes (ES, SRM)
   it reports. Write why simulated responsiveness to an *injected* change is not evidence of responsiveness
   to *clinical* change (KNOWLEDGE_BASE §9).
2. Draft a one-page COSMIN-structured validation plan for the ISO pointing task in people with SCI: content
   validity (who decides the task is relevant?), structural validity (n/a for a single score — say why),
   reliability, measurement error, construct validity (write 5 hypotheses with expected correlation
   directions and sizes **before** seeing data), responsiveness and interpretability (MCID anchors).
3. Using `sem_mdc` output from Week 5, state whether a hypothetical MCID of 0.3 bits/s would be detectable in
   an individual.

---

## Week 7 — Rehabilitation science, AT and AAC

**Goal:** understand how clinicians think about function, independence and AT matching.

Must read
- [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) §5–7.
- [`instruments.md`](../research/instruments.md) §1 and §3 (licensing realities).
- WHO ICF overview ([V] https://www.who.int/standards/classifications/international-classification-of-functioning-disability-and-health).
- Sawyer et al. 2025, Digital IADL ([V-DOI] 10.1016/j.ebiom.2025.105732).
- [`clinical_trials.md`](../research/clinical_trials.md) §1 (SRAlab DAI study design).
- Huggins et al. 2011 ([V-DOI] 10.3109/17482968.2011.572978) and Phillips & Zhao 1993 ([V-DOI]
  10.1080/10400435.1993.10132205).

Optional
- Cook & Polgar, *Assistive Technologies: Principles and Practice* [PK — any recent edition], chapters on
  access methods.
- Beukelman & Light, *Augmentative and Alternative Communication* [PK], chapters on access and assessment.
- The CMS Section GG self-care items and the 6-level assistance scale (via the IRF-PAI manual) [PK URL — find on cms.gov].

Exercises
1. Turn on switch control on a phone or tablet (iOS Switch Control or Android Switch Access) and write a text
   message using one switch with 1 s scanning. Time yourself. Then compute the theoretical scan steps per
   character for your layout (`methods_references.md` §G) and compare with `src/neurometric/simulator/scanning.py`.
2. Use Apple Head Pointer ([V] https://support.apple.com/guide/mac-help/use-head-pointer-mh41557/mac) or
   another free head pointer to complete the browser battery (`cd web && npm install && npm run dev`). Note
   every place where the battery was hard to use. File them as accessibility issues.
3. Shadow (with permission) an occupational therapist or AT specialist for half a day, or interview one
   (use [`interview_guides.md`](../research/interview_guides.md)).

---

## Week 8 — Regulatory science

**Goal:** answer "Are you a medical device?" and "Is this Part 11 compliant?" correctly and briefly.

Must read (primary documents; all [V] in [`regulatory_landscape.md`](../research/regulatory_landscape.md))
- FDA iBCI guidance (2021): https://www.fda.gov/media/120362/download — sections on clinical considerations,
  endpoints, home use.
- FDA PFDD Guidance 3 (final, Oct 2025): selecting, developing or modifying fit-for-purpose COAs.
- FDA DHT guidance (Dec 2023): https://www.fda.gov/media/155022/download — verification vs validation.
- 21 CFR Part 11: https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11 and the Oct 2024
  eSystems Q&A (https://www.fda.gov/media/166215/download).
- FD&C Act §520(o)(1)(D) (software that only transfers, stores or displays device data).
- MDDT programme page (https://www.fda.gov/medical-devices/medical-device-development-tools-mddt).

Free course
- FDA CDRH Learn ([V] https://www.fda.gov/training-and-continuing-education/cdrh-learn): modules on device
  classification, Q-Submissions, IDE and software as a medical device.

Exercises
1. Write NeuroMetric's **intended use statement** in two versions: (a) research data collection only, (b)
   clinician-facing score used to adjust therapy. For each, apply the table in `regulatory_landscape.md` §10
   and state whether it is likely a device.
2. Make a Part 11 gap list for this repository: what exists (`src/neurometric/study/audit.py`,
   `study/security.py`, `study/permissions.py`) versus §11.10 (a)–(k). Do not claim compliance; list gaps.
3. Draft a one-page "DHT verification and validation" plan for the browser battery, using the timing protocol
   in [`browser_timing.md`](../research/browser_timing.md) §5.

---

## Week 9 — Clinical research, GCP and ethics

**Goal:** be ready to work under an IRB protocol and talk to clinical sites.

Must read
- ICH E6(R3) Good Clinical Practice, final version adopted 6 January 2025 ([V]
  https://database.ich.org/sites/default/files/ICH_E6%28R3%29_Step4_FinalGuideline_2025_0106.pdf). Focus on
  principles, risk-proportionate approaches, and computerised systems/data governance.
- Declaration of Helsinki (2013 version, [V-DOI] 10.1001/jama.2013.281053; check for the 2024 revision [PK]).
- 21 CFR 50 (informed consent), 56 (IRBs) and 812 (IDE) — skim [PK URLs on eCFR].
- ISO 14155 (GCP for medical device investigations) — know it exists; it is paywalled [PK].
- CONSORT 2010 explanation ([V-DOI] 10.1136/bmj.c869), for how trials are reported.

Free course
- **GCP and human-subjects training:** complete the CITI Program modules your institution requires (UIUC uses
  institutional IRB training — check with the Office for the Protection of Research Subjects; [PK]).
  Note: the old free NIH/NIDA GCP training domain (gcp.nihtraining.com) now serves a different, commercial
  "PHRP Training" site ([V] observed 2026-11-27), so do not rely on older links to it.

Exercises
1. Draft a consent-form section explaining (in plain language) what NeuroMetric logs and does **not** log,
   using the scope rules in [`platform_matrix.md`](../research/platform_matrix.md) (no keystroke content,
   screenshots, messages or gaze coordinates).
2. Write how a person with locked-in syndrome would give consent through their AT, and how you would confirm
   understanding (see FAQ Q29).
3. Read `src/neurometric/study/audit.py` and explain what an auditor would check.

---

## Week 10 — Health economics and payer evidence

**Goal:** explain why FDA approval is not coverage, and what evidence moves a payer.

Must read
- [`health_economics_payer.md`](../research/health_economics_payer.md) (whole file).
- [`regulatory_landscape.md`](../research/regulatory_landscape.md) §7 (RAPID, TCET, benefit categories,
  NCD 50.1).
- CHEERS 2022 reporting standard ([V-DOI] 10.1016/j.jval.2021.11.1351).
- Anthem policy DME.00052 on BCI rehabilitation devices ([V] link in
  [`neuromodulation_market.md`](../research/neuromodulation_market.md)) — read it as a payer's critique.

Optional
- Neumann et al. (eds) 2016, *Cost-Effectiveness in Health and Medicine*, 2nd ed ([V-DOI]
  10.1093/acprof:oso/9780190492939.001.0001).
- Drummond et al., *Methods for the Economic Evaluation of Health Care Programmes* [PK, 4th ed 2015].

Exercises
1. Reproduce the caregiver-time arithmetic in `health_economics_payer.md` §3.3, then make it a
   one-way sensitivity analysis (hours saved 0.25–2/day; wage $17.21–$34/h). Note which inputs are [V] and
   which are [PK]/[HYP].
2. Look at `src/neurometric/economics/` and write which payer question each function answers.
3. Write a 150-word "medical necessity" argument for BCI-based *communication* versus general computer use,
   using NCD 50.1's distinction.

---

## Week 11 — Customers, competition and business model

**Goal:** know your buyers, your competitors and what would prove you wrong.

Must read
- [`competitors.md`](../research/competitors.md) §S (synthesis, entry niche, falsification tests F1–F6).
- [`prospects.md`](../research/prospects.md) and [`comparable_pricing.md`](../research/comparable_pricing.md).
- [`interview_guides.md`](../research/interview_guides.md).
- Fitzpatrick, *The Mom Test* [PK] — how to run customer interviews that do not lie to you.

Exercises
1. Conduct three discovery interviews (one sponsor, one clinician, one AT user or care partner) with the
   interview guides. Record what they said about willingness to pay, not what they said about your idea.
2. Update the falsification table in `competitors.md` §S4 with what you learned (do not edit research files
   silently; add dated notes).
3. Write the 10-slide outline of an investor deck that is honest about the concentration risk
   (`competitors.md` §S5).

---

## Week 12 — Integration: a validation study protocol and a pitch

**Goal:** turn the twelve weeks into two artefacts.

1. **Stage-1 validation protocol (draft, 6–8 pages):** objectives at named levels (L3–L5), population (healthy
   adults + AT users), design (within-person crossover of access methods; test–retest at 1 week), measures
   (ISO pointing, typing, grid, ADL tasks; NASA-TLX, SUS), sample-size reasoning for ICC precision, COSMIN
   hypotheses written in advance, analysis plan (ICC(A,1), SEM, MDC95, Bland–Altman across devices), data
   handling (Part 11 gap list from Week 8), and risks.
2. **Founder narrative (10 minutes):** levels → gap (Dohle 17.9%) → why neutral home evidence → what is built
   (repository) → what is validated vs simulated → next study → ask. Rehearse it against
   [`FAQ_HARD_QUESTIONS.md`](FAQ_HARD_QUESTIONS.md).

Final self-test: answer Q1, Q13, Q17, Q18, Q19 and Q26 of the FAQ aloud without notes, then compare.

---

## Reading list at a glance (by priority)

| Priority | Item | Label |
|---|---|---|
| 1 | Dohle et al. 2025; iBCI-CC consensus 2026; FDA iBCI guidance 2021 | [V-DOI]/[V] |
| 1 | Soukoreff & MacKenzie 2004; Soukoreff & MacKenzie 2003; Nuyujukian et al. 2015 | [V-DOI] |
| 1 | Koo & Li 2016; de Vet et al. 2006; Revicki et al. 2008; Devji et al. 2020 | [V-DOI] |
| 1 | FDA DHT guidance 2023; Part 11 + eSystems Q&A 2024 | [V] |
| 2 | Gilja et al. 2012; Willett et al. 2019; Shenoy & Carmena 2014; Perge et al. 2013 | [V-DOI] |
| 2 | Sawyer et al. 2025 (Digital IADL); Sawyer et al. 2026 (pivotal COAs); Fry et al. 2022 | [V-DOI] |
| 2 | ICH E6(R3) | [V] |
| 3 | Wolpaw & Wolpaw 2012; de Vet et al. 2011 or Streiner et al.; Neumann et al. 2016 | [V-DOI] |
| 3 | Hernán & Robins, *Causal Inference: What If* | [V] |
| 3 | Kandel/Purves; MacKenzie HCI book; Cook & Polgar; Beukelman & Light; Drummond; Fitzpatrick | [PK] |
