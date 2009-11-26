from xml.sax.handler import ContentHandler

from GooDiffProvider import GooDiffProvider
from GooDiffService import GooDiffService
from GooDiffDocument import GooDiffDocument

class ConfigReader(ContentHandler):

    def __init__(self, providers):

        self.providers = providers # stores the return values
        self.provider = ""
        self.service = ""
        self.document_url = ""
        self.document_name = ""

        self.inProviders = 0
        self.inProvider = 0
        self.inService = 0
        self.inDocument = 0
        self.inReplace = 0

    def startElement(self, name, attrs):
        if name == 'providers':
            self.inProviders = 1
        elif name == 'provider' and self.inProviders:
            self.inProvider = 1
            self.provider = GooDiffProvider(attrs.get('name', "").strip())
            self.providers.append(self.provider)
        elif name == 'service' and self.inProvider:
            self.inService = 1
            self.service = GooDiffService(attrs.get('name', "").strip())
            self.provider.services.append(self.service)
        elif name == 'document' and self.inService:
            self.inDocument = 1
            self.document = GooDiffDocument(attrs.get('url', "").strip())
            self.service.documents.append(self.document)
        elif name == 'replace' and self.inDocument:
            self.inReplace = 1
            pattern = attrs.get('pattern', "").strip()
            with = attrs.get('with', "").strip()
            self.document.replaces.append((pattern, with))

    def endElement(self, name):
        if name == 'providers':
            self.inProviders = 0
        elif name == 'provider' and self.inProviders:
            self.inProvider = 0
            # add provider to providers
        elif name == 'service' and self.inProvider:
            self.inService = 0
            # add service to provider
        elif name == 'document' and self.inService:
            self.inDocument = 0
            # add document to service
        elif name == 'replace' and self.inDocument:
            self.inReplace = 0
            # add replace to document

