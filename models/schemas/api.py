from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


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
    name: Optional[str] = Field(None, description="患者姓名")
    gender: Optional[str] = Field(None, description="性别")
    age: Optional[int] = Field(None, description="年龄")
    body_part: Optional[str] = Field(None, description="采集部位")
    posture: Optional[str] = Field(None, description="姿态")


class ClinicalInfo(BaseModel):
    chief_complaint: Optional[str] = Field(None, description="主诉")
    past_history: Optional[list[str]] = Field(None, description="既往病史")
    family_history: Optional[list[str]] = Field(None, description="家族史")
    allergies: Optional[list[str]] = Field(None, description="过敏史")
    medications: Optional[list[str]] = Field(None, description="用药史")
    diagnosis: Optional[str] = Field(None, description="初步诊断")
    doctor_opinion: Optional[str] = Field(None, description="医生诊断意见")


class IngestMetadata(BaseModel):
    device: DeviceInfo
    capture: CaptureParams
    environment: Optional[EnvironmentParams] = None
    patient: Optional[PatientInfo] = None
    clinical: Optional[ClinicalInfo] = None
    tags: Optional[list[str]] = None


class AnalyzeRequest(BaseModel):
    record_id: str


class DispatchRequest(BaseModel):
    record_id: str


class DeviceIngestRequest(BaseModel):
    capture_path: Optional[str] = Field(None, description="设备落盘目录（可选，缺省扫描 device-drop）")
    move_to_processed: bool = Field(True, description="入库后是否移动到 device-processed")


class EmrGenerateRequest(BaseModel):
    record_id: str = Field(..., description="采集记录 ID")
    force: bool = Field(False, description="是否强制重新生成")


class HistoryImportRequest(BaseModel):
    root_path: str = Field(..., description="历史数据根目录")
    analyze: bool = Field(True, description="是否自动生成报告与病历")


class EmrUpdateRequest(BaseModel):
    diagnosis: Optional[str] = None
    doctor_opinion: Optional[str] = None
    clinical: Optional[dict] = None
    treatment_plan: Optional[dict] = None
    report: Optional[dict] = None


class EmrArchiveRequest(BaseModel):
    archived: bool = True


class PatientUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    patient_id: Optional[str] = None
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    birth_date: Optional[str] = None
    id_card: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    allergies: Optional[str] = None
    medical_history: Optional[str] = None
    department: Optional[str] = None
    chief_complaint: Optional[str] = None


class PatientArchiveRequest(BaseModel):
    archived: bool = True


class PatientDeleteRequest(BaseModel):
    patient_ids: list[str]


class ReportArchiveRequest(BaseModel):
    date: str
    filename: str
    archived: bool = True
