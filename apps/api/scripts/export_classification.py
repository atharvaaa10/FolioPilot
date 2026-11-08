"""Export canonical classifications to docs/classification.json."""

import json
import sys
from pathlib import Path

# Ensure apps/api is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.classification_constants import CANONICAL_CLASSIFICATIONS, VALID_ASSET_CLASSES


def export_classification() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out_file = docs_dir / "classification.json"

    # Sort deterministically
    sorted_classifications = sorted(
        [
            {"asset_class": ac, "sub_category": sc}
            for ac, sc in CANONICAL_CLASSIFICATIONS
        ],
        key=lambda x: (x["asset_class"], x["sub_category"] or ""),
    )

    data = {
        "valid_asset_classes": sorted(list(VALID_ASSET_CLASSES)),
        "classifications": sorted_classifications,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print(f"Exported {len(sorted_classifications)} canonical classifications to {out_file}")


if __name__ == "__main__":
    export_classification()
