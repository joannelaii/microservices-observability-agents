import os
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from graphs.root_graph import build_graph

if __name__ == "__main__":
    dir_name = "artifacts"
    prefix = "graph"
    os.makedirs(dir_name, exist_ok=True)
    graph = build_graph().get_graph(xray=True)
    
    mmd = graph.draw_mermaid()
    graph.draw_mermaid_png(output_file_path=f"{dir_name}/{prefix}.png")
    with open(f"{dir_name}/{prefix}.mmd", "w") as f:
        f.write(mmd)