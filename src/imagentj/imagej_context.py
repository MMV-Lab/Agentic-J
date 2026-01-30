import imagej
from typing import Optional

_ij_instance: Optional["imagej.ImageJ"] = None

def get_ij():
    global _ij_instance
    if _ij_instance is None:
        _ij_instance  = imagej.init("/home/marilin/Downloads/Fiji.app", mode='interactive')
    return _ij_instance
