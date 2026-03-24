"""Mutable product state model used by the GUI and worker snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
import copy


@dataclass
class ProductIdentity:
    name: str = ""
    type_name: str = ""
    model: str = ""
    color1: str = ""
    color2: str = ""
    color3: str = ""
    extra: str = ""
    ean: str = ""
    product_id: str = ""

    @property
    def colors(self) -> list[str]:
        return [self.color1, self.color2, self.color3]


@dataclass
class ProductState:
    identity: ProductIdentity = field(default_factory=ProductIdentity)
    original_files: dict[str, str] = field(default_factory=dict)
    pending_additions: dict[int, str] = field(default_factory=dict)
    pending_deletions: dict[int, str] = field(default_factory=dict)
    pending_ftp_deletions: dict[int, str] = field(default_factory=dict)
    ftp_remote_only: dict[str, dict[str, str]] = field(default_factory=dict)
    ftp_presence: dict[str, str] = field(default_factory=dict)
    ftp_downloaded_final: set[str] = field(default_factory=set)
    sql_presence: dict[str, bool] | None = None

    def clone(self) -> "ProductState":
        return copy.deepcopy(self)

    def reset_runtime(self) -> None:
        self.original_files.clear()
        self.pending_additions.clear()
        self.pending_deletions.clear()
        self.pending_ftp_deletions.clear()
        self.ftp_remote_only.clear()
        self.ftp_presence.clear()
        self.ftp_downloaded_final.clear()
        self.sql_presence = None
