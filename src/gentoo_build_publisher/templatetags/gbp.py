"""Template tags for numerical values"""
from typing import Any

from django import template

register = template.Library()


@register.filter(is_safe=False)
def numberize(val: int, precision: int = 2) -> str:
    """Format number, `val` as a string.

    E.g. `1000` is returned as `"1k"` (precision 0), `123000000` as `"1.23M"` (precison
    2) etc.
    """
    if not isinstance(val, int):
        raise template.TemplateSyntaxError(
            f"Value must be an integer. {val!r} is not an integer"
        )

    str_val = str(val)
    num_digits = len(str_val)

    if num_digits >= 10:
        split, suffix = -9, "G"
    elif num_digits >= 7:
        split, suffix = -6, "M"
    elif num_digits > 4:
        split, suffix = -3, "k"
    else:
        return str_val

    dec, frac = str_val[:split], str_val[split:]
    rest = f".{frac[:precision]}" if precision else ""

    return f"{dec}{rest}{suffix}"


@register.filter
def key(value: dict[Any, Any], arg: Any, default: Any = None) -> Any:
    """Given the dict value and key return the value from the dict"""
    return value.get(arg, default)


@register.filter
def addstr(arg1: Any, arg2: Any) -> str:
    """Perform string concatination"""
    return str(arg1) + str(arg2)
