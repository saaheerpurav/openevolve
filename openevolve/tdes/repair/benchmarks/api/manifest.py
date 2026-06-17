"""Variant manifest for the REST-API repair task.

Each variant is a bug-placement configuration over the three modules
(``auth``/``router``/``validator``); see the pipeline manifest for the
``split`` vs ``colocated`` stratum semantics. The API is framework-free
(request dict in, response out), so the standard TDES sandbox runner applies.
"""

MODULES = ["auth", "router", "validator"]

BUGS = {
    "U1": {
        "module": "auth",
        "description": (
            "throttle records denied requests in the sliding window, "
            "so sustained pressure never clears"
        ),
        "caught_by": "u_auth_throttle_recovery",
    },
    "U2": {
        "module": "auth",
        "description": (
            "scope denials filter the declared list before implication closure, "
            "so denied scopes re-enter via implied grants"
        ),
        "caught_by": "u_auth_scopes",
    },
    "R1": {
        "module": "router",
        "description": (
            "route precedence compares summed segment ranks instead of "
            "leftmost-segment-first, mis-resolving tied overlapping patterns"
        ),
        "caught_by": "u_router_precedence",
    },
    "R2": {
        "module": "router",
        "description": (
            "HEAD is normalized to GET before route lookup, so explicit HEAD "
            "routes are shadowed by their GET siblings"
        ),
        "caught_by": "u_router_methods",
    },
    "V1": {
        "module": "validator",
        "description": (
            "cross-field rules are evaluated against the raw payload instead of "
            "the coerced values"
        ),
        "caught_by": "u_validator_rules",
    },
    "V2": {
        "module": "validator",
        "description": (
            "field validation returns at the first coercion failure, dropping "
            "every later field and unknown-key error"
        ),
        "caught_by": "u_validator_aggregation",
    },
}

VARIANTS = {
    "v1_split": {
        "kind": "split",
        "bugs": ["U1", "R1"],
        "overrides": {"auth": "auth_u1.py", "router": "router_r1.py"},
    },
    "v2_split": {
        "kind": "split",
        "bugs": ["R2", "V1"],
        "overrides": {"router": "router_r2.py", "validator": "validator_v1.py"},
    },
    "v3_split": {
        "kind": "split",
        "bugs": ["U2", "V2"],
        "overrides": {"auth": "auth_u2.py", "validator": "validator_v2.py"},
    },
    "v4_split": {
        "kind": "split",
        "bugs": ["U1", "R2", "V2"],
        "overrides": {
            "auth": "auth_u1.py",
            "router": "router_r2.py",
            "validator": "validator_v2.py",
        },
    },
    "v5_coloc": {
        "kind": "colocated",
        "bugs": ["U1", "U2"],
        "overrides": {"auth": "auth_u1_u2.py"},
    },
    "v6_coloc": {
        "kind": "colocated",
        "bugs": ["V1", "V2"],
        "overrides": {"validator": "validator_v1_v2.py"},
    },
}
