"""OpenID Diagnostic"""

# Please enter an OpenID URL: [______________]
# "I fetched ..."
# "I was redirected to ..."
# "I received a document..."
# X I got an ERROR RESPONSE.
# "I found a link tag (and a delegate tag?)..."
# X I found NO link tag.
# "I tried to associate with your OpenID server... (URL, IP)"
# X Your OpenID server isn't there / likes to explode / etc.
# X There is an OpenID server there but its Associate reply is broken:
#     assoc_handle must only contain bytes in xx-yy.

# Okay, so far for the identity URL _______ and the server _____,
# we have done:
#  associate:
#    with plaintext secret: OK
#    with DH-SHA1 secret: /!\ The server returned the secret in plaintext!
#       This is permitted by the OpenID specification, but means your server
#       is less secure than it might be.
#  checkid_immediate:
#    positive assertion: not seen [Make this request again?]
#    user_setup_url: OK (2 times)
#    no response: 0 times
#  checkid_setup:
#    positive assertion: OK
#    cancel: not seen [Make this request again?]
#    no response: 2 times I redirected you to make a request and you
#       didn't return.

# and in dumb mode:
#  checkid_immediate:
#    positive assertion: [Try now?]
#    user_setup_url: [Try now?]
#  checkid_setup:
#    positive assertion: /!\ 1 UNVERIFIED response.
#       (You were redirected back from the server, but
#        check_authentication did not complete!)
#    cancel: not seen [Make this request again?]
#    no response: 3 times I redirected you to make a request and you
#       didn't return.
#  check_authentication:
#     valid signature: 0 [Try Again]
#   invalid signature: 0 [Try Again]
# incomplete response: 1

# Miscellaneous error responses:
#   GET with return_to: got code 400, should have been a redirect
#   GET with bad arguments: OK, got HTML saying %blah%
#   GET with no arguments: got code 400, should have been 200.
#   POST: OK, got kvform in response with error "blah"

# Associations:
#  smart mode:
#   aoeuaosihxgah
#   asdfhjklxzilnb
#
#  dumb mode:
#   dzzzzzl9

# You most recently arrived at this page through
#   a normal request
#      with no referrer information.
#      referred by _________.
#   an OpenID response
#      a well-formed OpenID checkid_setup smart mode response
#        authenticating the identity ___________
#        (here is the parameter breakdown: and referrer:)
#      You wanted to test the checkid_setup Cancel response when you
#         made that request.  Try again?
#   an OpenID response, but it's kinda screwy!
#      This response to checkid_setup is missing the return_to parameter.
#      This response to checkid_setup has an incorrect value for [...]
#   an OpenID response with an invalid signature!

# Check a new OpenID: [___________________]
# or server: [___________________]
# or [Reset] this page.

from mod_python import apache
from mod_python.util import FieldStorage
from xml.sax.saxutils import escape, quoteattr

from openid.consumer import consumer
from openid.store.sqlstore import SQLiteStore
import pysqlite2.dbapi2


XMLCRAP = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/2002/REC-xhtml1-20020801/DTD/xhtml1-transitional.dtd">
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">'''



class Thing(object):
    consumer = None
    store = None
    
    def __init__(self, req):
        self.req = req
        self.fixed_length = False
        self._buffer = []
        storefile = req.get_options().get("OIDDiagStoreFile")
        if storefile is None:
            req.log_error("PythonOption OIDDiagStoreFile not found, using "
                          "in-memory store instead", apache.APLOG_WARNING)
            self.storefile = ":memory:"
        else:
            self.storefile = storefile

    def write(self, bytes):
        if self.fixed_length:
            self._buffer.append(bytes)
        else:
            self.req.write(bytes)

    def finish(self):
        if self._buffer:
            length = reduce(int.__add__, map(len, self._buffer))
            self.req.set_content_length(length)
            self.req.write(''.join(self._buffer))

    def handle(self, req=None):
        assert (req is None) or (req is self.req)
        req.content_type = "text/html"
        f = FieldStorage(self.req)
        openid_url = f.getfirst("openid_url")
        if openid_url is None:
            self.openingPage()
        else:
            self.otherStuff(openid_url)
        self.finish()
        return apache.OK

    def openingPage(self):
        self.fixed_length = True
        s = XMLCRAP + '''
<head>
<title>Check your OpenID</title>
</head>
<body>
<form name="openidcheck" id="openidcheck" action="" >
<p>Check an OpenID:
  <input type="text" name="openid_url" />
  <input type="submit" value="Check" /><br />
</p>
</form></body></html>'''
        self.write(s)

    def otherStuff(self, openid_url):
        s = XMLCRAP + '''
<head>
<title>Check your OpenID: %(url)s</title>
<style type="text/css">
   .status { font-size: smaller; }
</style>
</head>
<body>
<p>Checking <a href=%(urlAttrib)s>%(url)s</a>...</p>
''' % {
            'url': escape(openid_url),
            'urlAttrib': quoteattr(openid_url),
            }
        self.write(s)
        try:
            auth_request = self.fetchAndParse(openid_url)
            self.associate(auth_request)
        finally:
            self.write('</body></html>')

    def fetchAndParse(self, openid_url):
        consu = self.getConsumer()
        status, info = consu.beginAuth(openid_url)
        if status is consumer.SUCCESS:
            auth_request = info
            return auth_request

        elif status is consumer.HTTP_FAILURE:
            if info is None:
                self.write("Failed to connect to %s" % (openid_url,))
            else:
                http_code = info
                # XXX: That's not quite true - a server *somewhere*
                # returned that error, but it might have been after
                # a redirect.
                self.write("Server at %s returned error code %s" %
                           (http_code,))
            return None
        
        elif status is consumer.PARSE_ERROR:
            self.write("Did not find any OpenID information at %s" %
                       (openid_url,))
            return None
        else:
            raise AssertionError("status %r not handled" % (status,))

    def associate(self, auth_request):
        self.statusMsg("Associating with %s..." % (auth_request.server_url,))

    def statusMsg(self, msg):
        self.write('<span class="status">%s</span>\n' % (escape(msg),))

    def getConsumer(self):
        if self.consumer is None:
            if self.store is None:
                dbconn = pysqlite2.dbapi2.connect(self.storefile)
                self.store = SQLiteStore(dbconn)
                if self.storefile == ":memory:":
                    self.store.createTables()
            self.consumer = consumer.OpenIDConsumer(self.store)
        return self.consumer