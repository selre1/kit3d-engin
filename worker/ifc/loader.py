import ifcopenshell

class IfcLoader:
    def __init__(self, file_path):
        self.file_path = file_path
        
    def load(self):
        self.model = ifcopenshell.open(self.file_path)
        return self.model
    