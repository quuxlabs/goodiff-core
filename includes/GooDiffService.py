class GooDiffService:

    def __init__(self, name, documents=None):
        self.name = name
        self.documents = documents or []

    def debug(self):
        print "Service name:", self.name
        print "Service URLs:", self.documents
