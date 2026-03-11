"""
集成测试示例
"""
import pytest


@pytest.mark.integration
class TestPatientFlow:
    """患者完整流程集成测试"""
    
    def test_complete_patient_workflow(self, client, mock_patient_data, mock_record_data):
        """测试完整的患者工作流程"""
        # 1. 创建患者
        # patient_response = client.post("/patients", json=mock_patient_data)
        # assert patient_response.status_code == 200
        # patient_id = patient_response.json()["patient_id"]
        
        # 2. 上传数据
        # ...
        
        # 3. 生成报告
        # ...
        
        # 4. 创建EMR
        # ...
        
        # 临时跳过（等待重构）
        pytest.skip("Waiting for refactoring")
