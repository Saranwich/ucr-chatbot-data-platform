import json
import os
from pydantic import BaseModel
from typing import List, Optional, Dict

# --- 1. กำหนดโครงสร้าง (Schema) ให้ตรงกับไฟล์ JSON ---
class SurveyOption(BaseModel):
    label: str
    action_type: str
    value: Optional[str] = None # บางปุ่มอาจจะไม่มี value เช่น เปิดกล้อง/แผนที่

class SurveyQuestion(BaseModel):
    id: str
    type: str
    text: str
    options: List[SurveyOption] = []

class Survey(BaseModel):
    version: str
    questions: List[SurveyQuestion]

# --- 2. สร้าง Class สำหรับโหลดและดึงข้อมูล ---
class SurveyManager:
    def __init__(self):
        # เก็บข้อมูลไว้ใน Dictionary (RAM) จะได้ไม่ต้องไปเปิดไฟล์อ่านใหม่ทุกครั้งที่มีคนแชทมา
        self._surveys: Dict[str, Survey] = {}

    def load_from_file(self, file_path: str):
        """อ่านไฟล์ JSON และเก็บเข้า Memory"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"หาไฟล์แบบสำรวจไม่เจอที่ path: {file_path}")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            # ใช้ Pydantic แปลง dict เป็น Object (ถ้า JSON ผิด มันจะเด้ง Error ตรงนี้เลย)
            survey_data = Survey(**raw_data) 
            self._surveys[survey_data.version] = survey_data
            print(f"✅ Loaded survey version '{survey_data.version}' successfully!")

    def get_survey(self, version: str) -> Optional[Survey]:
        """ดึงข้อมูลแบบสำรวจทั้งชุดตามเวอร์ชัน"""
        return self._surveys.get(version)

    def get_question_by_step(self, version: str, step_index: int) -> Optional[SurveyQuestion]:
        """ดึงคำถามออกมาทีละข้อ (step_index เริ่มที่ 0)"""
        survey = self.get_survey(version)
        if survey and step_index < len(survey.questions):
            return survey.questions[step_index]
        return None

# สร้างตัวแปร Global ไว้ให้ไฟล์อื่น Import ไปใช้ได้เลย
survey_manager = SurveyManager()