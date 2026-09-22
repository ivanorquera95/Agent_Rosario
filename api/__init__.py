# Los modulos del agente viven en scripts/, igual que para agent_rosario.py.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))