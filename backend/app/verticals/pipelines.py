"""Glue between verticals and the skill pipeline: build a Vertical whose flows are compiled pipelines."""

from __future__ import annotations

from typing import Any, Mapping

from app.flows.base import Flow
from app.verticals.base import Vertical


def pipeline_vertical(
    spec: Mapping[str, Any],
    blueprints: Mapping[str, Any],
    *,
    legacy_flows: Mapping[str, Flow] | None = None,
    preset: Mapping[str, Any] | None = None,
    fixed_flows: Mapping[str, Flow] | None = None,
) -> Vertical:
    """A vertical on the pipeline (its ``flows`` are the default-config pipelines), or on its
    legacy flows when ``PIPELINE_VERTICALS`` leaves it out and legacy flows exist.

    ``fixed_flows`` are directions that never run on the pipeline (e-commerce's tuned outbound flow)."""
    from app.pipeline.compiled import PIPELINES
    from app.pipeline.settings import get_pipeline_settings

    key = str(spec["key"])
    fixed = dict(fixed_flows or {})
    if legacy_flows and not get_pipeline_settings().enabled(key):
        return Vertical(**spec, flows={**fixed, **legacy_flows})
    flows = {**fixed, **{direction: PIPELINES.get(bp, None, None, preset).flow for direction, bp in blueprints.items()}}
    return Vertical(**spec, flows=flows, blueprints=dict(blueprints), preset=dict(preset or {}))


def compiled_flow(vertical: Vertical, merchant: Any, direction: str) -> Flow | None:
    """This account's compiled flow for ``direction`` (cached by settings hash), or ``None``."""
    blueprint = vertical.blueprints.get(direction)
    if blueprint is None:
        return None
    from app.pipeline.compiled import PIPELINES

    return PIPELINES.get(
        blueprint,
        getattr(merchant, "agent_flow", None),
        getattr(merchant, "agent_flow_locks", None),
        vertical.preset or None,
    ).flow


__all__ = ["compiled_flow", "pipeline_vertical"]
