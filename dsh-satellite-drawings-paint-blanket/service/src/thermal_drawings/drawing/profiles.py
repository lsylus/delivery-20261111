from dataclasses import dataclass


@dataclass(frozen=True)
class DrawingProfile:
    target_dwg_version: str = "ACAD2018"
    dxf_version: str = "R2018"
    font: str = "DroidSansFallbackFull.ttf"
    tolerance_mm: float = 1e-6  # Analytic fixture oracle, not manufacturing tolerance.

    def __post_init__(self):
        if self.target_dwg_version != "ACAD2018" or self.dxf_version != "R2018":
            raise ValueError("B04 only implements the unverified ACAD2018 candidate profile")
        if self.tolerance_mm != 1e-6:
            raise ValueError("B04 analytic oracle tolerance is fixed")
