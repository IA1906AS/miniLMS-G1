"""Entry point to run the miniLMS web application."""

import os
import sys
from pathlib import Path

# Add workspace root and src/ to sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from app import create_app  # noqa: E402

if __name__ == "__main__":
    os.environ.setdefault("JWT_SECRET", "super_secret_jwt_key_that_is_at_least_32_characters_long")
    port = int(os.environ.get("PORT", 5000))
    app = create_app()
    print(f"\n[INFO] miniLMS Web Portal running at: http://127.0.0.1:{port}")
    print("[INFO] Open the URL above in your browser to access the 4-role UI.\n")
    is_debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
    app.run(host="127.0.0.1", port=port, debug=is_debug)
