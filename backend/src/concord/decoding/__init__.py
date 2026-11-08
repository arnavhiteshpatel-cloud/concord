"""Offline-evaluated baseline decoders. Outputs are ``decoded_intent`` with a ``model_id``."""

from concord.decoding.ridge import RidgeDecoder, StreamingDecoder, evaluate, fit

__all__ = ["RidgeDecoder", "StreamingDecoder", "evaluate", "fit"]
