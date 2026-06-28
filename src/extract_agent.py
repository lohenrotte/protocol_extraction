import json
from typing import Optional, Union
from pydantic import BaseModel, ValidationError

import llm_client

class Endpoint(BaseModel):
    id: str            
    objective_id: str  
    text: str


class Objective(BaseModel):
    id: str            
    category: str        
    text: str


class ObjectivesEndpoints(BaseModel):
    objectives: list[Objective]
    endpoints: list[Endpoint]


class Visit(BaseModel):
    day: str            
    window: str            


class SoARow(BaseModel):
    procedure: str
    category: Optional[str] = None   
    days_performed: list[str]       


class ScheduleOfActivities(BaseModel):
    visits: list[Visit]
    rows: list[SoARow]


class Criterion(BaseModel):
    id: str                      
    type: str                    
    category: str                 
    text: str                      
    structurable: bool              
    rule: Optional[str] = None      
 
 
class CriteriaList(BaseModel):
    criteria: list[Criterion]


OBJECTIVES_SYSTEM_PROMPT = """Convert this raw "Objectives and Endpoints" table
(a JSON grid of rows, each row a list of 2 cell strings) into clean structured JSON.

Rules:
- Row 0 is the header — use it only as information, do not extract data from it.
- A row where both cells are the same word in caps ("PRIMARY", "SECONDARY",
  "EXPLORATORY") is a category marker, not data. Everything after it belongs to
  that category until the next one.
- Objective numbers restart in each category, so build objective id as
  category prefix + number, e.g. "OBJ-PRI-1", "OBJ-SEC-5".
- If the left cell repeats the same objective across several rows, it's the
  SAME objective — only create it once. Each right-hand cell under it is a
  separate endpoint linked to that objective_id. If the right cell has a
  leading letter like "a)" or "b)", append it to the endpoint id,
  e.g. "EP-SEC-5a", "EP-SEC-5b". Otherwise just use "EP-" + objective number,
  e.g. "EP-PRI-1".
- Keep endpoint text close to the original wording. You can drop secondary
  details like "Population:", "Intercurrent events:", "Summary measure:" if
  short on space, but keep the core endpoint definition.
- Never invent objectives or endpoints not present in the grid.

Respond with ONLY this JSON shape, nothing else:
{
  "objectives": [{"id": "OBJ-PRI-1", "category": "primary", "text": "..."}],
  "endpoints": [{"id": "EP-PRI-1", "objective_id": "OBJ-PRI-1", "text": "..."}]
}
"""


SOA_SYSTEM_PROMPT = """Convert this raw Schedule of Activities table (a JSON grid
of rows, each row a list of cell strings, all rows same length) into clean
structured JSON.

Rules:
- Row 0 is the header — use it only as information, do not extract data from it.
- The first few rows are headers: one row has "Day" in column 0 and day numbers
  in the rest; another has "Window (days)" in column 0 and windows in the rest.
  Use these to build the `visits` list, one entry per day column, in that order.
- A row where the procedure cell's text repeats identically across every column
  is a section divider (e.g. "Efficacy assessments"), not a real row. Use it to
  set `category` for the rows that follow, until the next divider.
- For each real procedure row, list in `days_performed` only the day labels
  (from the header) where that row's cell is non-empty (has an "X" or any text).
  Leave out days where the cell is blank.
- Never invent rows or days not present in the grid.

Respond with ONLY this JSON shape, nothing else:
{
  "visits": [{"day": "1", "window": "NA"}, {"day": "8a", "window": "± 3"}],
  "rows": [{"procedure": "Medical history", "category": null, "days_performed": ["1"]}]
}
"""


CRITERIA_SYSTEM_PROMPT = """Convert this raw inclusion or exclusion criteria
section text into clean structured JSON.
 
The text has numbered criteria (1, 2, 3...) grouped under short bold category
headers (e.g. "Age", "Type of Participant", "Medical Conditions"). Some
criteria have nested sub-points (a, b, sub-bullets) — keep those nested
sub-points together as ONE criterion's text, do not split them into separate
criteria.
 
For each criterion, decide if it is "structurable": true only if it can become
ONE simple, unambiguous, machine-checkable field comparison (e.g. an age
cutoff, a yes/no flag, a lab value threshold). If it requires investigator
judgment, has multiple sub-exceptions, or is otherwise not reducible to one
clean comparison, set structurable to false and leave "rule" as null.
 
When structurable is true, write "rule" as a short pseudo-expression using
an UPPERCASE field name, e.g. "AGE >= 18", "PRIOR_COVID_INFECTION == false",
"FEVER_C > 37.8".
 
Number criteria as "INC-1", "INC-2"... for inclusion, or "EXC-1", "EXC-2"...
for exclusion, in the order they appear. Never invent criteria not present
in the text.
 
Respond with ONLY this JSON shape, nothing else:
{
  "criteria": [
    {"id": "INC-1", "type": "inclusion", "category": "Age", "text": "...", "structurable": true, "rule": "AGE >= 18"},
    {"id": "EXC-7", "type": "exclusion", "category": "Medical Conditions", "text": "...", "structurable": false, "rule": null}
  ]
}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    return text.strip()

    
def _extract(system_prompt: str, input: Union[list, str], input_type: str, schema_cls: type[BaseModel], max_retries: int = 1) -> dict:
    user_prompt = f"Raw input {input_type} :\n{json.dumps(input, ensure_ascii=False)}"
    for attempt in range(max_retries + 1):
        raw = llm_client.call_llm(prompt=user_prompt, system_prompt=system_prompt, temperature=0.0)
        cleaned = _strip_fences(raw)
        try:
            data = json.loads(cleaned)
            model = schema_cls.model_validate(data)
            return {"status": "ok", "data": model.model_dump()}
        except (json.JSONDecodeError, ValidationError) as e:
            user_prompt = (
                f"That response was invalid: {e}\nRespond again with ONLY the "
                f"corrected JSON.\n\nOriginal {input_type}:\n{json.dumps(input, ensure_ascii=False)}"
            )
    return {"status": "failed", "data": None, "raw_text": raw}


def extract_objectives_endpoints(grid: list) -> dict:
    return _extract(OBJECTIVES_SYSTEM_PROMPT, grid, "grid", ObjectivesEndpoints)

def extract_schedule_of_activities(grid: list) -> dict:
    return _extract(SOA_SYSTEM_PROMPT, grid, "grid", ScheduleOfActivities)

def extract_criteria(section_text: str) -> dict:
    return _extract(CRITERIA_SYSTEM_PROMPT, section_text, "text", CriteriaList)