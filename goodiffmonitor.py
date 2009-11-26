"""
This module provides the core functionality of the GooDiff monitor application.
"""
__version__ = "2.1"
__author__ = "Michael G. Noll (http://www.michael-noll.com/), Alexandre Dulaunoy (http://www.foo.be/)"
__copyright__ = "(C) 2006-2009 Michael G. Noll, Alexandre Dulaunoy"
__license__ = "AGPL 3.0"
__email__ = "dev@goodiff.org"

import ConfigParser
import datetime
import htmlentitydefs
import httplib
import os
import re
import socket
import sys
import time
import unittest
import urlparse
import urllib
from xml.sax import make_parser

# external dependencies
try:
    from BeautifulSoup import BeautifulSoup
except:
    print "Could not import BeautifulSoup. Get it from http://www.crummy.com/software/BeautifulSoup/."
    raise
try:
    import pysvn
except:
    print "Could not import pysvn. Get it from http://pysvn.tigris.org/."
    raise

from includes.ConfigReader import ConfigReader
from includes.GooDiffProvider import GooDiffProvider
from includes.GooDiffService import GooDiffService
import includes.html2text

class GooDiffMonitor(object):
    """The heart of GooDiff.org: an automated web document monitoring script with a Subversion interface.
    
    """


    def __init__(self,
                    configuration_global="config/goodiffmonitor.ini",
                    configuration_providers="config/providers.xml",
                    archive_source=None,
                    archive_text=None,
                    name=None,
                    http_proxy=None,
                    verbosity=None,
                    commit=None,
                    default_replace_with=None,
                    user_agent=None,
                    tries=None,
                    max_depth=None,
                    wait_seconds=None,
                ):
        """
        Parameters:

            archive_source:
                Absolute path to SVN repository for (raw) document sources

            archive_text:
                Absolute path to SVN repository for textified documents

            name (optional, default: 'GooDiffMonitor')
                Name of the script; used for verbose output

            http_proxy (optional, default: None)
                If set, the specified HTTP proxy is used.

            verbosity (optional, default: 1)
                Verbosity level for output of status information.
                Set to 0 to disable.

            commit (optional, default: True)
                Whether to commit or not commit changes to the repositories.

            default_replace_with (optional, default: 'REMOVED BY GOODIFF')
                Used to replace content specified by replace patterns in
                provider configuration file.

            user_agent (optional, default: 'Mozilla/5.0 (compatible; GooDiff/2.0; http://www.goodiff.org/wiki/GooDiffMonitor)')
                The user agent HTTP header to use when downloading
                documents from the WWW. Can be configured in the
                configuration file.

            tries (optional, default: 5):
                Try the specified number of times when downloading a
                monitored document fails. tries must be >= 1.
                See also wait_seconds.

            max_depth (optional, default: 3):
                Follow up to max_depth redirects for a url.
                max_depth must be >= 1.

            wait_seconds (optional, default: 2):
                Wait the specified number of seconds before re-trying to
                download a monitored document. wait_seconds must be >= 0.
                See also tries.

        """
        self.configuration_global = configuration_global
        self.configuration_providers = configuration_providers

        self.name = None
        self.archive_source = None
        self.archive_text = None
        self.http_proxy = None
        self.verbosity = None
        self.commit = None
        self.default_replace_with = None
        self.user_agent = None
        self.tries = None
        self.max_depth = None
        self.wait_seconds = None

        # load configuration files
        self._load()

        # overwrite configuration settings with parameters if they are set;
        # use default values for settings missing in configuration file AND
        # not specified via parameters
        if archive_source is not None:
            self.archive_source = archive_source
        if archive_text is not None:
            self.archive_text = archive_text
        if name is None:
            if self.name is None:
                self.name = 'GooDiffMonitor'
        else:
            self.name = name
        if http_proxy is not None:
            self.http_proxy = http_proxy
        if verbosity is None:
            if self.verbosity is None:
                self.verbosity = 1
        else:
            self.verbosity = verbosity
        if commit is None:
            if self.commit is None:
                self.commit = True
        else:
            self.commit = commit
        if default_replace_with is None:
            if self.default_replace_with is None:
                self.default_replace_with = "REMOVED_BY_GOODIFF"
        else:
            self.default_replace_with = default_replace_with
        if user_agent is None:
            if self.user_agent is None:
                self.user_agent = 'Mozilla/5.0 (compatible; GooDiff/2.0; http://www.goodiff.org/wiki/GooDiffMonitor)'
        else:
            self.user_agent = user_agent
        if tries is None:
            if self.tries is None:
                self.tries = 5
        else:
            self.tries = tries
        if max_depth is None:
            if self.max_depth is None:
                self.max_depth = 3
        else:
            self.max_depth = max_depth
        if wait_seconds is None:
            if self.wait_seconds is None:
                self.wait_seconds = 2
        else:
            self.wait_seconds = wait_seconds

        # sanity checks
        assert self.archive_source is not None
        assert self.archive_text is not None
        assert self.commit is not None
        assert self.default_replace_with is not None
        assert self.user_agent is not None
        assert self.tries >= 1
        assert self.max_depth >= 1
        assert self.wait_seconds >= 0

        self.svnclient = pysvn.Client()

    def download(self, url):
        """Download url from the Internet.

        Returns:
            a tuple of (http_code, source)

            If a networking error occurs, (-1, "") will be returned.

        """
        # see http://www.goodiff.org/wiki/FAQ why GooDiffMonitor
        # is not a robot, and thus does not care for robots.txt
        user_agent = self.user_agent
        method = "GET"
        request_headers = { 'User-agent' : user_agent }
        request_data = None

        conn = None
        if self.http_proxy:
            hostname, port = self.http_proxy.split(":")
            conn = httplib.HTTPConnection(hostname, port)
        else:
            hostname, port = self._get_hostname_and_port(url)
	    
        urlo = urlparse.urlsplit(url)

        if urlo[0] == "https":
            conn = httplib.HTTPSConnection(hostname, 443)
        else:
            conn = httplib.HTTPConnection(hostname, port)

        http_code = -1
        data = ""
        
        try:
            conn.request(method, url, request_data, request_headers)
            response = conn.getresponse()
            http_code = response.status
            if self.verbosity > 1:
                content_length = response.getheader('content-length', '')
                if content_length:
                    print "        Downloading", content_length, "bytes"
                else:
                    print "        Downloading ??? bytes"
            raw_data = response.read()
            data = unicode("", 'utf8')
            try:
                data = unicode(raw_data, 'utf8', errors='xmlcharrefreplace')
            except TypeError:
                # catches "TypeError: don't know how to handle UnicodeDecodeError in error callback"
                data = unicode(raw_data, 'utf8', errors='replace')
        except socket.error, msg:
            print "[%s] Socket error for url '%s': %s" % (self.name, url, msg)
            raise

        return (http_code, data)


    def _get_hostname_and_port(self, url):
        """Extract hostname and port from url and return it as a tuple.

        If the port is not explicitly specified in the url, a default
        value of 80 is returned for the port.

        """
        result = urlparse.urlparse(url)
        (scheme, netloc, path, parameters, query, fragment) = result
        splitted = netloc.rsplit(":", 1)
        hostname = splitted[0]
        port = 80
        if len(splitted) > 1 and splitted[1]:
            port = int(splitted[1])
        return (hostname, port)

    def _load(self):
        """Load the configuration files."""
        # location of the script itself; needed to make relative paths work
        if not sys.path[0] == "":
            SCRIPT_DIR = sys.path[0]
        else:
            # failback; this might not work 100% of the time though
            SCRIPT_DIR = os.getcwd()

        # read global configuration file
        config = ConfigParser.ConfigParser()
        config.read(SCRIPT_DIR + os.sep + self.configuration_global)

        try:
            self.name = config.get("General", "name")
        except ConfigParser.NoOptionError:
            pass
        try:
            self.http_proxy = config.get("General", "http_proxy")
        except ConfigParser.NoOptionError:
            pass
        try:
            self.verbosity = int(config.get("General", "verbosity"))
        except ConfigParser.NoOptionError:
            pass
        except ValueError:
            print 'verbosity must be an integer number'
        try:
            self.commit = bool(config.get("General", "commit"))
        except ConfigParser.NoOptionError:
            pass
        try:
            self.default_replace_with = config.get("General", "default_replace_with")
        except ConfigParser.NoOptionError:
            pass
        try:
            self.user_agent = config.get("General", "user_agent")
        except ConfigParser.NoOptionError:
            pass
        try:
            self.tries = int(config.get("General", "tries"))
        except ConfigParser.NoOptionError:
            pass
        except ValueError:
            print 'tries must be an integer number'
        try:
            self.max_depth = int(config.get("General", "max_depth"))
        except ConfigParser.NoOptionError:
            pass
        except ValueError:
            print 'max_depth must be an integer number'
        try:
            self.wait_seconds = int(config.get("General", "wait_seconds"))
        except ConfigParser.NoOptionError:
            pass
        except ValueError:
            print 'wait_seconds must be an integer number'

        # flat-file archives (under Subversion RCS)
        # no trailing slash!
        self.archive_source = config.get("Archives", "source")
        self.archive_text = config.get("Archives", "text")

        # load the provider configuration (list of documents to be monitored)
        providers = []
        parser = make_parser()
        configHandler = ConfigReader(providers)
        parser.setContentHandler(configHandler)
        parser.parse(open(SCRIPT_DIR + os.sep + self.configuration_providers))
        self.providers = providers
        

    def _url2filename(self, url):
        """Returns the safe conversion of url to a Unix filename."""
        # remove leading and trailing whitespace
        #
        url = url.strip()

        # add "index.html" suffix if we are monitoring a "directory" URL
        if url.endswith("/"):
            url += "index.html"

        p = re.compile('(?P<prot>^https?)://(?P<filepart>.+)')
        m = p.search(url)
        if m:
            protocol = m.group("prot")
            filepart = m.group("filepart")
    
            # replace un-safe characters in filepart with "_"
            #
            # it has been tested that storing and managing files with "?", "=", "&", "@", ":"
            # in their names is working flawlessly on the local filesystem and on Subversion/Trac
            # TODO: os.sep
            filepart = re.sub(r'[^a-zA-Z0-9.,-/\?=&@:_]', '_', filepart)
    
            # simple error checking
            #
            if not protocol or not filepart:
                print "[%s] ERROR: Invalid url '%s' - protocol and/or filepart is/are empty" % (self.name, url)
                raise GooDiffConfigurationError, "invalid url '%s' - protocol and/or filepart is/are empty" % url
            # TODO: os.sep
            p = re.compile('(?P<dirs>[a-zA-Z0-9.,-_/]*)/(?P<document>[a-zA-Z0-9.,-_?=&@:]+)')
            m = p.search(filepart)
            if m:
                dirs = m.group("dirs")
                document = m.group("document")
                if not document:
                    print "[%s] ERROR: Invalid url '%s' - filename is empty" % (self.name, url)
                    raise GooDiffConfigurationError, "invalid url '%s' - filename is empty" % url
                return filepart
            else:
                print "[%s] ERROR: Invalid url '%s'" % (self.name, url)
                raise GooDiffConfigurationError, "invalid url '%s'" % url
        else:
            print "[%s] ERROR: Invalid url '%s'" % (self.name, url)
            raise GooDiffConfigurationError, "invalid url '%s'" % url


    def _create_directory(self, path):
        """Create directory specified by path and add it to revision control."""
        if not os.access(path, os.F_OK):
            os.mkdir(path)
            if self.commit:
                self.svnclient.add(path)


    def _write_filename(self, base_dir, provider_name, filename, data):
        """Writes data to file.
        
        The full path of the file will be composed by concatenating
        base_dir, provider_name, and filename.
        
        Any existing data in the file will be overwritten.
        
        Parameters:
            base_dir
                the base directory of the file (absolute path recommended)
            
            provider_name
                name of the original provider of data (see providers.xml);
                a directory named 'provider_name' will be created below base_dir
            
            filename
                the local filename to which data will be written;
                generally, the filename is automatically generated by
                mapping a url to local filename by calling
                _url2filename()
            
            data
                the data to be written to file
        
        """
        # we use the name of a provider as the name of the subdirectory for all documents of a provider
        #
        path = base_dir + os.sep + provider_name
        self._create_directory(path)

        # create required directories if necessary
        #
        directories = filename.split(os.sep)

        # assumption: the part after the last os.sep is a file, not a directory
        for dir in directories[:-1]:
            path += os.sep + dir
            self._create_directory(path)

        fullpath = os.sep.join([base_dir, provider_name, filename])

        # make newlines in data consistent
        #data = re.sub(r'\r\n', '\n', data)

        f = open(fullpath, "w")
        f.write(data)
        f.close()
        if self.commit:
            changes = self.svnclient.status(fullpath)
            if fullpath in [f.path for f in changes if f.text_status == pysvn.wc_status_kind.unversioned]:
                self.svnclient.add(fullpath)


    def save_to_source_archive(self, provider_name, url, source, http_code):
        """Stores downloaded source of url with its http_code in mirror SVN repository."""
        filename = self._url2filename(url)
        encoded_source = source.encode('ascii', 'xmlcharrefreplace')
        self._write_filename(self.archive_source, provider_name, filename, encoded_source)

    def _strip_directory_path(self, directory, filename):
        """Remove the (leading) directory path from filename."""
        return filename[len(directory):]

    def commit_archive(self, directory, commit_message_footer):
        """Commit any changes in directory with commit_message_footer as footer of log message."""
        if self.verbosity:
            changes = self.svnclient.status(directory)
            added = [f.path for f in changes if f.text_status == pysvn.wc_status_kind.added]
            modified = [f.path for f in changes if f.text_status == pysvn.wc_status_kind.modified]
            deleted = [f.path for f in changes if f.text_status == pysvn.wc_status_kind.deleted]
            conflicted = [f.path for f in changes if f.text_status == pysvn.wc_status_kind.conflicted]
            unversioned = [f.path for f in changes if f.text_status == pysvn.wc_status_kind.unversioned]
            print "[%s] %s added, %s modified, %s deleted, %s conflicts, %s unversioned" % \
                (self.name, len(added), len(modified), len(deleted), len(conflicted), len(unversioned))
        # commit any changes
        _message = ""
        if added:
            _message += "Added files:\n"
            for file in added:
                _message += "  * %s\n" % self._strip_directory_path(directory, file)
            _message += "\n"
        if modified:
            _message += "Modified files:\n"
            for file in modified:
                _message += "  * %s\n" % self._strip_directory_path(directory, file)
            _message += "\n"
        if deleted:
            _message += "Deleted files:\n"
            for file in deleted:
                _message += "  * %s\n" % self._strip_directory_path(directory, file)
            _message += "\n"
        _message += commit_message_footer
        print _message
        self.svnclient.checkin([directory], _message)

    def get_from_mirror(self, url, revision):
        """Returns the revision of source of url from mirror SVN repository."""
        #TODO: needed only for rebuilding the archives from scratch due to changes to beautify/textify/etc.
        pass


    def replace(self, document, source):
        """Replace content in source of document by replacement patterns defined for document (see providers.xml)."""
        for pattern, repl in document.replaces:
            # empty string patterns are meaningless,
            # and are the result of an error on the
            # user's side in 100.0% of the cases
            if pattern:
                if not repl:
                    repl = self.default_replace_with
                if self.verbosity > 1:
                    print "        Replacing pattern '%s' with '%s'" % (pattern, repl)
                source = re.sub(r'%s' % pattern, repl, source)
        return source


    def beautify(self, source):
        """Returns a beautified/tidied version of HTML/XHTML source."""
        soup = BeautifulSoup(source)
        return soup.prettify()


    def textify(self, source):
        """Returns a text-only version (without markups etc.) from HTML/XHTML source."""
        source = source.decode('utf8')
        return includes.html2text.html2text(source)


    def save_to_text_archive(self, provider_name, url, text, http_code):
        """Stores text version of url with its http_code in GooDiff SVN repository."""
        filename = self._url2filename(url)
        encoded_text = text.encode('ascii', 'xmlcharrefreplace')
        # in contrast to save_to_mirror, we also "unescape" (="beautify")
        # Unicode characters and HTML entities in the HTML source;
        # e.g. "&copy;" -> "(c)"
        unicode_string = includes.html2text.unescape(encoded_text)
        encoded_text = unicode_string.encode('ascii', 'xmlcharrefreplace')
        self._write_filename(self.archive_text, provider_name, filename, encoded_text)


    def run(self):
        """Run the monitor for all configured urls."""
        
        print "[%s] Starting monitoring run at %s" % (self.name, datetime.datetime.now())
        if self.verbosity:
            documents = []
            for provider in self.providers:
                for service in provider.services:
                    for document in service.documents:
                        documents.append(document.url)
            print "[%s] This run will monitor %s documents" % (self.name, len(documents))

        
        # check whether the archive directories exists or not
        if not os.path.exists(self.archive_source) or not os.path.isdir(self.archive_source):
            print "ERROR: The source archive base directory", self.archive_source, "does not exist."
            print "       For safety reasons, it will not be created automatically."
            print "       Please create it manually via a SVN checkout of the source repository. Thanks!"
            raise GooDiffInstallationError, "source archive directory '%s' does not exist" % self.archive_source
        if not os.path.exists(self.archive_text) or not os.path.isdir(self.archive_text):
            print "ERROR: The text archive base directory", self.archive_text, "does not exist."
            print "       For safety reasons, it will not be created automatically."
            print "       Please create it manually via a SVN checkout of the text repository. Thanks!"
            raise GooDiffInstallationError, "text archive directory '%s' does not exist" % self.archive_text

        # now monitor all the configured providers
        for provider in self.providers:
            if self.verbosity:
                print "PROVIDER:", provider.name
            for service in provider.services:
                for document in service.documents:
                    if self.verbosity:
                        print "[", provider.name, ">", service.name, "] Processing ", document.url
                    self._process_document(provider.name, document)
        
        if self.commit:
            if self.verbosity:
                print "[%s] Committing source archive" % (self.name)
            self.commit_archive(self.archive_source, "%s run finished @ %s" % (self.name, datetime.datetime.now()))
            if self.verbosity:
                print "[%s] Committing text archive" % (self.name)
            self.commit_archive(self.archive_text, "%s run finished @ %s" % (self.name, datetime.datetime.now()))

        print "[%s] Finished monitoring run at %s" % (self.name, datetime.datetime.now())

    def _preprocess_source(self, source):
        """Preprocess source of document in a way which does not change the semantics of it.

        This method should be only used to ensure that processing the raw source
        will not result in critical exceptions which we cannot handle via normal
        means, e.g. because a malformatted source will break the Python interface
        to Subversion.

        """
        # pysvn doesn't like CTRL-M
        source = re.sub("\015","",source)
        return source

    def _process_document(self, provider_name, document):
        try:
            tries = self.tries
            max_depth = self.max_depth
            depth = 0
            while tries > 0:
                if self.verbosity:
                    print "    Downloading document (try %d of %d)" % (self.tries - tries + 1, self.tries)
                # try to download the document
                http_code, source = self.download(document.url)
                if http_code != 200:
                    if ((http_code >= 300 and http_code <= 303) or http_code == 307) and depth <= max_depth:
                        # handle redirects etc.
                        depth += 1
                        if self.verbosity:
                            print "    Redirect for document (going to depth %d, max depth is %d)" % (depth, max_depth)
                        #TODO: actually handle redirects ;-)
                        #      Note: watch out that 'tries' and 'max_depth' do not interfer
                        #            in an unwanted way (tries is decremented at the bottom
                        #            of the while loop)
                    else:
                        # an error occurred during download (404, 403, 500, ...);
                        # please try again
                        if self.verbosity:
                            print "    Failed download (error: %d)" % (http_code)
                        time.sleep(self.wait_seconds)
                else:
                    if source:
                        if self.verbosity:
                            print "    Preprocessing document"
                        source = self._preprocess_source(source)
                        if self.verbosity:
                            print "    Saving document to source archive"
                        self.save_to_source_archive(provider_name, document.url, source, http_code)
                        # note: the simple check on 'document.replaces' is not fully correct;
                        #       if the user entered an empty string pattern for a replace, the
                        #       replace definition is counted here but is ignored in the
                        #       subsequent call to replace()
                        if self.verbosity and document.replaces:
                            print "    Cleaning document as configured"
                        replaced = self.replace(document, source)
                        beautified = self.beautify(replaced)
                        text = self.textify(beautified)
                        if self.verbosity:
                            print "    Saving document to text archive"
                        self.save_to_text_archive(provider_name, document.url, text, http_code)
                        # we're done at this point
                        break
                tries -= 1
        except socket.error, msg:
            # skip the document
            print "[%s] Socket error for document '%s': %s" % (self.name, document.url, msg)


class GooDiffMonitorTester(unittest.TestCase):

    def testMonitorRun(self):
        """Test a full monitor run."""
        monitor = GooDiffMonitor()
        monitor.run()


class GooDiffError(Exception):
    pass

class GooDiffInstallationError(GooDiffError):
    """Indicates a problem with the installation or non-Python setup of GooDiffMonitor."""

class GooDiffConfigurationError(GooDiffError):
    """Indicates a problem with the configuration of GooDiffMonitor."""


if __name__ == "__main__":
    unittest.main()
