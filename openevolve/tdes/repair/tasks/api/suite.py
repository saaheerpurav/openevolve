"""
REST API repair test suite — 3 unit + 2 integration + 1 system test.

Bugs seeded:
  auth.py     : validate_token uses exp > now (inverted); AuthError status_code 403 not 401
  router.py   : resolve() lowercases the method (keys are uppercase); missing GET /users/<id>
  validator.py: EMAIL_RE too permissive (no TLD); REQUIRED_FIELDS missing "email"

Bug independence: auth, router, and validator don't call each other, so every
module's bugs are orthogonal. A candidate fixing auth while leaving router broken
passes auth unit tests and fails router unit tests — complementary coverage for
crossover to exploit.
"""

from openevolve.tdes.test_suite import TDESTestSuite, TestEnv

suite = TDESTestSuite(modules=["auth", "router", "validator"])


# ── UNIT TESTS ────────────────────────────────────────────────────────────────

@suite.unit("auth", description="valid token accepted; expired token raises AuthError with status 401")
def test_auth_validate_token(env: TestEnv):
    # Valid token must be accepted.
    token = env.auth.create_token(user_id=1, role="admin", ttl=3600)
    env.case(f"valid token (ttl=3600)")
    try:
        payload = env.auth.validate_token(token)
    except Exception as e:
        env.check(False, f"valid token was rejected: {e}")
        return
    env.check_equal(payload.get("role"), "admin")

    # Expired token must raise AuthError with status_code 401.
    expired = env.auth.create_token(user_id=2, role="user", ttl=-100)
    env.case("expired token (ttl=-100)")
    raised = False
    status_code = None
    try:
        env.auth.validate_token(expired)
    except Exception as e:
        raised = True
        status_code = getattr(e, "status_code", None)
    env.check(raised, "expired token should raise an error")
    env.check_equal(status_code, 401, "AuthError status_code should be 401")


@suite.unit("router", description="resolve returns correct handler; GET /users/<id> route exists")
def test_router_resolve(env: TestEnv):
    env.case("GET /users")
    handler = env.router.resolve("GET", "/users")
    env.check_equal(handler, "list_users")

    env.case("GET /users/42")
    try:
        handler2 = env.router.resolve("GET", "/users/42")
        env.check_equal(handler2, "get_user")
    except Exception as e:
        env.check(False, f"GET /users/<id> should resolve to get_user: {e}")


@suite.unit(
    "validator",
    description="email regex rejects no-TLD addresses; 'email' is a required field",
)
def test_validator_rules(env: TestEnv):
    env.case("user@nodomain")
    env.check(
        not env.validator.validate_email("user@nodomain"),
        "no-TLD email should be invalid",
    )

    body_no_email = {"username": "alice", "password": "secret"}
    env.case(body_no_email)
    errors = env.validator.validate_request(body_no_email)
    env.check(len(errors) > 0, "request without email should have errors")
    env.check(
        any("email" in e for e in errors),
        f"errors should mention 'email'; got {errors}",
    )


# ── INTEGRATION TESTS ─────────────────────────────────────────────────────────

@suite.integration(
    "auth",
    modules=["auth", "router"],
    description="valid token accepted then request routes correctly",
)
def test_auth_then_route(env: TestEnv):
    token = env.auth.create_token(user_id=1, role="admin", ttl=3600)
    env.case("valid token -> GET /users")
    try:
        payload = env.auth.validate_token(token)
    except Exception as e:
        env.check(False, f"valid token was rejected: {e}")
        return
    env.check(payload is not None)
    handler = env.router.resolve("GET", "/users")
    env.check_equal(handler, "list_users")


@suite.integration(
    "router",
    modules=["router", "validator"],
    description="POST /users routes correctly and valid body passes validation",
)
def test_route_then_validate(env: TestEnv):
    env.case("POST /users")
    handler = env.router.resolve("POST", "/users")
    env.check_equal(handler, "create_user")

    body = {"username": "alice", "password": "secret123", "email": "alice@example.com"}
    env.case(body)
    errors = env.validator.validate_request(body)
    env.check_equal(errors, [], f"complete request body should have no errors; got {errors}")


# ── SYSTEM TEST ───────────────────────────────────────────────────────────────

@suite.system(
    "router",
    modules=["auth", "router", "validator"],
    description="full flow: authenticate -> route -> validate body",
)
def test_full_authenticated_request(env: TestEnv):
    token = env.auth.create_token(user_id=7, role="user", ttl=3600)
    env.case("authenticated GET /users/42 + body validation")

    payload = env.auth.validate_token(token)
    env.check(payload is not None, "token must be valid")

    handler = env.router.resolve("GET", "/users/42")
    env.check_equal(handler, "get_user")

    body = {"username": "bob", "password": "pass123", "email": "bob@example.com"}
    env.case(body)
    errors = env.validator.validate_request(body)
    env.check_equal(errors, [], f"complete body should pass; got {errors}")
