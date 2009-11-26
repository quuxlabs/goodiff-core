class GooDiffDocument:

    def __init__(self, url, replaces=None):
        self.url = url
        self.replaces = replaces or []

    def debug(self):
        print "Document url:", self.url
        print "Document replaces:", self.replaces

