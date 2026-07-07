import sys
import os
import threading
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.node import Node
from src.gui import run_gui


def main():
    parser = argparse.ArgumentParser(description="Detector Distribuido de Objetos Vermelhos")
    parser.add_argument("--node-only", action="store_true", help="Rodar apenas como no (sem GUI)")
    args = parser.parse_args()

    if args.node_only:
        from src.node import run_node
        run_node()
        return

    node = Node()
    if not node.start(with_coordinator=True):
        print("Falha ao conectar ao Redis. Iniciando GUI mesmo assim...")

    run_gui(node)

    node.stop()


if __name__ == "__main__":
    main()
