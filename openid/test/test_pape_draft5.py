import unittest
import warnings

from openid.extensions.draft import pape5 as pape
from openid.message import OPENID2_NS, Message
from openid.server import server

warnings.filterwarnings('ignore', module=__name__,
                        message='"none" used as a policy URI')


class PapeRequestTestCase(unittest.TestCase):
    def setUp(self):
        self.req = pape.Request()

    def test_construct(self):
        self.assertEqual(self.req.preferred_auth_policies, [])
        self.assertIsNone(self.req.max_auth_age)
        self.assertEqual(self.req.ns_alias, 'pape')
        self.assertFalse(self.req.preferred_auth_level_types)

        bogus_levels = ['http://janrain.com/our_levels']
        req2 = pape.Request(
            [pape.AUTH_MULTI_FACTOR], 1000, bogus_levels)
        self.assertEqual(req2.preferred_auth_policies, [pape.AUTH_MULTI_FACTOR])
        self.assertEqual(req2.max_auth_age, 1000)
        self.assertEqual(req2.preferred_auth_level_types, bogus_levels)

    def test_addAuthLevel(self):
        self.req.addAuthLevel('http://example.com/', 'example')
        self.assertEqual(self.req.preferred_auth_level_types, ['http://example.com/'])
        self.assertEqual(self.req.auth_level_aliases['example'], 'http://example.com/')

        self.req.addAuthLevel('http://example.com/1', 'example1')
        self.assertEqual(self.req.preferred_auth_level_types, ['http://example.com/', 'http://example.com/1'])

        self.req.addAuthLevel('http://example.com/', 'exmpl')
        self.assertEqual(self.req.preferred_auth_level_types, ['http://example.com/', 'http://example.com/1'])

        self.req.addAuthLevel('http://example.com/', 'example')
        self.assertEqual(self.req.preferred_auth_level_types, ['http://example.com/', 'http://example.com/1'])

        self.assertRaises(KeyError, self.req.addAuthLevel, 'http://example.com/2', 'example')

        # alias is None; we expect a new one to be generated.
        uri = 'http://another.example.com/'
        self.req.addAuthLevel(uri)
        self.assert_(uri in self.req.auth_level_aliases.values())

        # We don't expect a new alias to be generated if one already
        # exists.
        before_aliases = self.req.auth_level_aliases.keys()
        self.req.addAuthLevel(uri)
        after_aliases = self.req.auth_level_aliases.keys()
        self.assertEqual(after_aliases, before_aliases)

    def test_add_policy_uri(self):
        self.assertEqual(self.req.preferred_auth_policies, [])
        self.req.addPolicyURI(pape.AUTH_MULTI_FACTOR)
        self.assertEqual(self.req.preferred_auth_policies, [pape.AUTH_MULTI_FACTOR])
        self.req.addPolicyURI(pape.AUTH_MULTI_FACTOR)
        self.assertEqual(self.req.preferred_auth_policies, [pape.AUTH_MULTI_FACTOR])
        self.req.addPolicyURI(pape.AUTH_PHISHING_RESISTANT)
        self.assertEqual(self.req.preferred_auth_policies, [pape.AUTH_MULTI_FACTOR, pape.AUTH_PHISHING_RESISTANT])
        self.req.addPolicyURI(pape.AUTH_MULTI_FACTOR)
        self.assertEqual(self.req.preferred_auth_policies, [pape.AUTH_MULTI_FACTOR, pape.AUTH_PHISHING_RESISTANT])

    def test_getExtensionArgs(self):
        self.assertEqual(self.req.getExtensionArgs(), {'preferred_auth_policies': ''})
        self.req.addPolicyURI('http://uri')
        self.assertEqual(self.req.getExtensionArgs(), {'preferred_auth_policies': 'http://uri'})
        self.req.addPolicyURI('http://zig')
        self.assertEqual(self.req.getExtensionArgs(), {'preferred_auth_policies': 'http://uri http://zig'})
        self.req.max_auth_age = 789
        self.assertEqual(self.req.getExtensionArgs(),
                         {'preferred_auth_policies': 'http://uri http://zig', 'max_auth_age': '789'})

    def test_getExtensionArgsWithAuthLevels(self):
        uri = 'http://example.com/auth_level'
        alias = 'my_level'
        self.req.addAuthLevel(uri, alias)

        uri2 = 'http://example.com/auth_level_2'
        alias2 = 'my_level_2'
        self.req.addAuthLevel(uri2, alias2)

        expected_args = {
            ('auth_level.ns.%s' % alias): uri,
            ('auth_level.ns.%s' % alias2): uri2,
            'preferred_auth_level_types': ' '.join([alias, alias2]),
            'preferred_auth_policies': '',
        }

        self.assertEqual(self.req.getExtensionArgs(), expected_args)

    def test_parseExtensionArgsWithAuthLevels(self):
        uri = 'http://example.com/auth_level'
        alias = 'my_level'

        uri2 = 'http://example.com/auth_level_2'
        alias2 = 'my_level_2'

        request_args = {
            ('auth_level.ns.%s' % alias): uri,
            ('auth_level.ns.%s' % alias2): uri2,
            'preferred_auth_level_types': ' '.join([alias, alias2]),
            'preferred_auth_policies': '',
        }

        # Check request object state
        self.req.parseExtensionArgs(request_args, is_openid1=False, strict=False)

        expected_auth_levels = [uri, uri2]

        self.assertEqual(self.req.preferred_auth_level_types, expected_auth_levels)
        self.assertEqual(self.req.auth_level_aliases[alias], uri)
        self.assertEqual(self.req.auth_level_aliases[alias2], uri2)

    def test_parseExtensionArgsWithAuthLevels_openID1(self):
        request_args = {
            'preferred_auth_level_types': 'nist jisa',
        }
        expected_auth_levels = [pape.LEVELS_NIST, pape.LEVELS_JISA]
        self.req.parseExtensionArgs(request_args, is_openid1=True)
        self.assertEqual(self.req.preferred_auth_level_types, expected_auth_levels)

        self.req = pape.Request()
        self.req.parseExtensionArgs(request_args, is_openid1=False)
        self.assertEqual(self.req.preferred_auth_level_types, [])

        self.req = pape.Request()
        self.assertRaises(ValueError, self.req.parseExtensionArgs, request_args, is_openid1=False, strict=True)

    def test_parseExtensionArgs_ignoreBadAuthLevels(self):
        request_args = {'preferred_auth_level_types': 'monkeys'}
        self.req.parseExtensionArgs(request_args, False)
        self.assertEqual(self.req.preferred_auth_level_types, [])

    def test_parseExtensionArgs_strictBadAuthLevels(self):
        request_args = {'preferred_auth_level_types': 'monkeys'}
        self.assertRaises(ValueError, self.req.parseExtensionArgs, request_args, is_openid1=False, strict=True)

    def test_parseExtensionArgs(self):
        args = {'preferred_auth_policies': 'http://foo http://bar',
                'max_auth_age': '9'}
        self.req.parseExtensionArgs(args, False)
        self.assertEqual(self.req.max_auth_age, 9)
        self.assertEqual(self.req.preferred_auth_policies, ['http://foo', 'http://bar'])
        self.assertEqual(self.req.preferred_auth_level_types, [])

    def test_parseExtensionArgs_strict_bad_auth_age(self):
        args = {'max_auth_age': 'not an int'}
        self.assertRaises(ValueError, self.req.parseExtensionArgs, args, is_openid1=False, strict=True)

    def test_parseExtensionArgs_empty(self):
        self.req.parseExtensionArgs({}, False)
        self.assertIsNone(self.req.max_auth_age)
        self.assertEqual(self.req.preferred_auth_policies, [])
        self.assertEqual(self.req.preferred_auth_level_types, [])

    def test_fromOpenIDRequest(self):
        policy_uris = [pape.AUTH_MULTI_FACTOR, pape.AUTH_PHISHING_RESISTANT]
        openid_req_msg = Message.fromOpenIDArgs({
            'mode': 'checkid_setup',
            'ns': OPENID2_NS,
            'ns.pape': pape.ns_uri,
            'pape.preferred_auth_policies': ' '.join(policy_uris),
            'pape.max_auth_age': '5476'
        })
        oid_req = server.OpenIDRequest()
        oid_req.message = openid_req_msg
        req = pape.Request.fromOpenIDRequest(oid_req)
        self.assertEqual(req.preferred_auth_policies, policy_uris)
        self.assertEqual(req.max_auth_age, 5476)

    def test_fromOpenIDRequest_no_pape(self):
        message = Message()
        openid_req = server.OpenIDRequest()
        openid_req.message = message
        pape_req = pape.Request.fromOpenIDRequest(openid_req)
        assert(pape_req is None)

    def test_preferred_types(self):
        self.req.addPolicyURI(pape.AUTH_PHISHING_RESISTANT)
        self.req.addPolicyURI(pape.AUTH_MULTI_FACTOR)
        pt = self.req.preferredTypes([pape.AUTH_MULTI_FACTOR,
                                      pape.AUTH_MULTI_FACTOR_PHYSICAL])
        self.assertEqual(pt, [pape.AUTH_MULTI_FACTOR])


class DummySuccessResponse:
    def __init__(self, message, signed_stuff):
        self.message = message
        self.signed_stuff = signed_stuff

    def isOpenID1(self):
        return False

    def getSignedNS(self, ns_uri):
        return self.signed_stuff


class PapeResponseTestCase(unittest.TestCase):
    def setUp(self):
        self.resp = pape.Response()

    def test_construct(self):
        self.assertEqual(self.resp.auth_policies, [])
        self.assertIsNone(self.resp.auth_time)
        self.assertEqual(self.resp.ns_alias, 'pape')
        self.assertIsNone(self.resp.nist_auth_level)

        req2 = pape.Response([pape.AUTH_MULTI_FACTOR],
                             "2004-12-11T10:30:44Z", {pape.LEVELS_NIST: 3})
        self.assertEqual(req2.auth_policies, [pape.AUTH_MULTI_FACTOR])
        self.assertEqual(req2.auth_time, "2004-12-11T10:30:44Z")
        self.assertEqual(req2.nist_auth_level, 3)

    def test_add_policy_uri(self):
        self.assertEqual(self.resp.auth_policies, [])
        self.resp.addPolicyURI(pape.AUTH_MULTI_FACTOR)
        self.assertEqual(self.resp.auth_policies, [pape.AUTH_MULTI_FACTOR])
        self.resp.addPolicyURI(pape.AUTH_MULTI_FACTOR)
        self.assertEqual(self.resp.auth_policies, [pape.AUTH_MULTI_FACTOR])
        self.resp.addPolicyURI(pape.AUTH_PHISHING_RESISTANT)
        self.assertEqual(self.resp.auth_policies, [pape.AUTH_MULTI_FACTOR, pape.AUTH_PHISHING_RESISTANT])
        self.resp.addPolicyURI(pape.AUTH_MULTI_FACTOR)
        self.assertEqual(self.resp.auth_policies, [pape.AUTH_MULTI_FACTOR, pape.AUTH_PHISHING_RESISTANT])

        self.assertRaises(RuntimeError, self.resp.addPolicyURI, pape.AUTH_NONE)

    def test_getExtensionArgs(self):
        self.assertEqual(self.resp.getExtensionArgs(), {'auth_policies': pape.AUTH_NONE})
        self.resp.addPolicyURI('http://uri')
        self.assertEqual(self.resp.getExtensionArgs(), {'auth_policies': 'http://uri'})
        self.resp.addPolicyURI('http://zig')
        self.assertEqual(self.resp.getExtensionArgs(), {'auth_policies': 'http://uri http://zig'})
        self.resp.auth_time = "1776-07-04T14:43:12Z"
        self.assertEqual(self.resp.getExtensionArgs(),
                         {'auth_policies': 'http://uri http://zig', 'auth_time': "1776-07-04T14:43:12Z"})
        self.resp.setAuthLevel(pape.LEVELS_NIST, '3')
        nist_args = {'auth_policies': 'http://uri http://zig', 'auth_time': "1776-07-04T14:43:12Z",
                     'auth_level.nist': '3', 'auth_level.ns.nist': pape.LEVELS_NIST}
        self.assertEqual(self.resp.getExtensionArgs(), nist_args)

    def test_getExtensionArgs_error_auth_age(self):
        self.resp.auth_time = "long ago"
        self.assertRaises(ValueError, self.resp.getExtensionArgs)

    def test_parseExtensionArgs(self):
        args = {'auth_policies': 'http://foo http://bar',
                'auth_time': '1970-01-01T00:00:00Z'}
        self.resp.parseExtensionArgs(args, is_openid1=False)
        self.assertEqual(self.resp.auth_time, '1970-01-01T00:00:00Z')
        self.assertEqual(self.resp.auth_policies, ['http://foo', 'http://bar'])

    def test_parseExtensionArgs_valid_none(self):
        args = {'auth_policies': pape.AUTH_NONE}
        self.resp.parseExtensionArgs(args, is_openid1=False)
        self.assertEqual(self.resp.auth_policies, [])

    def test_parseExtensionArgs_old_none(self):
        args = {'auth_policies': 'none'}
        self.resp.parseExtensionArgs(args, is_openid1=False)
        self.assertEqual(self.resp.auth_policies, [])

    def test_parseExtensionArgs_old_none_strict(self):
        args = {'auth_policies': 'none'}
        self.assertRaises(ValueError, self.resp.parseExtensionArgs, args, is_openid1=False, strict=True)

    def test_parseExtensionArgs_empty(self):
        self.resp.parseExtensionArgs({}, is_openid1=False)
        self.assertIsNone(self.resp.auth_time)
        self.assertEqual(self.resp.auth_policies, [])

    def test_parseExtensionArgs_empty_strict(self):
        self.assertRaises(ValueError, self.resp.parseExtensionArgs, {}, is_openid1=False, strict=True)

    def test_parseExtensionArgs_ignore_superfluous_none(self):
        policies = [pape.AUTH_NONE, pape.AUTH_MULTI_FACTOR_PHYSICAL]

        args = {
            'auth_policies': ' '.join(policies),
        }

        self.resp.parseExtensionArgs(args, is_openid1=False, strict=False)

        self.assertEqual(self.resp.auth_policies, [pape.AUTH_MULTI_FACTOR_PHYSICAL])

    def test_parseExtensionArgs_none_strict(self):
        policies = [pape.AUTH_NONE, pape.AUTH_MULTI_FACTOR_PHYSICAL]

        args = {
            'auth_policies': ' '.join(policies),
        }

        self.assertRaises(ValueError, self.resp.parseExtensionArgs, args, is_openid1=False, strict=True)

    def test_parseExtensionArgs_strict_bogus1(self):
        args = {'auth_policies': 'http://foo http://bar',
                'auth_time': 'yesterday'}
        self.assertRaises(ValueError, self.resp.parseExtensionArgs, args, is_openid1=False, strict=True)

    def test_parseExtensionArgs_openid1_strict(self):
        args = {'auth_level.nist': '0',
                'auth_policies': pape.AUTH_NONE,
                }
        self.resp.parseExtensionArgs(args, strict=True, is_openid1=True)
        self.assertEqual(self.resp.getAuthLevel(pape.LEVELS_NIST), '0')
        self.assertEqual(self.resp.auth_policies, [])

    def test_parseExtensionArgs_strict_no_namespace_decl_openid2(self):
        # Test the case where the namespace is not declared for an
        # auth level.
        args = {'auth_policies': pape.AUTH_NONE,
                'auth_level.nist': '0',
                }
        self.assertRaises(ValueError, self.resp.parseExtensionArgs, args, is_openid1=False, strict=True)

    def test_parseExtensionArgs_nostrict_no_namespace_decl_openid2(self):
        # Test the case where the namespace is not declared for an
        # auth level.
        args = {'auth_policies': pape.AUTH_NONE,
                'auth_level.nist': '0',
                }
        self.resp.parseExtensionArgs(args, is_openid1=False, strict=False)

        # There is no namespace declaration for this auth level.
        self.assertRaises(KeyError, self.resp.getAuthLevel, pape.LEVELS_NIST)

    def test_parseExtensionArgs_strict_good(self):
        args = {'auth_policies': 'http://foo http://bar',
                'auth_time': '1970-01-01T00:00:00Z',
                'auth_level.nist': '0',
                'auth_level.ns.nist': pape.LEVELS_NIST}
        self.resp.parseExtensionArgs(args, is_openid1=False, strict=True)
        self.assertEqual(self.resp.auth_policies, ['http://foo', 'http://bar'])
        self.assertEqual(self.resp.auth_time, '1970-01-01T00:00:00Z')
        self.assertEqual(self.resp.nist_auth_level, 0)

    def test_parseExtensionArgs_nostrict_bogus(self):
        args = {'auth_policies': 'http://foo http://bar',
                'auth_time': 'when the cows come home',
                'nist_auth_level': 'some'}
        self.resp.parseExtensionArgs(args, is_openid1=False)
        self.assertEqual(self.resp.auth_policies, ['http://foo', 'http://bar'])
        self.assertIsNone(self.resp.auth_time)
        self.assertIsNone(self.resp.nist_auth_level)

    def test_fromSuccessResponse(self):
        policy_uris = [pape.AUTH_MULTI_FACTOR, pape.AUTH_PHISHING_RESISTANT]
        openid_req_msg = Message.fromOpenIDArgs({
            'mode': 'id_res',
            'ns': OPENID2_NS,
            'ns.pape': pape.ns_uri,
            'pape.auth_policies': ' '.join(policy_uris),
            'pape.auth_time': '1970-01-01T00:00:00Z'
        })
        signed_stuff = {
            'auth_policies': ' '.join(policy_uris),
            'auth_time': '1970-01-01T00:00:00Z'
        }
        oid_req = DummySuccessResponse(openid_req_msg, signed_stuff)
        req = pape.Response.fromSuccessResponse(oid_req)
        self.assertEqual(req.auth_policies, policy_uris)
        self.assertEqual(req.auth_time, '1970-01-01T00:00:00Z')

    def test_fromSuccessResponseNoSignedArgs(self):
        policy_uris = [pape.AUTH_MULTI_FACTOR, pape.AUTH_PHISHING_RESISTANT]
        openid_req_msg = Message.fromOpenIDArgs({
            'mode': 'id_res',
            'ns': OPENID2_NS,
            'ns.pape': pape.ns_uri,
            'pape.auth_policies': ' '.join(policy_uris),
            'pape.auth_time': '1970-01-01T00:00:00Z'
        })

        signed_stuff = {}

        class NoSigningDummyResponse(DummySuccessResponse):
            def getSignedNS(self, ns_uri):
                return None

        oid_req = NoSigningDummyResponse(openid_req_msg, signed_stuff)
        resp = pape.Response.fromSuccessResponse(oid_req)
        self.assertIsNone(resp)


if __name__ == '__main__':
    unittest.main()
