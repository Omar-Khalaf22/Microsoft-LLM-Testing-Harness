"""Decimal point arithmetic shared by legacy and selected-criterion scoring."""

from decimal import ROUND_HALF_UP, Decimal
from math import isfinite

CENT = Decimal("0.01")


def allocation(value: object, *, allow_zero: bool = False) -> Decimal:
    if type(value) not in (int, float) or (type(value) is float and not isfinite(value)):
        raise ValueError("Points must be finite JSON numbers.")
    point = Decimal(str(value))
    if point < 0 or (point == 0 and not allow_zero) or point > 100:
        raise ValueError("Selected maximum points must be positive and at most 100.")
    if point != point.quantize(CENT):
        raise ValueError("Maximum points allow up to two decimal places.")
    return point


def earned_points(normalized: float, maximum: float) -> float:
    if type(normalized) not in (int, float) or not isfinite(normalized) or not 0 <= normalized <= 1:
        raise ValueError("Evaluator completion must be a finite number between zero and one.")
    return float((Decimal(str(normalized)) * Decimal(str(maximum))).quantize(CENT, ROUND_HALF_UP))


def total_points(values: list[float]) -> float:
    return float(sum((Decimal(str(value)) for value in values), Decimal(0)).quantize(CENT))
