"""python -m simcore model.yaml [--reps N] [--json]"""

import argparse
import json
import math

from .loader import load


def main() -> None:
    ap = argparse.ArgumentParser(prog="simcore")
    ap.add_argument("model")
    ap.add_argument("--reps", type=int)
    ap.add_argument("--json", action="store_true", help="print raw per-replication results")
    a = ap.parse_args()
    m = load(a.model)
    res = m.run(a.reps)
    if a.json:
        print(json.dumps(res.replications, default=lambda x: None if isinstance(x, float) and math.isnan(x) else str(x), indent=1))
    else:
        print(res.report())


main()
