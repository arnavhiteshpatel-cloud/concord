"""scikit-learn via skops, pickle refusal / explicit trust, through a real decoder host."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from dec_helpers import ENV, RNG, WIDTH, load_error, manifest, run_host

from concord_decoder_sdk import OutputKind, ipc
from concord_decoder_sdk.client import SyncDecoderHost
from concord_decoder_sdk.formats import sha256_file, write_bundle

# ----------------------------------------------------------------------------- scikit-learn

sklearn = pytest.importorskip("sklearn", reason="scikit-learn (sklearn extra)")
sio = pytest.importorskip("skops.io", reason="skops (sklearn extra)")
from sklearn.linear_model import LogisticRegression, Ridge  # noqa: E402


def _xy(n: int = 300) -> tuple[np.ndarray, np.ndarray]:
    x = RNG.poisson(3.0, (n, WIDTH)).astype(np.float64)
    return x, x @ RNG.standard_normal((WIDTH, 2)) + RNG.standard_normal((n, 2)) * 0.1


def test_skops_regressor_matches_sklearn(tmp_path: Path) -> None:
    x, y = _xy()
    est = Ridge(alpha=1.0).fit(x, y)
    sio.dump(est, tmp_path / "ridge.skops")
    path = write_bundle(
        tmp_path / "m",
        manifest("sk-ridge", "sklearn"),
        tmp_path / "ridge.skops",
        "skops",
        {"method": "predict"},
    )
    np.testing.assert_allclose(run_host(path, x[:20]), est.predict(x[:20]), rtol=1e-12)


def test_skops_classifier_posteriors_in_declared_class_order(tmp_path: Path) -> None:
    x, _ = _xy()
    labels = (x[:, 0] > x[:, 1]).astype(int) + (x[:, 2] > 4).astype(int)  # 0, 1, 2
    est = LogisticRegression(max_iter=500).fit(x, labels)
    sio.dump(est, tmp_path / "lr.skops")
    m = manifest("sk-lr", "sklearn", kind=OutputKind.CLASSES, dims=("rest", "left", "right"))
    # output order differs from the estimator's classes_ order on purpose
    io = {"method": "predict_proba", "class_labels": [2, 0, 1]}
    path = write_bundle(tmp_path / "m", m, tmp_path / "lr.skops", "skops", io)
    got = run_host(path, x[:10])
    np.testing.assert_allclose(got, est.predict_proba(x[:10])[:, [2, 0, 1]], rtol=1e-12)


def test_click_event_from_a_binary_classifier_with_history(tmp_path: Path) -> None:
    x, _ = _xy()
    hist = np.hstack([np.vstack([np.zeros((1, WIDTH)), x[:-1]]), x])  # previous + current bin
    click = (x[:, 0] > 3).astype(int)
    est = LogisticRegression(max_iter=500).fit(hist, click)
    sio.dump(est, tmp_path / "click.skops")
    m = manifest("sk-click", "sklearn", kind=OutputKind.EVENT, dims=("click",))
    io = {"method": "predict_proba", "class_labels": [1], "history_bins": 2}
    path = write_bundle(tmp_path / "m", m, tmp_path / "click.skops", "skops", io)
    np.testing.assert_allclose(run_host(path, x[:15]), est.predict_proba(hist[:15])[:, [1]])


def test_estimator_feature_count_must_match_manifest(tmp_path: Path) -> None:
    x, y = _xy()
    est = Ridge().fit(np.hstack([x, x]), y)  # 8 features, manifest says 4
    sio.dump(est, tmp_path / "r.skops")
    path = write_bundle(tmp_path / "m", manifest("sk-w", "sklearn"), tmp_path / "r.skops", "skops")
    assert "fitted on 8 features" in load_error(path).message


def test_skops_untrusted_type_is_refused_until_trusted(tmp_path: Path) -> None:
    from concord_test_estimators import TimesTwo

    x, _ = _xy()
    sio.dump(TimesTwo().fit(x), tmp_path / "custom.skops")
    path = write_bundle(
        tmp_path / "m", manifest("sk-custom", "sklearn"), tmp_path / "custom.skops", "skops"
    )
    err = load_error(path)
    assert err.type == ipc.UNTRUSTED_MODEL and "concord_test_estimators.TimesTwo" in err.message
    sha = sha256_file(tmp_path / "m" / "sk-custom.skops")
    np.testing.assert_allclose(run_host(path, x[:5], trusted=sha), x[:5, :2] * 2.0)


def test_pickle_is_refused_without_an_explicit_trust_decision(tmp_path: Path) -> None:
    x, y = _xy()
    est = Ridge().fit(x, y)
    (tmp_path / "r.pkl").write_bytes(pickle.dumps(est))
    path = write_bundle(tmp_path / "m", manifest("pk", "sklearn"), tmp_path / "r.pkl", "pickle")
    err = load_error(path)
    assert err.type == ipc.UNTRUSTED_MODEL and "arbitrary code" in err.message
    # trust names a hash: a decision about another file does not apply
    assert load_error(path, trusted="0" * 64).type == ipc.UNTRUSTED_MODEL
    sha = sha256_file(tmp_path / "m" / "pk.pkl")
    np.testing.assert_allclose(run_host(path, x[:5], trusted=sha), est.predict(x[:5]))


def test_malicious_pickle_never_executes_without_trust(tmp_path: Path) -> None:
    marker = tmp_path / "pwned"

    class Evil:
        def __reduce__(self) -> tuple[Any, tuple[str]]:
            import os

            return (os.system, (f"touch {marker}",))

    (tmp_path / "evil.pkl").write_bytes(pickle.dumps(Evil()))
    path = write_bundle(
        tmp_path / "m", manifest("evil", "sklearn"), tmp_path / "evil.pkl", "pickle"
    )
    assert load_error(path).type == ipc.UNTRUSTED_MODEL
    assert not marker.exists()


def test_manifest_without_artifact_or_with_bad_json(tmp_path: Path) -> None:
    p = tmp_path / "x.manifest.json"
    p.write_text("{not json")
    with SyncDecoderHost(model_path=p, env=ENV) as c:
        m = c.manifest()
        assert not m["compatible"] and m["problems"][0]["code"] == "manifest.parse"
    from concord_decoder_sdk.manifest import manifest_to_dict

    p.write_text(json.dumps(manifest_to_dict(manifest("noart", "onnx"))))
    with SyncDecoderHost(model_path=p, env=ENV) as c:
        assert {q["code"] for q in c.manifest()["problems"]} == {"manifest.artifact"}
