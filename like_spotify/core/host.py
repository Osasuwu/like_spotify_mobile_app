from typing import Protocol


class ExtensionHost(Protocol):
    """The handle a host gives extensions. Stub for #21.

    Filled in as the host grows (logging, config access, lifecycle hooks).
    Naming it now anchors the seam in every extension's signature.
    """

    config_dir: str
