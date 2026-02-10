from typing import Optional
from pydantic import BaseModel, Field


class DeviceInfo(BaseModel):
    device_id: str = Field(..., description="设备唯一标识")
    model: Optional[str] = Field(None, description="设备型号")
    firmware: Optional[str] = Field(None, description="固件版本")


class CaptureParams(BaseModel):
    capture_time: str = Field(..., description="采集时间（ISO8601）")
    frame_rate_hz: Optional[float] = Field(None, description="采样频率")
    resolution: Optional[str] = Field(None, description="分辨率，如 640x480")
    spectral_range: Optional[str] = Field(None, description="光谱范围")
    distance_m: Optional[float] = Field(None, description="采集距离")
    emissivity: Optional[float] = Field(None, description="发射率")


class EnvironmentParams(BaseModel):
    ambient_temp_c: Optional[float] = Field(None, description="环境温度")
    humidity_percent: Optional[float] = Field(None, description="湿度")
    airflow: Optional[str] = Field(None, description="气流情况")


class PatientInfo(BaseModel):
    patient_id: Optional[str] = Field(None, description="脱敏患者ID")
    body_part: Optional[str] = Field(None, description="采集部位")
    posture: Optional[str] = Field(None, description="姿态")


class IngestMetadata(BaseModel):
    device: DeviceInfo
    capture: CaptureParams
    environment: Optional[EnvironmentParams] = None
    patient: Optional[PatientInfo] = None
    tags: Optional[list[str]] = None


class AnalyzeRequest(BaseModel):
    record_id: str


class DispatchRequest(BaseModel):
    record_id: str
