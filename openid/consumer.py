import datetime
import re
import time
import urllib
import urllib2
import urlparse

from openid.constants import *
from openid.util import *
from openid.errors import *
from openid.association import *
from openid.parse import parseLinkAttrs

# Do not escape anything that is already 7-bit safe, so we do the
# minimal transform on the identity URL
def quote_minimal(s):
    res = []
    for c in s:
        if c >= u'\x80':
            for b in c.encode('utf8'):
                res.append('%%%02X' % ord(b))
        else:
            res.append(c)
    return str(''.join(res))

def normalize_url(url):
    assert isinstance(url, basestring), type(url)
    url = url.strip()
    if not (url.startswith('http://') or url.startswith('https://')):
        url = 'http://' + url

    if isinstance(url, unicode):
        parsed = urlparse.urlparse(url)
        authority = parsed[1].encode('idna')
        tail = map(quote_minimal, parsed[2:])
        encoded = (str(parsed[0]), authority) + tuple(tail)
        url = urlparse.urlunparse(encoded)
        assert type(url) is str

    return url


class SimpleHTTPClient(object):
    def get(self, url):
        f = urllib2.urlopen(url)
        try:
            data = f.read()
        finally:
            f.close()

        return (f.geturl(), data)

    def post(self, url, body):
        req = urllib2.Request(url, body)
        try:
            f = urllib2.urlopen(req)
            try:
                data = f.read()
            finally:
                f.close()
        except urllib2.HTTPError, why:
            if why.code == 400:
                try:
                    data = why.read()
                finally:
                    why.close()
                args = parsekv(data)
                error = args.get('error')
                if error is None:
                    raise ProtocolError("Unspecified Server Error: %r" %
                                        (args,))
                else:
                    raise ProtocolError("Server Response: %r" % (error,))
            else:
                raise 
            
        return (f.geturl(), data)


class OpenIDConsumer(object):
    # regexes for parsing out server url
    link_re = re.compile(r'<link(?P<linkinner>.*?)>', re.M|re.U|re.I)
    href_re = re.compile(r'.*?href\s*=\s*[\'"](?P<href>.*?)[\'"].*?',
                         re.M|re.U|re.I)
    
    def __init__(self, http_client=None, assoc_mngr=None):
        if http_client is None:
            http_client = SimpleHTTPClient()
        self.http_client = http_client
        
        if assoc_mngr is None:
            assoc_mngr = DumbAssociationManager()
        self.assoc_mngr = assoc_mngr

    def handle_request(self, url, return_to, trust_root=None, immediate=False):
        """Returns the url to redirect to or None if no identity was found."""
        url = normalize_url(url)
        
        server_info = self.find_server(url)
        if server_info is None:
            return None
        
        identity, server_url = server_info
        
        redir_args = {"openid.identity" : identity,
                      "openid.return_to" : return_to,}

        if trust_root is not None:
            redir_args["openid.trust_root"] = trust_root

        if immediate:
            mode = "checkid_immediate"
        else:
            mode = "checkid_setup"

        redir_args['openid.mode'] = mode

        assoc_handle = self.assoc_mngr.associate(server_url)
        if assoc_handle is not None:
            redir_args["openid.assoc_handle"] = assoc_handle

        return str(append_args(server_url, redir_args))

    def handle_response(self, req):
        """Handles an OpenID GET request with openid.mode in the
        arguments. req should be a Request instance, properly
        initialized with the http arguments given, and the http method
        used to make the request. Returns the expiry time of the
        session as a Unix timestamp.

        If the server returns a lifetime of 0 in dumb mode, a
        ValueMismatchError will be raised."""
        if req.http_method != 'GET':
            raise ProtocolError("Expected HTTP Method 'GET', got %r" %
                                (req.http_method,))

        func = getattr(self, 'do_' + req.mode, None)
        if func is None:
            raise ProtocolError("Unknown Mode: %r" % (req.mode,))

        return func(req)

    def determine_server_url(self, req):
        """Subclasses might extract the server_url from a cache or
        from a signed parameter specified in the return_to url passed
        to initialRequest. Returns the unix timestamp when the session
        will expire.  0 if invalid."""
        # Grab the server_url from the identity in args
        identity, server_url = self.find_server(req.identity)
        if req.identity != identity:
            raise ValueMismatchError("ID URL %r seems to have moved: %r"
                                     % (req.identity, identity))
        
        return server_url

    def find_server(self, url):
        """<--(identity_url, server_url) or None if no server
        found. Fetch url and parse openid.server and potentially
        openid.delegate urls.
        """
        identity, data = self.http_client.get(url)

        server = None
        delegate = None
        link_attrs = parseLinkAttrs(data)
        for attrs in link_attrs:
            rel = attrs.get('rel')
            if rel == 'openid.server' and server is None:
                href = attrs.get('href')
                if href is not None:
                    server = href
                    
            if rel == 'openid.delegate' and delegate is None:
                href = attrs.get('href')
                if href is not None:
                    delegate = href

        if server is None:
            return None

        if delegate is not None:
            identity = delegate
        
        return normalize_url(identity), normalize_url(server)
    
    def _dumb_auth(self, server_url, now, req):
        check_args = {}
        for k, v in req.args.iteritems():
            if k.startswith('openid.'):
                check_args[k] = v

        check_args['openid.mode'] = 'check_authentication'

        body = urllib.urlencode(check_args)
        _, data = self.http_client.post(server_url, body)
        results = parsekv(data)
        lifetime = int(results['lifetime'])
        if lifetime:
            invalidate_handle = results.get('invalidate_handle')
            if invalidate_handle is not None:
                self.assoc_mngr.invalidate(server_url, invalidate_handle)
            return datetime2timestamp(now) + lifetime
        else:
            raise ValueMismatchError("Server failed to validate signature")
        
    def do_id_res(self, req):
        now = utc_now()

        user_setup_url = req.get('user_setup_url')
        if user_setup_url is not None:
            raise UserSetupNeeded(user_setup_url)

        server_url = self.determine_server_url(req)

        assoc = self.assoc_mngr.get_association(server_url, req.assoc_handle)
        if assoc is None:
            # No matching association found. I guess we're in dumb mode...
            return self._dumb_auth(server_url, now, req)

        # Check the signature
        sig = req.sig
        signed_fields = req.signed.strip().split(',')

        _signed, v_sig = sign_reply(req.args, assoc.secret, signed_fields)
        if v_sig != sig:
            raise ValueMismatchError("Signatures did not Match: %r" %
                                     ((req.args, v_sig, assoc.secret),))

        issued = w3c2datetime(req.issued)
        valid_to = min(timestamp2datetime(assoc.expiry),
                       w3c2datetime(req.valid_to))
    
        return datetime2timestamp(now + (valid_to - issued))

    def do_error(self, req):
        error = req.get('error')
        if error is None:
            raise ProtocolError("Unspecified Server Error: %r" % (req.args,))
        else:
            raise ProtocolError("Server Response: %r" % (error,))

    def do_cancel(self, req):
        raise UserCancelled()
        