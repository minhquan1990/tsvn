"""Định dạng số để giá Bitcoin không hiện dạng khoa học."""

from __future__ import annotations


def format_number(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1000:
        return f"{value:,.2f}"
    if absolute >= 1:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if absolute == 0:
        return "0"
    return f"{value:.6f}".rstrip("0").rstrip(".")
