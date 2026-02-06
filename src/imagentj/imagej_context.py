import imagej
from typing import Optional
from config.imagej_config import FIJI_JAVA_HOME

_ij_instance: Optional["imagej.ImageJ"] = None

def get_ij():
    global _ij_instance
    if _ij_instance is None:
        _ij_instance = imagej.init(FIJI_JAVA_HOME, mode='interactive')
    return _ij_instance
