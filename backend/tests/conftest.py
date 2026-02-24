import pytest
from fastapi.testclient import TestClient
import pymysql
from unittest.mock import MagicMock

@pytest.fixture(scope="session")
def db_connection():
    """创建测试数据库连接"""
    # 这里可以使用测试数据库
    conn = MagicMock(spec=pymysql.connections.Connection)
    yield conn
    # 清理

@pytest.fixture
def client():
    """创建测试客户端"""
    from app.main import app
    with TestClient(app) as c:
        yield c

@pytest.fixture
def mock_patient_data():
    """模拟患者数据"""
    return {
        "name": "测试患者",
        "gender": "male",
        "age": 45,
        "phone": "13800138000",
        "id_card": "110101199001011234"
    }

@pytest.fixture
def mock_record_data():
    """模拟记录数据"""
    return {
        "patient_id": "P123456789",
        "device_id": "DEV001",
        "body_part": "全身",
        "capture_time": "2026-02-20T10:00:00"
    }
