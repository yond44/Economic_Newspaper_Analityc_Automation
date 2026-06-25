from pathlib import Path
from llama_index.core import SimpleDirectoryReader


current_dir = Path(__file__).parent
raw_dir = current_dir.parent.parent / "data" / "raw"

documents = SimpleDirectoryReader(
    str(raw_dir),
    file_metadata=lambda file_path: {
        "source": Path(file_path).name, 
        "type": "structured" if "structured" in str(file_path) else
                "deep" if "deep" in str(file_path) else
                "quant"
    }
).load_data()

for doc in documents:
    print(f"Source: {doc.metadata['source']}")
    print(f"Type: {doc.metadata['type']}")
    print(f"Length: {len(doc.text)} chars")
    print("---")