import sys
from pathlib import Path

# permite "import cti_graphrag" nos testes sem instalar o pacote
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: precisa do banco ou do LLM real")
