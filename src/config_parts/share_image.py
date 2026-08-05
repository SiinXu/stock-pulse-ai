"""Share-image domain configuration for the public ``src.config`` facade."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ShareImageConfig:
    """Web/API history share-image settings (independent of IM notification caps)."""

    # 100000 covers verbose detailed reports and multi-region market reviews (~20k-60k
    # typical) with headroom, without treating normal full reports as renderer failures.
    share_image_max_chars: int = 100000
    share_image_xiaohongshu_url: Optional[str] = None
    share_image_xiaohongshu_handle: Optional[str] = None
    share_image_xiaohongshu_id: Optional[str] = None
    share_image_xiaohongshu_qr_path: Optional[str] = None
