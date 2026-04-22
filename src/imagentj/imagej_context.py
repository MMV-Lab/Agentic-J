import imagej
from typing import Optional
from config.imagej_config import FIJI_JAVA_HOME
import scyjava

_ij_instance: Optional["imagej.ImageJ"] = None

scyjava.config.add_options('-Xmx6g')
# Local Fiji installation is complete — no network calls needed at JVM startup.
# Without this, scyjava tries to download Maven from archive.apache.org if mvn
# is not on PATH, which fails in restricted/flaky network environments.
scyjava.config.set_java_constraints(fetch='never')

def get_ij():
    global _ij_instance
    if _ij_instance is None:
        _ij_instance = imagej.init(FIJI_JAVA_HOME, mode='interactive')
    return _ij_instance
