"""Dev entry point: `python -m gatoway.main`.

Equivalent to `uvicorn gatoway.app:app --reload`; kept as a tiny script so
`python -m gatoway.main` works without remembering the uvicorn invocation.
"""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("gatoway.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
