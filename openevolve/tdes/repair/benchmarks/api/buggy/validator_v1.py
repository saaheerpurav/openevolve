"""Validator module: schema validation with coercion and cross-field rules.

``validate(payload, schema)`` walks the schema and returns
``(errors, coerced)``: a list of ``"<path>: <code>"`` strings plus the
cleanly-validated fields. Specs support ``kind`` (``"int"``, ``"number"``,
``"str"``, ``"bool"``, ``"list"``, ``"object"``), ``required``, numeric
``min``/``max``, ``minlen``/``maxlen``, ``choices``, and nested ``fields``
for objects. ``check_rules`` evaluates cross-field rules and
``validate_request`` runs both passes, returning the combined error list.
"""


def coerce(value, kind):
    """Interpret ``value`` as ``kind`` -> ``(ok, coerced_value)``."""
    if kind == "int":
        if isinstance(value, bool):
            return False, None
        if isinstance(value, int):
            return True, value
        if isinstance(value, str):
            digits = value[1:] if value.startswith("-") else value
            if digits.isdigit():
                return True, int(value)
        return False, None
    if kind == "number":
        if isinstance(value, bool):
            return False, None
        if isinstance(value, (int, float)):
            return True, value
        if isinstance(value, str):
            try:
                return True, float(value)
            except ValueError:
                return False, None
        return False, None
    if kind == "bool":
        if isinstance(value, bool):
            return True, value
        if value == "true":
            return True, True
        if value == "false":
            return True, False
        return False, None
    if kind == "str":
        if isinstance(value, str):
            return True, value
        return False, None
    if kind == "list":
        if isinstance(value, list):
            return True, value
        return False, None
    if kind == "object":
        if isinstance(value, dict):
            return True, value
        return False, None
    return True, value


def check_bounds(value, spec):
    """Range/length/choice error codes for an already-coerced value."""
    errors = []
    if spec.get("min") is not None and value < spec["min"]:
        errors.append("below min")
    if spec.get("max") is not None and value > spec["max"]:
        errors.append("above max")
    if spec.get("minlen") is not None and len(value) < spec["minlen"]:
        errors.append("too short")
    if spec.get("maxlen") is not None and len(value) > spec["maxlen"]:
        errors.append("too long")
    if spec.get("choices") is not None and value not in spec["choices"]:
        errors.append("not allowed")
    return errors


def validate(payload, schema, prefix=""):
    """Validate ``payload`` against ``schema`` -> ``(errors, coerced)``."""
    errors = []
    coerced = {}
    for field, spec in schema.items():
        path = prefix + field
        value = payload.get(field)
        if value is None:
            if spec.get("required"):
                errors.append(path + ": required")
            continue
        ok, value = coerce(value, spec.get("kind"))
        if not ok:
            errors.append(path + ": not a " + str(spec.get("kind")))
            continue
        if spec.get("kind") == "object":
            sub_errors, sub_coerced = validate(value, spec.get("fields", {}), path + ".")
            errors.extend(sub_errors)
            if not sub_errors:
                coerced[field] = sub_coerced
            continue
        codes = check_bounds(value, spec)
        errors.extend(path + ": " + code for code in codes)
        if not codes:
            coerced[field] = value
    for field in payload:
        if field not in schema:
            errors.append(prefix + field + ": unknown")
    return errors, coerced


def check_rules(values, rules):
    """Cross-field rule errors, in rule order."""
    errors = []
    for kind, a, b in rules:
        if kind == "requires":
            if a in values and b not in values:
                errors.append(a + ": requires " + b)
        elif kind == "excludes":
            if a in values and b in values:
                errors.append(a + ": excludes " + b)
        elif kind == "lte":
            if a in values and b in values and not values[a] <= values[b]:
                errors.append(a + ": must not exceed " + b)
    return errors


def validate_request(payload, schema, rules=()):
    """Field validation, then cross-field rules -> combined error list."""
    errors, coerced = validate(payload, schema)
    errors.extend(check_rules(payload, rules))
    return errors
