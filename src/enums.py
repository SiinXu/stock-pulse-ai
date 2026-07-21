# -*- coding: utf-8 -*-
"""
===================================
Enum type definition
===================================

Enumeration type used in the centralized management system, providing type safety and code readability.
"""

from enum import Enum


class ReportType(str, Enum):
    """
    Report type enumeration

    Select the report format to push when triggering API analysis.
    Inherit str to allow direct comparison and serialization with strings.
    """
    SIMPLE = "simple"  # Simplified report: using generate_single_stock_report
    FULL = "full"      # Full report: using generate_dashboard_report
    BRIEF = "brief"    # Concise mode: 3-5 sentences summary, suitable for mobile/push

    @classmethod
    def from_str(cls, value: str) -> "ReportType":
        """
        Safely convert to enum values from string.
        
        Args:
            value: String value
            
        Returns:
            Corresponding enum value, invalid input returns default value SIMPLE
        """
        try:
            normalized = value.lower().strip()
            if normalized == "detailed":
                normalized = cls.FULL.value
            return cls(normalized)
        except (ValueError, AttributeError):
            return cls.SIMPLE
    
    @property
    def display_name(self) -> str:
        """Get the display name"""
        return {
            ReportType.SIMPLE: "精简报告",
            ReportType.FULL: "完整报告",
            ReportType.BRIEF: "简洁报告",
        }.get(self, "精简报告")
