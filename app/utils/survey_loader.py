import json
import os
from pydantic import BaseModel
from typing import List, Optional, Dict, Union
from pathlib import Path


class SurveyOption(BaseModel):
    label: str
    action_type: str
    value: Optional[str] = None
    next_question_id: Optional[str] = None  # None=end, "__dynamic__"=use dispatcher


class SurveyQuestion(BaseModel):
    id: str
    type: str  # "quick_reply" | "location" | "image" | "multi_select"
    text: str
    options: List[SurveyOption] = []
    max_selections: Optional[int] = None  # only for multi_select


class Dispatcher(BaseModel):
    type: str  # always "dispatcher"
    look_up_answer_of: str
    map: Dict[str, Optional[str]]
    default: Optional[str] = None  # route to use when answer doesn't match any map key


class SurveyFlow(BaseModel):
    onstart: str
    after: Dict[str, Optional[Union[Dispatcher, str]]]
    forks: Dict[str, Dict[str, str]] = {}


class Survey(BaseModel):
    version: str
    questions: Dict[str, SurveyQuestion]
    routes: Dict[str, List[str]]
    flow: SurveyFlow


class SurveyManager:
    def __init__(self):
        self._surveys: Dict[str, Survey] = {}

    def load_from_file(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Survey file not found: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            survey_data = Survey(**raw_data)
            self._surveys[survey_data.version] = survey_data
            print(f"✅ Loaded survey version '{survey_data.version}' successfully!")

    def load_all_surveys_in_directory(self, directory_path: Path):
        if not directory_path.exists() or not directory_path.is_dir():
            print(f"⚠️ Directory not found: {directory_path}")
            return
        for file_path in directory_path.glob("*.json"):
            try:
                self.load_from_file(str(file_path))
            except Exception as e:
                print(f"⚠️ Skipping {file_path.name}: {e}")

    def get_survey(self, version: str) -> Optional[Survey]:
        return self._surveys.get(version)

    def get_question(self, version: str, question_id: str) -> Optional[SurveyQuestion]:
        survey = self.get_survey(version)
        if survey:
            return survey.questions.get(question_id)
        return None

    def get_route(self, version: str, route_id: str) -> Optional[List[str]]:
        survey = self.get_survey(version)
        if survey:
            return survey.routes.get(route_id)
        return None

    def get_flow(self, version: str) -> Optional[SurveyFlow]:
        survey = self.get_survey(version)
        if survey:
            return survey.flow
        return None


survey_manager = SurveyManager()
