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


class PatientUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    patient_id: Optional[str] = Field(None, description="患者ID")
    name: Optional[str] = Field(None, description="患者姓名")
    gender: Optional[str] = Field(None, description="性别")
    age: Optional[int] = Field(None, description="年龄")
    birth_date: Optional[str] = Field(None, description="出生日期")
    id_card: Optional[str] = Field(None, description="身份证号")
    phone: Optional[str] = Field(None, description="联系电话")
    address: Optional[str] = Field(None, description="联系地址")
    emergency_contact: Optional[str] = Field(None, description="紧急联系人")
    emergency_phone: Optional[str] = Field(None, description="紧急联系人电话")
    allergies: Optional[str] = Field(None, description="过敏史")
    medical_history: Optional[str] = Field(None, description="既往病史")
    department: Optional[str] = Field(None, description="就诊科室")
    chief_complaint: Optional[str] = Field(None, description="主诉")


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
    capture_path: Optional[str] = Field(
        None, description="设备落盘目录（可选，缺省扫描 device-drop）"
    )
    move_to_processed: bool = Field(
        True, description="入库后是否移动到 device-processed"
    )


class EmrGenerateRequest(BaseModel):
    record_id: str = Field(..., description="采集记录 ID")
    force: bool = Field(False, description="是否强制重新生成（默认false，已存在则直接返回）")


class HistoryImportRequest(BaseModel):
    root_path: str = Field(..., description="历史数据根目录（子目录包含 metadata.json 与数据文件）")
    analyze: bool = Field(True, description="是否自动生成报告与病历")


class EmrUpdateRequest(BaseModel):
    diagnosis: Optional[str] = Field(None, description="初步诊断")
    doctor_opinion: Optional[str] = Field(None, description="医生诊断意见")
    clinical: Optional[dict] = Field(None, description="病史信息")
    treatment_plan: Optional[dict] = Field(None, description="治疗方案")
    report: Optional[dict] = Field(None, description="诊断报告")


class EmrArchiveRequest(BaseModel):
    archived: bool = Field(True, description="是否归档")


class PatientArchiveRequest(BaseModel):
    archived: bool = Field(True, description="是否归档")


class PatientDeleteRequest(BaseModel):
    patient_ids: list[str] = Field(..., description="要删除的患者ID列表")


class ReportArchiveRequest(BaseModel):
    date: str = Field(..., description="报告日期目录，格式 YYYYMMDD")
    filename: str = Field(..., description="报告文件名")
    archived: bool = Field(True, description="是否归档（软删除）")
