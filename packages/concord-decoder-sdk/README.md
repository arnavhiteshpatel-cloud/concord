# concord-decoder-sdk (API 1.0)

Public SDK for bringing a neural decoder to Concord without changing Concord:

* **Decoder plugins**: a `Decoder` subclass with a `ModelManifest`, exposed in the
  `concord.decoders` entry-point group of an installed package.
* **Model files** in safe formats (ONNX, scikit-learn via skops, TorchScript, a PyTorch
  `state_dict` in safetensors) with a `<model id>.manifest.json` next to them. Pickle /
  joblib files are refused unless the operator marks the exact file (SHA-256) trusted.

Concord runs both in an isolated decoder host process (`python -m concord_decoder_sdk.host`),
validates every output against the manifest, and refuses to run a model on data that does
not match what it was trained on (modality, features, bin size, channel identities and
order, units, participant, sessions). Isolation is fault isolation, not a security sandbox.

```bash
pip install 'concord-decoder-sdk[onnx,sklearn]'   # + [torch] for TorchScript / safetensors
concord-decoder new my-decoder                     # scaffold a working plugin package
concord-decoder check my-decoder                   # run it through the host + validators
concord-decoder check --model data/models/m.manifest.json
concord-decoder list
```

Guide: `docs/DECODER_SDK.md` in the Concord repository. Example plugin:
`examples/decoders/concord-example-decoder`.
