# ImageJ/Fiji Configuration
# Update this path to your local Fiji installation's Java home
# Docker overrides via FIJI_PATH env var; local dev uses the default below
import os
FIJI_JAVA_HOME = os.environ.get("FIJI_PATH", "/home/marilin/Downloads/Fiji.app")
