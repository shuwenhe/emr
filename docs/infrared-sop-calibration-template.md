# Infrared Imaging SOP, Calibration, and Template Definition

This document provides a practical baseline for fixed-installation and handheld infrared imaging workflows.

## 1) Common Goals

- Ensure repeatable acquisition conditions.
- Keep the subject posture consistent with the template.
- Align thermal data to anatomical regions using calibration and/or keypoints.
- Store raw data, metadata, and calibration parameters per record.

## 2) Fixed Installation SOP

### 2.1 Environment Setup

- Room temperature stable (e.g., 22-26 C), no direct airflow to subject.
- Neutral background, low reflectivity, no strong heat sources nearby.
- Fixed camera height and distance; mark floor position for subject.

### 2.2 Subject Preparation

- Expose the target body regions; remove metal accessories.
- Rest time before capture (e.g., 10-15 minutes) to stabilize skin temperature.
- Standard posture: feet shoulder-width, arms relaxed, consistent angle.

### 2.3 Capture Steps

- Confirm device warm-up status.
- Capture thermal image + visible image (if available) simultaneously.
- Save to record folder with metadata (subject ID, posture, view, capture time).

### 2.4 Quality Checks

- No motion blur or partial body missing.
- Temperature scale valid and not saturated.
- Background temperature separation from subject is sufficient.

## 3) Handheld SOP

### 3.1 Environment Setup

- Same as fixed installation where possible.
- Use tripod or stabilizer if available.

### 3.2 Subject Preparation

- Same as fixed installation.

### 3.3 Capture Steps

- Maintain a consistent distance (use a marker or laser range if available).
- Keep camera perpendicular to the body region.
- Capture multiple frames and keep the most stable one.

### 3.4 Quality Checks

- Reject frames with strong angle distortion.
- Avoid missing limbs or cropped regions.

## 4) Calibration and Alignment

### 4.1 Fixed Installation

- Perform a one-time calibration using a calibration board or fiducial markers.
- Compute a stable transform from visible to thermal (or thermal to visible).
- Store the transform matrix and reuse it for all records.

### 4.2 Handheld

- Use a per-session quick calibration (fiducial marker within view).
- If no markers, use keypoints from visible image for dynamic alignment.

### 4.3 Recommended Approach

- Dual-channel device: detect keypoints on visible image, map to thermal.
- Single-channel: use thermal silhouette and rule-based keypoint estimation.

## 5) Template Definition (15 Regions)

### 5.1 Standard Grid (3 x 5)

- Use a normalized grid or a keypoint-anchored grid.
- Default mapping:
  - Row 1: left shoulder, neck, right shoulder
  - Row 2: left upper back, spine, right upper back
  - Row 3: left waist, waist, right waist
  - Row 4: left hip, pelvis, right hip
  - Row 5: left knee, knee, right knee

### 5.2 Keypoint-Anchored Template (recommended)

- Identify shoulder, hip, and knee points.
- Define row boundaries using these points:
  - Row 1: above shoulders
  - Row 2: shoulders to upper back
  - Row 3: upper back to waist
  - Row 4: waist to hip
  - Row 5: hip to knee
- Define left/middle/right columns by the body midline.

### 5.3 Metadata Required

- posture (standing/sitting)
- view (front/back)
- distance and angle (if available)
- calibration matrix (if used)

## 6) Output Expectations

- Each record should contain:
  - thermal image
  - optional visible image
  - metadata.json with posture/view/calibration info
  - normalized region statistics (avg/min/max per region)

## 7) Handheld vs Fixed Summary

- Fixed: best accuracy, stable alignment, repeatable results.
- Handheld: flexible but needs frequent alignment checks.

---

If you want, I can add a checklist form or a calibration matrix template file.
