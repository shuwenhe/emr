from typing import List
from .models import IngestMetadata


def run_qc(metadata: IngestMetadata) -> List[str]:
    issues: List[str] = []

    if metadata.capture.emissivity is not None:
        if not (0.0 < metadata.capture.emissivity <= 1.0):
            issues.append("emissivity_out_of_range")

    if metadata.capture.frame_rate_hz is not None:
        if metadata.capture.frame_rate_hz <= 0:
            issues.append("frame_rate_invalid")

    if metadata.environment and metadata.environment.humidity_percent is not None:
        if not (0.0 <= metadata.environment.humidity_percent <= 100.0):
            issues.append("humidity_out_of_range")

    return issues
