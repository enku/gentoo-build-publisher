"""Template tags for numerical values"""
from django import template

register = template.Library()


@register.filter(is_safe=False)
def numberize(val, precision=2):
    """Format number, `val` as a string.

    E.g. `1000` is returned as `"1k"` (precision 0), `123000000` as `"1.23M"` (precison
    2) etc.
    """
    try:
        val: str = str(int(val))
    except ValueError as error:
        raise template.TemplateSyntaxError(
            f"Value must be an integer. {val} is not an integer"
        ) from error

    num_digits = len(val)

    if num_digits >= 10:
        split, suffix = -9, "G"
    elif num_digits >= 7:
        split, suffix = -6, "M"
    elif num_digits > 4:
        split, suffix = -3, "k"
    else:
        return val

    dec, frac = val[:split], val[split:]

    if precision:
        rest = f".{frac[:precision]}"
    else:
        rest = ""

    return f"{dec}{rest}{suffix}"


@register.filter
def key(value, arg, default=None):
    """Given the dict valeu and key return the value from the dict"""
    return value.get(arg, default)


@register.filter
def addstr(arg1, arg2):
    """Perform string concatination"""
    return str(arg1) + str(arg2)
