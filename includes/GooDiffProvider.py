from GooDiffService import GooDiffService

class GooDiffProvider:

    def __init__(self, name, services=None):
        self.name = name
        self.services = services or []

    def debug(self):
        print "Provider name:", self.name
        for service in self.services:
            service.debug()

