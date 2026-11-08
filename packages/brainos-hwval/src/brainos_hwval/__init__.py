"""brainos-hwval: verify that BrainOS received exactly what an independent reference recorded.

The toolkit compares a BrainOS recording (``*.brainos.jsonl``) with a recording made at the
same time by established reference software:

* Lab Streaming Layer: an XDF file written by LabRecorder (read with pyxdf);
* Open Ephys: a Binary-format recording written by the Open Ephys GUI's Record Node.

It reports pass / fail / inconclusive / not-tested per check, with the evidence. It never
awards hardware or human validation by itself (docs/HARDWARE_VALIDATION.md).
"""

__version__ = "0.1.0"
