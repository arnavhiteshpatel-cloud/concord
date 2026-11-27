# Measurement methodology references (with implementation takeaways)

Accessed 2026-11-27. Each DOI below was resolved against the Crossref API on that date (author,
year, title and venue all match). That check is what the **[V-DOI]** label means.

Formulas and assumptions are written from prior knowledge of the papers. They were **not**
re-read in full text this session, so each carries **[PK]** unless stated otherwise. Re-check
against the PDF before freezing code.

ISO standards are paywalled and could not be fetched (iso.org returned 403). Their status comes
from search excerpts of iso.org and national-body stores.

---

## A. Pointing / Fitts' law

| Ref | DOI / source | Takeaway for implementation |
|---|---|---|
| Fitts 1954, J Exp Psychol 47:381-391 | 10.1037/h0055392 [V-DOI] | Original law. ID = log2(2A/W) [PK]. Historical only; use the Shannon form below. |
| MacKenzie 1992, Human-Computer Interaction 7:91-139 | 10.1207/s15327051hci0701_3 [V-DOI] | Shannon formulation ID = log2(D/W + 1). When only the error rate is known, We = W x 2.066 / z(1 - Err/2) [PK]. |
| ISO 9241-9:2000 (withdrawn) and **ISO/TS 9241-411:2012**, "Evaluation methods for the design of physical input devices" | No DOI. https://www.iso.org/standard/54106.html | 9241-411, together with 9241-400/-410/-420, cancels and replaces ISO 9241-4 and 9241-9. 9241-411 is listed as current and confirmed on review (ISO page excerpt; one mirror says 2022, another 2026) [V-search excerpt]. It specifies one-directional and **multidirectional (circular, odd number of targets) tapping tasks** with throughput TP = IDe/MT [PK]. Implement a 2D ring of 13 (or 25) targets with alternating opposite selections, several D x W conditions, and a practice block. |
| Douglas, Kirkpatrick & MacKenzie 1999, CHI '99:215-222 | 10.1145/302979.303042 [V-DOI] | How to run ISO 9241-9 in practice, including the device assessment questionnaire. Useful template for the protocol section. |
| **Soukoreff & MacKenzie 2004**, IJHCS 61:751-789 | 10.1016/j.ijhcs.2004.09.001 [V-DOI] | **The canonical recipe** [PK]. For each participant x condition (D, W): We = 4.133 x SDx, where SDx is the SD of selection endpoints projected on the task axis (signed distance from target centre along the vector from start to target). De = mean actual movement amplitude. IDe = log2(De/We + 1). TP = IDe / MT, with MT in seconds. Participant TP = mean over conditions ("mean of means"); grand TP = mean over participants. Do **not** report 1/b (regression slope) as throughput. Exclude outliers (e.g. misfires or double-clicks) by an a-priori rule and report the rule. |
| Wobbrock et al. 2011, CHI '11:1639-1648, "The effects of task dimensionality, endpoint deviation, throughput calculation, and experiment design on pointing measures and models" | 10.1145/1978942.1979181 [V-DOI] | Compares univariate (SDx) and bivariate (SDx,y) endpoint deviation, 1D vs 2D tasks, and mean-of-means vs slope-based TP [PK]. Takeaway: fix and pre-register each of these choices, and report both univariate and bivariate We for 2D tasks. |
| MacKenzie, Kauppinen & Silfverberg 2001, CHI '01:9-16, "Accuracy measures for evaluating computer pointing devices" | 10.1145/365024.365028 [V-DOI] | **Path-based metrics for cursor trajectories** (the key match for BCI/eye/joystick data) [PK]. Rotate each trial so the task axis is x and y_i is the perpendicular deviation. Counts: TRE (target re-entry), TAC (task-axis crossings), MDC (movement-direction changes, parallel to axis), ODC (orthogonal direction changes). Continuous: MV = sqrt(sum (y_i - ybar)^2 / (n-1)), ME = sum abs(y_i) / n, MO = ybar. Resample to a fixed rate first (e.g. 60-100 Hz) because the counts depend on the sampling rate. |
| Zhai 2004, IJHCS 61:791-809, "Characterizing computer input with Fitts' law parameters" | 10.1016/j.ijhcs.2004.09.006 [V-DOI] | Throughput is not a single constant. Report a and b plus the D-W design range, and don't compare TP across studies with different ID ranges [PK]. |
| Zhai, Kong & Ren 2004, IJHCS 61:823-856, "Speed-accuracy tradeoff in Fitts' law tasks: on the equivalency of actual and nominal pointing precision" | 10.1016/j.ijhcs.2004.09.007 [V-DOI] | The effective-width adjustment does not fully equalize speed and accuracy biases. Instruct participants consistently ("as quickly and accurately as possible") and report error rates alongside TP [PK]. |
| Gori, Rioul & Guiard 2018, ACM TOCHI 25:1-33 | 10.1145/3231595 [V-DOI] | Information-theoretic reformulation (FITTS). Useful when error rates are high, as with BCIs; consider as a secondary analysis [PK]. |

## B. Text entry

| Ref | DOI | Takeaway |
|---|---|---|
| MacKenzie & Soukoreff 2002, HCI 17:147-198, "Text entry for mobile computing: models and methods" | 10.1207/S15327051HCI172&3_2 [V-DOI] | WPM = ((abs(T) - 1) / S) x 60 / 5, where T is the transcribed string and S is the seconds from first to last keystroke [PK]. Use phrase sets (MacKenzie & Soukoreff 2003 phrase set) presented one at a time. |
| Soukoreff & MacKenzie 2001, CHI EA '01:319-320, "Measuring errors in text entry tasks: Levenshtein" | 10.1145/634067.634256 [V-DOI] | MSD error rate = MSD(P, T) / max(abs(P), abs(T)) x 100%, where MSD is the Levenshtein distance between presented P and transcribed T [PK]. |
| MacKenzie 2002, Mobile HCI (LNCS 2411):195-210, "KSPC as a characteristic of text entry techniques" | 10.1007/3-540-45756-9_16 [V-DOI] | KSPC = total keystrokes (input events, including corrections) / characters in the transcribed text [PK]. For scanning, the analogous measure is scan steps per character (see E). |
| **Soukoreff & MacKenzie 2003**, CHI '03:113-120, "Metrics for text entry research: an evaluation of MSD and KSPC, and a new unified error metric" | 10.1145/642611.642632 [V-DOI] | Classify the input stream [PK]: **C** = correct, **INF** = incorrect not fixed, **IF** = incorrect but fixed, **F** = fixes (backspace, delete, etc.). **Total ER = (INF + IF) / (C + INF + IF)**. Corrected ER = IF / (C + INF + IF). Not-corrected ER = INF / (C + INF + IF). Related: correction efficiency = IF/F, utilized bandwidth = C/(C + INF + IF + F). Requires keystroke-level logs, not just final strings. Log every input event with a timestamp. |
| Dhakal et al. 2018, CHI '18, "Observations on typing from 136 million keystrokes" | 10.1145/3173574.3174220 [V-DOI] | Large-sample norms for able-bodied typing: IKI distributions, rollover, error-correction behaviour. Use as a reference distribution. Data licence is research/non-commercial only (see datasets.md) [V]. |

## C. BCI information rate

| Ref | DOI | Takeaway |
|---|---|---|
| Wolpaw et al. 1998, IEEE TRE 6:326-333 | 10.1109/86.712231 [V-DOI] | **Wolpaw ITR** [PK]: B = log2 N + P log2 P + (1 - P) log2((1 - P) / (N - 1)) bits per selection. Bits/min = B x (selections/min), where selection time must include all overhead (inter-trial intervals, error correction). Assumptions: (1) N targets equiprobable; (2) accuracy P equal for every target; (3) errors spread uniformly over the other N - 1 targets; (4) memoryless, stationary channel; (5) P > 1/N (otherwise B is set to 0); (6) fixed trial length. Most assumptions are violated by real cursor and speller systems. Report it only alongside a practical metric. |
| Wolpaw et al. 2002, Clin Neurophysiol 113:767-791 | 10.1016/S1388-2457(02)00057-3 [V-DOI] | Review; standard citation for the ITR definition. |
| Yuan et al. 2013, J Neural Eng 10:026014 | 10.1088/1741-2560/10/2/026014 [V-DOI] | Documents the misuse of ITR in online BCIs: excluding pauses, unequal priors, non-uniform errors, and small-sample accuracy estimates [PK]. Takeaway: compute ITR over the whole session time and report confidence intervals for P. |
| Thompson et al. 2014, J Neural Eng 11:035001 | 10.1088/1741-2560/11/3/035001 [V-DOI] | Tutorial on BCI performance measurement. Recommends reporting at the level the user experiences (e.g. correct characters per minute, task completion) plus Fitts TP for continuous cursors [PK]. |
| **Nuyujukian et al. 2015**, IEEE TBME 62:21-29 | 10.1109/TBME.2014.2354697 [V-DOI] | **Achieved bitrate** [PK]: ABR = log2(N - 1) x max(Sc - Si, 0) / t. N = number of selectable targets, Sc and Si = correct and incorrect selections, t = elapsed time. It assumes every error costs one extra correct selection (e.g. a backspace) to undo, giving a conservative practical rate. Use it as the primary information metric for grid tasks. |
| Pandarinath et al. 2017, eLife 6:e18554 | 10.7554/eLife.18554 [V-DOI] | Applies achieved bitrate and typing rates (correct characters per minute) in BrainGate participants (ALS and SCI); a benchmark for clinical comparison [PK]. |
| Gilja et al. 2012, Nat Neurosci 15:1752-1757 | 10.1038/nn.3265 [V-DOI] | ReFIT decoder. Reports Fitts-style TP and time-to-target with dial-in times for BCI cursors [PK]. |
| Neuralink **Webgrid** "bits per second" | https://neuralink.com/webgrid [V] | The page says the BPS score "is derived from net correct targets selected per minute (NTPM), grid size, and the number of click types", and that participants exceeded 10 BPS [CC]. The exact formula is not published on the page [V]. It is presumably the achieved-bitrate form with N = grid cells x click types [INF]. Default grid 35 x 35 [V]. |
| Paradromics SONIC benchmark (blog, 2025-10-03) | https://www.paradromics.com/blog/bci-benchmarking [CC] | Argues for reporting **achieved** information transfer together with **latency**, since look-back decoding can inflate rates. It claims more than 200 bps for Connexus [CC; preprint not checked]. Takeaway: always log end-to-end latency from intent cue to effect. |

## D. Reliability, agreement, measurement error

| Ref | DOI | Takeaway |
|---|---|---|
| Shrout & Fleiss 1979, Psychol Bull 86:420-428 | 10.1037/0033-2909.86.2.420 [V-DOI] | Six ICC forms [PK]: ICC(1,1), (2,1), (3,1) and their k-rater means. ICC(2,1) = (MSR - MSE) / (MSR + (k-1) MSE + k (MSC - MSE) / n). |
| McGraw & Wong 1996, Psychol Methods 1:30-46 | 10.1037/1082-989X.1.1.30 [V-DOI] | Ten ICC forms; consistency vs absolute-agreement terminology [PK]. |
| **Koo & Li 2016**, J Chiropr Med 15:155-163 | 10.1016/j.jcm.2016.02.012 [V-DOI] | Report model (one-way random, two-way random, two-way mixed), type (single vs mean) and definition (consistency vs absolute agreement), plus the 95% CI [PK]. Interpret using the CI: below 0.5 poor, 0.5-0.75 moderate, 0.75-0.9 good, above 0.9 excellent. For test-retest of NeuroMetric tasks, use **ICC(2,1) or ICC(A,1), absolute agreement, single measurement** (sessions treated as random). |
| **de Vet et al. 2006**, J Clin Epidemiol 59:1033-1039 | 10.1016/j.jclinepi.2005.10.015 [V-DOI] | Agreement (SEM, LoA) answers "how much does a person's score vary"; reliability (ICC) answers "can we tell people apart". Report both [PK]. SEM_agreement = sqrt(sigma2_occasion + sigma2_residual) from variance components (preferred over SD x sqrt(1 - ICC)). **SDC (= MDC95) = 1.96 x sqrt(2) x SEM**; group-level SDC = SDC / sqrt(n). |
| de Vet, Terwee, Mokkink & Knol 2011, *Measurement in Medicine* (CUP) | 10.1017/CBO9780511996214 [V-DOI] | Textbook covering all of the above. Read the chapters on reliability and responsiveness before writing the SAP. |
| Bland & Altman 1986, Lancet 327:307-310 | 10.1016/S0140-6736(86)90837-8 [V-DOI] | Limits of agreement = mean difference ± 1.96 x SD of differences. Plot differences against means [PK]. |
| Bland & Altman 1999, Stat Methods Med Res 8:135-160 | 10.1177/096228029900800204 [V-DOI] | Repeated measures per subject, proportional bias (regress difference on mean), log transform for ratio scales such as MT and WPM [PK]. Use it to compare NeuroMetric metrics across devices or sessions. |

## E. COSMIN, floor/ceiling, responsiveness, MCID

| Ref | DOI | Takeaway |
|---|---|---|
| Mokkink et al. 2010, J Clin Epidemiol 63:737-745 | 10.1016/j.jclinepi.2010.02.006 [V-DOI] | COSMIN taxonomy [PK]. Reliability domain: internal consistency, reliability, measurement error. Validity: content, structural, hypotheses testing, cross-cultural, criterion. Plus responsiveness and interpretability. Use these names in all NeuroMetric validation docs. |
| Mokkink et al. 2010, Qual Life Res 19:539-549 | 10.1007/s11136-010-9606-8 [V-DOI] | Original COSMIN checklist. |
| Mokkink et al. 2018, Qual Life Res 27:1171-1179 (RoB checklist) and Prinsen et al. 2018, Qual Life Res 27:1147-1157 (guideline) | 10.1007/s11136-017-1765-4 ; 10.1007/s11136-018-1798-3 [V-DOI] | Risk-of-bias standards for PROM studies. Design our studies to score "very good". |
| **Mokkink et al. 2020**, BMC Med Res Methodol 20 (COSMIN RoB tool for reliability/measurement error of *outcome measurement instruments*) | 10.1186/s12874-020-01179-5 [V-DOI] | Extends COSMIN to **performance-based and clinician-based** instruments [PK]. Define which components vary between repeated measurements (device setup, calibration, day, rater). This directly applies to NeuroMetric task batteries. |
| **Terwee et al. 2007**, J Clin Epidemiol 60:34-42 | 10.1016/j.jclinepi.2006.03.012 [V-DOI] | **Floor/ceiling effects are present when more than 15% of respondents hit the lowest or highest possible score** [PK]. Other criteria: ICC ≥ 0.70; SDC < MIC; Cronbach alpha 0.70-0.95 (with unidimensionality); 75% or more of hypotheses confirmed. For performance tasks with time caps, count capped or timed-out trials as "floor". |
| Guyatt, Walter & Norman 1987, J Chronic Dis 40:171-178 | 10.1016/0021-9681(87)90069-5 [V-DOI] | **Responsiveness index = MCID / SD of change in stable subjects** [PK]. Other indices: ES = mean change / SD baseline; SRM = mean change / SD change. COSMIN prefers hypothesis testing (correlations of change with anchors) over ES or SRM alone. |
| Jaeschke, Singer & Guyatt 1989, Control Clin Trials 10:407-415 | 10.1016/0197-2456(89)90005-6 [V-DOI] | Origin of MCID ("smallest difference ... patients perceive as beneficial"); anchor = global rating of change [PK]. |
| Revicki et al. 2008, J Clin Epidemiol 61:102-109 | 10.1016/j.jclinepi.2007.03.012 [V-DOI] | Anchor-based methods are primary and distribution-based (0.5 SD, 1 SEM) supportive. Anchors should correlate at least about 0.3 with the change score. Triangulate several anchors [PK]. |
| Devji et al. 2020, BMJ 369:m1714 | 10.1136/bmj.m1714 [V-DOI] | Credibility instrument for anchor-based MIDs: anchor understandable and relevant; anchor-change correlation reported and adequate (≥0.5 is high credibility); precise estimate; threshold close to "small but important" [PK]. Use it as the checklist for our MCID studies. |
| Terwee et al. 2021, Qual Life Res 30:2729-2754 | 10.1007/s11136-021-02925-y [V-DOI] | MIC is not the same as MID. The ROC-based MIC needs adjustment when the proportion improved differs from 50% (the predictive-modelling method with adjustment) [PK]. |

## F. Movement-kinematics models

| Ref | DOI | Takeaway |
|---|---|---|
| **Flash & Hogan 1985**, J Neurosci 5:1688-1703 | 10.1523/JNEUROSCI.05-07-01688.1985 [V-DOI] | **Minimum-jerk trajectory** [PK]: x(t) = x0 + (xf - x0)(10 tau^3 - 15 tau^4 + 6 tau^5), tau = t/T. Straight path with a bell-shaped speed profile; peak speed = 1.875 D/T at tau = 0.5. Use it as the ideal reference: report deviation of observed speed profiles (RMSE vs fitted min-jerk), normalized jerk, and number of speed peaks as smoothness metrics. BCI cursors are noisy, so low-pass filter consistently (state the cut-off). |
| **Meyer et al. 1988**, Psychol Rev 95:340-370 | 10.1037/0033-295X.95.3.340 [V-DOI] | **Stochastic optimized-submovement model** [PK]. A primary ballistic submovement plus optional corrective submovements; endpoint SD of each scales with its velocity. For 2 submovements MT = a + b sqrt(D/W); in general MT = a + b (D/W)^(1/n). Implementation: parse submovements (speed minima or zero-crossings of acceleration, with a minimum duration and amplitude), then report primary-submovement amplitude/accuracy and the number of corrective submovements. This is useful to separate a decoder's ballistic gain from its fine-control problems. |

## G. Switch scanning

| Ref | DOI | Takeaway |
|---|---|---|
| Damper 1984, Applied Ergonomics 15:289-296 | 10.1016/0003-6870(84)90201-1 [V-DOI] | Rate-prediction model for scanning input. Expected time per character = sum over characters c of p(c) x [scan steps to reach c x scan period] + switch overheads [PK]. Build the same model to predict ceiling WPM for any layout and scan rate. |
| Koester & Levine 1994, Assistive Technology 6:42-53 | 10.1080/10400435.1994.10132226 [V-DOI] | Learning and performance with row-column scanning, with and without word prediction. Keystroke-level timing components: scan wait, switch reaction, list-search time [PK]. Log scan-onset and switch timestamps separately. |
| Koester & Levine 1996, AAC 12:155-168 | 10.1080/07434619612331277608 [V-DOI] | Word-prediction cost/benefit. Saving keystrokes does not always save time, because of the cognitive cost of searching the list [PK]. |
| Simpson & Koester 1999, IEEE TRE 7:464-473 | 10.1109/86.808950 [V-DOI] | **Adaptive one-switch row-column scanning**: the scan delay adapts from performance (errors and reaction times) [PK]. Report the scan period trajectory and the reaction-time margin. |
| Lesher, Moulton & Higginbotham 1998, AAC 14:81-101 | 10.1080/07434619812331278236 [V-DOI] | Techniques for augmenting scanning communication: layouts and prediction, with scan-step metrics [PK]. |
| Bhattacharya, Samanta & Basu 2008, IEEE TNSRE 16:510-519 | 10.1109/TNSRE.2008.2003377 [V-DOI] | Performance models for automatic evaluation of virtual scanning keyboards; model-predicted vs observed rates [PK]. |
| MacKenzie & Felzer 2010, ACM TOCHI 17:1-39 ("SAK: scanning ambiguous keyboard") | 10.1145/1806923.1806925 [V-DOI] | **Scan steps per character (SPC)**, analogous to KSPC. Theoretical WPM from SPC and scan interval [PK]. Report SPC, missed-scan count and false activations. |
| Felzer et al. 2014, J Interaction Science 2 (OnScreenDualScribe) | 10.1186/s40166-014-0002-7 [V-DOI] | Case work with neuromuscular-disease users; useful for task design [PK]. |

Implementation takeaway for switch-scanning tasks [INF]:
- **Log**: scan-step onset times, switch press and release, the item highlighted at the press,
  intended target, and the scan period.
- **Derive**: switch reaction time (press minus highlight onset of the intended item), missed
  scans (intended item highlighted with no press), false activations, SPC, WPM, and Total ER
  (Soukoreff 2003).
- **Model**: compare observed time against the Damper / Bhattacharya-style prediction to get a
  "scanning efficiency" percentage.

## H. Eye-gaze dwell selection

| Ref | DOI | Takeaway |
|---|---|---|
| Ware & Mikaelian 1986/87, "An evaluation of an eye tracker as a device for computer input", SIGCHI Bulletin 17/18:183-188 (CHI+GI '87) | 10.1145/30851.275627 [V-DOI] (an alternate DOI 10.1145/1165387.275627 also resolves) | Dwell, screen-button and hardware-button selection compared; eye selection is fast but limited by target size [PK]. |
| Jacob 1991, ACM TOIS 9:152-169 | 10.1145/123078.128728 [V-DOI] | The "Midas touch" problem. Dwell thresholds involve a trade-off between speed and unintended activation [PK]. Log unintended activations as a primary error class. |
| Majaranta & Räihä 2002, ETRA '02:15-22, "Twenty years of eye typing" | 10.1145/507072.507076 [V-DOI] | Review of gaze-typing systems and metrics [PK]. |
| Majaranta, Ahola & Špakov 2009, CHI '09:357-360, "Fast gaze typing with an adjustable dwell time" | 10.1145/1518701.1518758 [V-DOI] | User-adjustable dwell. Over sessions, novices shortened dwell substantially and typing speed rose [PK; exact values not re-verified]. Takeaway: dwell time is a **user-tuned parameter** and must be logged per trial. Compare users at their own settings and also at a fixed reference dwell. |
| Mott et al. 2017, CHI '17:2558-2570 | 10.1145/3025453.3025517 [V-DOI] | Dynamic, cascading dwell times (per-key dwell adapts to the language-model probability). Shows dwell as a design variable [PK]. |
| Feit et al. 2017, CHI '17:1118-1130 | 10.1145/3025453.3025599 [V-DOI] | Eye-tracking accuracy and precision vary widely across users and screen regions. Derive target sizes from measured accuracy/precision [PK]. Run a calibration-quality check (accuracy and precision in degrees) at the start of every NeuroMetric gaze session. |
| Zhang & MacKenzie 2007, HCII (LNCS 4552):779-788 | 10.1007/978-3-540-73110-8_85 [V-DOI] | Applies ISO 9241-9 multidirectional tapping to eye tracking, with throughput for dwell vs key selection [PK]. Template for gaze Fitts tasks. Note that dwell time inflates MT, so report TP both with and without dwell. |

## I. BCI communication outcome references (for benchmarking)

| Ref | DOI | Note |
|---|---|---|
| Hochberg et al. 2006, Nature 442:164-171 | 10.1038/nature04970 [V-DOI] | First BrainGate cursor control. |
| Willett et al. 2021, Nature 593:249-254 (handwriting) | 10.1038/s41586-021-03506-2 [V-DOI] | 90 characters/min, SCI participant [PK]. Data on Dryad, CC0 (datasets.md). |
| Willett et al. 2023, Nature 620:1031-1036 (speech) | 10.1038/s41586-023-06377-x [V-DOI] | 62 words/min, 9.1% WER on a 50-word vocabulary, ALS participant (WER from the Dryad abstract [V]; rate [PK]). |
| Metzger et al. 2023, Nature 620:1037-1046 | 10.1038/s41586-023-06443-4 [V-DOI] | ECoG speech and avatar decoding. |
| Card et al. 2024, NEJM 391:609-618 | 10.1056/NEJMoa2314132 [V-DOI] | Rapidly calibrating speech neuroprosthesis, ALS participant. Data on Dryad, CC0. |
| Willett et al. 2016/17, J Neural Eng 14:016001 | 10.1088/1741-2560/14/1/016001 [V-DOI] | Feedback-control policies of iBCI users; models cursor control as a closed loop. Motivates trajectory metrics beyond endpoint. |

---

## Implementation checklist derived from the above [INF]
1. **Per trial, log**: target centre and size; start position; cursor samples (t, x, y) at the
   native rate; every selection event with its type (click/dwell/switch/BCI-click); dwell or scan
   parameters; calibration state; latency markers.
2. **Pointing**: TP (Soukoreff & MacKenzie, mean-of-means, univariate and bivariate We); MT; error
   rate; path metrics (MacKenzie 2001); submovement count (Meyer); min-jerk deviation (Flash &
   Hogan).
3. **Text**: WPM, Total ER / Corrected ER / Not-corrected ER, KSPC or SPC, MSD ER.
4. **Information rate**: achieved bitrate (primary), Wolpaw ITR (secondary, with assumptions
   stated), and end-to-end latency.
5. **Psychometrics**:
   - test-retest ICC(A,1) with 95% CI; SEM from variance components; SDC95;
   - Bland-Altman LoA on log scale across devices;
   - floor/ceiling against the 15% rule;
   - responsiveness by COSMIN hypothesis testing;
   - MIC via anchor-based predictive modelling, with Devji credibility criteria.
