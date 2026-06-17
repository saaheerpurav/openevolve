"""Hierarchical TDES test suite for the REST-API repair task.

Three framework-free modules — ``auth`` (bearer tokens, scope grants,
throttling), ``router`` (pattern precedence and method dispatch), and
``validator`` (schema coercion and cross-field rules) — exercised by UNIT
tests per module (each catalogued bug in ``manifest.BUGS`` is caught by at
least one unit test of its own module), INTEGRATION tests over module pairs,
and SYSTEM tests that drive the full request lifecycle and assert
``(status, body)`` outcomes.

Loaded via ``TDESTestSuite.load_from_file`` (required for sandboxed runs).
"""

from openevolve.tdes import TDESTestSuite

suite = TDESTestSuite(modules=["auth", "router", "validator"])

ROUTES = [
    ("GET", "/status", "status_get"),
    ("HEAD", "/status", "status_head"),
    ("GET", "/users/me", "self_profile"),
    ("GET", "/users/{id:int}", "get_user"),
    ("PUT", "/users/{id:int}", "update_user"),
    ("GET", "/files/{name}/raw", "file_raw"),
    ("GET", "/files/static/{name}", "static_file"),
    ("GET", "/reports/{name}/summary", "named_report"),
    ("GET", "/reports/daily/summary", "daily_report"),
    ("POST", "/orders", "create_order"),
    ("GET", "/orders/{id:int}", "get_order"),
    ("GET", "/orders/{slug}", "order_by_slug"),
]

ORDER_SCHEMA = {
    "item": {"kind": "str", "required": True, "minlen": 1, "maxlen": 12},
    "qty": {"kind": "int", "required": True, "min": 1, "max": 100},
    "qty_max": {"kind": "int", "min": 1, "max": 1000},
    "priority": {"kind": "str", "choices": ["low", "normal", "high"]},
    "shipping": {
        "kind": "object",
        "fields": {
            "city": {"kind": "str", "required": True, "minlen": 2},
            "zip": {"kind": "str", "minlen": 5, "maxlen": 5},
        },
    },
}

ORDER_RULES = [
    ("lte", "qty", "qty_max"),
    ("requires", "priority", "shipping"),
]


# --- Unit: auth -------------------------------------------------------------
@suite.unit(
    "auth", description="parse_token accepts well-formed bearer headers, rejects malformed ones"
)
def u_auth_parse(env):
    env.check_equal(
        env.auth.parse_token(env.case("Bearer ana|read+write|50")),
        {"user": "ana", "scopes": ["read", "write"], "exp": 50},
    )
    env.check(env.auth.parse_token(env.case(None)) is None)
    env.check(env.auth.parse_token(env.case("Bearer ana|read")) is None)
    env.check(env.auth.parse_token(env.case("Bearer |read|5")) is None)
    env.check(env.auth.parse_token(env.case("Bearer ana||5")) is None)
    env.check(env.auth.parse_token(env.case("Bearer ana|read|soon")) is None)


@suite.unit(
    "auth", description="throttle allows a burst up to the limit, then denies with a retry hint"
)
def u_auth_throttle_limit(env):
    history = {}
    for now in (0, 1, 2):
        env.check_equal(env.auth.throttle(history, "ann", env.case(now)), (True, 0))
    env.check_equal(env.auth.throttle(history, "ann", env.case(3)), (False, 7))
    env.check_equal(env.auth.throttle(history, "bob", env.case(3)), (True, 0))


@suite.unit(
    "auth", description="throttle pressure subsides as the window slides over the request history"
)
def u_auth_throttle_recovery(env):
    history = {}
    battery = [(0, True), (1, True), (2, True), (3, False), (4, False), (5, False), (12, True)]
    for step, (now, expected) in enumerate(battery):
        env.case({"step": step, "now": now})
        allowed, _retry = env.auth.throttle(history, "kim", now)
        env.check_equal(allowed, expected)
    history = {}
    for step, (now, expected) in enumerate([(0, True), (1, True), (2, True), (10, True)]):
        env.case({"step": step, "now": now})
        allowed, _retry = env.auth.throttle(history, "lee", now)
        env.check_equal(allowed, expected)


@suite.unit("auth", description="scope grants honor implication chains and explicit denials")
def u_auth_scopes(env):
    env.check_equal(
        env.auth.grants(env.case(["admin"])),
        {"admin", "write", "audit", "read", "metrics"},
    )
    env.check_equal(env.auth.grants(env.case(["audit"])), {"audit", "read", "metrics"})
    env.check_equal(env.auth.grants(env.case(["write", "!read"])), {"write"})
    env.check_equal(
        env.auth.grants(env.case(["admin", "!write"])),
        {"admin", "audit", "read", "metrics"},
    )
    env.check_equal(env.auth.grants(env.case(["write", "!write"])), {"read"})


@suite.unit("auth", description="tokens move through active, grace, and expired stages")
def u_auth_grace(env):
    token = {"user": "g", "scopes": ["write"], "exp": 100}
    env.check_equal(env.auth.token_state(token, env.case(99)), "active")
    env.check_equal(env.auth.token_state(token, env.case(100)), "grace")
    env.check_equal(env.auth.token_state(token, env.case(129)), "grace")
    env.check_equal(env.auth.token_state(token, env.case(130)), "expired")
    env.check_equal(
        env.auth.authenticate(env.case("Bearer g|write|100"), 99, "write"), (True, None)
    )
    env.check_equal(
        env.auth.authenticate(env.case("Bearer g|write|100"), 110, "read"), (True, None)
    )
    env.check_equal(
        env.auth.authenticate(env.case("Bearer g|write|100"), 110, "write"),
        (False, "expired"),
    )


# --- Unit: router -----------------------------------------------------------
@suite.unit(
    "router", description="pattern compilation: typed params coerce, wildcards span one segment"
)
def u_router_compile(env):
    env.check_equal(env.router.split_path(env.case("/users/42/")), ["users", "42"])
    env.check_equal(env.router.split_path(env.case("/users?limit=5")), ["users"])
    compiled = env.router.compile_pattern("/users/{id:int}")
    env.check_equal(env.router.match_pattern(compiled, env.case(["users", "42"])), {"id": 42})
    env.check_equal(env.router.match_pattern(compiled, env.case(["users", "4x2"])), None)
    env.check_equal(env.router.match_pattern(compiled, env.case(["users"])), None)
    wild = env.router.compile_pattern("/a/*/c")
    env.check_equal(env.router.match_pattern(wild, env.case(["a", "b", "c"])), {})
    env.check_equal(env.router.match_pattern(wild, env.case(["a", "b", "d"])), None)


@suite.unit("router", description="overlapping route patterns resolve by segment specificity")
def u_router_precedence(env):
    env.check_equal(
        env.router.dispatch(ROUTES, "GET", env.case("/users/me")),
        (200, "self_profile", {}),
    )
    env.check_equal(
        env.router.dispatch(ROUTES, "GET", env.case("/orders/42")),
        (200, "get_order", {"id": 42}),
    )
    env.check_equal(
        env.router.dispatch(ROUTES, "GET", env.case("/reports/daily/summary")),
        (200, "daily_report", {}),
    )
    env.check_equal(
        env.router.dispatch(ROUTES, "GET", env.case("/files/static/raw")),
        (200, "static_file", {"name": "raw"}),
    )


@suite.unit("router", description="each method resolves to the route table entry meant for it")
def u_router_methods(env):
    env.check_equal(
        env.router.dispatch(ROUTES, "GET", env.case("/status")), (200, "status_get", {})
    )
    env.check_equal(
        env.router.dispatch(ROUTES, "PUT", env.case("/users/7")),
        (200, "update_user", {"id": 7}),
    )
    env.check_equal(
        env.router.dispatch(ROUTES, "HEAD", env.case("/status")), (200, "status_head", {})
    )


@suite.unit(
    "router", description="requests fall back sensibly when no route matches the method or path"
)
def u_router_fallbacks(env):
    env.check_equal(
        env.router.dispatch(ROUTES, "HEAD", env.case("/users/42")),
        (200, "get_user", {"id": 42}),
    )
    env.check_equal(
        env.router.dispatch(ROUTES, "DELETE", env.case("/users/42")),
        (405, None, {"allow": ["GET", "PUT"]}),
    )
    env.check_equal(
        env.router.dispatch(ROUTES, "HEAD", env.case("/orders")),
        (405, None, {"allow": ["POST"]}),
    )
    env.check_equal(env.router.dispatch(ROUTES, "GET", env.case("/nope")), (404, None, {}))
    env.check_equal(env.router.dispatch(ROUTES, "GET", env.case("/users/7/posts")), (404, None, {}))


# --- Unit: validator --------------------------------------------------------
@suite.unit("validator", description="values are coerced to their declared kinds before checks")
def u_validator_coerce(env):
    env.check_equal(env.validator.coerce(env.case("12"), "int"), (True, 12))
    env.check_equal(env.validator.coerce(env.case("-3"), "int"), (True, -3))
    env.check_equal(env.validator.coerce(env.case(True), "int"), (False, None))
    env.check_equal(env.validator.coerce(env.case("3.5"), "number"), (True, 3.5))
    env.check_equal(env.validator.coerce(env.case("true"), "bool"), (True, True))
    env.check_equal(env.validator.coerce(env.case(7), "str"), (False, None))
    errors, coerced = env.validator.validate(env.case({"item": "pen", "qty": "9"}), ORDER_SCHEMA)
    env.check_equal(errors, [])
    env.check_equal(coerced["qty"], 9)


@suite.unit("validator", description="validation reports every problem in a payload, not just one")
def u_validator_aggregation(env):
    errors, _ = env.validator.validate(env.case({"item": 7, "qty": 200, "extra": 1}), ORDER_SCHEMA)
    env.check_equal(errors, ["item: not a str", "qty: above max", "extra: unknown"])
    errors, _ = env.validator.validate(env.case({"qty": "x", "priority": "urgent"}), ORDER_SCHEMA)
    env.check_equal(errors, ["item: required", "qty: not a int", "priority: not allowed"])


@suite.unit("validator", description="cross-field rules: quantity ordering and field dependencies")
def u_validator_rules(env):
    env.check_equal(
        env.validator.validate_request(
            env.case({"item": "pen", "qty": 2, "qty_max": 10}), ORDER_SCHEMA, ORDER_RULES
        ),
        [],
    )
    env.check_equal(
        env.validator.validate_request(
            env.case({"item": "pen", "qty": 9, "qty_max": 3}), ORDER_SCHEMA, ORDER_RULES
        ),
        ["qty: must not exceed qty_max"],
    )
    env.check_equal(
        env.validator.validate_request(
            env.case({"item": "pen", "qty": "9", "qty_max": "10"}), ORDER_SCHEMA, ORDER_RULES
        ),
        [],
    )
    env.check_equal(
        env.validator.validate_request(
            env.case({"item": "pen", "qty": 1, "priority": "high"}), ORDER_SCHEMA, ORDER_RULES
        ),
        ["priority: requires shipping"],
    )


@suite.unit("validator", description="nested objects validate field-by-field with dotted paths")
def u_validator_nested(env):
    errors, _ = env.validator.validate(
        env.case({"item": "pen", "qty": 1, "shipping": {"city": "X", "zip": "123"}}),
        ORDER_SCHEMA,
    )
    env.check_equal(errors, ["shipping.city: too short", "shipping.zip: too short"])
    errors, _ = env.validator.validate(
        env.case({"item": "pen", "qty": 1, "shipping": {"zip": "12345"}}), ORDER_SCHEMA
    )
    env.check_equal(errors, ["shipping.city: required"])
    errors, _ = env.validator.validate(
        env.case({"item": "pen", "qty": 1, "shipping": {"city": "Oslo", "country": "NO"}}),
        ORDER_SCHEMA,
    )
    env.check_equal(errors, ["shipping.country: unknown"])


# --- Integration ------------------------------------------------------------
@suite.integration(
    "auth",
    modules=["router", "auth"],
    description="secured dispatch: resolve a protected route, then enforce token scopes",
)
def i_secured_dispatch(env):
    env.check_equal(
        env.router.dispatch(ROUTES, "GET", env.case("/orders/7")),
        (200, "get_order", {"id": 7}),
    )
    env.check_equal(
        env.auth.authenticate(env.case("Bearer kai|write+!read|800"), 100, "write"),
        (True, None),
    )
    env.check_equal(
        env.auth.authenticate(env.case("Bearer kai|read|90"), 100, "read"), (True, None)
    )
    env.check_equal(
        env.auth.authenticate(env.case("Bearer kai|write+!read|800"), 100, "read"),
        (False, "forbidden"),
    )


@suite.integration(
    "validator",
    modules=["router", "validator"],
    description="order intake: route the POST, then validate the body it carries",
)
def i_order_intake(env):
    env.check_equal(
        env.router.dispatch(ROUTES, "POST", env.case("/orders?dry=1")),
        (200, "create_order", {}),
    )
    env.check_equal(
        env.validator.validate_request(
            env.case({"item": "pen", "qty": 1, "priority": "urgent"}), ORDER_SCHEMA, ORDER_RULES
        ),
        ["priority: not allowed"],
    )
    env.check_equal(
        env.validator.validate_request(
            env.case({"item": 9, "qty": True}), ORDER_SCHEMA, ORDER_RULES
        ),
        ["item: not a str", "qty: not a int"],
    )


# --- System -----------------------------------------------------------------
_SCOPES = {
    "status_get": None,
    "status_head": None,
    "self_profile": "read",
    "get_user": "read",
    "update_user": "write",
    "file_raw": "read",
    "static_file": "read",
    "named_report": "metrics",
    "daily_report": "metrics",
    "create_order": "write",
    "get_order": "read",
    "order_by_slug": "read",
}


def _handle(env, req, history):
    """Full request lifecycle: dispatch -> authenticate -> validate -> respond."""
    status, handler, _extra = env.router.dispatch(ROUTES, req["method"], req["path"])
    if status != 200:
        return status, None
    required = _SCOPES.get(handler)
    if required is not None:
        ok, reason = env.auth.authenticate(req.get("auth"), req["now"], required, history)
        if not ok:
            if reason == "throttled":
                return 429, None
            return (401 if reason in ("no_token", "expired") else 403), None
    if handler == "create_order":
        errors = env.validator.validate_request(req.get("body") or {}, ORDER_SCHEMA, ORDER_RULES)
        if errors:
            return 422, tuple(errors)
    return 200, handler


@suite.system(
    "router",
    modules=["auth", "router", "validator"],
    description="request lifecycle battery: dispatch, authenticate, validate, respond",
)
def s_request_lifecycle(env):
    history = {}
    reader = "Bearer rhea|read|99999"
    writer = "Bearer wade|write|99999"
    auditor = "Bearer ana|audit|99999"
    noread = "Bearer mia|write+!read|99999"
    battery = [
        ({"method": "GET", "path": "/status", "now": 0}, (200, "status_get")),
        ({"method": "HEAD", "path": "/status", "now": 10}, (200, "status_head")),
        (
            {"method": "HEAD", "path": "/users/7", "auth": reader, "now": 20},
            (200, "get_user"),
        ),
        (
            {"method": "GET", "path": "/files/static/raw", "auth": reader, "now": 40},
            (200, "static_file"),
        ),
        (
            {"method": "GET", "path": "/files/notes/raw", "auth": reader, "now": 60},
            (200, "file_raw"),
        ),
        (
            {"method": "GET", "path": "/reports/daily/summary", "auth": auditor, "now": 80},
            (200, "daily_report"),
        ),
        (
            {"method": "GET", "path": "/reports/q3/summary", "auth": auditor, "now": 100},
            (200, "named_report"),
        ),
        ({"method": "GET", "path": "/orders/7", "auth": noread, "now": 120}, (403, None)),
        (
            {
                "method": "POST",
                "path": "/orders",
                "auth": noread,
                "now": 140,
                "body": {"item": "pen", "qty": 1},
            },
            (200, "create_order"),
        ),
        (
            {"method": "GET", "path": "/orders/special", "auth": reader, "now": 160},
            (200, "order_by_slug"),
        ),
        (
            {
                "method": "POST",
                "path": "/orders",
                "auth": writer,
                "now": 180,
                "body": {"item": "pen", "qty": "9", "qty_max": "10"},
            },
            (200, "create_order"),
        ),
        (
            {
                "method": "POST",
                "path": "/orders",
                "auth": writer,
                "now": 200,
                "body": {"qty": "x", "priority": "urgent"},
            },
            (422, ("item: required", "qty: not a int", "priority: not allowed")),
        ),
    ]
    for req, expected in battery:
        env.check_equal(_handle(env, env.case(req), history), expected)
    bob = "Bearer bob|read|99999"
    for now, expected_status in [
        (300, 200),
        (301, 200),
        (302, 200),
        (303, 429),
        (304, 429),
        (305, 429),
        (312, 200),
    ]:
        req = {"method": "GET", "path": "/users/me", "auth": bob, "now": now}
        status, _body = _handle(env, env.case(req), history)
        env.check_equal(status, expected_status)


@suite.system(
    "auth",
    modules=["auth", "router", "validator"],
    description="lifecycle edge cases: bad credentials, odd paths, and rejected orders",
)
def s_edge_cases(env):
    history = {}
    reader = "Bearer rosa|read|99999"
    writer = "Bearer wim|write|99999"
    denied_metrics = "Bearer noa|audit+!metrics|99999"
    battery = [
        ({"method": "GET", "path": "/users/7", "now": 0}, (401, None)),
        ({"method": "GET", "path": "/users/7", "auth": "Bearer ??", "now": 10}, (401, None)),
        ({"method": "GET", "path": "/users/7", "auth": "Bearer u||5", "now": 20}, (401, None)),
        (
            {"method": "GET", "path": "/users/7", "auth": "Bearer u|read|5", "now": 100},
            (401, None),
        ),
        (
            {"method": "GET", "path": "/users/me/?full=1", "auth": reader, "now": 120},
            (200, "self_profile"),
        ),
        ({"method": "GET", "path": "/users/abc", "auth": reader, "now": 140}, (404, None)),
        ({"method": "DELETE", "path": "/users/7", "auth": reader, "now": 160}, (405, None)),
        (
            {
                "method": "GET",
                "path": "/reports/daily/summary",
                "auth": denied_metrics,
                "now": 180,
            },
            (403, None),
        ),
        (
            {
                "method": "POST",
                "path": "/orders",
                "auth": writer,
                "now": 200,
                "body": {
                    "item": "mug",
                    "qty": 2,
                    "priority": "high",
                    "shipping": {"city": "Oslo", "zip": "00500"},
                },
            },
            (200, "create_order"),
        ),
        (
            {
                "method": "POST",
                "path": "/orders",
                "auth": writer,
                "now": 220,
                "body": {"item": "mug", "qty": 2, "priority": "high"},
            },
            (422, ("priority: requires shipping",)),
        ),
        (
            {
                "method": "POST",
                "path": "/orders",
                "auth": writer,
                "now": 240,
                "body": {"qty": "x", "extra": 5},
            },
            (422, ("item: required", "qty: not a int", "extra: unknown")),
        ),
        ({"method": "GET", "path": "/orders/5", "auth": writer, "now": 260}, (200, "get_order")),
    ]
    for req, expected in battery:
        env.check_equal(_handle(env, env.case(req), history), expected)
