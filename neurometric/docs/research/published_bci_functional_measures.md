# Published measures of BCI functional performance and clinical-utility frameworks

Prepared for NeuroMetric. Accessed 2026-11-27. Labels per `CONVENTIONS.md`.
Many classic definitions below (Wolpaw ITR, Fitts' law, typing-rate conventions) are textbook
material that could not be re-fetched this session. They are labeled [PK] and are **not
re-verified**. Items checked against a primary source this session are [V], [RF] or [CC] with URLs.

---

## 1. The measurement hierarchy

The literature and the 2026 consensus documents converge on a chain with four levels:

| Level | What it measures | Examples | Who cares most |
|---|---|---|---|
| L1 Signal / decoder | Neural-signal quality, decoder accuracy | impedance, SNR, channel count, decoding accuracy, R² | Engineers, FDA (device performance) |
| L2 Task performance (PerfO) | Speed and accuracy on standardized tasks | ITR/bitrate, webgrid BPS, Fitts throughput, CCPM/WPM, WER/PER, success rate, time to target | Engineers, FDA (effectiveness) |
| L3 Function / activity (COA) | Ability to perform real activities independently | Digital IADL, DAI index, CARE/Section GG-type independence, ARAT/SCIM (effector BCIs), COPM | FDA (clinical benefit), CMS |
| L4 Health outcome / burden / participation | Feels and survives; care burden; participation | PIADS, QUEST, QoL (WHOQOL-BREF, McGill, ALSSQOL), Zarit Burden, care hours, safety-call ability | CMS and private payers |

- The iBCI-CC "shared measurement chain" is exactly L2 → L3 → L4: "from device performance, to
  functional or activity-level outcome, to health outcome or change in care burden".
  https://www.ibci-cc.org/s/iBCI-CC-Assessment-of-the-iBCI-Endpoints-for-Clinical-Utility.pdf [V]
- Dohle et al. (2025) found that iBCI studies overwhelmingly report L1/L2 (see Section 2). [RF]

---

## 2. Evidence of the gap: Dohle et al. 2025 systematic review

- **Citation:** Dohle E, Swanson E, Jovanovic L, Yusuf S, Thompson L, Layard Horsfall H, Muirhead W,
  Bashford L, Brannigan J. "Toward the Clinical Translation of Implantable Brain–Computer Interfaces
  for Motor Impairment: Research Trends and Outcome Measures." *Advanced Science* 2025;12(32):e01912.
  Published online 23 July 2025. DOI 10.1002/advs.202501912. PMCID PMC12407270; PMID 40697162.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC12407270/ [V]/[RF]
- **Scope:** 112 iBCI studies published 2000–2024.
- **Findings:**
  - Most (69.6%) reported outcome measures prospectively, but these "primarily related to decoding
    (69.6%) and task performance (62.5%), **with only 17.9% assessing clinical outcomes**" (20/112).
  - Accuracy was the most common engineering metric (74.1%).
  - Communication speed (CCPM or WPM) was reported in 16.1%.
  - **ITR in only 8%.**
  - Clinical measures were heterogeneous: ARAT, GRASSP and Grasp Release Test in SCI studies;
    ADL, AT measures and EQ-5D-5L in ALS studies. [V]
- **Recommendations:**
  - Organize outcomes by feels / functions / survives (following FDA and Fry et al. 2022).
  - Use PIADS/SF-36 for "feels" and consider caregiver-burden measures such as the Zarit Burden
    Interview.
  - Develop a **digital ADL instrument** urgently, and consider a "digital motor output" measure.
  - Build measures through multi-stakeholder consensus. [V]
- **Playbook check:** "Dohle et al. Advanced Science 2025, 17.9%, PMC12407270" is **confirmed**. [V]

---

## 3. Task-performance (L2) metrics

### 3.1 Information transfer rate (ITR, "Wolpaw bitrate") [PK]
- Formula: B = log2 N + P·log2 P + (1−P)·log2[(1−P)/(N−1)] bits per selection, multiplied by
  selections per minute. N is the number of targets; P is accuracy.
- Assumes equiprobable targets, uniform errors, and no error correction. It overstates practical
  communication when errors must be corrected, and it ignores latency.
- Validation status: a mathematical construct. It has no clinical validation and no MCID.
- Dohle et al. found it in only 8% of iBCI studies [V]. Ottawa NCC (NCT03100110), OHSU BCI-FIT
  (NCT04468919, mutual information with a language model) and Cognixion (NCT07871071) register it
  as an outcome. [V]

### 3.2 Achieved bitrate / net-selection bitrate [PK]
- Formula: log2(N−1) × max(correct − incorrect, 0) / time. Each error is assumed to cost one
  correction selection.
- Used in Stanford/BrainGate cursor-typing papers (e.g., Nuyujukian et al. 2015; Pandarinath et al.
  2017 *eLife*). [PK]
- More conservative than Wolpaw ITR, but grid-task-specific.

### 3.3 Neuralink "webgrid" bits per second (BPS) [CC]/[V for the formula as published]
- Neuralink publishes the formula: **BPS = log2(N_click · grid_size² − 1) × max(correct − incorrect, 0) / 60**.
  The task is a timed (60 s) grid-selection game, playable publicly at neuralink.com/webgrid.
- Neuralink says BPS "measures max information transfer rate when using the cursor … It is the
  closest thing we have to an objective metric for decoder quality."
- Company-reported figures: "median Neuralinker BPS is roughly 10". Record of **11.32 BPS**
  (previous record 10.39). Source: Neuralink blog, 1 Oct 2026,
  https://neuralink.com/updates/pretraining-on-50000-hours/ [CC]
- Variants are now registered by others:
  - StairMed RISE (NCT06829212): "BPS … net number of correct targets selected per minute … and the grid size". [V]
  - BCIFlex LEAP (NCT07784088): "Brain Control Fluency Index … mean Information Transfer Rate measured by the Web-Grid Task". [V]
- **Status:** a de facto industry throughput benchmark.
  - Not a COA.
  - Not validated against function.
  - Sensitive to grid size, click types and the definition of an error.
  - Maximum-performance (peak) metric, not typical daily performance. [INF]

### 3.4 Paradromics' position: achieved ITR plus latency (SONIC) [CC]
- Paradromics blog (3 Oct 2025): "The most honest method is to report the data you actually
  transferred"; latency must be reported alongside ITR.
- SONIC benchmark (Perkins et al. 2025, bioRxiv) uses preclinical sheep auditory decoding. It claims
  200+ bps at 56 ms latency.
- Company advocacy; preclinical; not peer-reviewed at the time of the blog.
  https://www.paradromics.com/blog/bci-benchmarking [CC]

### 3.5 Fitts' law throughput [PK]
- ISO 9241-9 / 9241-411 pointing tasks: throughput = effective index of difficulty / movement time
  (bits/s).
- Used in some BCI cursor papers to compare with mouse, trackpad and eye-gaze.
- Good for *input-agnostic* comparison, which is directly relevant to NeuroMetric. Lab-only.
  Weak link to function.

### 3.6 Typing and communication rate [PK unless noted]
- CCPM (correct characters per minute), WPM, **CWPM** (correct words per minute; Neuralink VOICE
  secondary, NCT07224256 [V]), characters or keywords per minute (CortiCom-Utrecht [V]).
- Speech BCIs add WER/PER (BrainGate BG-Speech-02 [V]), BLEU/BERTScore (RECLAIM [V]) and CER
  (StairMed WISE [V]).
- Landmarks [PK, not re-verified]:
  - Willett et al. 2021 handwriting BCI, about 90 CCPM.
  - Willett et al. 2023 and Metzger et al. 2023 speech neuroprostheses, about 62–78 WPM.
  - Card et al. 2024 *NEJM* (UC Davis), high-accuracy speech decoding.
- Comparability problems:
  - copy versus free typing
  - vocabulary size
  - language-model assistance
  - whether time for error correction is counted
  - Paradromics: WPM "can mislead" when ITRs differ [CC]
- BrainGate BG-Speech-01 pre-specifies a **≥5 WPM** threshold, a rare example of an a priori
  success criterion. [V]

### 3.7 Task success rate and time (CortiCom-style) [V]
- CortiCom (NCT03567213): "ratio of successful trials to total trials" and "time to complete
  successful trials (in seconds)".
- CortiCom-Utrecht (NCT06207591): sensitivity/accuracy thresholds (>80% for 1-command; 90%/80% for
  6-command) and **hours of independent home use**.
- Simple and transparent. Task-specific; not normed.

### 3.8 Real-world use metrics [V]
- Hours of BCI use per day (Utrecht NCT02224469; CortiCom-Utrecht).
- Hours per month (Neuracle, StairMed, NeuroXess, BCIFlex).
- **Voluntary daily use time per modality** (Cognixion NCT07871071, *primary*). The registry
  argues it is "robust to learning effects, communication-partner effects, and prompt-driven
  artifacts".
- Validation status: face-valid behavioral endpoints. Interpretation depends on context (need,
  caregiver availability). No MCID.

---

## 4. Function-level (L3) clinical outcome assessments

### 4.1 Digital IADL Scale (Sawyer et al. 2025) [RF]
- **Citation:** Sawyer A, Brannigan J, Spielman L; BCI Functional Outcome Measures Group; Putrino D,
  Fry A. "Development of a novel clinical outcome assessment: digital instrumental activities of
  daily living." *EBioMedicine* 2025;116:105732. DOI 10.1016/j.ebiom.2025.105732. PMID 40424668;
  PMCID PMC12155723. Abstract retrieved via PubMed E-utilities. [V]
- **Method:**
  - Systematic review: 1,250 IADL items, of which 353 met criteria, deduplicated to 77, with 42
    retained after Delphi.
  - Survey of individuals with lived experience: 152 items, 132 meeting criteria, 41 after
    deduplication.
  - Item rating reduced the combined pool to 69 items.
  - Focus groups produced the final structure: **9 domains, 37 items**, with suggested response
    scales.
- **Status:** "initial development … which will be submitted to further validation". Content-
  validity stage only. No published reliability, construct validity, responsiveness or MCID was
  found this session. **NEEDS FORMAL VALIDATION.**
- COI: AF disclosed Synchron stock options; JB and LS disclosed Synchron consulting fees. [V]
- Registered use: BCIFlex LEAP (NCT07784088) lists "Digital Instrumental Activities of Daily Living
  (dIADL)". NCT07407725 cites the paper as background. [V]

### 4.2 CARE scale / CMS Section GG response scale [PK]/[CC]
- CMS's standardized functional items (from the CARE item set, now Section GG in IRF-PAI, MDS,
  OASIS, LCDS) rate assistance on a 6-level scale, from "06 Independent" to "01 Dependent".
  IRF-PAI Section GG's 6-point assistance scale is confirmed in the NCT07407725 record [V].
- Validated for post-acute care self-care and mobility (e.g., Deutsch et al. 2023, cited in
  NCT07407725). [PK]/[V citation]
- Not validated for digital tasks.
- Paradromics (Matt Angle, 25 Nov 2025, "Measuring What Matters in BCI") reports that Sawyer et
  al. "strongly suggest adopting the CARE scale". Paradromics argues it is a good start but
  incomplete because it captures independence, not performance quality. Its proposal: "graded
  scales for both must exist", an independence × performance 2×2.
  https://www.paradromics.com/blog/measuring-what-matters-in-bci [CC]
- **Why it matters:** CARE/Section GG is *CMS's own language*. A digital-function score expressed
  on that scale is payer-legible. [INF]

### 4.3 SRAL Digital Assessment Interface (DAI) index (in development) [V]
- Defined in NCT07407725: a PerfO battery (click, scroll, type, click-and-drag within simulated
  dADLs) plus NASA-TLX, SUS (patient and clinician versions), modified COPM and PIADS, combined
  into an index.
- Validation with Section GG, WHOQOL-BREF, ALSFRS-R and ISNCSCI as anchors. Healthy-control norms.
- **Status:** development. **NEEDS FORMAL VALIDATION.** See `clinical_trials.md`.

### 4.4 Fry et al. 2022: clinical benefit framework for PC-control BCIs [RF]
- Fry A, Chan HW, Harel NY, Spielman LA, Escalon MX, Putrino DF. "Evaluating the clinical benefit of
  brain-computer interfaces for control of a personal computer." *J Neural Eng* 2022 (published
  2022-04-01). DOI 10.1088/1741-2552/ac60ca. [V]
- Framework:
  - **Feels**: various PROMs.
  - **Functions**: ADLs, noting that "new instruments that are sensitive to increases in functional
    independence via the ability to perform digital tasks may be needed".
  - **Survives**: not previously evaluated; patient-initiated communication channels might improve
    health outcomes. [V]

### 4.5 Existing rehabilitation and AT instruments used in BCI trials [PK for psychometrics; V for registry use]
| Instrument | Construct | Used in (registry) | Validation note |
|---|---|---|---|
| ARAT | Upper-limb function | JHU BiCNS, Pittsburgh, Neuracle, NeuroXess, Grenoble, EPFL | Validated in stroke/SCI; MCID published for stroke [PK] |
| GRASSP | SCI hand function | EPFL UP2, Miami | Validated in cervical SCI [PK] |
| SCIM III | SCI independence | STIMO-BSI, Miami | Validated [PK] |
| Barthel Index | Basic ADL | NeuroXess, Nanjing | Validated; ceiling and floor issues [PK] |
| COPM (modified) | Self-identified occupational goals | SRAL DAI | COPM validated; modification is not [PK] |
| PIADS | Psychosocial impact of AT | CONVOY, Utrecht, BCIFlex, SRAL | Validated in AT users [PK] |
| QUEST 2.0 | AT satisfaction | Utrecht x2, Nanjing | Validated [PK] |
| ATD PA | AT predisposition / match | Neuralink CONVOY | Validated in AT matching [PK] |
| SUS | Usability | SRAL, Cognixion | Generic usability; not a clinical COA [PK] |
| NASA-TLX | Workload | Utrecht, OHSU, Cognixion, SRAL | Human-factors tool [PK] |
| ALSFRS-R | ALS function | SRAL (characterization), Cognixion | Validated disease-progression measure; not a device-benefit measure [PK] |
| Zarit Burden Interview | Caregiver burden | Cognixion | Validated [PK] |

---

## 5. Clinical-utility frameworks (2025–2026)

### 5.1 MAH → COI → COA (Sawyer et al., J Neural Eng 2026) [RF]
- Summary of the 11th BCI Society Meeting 2025 workshop, held with the iBCI-CC.
  *J Neural Eng* 23(5), published 2026-09-11. DOI 10.1088/1741-2552/ae9eee.
  https://iopscience.iop.org/article/10.1088/1741-2552/ae9eee [V]
- Approach: identify **meaningful aspects of health (MAHs)**, define **concepts of interest (COIs)**,
  then select or adapt **COAs** that capture "both functional impact and real-world use".
- Challenges named:
  - patient heterogeneity
  - "the lack of widely validated and fit-for-purpose COAs"
  - home and daily-life measurement
- Lesson drawn from ADAPT-PD: capture performance in home settings with context-sensitive, flexible
  metrics. [V]
- **Playbook check:** "Sawyer et al. DOI 10.1088/1741-2552/ae9eee on BCI pivotal-trial COAs" is
  **confirmed**. Full author list: Sawyer, Welle, French, Kelemen, Bashford, Kramer, McMullen,
  Franklin, Angle, Herrmann, Oxley, Dister, Chetty, Radcliffe, Kowalczyk, Bose, Farooqui, Hochberg. [V]

### 5.2 iBCI-CC consensus statement (1 Oct 2026) [V]
- Three principles:
  1. A single existing measure is *unlikely* to suffice, so use combinatory, new or mixed strategies.
  2. A shared measurement chain respecting distinct FDA/CMS standards.
  3. PROs, QoL and participation are not categorically secondary. Care-partner burden,
     functional communication and participation are "key outcomes of interest, particularly for
     payor decision-making".
- See `regulatory_landscape.md` Section 6.

### 5.3 FDA/NIH workshop (Sept 2024) [PK]
- "Implanted Brain-Computer Interface Clinical Outcome Assessments to Demonstrate Benefit" (FDA/NIH
  joint workshop). Search results point to an FDA media file (fda.gov/media/182567/download). That
  file was not opened this session. [UNR] for content.

### 5.4 2023 COA consensus workshop [PK]
- Search results reference a 2023 workshop report on building consensus for COAs in BCI devices.
  It found agreement on the need for new COAs but deferred instrument selection. Not re-verified.

---

## 6. What is validated vs not

| Measure | Validated as | Not validated as | Label |
|---|---|---|---|
| ITR / bitrate / BPS | Mathematical throughput | Clinical benefit; no MCID; peak, not typical use | [PK]/[CC] |
| Fitts throughput | Pointing-device performance (ISO) | Clinical benefit in BCI | [PK] |
| CCPM/WPM/CWPM, WER/PER | Task performance | Function; no MCID; protocol-dependent | [PK]/[V] |
| Success rate / time (CortiCom) | Task performance | Function | [V] |
| Home-use hours | Behavioral exposure | Benefit without context | [V] |
| Digital IADL | Content validity (development) | Reliability, construct validity, responsiveness, MCID | [RF] |
| CARE / Section GG | Post-acute self-care and mobility independence | Digital tasks | [PK] |
| SRAL DAI index | (under development) | Everything pending | [V] |
| PIADS, QUEST, COPM, SUS, NASA-TLX | AT/usability constructs | iBCI effectiveness endpoints with MCID | [PK] |
| ARAT, GRASSP, SCIM, Barthel | Motor and ADL function in SCI/stroke | Digital-control BCIs | [PK] |

**No BCI-specific COA is qualified by FDA (MDDT) or validated for a pivotal effectiveness claim**
as of 2026-11-27. [V] (MDDT list) / [INF]

---

## 7. Implications for NeuroMetric [INF]
1. **Own the L2 → L3 bridge.** Capture input-agnostic interaction primitives (pointing throughput,
   selection accuracy, text-entry rate, error and correction cost, latency) consistently across
   BCI, eye-gaze, switch and voice. Map them to dADL task completion and to CARE-style independence
   levels. This is what Digital IADL and DAI need in order to scale, and what the iBCI-CC chain
   describes.
2. **Report peak and typical performance.** Report webgrid-style BPS (peak) alongside home typical
   performance and voluntary-use time. This answers both the Neuralink-style benchmark and the
   Cognixion-style real-world endpoint.
3. **Plan the validation program explicitly** under PFDD Guidance 3: content validity (lived
   experience), test-retest reliability, construct validity versus Section GG/SCIM/ALSFRS-R,
   responsiveness, and anchor-based meaningful change. Consider an MDDT proposal for a defined
   context of use.
4. **Avoid becoming one sponsor's metric.** Neutrality is the asset, because each company currently
   favors its own metric (BPS, achieved ITR, independence framing).
