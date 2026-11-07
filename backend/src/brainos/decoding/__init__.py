"""Offline-evaluated baseline decoders. Outputs are ``decoded_intent`` with a ``model_id``."""

from brainos.decoding.ridge import RidgeDecoder, StreamingDecoder, evaluate, fit

__all__ = ["RidgeDecoder", "StreamingDecoder", "evaluate", "fit"]
