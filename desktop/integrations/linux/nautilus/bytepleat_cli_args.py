"""Build the shared bytepleat-desktop argument vector without shell parsing."""


def selection_arguments(action, paths):
    if action not in ("create", "extract", "open"):
        raise ValueError("unsupported desktop action")
    return ["--" + action, "--", *paths]
