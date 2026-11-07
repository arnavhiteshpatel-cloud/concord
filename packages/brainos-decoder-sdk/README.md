# brainos-decoder-sdk (API 1.0)

Public SDK for bringing a neural decoder to BrainOS without changing BrainOS:

* **Decoder plugins**: a `Decoder` subclass with a `ModelManifest`, exposed in the
  `brainos.decoders` entry-point group of an installed package.
* **Model files** in safe formats (ONNX, scikit-learn via skops, TorchScript, a PyTorch
  `state_dict` in safetensors) with a `<model id>.manifest.json` next to them. Pickle /
  joblib files are refused unless the operator marks the exact file (SHA-256) trusted.

BrainOS runs both in an isolated decoder host process (`python -m brainos_decoder_sdk.host`),
validates every output against the manifest, and refuses to run a model on data that does
not match what it was trained on (modality, features, bin size, channel identities and
order, units, participant, sessions). Isolation is fault isolation, not a security sandbox.

```bash
pip install 'brainos-decoder-sdk[onnx,sklearn]'   # + [torch] for TorchScript / safetensors
brainos-decoder new my-decoder                     # scaffold a working plugin package
brainos-decoder check my-decoder                   # run it through the host + validators
brainos-decoder check --model data/models/m.manifest.json
brainos-decoder list
```

Guide: `docs/DECODER_SDK.md` in the BrainOS repository. Example plugin:
`examples/decoders/brainos-example-decoder`.
