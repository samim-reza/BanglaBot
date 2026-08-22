"""Service-type registry: one conversation flow per vertical."""

from __future__ import annotations

from app.flows.base import CORE_RULES_BN, Flow, Terminal, build_node_directive_bn
from app.flows.courier import CourierFlow
from app.flows.ecommerce import EcommerceFlow
from app.flows.runtime import FlowRuntime

_FLOWS: dict[str, Flow] = {flow.key: flow for flow in (EcommerceFlow(), CourierFlow())}

DEFAULT_SERVICE = "ecommerce"
SERVICE_KEYS = tuple(_FLOWS)


def get_flow(service_type: str) -> Flow:
    """The flow for a merchant's service; unknown values fall back to ecommerce."""
    return _FLOWS.get(service_type or DEFAULT_SERVICE, _FLOWS[DEFAULT_SERVICE])


def is_valid_service(service_type: str) -> bool:
    return service_type in _FLOWS


def validate_flow_settings(service_type: str, settings: dict) -> dict[str, bool]:
    """Coerce a merchant-supplied settings dict to this service's known toggles."""
    flow = get_flow(service_type)
    if not isinstance(settings, dict):
        return {}
    return {
        key: bool(settings[key]) for key in flow.settings_spec if key in settings
    }


def public_catalog() -> list[dict]:
    """Service list for the admin/signup selectors."""
    return [
        {
            "key": flow.key,
            "name_bn": flow.name_bn,
            "description_bn": flow.description_bn,
            "icon": flow.icon,
            "order_noun_bn": flow.order_noun_bn,
        }
        for flow in _FLOWS.values()
    ]


__all__ = [
    "CORE_RULES_BN",
    "DEFAULT_SERVICE",
    "SERVICE_KEYS",
    "Flow",
    "FlowRuntime",
    "Terminal",
    "build_node_directive_bn",
    "get_flow",
    "is_valid_service",
    "public_catalog",
    "validate_flow_settings",
]
