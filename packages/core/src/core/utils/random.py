"""Random utility functions."""

import random


def random_int_with_length(length: int) -> int:
    """Generate a random integer with specified number of digits."""
    if length <= 0:
        raise ValueError("Length must be positive")

    min_val = 10 ** (length - 1)
    max_val = 10 ** length - 1

    return random.randint(min_val, max_val)


