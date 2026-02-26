from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class IfcObject:
    guid: str
    ifc_class: str
    name: str | None
    
    properties: Dict[str, Any] = field(default_factory=dict)
    parents: List[Dict[str, str]] = field(default_factory=list)
    
    triangles: List = field(default_factory=list)
    material_parts: List = field(default_factory=list)
    material_index: int = 0
    shaders: Dict[str, Any] = field(default_factory=dict)