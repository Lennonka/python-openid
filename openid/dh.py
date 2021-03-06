from openid import cryptutil


def _xor(a_b):
    a, b = a_b
    return chr(ord(a) ^ ord(b))


def strxor(x, y):
    if len(x) != len(y):
        raise ValueError('Inputs to strxor must have the same length')

    return "".join(map(_xor, zip(x, y)))


class DiffieHellman(object):
    DEFAULT_MOD = int('155172898181473697471232257763715539915724801966915404479707795314057629378541917580651227423698'
                      '188993727816152646631438561595825688188889951272158842675419950341258706556549803580104870537681'
                      '476726513255747040765857479291291572334510643245094715007229621094194349783925984760375594985848'
                      '253359305585439638443')

    DEFAULT_GEN = 2

    @classmethod
    def fromDefaults(cls):
        return cls(cls.DEFAULT_MOD, cls.DEFAULT_GEN)

    def __init__(self, modulus, generator):
        self.modulus = long(modulus)
        self.generator = long(generator)

        self._setPrivate(cryptutil.randrange(1, modulus - 1))

    def _setPrivate(self, private):
        """This is here to make testing easier"""
        self.private = private
        self.public = pow(self.generator, self.private, self.modulus)

    def usingDefaultValues(self):
        return (self.modulus == self.DEFAULT_MOD and
                self.generator == self.DEFAULT_GEN)

    def getSharedSecret(self, composite):
        return pow(composite, self.private, self.modulus)

    def xorSecret(self, composite, secret, hash_func):
        dh_shared = self.getSharedSecret(composite)
        hashed_dh_shared = hash_func(cryptutil.longToBinary(dh_shared))
        return strxor(secret, hashed_dh_shared)
