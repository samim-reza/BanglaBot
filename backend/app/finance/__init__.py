"""The financial engine: what every call costs, what every account pays, and the margin.

- ``pricebook`` — unit prices per provider SKU (defaults + admin overrides by date).
- ``meter`` — a finished call's provider usage → priced ledger lines.
- ``ledger`` / ``rollup`` — ``usage_events`` (append-only) and ``usage_daily`` (dashboards).
- ``recorder`` — failure-proof entry points (call end, payment fees); ``sms_meter`` — texts.
- ``revenue`` (+ ``subscriptions``) / ``reports`` / ``accounts`` / ``export`` — the admin console's numbers.
- ``guard`` — daily spend caps per provider (``over_cap(provider)``).
- ``scheduler`` — background jobs (SMS metering, cap refresh, retention).
"""
