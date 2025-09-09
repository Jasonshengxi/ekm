from dataclasses import dataclass
from typing import Optional

@dataclass()
class BuildConfig:
    inherits: Optional[dict[str, str]] = None
    debug: Optional[int] = None

    warn: Optional[list[str]] = None
    sanitize: Optional[list[str]] = None
    cflags: Optional[list[str]] = None
    ldflags: Optional[list[str]] = None

    lto: Optional[str] = None
    cc: Optional[str] = None
    out: Optional[str] = None
    run: Optional[str] = None
    
    opt_level: Optional[str | int] = None
