from typing import Any

def apply(logic: Any, data: Any = None) -> Any:
    """
    Apply JSON-Logic to data.
    Supports subset: ==, !=, >, >=, <, <=, and, or, var.
    """
    # Literal values
    if not isinstance(logic, dict):
        return logic

    # Logic relies on a single key operator
    operator = list(logic.keys())[0]
    values = logic[operator]

    # Ensure values is a list for unary/binary ops
    if not isinstance(values, list):
        values = [values]

    # Operations
    if operator == "var":
        return get_var(data, values[0] if values else None, values[1] if len(values) > 1 else None)
    
    # Recursive evaluation
    eval_values = [apply(v, data) for v in values]

    if operator == "==":
        return eval_values[0] == eval_values[1]
    if operator == "!=":
        return eval_values[0] != eval_values[1]
    if operator == ">":
        return eval_values[0] > eval_values[1]
    if operator == ">=":
        return eval_values[0] >= eval_values[1]
    if operator == "<":
        return eval_values[0] < eval_values[1]
    if operator == "<=":
        return eval_values[0] <= eval_values[1]
    
    if operator == "and":
        return all(eval_values)
    if operator == "or":
        return any(eval_values)

    return False

def get_var(data: Any, key: str, default: Any = None) -> Any:
    """Retrieve variable from data."""
    if key is None or key == "":
        return data
    
    try:
        parts = str(key).split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part, default)
            else:
                return default
        return current
    except Exception:
        return default
