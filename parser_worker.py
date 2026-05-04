import re
from pydantic import BaseModel, ValidationError
from typing import Optional

class CardMetadata(BaseModel):
    emp_id: Optional[str] = None
    name: Optional[str] = None
    policy_no: Optional[str] = None
    policy_type: Optional[str] = None
    card_no: Optional[str] = None
    relationship: Optional[str] = None
    age: Optional[int] = None
    valid_up_to: Optional[str] = None

def extract_metadata_from_text(text: str) -> CardMetadata:
    data = {}
    text = text.replace('\n:', ':')
    
    emp_match = re.search(r"(?i)Emp\.?\s*ID\.?\s*[:\-]?\s*([A-Za-z0-9]+)", text)
    if emp_match: data['emp_id'] = emp_match.group(1).upper()
    
    name_match = re.search(r"(?i)Name\s*[:\-]?\s*([A-Za-z\s\.]+)", text)
    if name_match: data['name'] = name_match.group(1).split('\n')[0].strip()
        
    policy_match = re.search(r"(?i)Policy\s*No\.?\s*[:\-]?\s*([A-Za-z0-9]+)", text)
    if policy_match: data['policy_no'] = policy_match.group(1).strip()
        
    type_match = re.search(r"(?i)Policy\s*Type\s*[:\-]?\s*([A-Za-z\s]+)", text)
    if type_match: data['policy_type'] = type_match.group(1).split('\n')[0].strip()
        
    card_match = re.search(r"(?i)Card\s*No\.?\s*[:\-]?\s*([A-Za-z0-9]+)", text)
    if card_match: data['card_no'] = card_match.group(1).strip()
        
    rel_match = re.search(r"(?i)Relationship\s*[:\-]?\s*([A-Za-z]+)", text)
    if rel_match: data['relationship'] = rel_match.group(1).strip()
        
    age_match = re.search(r"(?i)Age\s*[:\-]?\s*(\d+)", text)
    if age_match: data['age'] = int(age_match.group(1).strip())
        
    valid_match = re.search(r"(?i)Valid\s*Up\s*to\s*[:\-]?\s*([0-9\-]+)", text)
    if valid_match: data['valid_up_to'] = valid_match.group(1).strip()

    try:
        return CardMetadata(**data)
    except ValidationError:
        return CardMetadata()